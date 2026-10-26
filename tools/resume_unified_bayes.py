"""Mở tiếp run U-BICL đã có journal; giữ nguyên kernel và receipt nguồn đã khóa."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from pathlib import Path
import sys
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.historical_signals import digest
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once
from core.unified_bayes_cohort import CohortRun
from scripts import run_unified_bayes as cli

ADAPTER_PATH = Path(__file__).resolve()
RECEIPT_NAME = "resume_entrypoint_v1.json"
VALIDATION = ROOT / "outputs/bayesian_benchmark/unified_bic_v1/validation/20261025T220030_8658658ad88c4fe1ba8b33afe7e273de"
READINESS = ROOT / "outputs/bayesian_benchmark/unified_bic_v1/development/readiness/execution_readiness.json"


def adapter_sha256() -> str:
    """Khóa byte adapter riêng, không thay hash code/plan/receipt của kernel cũ."""
    return hashlib.sha256(ADAPTER_PATH.read_bytes()).hexdigest()


class ResumedCohort(CohortRun):
    """Chỉ nạp journal hiện hữu; không so slot đã tiến triển với trạng thái planned."""

    def __init__(self, cohort: Any, plan: dict[str, Any], llm: Any, root: Path,
                 ledger: Path, *, record: bool = False) -> None:
        self._adapter_binding: dict[str, Any] | None = None
        if not (Path(root) / "cohort.json").is_file() or not (Path(root) / "journal/identity.json").is_file():
            raise ValueError("Resume cần cohort và journal đã tồn tại; không khởi tạo run mới")
        super().__init__(cohort, plan, llm, root, ledger, create=False)
        expected = {"adapter_version": "unified_bic_resume_entrypoint_v1",
            "policy": "OPEN_EXISTING_COHORT_AND_JOURNAL_CREATE_FALSE",
            "adapter_path": "tools/resume_unified_bayes.py", "adapter_sha256": adapter_sha256(),
            "run_signature": self.signature, "plan_sha256": digest(plan),
            "execution_code_sha256": plan["code_sha256"], "runtime": plan["runtime"],
            "split": plan["split"], "changes_request_or_scientific_protocol": False}
        self._adapter_binding = expected
        path = self.root / RECEIPT_NAME
        if record:
            _write_once(path, expected)
        elif not path.exists():
            self._adapter_binding = None
        self._control()

    def _control(self) -> None:
        """Giữ mọi guard kernel, thêm kiểm byte adapter và receipt trước HTTP/retry."""
        super()._control()
        expected = self._adapter_binding
        if expected is not None and (adapter_sha256() != expected["adapter_sha256"] or
                digest(read_envelope(self.root / RECEIPT_NAME)) != digest(expected)):
            raise ValueError("Adapter resume hoặc receipt đã đổi; dừng, giữ nguyên checkpoint")


@contextmanager
def existing_journal_entrypoint(*, record: bool) -> Iterator[None]:
    """Đổi riêng cách mở handle; giữ nguyên parser, authorization, key và dispatch CLI."""
    previous = cli.CohortRun
    def open_existing(cohort: Any, plan: dict[str, Any], llm: Any, root: Path,
                      ledger: Path, *, create: bool = False) -> ResumedCohort:
        """Tham số create từ CLI cũ không được khởi tạo lại journal khi resume."""
        return ResumedCohort(cohort, plan, llm, root, ledger, record=record)
    cli.CohortRun = open_existing
    try:
        yield
    finally:
        cli.CohortRun = previous


def main(argv: list[str] | None = None) -> None:
    """Mặc định kiểm offline; --run --resume mới cho CLI cũ đọc key/gọi API."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for name in ("run", "verify-only", "report", "verify-report"):
        modes.add_argument("--" + name, action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--repeats", action="store_true")
    parser.add_argument("--technical-gates", type=Path, default=VALIDATION / "technical_gates.json")
    parser.add_argument("--readiness", type=Path, default=READINESS)
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args(argv)
    if args.run and not args.resume:
        parser.error("Run phục hồi bắt buộc --resume")
    if not args.run and (args.resume or args.repeats or args.env_file):
        parser.error("Resume/repeats/env-file chỉ dùng với --run")
    if args.run:
        path = cli.RUN_PATH / "preflight.json"
        if not path.is_file() or read_envelope(path).get("status") != "complete":
            raise ValueError("Cần preflight đã complete trong run cũ trước lệnh phục hồi")
        flags = ["--run", "--resume", "--technical-gates", str(args.technical_gates),
                 "--readiness", str(args.readiness)]
        if args.repeats:
            flags.append("--repeats")
        if args.env_file:
            flags += ["--env-file", str(args.env_file)]
    else:
        flags = ["--report" if args.report else "--verify-report" if args.verify_report else "--verify-only"]
    previous_argv = sys.argv
    try:
        sys.argv = [str(ADAPTER_PATH), *flags]
        with existing_journal_entrypoint(record=args.run):
            cli.main()
    finally:
        sys.argv = previous_argv


if __name__ == "__main__":
    main()
