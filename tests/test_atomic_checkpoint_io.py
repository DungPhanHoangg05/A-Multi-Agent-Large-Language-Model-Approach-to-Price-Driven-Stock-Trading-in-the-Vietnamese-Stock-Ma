"""Fault test I/O nguyên tử; chỉ dùng thư mục tạm, không gọi API."""

import ctypes
import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.bayesian_memory import atomic_write_json, read_json


def windows_error(code: int) -> OSError:
    """Tạo lỗi Windows xác định để test cả trên hệ điều hành khác."""
    error = PermissionError(errno.EACCES, "Khóa fixture")
    error.winerror = code
    return error


class AtomicCheckpointIOTests(unittest.TestCase):
    """Checkpoint cũ phải nguyên byte cho tới khi replace thành công."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "checkpoint.json"
        atomic_write_json(self.path, {"revision": 1})
        self.original = self.path.read_bytes()

    def test_transient_windows_errors_retry_same_closed_fsynced_file(self) -> None:
        replace = os.replace
        for code in (5, 32, 33):
            with self.subTest(code=code):
                self.path.write_bytes(self.original)
                sources = []
                def replace_locked(source, target):
                    sources.append(source)
                    self.assertEqual(self.path.read_bytes(), self.original)
                    self.assertEqual(read_json(Path(source)), {"revision": 2})
                    if len(sources) < 3:
                        raise windows_error(code)
                    replace(source, target)
                with patch("core.bayesian_memory.os.replace", side_effect=replace_locked), \
                     patch("core.bayesian_memory.os.fsync", wraps=os.fsync) as sync, \
                     patch("core.bayesian_memory.time.sleep") as sleep:
                    atomic_write_json(self.path, {"revision": 2})
                self.assertEqual(sync.call_count, 1)
                self.assertEqual(len(set(sources)), 1)
                self.assertEqual([c.args[0] for c in sleep.call_args_list], [.05, .1])
                self.assertEqual(read_json(self.path), {"revision": 2})
                self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_persistent_access_denied_is_bounded_and_preserves_old_bytes(self) -> None:
        failure = windows_error(5)
        with patch("core.bayesian_memory.os.replace", side_effect=failure) as replace, \
             patch("core.bayesian_memory.time.sleep") as sleep:
            with self.assertRaises(OSError) as caught:
                atomic_write_json(self.path, {"revision": 2})
        self.assertIs(caught.exception, failure)
        self.assertEqual(replace.call_count, 5)
        self.assertAlmostEqual(sum(c.args[0] for c in sleep.call_args_list), .75)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_non_windows_permission_and_full_disk_fail_without_retry(self) -> None:
        for error in (PermissionError(errno.EACCES, "Quyền fixture"), OSError(errno.ENOSPC, "Đĩa đầy")):
            with self.subTest(error=error), patch("core.bayesian_memory.os.replace", side_effect=error) as replace, \
                 patch("core.bayesian_memory.time.sleep") as sleep, self.assertRaises(OSError):
                atomic_write_json(self.path, {"revision": 2})
            self.assertEqual(replace.call_count, 1)
            sleep.assert_not_called()
            self.assertEqual(self.path.read_bytes(), self.original)

    def test_fsync_failure_never_replaces_target(self) -> None:
        with patch("core.bayesian_memory.os.fsync", side_effect=windows_error(5)), \
             patch("core.bayesian_memory.os.replace") as replace, \
             patch("core.bayesian_memory.time.sleep") as sleep, self.assertRaises(OSError):
            atomic_write_json(self.path, {"revision": 2})
        replace.assert_not_called()
        sleep.assert_not_called()
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_partial_temporary_write_never_exposes_partial_json(self) -> None:
        factory = tempfile.NamedTemporaryFile
        class PartialWriter:
            """Ghi dở file tạm rồi mô phỏng hết dung lượng."""
            def __init__(self, **kwargs):
                self.file = factory(**kwargs)
                self.name = self.file.name
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.file.close()
            def write(self, content: str) -> None:
                self.file.write(content[:5])
                self.file.flush()
                raise OSError(errno.ENOSPC, "Đĩa đầy khi ghi fixture")
        with patch("core.bayesian_memory.tempfile.NamedTemporaryFile", PartialWriter), \
             patch("core.bayesian_memory.os.replace") as replace, self.assertRaises(OSError):
            atomic_write_json(self.path, {"revision": 2})
        replace.assert_not_called()
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_cleanup_failure_does_not_mask_primary_disk_error(self) -> None:
        failure = OSError(errno.ENOSPC, "Đĩa đầy fixture")
        with patch("core.bayesian_memory.os.replace", side_effect=failure), \
             patch("core.bayesian_memory.os.unlink", side_effect=windows_error(32)), \
             patch("core.bayesian_memory.time.sleep"), self.assertRaises(OSError) as caught:
            atomic_write_json(self.path, {"revision": 2})
        self.assertIs(caught.exception, failure)
        self.assertTrue(any("file tạm" in note for note in failure.__notes__))
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(len(list(self.path.parent.glob("*.tmp"))), 1)

    def test_serialization_failure_does_not_touch_disk(self) -> None:
        with self.assertRaises(ValueError):
            atomic_write_json(self.path, {"value": float("nan")})
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    @unittest.skipUnless(os.name == "nt", "Cần handle Windows thật")
    def test_actual_windows_reader_blocks_replace_until_closed(self) -> None:
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        # Chỉ chia sẻ đọc/ghi, cố ý không chia sẻ DELETE để tái hiện sharing violation.
        handle = kernel.CreateFileW(str(self.path), 0x80000000, 3, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        held = [handle]
        def release(seconds: float) -> None:
            self.assertEqual(self.path.read_bytes(), self.original)
            self.assertTrue(kernel.CloseHandle(held.pop()))
        try:
            with patch("core.bayesian_memory.time.sleep", side_effect=release) as sleep:
                atomic_write_json(self.path, {"revision": 2})
            sleep.assert_called_once_with(.05)
            self.assertEqual(read_json(self.path), {"revision": 2})
            # Reader JSON thường đóng handle trước khi caller bắt đầu lần ghi kế tiếp.
            atomic_write_json(self.path, {"revision": 3})
            self.assertEqual(read_json(self.path), {"revision": 3})
        finally:
            if held:
                kernel.CloseHandle(held.pop())
