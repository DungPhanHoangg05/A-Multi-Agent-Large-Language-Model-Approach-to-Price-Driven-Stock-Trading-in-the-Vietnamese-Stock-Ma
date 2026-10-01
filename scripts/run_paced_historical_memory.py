"""Giới hạn nhịp gọi LLM cho runner lịch sử mà không đổi mã nguồn đã ký."""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from core.bayesian_memory import atomic_write_json, read_json
from utils import historical_api

PACE_FILE = "api_pace.json"
DEFAULT_LLM_GAP_SECONDS = 75.0
BASE_RETRYING_LLM = historical_api.RetryingLLM


class RequestPacer:
    """Lưu mốc gọi LLM để khoảng nghỉ vẫn có hiệu lực sau khi khởi động lại."""

    def __init__(self, output_dir: Path, gap_seconds: float, *,
                 clock: Callable[[], float] = time.time,
                 sleeper: Callable[[float], None] = time.sleep) -> None:
        if isinstance(gap_seconds, bool) or not isinstance(gap_seconds, (int, float)) \
                or not math.isfinite(gap_seconds) or gap_seconds < 0:
            raise ValueError("Khoảng nghỉ LLM phải là số giây hữu hạn, không âm")
        self.output_dir = output_dir
        self.gap_seconds = float(gap_seconds)
        self.clock = clock
        self.sleeper = sleeper
        self.path = output_dir / PACE_FILE

    def _last_activity(self) -> float | None:
        """Ưu tiên mốc gọi đã lưu; journal giúp bảo vệ run cũ chưa có pace file."""
        if self.path.exists():
            payload = read_json(self.path)
            if type(payload) is not dict or set(payload) != {"last_call_epoch"} \
                    or type(payload["last_call_epoch"]) is not float \
                    or not math.isfinite(payload["last_call_epoch"]):
                raise ValueError("Mốc nghỉ LLM sai cấu trúc")
            return payload["last_call_epoch"]
        episodes = self.output_dir / "episodes"
        return max((item.stat().st_mtime for item in episodes.glob("*.json")), default=None)

    def _mark_activity(self) -> None:
        """Ghi nguyên tử trước và sau request, kể cả khi tiến trình bị ngắt."""
        atomic_write_json(self.path, {"last_call_epoch": float(self.clock())})

    def before_request(self) -> None:
        """Chỉ gửi request sau khi cửa sổ TPM của request trước đã qua."""
        last = self._last_activity()
        if last is not None and self.gap_seconds:
            remaining = last + self.gap_seconds - self.clock()
            if remaining > 0:
                print(f"[TPM] Nghỉ {remaining:.1f} giây trước lời gọi LLM kế tiếp.", flush=True)
            while remaining > 0:
                self.sleeper(min(remaining, 30.0))
                remaining = last + self.gap_seconds - self.clock()
        self._mark_activity()

    def after_request(self) -> None:
        """Đếm khoảng nghỉ từ lúc request kết thúc, gồm cả request thất bại."""
        self._mark_activity()


def make_paced_llm_class(pacer: RequestPacer) -> type[historical_api.RetryingLLM]:
    """Bọc mọi lời gọi của hai model bằng cùng bộ điều tiết tuần tự."""
    class PacedRetryingLLM(BASE_RETRYING_LLM):
        def invoke(self, *args: Any, **kwargs: Any) -> Any:
            """Nghỉ trước khi gọi; giữ nguyên cơ chế retry và nội dung trả về."""
            pacer.before_request()
            try:
                return super().invoke(*args, **kwargs)
            finally:
                pacer.after_request()

    return PacedRetryingLLM


def main() -> None:
    """Gắn nhịp gọi vào adapter trước khi runner gốc khởi tạo agent."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/historical_memory_run")
    options, _ = parser.parse_known_args()
    gap = float(os.environ.get("HISTORICAL_LLM_GAP_SECONDS", DEFAULT_LLM_GAP_SECONDS))
    pacer = RequestPacer(options.output_dir.resolve(), gap)
    historical_api.RetryingLLM = make_paced_llm_class(pacer)
    from scripts.run_historical_memory import main as run_original
    run_original()


if __name__ == "__main__":
    main()
