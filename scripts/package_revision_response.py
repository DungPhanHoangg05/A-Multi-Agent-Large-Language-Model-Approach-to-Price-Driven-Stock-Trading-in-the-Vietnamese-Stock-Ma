"""Đóng gói/kiểm archive phản hồi nội bộ từ allowlist, không API hoặc inference."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.revision_reproducibility import (
    check_self_digest, digest, encoded, file_hash, local_path, offline_guard,
    read, require, safe_name, scan_bytes,
)

RELEASE = Path('outputs/revision/reviewer_response_v1')


def _rows(rows: list[dict]) -> None:
    """Từ chối trùng tên kể cả khác hoa/thường và tên vượt workspace."""
    require(bool(rows), 'Allowlist rỗng')
    names = [safe_name(row['path']) for row in rows]
    require(len({name.casefold() for name in names}) == len(names), 'Trùng archive member')
    require(all(len(row['sha256']) == 64 for row in rows), 'Hash allowlist không hợp lệ')


def build(root: Path, release: Path = RELEASE) -> dict:
    """Build một lần; khóa hash trước đọc và ghi, không glob nguồn/credentials."""
    folder = root / release
    spec = read(folder / 'package_spec.json')
    require(spec['distribution'] == 'local_private_draft_only', 'Chỉ build gói nội bộ')
    rows = spec['members']
    _rows(rows)
    archive = folder / 'private_bundle.zip'
    index = folder / 'archive_index.json'
    require(not archive.exists() and not index.exists(), 'Không ghi đè archive/index')
    members = []
    with offline_guard():
        # Kiểm toàn bộ nguồn trước khi mở file archive để lỗi nguồn không tạo gói dở.
        for row in rows:
            require(file_hash(local_path(root, row['path'])) == row['sha256'], 'Nguồn khác allowlist: ' + row['path'])
        with ZipFile(archive, 'x', compression=ZIP_DEFLATED) as z:
            for row in rows:
                data = local_path(root, row['path']).read_bytes()
                require(digest(data) == row['sha256'], 'Nguồn đổi trong khi đóng gói')
                scanned = scan_bytes(data, row['path'])
                info = ZipInfo(row['path'], (2026, 11, 5, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                z.writestr(info, data)
                members.append({**row, 'bytes': len(data), 'scanned_files': scanned})
        result = {'archive': 'private_bundle.zip', 'sha256': file_hash(archive),
                  'bytes': archive.stat().st_size, 'members': members,
                  'distribution': spec['distribution'], 'pid': None}
        index.write_bytes(encoded(result))
        verify_archive(folder)
    return {'members': len(members), 'bytes': result['bytes'], 'api_calls': 0}


def verify_archive(folder: Path) -> dict:
    """Kiểm index và từng member; không phụ thuộc data/cache workspace gốc."""
    index = read(folder / 'archive_index.json')
    rows = index['members']
    _rows(rows)
    require(index['archive'] == 'private_bundle.zip', 'Tên archive ngoài hợp đồng')
    archive = folder / 'private_bundle.zip'
    require(file_hash(archive) == index['sha256'], 'Hash toàn archive khác')
    require(archive.stat().st_size == index['bytes'], 'Kích thước archive khác')
    with ZipFile(archive) as z:
        infos = z.infolist()
        require(len(infos) == len(rows) and {i.filename for i in infos} == {r['path'] for r in rows}, 'Members thiếu/thừa/trùng')
        for info in infos:
            require((info.external_attr >> 16) & 0o170000 != 0o120000, 'Không nhận symlink')
        for row in rows:
            data = z.read(row['path'])
            require(len(data) == row['bytes'] and digest(data) == row['sha256'], 'Byte member khác: ' + row['path'])
            scan_bytes(data, row['path'])
    return {'archive_members': len(rows), 'archive_bytes': index['bytes']}


def check(root: Path, release: Path = RELEASE, archive_only: bool = False) -> dict:
    """Kiểm snapshot mới; tham chiếu lịch sử chỉ từ ZIP/member đã khóa riêng."""
    folder = root / release
    with offline_guard():
        m = read(folder / 'manifest.json')
        require(check_self_digest(m) == 'pretty_sorted_utf8_lf', 'Self-digest không khớp')
        for row in m['outputs']:
            require(file_hash(local_path(folder, row['path'])) == row['sha256'], 'Output khác: ' + row['path'])
        count = 0
        if not archive_only:
            for row in m['sources']:
                require(file_hash(local_path(root, row['path'])) == row['sha256'], 'Current source khác: ' + row['path'])
                count += 1
            for row in m['historical_references']:
                with ZipFile(local_path(root, row['archive'])) as z:
                    require(z.namelist().count(row['member']) == 1, 'Member lịch sử thiếu/trùng')
                    require(digest(z.read(safe_name(row['member']))) == row['sha256'], 'Byte nguồn lịch sử khác')
        rights = read(folder / 'rights.json')
        require(rights['public_release_authorized'] is False and rights['pid'] is None, 'Quyền/PID cần release mới')
        rows = read(folder / 'response_map.json')
        expected = {f'R{n}.{i}' for n, size in enumerate((7,4,4,5,5,3,8,5,6,6,2,4,3,3,3,10,6,3), 1) for i in range(1, size+1)}
        require(len(rows) == 87 and {r['id'] for r in rows} == expected, 'Response thiếu/trùng yêu cầu')
        require(all(r['comment_closed'] is False and r['final_pdf_locator'] is None and bool(r['response']) for r in rows), 'Closure/locator vượt evidence')
        response = local_path(root, 'revision/response_to_reviewers.md').read_bytes() if not archive_only else None
        if response is not None:
            text = response.decode('utf-8').replace('\r\n', '\n')
            require(all(text.count('### ' + r['id'] + '\n') == 1 and r['response'] in text for r in rows), 'Response/map không khớp')
            for row in rows:
                for loc in row['source_locations']:
                    p = local_path(root, loc['path'])
                    require(file_hash(p) == loc['sha256'], 'Nguồn locator đổi')
                    require(loc['anchor'] in p.read_text(encoding='utf-8').splitlines()[loc['line']-1], 'Locator sai dòng')
                for item in row['evidence']:
                    require(file_hash(local_path(root, item['path'])) == item['sha256'], 'Evidence response đổi')
        return {**verify_archive(folder), 'current_source_hashes': count,
                'output_hashes': len(m['outputs']), 'requests': len(rows),
                'comments_closed': 0, 'scope': 'archive-only' if archive_only else 'workspace-and-archive'}


def main() -> None:
    """Không tạo package public, không cung cấp lệnh upload khi thiếu quyền."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build', 'check'))
    parser.add_argument('--release', type=Path, default=RELEASE)
    parser.add_argument('--archive-only', action='store_true')
    args = parser.parse_args()
    result = build(ROOT, args.release) if args.command == 'build' else check(ROOT, args.release, args.archive_only)
    print('Archive phản hồi offline: ' + str(result))


if __name__ == '__main__':
    main()
