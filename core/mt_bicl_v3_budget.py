"""Một counter18 giờ v3 qua mọi stage/resume/W12; tạo trước thực nghiệm đầu tiên."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v3_protocol import PROTOCOL_SHA256
from core.prior_run_lock import PriorRunLock

VERSION = "utility_icl_runtime_budget_v3"
GRANT_SHA256 = "14e00747e8a1d2a3f783626daddb6ac1429b16e580740d9777694a2d167eb119"


class BudgetStop(RuntimeError):
    """Hết cap/deadline: giữ UUID/reserve/checkpoint và trạng thái incomplete."""


def budget_identity() -> dict[str, Any]:
    """Không nhận cap từ caller, không tạo grant mới theo stage hoặc tuần."""
    data = (Path(__file__).resolve().parents[1]/"docs/plan/week11/budget_v3.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != GRANT_SHA256:
        raise ValueError("Grant v3 khác byte người dùng đã xác nhận")
    grant = json.loads(data)
    return {"protocol_sha256": PROTOCOL_SHA256, "grant_sha256": GRANT_SHA256,
            "cap_seconds": grant["cap_seconds"], "data_stop": grant["data_stop"]}


class RuntimeBudget:
    """Giữ khóa OS xuyên phiên; hard crash tính gap bảo thủ, clean pause loại downtime."""

    def __init__(self, root: Path, stage: str, *, now: Callable[[], datetime] | None = None,
                 monotonic: Callable[[], float] = perf_counter) -> None:
        """Không ghi file khi khởi tạo object hoặc import module trong unit/spec lint."""
        if stage not in ("offline_validation", "API_preflight", "development", "confirmation_if_released", "cold_verification", "report_replay"):
            raise ValueError("Stage không thuộc grant v3")
        self.path = root/"outputs/bayesian_benchmark/mt_bicl_v3/runtime_budget.json"
        self.stage = stage
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic
        self.identity = budget_identity()
        self.stop = datetime.fromisoformat(self.identity["data_stop"])
        self.state: dict[str, Any] | None = None
        self.started: float | None = None
        self.lock: PriorRunLock | None = None

    def _now(self) -> datetime:
        """Bắt buộc UTC có timezone; không dựa múi giờ của máy chạy."""
        value = self.now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Đồng hồ budget phải có timezone")
        return value.astimezone(timezone.utc)

    def _validate(self) -> None:
        """Counter không được thấp hơn tổng phiên durable hoặc đổi identity/cap."""
        state = self.state
        if (state is None or set(state) != {"identity", "elapsed_seconds", "active_since", "active_stage", "sessions"}
                or state["identity"] != self.identity or type(state["elapsed_seconds"]) not in (int, float)
                or not math.isfinite(state["elapsed_seconds"]) or not 0 <= state["elapsed_seconds"] <= self.identity["cap_seconds"]
                or type(state["sessions"]) is not list):
            raise ValueError("Counter v3 sai identity/cap/schema; không reset")
        durations = [session["charged_seconds"] for session in state["sessions"]]
        if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in durations) or abs(math.fsum(durations)-state["elapsed_seconds"]) > 1e-6:
            raise ValueError("Counter v3 không khớp tổng các đoạn đã tính phí")
        if (state["active_since"] is None) != (state["active_stage"] is None):
            raise ValueError("Phiên active thiếu stage/cutoff")
        if state["active_since"] is not None:
            value = datetime.fromisoformat(state["active_since"])
            if value.tzinfo is None or state["active_stage"] not in ("offline_validation", "API_preflight", "development", "confirmation_if_released", "cold_verification", "report_replay"):
                raise ValueError("Phiên active không đúng UTC/stage")

    def _save(self) -> None:
        """Ghi atomic trước khi chạy; lỗi ghi không được coi là đã lưu checkpoint."""
        self._validate()
        write_envelope(self.path, VERSION, self.state)

    def used(self) -> float:
        """Thời gian đơn điệu trong phiên gồm cả pacing/retry/serialization."""
        if self.state is None:
            raise ValueError("Budget chưa được mở")
        extra = 0. if self.started is None else self.monotonic()-self.started
        if extra < 0 or not math.isfinite(extra):
            raise ValueError("Đồng hồ monotonic budget đi lùi/không hữu hạn")
        return float(min(self.identity["cap_seconds"], self.state["elapsed_seconds"]+extra))

    def remaining_seconds(self) -> float:
        """Caller kiểm cả sleep/provider reset với phần cap và lịch còn lại."""
        return float(max(0., min(self.identity["cap_seconds"]-self.used(), (self.stop-self._now()).total_seconds())))

    def check(self, required_seconds: float = 0.) -> None:
        """Dừng trước thao tác không thể fit cap/deadline, không mở grant mới."""
        if self.started is None:
            raise ValueError("Kiểm runtime phải trong phiên budget đang mở")
        if type(required_seconds) not in (int, float) or not math.isfinite(required_seconds) or required_seconds < 0:
            raise ValueError("Thời gian dự kiến không hợp lệ")
        remaining = self.remaining_seconds()
        if remaining <= 0 or required_seconds > remaining:
            raise BudgetStop("BUDGET_OR_DEADLINE_INCOMPLETE: giữ UUID/reserve/checkpoint, không reset v3")

    def checkpoint(self) -> None:
        """Flush sau mỗi slot/stage; vẫn giữ active_since để crash tiếp theo được tính."""
        if self.started is None or self.state is None:
            raise ValueError("Không checkpoint phiên budget chưa mở")
        now = self._now()
        if now < datetime.fromisoformat(self.state["active_since"]):
            raise ValueError("Đồng hồ UTC đi lùi trong phiên budget")
        used = self.used()
        self.state["sessions"].append({"stage": self.stage, "kind": "MONOTONIC", "started_at": self.state["active_since"],
                                       "ended_at": now.isoformat(), "charged_seconds": float(used-self.state["elapsed_seconds"])})
        self.state.update(elapsed_seconds=used, active_since=now.isoformat(), active_stage=self.stage)
        self.started = self.monotonic()
        self._save()

    def __enter__(self) -> RuntimeBudget:
        """Counter thiếu trong namespace đã có dữ liệu là lỗi, không tạo lại từ0."""
        if self.lock is not None or self.started is not None:
            raise ValueError("Budget đã có phiên mở, không lồng/reenter")
        previous_owner = (self.path.parent/"runtime_budget.lock/run.owner.json").exists()
        self.lock = PriorRunLock(self.path.parent/"runtime_budget.lock", "utility-icl-budget-v3")
        self.lock.__enter__()
        try:
            if self.path.exists():
                self.state = read_envelope(self.path, VERSION)
            else:
                if previous_owner or any(item.name != "runtime_budget.lock" for item in self.path.parent.iterdir()):
                    raise ValueError("Mất counter trong namespace v3 đã có dữ liệu; không reset về0")
                self.state = {"identity": deepcopy(self.identity), "elapsed_seconds": 0., "active_since": None, "active_stage": None, "sessions": []}
            self._validate()
            now = self._now()
            if self.state["active_since"] is not None:
                active = datetime.fromisoformat(self.state["active_since"])
                if now < active:
                    raise ValueError("Đồng hồ UTC đi lùi khi phục hồi budget")
                gap = max(0., (min(now, self.stop)-active).total_seconds())
                charged = min(gap, self.identity["cap_seconds"]-self.state["elapsed_seconds"])
                self.state["sessions"].append({"stage": self.state["active_stage"], "kind": "CRASH_GAP_CONSERVATIVE",
                    "started_at": active.isoformat(), "ended_at": min(now, self.stop).isoformat(), "charged_seconds": float(charged)})
                self.state["elapsed_seconds"] += charged
            self.state.update(active_since=now.isoformat(), active_stage=self.stage)
            self.started = self.monotonic()
            self._save()
            self.check()
            return self
        except BaseException:
            if self.started is not None:
                self.__exit__()
            elif self.lock is not None:
                self.lock.__exit__(None, None, None)
                self.lock = None
            raise

    def __exit__(self, *args: Any) -> None:
        """Đóng sạch cả Ctrl+C/lỗi; không xóa counter/lock/reserve hoặc tính downtime sạch."""
        try:
            if self.started is not None:
                self.checkpoint()
                self.state.update(active_since=None, active_stage=None)
                self.started = None
                self._save()
        finally:
            if self.lock is not None:
                self.lock.__exit__(None, None, None)
                self.lock = None
