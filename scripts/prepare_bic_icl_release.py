"""Khóa/phát hành hoặc verify release development VERIFIED_CACHE hoàn toàn offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.bic_icl_protocol import CohortSources, NAMESPACE, namespace_path
from core.bic_icl_release import LEDGER, RELEASE_ROOT, issue_development_release, verify_development_release
from core.research_cohort import read_envelope


def main(argv: list[str] | None = None) -> None:
    """Mặc định verify; không có cờ online hoặc khả năng đọc credential."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--issue', action='store_true', help='Khóa snapshot và ghi release sau bốn gate')
    mode.add_argument('--verify-only', action='store_true', help='Dựng lại semantic và kiểm release đã có')
    parser.add_argument('--plan', type=Path, default=NAMESPACE/'development_plan_release_v2.json')
    parser.add_argument('--output-dir', type=Path, default=NAMESPACE/'development_run_release_v2')
    parser.add_argument('--release', type=Path, default=RELEASE_ROOT/'development_release_v1.json')
    parser.add_argument('--technical-gates', type=Path, required=True)
    parser.add_argument('--ledger', type=Path, default=LEDGER)
    args = parser.parse_args(argv)
    plan = read_envelope(namespace_path(args.plan, 'plan'))
    options = {'run_root': args.output_dir, 'ledger_path': args.ledger}
    if args.issue:
        result = issue_development_release(args.release, args.technical_gates, plan, CohortSources(), **options)
    else:
        result = verify_development_release(args.release, args.technical_gates, plan, **options)
    print(json.dumps({'status': 'RELEASED' if args.issue else 'VERIFIED',
        'plan_sha256': result['plan_sha256'], 'run_root': result['run_binding']['run_root'],
        'context_lock_sha256': result['decision_context_lock_sha256'],
        'request_manifest_sha256': result['request_manifest_sha256'],
        'decision_calls': 0, 'confirmation_allowed': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
