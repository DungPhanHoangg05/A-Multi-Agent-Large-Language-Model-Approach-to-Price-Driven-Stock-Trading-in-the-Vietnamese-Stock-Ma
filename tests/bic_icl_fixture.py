"""Fixture SDK/transport thực với HTTP mock và đồng hồ giả cho Decision revision."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
from typing import Any

import httpx
from langchain_groq import ChatGroq

from core.bic_icl_decisions import DecisionBlock
from core.improvement_recovery import ResilientPacer, ResilientTransport


class DecisionFixture:
    """Không đọc key/env hoặc gọi mạng; giữ ledger giữa các block/lượt."""

    def __init__(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.now = 100000.
        self.requests: list[dict[str, Any]] = []
        self.handler: Any = None
        self.payload = {"decision": "LONG", "forecast_horizon": "T+2.5", "confidence": "Cao",
            "risk_reward_ratio": 1.5, "evidence_for": "Bằng chứng fixture.",
            "evidence_against": "Rủi ro fixture.", "justification": "Kiểm thử offline."}
        self.pacer = ResilientPacer(self.root/"usage.json", credential="fixture-secret", amendment_sha256="b"*64,
            clock=lambda: self.now, sleep=self.sleep, policy="request_admission_v2")
        self.transport = ResilientTransport(self.pacer, self.root/"cache", httpx.MockTransport(self.handle))
        self.client = httpx.Client(transport=self.transport)
        self.llm = ChatGroq(model="openai/gpt-oss-20b", api_key="fixture-secret", temperature=0., max_tokens=2048,
            max_retries=0, reasoning_effort="low", reasoning_format="hidden", http_client=self.client)
        self.llm.temperature = 0.
        self.shared = {"reports": {"trend_report": "Xu hướng fixture."}, "current_signals": {"trend": "BULLISH"},
            "market_regime": {"as_of_date": "2023-01-06", "feature_end_date": "2023-01-06", "regime_name": "BULL"},
            "prior_provenance": {"context": {"as_of_date": "2023-01-06"}}}

    def sleep(self, seconds: float) -> None:
        """Tiến đồng hồ giả, không đợi hạn quota thật."""
        self.now += seconds

    def restart(self) -> None:
        """Dựng lại pacer/transport/SDK từ ledger và cache disk, như process mới."""
        self.client.close()
        self.pacer = ResilientPacer(self.root/"usage.json", credential="fixture-secret", amendment_sha256="b"*64,
            clock=lambda: self.now, sleep=self.sleep, policy="request_admission_v2")
        self.transport = ResilientTransport(self.pacer, self.root/"cache", httpx.MockTransport(self.handle))
        self.client = httpx.Client(transport=self.transport)
        self.llm = ChatGroq(model="openai/gpt-oss-20b", api_key="fixture-secret", temperature=0., max_tokens=2048,
            max_retries=0, reasoning_effort="low", reasoning_format="hidden", http_client=self.client)
        self.llm.temperature = 0.

    def response(self, payload: dict[str, Any] | None = None) -> httpx.Response:
        """Response provider chỉ chứa JSON/schema fixture."""
        return httpx.Response(200, json={"id": "fixture-response", "object": "chat.completion", "created": 1,
            "model": "openai/gpt-oss-20b", "choices": [{"index": 0, "message": {"role": "assistant",
                "content": json.dumps(self.payload if payload is None else payload, ensure_ascii=False)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}})

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Ghi body thực, không ghi credential/header."""
        self.requests.append(json.loads(request.content))
        return self.handler(request) if self.handler else self.response()

    def block(self, repeat_id: int = 0, *, point_id: str = "FPT-2023-01-06", signature: str = "a"*64) -> DecisionBlock:
        """Các block dùng cùng client/pacer đã kiểm, nhưng slot khoa học riêng."""
        return DecisionBlock(self.root/"run", signature, point_id, repeat_id, self.llm, fixture=True)

    def request(self, name: str, *, prompt: str = "Prompt Original fixture.", prefix: str = "", base: str = "c"*64) -> dict[str, Any]:
        """Cấp prompt đã render; prefix/evidence thuộc renderer của task tiếp theo."""
        return {"branch_id": name, "prompt": prompt, "prefix": prefix,
            "base_evidence_sha256": None if name in ("original", "original_duplicate") else base}

    def run(self, block: DecisionBlock, requests: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Shared luôn cấp bằng bản sao, verifier callback mặc định không I/O."""
        return block.run(deepcopy(self.shared), requests, verify_sources=lambda: None, **kwargs)

    def close(self) -> None:
        """Đóng HTTP handles trước khi dọn checkpoint Windows."""
        self.client.close()
        self.directory.cleanup()
