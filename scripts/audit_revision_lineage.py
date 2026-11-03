"""Đối soát duplication legacy bằng ngày thật, không xác nhận request từ tên nhánh."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from itertools import combinations
import json
from pathlib import Path
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs/revision/legacy_lineage_v1"
TREES = ("outputs/backtest_result", "outputs/robustness", "outputs/ablation")
DECISION_FIELDS = ("prediction", "correct", "confidence", "risk_reward_ratio",
                   "time_sec", "decision_source", "fallback_reason", "error")
MARKET_FIELDS = ("window_start", "window_end", "actual_direction", "actual_pct_change",
                 "actual_prev_close", "actual_next_close", "entry_open", "exit_close",
                 "entry_time", "exit_time")
ACCOUNT_FIELDS = ("executed_action", "execution_skip_reason", "account_return", "equity",
                  "cash_vnd", "shares", "position_value_vnd", "equity_vnd",
                  "transaction_fee_vnd", "slippage_cost_vnd", "pnl")


def json_bytes(value: Any) -> bytes:
    """Tuần tự hóa xác định, không chấp nhận NaN hoặc Infinity."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def sha(data: bytes) -> str:
    """Hash nguyên byte, giữ nguyên CRLF của bằng chứng gốc."""
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> bytes:
    """Đọc lịch sử Git cục bộ; commit lưu file không phải commit thực thi."""
    return subprocess.check_output(["git", *args], cwd=ROOT)


def normalize(value: dict, path: str) -> list[dict]:
    """Tách stream, giữ missing là null và từ chối ngày trùng hoặc nhãn sai."""
    points = value["test_points"]
    if not points or len(points) != value["n_tests"]:
        raise ValueError(f"Số điểm không khớp: {path}")
    variants = value.get("variants", ("full", "baseline"))
    streams = []
    for variant in variants:
        rows = []
        for point in points:
            if "variants" in point:
                decision = {key: point["variants"][variant].get(key) for key in DECISION_FIELDS}
                account = {key: None for key in ACCOUNT_FIELDS}
            else:
                suffix = "full" if variant == "full" else "no_alpha"
                mapping = {"prediction": "pred", "risk_reward_ratio": "rr",
                           "time_sec": "time", "fallback_reason": "decision_fallback_reason"}
                decision = {key: point.get(f"{mapping.get(key, key)}_{suffix}" +
                            ("_sec" if key == "time_sec" else "")) for key in DECISION_FIELDS}
                account = {key: point.get(f"{key.removesuffix('_vnd')}_{suffix}_vnd"
                           if key.endswith("_vnd") else f"{key}_{suffix}") for key in ACCOUNT_FIELDS}
            if decision["prediction"] not in ("LONG", "SHORT") or point["actual_direction"] not in ("UP", "DOWN"):
                raise ValueError(f"Nhãn không hợp lệ: {path}")
            rows.append({"test_id": point["test_id"], "cutoff": point["window_end"],
                         "market": {key: point.get(key) for key in MARKET_FIELDS},
                         "decision": decision, "account": account})
        cutoffs = [r["cutoff"] for r in rows]
        if cutoffs != sorted(set(cutoffs)):
            raise ValueError(f"Ngày trùng hoặc không tăng dần: {path}")
        streams.append({"id": f"{path}#{variant}", "path": path, "symbol": value["symbol"],
                        "variant": variant, "panel": value.get("panel"), "scenario": value.get("scenario"),
                        "protocol_recorded": value.get("protocol"),
                        "timestamps_recorded": {k: value.get(k) for k in ("started_at", "ended_at", "updated_at")},
                        "summary_recorded": next((r for r in value.get("summary", {}).get("rows", [])
                                                  if r.get("variant") == variant), None),
                        "n": len(rows), "cutoff_hash": sha(json_bytes(cutoffs)),
                        "prediction_hash": sha(json_bytes([r["decision"]["prediction"] for r in rows])),
                        "request_id": None, "parent_artifact_id": None, "actual_prompt_hash": None,
                        "model_revision": "unknown", "execution_commit": "unknown",
                        "branch_execution_status": "unverified", "rows": rows})
    return streams


def compare(left: dict, right: dict) -> dict:
    """Joins theo symbol/cutoff, không so vị trí hoặc suy reuse từ prediction trùng."""
    if left["symbol"] != right["symbol"]:
        raise ValueError("Không ghép hai mã khác nhau")
    lrows = {r["cutoff"]: r for r in left["rows"]}
    rrows = {r["cutoff"]: r for r in right["rows"]}
    common = sorted(lrows.keys() & rrows.keys())
    counts = {}
    for section, fields in (("market", MARKET_FIELDS), ("decision", DECISION_FIELDS), ("account", ACCOUNT_FIELDS)):
        for field in fields:
            pairs = [(lrows[d][section][field], rrows[d][section][field]) for d in common]
            counts[f"{section}.{field}"] = {
                "both_present": sum(a is not None and b is not None for a, b in pairs),
                "equal_present": sum(a is not None and b is not None and a == b for a, b in pairs),
                "missing_either": sum(a is None or b is None for a, b in pairs)}
    identical = bool(common) and len(common) == left["n"] == right["n"] and all(
        lrows[d]["decision"]["prediction"] == rrows[d]["decision"]["prediction"] for d in common)
    intended = left["variant"] == right["variant"] == "baseline" and left["panel"] == right["panel"] and (
        left["panel"] in ("norm", "weights")) and left["protocol_recorded"] == right["protocol_recorded"] == "shared_upstream_across_alpha_configs"
    return {"left": left["id"], "right": right["id"], "symbol": left["symbol"],
            "n_common": len(common), "n_left_only": len(lrows.keys() - rrows.keys()),
            "n_right_only": len(rrows.keys() - lrows.keys()), "identical_prediction_sequence": identical,
            "classification": ("intended_shared_control_parent_unverified" if intended and identical else
                               "duplicate_sequence_execution_unverified" if identical else "no_complete_duplicate"),
            "counts": counts}


