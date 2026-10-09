"""Ngân sách chung cho node, gồm HTTP retry và lần sửa định dạng Decision."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import time
from typing import Any, Iterator
from uuid import uuid4

ENABLED: ContextVar[bool] = ContextVar("research_budget_enabled", default=False)
CURRENT: ContextVar[Any] = ContextVar("research_invocation", default=None)


@dataclass
class InvocationBudget:
    """Ba HTTP và tối đa 120 giây nghỉ cộng dồn cho một invocation gốc."""

    role: str
    invocation_id: str = field(default_factory=lambda: str(uuid4()))
    attempts: int = 0
    wait_seconds: float = 0.
    checkpoint_attempt_id: str | None = None
    point_id: str | None = None
    branch_id: str | None = None
    run_signature: str | None = None
    on_finish: Any = None
    started: float = field(default_factory=time.monotonic)
    elapsed_seconds: float | None = None
    status: str = "unknown"

    def check_wait(self, delay: float) -> None:
        """Dừng trước khi vượt trần; không tạo một budget mới để tiếp tục."""
        if self.wait_seconds + delay > 120:
            from core.groq_pacing import PilotStop
            raise PilotStop("INVOCATION_WAIT_BUDGET_EXCEEDED; giữ checkpoint để đối soát")

    def before_http(self) -> None:
        """Mỗi HTTP thực, kể cả format repair, tiêu một lượt."""
        if self.attempts >= 3:
            from core.groq_pacing import PilotStop
            raise PilotStop("INVOCATION_ATTEMPT_BUDGET_EXCEEDED; giữ checkpoint")
        self.attempts += 1


@contextmanager
def invocation_scope(role: str) -> Iterator[InvocationBudget | None]:
    """Node lồng nhau dùng chung budget; luồng cũ không tự bật policy mới."""
    if not ENABLED.get() or CURRENT.get() is not None:
        yield CURRENT.get()
        return
    budget = InvocationBudget(role)
    token = CURRENT.set(budget)
    try:
        yield budget
        budget.status = "complete"
    except BaseException:
        budget.status = "stopped"
        raise
    finally:
        CURRENT.reset(token)
        budget.elapsed_seconds = float(max(0., time.monotonic() - budget.started))
        if budget.on_finish is not None:
            budget.on_finish(budget)


def invoke_once(call_fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Transport quản retry 429; các lớp agent không nhân ngân sách hoặc fallback lỗi mơ hồ."""
    try:
        return call_fn(*args, **kwargs)
    except (ValueError, AssertionError):
        raise
    except Exception:
        from core.groq_pacing import PilotStop
        raise PilotStop("INVOCATION_AMBIGUOUS; không tự gửi lại request") from None
