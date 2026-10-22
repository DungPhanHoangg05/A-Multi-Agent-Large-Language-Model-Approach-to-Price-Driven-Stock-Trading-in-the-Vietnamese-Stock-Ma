"""Kiểm shared-off/alias/duplicate bằng serializer và HTTP mock production."""

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx

from bic_icl_fixture import DecisionFixture
from core.bic_icl_decisions import DecisionBlock, branch_order, shared_stage_scope
from core.groq_pacing import PilotStop
from core.research_cohort import read_envelope, save_envelope
from core.research_input_lock import _write_once
from core.prior_run_lock import PriorRunLock


class DecisionBlockTests(unittest.TestCase):
    """Các bản sao logic không phát sinh HTTP hoặc quan sát độc lập giả."""

    def setUp(self) -> None:
        """Tạo fixture hoàn toàn offline cho từng ca."""
        self.f = DecisionFixture()
        self.addCleanup(self.f.close)
        self.original = self.f.request("original")

    def test_off_reuses_original_raw_and_never_creates_http_attempt(self) -> None:
        """Prior-off giống toàn request dùng raw Original cùng point/lượt."""
        block = self.f.block()
        requests = [self.original, self.f.request("A_reference_shared_off"), self.f.request("R_pool_full")]
        result = self.f.run(block, requests, create=True)
        branches = result["branches"]
        self.assertEqual(len(self.f.requests), 1)
        self.assertEqual(len(self.f.pacer.state["requests"]), 1)
        for name in ("A_reference_shared_off", "R_pool_full"):
            self.assertEqual(branches[name]["output"], branches["original"]["output"])
            self.assertEqual(branches[name]["decision_origin"], "shared_original")
            self.assertEqual(branches[name]["attempts"], [])
            self.assertEqual(branches[name]["source"]["branch_id"], "original")
        branches["R_pool_full"]["output"]["messages"][0]["data"]["content"] = "Đổi bản sao."
        self.assertNotEqual(branches["original"]["output"], branches["R_pool_full"]["output"])
        self.assertEqual(self.f.run(block, requests, verify_only=True)["branches"]["original"]["status"], "complete")

    def test_empty_prefix_with_different_message_calls_llm(self) -> None:
        """Prefix rỗng không đủ để reuse request khác Original."""
        result = self.f.run(self.f.block(), [self.original, self.f.request("R_pool_full", prompt="Prompt khác.")], create=True)
        self.assertEqual(len(self.f.requests), 2)
        self.assertEqual(result["branches"]["R_pool_full"]["decision_origin"], "llm")

    def test_stats_alias_is_restricted_to_pair_and_shared_base(self) -> None:
        """Hai stats cùng body/base dùng một Decision; full không alias stats."""
        prefix = "Posterior fixture."
        options = {"prompt": prefix+" Prompt.", "prefix": prefix}
        rows = [self.original, self.f.request("R_task_stats_only", **options),
            self.f.request("R_pool_stats_only", **options), self.f.request("R_pool_full", **options)]
        result = self.f.run(self.f.block(), rows, create=True)
        self.assertEqual(len(self.f.requests), 3)
        alias = result["branches"]["R_pool_stats_only"]
        self.assertEqual(alias["decision_origin"], "stats_alias")
        self.assertEqual(alias["source"]["branch_id"], "R_task_stats_only")
        self.assertEqual(result["branches"]["R_pool_full"]["decision_origin"], "llm")

    def test_equal_stats_messages_with_different_base_do_not_alias(self) -> None:
        """Body trùng nhưng base khác không là đối chứng stats ghép cặp đã khóa."""
        options = {"prompt": "Prior. Prompt.", "prefix": "Prior."}
        rows = [self.original, self.f.request("R_pool_stats_only", **options),
            self.f.request("R_task_stats_only", base="d"*64, **options)]
        result = self.f.run(self.f.block(), rows, create=True)
        self.assertEqual(len(self.f.requests), 3)
        self.assertEqual(result["branches"]["R_task_stats_only"]["decision_origin"], "llm")

    def test_repeat_and_duplicate_are_independent_of_primary(self) -> None:
        """Mỗi repeat có Original mới; duplicate cùng body nhưng UUID/HTTP riêng."""
        self.f.run(self.f.block(), [self.original, self.f.request("R_pool_full")], create=True)
        rows = [self.original, self.f.request("original_duplicate"), self.f.request("R_pool_full")]
        result = self.f.run(self.f.block(1), rows, create=True)
        self.assertEqual(len(self.f.requests), 3)
        branches = result["branches"]
        self.assertEqual(branches["original_duplicate"]["decision_origin"], "independent_duplicate")
        self.assertNotEqual(branches["original"]["attempts"][0]["attempt_id"],
            branches["original_duplicate"]["attempts"][0]["attempt_id"])
        self.assertEqual(branches["R_pool_full"]["source"]["branch_id"], "original")

    def test_completed_resume_and_later_ledger_append_are_read_only(self) -> None:
        """Ledger tăng cho point/lượt khác không làm replay block đã complete."""
        block = self.f.block()
        rows = [self.original, self.f.request("R_pool_full")]
        result = self.f.run(block, rows, create=True)
        before = block.path.read_bytes()
        self.f.run(self.f.block(1), [self.original, self.f.request("original_duplicate"), self.f.request("R_pool_full")], create=True)
        calls = len(self.f.requests)
        self.assertEqual(self.f.run(block, rows), result)
        self.assertEqual(self.f.run(block, rows, verify_only=True), result)
        self.assertEqual(block.path.read_bytes(), before)
        self.assertEqual(len(self.f.requests), calls)

    def test_other_point_same_prompt_requires_new_original(self) -> None:
        """Body trùng giữa hai ngày không chia sẻ scientific response hoặc UUID."""
        first = self.f.run(self.f.block(), [self.original, self.f.request("R_pool_full")], create=True)
        self.f.shared["market_regime"].update(as_of_date="2023-01-09", feature_end_date="2023-01-09")
        self.f.shared["prior_provenance"]["context"]["as_of_date"] = "2023-01-09"
        second = self.f.run(self.f.block(point_id="FPT-2023-01-09"),
                            [self.original, self.f.request("R_pool_full")], create=True)
        self.assertEqual(len(self.f.requests), 2)
        self.assertNotEqual(first["branches"]["original"]["attempts"][0]["attempt_id"],
                            second["branches"]["original"]["attempts"][0]["attempt_id"])

    def test_original_durable_before_alias_crash_is_not_replayed(self) -> None:
        """Dừng lúc persist alias không gọi lại Original đã complete."""
        block = self.f.block(); rows = [self.original, self.f.request("R_pool_full")]
        original_save = save_envelope
        def crash(path, value):
            if value["branches"]["R_pool_full"]["status"] == "complete":
                raise KeyboardInterrupt("Fixture ngắt trước ghi alias.")
            original_save(path, value)
        with patch("core.bic_icl_decisions.save_envelope", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                self.f.run(block, rows, create=True)
        self.assertEqual(len(self.f.requests), 1)
        result = self.f.run(block, rows)
        self.assertEqual(result["branches"]["R_pool_full"]["status"], "complete")
        self.assertEqual(len(self.f.requests), 1)

    def test_unknown_after_durable_http_resumes_same_uuid_without_http(self) -> None:
        """Cache response đã fsync phục hồi khi process chết trước checkpoint complete."""
        block = self.f.block(); rows = [self.original]
        original_save = save_envelope
        def crash(path, value):
            if value["branches"]["original"]["status"] == "complete":
                raise KeyboardInterrupt("Fixture sau HTTP durable.")
            original_save(path, value)
        with patch("core.bic_icl_decisions.save_envelope", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                self.f.run(block, rows, create=True)
        pending = read_envelope(block.path)["branches"]["original"]
        self.assertEqual(pending["status"], "unknown")
        self.f.restart()
        result = self.f.run(self.f.block(), rows)
        completed = result["branches"]["original"]
        self.assertEqual(completed["attempts"][0]["attempt_id"], pending["attempts"][0]["attempt_id"])
        self.assertEqual(len(completed["resumes"]), 1)
        self.assertEqual(len(self.f.requests), 1)
        self.assertTrue(any(e["reason"] == "DURABLE_RESPONSE_REUSED" for e in self.f.pacer.state["recovery_events"]))

    def test_orphan_identity_before_state_recovers_without_new_scientific_slot(self) -> None:
        """Crash khởi tạo trước state chưa thể gọi HTTP; resume phục hồi cùng binding."""
        block = self.f.block()
        def fail(path, value):
            if path.name == "state.json":
                raise KeyboardInterrupt("Fixture sau identity trước state.")
            _write_once(path, value)
        with patch("core.bic_icl_decisions._write_once", side_effect=fail):
            with self.assertRaises(KeyboardInterrupt):
                self.f.run(block, [self.original], create=True)
        self.assertEqual(self.f.requests, [])
        self.assertEqual(self.f.run(block, [self.original])["branches"]["original"]["status"], "complete")
        self.assertEqual(len(self.f.requests), 1)

    def test_orphan_planned_state_before_ready_recovers_safely(self) -> None:
        """State planned trước ready không bị nhầm thành response hoặc replay complete."""
        block = self.f.block()
        def fail(path, value):
            if path.name == "ready.json":
                raise KeyboardInterrupt("Fixture sau planned state trước ready.")
            _write_once(path, value)
        with patch("core.bic_icl_decisions._write_once", side_effect=fail):
            with self.assertRaises(KeyboardInterrupt):
                self.f.run(block, [self.original], create=True)
        self.assertEqual(self.f.requests, [])
        self.assertEqual(self.f.run(block, [self.original])["branches"]["original"]["status"], "complete")
        self.assertEqual(len(self.f.requests), 1)

    def test_existing_block_lock_prevents_concurrent_http(self) -> None:
        """Hai writer không được cùng tiến slot khi một handle OS còn sống."""
        block = self.f.block()
        with PriorRunLock(self.f.root/"run/decision_lock", "a"*64):
            with self.assertRaises(RuntimeError):
                self.f.run(block, [self.original], create=True)
        self.assertEqual(self.f.requests, [])

    def test_intent_crash_before_http_resumes_one_uuid(self) -> None:
        """Intent durable không được thay bằng UUID mới khi chưa có HTTP."""
        block = self.f.block()
        with patch.object(block, "_invoke", side_effect=KeyboardInterrupt("Fixture trước HTTP.")):
            with self.assertRaises(KeyboardInterrupt):
                self.f.run(block, [self.original], create=True)
        pending = read_envelope(block.path)["branches"]["original"]
        result = self.f.run(block, [self.original])
        self.assertEqual(result["branches"]["original"]["attempts"][0]["attempt_id"], pending["attempts"][0]["attempt_id"])
        self.assertEqual(len(self.f.requests), 1)

    def test_rate_limit_and_format_repair_share_uuid_and_true_ledger(self) -> None:
        """429 và output sai schema là HTTP thật trong cùng scientific attempt."""
        def handle(request):
            if len(self.f.requests) == 1:
                return httpx.Response(429, headers={"retry-after": "1"}, json={"error": {"message": "TPM retry after 1 seconds"}})
            if len(self.f.requests) == 2:
                return self.f.response({"decision": "NEUTRAL"})
            return self.f.response()
        self.f.handler = handle
        result = self.f.run(self.f.block(), [self.original, self.f.request("R_pool_full")], create=True)
        self.assertEqual([r["status"] for r in self.f.pacer.state["requests"]], [429, 200, 200])
        self.assertEqual(len({r["checkpoint_attempt_id"] for r in self.f.pacer.state["requests"]}), 1)
        self.assertEqual(result["branches"]["R_pool_full"]["attempts"], [])
        self.assertNotIn("fixture-secret", (self.f.root/"usage.json").read_text())

    def test_daily_quota_stops_following_slots_and_verify_never_calls(self) -> None:
        """Quota ngày giữ unknown; không giả CASH hoặc chạy nhánh kế tiếp."""
        self.f.handler = lambda request: httpx.Response(429, headers={"retry-after": "3600"},
            json={"error": {"message": "Rate limit reached on tokens per day (TPD)"}})
        block = self.f.block(); rows = [self.original, self.f.request("R_pool_full")]
        with self.assertRaises(PilotStop):
            self.f.run(block, rows, create=True)
        result = self.f.run(block, rows, verify_only=True)
        self.assertEqual(result["branches"]["original"]["status"], "unknown")
        self.assertIsNone(result["branches"]["original"]["output"])
        self.assertEqual(result["branches"]["R_pool_full"]["status"], "planned")
        self.assertEqual(len(self.f.requests), 1)

    def test_scheduler_original_first_and_repeat_rotation(self) -> None:
        """Xoay chỉ các nhánh ngoài Original, không thêm Numeric thành HTTP slot."""
        self.assertEqual(branch_order("development", 0)[0], "original")
        self.assertEqual(len(branch_order("development", 0)), 8)
        self.assertEqual(len(branch_order("development", 1, task_enabled=False)), 5)
        self.assertEqual(len(branch_order("confirmation", 0, 1)), 6)
        first = branch_order("development", 0, 1)[1:]
        self.assertEqual(branch_order("development", 1, 1), ["original", *first[3:], *first[:3]])
        for args in (("other", 0, 0), ("development", True, 0), ("development", 0, 4)):
            with self.assertRaises(ValueError):
                branch_order(*args)

    def test_shared_stages_resume_once_and_deep_copy_outputs(self) -> None:
        """Cùng journal qua primary/repeat dùng lại bốn stage, state đầu không đổi."""
        events = []
        outputs = {"indicator": {"indicator_report": "I"}, "pattern": {"pattern_report": "P"},
            "trend": {"trend_report": "T", "trend_image": "ảnh", "trend_image_filename": "ảnh.png", "trend_image_description": "D"},
            "full": {"alpha_report": "A", "sentiment_report": "S", "sentiment_data": {}, "sentiment_norm": {}}}
        initial = {"stock_name": "FPT", "as_of_date": "2023-01-06"}
        def invoke(name, state):
            events.append(name)
            return deepcopy(outputs[name])
        for round_index in range(2):
            state = deepcopy(initial)
            with shared_stage_scope(self.f.root/"run", "a"*64, "FPT-2023-01-06", "d"*64,
                                    create=round_index == 0, fixture=True) as journal:
                for name in outputs:
                    state.update(journal.invoke(name, lambda actual, n=name: invoke(n, actual), deepcopy(state)))
            state["sentiment_data"]["mutated"] = True
        self.assertEqual(events, list(outputs))
        self.assertEqual(initial, {"stock_name": "FPT", "as_of_date": "2023-01-06"})


if __name__ == "__main__":
    unittest.main()
