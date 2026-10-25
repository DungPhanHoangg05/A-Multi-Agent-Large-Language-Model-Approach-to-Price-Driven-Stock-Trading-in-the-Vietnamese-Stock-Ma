"""SDK Groq thật qua HTTP mock; source/context tổng hợp, không dùng key hoặc API thật."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import httpx
from langchain_groq import ChatGroq

from core.historical_signals import digest
from core.improvement_recovery import ResilientPacer
from core.unified_bayes_decision import DecisionPreparer
from core.unified_bayes_runtime import ExecutionJournal, branch_order
from core.unified_bayes_transport import UnifiedTransport
from unified_context_test_support import dense_inputs, features, make_context, query

MODELS = {"agent_llm_model": "openai/gpt-oss-20b", "agent_llm_temperature": 0., "agent_llm_max_tokens": 2048}
PAYLOAD = {"decision": "LONG", "forecast_horizon": "T+2.5", "confidence": "Cao", "risk_reward_ratio": 1.5,
    "evidence_for": "Tín hiệu hiện tại.", "evidence_against": "Rủi ro.", "justification": "Căn cứ hiện tại khác prior."}


class SourcePoint:
    """Fake biên source; mọi packet vẫn qua context/stats/selector/prompt/SDK production."""

    def __init__(self, input_features: dict[str, Any], shared: dict[str, Any]) -> None:
        self._features = deepcopy(input_features)
        self._shared = deepcopy(shared)
        self.changed = False
        self.checks = 0
        self._adapter = SimpleNamespace(verify_sources=self.check)
        self.source_provenance = {"context": {"symbol": shared["stock_name"], "as_of_date": shared["as_of_date"]},
                                  "fixture_source_sha256": "a" * 64}

    def check(self) -> None:
        """Nguồn đổi phải dừng trước invocation; không đọc file trong fixture."""
        self.checks += 1
        if self.changed:
            raise ValueError("Nguồn fixture đã đổi")

    def verify_source(self, state: dict[str, Any]) -> None:
        """Full phải giữ nguyên cả năm report và metadata query."""
        self.check()
        if digest(state) != digest(self._shared):
            raise ValueError("Full khác source đã seal")

    def price_features(self) -> dict[str, Any]:
        """Feature qua extractor thật trước khi tạo điểm giả."""
        return deepcopy(self._features)


def shared_state(cutoff: str = "2023-01-06", *, language: str = "vi", saturated: bool = False) -> dict[str, Any]:
    """Không có outcome hoặc Decision trong Full chung."""
    q = query(cutoff)
    return {"stock_name": q["symbol"], "as_of_date": cutoff, "time_frame": "1d", "is_backtest": True,
        "language": language, "current_signals": q["current_signals"], "market_regime": {"regime_name": q["current_regime"]},
        **{name + "_report": "Đ" * 10000 if saturated else f"Báo cáo {name} tại {cutoff}."
           for name in ("trend", "pattern", "indicator", "alpha", "sentiment")}}


class ExecutionFixture:
    """Một ledger/cache thật trong temp, fake clock và HTTP server có thể gây lỗi."""

    def __init__(self, root: Path, context: Any, inputs: dict[str, Any], *, cutoff: str = "2023-01-06") -> None:
        self.root, self.context, self.inputs, self.cutoff = root, context, inputs, cutoff
        self.now = 100000.
        self.calls: list[dict[str, Any]] = []
        self.handler: Any = None
        self.pacer = ResilientPacer(root / "usage.json", credential="fixture-secret", amendment_sha256="a" * 64,
            clock=lambda: self.now, sleep=lambda seconds: setattr(self, "now", self.now + seconds), policy="request_admission_v2")
        self.transport = UnifiedTransport(self.pacer, root / "cache", httpx.MockTransport(self.respond))
        self.client = httpx.Client(transport=self.transport)
        self.llm = ChatGroq(model=MODELS["agent_llm_model"], api_key="fixture-secret", temperature=0., max_tokens=2048,
            max_retries=0, reasoning_effort="low", reasoning_format="hidden", http_client=self.client)
        self.llm.temperature = 0.
        self.source: SourcePoint | None = None
        self.prepared: Any = None
        self.budget_patch = patch("core.groq_pacing.request_budget", return_value=20)
        self.budget_patch.start()

    def close(self) -> None:
        """Nhả client/fake budget, không để state mock lọt sang test khác."""
        self.client.close()
        self.budget_patch.stop()

    def response(self, payload: Any = None) -> httpx.Response:
        """HTTP response đủ để SDK thật parse structured output."""
        payload = PAYLOAD if payload is None else payload
        content = payload if type(payload) is str else json.dumps(payload, ensure_ascii=False)
        return httpx.Response(200, json={"id": "fixture-response", "object": "chat.completion", "created": 1,
            "model": MODELS["agent_llm_model"], "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
            "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}})

    def respond(self, request: httpx.Request) -> httpx.Response:
        """Ghi từng HTTP thực; shared-off/cache không được đi qua callback này."""
        self.calls.append(json.loads(request.content))
        return self.handler(request) if self.handler else self.response()

    def prepare(self, *, language: str = "vi", saturated: bool = False) -> Any:
        """Chỉ mock cold renderer loader; toàn producer còn lại chạy thật."""
        shared = shared_state(self.cutoff, language=language, saturated=saturated)
        self.source = SourcePoint(features(self.inputs, self.cutoff), shared)
        with patch("core.unified_bayes_decision.load_renderer_lock", return_value={}):
            producer = DecisionPreparer(self.context, self.llm, MODELS)
        self.prepared = producer.prepare(self.source, shared)
        return self.prepared

    def journal(self, *, repeats: bool = False, create: bool = True) -> ExecutionJournal:
        """Manifest khóa trước action; repeat luôn đủ ba lượt với duplicate độc lập."""
        point = self.prepared or self.prepare()
        schedule = [{"point_id": point.point_id, "repeat_id": rid, "order": branch_order(0, rid)}
                    for rid in ((0, 1, 2, 3) if repeats else (0,))]
        return ExecutionJournal(self.root / "run", "b" * 64, [point], self.llm, schedule, create=create)
