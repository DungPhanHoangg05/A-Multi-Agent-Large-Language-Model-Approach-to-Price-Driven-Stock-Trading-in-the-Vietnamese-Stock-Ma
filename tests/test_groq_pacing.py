"""Kiểm pacing mọi transport, quota durable và dừng trước khi bắt đầu điểm."""

from pathlib import Path
import tempfile
import json
import unittest
from unittest.mock import patch, Mock

import httpx

from core.groq_pacing import GroqPacer, MODEL_LIMITS, PacedGroqTransport, PilotStop, request_budget
from core.historical_signals import MODEL_CONFIG_KEYS
from default_config import DEFAULT_CONFIG


class GroqPacingTests(unittest.TestCase):
    """Đồng hồ giả kiểm cửa sổ token, không dùng API hay nghỉ thật."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "usage.json"
        self.now = 100000.
        self.sleeps = []
        def sleep(seconds: float) -> None:
            self.sleeps.append(seconds)
            self.now += seconds
        self.pacer = GroqPacer(self.path, clock=lambda: self.now, sleep=sleep)
        self.model = "openai/gpt-oss-20b"

    def body(self, model: str | None = None) -> dict:
        return {"model": model or self.model, "messages": [{"role": "user", "content": "kiểm tra"}],
                "max_tokens": 1024, "stream": False}

    def daily_rows(self, count: int, tokens: int = 8000) -> None:
        """Tạo usage hợp lệ đã qua cửa sổ phút nhưng còn trong ngày."""
        self.pacer.state["requests"] = [{"model": self.model, "started_at": self.now - 100,
            "reserved_tokens": tokens, "status": "unknown"} for _ in range(count)]

    def test_request_policy_admits_at_8000_remaining_without_48000_reserve(self) -> None:
        self.daily_rows(24)
        with self.assertRaises(PilotStop):
            self.pacer.before_point()
        self.pacer.policy = "request_admission_v2"
        self.pacer.before_point()
        self.assertEqual(len(self.pacer.state["requests"]), 24)
        self.pacer.reserve(self.model, 8000)
        with self.assertRaises(PilotStop):
            self.pacer.reserve(self.model, 1)
        self.assertEqual(self.pacer.state["last_stop"]["remaining_tokens"], 0)
        self.assertIsNotNone(self.pacer.state["last_stop"]["resume_not_before_utc"])

    def test_rpd_boundary_and_expiration_keep_unknown_history(self) -> None:
        self.daily_rows(1000, 1)
        with self.assertRaises(PilotStop):
            self.pacer.reserve(self.model, 1)
        self.now += 86300
        self.pacer.reserve(self.model, 1)
        self.assertEqual(len(self.pacer.state["requests"]), 1001)

    def test_120_seconds_total_wait_and_durable_measured_pacing(self) -> None:
        first = self.pacer.reserve(self.model, 1)
        first["retry_until"] = self.now + 120
        record = self.pacer.reserve(self.model, 1)
        self.assertEqual(record["pacing_seconds"], 120.)
        self.assertEqual(self.pacer.state["pacing_seconds"], 120.)
        self.assertEqual(self.sleeps, [30.] * 4)
        first["retry_until"] = self.now + 121
        with self.assertRaises(PilotStop):
            self.pacer.reserve(self.model, 1)
        self.assertEqual(len(self.sleeps), 4)

    def test_repeated_short_delays_cannot_reset_wait_budget(self) -> None:
        first = self.pacer.reserve(self.model, 1)
        first["retry_until"] = self.now + 60
        def moving_cooldown(seconds: float) -> None:
            self.now += seconds
            first["retry_until"] = self.now + 60
        self.pacer.sleep = moving_cooldown
        with self.assertRaises(PilotStop):
            self.pacer.reserve(self.model, 1)
        self.assertEqual(self.pacer.state["last_stop"]["pacing_seconds"], 90.)
        self.assertEqual(len(self.pacer.state["requests"]), 1)

    def test_long_cooldown_blocks_before_upstream(self) -> None:
        first = self.pacer.reserve(self.model, 1)
        first["retry_until"] = self.now + 554
        with self.assertRaises(PilotStop):
            self.pacer.before_point()
        self.assertEqual(self.pacer.state["last_stop"]["reason"], "COOLDOWN_BEFORE_POINT")
        self.assertFalse(self.sleeps)

    def test_changed_limits_fail_closed_and_higher_limits_do_not_expand_budget(self) -> None:
        first = self.pacer.reserve(self.model, 1)
        first["rate_limits"] = {"x-ratelimit-limit-tokens": "4000"}
        with self.assertRaises(PilotStop):
            self.pacer.reserve(self.model, 1)
        first["rate_limits"] = {"x-ratelimit-limit-tokens": "16000"}
        with self.assertRaises(PilotStop):
            self.pacer.reserve(self.model, 8001)
        self.pacer.state["limits"] = {**MODEL_LIMITS, self.model: {"tpm": 4000}}
        self.pacer.save()
        with self.assertRaises(ValueError):
            GroqPacer(self.path)

    def test_provider_daily_reset_uses_header_and_bad_header_stops(self) -> None:
        first = self.pacer.reserve(self.model, 1)
        first["rate_limits"] = {"x-ratelimit-remaining-requests": "0", "x-ratelimit-reset-requests": "2m10s"}
        with self.assertRaises(PilotStop):
            self.pacer.reserve(self.model, 1)
        self.now += 131
        self.pacer.reserve(self.model, 1)
        self.pacer.state["requests"][-1]["rate_limits"] = {"x-ratelimit-remaining-tokens": "nan"}
        with self.assertRaises(PilotStop):
            self.pacer.reserve(self.model, 1)

    def test_underestimate_returns_response_but_stops_next_http_even_after_resume(self) -> None:
        seen = []
        def respond(request):
            seen.append(request)
            return httpx.Response(200, json={"usage": {"total_tokens": 9000}, "choices": []})
        with httpx.Client(transport=PacedGroqTransport(self.pacer, httpx.MockTransport(respond))) as client:
            self.assertEqual(client.post("https://api.groq.com/openai/v1/chat/completions", json=self.body()).status_code, 200)
            with self.assertRaises(PilotStop):
                client.post("https://api.groq.com/openai/v1/chat/completions", json=self.body())
        self.assertEqual(len(seen), 1)
        restored = GroqPacer(self.path)
        with self.assertRaises(PilotStop):
            restored.before_point()

    def test_cli_checks_cache_without_key_or_network_and_loads_ledger_under_lock(self) -> None:
        from scripts import run_bayesian_ablation as cli
        plan = {"cutoffs": ["2023-01-01"], "signal_config": {}}
        held = []
        class Lock:
            """Khóa giả kiểm thứ tự nạp ledger; khóa OS thật có suite riêng."""
            def __init__(self, *args):
                pass
            def __enter__(self):
                held.append(True)
            def __exit__(self, *args):
                held.pop()
        def pacer(*args, **kwargs):
            self.assertTrue(held)
            self.assertEqual(kwargs["policy"], "request_admission_v2")
            return Mock()
        with patch.object(cli, "verify_inputs", return_value=plan), patch.object(cli, "build_adapter"), \
             patch.object(cli, "tokenizer_cached", return_value=False), patch.object(cli, "dotenv_values") as key, \
             patch.object(cli, "GroqPacer", side_effect=pacer) as constructor, \
             patch.object(cli, "PriorRunLock", Lock), patch.object(cli, "execute"):
            with patch("sys.argv", ["runner", "--run"]), self.assertRaisesRegex(ValueError, "prepare_groq_tokenizer"):
                cli.main()
            key.assert_not_called()
            constructor.assert_not_called()
            with patch("sys.argv", ["runner", "--verify-only"]):
                cli.main()
            constructor.assert_called_once()
            key.assert_not_called()

    def test_token_reservations_wait_before_http_and_survive_key_rotation(self) -> None:
        self.pacer.reserve(self.model, 5000)
        restored = GroqPacer(self.path, clock=lambda: self.now, sleep=self.pacer.sleep)
        restored.reserve(self.model, 5000)
        self.assertGreaterEqual(sum(self.sleeps), 61)
        self.assertTrue(all(s <= 30 for s in self.sleeps))
        self.assertEqual(len(restored.state["requests"]), 2)

    def test_rpm_independent_of_tpm(self) -> None:
        for _ in range(30):
            self.pacer.reserve(self.model, 1)
        self.assertFalse(self.sleeps)
        self.pacer.reserve(self.model, 1)
        self.assertGreaterEqual(sum(self.sleeps), 61)

    def test_models_have_separate_buckets_and_shared_ledger(self) -> None:
        self.pacer.reserve(self.model, 7000)
        self.pacer.reserve("qwen/qwen3.8-27b", 7000)
        self.assertFalse(self.sleeps)

    def test_vision_counts_2048_and_output_not_base64_size(self) -> None:
        body = self.body("qwen/qwen3.8-27b")
        body["messages"][0]["content"] = [{"type": "text", "text": "x"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "a" * 100000}}]
        budget = request_budget(body)
        self.assertGreaterEqual(budget, 2048 + 1024)
        self.assertLess(budget, 4000)
        body["max_tokens"] = 2048
        self.assertEqual(request_budget(body), budget + 1024)

    def test_daily_and_oversized_request_stop_without_reserving(self) -> None:
        with self.assertRaises(PilotStop):
            self.pacer.reserve(self.model, 8001)
        self.pacer.state["requests"] = [{"model": self.model, "started_at": self.now,
            "reserved_tokens": 8000, "total_tokens": 199000, "status": 200}]
        with self.assertRaises(PilotStop):
            self.pacer.reserve(self.model, 2000)
        with self.assertRaises(PilotStop):
            self.pacer.before_point()
        self.assertEqual(len(self.pacer.state["requests"]), 1)

    def test_retry_after_is_durable_and_not_waited_inside_agent(self) -> None:
        inner = httpx.MockTransport(lambda request: httpx.Response(429,
            headers={"retry-after": "554"}, json={"error": {"message": "quota secret-must-not-save"}}))
        with httpx.Client(transport=PacedGroqTransport(self.pacer, inner)) as client:
            with self.assertRaises(PilotStop):
                client.post("https://api.groq.com/openai/v1/chat/completions", json=self.body(),
                            headers={"Authorization": "Bearer secret-key"})
        self.assertEqual(self.pacer.state["requests"][0]["retry_until"], self.now + 554)
        self.assertNotIn("secret", self.path.read_text("utf-8"))
        restored = GroqPacer(self.path, clock=lambda: self.now, sleep=self.pacer.sleep)
        with self.assertRaises(PilotStop):
            restored.reserve(self.model, 1000)
        self.assertFalse(self.sleeps)

    def test_real_usage_request_id_and_structured_payload_are_measured(self) -> None:
        inner = httpx.MockTransport(lambda request: httpx.Response(200, headers={"x-request-id": "provider-real-id"},
            json={"usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40}, "choices": []}))
        body = self.body()
        body["response_format"] = {"type": "json_object"}
        with httpx.Client(transport=PacedGroqTransport(self.pacer, inner)) as client:
            response = client.post("https://api.groq.com/openai/v1/chat/completions", json=body)
        self.assertEqual(response.status_code, 200)
        saved = self.pacer.state["requests"][0]
        self.assertEqual(saved["total_tokens"], 40)
        self.assertEqual(saved["request_id"], "provider-real-id")
        self.assertNotIn("messages", saved)

    def test_provider_remaining_tokens_prevent_external_usage_collision(self) -> None:
        first = self.pacer.reserve(self.model, 100)
        first.update(completed_at=self.now, rate_limits={"x-ratelimit-remaining-tokens": "0"})
        self.pacer.reserve(self.model, 4000)
        self.assertGreaterEqual(sum(self.sleeps), 30)

    def test_bad_request_without_model_or_streaming_is_rejected(self) -> None:
        for field, value in (("model", "other-model"), ("stream", True), ("max_tokens", None)):
            body = self.body()
            body[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                request_budget(body)

    def test_real_chatgroq_clients_send_exact_frozen_temperature_and_options(self) -> None:
        from scripts.run_bayesian_ablation import make_builder
        from langchain_core.messages import HumanMessage
        from utils.historical_api import _invoke_with_retry
        seen = []
        def respond(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            seen.append(body)
            return httpx.Response(200, json={"id": "chatcmpl-fixture", "object": "chat.completion", "created": 1,
                "model": body["model"], "choices": [{"index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": '{"ok":true}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}})
        plan = {"signal_config": {"models": {key: DEFAULT_CONFIG[key] for key in MODEL_CONFIG_KEYS}},
                "client_options": {"agent": {"reasoning_format": "hidden", "reasoning_effort": "low"},
                                   "graph": {"reasoning_format": "hidden", "reasoning_effort": "none"}}}
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            builder = make_builder(plan, "offline-fixture-key", client)
            for llm in (builder.agent_llm, builder.graph_llm):
                self.assertEqual(llm.temperature, 0.)
                _invoke_with_retry(llm.invoke, [HumanMessage(content="test")], retries=1)
        self.assertEqual([body["temperature"] for body in seen], [0., 0.])
        self.assertEqual([body["reasoning_effort"] for body in seen], ["low", "none"])


if __name__ == "__main__":
    unittest.main()
