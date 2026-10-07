"""Pacing HTTP dùng chung cho pilot; giữ quota và telemetry khi đổi key/resume."""

from __future__ import annotations

import json
import hashlib
import math
import os
import re
from pathlib import Path
import threading
import tempfile
import time
from typing import Any, Callable
from uuid import uuid4

import httpx
import tiktoken

from core.bayesian_memory import atomic_write_json, read_json


MODEL_LIMITS = {model: {"rpm": 30, "rpd": 1000, "tpm": 8000, "tpd": 200000}
                for model in ("openai/gpt-oss-20b", "qwen/qwen3.8-27b")}


class PilotStop(KeyboardInterrupt):
    """Dừng toàn graph, không để agent retry hoặc dùng báo cáo dự phòng giả."""


def request_budget(body: dict[str, Any]) -> int:
    """Ước lượng bảo thủ văn bản, cộng 2.048 token/ảnh và toàn output reserve.

    GPT-OSS dùng o200k; thêm 20% và overhead cho template/tool. Với Qwen,
    dùng số byte UTF-8 làm chặn trên cho văn bản, không đếm base64 ảnh.
    Đây là reserve trước API; telemetry kiểm lại bằng usage thực của provider.
    """
    model = body.get("model")
    if model not in MODEL_LIMITS or body.get("stream"):
        raise ValueError("Pilot chỉ hỗ trợ hai model đã khóa và response không streaming")
    output = body.get("max_completion_tokens", body.get("max_tokens"))
    if type(output) is not int or output < 1:
        raise ValueError("Mọi request cần giới hạn output token tường minh")
    texts: list[str] = []
    images = 0
    for message in body["messages"]:
        content = message.get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for part in content:
                if part["type"] == "image_url":
                    images += 1
                elif part["type"] == "text":
                    texts.append(part["text"])
                else:
                    raise ValueError("Loại nội dung chưa có chính sách token")
        elif content is not None:
            raise ValueError("Nội dung request không hợp lệ")
        texts.append(json.dumps({k: v for k, v in message.items() if k != "content"}, ensure_ascii=False))
    for field in ("tools", "response_format"):
        if field in body:
            texts.append(json.dumps(body[field], ensure_ascii=False))
    text = "\n".join(texts)
    if model == "openai/gpt-oss-20b" and tokenizer_cached():
        count = len(tiktoken.get_encoding("o200k_base").encode(text, disallowed_special=()))
        input_reserve = math.ceil(count * 1.2) + 128
    else:
        input_reserve = len(text.encode("utf-8")) + 128
    if images > 3 or (images and model != "qwen/qwen3.8-27b"):
        raise ValueError("Ảnh không phù hợp model hoặc vượt ba ảnh/request")
    return input_reserve + images * 2048 + output


def tokenizer_cached() -> bool:
    """Không tải tokenizer ngầm bên trong API; cache thiếu dùng byte upper bound."""
    url = "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"
    directory = os.environ.get("TIKTOKEN_CACHE_DIR", os.environ.get("DATA_GYM_CACHE_DIR", str(Path(tempfile.gettempdir()) / "data-gym-cache")))
    if not directory:
        return False
    path = Path(directory) / hashlib.sha1(url.encode()).hexdigest()
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"