def build() -> tuple[dict[str, bytes], list[dict]]:
    """Đóng băng phạm vi legacy, mọi cặp cùng mã và mã nguồn lịch sử liên quan."""
    files = sorted(p for tree in TREES for p in (ROOT / tree).rglob("*") if p.is_file())
    sources = [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p.read_bytes()),
                "size_bytes": p.stat().st_size} for p in files]
    streams = []
    history = []
    for p in files:
        relative = p.relative_to(ROOT).as_posix()
        if p.suffix == ".json":
            value = json.loads(p.read_bytes())
            if "test_points" in value:
                streams.extend(normalize(value, relative))
        events = git("log", "--format=%H", "--", relative).decode().splitlines()
        first = git("show", f"{events[-1]}:{relative}") if events else None
        equal_json = (json.loads(first) == json.loads(p.read_bytes())) if first and p.suffix == ".json" else None
        history.append({"path": relative, "file_commits": events, "execution_commit": "unknown",
                        "earliest_retained_blob_sha256": sha(first) if first else None,
                        "current_equals_earliest_blob_bytes": first == p.read_bytes() if first else None,
                        "current_equals_earliest_after_crlf_comparison":
                            first.replace(b"\r\n", b"\n") == p.read_bytes().replace(b"\r\n", b"\n")
                            if first and p.suffix in (".json", ".csv") else None,
                        "current_equals_earliest_json_content": equal_json})
    pairs = [compare(a, b) for a, b in combinations(streams, 2) if a["symbol"] == b["symbol"]]
    snapshots = {}
    for revision, paths in {
        "cc7153ea": ("core/run_robustness.py", "core/backtest_engine.py", "utils/graph_setup.py"),
        "c9371886": ("scripts/run_ablation_matrix.py", "core/backtest_engine.py", "utils/graph_setup.py"),
    }.items():
        commit = git("rev-parse", revision).decode().strip()
        for path in paths:
            name = f"historical_sources/{revision}/{path}"
            snapshots[name] = git("show", f"{commit}:{path}")
    coverage = Counter(s["symbol"] for s in streams)
    report = {"schema_version": "legacy_lineage_v1", "scope": list(TREES),
              "artifact_count": len(files), "point_artifact_count": len({s["path"] for s in streams}),
              "stream_count": len(streams), "row_count": sum(s["n"] for s in streams),
              "streams_by_symbol": dict(sorted(coverage.items())), "pair_count": len(pairs),
              "duplicate_pair_count": sum(p["identical_prediction_sequence"] for p in pairs),
              "classifications": dict(Counter(p["classification"] for p in pairs)),
              "authenticated_legacy_requests": 0, "submission_snapshot": "unverified",
              "git_json_content_matches_earliest_retained": sum(r["current_equals_earliest_json_content"] is True for r in history),
              "root_cause": "unknown; duplicate predictions do not establish reuse or independent execution",
              "policy": "legacy audit only; Git commits and stored flags do not authenticate executed requests"}
    outputs = {"report.json": json_bytes(report), "streams.json": json_bytes(streams),
               "comparisons.json": json_bytes(pairs), "git_history.json": json_bytes(history), **snapshots}
    for path in ("scripts/audit_revision_lineage.py", "tests/test_revision_lineage.py"):
        p = ROOT / path
        sources.append({"path": path, "sha256": sha(p.read_bytes()), "size_bytes": p.stat().st_size})
    return outputs, sources


def verify(folder: Path) -> int:
    """Từ chối nguồn hoặc output khác byte, không chạy lại inference."""
    manifest = json.loads((folder / "manifest.json").read_bytes())
    checked = 0
    for group, base in (("sources", ROOT), ("outputs", folder)):
        for item in manifest[group]:
            if sha((base / item["path"]).read_bytes()) != item["sha256"]:
                raise ValueError(f"Hash không khớp: {item['path']}")
            checked += 1
    return checked


def main() -> None:
    """Tạo release mới hoặc kiểm lại cả hash và kết quả tái tính xác định."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        count = verify(args.output)
        outputs, _ = build()
        for name, content in outputs.items():
            if (args.output / name).read_bytes() != content:
                raise ValueError(f"Tái tính không khớp: {name}")
        print(f"Đối soát PASS: {count} hash và {len(outputs)} outputs tái lập nguyên byte.")
        return
    if args.output.exists():
        raise FileExistsError("Output đã tồn tại; dùng --check hoặc chọn thư mục mới")
    outputs, sources = build()
    args.output.mkdir(parents=True)
    for name, content in outputs.items():
        path = args.output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest = {"schema_version": "legacy_lineage_manifest_v1", "sources": sources,
                "outputs": [{"path": name, "sha256": sha(data)} for name, data in sorted(outputs.items())]}
    (args.output / "manifest.json").write_bytes(json_bytes(manifest))
    print(f"Đã đóng băng audit legacy: {verify(args.output)} hash; chưa xác thực request lịch sử.")


if __name__ == "__main__":
    main()
