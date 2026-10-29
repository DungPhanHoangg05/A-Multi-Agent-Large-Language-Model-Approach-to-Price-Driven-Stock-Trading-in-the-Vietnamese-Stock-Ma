"""Kiểm spec v3, schema, lịch/seed/budget và ledger; chưa kiểm implementation utility bước08."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v3_protocol import (
    DIRECTORY, PREFIX, PROTOCOL, PROTOCOL_SHA256, REVISIONS, branch_order, component_seed,
    validate_bundle, validate_document, verify_ledger,
)


class ProtocolTests(unittest.TestCase):
    """Các fixture độc lập không đọc price2025, không chạy torch/model, không gọi API."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = PROTOCOL.read_bytes()
        cls.spec = json.loads(cls.data)
        cls.artifacts = {n: Path(n).read_bytes() for n in cls.spec["artifacts_sha256"]}
        cls.schema = json.loads(cls.artifacts[(DIRECTORY/"utility_icl_v3.schema.json").as_posix()])
        cls.fixtures = json.loads(cls.artifacts[(DIRECTORY/"protocol_fixtures_v3.json").as_posix()])

    def test_exact_locked_bundle_and_no_API_or_training_release(self) -> None:
        spec = validate_bundle(self.data, self.artifacts)
        self.assertEqual(hashlib.sha256(self.data).hexdigest(), PROTOCOL_SHA256)
        for name in ("training_allowed", "teacher_fit_allowed", "development_allowed", "decision_calls_allowed", "confirmation_allowed"):
            self.assertIs(spec[name], False)
        self.assertEqual(spec["next_stage"], "W11_08_IMPLEMENTATION_ONLY_NO_API")

    def test_rehashed_relaxed_rule_budget_or_API_flag_cannot_self_seal(self) -> None:
        for key in ("policy", "budget_artifact", "development_allowed"):
            value = deepcopy(self.spec);value[key] = True
            changed = json.dumps(value, ensure_ascii=False).encode()
            with self.subTest(key=key), self.assertRaises(ValueError): validate_bundle(changed, self.artifacts)

    def test_missing_extra_or_changed_artifact_rejected(self) -> None:
        for mode in ("missing", "extra", "changed"):
            values = deepcopy(self.artifacts)
            if mode == "missing": values.pop(next(iter(values)))
            if mode == "extra": values["extra.json"] = b"{}"
            if mode == "changed": values[next(iter(values))] += b" "
            with self.subTest(mode=mode), self.assertRaises(ValueError): validate_bundle(self.data, values)

    def test_reset_budget18_hours_separate_from_legacy_and_shared_with_W12(self) -> None:
        budget = json.loads(self.artifacts[(DIRECTORY/"budget_v3.json").as_posix()])
        self.assertEqual((budget["cap_seconds"], budget["charged_seconds_at_reset"]), (64800, 0))
        self.assertFalse(budget["deduct_v1_v2_runtime"])
        self.assertEqual(budget["resume_and_W12"], "SAME_COUNTER_NO_RESET")
        self.assertIn("provider_quota_wait", budget["includes"])
        self.assertFalse(budget["new_API_quota_granted"])

    def test_primary_and_repeat_orders_preserve_global_index(self) -> None:
        self.assertEqual(branch_order(1), [*PREFIX, *REVISIONS[1:], REVISIONS[0]])
        self.assertEqual(branch_order(1, 1), [*PREFIX, "No_target", "Stats_only", "Original_duplicate", "Plain_revision", "Full_utility_ICL", "No_utility"])
        for j, r in ((True, 0), (-1, 0), (0, True), (0, 4)):
            with self.assertRaises(ValueError): branch_order(j, r)

    def test_12_repeat_points_lock_five_exposed_and_seven_hash_selected(self) -> None:
        spec = self.spec["development"]
        sample = spec["repeat_selection"]["point_ids"]
        changed = spec["repeat_selection"]["changed_v2_ids"]
        self.assertEqual(len(set(sample)), 12)
        self.assertTrue(set(changed) <= set(sample))
        ranked = sorted((p for p in spec["point_ids"] if p not in changed), key=lambda p: hashlib.sha256(("v3-repeat|"+p).encode()).hexdigest())
        self.assertEqual(set(sample)-set(changed), set(ranked[:7]))
        self.assertEqual(sample, self.fixtures["development_repeat_ids"])

    def test804_and1348_slots_include_independent_duplicate(self) -> None:
        selected = set(self.spec["development"]["repeat_selection"]["point_ids"])
        primary = sum(len(branch_order(j)) for j in range(60))
        repeated = sum(len(branch_order(j, r)) for r in (1, 2, 3)
                       for j, p in enumerate(self.spec["development"]["point_ids"]) if p in selected)
        self.assertEqual((primary, repeated, primary+repeated), (480, 324, 804))
        self.assertEqual(128*8+repeated, 1348)
        self.assertEqual(len(self.spec["confirmation"]["secondary"]), 7)
        self.assertEqual(self.spec["confirmation"]["bootstrap"]["secondary_ci"], 1-.05/7)

    def test_seed_fixture_reproducible_and_components_independent(self) -> None:
        seed = self.fixtures["seed"]
        actual = component_seed(seed["protocol_sha256"], seed["point_id"], "theta")
        self.assertEqual(actual, seed["uint128_decimal"])
        self.assertNotEqual(actual, component_seed(seed["protocol_sha256"], seed["point_id"], "lambda"))
        self.assertNotEqual(actual, component_seed("1"*64, seed["point_id"], "theta"))
        for point, component in (("FPT-2023-99-01", "theta"), ("../x", "theta"), (seed["point_id"], "branch_repeat_1")):
            with self.assertRaises(ValueError): component_seed("0"*64, point, component)

    def test_teacher_U_and_student_p_roles_and_ablation_are_separate(self) -> None:
        self.assertFalse(self.spec["learner"]["U_is_distilled_output"])
        self.assertFalse(self.spec["learner"]["reuse_v2_p_for_new_membership"])
        self.assertEqual(self.spec["learner"]["packing"], "PAIRED_37")
        self.assertIn("RECOMPUTE_P_TEACHER_U_AND_OWN_SUPPORT", self.spec["decision"]["No_target"])
        self.assertIn("NO_NUMERIC_VETO", self.spec["decision"]["Plain_revision"])
        self.assertEqual(self.spec["utility"]["support"], {"K_min": 2, "gain_min": 5, "loss_min": 5, "zero_net_in_loss": True})

    def facts(self) -> dict:
        """Packet tổng hợp minh họa MACD âm nhưng trên Signal, không là lời giải LLM."""
        return {"version": "utility_icl_facts_v3", "point_id": "VCB-2023-10-30", "as_of_date": "2023-10-30",
            "frame_end_date": "2023-10-30", "prefix_rows": 45,
            "numeric": {"macd": -.6521, "signal": -.7620, "macd_minus_signal": .1099, "close": 90., "sma20": 89., "close_minus_sma20": 1.},
            "bucket": "MACD_POS_PRICE_POS", "assertions": {"MACD_SIGNAL": "ABOVE", "MACD_ZERO": "NEGATIVE", "PRICE_SMA20": "ABOVE"},
            "horizon": "T+2.5", "reported_warnings": [], "source_sha256": {"prices": "a"*64}}

    def test_fact_schema_separates_below_zero_from_below_signal(self) -> None:
        value = self.facts();validate_document(value, self.schema)
        value["assertions"]["MACD_SIGNAL"] = "NEGATIVE"
        with self.assertRaises(ValueError): validate_document(value, self.schema)

    def test_schema_rejects_query_labels_nonfinite_and_unregistered_fields(self) -> None:
        for change in ("query_y", "nonfinite", "other"):
            value = self.facts()
            if change == "query_y": value["query_y"] = 1
            if change == "nonfinite": value["numeric"]["macd"] = float("nan")
            if change == "other": value["numeric"]["future_close"] = 100.
            with self.subTest(change=change), self.assertRaises(ValueError): validate_document(value, self.schema)

    def test_schema_rejects_external_reference_without_network(self) -> None:
        with self.assertRaises(ValueError): validate_document({}, {"$ref": "https://example.invalid/schema.json"})

    def test_reply_schema_requires_three_unique_citations_and_legacy_horizon(self) -> None:
        reply = {"version": "utility_icl_reply_v3", "decision": "LONG", "forecast_horizon": "T+2.5", "confidence": "Thấp",
            "risk_reward_ratio": 1., "evidence_for": "Fixture thuận.", "evidence_against": "Fixture nghịch.", "justification": "Fixture offline.",
            "fact_ids": ["MACD_SIGNAL", "MACD_ZERO", "PRICE_SMA20"], "fact_assertions": self.facts()["assertions"], "context_reason": "SUPPORTED"}
        validate_document(reply, self.schema)
        for ids in (["MACD_SIGNAL"]*3, ["MACD_SIGNAL", "MACD_ZERO"], ["MACD_SIGNAL", "MACD_ZERO", "unknown"]):
            changed = deepcopy(reply);changed["fact_ids"] = ids
            with self.assertRaises(ValueError): validate_document(changed, self.schema)

    def test_utility_schema_supported_draws_and_support_must_be_real(self) -> None:
        utility = {"version": "utility_icl_posterior_v3", "point_id": "FPT-2023-01-06", "branch_id": "Full_utility_ICL",
            "status": "SUPPORTED", "reason": "SUPPORTED", "source": "TEACHER_SIGN_BAYESIAN_BOOTSTRAP_MAGNITUDE",
            "probability_student": .4, "posterior_mean_theta": .4, "mean_U_net_fraction": .004, "MC_mean_U_net_fraction": .0041,
            "q10_U_net_fraction": .001, "q90_U_net_fraction": .01, "gain_count": 5, "loss_count": 5, "K": 2, "m": 0,
            "draws": 4096, "seed_uint128_decimal": "123", "membership_sha256": "a"*64, "draws_sha256": "b"*64}
        validate_document(utility, self.schema)
        for field, value in (("gain_count", 4), ("draws", 0), ("probability_student", 1.1), ("posterior_mean_theta", None)):
            changed = deepcopy(utility);changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): validate_document(changed, self.schema)
        unsupported = deepcopy(utility);unsupported.update(status="UTILITY_UNSUPPORTED", draws=0, draws_sha256=None)
        for field in ("posterior_mean_theta", "mean_U_net_fraction", "MC_mean_U_net_fraction", "q10_U_net_fraction", "q90_U_net_fraction"):
            unsupported[field] = None
        validate_document(unsupported, self.schema)

    def test_ledger_allows_append_but_not_reserve_mutation_reset_or_duplicate_ID(self) -> None:
        rows = [{"id": "old", "reserved_tokens": 100, "status": "unknown"}]
        baseline = {"count": 1, "requests_prefix_sha256": content_hash(rows)}
        verify_ledger({"requests": rows+[{"id": "new", "reserved_tokens": 200}]}, baseline)
        for changed in ([], [{**rows[0], "reserved_tokens": 0}], rows+rows):
            with self.assertRaises(ValueError): verify_ledger({"requests": changed}, baseline)


if __name__ == "__main__":
    unittest.main()
