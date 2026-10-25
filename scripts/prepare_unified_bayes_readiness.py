"""Dry-run/coverage/MDE và readiness U-BICL từ nguồn đã khóa; không có chế độ gọi API."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.research_cohort import read_envelope
from core.unified_bayes_memory import OUTPUT as MEMORY_PATH
from core.unified_bayes_readiness import build_assessment, publish
from core.unified_bayes_source import NAMESPACE, PLAN_PATH, SOURCE, load_source
from scripts.run_unified_bayes import authorize, offline_client

OUTPUT = NAMESPACE / "development/readiness"


def main() -> None:
    """Mặc định verify-only; prepare chỉ thêm artifact, không sửa plan/run hoặc ledger."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--validation-audit", type=Path, required=True)
    args = parser.parse_args()
    if not args.validation_audit.resolve().is_relative_to((NAMESPACE / "validation").resolve()):
        raise ValueError("Audit phải thuộc namespace validation U-BICL")
    models = read_envelope(ROOT / SOURCE / "plan.json")["inputs"]["signal_config"]["models"]
    with offline_client(models, OUTPUT / "unused_ledger.json", OUTPUT / "unused_cache") as llm:
        cohort = load_source(llm)
        plan = cohort.read_plan(PLAN_PATH, llm)
        expected = build_assessment(cohort, plan, llm, read_envelope(ROOT / MEMORY_PATH), args.validation_audit)
        publish(OUTPUT, expected, cohort, plan, llm, prepare=args.prepare)
        authorize(plan, args.validation_audit.parent / "technical_gates.json", OUTPUT / "execution_readiness.json")
        print(f"Dry-run/readiness nguồn PASS: {len(plan['requests'])} điểm; coverage/repeat/MDE đã khóa, "
              "HTTP/payoff query=0; chưa preflight, handoff hoặc release xác nhận")


if __name__ == "__main__":
    main()
