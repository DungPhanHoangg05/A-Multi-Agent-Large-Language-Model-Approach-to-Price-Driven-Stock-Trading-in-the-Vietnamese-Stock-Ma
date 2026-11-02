"""CLI riêng cho profile revision_72h; mặc định chỉ thao tác offline."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    """Lệnh smoke/run mới gọi API; mọi artifacts mới nằm ngoài run lịch sử."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "assets", "freeze", "smoke", "run", "status", "analyze", "verify", "numeric", "migrate-provider-pool"))
    parser.add_argument("--bank", type=Path, default=ROOT / "outputs/revision/r1_72h_bank_v2")
    parser.add_argument("--run", type=Path, default=ROOT / "outputs/revision/r1_72h_run_v2")
    parser.add_argument("--org", type=int, choices=range(1, 6))
    parser.add_argument("--all", action="store_true", help="Năm process độc lập, mỗi process một org")
    args = parser.parse_args()
    bank, run = args.bank.resolve(), args.run.resolve()
    try:
        if args.command == "prepare":
            from core.revision72_data import prepare
            prepare(ROOT, bank)
        elif args.command == "assets":
            from core.revision72_data import assets
            assets(ROOT, bank)
        elif args.command in ("numeric", "analyze"):
            from core.revision72_analysis import numeric, analyze
            (numeric if args.command == "numeric" else analyze)(ROOT, bank, run)
        else:
            if args.command in ("smoke", "run") and args.org:
                import os
                work = run / f"shards/org{args.org}/work"
                temporary = work / "temp"
                temporary.mkdir(parents=True, exist_ok=True)
                os.environ["TEMP"] = os.environ["TMP"] = str(temporary)
                os.environ["MPLCONFIGDIR"] = str(work / "matplotlib")
                os.environ["MPLBACKEND"] = "Agg"
            from core.revision72_run import dispatch
            dispatch(ROOT, bank, run, args.command, args.org, args.all)
    except BaseException as exc:
        from core.revision_call_archive import StudyStop
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        import os
        message = str(exc)
        for k, value in os.environ.items():
            if k.startswith("GROQ_") and k.endswith("API_KEY") and value:
                message = message.replace(value, "[REDACTED]")
        parser.exit(3 if isinstance(exc, StudyStop) else 1, f"Profile dừng: {message}\n")


if __name__ == "__main__":
    main()
