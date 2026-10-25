"""Poison metadata, request và control giữa retry phải dừng trước HTTP tiếp theo."""

from copy import deepcopy
import unittest
from unittest.mock import patch

import httpx

from core.historical_signals import digest
from core.research_cohort import read_envelope, save_envelope
from core.unified_bayes_cohort import lock_authorization
from core.unified_bayes_validation import diagnostics, run_gates
from unified_validation_test_support import MATRIX, ValidationFixture


class ValidationLeakageTests(ValidationFixture, unittest.TestCase):
    """Nguồn thật và partition metadata có quyền phủ quyết checksum tự reseal."""

    def test_memory_poison_cannot_reseal_and_enter_diagnostics(self) -> None:
        memory = self.context.memory.payload
        memory["metadata"][0]["exit_date"] = "2025-01-01"
        with self.assertRaises(ValueError):
            diagnostics(self.cohort, self.plan, self.fx.llm, memory)
        self.assertEqual(self.fx.calls, [])
        self.assertEqual(self.fx.evaluations, [])

    def test_partition_missing_member_cannot_pass_self_consistent_plan(self) -> None:
        point = next(iter(self.cohort.prepared.values()))
        point._base["statistics"]["groups"]["B2"]["episode_ids"].pop()
        # Cho cả plan theo dữ liệu sai; oracle metadata vẫn phải chặn độc lập.
        plan = self.cohort.plan(self.fx.llm)
        with self.assertRaises(ValueError):
            diagnostics(self.cohort, plan, self.fx.llm, self.context.memory.payload)

    def test_alias_and_age_poison_in_prepared_state_cannot_reseal(self) -> None:
        point = next(iter(self.cohort.prepared.values()))
        original = deepcopy(point._base)
        point._packets["U_stats"]["visible_aliases"] = {"T1": {"kind": "task"}}
        with self.assertRaises(ValueError):
            diagnostics(self.cohort, self.cohort.plan(self.fx.llm), self.fx.llm, self.context.memory.payload)
        point._packets["U_stats"]["visible_aliases"] = {}
        point._base["selection"]["trace"][0]["age_days"] += 1
        with self.assertRaises(ValueError):
            diagnostics(self.cohort, self.cohort.plan(self.fx.llm), self.fx.llm, self.context.memory.payload)
        point._base = original

    def test_selected_future_self_cross_symbol_unknown_and_old_are_rejected(self) -> None:
        memory = self.context.memory.payload
        point = next(iter(self.cohort.prepared.values()))
        original = deepcopy(point._base)
        rows = memory["metadata"]
        for kind in MATRIX["pit_corruptions"]:
            with self.subTest(kind=kind):
                point._base = deepcopy(original)
                selected = next((r for r in rows if r["symbol"] == "FPT" and r["as_of_date"] < "2021-01-06"), None)
                if kind == "unknown_id":
                    key = "FPT:1900-01-01"
                elif kind == "self_match":
                    key = "FPT:2023-01-06"
                elif kind == "wrong_symbol":
                    key = next(r["episode_id"] for r in rows if r["symbol"] == "MWG")
                elif kind == "future_exit":
                    key = next(r["episode_id"] for r in rows if r["symbol"] == "FPT" and r["exit_date"] >= "2023-01-06")
                else:
                    self.assertIsNotNone(selected)
                    key = selected["episode_id"]
                point._base["selection"]["selected_ids"] = [key]
                with self.assertRaises(ValueError):
                    diagnostics(self.cohort, self.cohort.plan(self.fx.llm), self.fx.llm, memory)
        point._base = original
        self.assertEqual(self.fx.calls, [])

    def test_unselected_source_changed_between_retries_stops_dispatch(self) -> None:
        run = self.handle()
        source = self.cohort.points["VNM-2023-01-06"]
        def respond(_):
            source.changed = True
            return httpx.Response(503, json={"error": {"message": "Lỗi tạm fixture"}})
        self.fx.handler = respond
        with self.assertRaises(ValueError):
            run.run()
        self.assertEqual(len(self.fx.calls), 1)
        self.assertEqual(self.fx.evaluations, [])

    def test_authorization_changed_between_retries_stops_dispatch(self) -> None:
        run = self.handle()
        auth = lock_authorization(run.root, self.plan, {"technical_gates_sha256": "b" * 64, "readiness_sha256": "c" * 64})
        self.fx.pacer.amendment_sha256 = digest(auth)
        def respond(_):
            value = read_envelope(run.root / "authorization.json")
            value["readiness_sha256"] = "d" * 64
            save_envelope(run.root / "authorization.json", value)
            return httpx.Response(503, json={"error": {"message": "Lỗi tạm fixture"}})
        self.fx.handler = respond
        with self.assertRaises(ValueError):
            run.run()
        self.assertEqual(len(self.fx.calls), 1)

    def test_execution_code_changed_between_retries_stops_dispatch(self) -> None:
        run = self.handle()
        original = self.plan["code_sha256"]
        def code():
            return {**original, "core/unified_bayes_cohort.py": "0" * 64} if self.fx.calls else original
        self.fx.handler = lambda _: httpx.Response(503, json={"error": {"message": "Lỗi tạm fixture"}})
        with patch("core.unified_bayes_cohort.code_identity", side_effect=code), self.assertRaises(ValueError):
            run.run()
        self.assertEqual(len(self.fx.calls), 1)

    def test_validation_code_changed_after_gate_cannot_publish_receipt(self) -> None:
        expected = self.diagnostic()
        identity = expected["validation_code_sha256"]
        changed = []
        def code():
            return {**identity, "tests/poison.py": "0" * 64} if changed else identity
        def process(*args, **kwargs):
            changed.append(True)
            from types import SimpleNamespace
            kwargs["stdout"].write(b"fixture\n")
            return SimpleNamespace(returncode=0)
        root = self.fx.root / "changed"
        with patch("core.unified_bayes_validation.validation_identity", side_effect=code), \
             patch("core.unified_bayes_validation.subprocess.run", side_effect=process), self.assertRaises(ValueError):
            run_gates(self.plan, expected, root, notify=lambda _: None)
        self.assertEqual(list(root.rglob("technical_gates.json")), [])


if __name__ == "__main__":
    unittest.main()
