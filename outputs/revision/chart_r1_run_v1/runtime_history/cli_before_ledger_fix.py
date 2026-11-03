"""Rerun chart riêng qua pool Free hiện có; prepare/status không gọi API."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.revision72_provider import RoutedLLM
from core.revision72_run import checked, freeze, signed
from core.revision_common_study import write_json
from core.revision_call_archive import StudyStop

OLD = ROOT / "outputs/revision/r1_72h_run_v2"
BANK = ROOT / "outputs/revision/r1_72h_bank_v2"
RUN = ROOT / "outputs/revision/chart_r1_run_v1"
R4_BANK = ROOT / "outputs/revision/chart_r4_bank_v1"
R4_RUN = ROOT / "outputs/revision/chart_r4_run_v1"


def sha(path: Path) -> str:
    """Hash byte nguồn/copy, không đọc hoặc hash credentials."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PatternCacheOnly(RoutedLLM):
    """Cache miss của Pattern dừng trước SDK; các node khác giữ routing hiện hành."""
    def invoke(self, prompt: object, **kwargs: object) -> object:
        if self.kwargs.get("metadata", {}).get("langgraph_node") == "Pattern Agent":
            raise StudyStop("Pattern cache miss trong chart rerun; không tự tạo thêm Pattern response")
        return super().invoke(prompt, **kwargs)


def verify_preparation() -> dict:
    """Từ chối sửa code, policy hoặc các raw copies trước resume."""
    value = checked(RUN / "chart_rerun_preparation.json")
    for record in value["sources"]:
        if sha(ROOT / record["path"]) != record["sha256"]:
            raise ValueError("Nguồn chart rerun đã đổi: " + record["path"])
    for record in value["copies"]:
        if sha(RUN / record["path"]) != record["sha256"]:
            raise ValueError("Pattern raw copy đã đổi")
    if checked(RUN / "run_manifest.json")["sha256"] != value["run_signature"]:
        raise ValueError("Rerun identity không khớp preparation")
    return value


