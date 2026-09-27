"""Bảo vệ lời gọi LLM của runner lịch sử bằng retry có backoff và thời gian Groq."""

from __future__ import annotations

import re
import time
from typing import Any, Callable


def _invoke_with_retry(call_fn: Callable[..., Any], *args: Any, retries: int = 3,
                       wait_sec: float = 5.0, **kwargs: Any) -> Any:
    """Không retry lỗi liêm chính; tôn trọng toàn bộ thời gian server yêu cầu chờ."""
    for attempt in range(retries):
        try:
            return call_fn(*args, **kwargs)
        except (ValueError, AssertionError):
            raise
        except Exception as error:
            if attempt + 1 == retries:
                raise
            delay = wait_sec * 2 ** attempt
            match = re.search(r"(?:retry after|try again in)\s*(?:(\d+(?:\.\d+)?)\s*m)?\s*(\d+(?:\.\d+)?)\s*s",
                              str(error), re.IGNORECASE)
            if match:
                delay = max(delay, 60 * float(match.group(1) or 0) + float(match.group(2)) + 1.0)
            print(f"Lời gọi LLM lỗi lần {attempt + 1}/{retries}; chờ {delay:.1f} giây")
            while delay > 0:
                duration = min(delay, 60.0)
                time.sleep(duration)
                delay -= duration
    raise ValueError("Số lần retry phải dương")


class RetryingLLM:
    """Adapter invoke cho cả suy luận thị giác và dự phòng văn bản của agent cũ."""

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Mọi request của runner đi qua cùng wrapper, kể cả đường dự phòng."""
        return _invoke_with_retry(self.delegate.invoke, *args, **kwargs)
