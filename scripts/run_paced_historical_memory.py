"""Giới hạn nhịp gọi LLM cho runner lịch sử mà không đổi mã nguồn đã ký."""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import re
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

from core.bayesian_memory import atomic_write_json, exact_object, read_json
from core import historical_signals
from utils import historical_api

PACE_FILE = "api_pace.json"
DEFAULT_LLM_GAP_SECONDS = 75.0
BASE_RETRYING_LLM = historical_api.RetryingLLM
BASE_REPORT_SIGNAL = historical_signals.report_signal
REPORT_PARSE_FILE = "report_parse_compat.json"


def make_compatible_report_parser(output_dir: Path) -> Callable[[str, tuple[str, ...]], str]:
    """Đọc trường Trend viết tắt, lưu biên bản riêng và giữ nguyên báo cáo gốc."""
    def parse(report: str, labels: tuple[str, ...]) -> str:
        """Ưu tiên bộ đọc gốc; không suy đoán hướng từ phần diễn giải."""
        try:
            return BASE_REPORT_SIGNAL(report, labels)
        except ValueError:
            if type(report) is not str or labels != ("Hướng xu hướng", "Trend direction"):
                raise
            cleaned = report.replace("**", "")
            canonical = r"^\s*(?:[-*]\s*)?(?:Hướng xu hướng|Trend direction)\s*:"
            if re.search(canonical, cleaned, re.IGNORECASE | re.MULTILINE):
                raise
            fields = re.findall(r"^\s*(?:[-*]\s*)?Hướng xu\s*:\s*([^\n]+)", cleaned,
                                flags=re.IGNORECASE | re.MULTILINE)
            if len(fields) != 1 or len(re.findall(r"\bHướng xu\s*:", cleaned, re.IGNORECASE)) != 1:
                raise
            direction = re.split(r"\s+(?=(?:Mức h|Mức k|Độ dốc đường xu)\s*:|Giá so với h(?:\s|[.:]|$))",
                                 fields[0], maxsplit=1, flags=re.IGNORECASE)[0].strip()
            if not re.fullmatch(r"(?:Tăng|Giảm|Đi ngang|Trung tính|Hỗn hợp)[.!]?", direction,
                                flags=re.IGNORECASE):
                raise
            signal = BASE_REPORT_SIGNAL(f"Hướng xu hướng: {direction}", labels)
            entry = {"report_sha256": historical_signals.digest(report), "signal": signal,
                     "parser_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                     "rule": "abbreviated_trend_direction_v1"}
            path = output_dir / REPORT_PARSE_FILE
            payload = {"format_version": 1, "entries": []}
            if path.exists():
                envelope = read_json(path)
                exact_object(envelope, {"payload", "sha256"})
                payload = envelope["payload"]
                exact_object(payload, {"format_version", "entries"})
                if (historical_signals.digest(payload) != envelope["sha256"]
                        or payload["format_version"] != 1 or type(payload["entries"]) is not list):
                    raise ValueError("Biên bản đọc báo cáo tương thích sai checksum hoặc cấu trúc")
            if entry not in payload["entries"]:
                payload["entries"].append(entry)
                atomic_write_json(path, {"payload": payload, "sha256": historical_signals.digest(payload)})
            print(f"[Tín hiệu] Đọc trường Trend viết tắt thành {signal}; đã lưu biên bản tương thích.", flush=True)
            return signal

    return parse


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
    historical_signals.report_signal = make_compatible_report_parser(options.output_dir.resolve())
    from scripts.run_historical_memory import main as run_original
    run_original()


if __name__ == "__main__":
    main()
