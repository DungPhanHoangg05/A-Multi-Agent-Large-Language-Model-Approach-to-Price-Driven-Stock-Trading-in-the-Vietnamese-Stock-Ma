"""CLI T22 offline: build/check/extract gói nội bộ, không publish hoặc inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main() -> None:
    """Kiểm gói không cần scientific SDK; build chỉ nhận snapshot local đã có."""
    from core.revision_reproducibility import OUTPUT, build_release, check_release, extract_release
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('build','check','extract'))
    parser.add_argument('--package',type=Path,default=OUTPUT)
    parser.add_argument('--snapshot',type=Path)
    parser.add_argument('--destination',type=Path)
    parser.add_argument('--with-weights',action='store_true')
    args=parser.parse_args()
    if args.command=='build':
        if args.snapshot is None:
            parser.error('build cần --snapshot local, không được tải model')
        result=build_release(ROOT,args.package,args.snapshot)
    elif args.command=='check':
        result=check_release(args.package,args.with_weights)
    else:
        if args.destination is None:
            parser.error('extract cần --destination mới')
        result=extract_release(args.package,args.destination,args.with_weights)
    print('T22 offline: '+json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
