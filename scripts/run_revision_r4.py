"""CLI R4: status/verify/analyze offline; chỉ run mới dùng năm key thật trong .env."""

from __future__ import annotations

import argparse
from pathlib import Path
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main() -> None:
    """Không sửa R1–R3 hoặc tự gọi network từ status/verify/analyze."""
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('status','verify','run','analyze'))
    p.add_argument('--bank',type=Path,default=ROOT/'outputs/revision/r4_value_bank_v1')
    p.add_argument('--run',type=Path,default=ROOT/'outputs/revision/r4_value_run_v1')
    p.add_argument('--org',type=int,choices=range(1,6));p.add_argument('--all',action='store_true')
    args=p.parse_args();bank=args.bank.resolve();run=args.run.resolve()
    try:
        from core.revision_r4_run import verify_bank,collect,worker
        m=verify_bank(ROOT,bank)
        if args.command=='run':
            if args.all and args.org:p.error('Chọn --all hoặc --org')
            if args.all:
                processes=[subprocess.Popen([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'run','--org',str(i),
                    '--bank',str(bank),'--run',str(run)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) for i in range(1,6)]
                codes=[process.wait() for process in processes]
                if any(codes):p.exit(3,f'R4 có checkpoint; mã thoát từng shard: {codes}. Chạy lại cùng lệnh sau khi provider khả dụng.\n')
            elif args.org:worker(ROOT,bank,run,args.org)
            else:p.error('run cần --all hoặc --org')
        else:
            records=collect(m,run)
            attempts=len(list(run.glob('shards/org*/calls/*.request.json')))
            print(f'R4: {len(records)}/270 Decision executions; {attempts} attempts; 0 vision calls mới.')
            if args.command=='analyze':
                if len(records)!=270:raise ValueError('Chưa đủ 270 executions; không xuất kết luận từ lượt dở')
                from scripts.analyze_revision_r4 import analyze_new
                analyze_new(m,records,run,bank)
    except BaseException as exc:
        if isinstance(exc,(SystemExit,KeyboardInterrupt)):raise
        message=str(exc)
        for k,v in os.environ.items():
            if k.startswith('GROQ_') and k.endswith('API_KEY') and v:message=message.replace(v,'[REDACTED]')
        p.exit(3,'R4 dừng có checkpoint: '+message+'\n')


if __name__=='__main__':main()
