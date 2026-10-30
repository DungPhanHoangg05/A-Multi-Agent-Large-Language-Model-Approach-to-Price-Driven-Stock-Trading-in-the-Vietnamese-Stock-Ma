"""Kiểm offline v3 và tự resume; --verify-only cold replay, không API/refit/payoff2025."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import socket
import sys

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mt_bicl_v3_validation import run
from core.mt_bicl_v3_validation_checks import contracts
from scripts.verify_mt_bicl_development import reject_network


def main() -> None:
    """Không đọc key/client; socket bị chặn trước mọi loader/forward."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify-only", action="store_true")
    mode.add_argument("--contracts", action="store_true")
    args = parser.parse_args()
    socket.create_connection = reject_network
    socket.socket.connect = reject_network
    if args.contracts:
        result = contracts(ROOT)
        print(f"Fixture PASS: {result['tests_run']} test; receipt={result['path']}; không runtime thực nghiệm.")
        return
    result = run(ROOT, verify_only=args.verify_only)
    print(f"W11-09: {result['status']}; technical={result['technical_status']}; N={result['cohort_N']}; API=0; chưa release v3.")


if __name__ == "__main__":
    main()
