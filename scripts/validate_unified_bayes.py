"""Diagnostics và bốn gate offline U-BICL; readiness/API vẫn có bước nghiệm thu riêng."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.research_cohort import read_envelope
from core.research_input_lock import _write_once
from core.unified_bayes_memory import OUTPUT as MEMORY_PATH
from core.unified_bayes_source import NAMESPACE, PLAN_PATH, SOURCE, load_source
from core.unified_bayes_validation import diagnostics, read_diagnostics, read_validation, run_gates
from scripts.run_unified_bayes import offline_client

OUTPUT = NAMESPACE / "validation"


def main() -> None:
    """Cold load nguồn/request đã khóa; chỉ ghi namespace validation mới khi được yêu cầu."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--run-gates", action="store_true")
    modes.add_argument("--verify-audit", type=Path)
    parser.add_argument("--diagnostics", type=Path, default=OUTPUT / "diagnostics.json")
    args = parser.parse_args()
    if not args.diagnostics.resolve().is_relative_to(OUTPUT.resolve()):
        raise ValueError("Diagnostics chỉ thuộc namespace validation riêng")
    if args.verify_audit and not args.verify_audit.resolve().is_relative_to(OUTPUT.resolve()):
        raise ValueError("Audit chỉ thuộc namespace validation riêng")
    models = read_envelope(ROOT / SOURCE / "plan.json")["inputs"]["signal_config"]["models"]
    with offline_client(models, OUTPUT / "unused_usage.json", OUTPUT / "unused_cache") as llm:
        cohort = load_source(llm)
        plan = cohort.read_plan(PLAN_PATH, llm)
        expected = diagnostics(cohort, plan, llm, read_envelope(ROOT / MEMORY_PATH))
        if args.prepare:
            _write_once(args.diagnostics, expected)
            read_diagnostics(args.diagnostics, expected)
        elif args.run_gates:
            audit = run_gates(plan, expected, OUTPUT)
            print(f"Bốn gate/diagnostics PASS; audit: {audit}")
        elif args.verify_audit:
            read_validation(args.verify_audit, plan, expected)
        else:
            read_diagnostics(args.diagnostics, expected)
        print(f"Diagnostics nguồn/PIT/prompt PASS: {len(expected['points'])} điểm; chưa cấp readiness U10-09")


if __name__ == "__main__":
    main()