def prepare() -> None:
    """Khóa run mới và copy Pattern raw nguyên byte, không thay chart/node cũ."""
    if (RUN / "chart_rerun_preparation.json").exists():
        verify_preparation(); print("Preparation đã khóa và vẫn khớp."); return
    if RUN.exists():
        raise FileExistsError("Run đã có nhưng chưa có preparation; cần kiểm tra trước khi tiếp tục")
    identity = freeze(ROOT, BANK, RUN)
    copies, sources = [], [Path(__file__), ROOT / "tests/test_chart_rerun.py", ROOT / "revision/r1_provider_policy.json",
                          ROOT / "revision/chart_convention_policy.json", ROOT / "outputs/revision/chart_convention_v1/rerun_protocol.json"]
    for request in sorted(OLD.glob("shards/org*/calls/*.request.json")):
        value = checked(request)
        if value["context"].get("node") != "Pattern Agent":
            continue
        for suffix in ("request", "response", "response_digest", "error"):
            source = request.with_name(request.name.replace(".request.", "." + suffix + "."))
            if not source.exists():
                continue
            relative = source.relative_to(OLD); dest = RUN / relative
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, dest)
            copies.append({"path": relative.as_posix(), "origin": source.relative_to(ROOT).as_posix(), "sha256": sha(source)})
            sources.append(source)
    if len({r["path"] for r in copies if r["path"].endswith(".request.json")}) != 140:
        raise ValueError("Thiếu raw Pattern attempts của run cũ")
    preparation = signed({"schema_version": "chart_rerun_preparation_v1", "run_signature": identity["sha256"],
        "execution_policy": "provider_only_five_author_asserted_free_orgs", "internal_attempt_caps": None,
        "reuse": "Only unchanged Pattern raw calls; original files/call IDs preserved with origin hashes. CachedLLM must match exact messages/context; a miss raises before network. Copied historical calls are not new calls.",
        "copies": copies, "sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)} for p in sorted(set(sources))]})
    write_json(RUN / "chart_rerun_preparation.json", preparation, True)
    verify_preparation(); print("Đã freeze chart rerun và raw Pattern reuse, chưa gọi API.")


def prepare_r4() -> None:
    """Dựng lại 90 prompts từ Trend mới, giữ panel/donor/order R4 đã khóa."""
    verify_preparation()
    if R4_BANK.exists():
        from core.revision_r4_run import verify_bank
        verify_bank(ROOT, R4_BANK); print("Bank corrected-chart R4 đã khóa."); return
    from core.revision_r4_factorial import controlled_prompt, prompt_parts, VARIANTS
    from core.revision_r4_run import prepare as freeze_r4
    old_bank = ROOT / "outputs/revision/r4_value_bank_v1/manifest.json"
    original = checked(old_bank); units, sources = [], [old_bank, Path(__file__), RUN / "chart_rerun_preparation.json"]
    for old in original["units"]:
        unit = old["unit"]; key = unit["id"]
        matches = list(RUN.glob(f"shards/org*/decisions/{key}_r0_AS_n0.json"))
        if len(matches) != 1:
            raise ValueError("Chưa đủ corrected upstream/AS cho R4: " + key)
        path = matches[0]; decision = checked(path)
        asset_path = BANK / f"features/{unit['symbol']}_{unit['decision']}.json"
        donor_path = BANK / f"features/{unit['symbol']}_{old['donor_index']}.json"
        asset, donor = checked(asset_path), checked(donor_path)
        if (asset["sha256"], donor["sha256"]) != (old["asset_hash"], old["donor_hash"]):
            raise ValueError("Asset/donor R4 đổi")
        parts = prompt_parts(decision["state"]["decision_prompt"])
        row = deepcopy(old); row["prompts"] = {v: controlled_prompt(parts, asset, donor, v) for v in VARIANTS}
        from core.revision_common_study import digest
        row["prompt_hashes"] = {v: digest(t) for v, t in row["prompts"].items()}
        row["upstream_parent_hash"] = decision["parent"]["upstream_hash"]
        row["original_request_id"] = decision["request_ids"][-1]
        row["corrected_chart_source"] = {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)}
        units.append(row); sources += [path, asset_path, donor_path]
    freeze_r4(ROOT, R4_BANK, units, sources)


def main() -> None:
    """Chỉ smoke/run/run-r4 gọi pool Free; không mua quota hoặc đổi model."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "smoke", "run", "status", "prepare-r4", "run-r4"))
    parser.add_argument("--all", action="store_true"); parser.add_argument("--org", type=int, choices=range(1, 6))
    args = parser.parse_args()
    try:
        if args.command == "prepare": prepare(); return
        if args.command == "prepare-r4": prepare_r4(); return
        value = verify_preparation()
        if args.command == "status":
            copied = {r["path"] for r in value["copies"] if r["path"].endswith(".request.json")}
            requests = list(RUN.glob("shards/org*/calls/*.request.json"))
            decisions = [checked(p) for p in RUN.glob("shards/org*/decisions/*.json")]
            print(json.dumps({"new_attempts": sum(p.relative_to(RUN).as_posix() not in copied for p in requests),
                  "reused_pattern_attempts": len(copied), "research_decisions": sum(not r["context"]["smoke"] for r in decisions),
                  "smoke_decisions": sum(r["context"]["smoke"] for r in decisions), "execution_policy": "provider_only", "internal_attempt_caps": None}, indent=2)); return
        if args.command == "run-r4":
            prepare_r4()
            command = [sys.executable, "-X", "utf8", str(ROOT / "scripts/run_revision_r4.py"), "run", "--bank", str(R4_BANK), "--run", str(R4_RUN)]
            command += ["--all"] if args.all else ["--org", str(args.org)] if args.org else []
            raise SystemExit(subprocess.call(command, cwd=ROOT))
        if args.all and not args.org:
            children = [subprocess.Popen([sys.executable, "-X", "utf8", str(Path(__file__).resolve()), args.command, "--org", str(i)],
                        cwd=ROOT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) for i in range(1, 6)]
            codes = [p.wait() for p in children]
            raise SystemExit(0 if not any(codes) else 3)
        if not args.org:
            parser.error("smoke/run cần --all hoặc --org")
        work = RUN / f"shards/org{args.org}/work"
        temporary = work / "temp"; temporary.mkdir(parents=True, exist_ok=True)
        os.environ["TEMP"] = os.environ["TMP"] = str(temporary)
        os.environ["MPLCONFIGDIR"] = str(work / "matplotlib")
        os.environ["MPLBACKEND"] = "Agg"
        import core.revision72_run as runner
        with patch.object(runner, "RoutedLLM", PatternCacheOnly):
            runner.worker(ROOT, BANK, RUN, args.org, args.command == "smoke")
            if args.command == "run": runner.complete(BANK, RUN)
    except BaseException as exc:
        if isinstance(exc, (SystemExit, KeyboardInterrupt)): raise
        message = str(exc)
        for k, v in os.environ.items():
            if k.startswith("GROQ_") and k.endswith("API_KEY") and v: message = message.replace(v, "[REDACTED]")
        parser.exit(3 if isinstance(exc, StudyStop) else 1, "Chart rerun dừng có checkpoint: " + message + "\n")


if __name__ == "__main__":
    main()
