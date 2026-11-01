"""Chuẩn bị, chạy từng đợt và phân tích study Full/baseline chung snapshot cho R1."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.revision_common_study import prepare_bank, prepare_features, run_full, verify_bank, verify_features


def main() -> None:
    """Mặc định không gọi API; lệnh run yêu cầu budget request rõ ràng."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "features", "preflight", "run", "analyze"))
    parser.add_argument("--bank", type=Path, default=ROOT / "outputs/revision/r1_common_bank_v2")
    parser.add_argument("--run", type=Path, default=ROOT / "outputs/revision/r1_common_run_v2")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/revision/r1_common_analysis_v2")
    parser.add_argument("--protocol", type=Path, default=ROOT / "revision/r1_common_protocol.json")
    parser.add_argument("--max-requests", type=int, help="Trần attempt cộng dồn của đúng run, không phải budget mỗi lần resume")
    parser.add_argument("--workers", type=int, default=4, help="Worker CPU cho feature bank, từ 1 tới 4; không phải agent LLM")
    args = parser.parse_args()
    bank, run = args.bank.resolve(), args.run.resolve()
    try:
        if args.command == "prepare":
            manifest = prepare_bank(ROOT, bank, args.protocol.resolve())
            print(f"Đã khóa {manifest['n_test']} test, {manifest['n_calibration']} calibration; tối thiểu {manifest['nominal_llm_requests']} requests.")
        elif args.command == "features":
            count = prepare_features(ROOT, bank, args.workers)
            print(f"Feature bank hoàn tất: {count} điểm. Không gọi API LLM.")
        elif args.command == "preflight":
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
            manifest = verify_bank(ROOT, bank)
            verify_features(bank, manifest)
            configured = bool(os.environ.get("GROQ_API_KEY"))
            print(f"Nguồn/feature PASS; API key đã cấu hình: {configured}; nominal requests: {manifest['nominal_llm_requests']}.")
            if not configured:
                parser.exit(2, "Thiếu GROQ_API_KEY; chưa gọi inference.\n")
        elif args.command == "run":
            if args.max_requests is None:
                parser.error("run cần --max-requests; không tự dùng budget không giới hạn")
            run_full(ROOT, bank, run, args.max_requests)
        else:
            from core.revision_common_analysis import analyze
            analyze(ROOT, bank, run, args.output.resolve())
    except BaseException as exc:
        from core.revision_call_archive import StudyStop
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        secret = os.environ.get("GROQ_API_KEY", "")
        message = str(exc).replace(secret, "[REDACTED]") if secret else str(exc)
        parser.exit(3 if isinstance(exc, StudyStop) else 1, f"Study dừng: {message}\n")


if __name__ == "__main__":
    main()
