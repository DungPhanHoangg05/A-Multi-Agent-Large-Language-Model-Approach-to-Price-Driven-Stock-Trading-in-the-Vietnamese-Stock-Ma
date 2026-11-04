"""CLI T23 offline, không provider SDK/worker hoặc inference mới."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main() -> None:
    """Replay mới từ package, hoặc check hash-only release đã có."""
    from core.revision_clean_replay import OUTPUT, PACKAGE, build_release, check_release
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('build','check'))
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--package',type=Path,default=PACKAGE)
    parser.add_argument('--runtime-release',type=Path)
    args=parser.parse_args()
    if args.command=='check': print('T23 hashes: '+str(check_release(ROOT,args.output)))
    else:
        result=build_release(ROOT,args.output,args.package,args.runtime_release)
        print(f"T23 PASS: {result['raw_predictions_reparsed']} predictions, {result['accounts_rebuilt_from_prices']} accounts, API=0.")


if __name__=='__main__':
    main()
