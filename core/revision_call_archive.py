"""Archive từng lời gọi LLM và chặn ngân sách trước network cho study R1."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import messages_to_dict

from core.revision_common_study import digest, native, read_json, write_json


class StudyStop(BaseException):
    """Dừng guard không được retry như một lỗi provider tạm thời."""


class CallArchive(BaseCallbackHandler):
    """Chỉ lưu messages/response; không dump serialized client chứa credentials."""

    raise_error = True

    def __init__(self, directory: Path, bank_id: str, max_requests: int, secret: str) -> None:
        if max_requests < 1:
            raise ValueError("Ngân sách request phải dương")
        self.directory, self.bank_id = directory, bank_id
        self.max_requests, self.secret = max_requests, secret
        self.context: dict[str, Any] = {}
        self.pending: dict[str, dict] = {}
        self.ids: list[str] = []
        self.not_before = 0.0
        self.count_path = directory / "usage.json"
        if self.count_path.exists():
            usage = read_json(self.count_path)
            if usage["bank_id"] != bank_id:
                raise ValueError("Usage thuộc bank khác")
            self.count = int(usage["attempted_requests"])
        else:
            self.count = 0

    def clean(self, value: Any) -> Any:
        """Ẩn chính xác key đã cấp, kể cả khi provider nhắc lại trong lỗi."""
        value = native(value)
        if isinstance(value, str):
            return value.replace(self.secret, "[REDACTED]") if self.secret else value
        if isinstance(value, dict):
            return {k: self.clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.clean(v) for v in value]
        return value

    def on_chat_model_start(self, serialized: dict, messages: list, *, run_id: Any, **kwargs: Any) -> None:
        """Trừ request trước API, khóa prompt thật và kiểm tra Decision <6500 ký tự."""
        if self.count >= self.max_requests:
            raise StudyStop("Đã hết ngân sách request; chưa gửi lời gọi tiếp theo.")
        if not self.context:
            raise StudyStop("Lời gọi LLM không có context study; chặn trước network.")
        import time
        while time.monotonic() < self.not_before:
            time.sleep(min(30.0, self.not_before - time.monotonic()))
        if self.context.get("stage") == "decision":
            chars = sum(len(message.content) for batch in messages for message in batch if isinstance(message.content, str))
            if chars >= 6500:
                raise StudyStop(f"Prompt Decision dài {chars} ký tự, vi phạm ngưỡng <6500.")
        self.count += 1
        write_json(self.count_path, {"bank_id": self.bank_id, "attempted_requests": self.count,
                                    "max_requests_current_command": self.max_requests})
        key = str(run_id)
        request = {"bank_id": self.bank_id, "attempt_id": key, "context": deepcopy(self.context),
                   "started_at_utc": datetime.now(timezone.utc).isoformat(),
                   "model_metadata": {k: v for k, v in kwargs.get("metadata", {}).items()
                                      if k in ("ls_provider", "ls_model_name", "ls_temperature", "ls_max_tokens", "langgraph_node")},
                   "invocation_parameters": {k: v for k, v in kwargs.get("invocation_params", {}).items()
                                             if k in ("model", "max_tokens", "temperature", "stop", "tools", "tool_choice", "response_format", "reasoning_format")},
                   "messages": [messages_to_dict(batch) for batch in messages]}
        request = self.clean(request)
        request["sha256"] = digest(request)
        self.pending[key] = request
        self.ids.append(key)
        write_json(self.directory / "calls" / f"{key}.request.json", request, exclusive=True)

    def on_llm_end(self, response: Any, *, run_id: Any, **kwargs: Any) -> None:
        """Lưu response nguyên bản, token usage/model/request IDs do SDK trả về."""
        key = str(run_id)
        if key not in self.pending:
            raise StudyStop("Response không có request parent trong phiên hiện tại.")
        result = self.clean(response.model_dump(mode="json"))
        write_json(self.directory / "calls" / f"{key}.response.json", {
            "attempt_id": key, "parent_request_hash": self.pending[key]["sha256"],
            "ended_at_utc": datetime.now(timezone.utc).isoformat(), "response": result}, exclusive=True)
        self.pending.pop(key)

    def on_llm_error(self, error: BaseException, *, run_id: Any, **kwargs: Any) -> None:
        """Giữ lỗi thật; không thay bằng một phán quyết hoặc đổi model."""
        key = str(run_id)
        write_json(self.directory / "calls" / f"{key}.error.json", self.clean({
            "attempt_id": key, "context": self.context, "type": type(error).__name__, "error": str(error)[:2000]}))
        self.pending.pop(key, None)
        import re
        import time
        match = re.search(r"(?:retry after|try again in)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:s|seconds)", str(error), re.I)
        if match:
            self.not_before = max(self.not_before, time.monotonic() + float(match.group(1)) + 1.0)


class GuardedLLM:
    """Proxy giữ structured output và bắt mọi invoke đi qua wrapper retry chuẩn."""

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Các agent giữ retry vòng ngoài; proxy chỉ chạy một attempt được archive."""
        from agents.decision_agent import _invoke_with_retry
        return _invoke_with_retry(lambda: self.delegate.invoke(*args, **kwargs), retries=1)

    def with_structured_output(self, *args: Any, **kwargs: Any) -> GuardedLLM:
        """Callback và budget vẫn nằm trên underlying chat model."""
        return GuardedLLM(self.delegate.with_structured_output(*args, **kwargs))


class StudyLock:
    """Khóa OS tự nhả khi tiến trình kết thúc, không cần xóa lock directory."""

    def __init__(self, path: Path) -> None:
        self.path, self.handle = path, None

    def __enter__(self) -> StudyLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, 2)
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            import os
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise RuntimeError("Study đang bị một tiến trình khác khóa") from None
        return self

    def __exit__(self, *args: Any) -> None:
        if self.handle is not None:
            self.handle.close()
