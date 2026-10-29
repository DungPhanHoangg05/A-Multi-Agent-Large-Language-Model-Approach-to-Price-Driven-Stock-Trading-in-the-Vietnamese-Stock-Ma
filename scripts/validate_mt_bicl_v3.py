"""Kiểm offline v3 và tự resume; --verify-only cold replay, không API/refit/payoff2025."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mt_bicl_v3_validation import run
from scripts.verify_mt_bicl_development import reject_network


def main() -> None:
    """Không đọc key/client; socket bị chặn trước mọi loader/forward."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    socket.create_connection = reject_network
    socket.socket.connect = reject_network
    result = run(ROOT, verify_only=args.verify_only)
    print(f"W11-09: {result['status']}; technical={result['technical_status']}; N={result['cohort_N']}; API=0; chưa release v3.")


if __name__ == "__main__":
    main()
