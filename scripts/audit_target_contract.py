"""Audit D2-08: giá/label tường minh, legacy ambiguous và actual prompt đã khóa."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
import textwrap

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jsonschema
import numpy as np
import pandas as pd

from agents.decision_agent import _build_compact_prompt_en
from core.revision_baselines import load_prices
from core.revision72_run import checked
from scripts.analyze_revision_statistics import load_panel, csv_text
from utils.target_contract import target_fields

OUTPUT = ROOT / "outputs/revision/target_contract_v1"


def read(path: Path) -> dict:
    """Đọc JSON không thay nguồn."""
    return json.loads(path.read_bytes())


def sha(path: Path) -> str:
    """Hash byte nguyên bản, kể cả CRLF lịch sử."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_bytes(value: object) -> bytes:
    """Từ chối NaN/Infinity và giữ null cho dữ liệu chưa xác minh."""
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def message_text(value: object) -> str:
    """Chỉ lấy text đã archive, không render lại request bằng source hiện tại."""
    if isinstance(value, dict):
        return "\n".join([value["content"]] if isinstance(value.get("content"), str) else
                         [message_text(v) for v in value.values()])
    if isinstance(value, list):
        return "\n".join(message_text(v) for v in value)
    return ""


def manuscript_artifacts() -> dict[str, bytes]:
    """Sinh ví dụ từ builder giữ nguyên, chỉ wrap prose/pretty-print JSON để in."""
    example = _build_compact_prompt_en("{stock_name}", "{time_frame}", 5, True, True,
        "{h_desc}", "{h_val}", "{h_note}", "{trend_report}", "{pattern_report}", "{indicator_report}", "{alpha_report}", "{sentiment_report}")
    wrapped = []
    for line in example.splitlines():
        if line.startswith('{"decision"'):
            wrapped.extend(json.dumps(json.loads(line), indent=2).splitlines())
        else:
            wrapped.extend(textwrap.wrap(line, width=75, break_long_words=False, break_on_hyphens=False) or [""])
    prompt = "\n".join([r"\begin{framed}", r"\begin{small}", r"\begin{verbatim}", *wrapped,
                          r"\end{verbatim}", r"\end{small}", r"\end{framed}", ""])
    table = r"""\begin{table}[htbp]
\centering\small
\caption{Canonical evaluation fields recorded after inference, outside graph inputs.}
\label{tab:target_schema}
\begin{tabularx}{\linewidth}{lX}
\hline
Field & Meaning \\
\hline
\texttt{decision\_close} & Observed $C_{e-1}$, never substituted for entry. \\
\texttt{entry\_open} & Candidate next-bar entry $O_e$. \\
\texttt{exit\_close} & Immutable target close $C_{e+L-1}$. \\
\texttt{gross\_return} & Fraction $C_{e+L-1}/O_e-1$, before costs. \\
\texttt{net\_return} & Candidate LONG fraction after both cost legs, Eq.~\eqref{eq:label}; not necessarily an executed account return. \\
\texttt{label\_net} & Primary UP iff net return $>0$; DOWN otherwise. \\
\texttt{label\_gross} & Secondary UP iff gross return $>0$; DOWN otherwise. \\
\texttt{decision\_bar\_index} & Zero-based final observed bar $e-1$. \\
\texttt{target\_horizon\_bars} & Complete observed-bar horizon $L$, not calendar days. \\
\texttt{label\_fee\_each\_side} & Fee rate used for the immutable label. \\
\texttt{label\_slippage\_each\_side} & Slippage rate used for the immutable label. \\
\texttt{label\_contract\_version} & \texttt{net\_cycle\_v1} for new records; \texttt{legacy\_unverified} when canonical provenance is missing. \\
\hline
\end{tabularx}
\par\smallskip\footnotesize Canonical returns are fractions; legacy \texttt{actual\_pct\_change} is net percent and \texttt{execution\_pct\_change} is gross percent. New records retain \texttt{actual\_direction} as a net-label alias. Historical \texttt{actual\_prev\_close} is not automatically renamed: its meaning is unverified without the original snapshot. SHORT is a DOWN forecast with CASH execution, not a short sale. Zero returns map to DOWN; incomplete horizons are not shortened. Execution stress costs/delays do not relabel the fixed target.
\end{table}
"""
    return {"prompt_example_en.txt": (example + "\n").encode(), "target_prompt_excerpt.tex": prompt.encode(),
            "target_schema_table.tex": table.encode()}


