"""Chặn source/plan/report/ledger tự reseal và đường API ngoài gate U-BICL."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from core.historical_signals import digest
from core.research_cohort import read_envelope, save_envelope
from core.unified_bayes_cohort import CohortRun, offline_transport, preflight, lock_authorization
from core.unified_bayes_contracts import validate
from core.unified_bayes_reports import read_report
from core.unified_bayes_source import BoundCohort, prepare_plan
from unified_context_test_support import dense_inputs, make_context
from unified_execution_test_support import ExecutionFixture
from unified_cohort_test_support import make_cohort


class UnifiedCohortLeakageTests(unittest.TestCase):
    """Consumer luôn dựng lại nguồn thật, không nhận cờ PASS hoặc checksum tự khai."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = dense_inputs()
        cls.context = make_context(cls.inputs)

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.fx = ExecutionFixture(Path(temp.name), self.context, self.inputs)
        self.addCleanup(self.fx.close)
        self.cohort = make_cohort(self.fx)
        self.plan = self.cohort.plan(self.fx.llm)

    def run_handle(self, create=True):
        return CohortRun(self.cohort, self.plan, self.fx.llm, self.fx.root / "cohort", self.fx.pacer.path, create=create)

    def test_resealed_plan_packet_evidence_schedule_and_native_type_are_rejected(self) -> None:
        path = self.fx.root / "plan.json"
        for kind in ("packet", "evidence", "schedule", "type"):
            value = deepcopy(self.plan)
            first = next(iter(value["requests"].values()))
            if kind == "packet":
                first["packets"]["Original"]["body"]["model"] = "other"
            elif kind == "evidence":
                first["u_evidence"]["task_groups"] = {}
            elif kind == "schedule":
                value["schedule"][0]["order"] = list(reversed(value["schedule"][0]["order"]))
            else:
                value["schedule"][0]["repeat_id"] = 0.0
            save_envelope(path, value)
            with self.assertRaises(ValueError):
                self.cohort.read_plan(path, self.fx.llm)
            with self.assertRaises(ValueError):
                prepare_plan(self.cohort, path, self.fx.llm)
        self.assertEqual(self.fx.calls, [])

    def test_unselected_source_changed_blocks_all_http(self) -> None:
        run = self.run_handle()
        self.cohort.points["VNM-2023-01-06"].changed = True
        with self.assertRaises(ValueError):
            run.run()
        self.assertEqual(self.fx.calls, [])

    def test_code_or_manifest_changed_blocks_before_http(self) -> None:
        run = self.run_handle()
        path = run.root / "cohort.json"
        value = deepcopy(run.binding)
        value["plan_sha256"] = "b" * 64
        save_envelope(path, value)
        with self.assertRaises(ValueError):
            run.run()
        self.assertEqual(self.fx.calls, [])

    def test_evaluation_source_changed_during_projection_is_rejected(self) -> None:
        run = self.run_handle()
        run.run()
        point = self.cohort.points["FPT-2023-01-06"]
        original = point._adapter.execution_data
        def change(symbol):
            result = original(symbol)
            point.changed = True
            return result
        point._adapter.execution_data = change
        with self.assertRaises(ValueError):
            run.report()

    def test_fixture_handle_cannot_self_declare_real_development(self) -> None:
        with self.assertRaises(ValueError):
            BoundCohort(list(self.cohort.prepared.values()), self.cohort.points, self.cohort.upstream,
                self.cohort.source_check, {}, self.cohort.models, split="development_2023_exploratory")

    def test_report_resealed_repeat_into_primary_or_usage_counts_is_rejected(self) -> None:
        run = self.run_handle()
        expected = run.report()
        path = run.root / "report.json"
        for kind in ("repeat", "http", "numeric"):
            changed = deepcopy(expected)
            if kind == "repeat":
                changed["repeats"]["in_primary"] = True
            elif kind == "http":
                changed["telemetry"]["http_attempt_count"] = 999
            else:
                changed["points"][0]["branches"]["Numeric_only"]["decision"]["action"] = "LONG"
            save_envelope(path, changed)
            with self.assertRaises(ValueError):
                read_report(path, run.report())

    def test_report_cannot_read_target_before_all_llm_or_start_repeats_early(self) -> None:
        run = self.run_handle()
        with self.assertRaises(ValueError):
            run.run(repeats=True)
        run.report()
        self.assertEqual(self.fx.evaluations, [])
        self.assertEqual(self.fx.calls, [])

    def test_offline_transport_never_reserves_or_dispatches(self) -> None:
        transport = offline_transport(self.fx.root / "absent_ledger.json", self.fx.root / "readonly_cache")
        with httpx.Client(transport=transport) as client, self.assertRaises(AssertionError):
            client.post("https://api.groq.com/openai/v1/chat/completions", json={})
        self.assertFalse(transport.pacer.path.exists())
        self.assertFalse(transport.cache_root.exists())

    def test_source_change_blocks_preflight_before_http(self) -> None:
        self.cohort.points["VNM-2023-01-06"].changed = True
        with self.assertRaises(ValueError):
            preflight(self.cohort, self.plan, self.fx.llm, self.fx.root, execute=True)
        self.assertEqual(self.fx.calls, [])

    def test_schema_rejects_duplicate_keys_nonfinite_and_foreign_legacy_fields(self) -> None:
        from core.research_cohort import read_envelope
        path = self.fx.root / "bad.json"
        for raw in ('{"payload":{},"sha256":"a","sha256":"b"}', '{"payload":{"a":NaN},"sha256":"a"}'):
            path.write_text(raw, encoding="utf-8")
            with self.assertRaises(ValueError):
                read_envelope(path)
        from unified_execution_test_support import PAYLOAD
        with self.assertRaises(ValueError):
            validate({**PAYLOAD, "prior_use": {}}, "legacy_decision")

    def test_authorization_cannot_change_receipt_or_conflict_with_http_usage(self) -> None:
        run = self.run_handle()
        receipts = {"technical_gates_sha256": "a" * 64, "readiness_sha256": "b" * 64}
        auth = lock_authorization(run.root, self.plan, receipts)
        with self.assertRaises(ValueError):
            lock_authorization(run.root, self.plan, {**receipts, "readiness_sha256": "c" * 64})
        # Pacer fixture đã khóa amendment khác auth: phải chặn ngay trước HTTP.
        with self.assertRaises(ValueError):
            run.run()
        self.assertEqual(self.fx.calls, [])
        self.assertEqual(read_envelope(run.root / "authorization.json"), auth)

    def test_preflight_parsed_and_output_cannot_replace_raw_http(self) -> None:
        from core.research_cohort import read_envelope
        root = self.fx.root / "preflight_tamper"
        expected = preflight(self.cohort, self.plan, self.fx.llm, root, execute=True)
        changed = deepcopy(expected)
        changed["response"]["parsed"]["decision"] = "SHORT"
        changed["response"]["raw_message"]["data"]["content"] = json.dumps(changed["response"]["parsed"])
        save_envelope(root / "preflight.json", changed)
        with self.assertRaises(ValueError):
            preflight(self.cohort, self.plan, self.fx.llm, root)


if __name__ == "__main__":
    unittest.main()
