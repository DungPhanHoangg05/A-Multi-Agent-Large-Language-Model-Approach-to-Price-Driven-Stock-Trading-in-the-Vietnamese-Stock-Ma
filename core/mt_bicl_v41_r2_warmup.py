"""Warmup r2 độc lập; người dùng tải lại VCI, giữ nguyên giá nghiên cứu từ2018."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from core.execution_prices import load_verified_execution_data
from core.mt_bicl_v4_completion import DataCompletionError
from core.mt_bicl_v4_dataset import immutable
from core.mt_bicl_v4_protocol import canonical, checksum, read
from core.mt_bicl_v4_warmup import PendingWarmup, combine_warmup
from core.mt_bicl_v41_r2_data import NAMESPACE

COLLECTION = NAMESPACE / 'collection'
RELEASE = Path('docs/plan/week11/collection_release_v4_1_r2.json')


def load(root: Path, release: dict[str, Any], *, fetch: Callable[..., Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Cache trước fetch; mất raw đã seal là lỗi integrity, không tự thay bằng nguồn mới."""
    ready_path = root / COLLECTION / 'warmup_verified.json'
    sealed = read(ready_path.read_bytes()) if ready_path.exists() else None
    settings = release['warmup']
    frames, receipts = {}, {}
    for symbol in release['config']['symbol_order']:
        path = root / COLLECTION / 'warmup' / (symbol + '.json')
        if sealed is not None and (not path.exists() or checksum(path.read_bytes()) != sealed['symbols'][symbol]['sha256']):
            raise DataCompletionError('Warmup r2 đã seal bị mất/sửa: ' + symbol)
        if path.exists():
            document = read(path.read_bytes())
        else:
            if fetch is None:
                raise PendingWarmup('Chưa có warmup r2 ' + symbol + '; cần người dùng chạy lệnh collection')
            url = f'https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/{symbol}/price-history'
            records, pages = fetch(url, {'fromDate': settings['start'].replace('-', ''), 'toDate': settings['end'].replace('-', '')})
            document = {'symbol': symbol, 'start': settings['start'], 'end': settings['end'], 'records': records, 'pages': pages}
            base, _ = load_verified_execution_data(root / 'data/execution_prices', symbol)
            combine_warmup(symbol, records, base, settings)
            immutable(path, document)
        if (set(document) != {'symbol', 'start', 'end', 'records', 'pages'} or document['symbol'] != symbol
                or document['start'] != settings['start'] or document['end'] != settings['end']):
            raise DataCompletionError('Identity warmup r2 khác release')
        base, _ = load_verified_execution_data(root / 'data/execution_prices', symbol)
        frames[symbol], proof = combine_warmup(symbol, document['records'], base, settings)
        receipts[symbol] = {**proof, 'path': path.relative_to(root).as_posix(), 'sha256': checksum(path.read_bytes())}
        print(f'Warmup r2 {symbol}: {proof["pre_anchor_rows"]} nến trước2018, overlap{proof["overlap_rows"]} PASS.', flush=True)
    ready = {'version': 'conditional_v4_1_r2_warmup_verified', 'symbols': receipts,
             'no_research_price_or_label_replacement': True, 'pre2018_labels_created': False}
    immutable(ready_path, ready)
    return frames, ready


def identity(root: Path, release: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Identity mới bind release/panel/raw warmup; không tái dùng chữ ký hoặc UUID lượt cũ."""
    frames, warmup = load(root, release)
    binding = {'release_sha256': checksum((root / RELEASE).read_bytes()), 'warmup': warmup,
               'panel_manifest_sha256': release['panel_sha256'], 'runtime_namespace': NAMESPACE.as_posix()}
    immutable(root / COLLECTION / 'identity.json', binding)
    return frames, warmup, checksum(canonical(binding))
