"""Kiểm guard archive phản hồi, không chạy inference hoặc thống kê lại."""
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile, ZipInfo

from core.revision_reproducibility import encoded, digest, file_hash, read
from scripts.package_revision_response import build, verify_archive, check


class ResponsePackageTests(unittest.TestCase):
    """Dữ liệu nhỏ kiểm tamper, nguồn, traversal và credential trước bàn giao."""

    def setUp(self) -> None:
        """Mỗi test có workspace độc lập, không dùng package thật."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / 'release'
        self.folder.mkdir()
        (self.root / 'example.txt').write_bytes(b'fixture')
        self.spec([{'path': 'example.txt', 'sha256': digest(b'fixture')}])

    def spec(self, rows: list[dict]) -> None:
        """Allowlist phải ghi rõ nội bộ; không suy quyền từ file tồn tại."""
        (self.folder / 'package_spec.json').write_bytes(encoded({'distribution': 'local_private_draft_only', 'members': rows}))

    def test_roundtrip_and_no_overwrite(self) -> None:
        """Byte archive khớp, build lần hai bị chặn."""
        self.assertEqual(build(self.root, Path('release'))['members'], 1)
        self.assertEqual(verify_archive(self.folder)['archive_members'], 1)
        with self.assertRaises(ValueError):
            build(self.root, Path('release'))

    def test_source_tamper_stops_before_archive(self) -> None:
        """Nguồn không khớp hash không được tạo artifact dở."""
        (self.root / 'example.txt').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            build(self.root, Path('release'))
        self.assertFalse((self.folder / 'private_bundle.zip').exists())

    def test_case_alias_and_traversal_rejected(self) -> None:
        """ZIP không được dùng alias Windows hoặc thoát root."""
        for names in [('example.txt', 'EXAMPLE.txt'), ('../outside.txt',)]:
            self.spec([{'path': n, 'sha256': digest(b'fixture')} for n in names])
            with self.assertRaises(ValueError):
                build(self.root, Path('release'))

    def test_credential_pattern_rejected(self) -> None:
        """Chỉ fixture giả, không đọc/in credentials của máy."""
        data = b'gsk_' + b'x' * 24
        (self.root / 'example.txt').write_bytes(data)
        self.spec([{'path': 'example.txt', 'sha256': digest(data)}])
        with self.assertRaises(ValueError):
            build(self.root, Path('release'))
        self.assertFalse((self.folder / 'archive_index.json').exists())

    def test_archive_tamper_rejected(self) -> None:
        """Hash container bảo vệ cả dữ liệu và member set."""
        build(self.root, Path('release'))
        with (self.folder / 'private_bundle.zip').open('ab') as f:
            f.write(b'changed')
        with self.assertRaises(ValueError):
            verify_archive(self.folder)

    def test_symlink_rejected_even_with_matching_hash(self) -> None:
        """Metadata symlink không được thông qua chỉ vì bytes khớp."""
        archive = self.folder / 'private_bundle.zip'
        with ZipFile(archive, 'w') as z:
            info = ZipInfo('example.txt')
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            z.writestr(info, b'fixture')
        (self.folder / 'archive_index.json').write_bytes(encoded({'archive': archive.name, 'sha256': file_hash(archive), 'bytes': archive.stat().st_size,
            'members': [{'path': 'example.txt', 'bytes': 7, 'sha256': digest(b'fixture')}]}))
        with self.assertRaises(ValueError):
            verify_archive(self.folder)

    def seal(self, closed: bool = False) -> None:
        """Receipt nhỏ vẫn có đủ 87 IDs để thử gate closure độc lập hash."""
        build(self.root, Path('release'))
        rows = [{'id': f'R{n}.{i}', 'response': 'fixture', 'comment_closed': closed,
                 'final_pdf_locator': None, 'source_locations': [], 'evidence': []}
                for n, size in enumerate((7,4,4,5,5,3,8,5,6,6,2,4,3,3,3,10,6,3), 1)
                for i in range(1, size+1)]
        (self.folder / 'response_map.json').write_bytes(encoded(rows))
        (self.folder / 'rights.json').write_bytes(encoded({'public_release_authorized': False, 'pid': None}))
        (self.root / 'revision').mkdir()
        (self.root / 'revision/response_to_reviewers.md').write_text(''.join('### '+r['id']+'\nfixture\n' for r in rows), encoding='utf-8')
        m = {'sources': [{'path': 'example.txt', 'sha256': digest(b'fixture')}], 'historical_references': [],
             'outputs': [{'path': p.name, 'sha256': file_hash(p)} for p in self.folder.iterdir()]}
        m['sha256'] = digest(encoded(m))
        (self.folder / 'manifest.json').write_bytes(encoded(m))

    def test_archive_only_does_not_claim_current_sources(self) -> None:
        """Gói độc lập vẫn check được khi nguồn workspace đã thay đổi."""
        self.seal()
        self.assertEqual(check(self.root, Path('release'))['requests'], 87)
        (self.root / 'example.txt').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            check(self.root, Path('release'))
        result = check(self.root / 'absent', self.folder, archive_only=True)
        self.assertEqual(result['current_source_hashes'], 0)
        self.assertEqual(result['scope'], 'archive-only')

    def test_closure_rejected_despite_valid_manifest(self) -> None:
        """Hash hợp lệ không thay bằng chứng đóng comment hoặc PDF locator."""
        self.seal(closed=True)
        with self.assertRaises(ValueError):
            check(self.root, Path('release'))


if __name__ == '__main__':
    unittest.main()
