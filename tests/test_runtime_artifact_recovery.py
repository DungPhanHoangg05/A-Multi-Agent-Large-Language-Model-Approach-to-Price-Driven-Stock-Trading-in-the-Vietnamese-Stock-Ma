"""Kiểm phục hồi đúng byte, không ghi đè và không công bố file ghi dở."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.recover_mt_bicl_runtime import restore_exact, sha256


class ExactRecoveryTests(unittest.TestCase):
    """Các lỗi integrity phải dừng trước khi thay đổi bằng chứng hiện có."""

    def test_restore_and_resume_preserve_original_bytes(self) -> None:
        """CRLF và thứ tự key của bằng chứng được giữ khi chạy lại."""
        raw = b'{\r\n  "b": 2,\r\n  "a": 1\r\n}\r\n'
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(restore_exact(root, 'bank/record.json', raw, sha256(raw)), 'RESTORED_EXACT')
            self.assertEqual(restore_exact(root, 'bank/record.json', raw, sha256(raw)), 'ALREADY_EXACT')
            self.assertEqual((root / 'bank/record.json').read_bytes(), raw)

    def test_wrong_candidate_hash_creates_nothing(self) -> None:
        """Không reseal JSON có cùng nội dung nhưng khác byte."""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                restore_exact(root, 'bank/record.json', b'{}\n', sha256(b'{}\r\n'))
            self.assertEqual(list(root.iterdir()), [])

    def test_existing_conflict_is_never_overwritten(self) -> None:
        """Bằng chứng hiện có khác candidate phải được giữ nguyên."""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / 'record.json'
            target.write_bytes(b'original')
            with self.assertRaisesRegex(ValueError, 'Giữ nguyên'):
                restore_exact(root, target.name, b'candidate', sha256(b'candidate'))
            self.assertEqual(target.read_bytes(), b'original')

    def test_path_escape_is_rejected(self) -> None:
        """Không phục hồi ra ngoài workspace hoặc thay root bằng một file."""
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / 'workspace'
            root.mkdir()
            for name in ('../escape.json', str(root.parent / 'absolute.json'), '.'):
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'ngoài workspace'):
                    restore_exact(root, name, b'x', sha256(b'x'))

    def test_failed_publication_leaves_no_partial_target(self) -> None:
        """Lỗi công bố file không để lại artifact giả hoàn chỉnh hoặc temp thừa."""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch('scripts.recover_mt_bicl_runtime.os.link', side_effect=OSError('fixture')):
                with self.assertRaises(OSError):
                    restore_exact(root, 'record.json', b'complete', sha256(b'complete'))
            self.assertEqual(list(root.iterdir()), [])

    def test_concurrent_writer_is_preserved(self) -> None:
        """Nếu writer khác tạo file sau bước kiểm thì không được replace file đó."""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)

            def competing_writer(source: Path, target: Path) -> None:
                """Mô phỏng file đích xuất hiện ngay trước khi công bố."""
                target.write_bytes(b'other-writer')
                raise FileExistsError('fixture')

            with patch('scripts.recover_mt_bicl_runtime.os.link', side_effect=competing_writer):
                with self.assertRaises(FileExistsError):
                    restore_exact(root, 'record.json', b'candidate', sha256(b'candidate'))
            self.assertEqual((root / 'record.json').read_bytes(), b'other-writer')
            self.assertEqual(len(list(root.iterdir())), 1)


if __name__ == '__main__':
    unittest.main()
