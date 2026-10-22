"""Chuẩn bị/verify memory và diagnostics train offline, không có lệnh gọi LLM."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.bic_icl_diagnostics import build_train_diagnostics
from core.bic_icl_memory import FrozenSources, METHOD_SHA, build_memory, build_revision_index, sha
from core.historical_signals import digest
from core.improvement_protocol import code_identity
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once, runtime_identity

NAMESPACE = ROOT/'outputs/bayesian_benchmark/bic_icl_v2'


def component_identity() -> dict[str, str]:
    """Ghim dependency thực thi bằng LF; checksum bằng chứng vẫn theo byte."""
    return {**code_identity(), **{name: hashlib.sha256((ROOT/name).read_text('utf-8').encode()).hexdigest()
        for name in ('core/bic_icl_memory.py', 'core/bic_icl_statistics.py',
                     'core/bic_icl_diagnostics.py', 'scripts/prepare_bic_icl_memory.py')}}


def prepare(destination: Path, *, kind: str, verify_only: bool = False) -> dict[str, Any]:
    """Rebuild cùng producer khi verify; không dùng checksum tự khai thay semantic."""
    destination = destination.resolve()
    if not destination.is_relative_to(NAMESPACE.resolve()) or destination == NAMESPACE.resolve():
        raise ValueError('Artifact cần thư mục con riêng trong namespace bic_icl_v2')
    if kind not in ('memory', 'train'):
        raise ValueError('Chỉ chuẩn bị memory hoặc train, không chạy cohort Decision')
    sources = FrozenSources()
    identity = component_identity()
    runtime = runtime_identity()
    if kind == 'memory':
        memory, adapter = build_memory(sources)
        legacy = adapter.load_price_feature_index('outputs/bayesian_benchmark/price_features/candidate_index_v1.json')
        index = build_revision_index(memory, adapter, legacy)
        outputs = {'memory.json': memory.payload, 'index.json': index.payload}
    else:
        outputs = {'diagnostics.json': build_train_diagnostics(sources, progress=lambda s: print(s, flush=True))}
    sources.verify()
    if component_identity() != identity or runtime_identity() != runtime:
        raise ValueError('Code/runtime thay đổi giữa lúc producer đang chạy')
    receipt = {'version': 'bic_icl_preparation_v1', 'kind': kind, 'method_sha256': METHOD_SHA,
        'code_sha256': identity, 'runtime': runtime, 'outputs': {name: digest(value) for name, value in outputs.items()}}
    if verify_only:
        if read_envelope(destination/'receipt.json') != receipt:
            raise ValueError('Receipt khác code/runtime/nguồn hoặc output tái dựng')
        for name, value in outputs.items():
            if read_envelope(destination/name) != value:
                raise ValueError(f'Artifact khác semantic tái dựng: {name}')
    else:
        for name, value in outputs.items():
            _write_once(destination/name, value)
        _write_once(destination/'receipt.json', receipt)
    return {'status': 'VERIFIED' if verify_only else 'PREPARED', 'kind': kind,
        'receipt_sha256': sha(destination/'receipt.json'), 'output_hashes': receipt['outputs']}


def main() -> None:
    """Chỉ nhận tác vụ offline và destination rõ ràng, không đọc khóa/API/quota."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=('memory', 'train'), required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    print(prepare(args.destination, kind=args.kind, verify_only=args.verify), flush=True)


if __name__ == '__main__':
    main()