def generate() -> tuple[dict[str, bytes], list[Path]]:
    """Kiểm 102 labels/predictions, legacy field aliases và từng actual decision request."""
    rows, sources = load_panel()
    bank_path = ROOT / "outputs/revision/r1_72h_bank_v2/manifest.json"
    bank = read(bank_path)
    protocol = bank["protocol"]
    frames, _ = load_prices(ROOT / protocol["price_snapshot"], protocol["price_quality_policy"])
    schema_path = ROOT / "revision/target_schema.json"
    schema = read(schema_path)
    indexed = {(r["unit_id"], r["variant"]): r for r in rows}
    labels = []
    for unit in bank["units"]:
        record = target_fields(frames[unit["symbol"]], int(unit["decision"] + 1), 3,
                               protocol["fee_each_side"], protocol["slippage_each_side"])
        jsonschema.validate(record, schema)
        for variant in {r["variant"] for r in rows}:
            expected = indexed[(unit["id"], variant)]
            if record["label_net"] != expected["label_net"] or record["label_gross"] != expected["label_gross"]:
                raise ValueError("Label mới không khớp release gốc")
        labels.append({"unit_id": unit["id"], "symbol": unit["symbol"], "fold": unit["fold"], "date": unit["date"], **record})
    legacy_manifest = ROOT / "outputs/revision/legacy_lineage_v1/manifest.json"
    legacy = []
    for source in read(legacy_manifest)["sources"]:
        if not source["path"].endswith(".json") or not source["path"].startswith(("outputs/backtest_result/", "outputs/robustness/", "outputs/ablation/")):
            continue
        path = ROOT / source["path"]
        if sha(path) != source["sha256"]:
            raise ValueError("Legacy source đã đổi")
        value = read(path)
        if "test_points" not in value:
            continue
        sources.append(path)
        for p in value["test_points"]:
            legacy.append({"path": source["path"], "symbol": value["symbol"], "test_id": p["test_id"], "cutoff": p["window_end"],
                "stored_actual_prev_close": p.get("actual_prev_close"), "entry_open": p.get("entry_open"), "exit_close": p.get("exit_close"),
                "actual_prev_equals_entry": bool(np.isclose(p["actual_prev_close"], p["entry_open"], atol=1e-10, rtol=0)),
                "decision_close": None, "decision_close_provenance": "unverified_original_snapshot_not_authenticated",
                "stored_label_net": p["actual_direction"], "stored_net_percent": p["actual_pct_change"]})
    prompts, counts = [], Counter()
    for run_name in ("r1_72h_run_v2", "r4_value_run_v1"):
        for path in sorted((ROOT / "outputs/revision" / run_name).glob("shards/org*/calls/*.request.json")):
            request = checked(path)
            if request["context"]["stage"] != "decision":
                continue
            text = message_text(request["messages"])
            vi = all(marker in text for marker in ("LONG", "SHORT", "Open", "Close", "0,25%", "0,10%", "MỖI chiều", "CASH"))
            en = all(marker in text for marker in ("LONG", "SHORT", "Open", "Close", "0.25%", "0.10%", "EACH", "CASH"))
            if not vi and not en:
                raise ValueError("Actual prompt không chứng minh hợp đồng net hai chiều: " + path.name)
            prompts.append({"run": run_name, "path": path.relative_to(ROOT).as_posix(), "sha256": sha(path),
                "unit_id": request["context"]["unit_id"], "smoke": bool(request["context"]["smoke"]),
                "net_contract_present": True, "legacy_horizon_token_present": "T+2.5" in text, "n_chars": len(text)})
            sources.append(path)
            counts[run_name] += 1
    if len(labels) != 102 or len(legacy) != 600:
        raise ValueError("Target/legacy support không đủ")
    agent = ROOT / "agents/decision_agent.py"
    r4_bank = ROOT / "outputs/revision/r4_value_bank_v1/manifest.json"
    if sha(agent) != next(r["sha256"] for r in read(r4_bank)["source_hashes"] if r["path"] == "agents/decision_agent.py"):
        raise ValueError("Không được nhận prompt builder đã đổi là source R4 gốc")
    report = {"scope": "D2-08 schema/prose correction; target, predictions and archived prompts unchanged",
              "n_units": len(labels), "n_predictions_reconciled": len(rows), "n_legacy_point_records": len(legacy),
              "legacy_prev_equals_entry_count": sum(r["actual_prev_equals_entry"] for r in legacy),
              "legacy_decision_close_authenticated": 0, "decision_requests_by_run": dict(counts),
              "n_gross_net_label_disagreements": sum(r["label_net"] != r["label_gross"] for r in labels),
              "agent_source_unchanged_against_r4": True, "n_new_api_calls": 0,
              "limits": "Prompt legacy T+2.5 token is not a verified settlement guarantee; canonical fields are outcomes outside graph inputs; custom costs only offline unless separately versioned prompt/protocol"}
    outputs = {"report.json": json_bytes(report), "canonical_labels.csv": csv_text(labels).encode(),
               "legacy_field_audit.csv": csv_text(legacy).encode(), "actual_prompt_audit.csv": csv_text(prompts).encode(),
               **manuscript_artifacts()}
    sources += [bank_path, legacy_manifest, r4_bank, schema_path, agent, ROOT / "agents/agent_state.py",
        ROOT / "utils/target_contract.py", ROOT / "core/backtest_engine.py", ROOT / "core/run_robustness.py",
        ROOT / "scripts/run_ablation_matrix.py", Path(__file__).resolve(), ROOT / "tests/test_target_contract.py",
        ROOT / "core/revision_baselines.py", ROOT / "core/alpha_compare.py", ROOT / "scripts/analyze_revision_statistics.py",
        ROOT / "revision/requirements-r1.txt", ROOT / "tests/test_paired_protocol.py",
        ROOT / "tests/test_ablation_matrix.py", ROOT / "tests/test_robustness_sweep.py",
        ROOT / "outputs/revision/r1_prices_v1/manifest.json", *sorted((ROOT / "outputs/revision/r1_prices_v1").glob("*.csv"))]
    return outputs, sorted(set(sources))


