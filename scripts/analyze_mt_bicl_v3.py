"""Cold audit/account/report/nomination v3 offline; không API, train hoặc payoff2025."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v21_preparation import file_hash
from core.mt_bicl_v3_audit import ACCOUNTS, OUTPUT, VERSION as ACCOUNT_VERSION, rebuild, evidence
from core.mt_bicl_v3_analysis import VERSION, build_report, nominate, figure_bytes
from core.mt_bicl_v3_unbounded import RuntimeSession
from core.prior_run_lock import PriorRunLock

REPORT = OUTPUT/"analysis/report.json"
FIGURE = OUTPUT/"analysis/results.png"
NOMINATION = Path("docs/plan/week11/development_nomination_v3.json")
NOMINATION_VERSION = "utility_icl_development_nomination_v3"
CODE = ("core/mt_bicl_v3_audit.py", "core/mt_bicl_v3_analysis.py", "scripts/analyze_mt_bicl_v3.py",
        "tests/test_mt_bicl_v3_analysis.py", "tests/test_mt_bicl_v3_analysis_leakage.py")


def source_binding(root: Path) -> dict:
    """Khóa đúng consumer mới trước mở payoff, không thay source thí nghiệm đã hoàn tất."""
    commit = subprocess.check_output(["git", "log", "-1", "--format=%H", "--", *CODE], cwd=root, text=True).strip()
    for name in CODE:
        if subprocess.check_output(["git", "show", commit+":"+name], cwd=root) != (root/name).read_bytes():
            raise ValueError("Consumer chưa neo Git: "+name)
    return {"source_commit": commit, "source_sha256": {n: file_hash(root/n) for n in CODE}}


def save(root: Path, path: Path, version: str, value: dict, verify_only: bool) -> None:
    """Output immutable, cold verify phải khớp toàn payload thay vì tin cờ PASS."""
    if verify_only or (root/path).exists():
        if read_envelope(root/path, version) != value: raise ValueError("Artifact khác kết quả tái dựng: "+str(path))
    else:
        write_envelope(root/path, version, value, immutable=True)


def main() -> None:
    """Một lệnh hoàn tất W11-12; verify-only tái dựng từ raw/source đến nomination và hình."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    def reject(*a: object, **k: object) -> None: raise AssertionError("Phân tích offline không được network")
    socket.create_connection = socket.socket.connect = reject
    with RuntimeSession(ROOT, "report_replay" if args.verify_only else "cold_verification"):
        with PriorRunLock(ROOT/"outputs/oos_pilot/api_usage.json.lock", "shared-account-ledger-v2"):
            binding = source_binding(ROOT)
            source, protocol, ledger = rebuild(ROOT)
            source["binding"].update(binding)
            report = build_report(source, protocol, ledger)
            result = nominate(report, protocol)
            image = figure_bytes(report)
            save(ROOT, ACCOUNTS, ACCOUNT_VERSION, source, args.verify_only)
            save(ROOT, REPORT, VERSION, report, args.verify_only)
            result["binding"] = {**binding, **evidence(ROOT), "accounts_path": ACCOUNTS.as_posix(),
                "accounts_sha256": file_hash(ROOT/ACCOUNTS), "report_path": REPORT.as_posix(),
                "report_sha256": file_hash(ROOT/REPORT), "protocol_sha256": file_hash(ROOT/"docs/plan/week11/protocol_v3.json"),
                "runtime_policy_sha256": file_hash(ROOT/"docs/plan/week11/runtime_policy_v3.json")}
            save(ROOT, NOMINATION, NOMINATION_VERSION, result, args.verify_only)
            if args.verify_only or (ROOT/FIGURE).exists():
                if (ROOT/FIGURE).read_bytes() != image: raise ValueError("Hình khác report vừa dựng lại")
            else:
                (ROOT/FIGURE).write_bytes(image)
            if args.verify_only and subprocess.check_output(["git", "show", "HEAD:"+NOMINATION.as_posix()], cwd=ROOT) != (ROOT/NOMINATION).read_bytes():
                raise ValueError("Nomination chưa neo đúng byte Git")
    print(f"W11-12 PASS: {result['status']}; D Full−Original={result['metrics']['D_Full_Original_pp']:.6f} đpt; Full−Fact_Anchor={result['metrics']['D_Full_Fact_Anchor_pp']:.6f} đpt; chưa quyền xác nhận2025.")


if __name__ == "__main__":
    main()
