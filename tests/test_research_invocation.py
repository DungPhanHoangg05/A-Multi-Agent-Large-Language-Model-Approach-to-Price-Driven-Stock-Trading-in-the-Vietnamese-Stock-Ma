"""Fault HTTP/format repair chia sẻ ba lượt và 120 giây bằng đồng hồ giả."""

import unittest
from unittest.mock import patch
import httpx

from core.groq_pacing import PacedGroqTransport, PilotStop
from core.research_invocation import ENABLED, invocation_scope
from core.research_metrics import http_telemetry
import test_groq_pacing as support


class InvocationTests(unittest.TestCase):
    def setUp(self):
        self.fx = support.GroqPacingTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        token = ENABLED.set(True)
        self.addCleanup(ENABLED.reset, token)

    def test_429_and_format_repair_share_three_attempts(self):
        seen = []
        def respond(request):
            seen.append(request)
            return httpx.Response(429 if len(seen) == 1 else 200, headers={"retry-after": "1"},
                                  json={"choices": [], "usage": {"total_tokens": 0}})
        with invocation_scope("decision") as budget, httpx.Client(transport=PacedGroqTransport(
                self.fx.pacer, httpx.MockTransport(respond))) as client:
            budget.run_signature = "fixture"
            for _ in range(2):
                client.post("https://api.groq.com/openai/v1/chat/completions", json=self.fx.body())
            with self.assertRaises(PilotStop):
                client.post("https://api.groq.com/openai/v1/chat/completions", json=self.fx.body())
            self.assertEqual(budget.attempts, 3)
            self.assertGreaterEqual(budget.wait_seconds, 5.)
            self.assertLessEqual(budget.wait_seconds, 120.)
        self.assertEqual(len(seen), 3)
        summary = http_telemetry(self.fx.pacer.state["requests"], ["fixture"])
        self.assertEqual(summary["invocation_count"], 1)
        self.assertEqual(summary["total_tokens"]["sum"], 0.)
        self.assertIsNone(summary["completion_tokens"]["sum"])
        self.assertNotIn("messages", str(summary))

    def test_total_wait_across_success_and_next_request_is_bounded(self):
        def respond(request):
            return httpx.Response(429, headers={"retry-after": "65"}, json={"error": {}})
        with invocation_scope("pattern") as budget, httpx.Client(transport=PacedGroqTransport(
                self.fx.pacer, httpx.MockTransport(respond))) as client:
            with self.assertRaises(PilotStop):
                client.post("https://api.groq.com/openai/v1/chat/completions", json=self.fx.body())
            self.assertEqual(len(self.fx.pacer.state["requests"]), 2)
            self.assertEqual(budget.wait_seconds, 66.)
        item = self.fx.pacer.state["invocations"][budget.invocation_id]
        self.assertEqual(item["wait_seconds"], 66.)
        self.assertIsNotNone(item["elapsed_seconds"])

    def test_ambiguous_no_agent_retry_and_no_nested_budget(self):
        from agents.decision_agent import _invoke_with_retry
        with invocation_scope("decision") as budget:
            with invocation_scope("repair") as nested:
                self.assertIs(nested, budget)
            with patch("time.sleep", side_effect=AssertionError("Không ngủ")), self.assertRaises(PilotStop):
                _invoke_with_retry(lambda: (_ for _ in ()).throw(TimeoutError()))

    def test_p95_zero_missing_and_duplicate_http(self):
        rows = [{"id": str(i), "run_signature": "x", "invocation_id": "same", "latency_seconds": v}
                for i, v in enumerate((0., 10., None))]
        out = http_telemetry(rows, ["x"])
        self.assertEqual(out["http_latency_seconds"], {"measured_count": 2, "missing_count": 1, "sum": 10., "p95": 9.5})
        with self.assertRaises(ValueError):
            http_telemetry(rows + [rows[0]], ["x"])


if __name__ == "__main__":
    unittest.main()
