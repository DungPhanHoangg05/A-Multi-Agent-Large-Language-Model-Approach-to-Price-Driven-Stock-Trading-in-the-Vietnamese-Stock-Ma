"""Khóa OS byte 0 cho một máy local; metadata không thay cho handle khóa."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import os
from pathlib import Path
import socket
import subprocess
from typing import Any
from uuid import UUID, uuid4

from core.bayesian_memory import atomic_write_json, read_json
from core.prior_config import copy_prior_json


def utc_now() -> str:
    """Chuẩn UTC dùng trong schema checkpoint."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_path(root: Path, relative: str) -> Path:
    """Resolve file trong run-dir, không chấp nhận parent/absolute/symlink thoát root."""
    if type(relative) is not str or not relative or "\\" in relative or ":" in relative:
        raise ValueError("Path checkpoint không hợp lệ")
    parts = Path(relative)
    if parts.is_absolute() or any(p in (".", "..") for p in relative.split("/")):
        raise ValueError("Path checkpoint vượt root")
    path = (root / parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Symlink checkpoint vượt root")
    return path


@lru_cache(maxsize=1)
def host_boot() -> tuple[str, str]:
    """ID host/boot ổn định; không xác định được thì dừng thay vì đoán owner chết."""
    host = socket.gethostname().casefold()
    if os.name == "nt":
        command = "(Get-CimInstance Win32_OperatingSystem -ErrorAction Stop).LastBootUpTime.ToUniversalTime().Ticks"
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
        boot = result.stdout.strip()
        if result.returncode or not boot.isdigit():
            raise RuntimeError("Không xác minh được boot của máy local")
    else:
        boot = Path("/proc/sys/kernel/random/boot_id").read_text("utf-8").strip()
    if not host or not boot:
        raise RuntimeError("Thiếu identity host/boot")
    return host, boot


def process_start(pid: int) -> str | None:
    """Trả ID creation time hoặc None khi đã chết; access denied là lỗi rà soát."""
    if type(pid) is not int or pid < 1:
        raise ValueError("PID owner không hợp lệ")
    if os.name != "nt":
        try:
            fields = Path(f"/proc/{pid}/stat").read_text("utf-8").rsplit(")", 1)[1].split()
        except FileNotFoundError:
            return None
        return None if fields[0] == "Z" else fields[19]
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return None
        raise RuntimeError("Không xác định được liveness của owner")
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise RuntimeError("Không đọc được trạng thái owner")
        if code.value != 259:
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
            raise RuntimeError("Không đọc được creation time owner")
        return str((int(times[0].dwHighDateTime) << 32) | int(times[0].dwLowDateTime))
    finally:
        kernel.CloseHandle(handle)


def lock_handle(handle: Any) -> None:
    """Windows khóa byte 0; POSIX flock thuộc descriptor, không nhả khóa fd khác."""
    handle.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)


class PriorRunLock:
    """Giữ handle suốt run; file tồn tại không tự ngăn resume."""

    def __init__(self, root: Path, signature: str) -> None:
        self.root, self.signature = root.resolve(), signature
        self.handle: Any = None
        self.owner: dict[str, Any] | None = None

    def __enter__(self) -> PriorRunLock:
        self.root.mkdir(parents=True, exist_ok=True)
        self.handle = safe_path(self.root, "run.lock").open("a+b")
        try:
            self.handle.seek(0, 2)
            if self.handle.tell() == 0:
                self.handle.write(b"0")
                self.handle.flush()
            lock_handle(self.handle)
        except OSError:
            self.handle.close()
            self.handle = None
            raise RuntimeError("Run đang được tiến trình khác giữ khóa OS") from None
        try:
            host, boot = host_boot()
            own_start = process_start(os.getpid())
            if own_start is None:
                raise RuntimeError("Không xác minh được creation time hiện tại")
            owner_path = safe_path(self.root, "run.owner.json")
            if owner_path.exists():
                previous = copy_prior_json(read_json(owner_path))
                required = {"host_id", "boot_id", "pid", "process_start_time", "owner_uuid", "acquired_at",
                            "run_signature", "owner_state", "released_at"}
                if type(previous) is not dict or set(previous) != required:
                    raise ValueError("Metadata owner không đúng schema; cần rà soát")
                try:
                    UUID(previous["owner_uuid"])
                except (ValueError, TypeError, AttributeError):
                    raise ValueError("Owner UUID không hợp lệ") from None
                for key in ("acquired_at", "released_at"):
                    value = previous[key]
                    if value is not None and (type(value) is not str or not value.endswith("Z")):
                        raise ValueError("Mốc owner phải UTC")
                    if value is not None:
                        datetime.fromisoformat(value)
                if (previous["host_id"] != host or previous["run_signature"] != self.signature
                        or type(previous["process_start_time"]) is not str or not previous["process_start_time"]
                        or type(previous["boot_id"]) is not str or not previous["boot_id"]
                        or type(previous["pid"]) is not int or previous["pid"] < 1
                        or previous["acquired_at"] is None):
                    raise ValueError("Owner khác host/signature hoặc metadata không xác minh được")
                if previous["owner_state"] == "released" and previous["released_at"] is not None:
                    reason = "released"
                elif previous["owner_state"] == "active" and previous["released_at"] is None:
                    start = None if previous["boot_id"] != boot else process_start(previous["pid"])
                    if start == previous["process_start_time"]:
                        raise RuntimeError("Owner active vẫn sống nhưng không giữ OS lock; cần rà soát")
                    reason = "dead" if start is None else "pid_reused"
                else:
                    raise ValueError("Owner state/released_at không nhất quán")
                recovery_path = safe_path(self.root, "run.recovery.json")
                recovery = read_json(recovery_path) if recovery_path.exists() else {"format_version": 1, "records": []}
                if type(recovery) is not dict or set(recovery) != {"format_version", "records"} or type(recovery["format_version"]) is not int or recovery["format_version"] != 1 or type(recovery["records"]) is not list:
                    raise ValueError("Biên bản phục hồi owner không hợp lệ")
                for record in recovery["records"]:
                    if (type(record) is not dict or set(record) != {"previous_owner_uuid", "reason", "at"}
                            or record["reason"] not in ("released", "dead", "pid_reused")
                            or type(record["at"]) is not str or not record["at"].endswith("Z")):
                        raise ValueError("Record phục hồi owner không hợp lệ")
                    UUID(record["previous_owner_uuid"])
                    datetime.fromisoformat(record["at"])
                recovery["records"].append({"previous_owner_uuid": previous["owner_uuid"], "reason": reason, "at": utc_now()})
                atomic_write_json(recovery_path, recovery)
            self.owner = {"host_id": host, "boot_id": boot, "pid": os.getpid(), "process_start_time": own_start,
                "owner_uuid": str(uuid4()), "acquired_at": utc_now(), "run_signature": self.signature,
                "owner_state": "active", "released_at": None}
            atomic_write_json(owner_path, self.owner)
            return self
        except BaseException:
            self.handle.close()
            self.handle = None
            raise

    def __exit__(self, *args: Any) -> None:
        try:
            path = safe_path(self.root, "run.owner.json")
            current = read_json(path)
            if current.get("owner_uuid") != self.owner["owner_uuid"]:
                raise ValueError("Owner thay đổi khi đang giữ handle; không ghi đè metadata")
            atomic_write_json(path, {**self.owner, "owner_state": "released", "released_at": utc_now()})
        finally:
            self.handle.close()
            self.handle = None
