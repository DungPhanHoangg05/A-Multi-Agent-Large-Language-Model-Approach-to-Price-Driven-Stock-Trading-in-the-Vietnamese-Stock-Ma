"""Mirror checkpoint ngoài dự án sau mỗi raw response; không sao chép credential."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Any

from core.mt_bicl_v4_dataset import encoded
from core.mt_bicl_v4_protocol import checksum, read
from core.mt_bicl_v41_r2_data import DATA, DOC, NAMESPACE
from core.mt_bicl_v41_r2_warmup import COLLECTION, RELEASE


def write_atomic(path: Path, raw: bytes) -> None:
    """Đóng/fsync file tạm trước replace; lỗi ghi không phá bản sao trước đó."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def checkpoint(root: Path, destination: Path | None = None) -> dict[str, Any]:
    """Mirror whitelist bằng chứng; raw/nguồn đã khóa không được ghi đè khác hash."""
    destination = destination or Path.home() / 'Documents/CodexRecovery/mt_bicl_v4_1_r2'
    if destination.resolve().is_relative_to(root.resolve()):
        raise ValueError('Bản sao runtime phải nằm ngoài thư mục dự án')
    release = read((root / RELEASE).read_bytes())
    static = {**release['input_sha256'], **release['news_sha256'], **release['numeric_artifact_sha256'],
              **release['receipt_sha256'], **release['historical_evidence']['surviving_evidence_sha256']}
    paths = set(static) | {RELEASE.as_posix(), 'outputs/oos_pilot/api_usage.json'}
    paths.update(p.relative_to(root).as_posix() for p in (root / COLLECTION).rglob('*.json') if p.name != 'run.owner.json')
    manifest, copied = {}, 0
    for name in sorted(paths):
        source = (root / name).resolve()
        target = (destination / name).resolve()
        if not source.is_relative_to(root.resolve()) or not target.is_relative_to(destination.resolve()):
            raise ValueError('Đường dẫn mirror nằm ngoài phạm vi')
        raw = source.read_bytes()
        sha = checksum(raw)
        if name in static and sha != static[name]:
            raise ValueError('Nguồn mirror khác bằng chứng khóa: ' + name)
        if target.exists():
            if checksum(target.read_bytes()) == sha:
                manifest[name] = sha
                continue
            if name in static or '/http_cache/' in name or '/warmup/' in name or name.endswith('/complete.json'):
                raise ValueError('Bản sao immutable khác hash; giữ cả hai phía: ' + name)
        write_atomic(target, raw)
        if checksum(target.read_bytes()) != sha:
            raise OSError('Không xác minh được byte sau khi sao lưu: ' + name)
        manifest[name] = sha
        copied += 1
    result = {'version': 'conditional_v4_1_r2_runtime_mirror', 'files_sha256': manifest,
              'credentials_copied': False, 'copied_this_checkpoint': copied}
    write_atomic(destination / 'mirror_manifest.json', encoded(result))
    return {'path': str(destination), 'files': len(manifest), 'copied': copied}