def main() -> None:
    """Không ghi đè release; --check tái tính đúng byte và kiểm runtime/source hashes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if OUTPUT.exists() and not args.check:
        raise FileExistsError("Release đã có; dùng --check")
    runtime = {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "jsonschema": version("jsonschema")}
    checked_count = 0
    if args.check:
        manifest = read(OUTPUT / "manifest.json")
        if manifest["runtime"] != runtime:
            raise ValueError("Runtime không khớp")
        for group, base in (("sources", ROOT), ("outputs", OUTPUT)):
            for r in manifest[group]:
                if sha(base / r["path"]) != r["sha256"]:
                    raise ValueError("Hash đã đổi: " + r["path"])
                checked_count += 1
    outputs, sources = generate()
    for name, content in outputs.items():
        if args.check:
            if (OUTPUT / name).read_bytes() != content:
                raise ValueError("Tái lập không khớp: " + name)
        else:
            OUTPUT.mkdir(exist_ok=True)
            (OUTPUT / name).write_bytes(content)
        if name.endswith(".tex"):
            path = ROOT / "paper/generated" / name
            if args.check:
                if path.read_bytes() != content:
                    raise ValueError("Bảng/prompt excerpt khác release")
            else:
                path.write_bytes(content)
    if not args.check:
        manifest = {"schema_version": "target_contract_release_v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                    "runtime": runtime, "sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)} for p in sources],
                    "outputs": [{"path": name, "sha256": sha(OUTPUT / name)} for name in outputs]}
        (OUTPUT / "manifest.json").write_bytes(json_bytes(manifest))
    print(f"PASS D2-08: {len(outputs)} outputs; {checked_count} hashes khi kiểm lại; không gọi API.")


if __name__ == "__main__":
    main()
