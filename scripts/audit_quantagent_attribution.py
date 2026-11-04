"""Kiểm evidence T16 từ snapshots đã khóa; không import source/SDK hoặc truy cập mạng."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'outputs/revision/quantagent_attribution_v1'


def sha(data: bytes) -> str:
    """Hash nguyên byte, không chuẩn hóa snapshots lịch sử."""
    return hashlib.sha256(data).hexdigest()


def redacted_snapshot(data: bytes) -> tuple[bytes, int]:
    """Che mẫu giống credential trong bản chia sẻ; không sửa blob/workspace gốc."""
    return re.subn(rb'gsk_[A-Za-z0-9]{20,}|sk-proj-[A-Za-z0-9_-]{20,}',
                   b'[REDACTED_CREDENTIAL_PATTERN]', data)


def symbols(data: bytes) -> dict[str, dict]:
    """Đọc AST tĩnh, giữ tên lồng nhau và hash/locator, tuyệt đối không exec/import."""
    tree = ast.parse(data.decode('utf-8-sig'))
    lines = data.decode('utf-8-sig').splitlines(keepends=True)
    result = {}

    def walk(nodes: list[ast.stmt], prefix: str = '') -> None:
        """Khóa AST không gồm tọa độ; hash đoạn source vẫn có scope riêng."""
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + node.name
                result[name] = {'line': node.lineno, 'end_line': node.end_lineno,
                                'ast_sha256': sha(ast.dump(node, include_attributes=False).encode('utf-8')),
                                'source_segment_sha256': sha(''.join(lines[node.lineno-1:node.end_lineno]).encode('utf-8'))}
                walk(node.body, name + '.')
    walk(tree.body)
    return result


def file_comparison(upstream: bytes, initial: bytes | None, current: bytes, python: bool) -> dict:
    """So file và symbol; AST equality không khẳng định equivalence hay nguồn tác giả duy nhất."""
    result = {'upstream_sha256': sha(upstream), 'initial_local_sha256': sha(initial) if initial is not None else None, 'current_sha256': sha(current),
              'initial_exact_bytes': upstream == initial if initial is not None else None, 'current_exact_bytes': upstream == current,
              'initial_equal_after_lf': upstream.replace(b'\r\n', b'\n') == initial.replace(b'\r\n', b'\n') if initial is not None else None,
              'current_equal_after_lf': upstream.replace(b'\r\n', b'\n') == current.replace(b'\r\n', b'\n')}
    if python:
        states = {'upstream': symbols(upstream), 'initial_local': symbols(initial) if initial is not None else None, 'current': symbols(current)}
        result['symbols'] = states
        for name in ('initial_local', 'current'):
            result[f'{name}_identical_ast_symbols'] = [k for k, v in states['upstream'].items()
                if k in states[name] and v['ast_sha256'] == states[name][k]['ast_sha256']] if states[name] is not None else None
    return result


def verify(folder: Path, root: Path = ROOT) -> int:
    """Kiểm hashes, toàn bộ ZIP members và tái tính file/AST comparison không network."""
    manifest = json.loads((folder / 'manifest.json').read_bytes()); count = 0
    for group, base in (('sources', root), ('outputs', folder)):
        for row in manifest[group]:
            path = (base / row['path']).resolve()
            if not path.is_relative_to(base.resolve()) or sha(path.read_bytes()) != row['sha256']:
                raise ValueError('Hash/đường dẫn thay đổi: ' + row['path'])
            count += 1
    evidence = json.loads((folder / 'attribution.json').read_bytes())
    with zipfile.ZipFile(folder / 'sources.zip') as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != {r['member'] for r in evidence['snapshot_members']}:
            raise ValueError('ZIP có duplicate/thừa/thiếu members')
        for row in evidence['snapshot_members']:
            data = archive.read(row['member'])
            if sha(data) != row['sha256'] or redacted_snapshot(data)[1]:
                raise ValueError('Snapshot đổi: ' + row['member'])
        for row in evidence['file_components']:
            current = archive.read(row['current_member'])
            safe_current, _ = redacted_snapshot((root / row['local_path']).read_bytes())
            if current != safe_current:
                raise ValueError('Current source không khớp snapshot: ' + row['local_path'])
            if row['upstream_path'] is None:
                if row['classification'] != 'new_to_comparison': raise ValueError('Sai scope thành phần bổ sung')
                continue
            upstream = archive.read(row['upstream_member'])
            initial = archive.read(row['initial_member']) if row['initial_member'] is not None else None
            actual = file_comparison(upstream, initial, current, row['local_path'].endswith('.py'))
            if actual != row['comparison'] or row['classification'] != ('reused' if upstream == current else 'modified'):
                raise ValueError('Comparison/classification không tái lập: ' + row['local_path'])
        license_bytes = archive.read('upstream/LICENSE')
        if license_bytes != (root / 'LICENSES/QuantAgent-MIT.txt').read_bytes():
            raise ValueError('MIT notice không giữ nguyên byte upstream')
        if b'Copyright (c) 2025 Y-Research @SBU' not in license_bytes:
            raise ValueError('Thiếu copyright upstream')
    return count


def main() -> None:
    """Chỉ kiểm release đã có; không tải Git, tạo SDK hoặc ghi đè output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--check', action='store_true', required=True)
    args = parser.parse_args()
    print(f'T16 PASS: {verify(args.output)} hashes; ZIP và file/AST comparison khớp, không gọi API.')


if __name__ == '__main__':
    main()
