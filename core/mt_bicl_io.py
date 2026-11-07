"""Envelope atomic và đồng hồ active MT-BICL dùng chung, không reset giữa các stage/seed."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
from time import perf_counter
from typing import Any

from core.bayesian_memory import atomic_write_json, read_json
from core.mt_bicl_bank import content_hash


def read_envelope(path: Path, version: str) -> dict[str, Any]:
    """Không nhận NaN, kiểu NumPy, sai version hoặc self-hash không khớp payload."""
    value = read_json(path)
    if (set(value) != {"version", "payload", "sha256"} or value["version"] != version
            or content_hash(value["payload"]) != value["sha256"]):
        raise ValueError("Envelope MT-BICL không hợp lệ: "+str(path))
    return value["payload"]


def write_envelope(path: Path, version: str, payload: dict[str, Any], *, immutable: bool = False) -> None:
    """Chỉ atomic dưới OS lock caller; artifact đã seal không được ghi đè."""
    if immutable and path.exists():
        if read_envelope(path, version) != payload:
            raise ValueError("Không ghi đè artifact MT-BICL đã khóa: "+str(path))
        return
    atomic_write_json(path, {"version": version, "payload": payload, "sha256": content_hash(payload)})


class ActiveBudget:
    """Dùng chung 14.400 giây; crash tính bảo thủ toàn gap, pause sạch loại downtime."""

    def __init__(self, path: Path, identity: dict[str, Any]) -> None:
        """Identity chỉ gồm protocol/grant/cap, không cấp lại4 giờ khi đổi module/stage."""
        self.path, self.identity = path, identity
        self.state = read_envelope(path, "mt_bicl_active_budget") if path.exists() else {
            "identity": identity, "elapsed_seconds": 0., "active_since": None, "sessions": []}
        if self.state["identity"] != identity:
            raise ValueError("Ngân sách dùng chung khác identity")
        self.started: float | None = None

    def save(self) -> None:
        """Lưu cả active_since trước xử lý để hard crash không làm mất chi phí."""
        write_envelope(self.path, "mt_bicl_active_budget", self.state)

    def used(self) -> float:
        """Tính cả generation/serialization/checkpoint của phiên đang chạy."""
        return float(self.state["elapsed_seconds"]+(perf_counter()-self.started if self.started is not None else 0))

    def check(self) -> None:
        """Hết cap hoặc hạn W10 thì dừng, không tự reset state hoặc hạ gate."""
        stop = datetime.fromisoformat(self.identity["W10_stop"]+"T23:59:59+07:00")
        if self.used() >= self.identity["cap_seconds"] or datetime.now(timezone.utc) >= stop:
            raise RuntimeError("Hết cap/lịch W10: INCOMPLETE, không mở train mới")

    def __enter__(self) -> ActiveBudget:
        """Phục hồi gap trước khi mở phiên; dùng perf_counter trong một phiên."""
        value = self.state["elapsed_seconds"]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("Thời gian active không hợp lệ")
        durations = [session["duration_seconds"] for session in self.state["sessions"]]
        if (any(type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0
                for duration in durations) or value+1e-9 < math.fsum(durations)):
            raise ValueError("Counter active thấp hơn các phiên đã ghi, không reset ngân sách")
        now = datetime.now(timezone.utc)
        if self.state["active_since"] is not None:
            gap = (now-datetime.fromisoformat(self.state["active_since"])).total_seconds()
            if gap < 0:
                raise ValueError("Đồng hồ đi lùi khi phục hồi budget")
            self.state["elapsed_seconds"] += gap
        self.state["active_since"] = now.isoformat()
        self.started = perf_counter()
        self.save()
        try:
            self.check()
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *args: Any) -> None:
        """Đóng phiên cả khi lỗi/Ctrl+C, giữ chi phí đã phát sinh."""
        duration = perf_counter()-self.started if self.started is not None else 0.
        self.state["elapsed_seconds"] = self.used()
        self.state["sessions"].append({"started_at": self.state["active_since"],
                                       "duration_seconds": float(duration)})
        self.state["active_since"], self.started = None, None
        self.save()