class GroqPacer:
    """Đặt trước quota từng model; lưu trước HTTP, thất bại giữ nguyên reserve.

    Sử dụng cửa sổ trượt 61 giây/24 giờ, không xóa lịch sử khi đổi key.
    Một tiến trình pilot giữ OS lock; mutex bảo vệ mọi client chung transport.
    """

    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.path, self.clock, self.sleep = path, clock, sleep
        self._mutex = threading.Lock()
        self.state = read_json(path) if path.exists() else {"version": 1, "limits": MODEL_LIMITS, "requests": []}
        if self.state.get("version") != 1 or self.state.get("limits") != MODEL_LIMITS:
            raise ValueError("Quota durable không khớp cấu hình đã xác minh")
        for record in self.state["requests"]:
            if (record["model"] not in MODEL_LIMITS or type(record["reserved_tokens"]) is not int
                    or record["reserved_tokens"] < 1 or not math.isfinite(record["started_at"])):
                raise ValueError("Lịch sử quota không hợp lệ")

    def save(self) -> None:
        """Ghi nguyên tử, không lưu prompt, base64, key hay header xác thực."""
        atomic_write_json(self.path, self.state)

    def reserve(self, model: str, tokens: int) -> dict[str, Any]:
        """Nghỉ ngắn trước request; dừng trước transport nếu daily quota không đủ."""
        limits = MODEL_LIMITS[model]
        if type(tokens) is not int or not 0 < tokens <= limits["tpm"]:
            raise PilotStop("Ngân sách một request vượt TPM; cần cấu hình run mới")
        while True:
            now = self.clock()
            records = [r for r in self.state["requests"] if r["model"] == model]
            daily = [r for r in records if r["started_at"] > now - 86400]
            charged = sum(r.get("total_tokens") or r["reserved_tokens"] for r in daily)
            if len(daily) >= limits["rpd"] or charged + tokens > limits["tpd"]:
                raise PilotStop("Quota ngày không đủ; giữ checkpoint và resume sau khi quota phục hồi")
            minute = [r for r in daily if r["started_at"] > now - 61]
            cooldown = max((r.get("retry_until", 0) for r in records), default=0)
            delay = max(0., cooldown - now)
            if records:
                last = records[-1]
                headers = last.get("rate_limits", {})
                if headers.get("x-ratelimit-remaining-requests") == "0" and now - last["started_at"] < 86400:
                    raise PilotStop("Provider báo RPD còn 0; dừng giữ checkpoint")
                remaining = headers.get("x-ratelimit-remaining-tokens")
                if remaining is not None:
                    available = min(limits["tpm"], float(remaining) + max(0., now - last.get("completed_at", last["started_at"])) * limits["tpm"] / 60)
                    if available < tokens:
                        delay = max(delay, (tokens - available) * 60 / limits["tpm"] + 1.)
            if minute and (len(minute) >= limits["rpm"] or sum(r["reserved_tokens"] for r in minute) + tokens > limits["tpm"]):
                delay = max(delay, min(r["started_at"] for r in minute) + 61 - now)
            if delay > 0:
                if delay > 120:
                    raise PilotStop(f"Provider yêu cầu cooldown {math.ceil(delay)} giây; đã lưu, dừng để resume sau")
                print(f"[Quota] Nghỉ chủ động {delay:.1f} giây trước request {model}", flush=True)
                self.sleep(min(delay, 30.))
                continue
            record = {"id": str(uuid4()), "model": model, "started_at": float(now),
                      "reserved_tokens": tokens, "status": "unknown"}
            self.state["requests"].append(record)
            self.save()
            return record

    def before_point(self) -> None:
        """Giữ dự phòng cho toàn điểm trước upstream; không khởi động khi sát TPD.

        Một điểm tối đa một Indicator + năm Decision và hai vision thành công.
        Retry bất thường vẫn được guard riêng, không đảm bảo daily quota bên
        ngoài tiến trình này. Dự phòng dùng TPM tối đa cho mỗi request.
        """
        now = self.clock()
        for model, requests in (("openai/gpt-oss-20b", 6), ("qwen/qwen3.8-27b", 2)):
            rows = [r for r in self.state["requests"] if r["model"] == model and r["started_at"] > now - 86400]
            tokens = sum(r.get("total_tokens") or r["reserved_tokens"] for r in rows)
            if (tokens + requests * MODEL_LIMITS[model]["tpm"] > MODEL_LIMITS[model]["tpd"]
                    or len(rows) + requests > MODEL_LIMITS[model]["rpd"]):
                raise PilotStop("Quota ngày không đủ dự phòng toàn điểm; chưa bắt đầu upstream, resume sau")


class PacedGroqTransport(httpx.BaseTransport):
    """Quan sát mọi request text/vision/structured/fallback ở ranh giới HTTP."""

    def __init__(self, pacer: GroqPacer, inner: httpx.BaseTransport | None = None) -> None:
        self.pacer, self.inner = pacer, inner or httpx.HTTPTransport(retries=0)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Chặn request không hỗ trợ và lưu usage/status/request ID an toàn."""
        if request.url.host != "api.groq.com":
            raise ValueError("Transport pilot chỉ cho phép Groq")
        if request.method != "POST" or request.url.path != "/openai/v1/chat/completions":
            return self.inner.handle_request(request)
        body = json.loads(request.content)
        with self.pacer._mutex:
            record = self.pacer.reserve(body["model"], request_budget(body))
            try:
                response = self.inner.handle_request(request)
                response.read()
            except (httpx.HTTPError, OSError):
                record.update(status="transport_error", latency_seconds=float(self.pacer.clock() - record["started_at"]))
                self.pacer.save()
                raise PilotStop("Transport gián đoạn; dừng và kiểm checkpoint") from None
            try:
                payload = response.json()
            except ValueError:
                record.update(status=int(response.status_code), error="NON_JSON_RESPONSE")
                self.pacer.save()
                raise PilotStop("Provider trả nội dung không phải JSON; giữ checkpoint") from None
            record.update(status=int(response.status_code), completed_at=float(self.pacer.clock()), latency_seconds=float(self.pacer.clock() - record["started_at"]),
                          request_id=response.headers.get("x-request-id") or payload.get("id"))
            usage = payload.get("usage") or {}
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if type(usage.get(key)) is int and usage[key] >= 0:
                    record[key] = usage[key]
            record["rate_limits"] = {key: response.headers[key] for key in (
                "x-ratelimit-limit-requests", "x-ratelimit-remaining-requests", "x-ratelimit-reset-requests",
                "x-ratelimit-limit-tokens", "x-ratelimit-remaining-tokens", "x-ratelimit-reset-tokens") if key in response.headers}
            if response.status_code == 429:
                try:
                    delay = float(response.headers.get("retry-after", "61"))
                except ValueError:
                    delay = 61.
                # Thông báo provider có thể chứa thời gian dài hơn header.
                message = str((payload.get("error") or {}).get("message", ""))
                match = re.search(r"(?:retry after|try again in)\s*(?:(\d+(?:\.\d+)?)m)?\s*(\d+(?:\.\d+)?)s", message, re.I)
                if match:
                    delay = max(delay, 60 * float(match[1] or 0) + float(match[2]))
                record["retry_until"] = float(self.pacer.clock() + max(61., delay))
            self.pacer.save()
            if response.status_code >= 400:
                raise PilotStop(f"Groq HTTP {response.status_code}; xem telemetry an toàn và giữ checkpoint")
            if record.get("total_tokens", 0) > record["reserved_tokens"]:
                raise PilotStop("Usage thực vượt reserve; cần rà token estimator trước request tiếp theo")
            return response

    def close(self) -> None:
        """Đóng kết nối khi caller kết thúc lượt chạy."""
        self.inner.close()
