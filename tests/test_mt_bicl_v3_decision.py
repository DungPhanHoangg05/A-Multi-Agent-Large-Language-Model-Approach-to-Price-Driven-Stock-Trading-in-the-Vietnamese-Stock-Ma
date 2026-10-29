"""Kiểm facts/anchor/raw-final, ablation, renderer và lỗi transport bằng LLM giả."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from core.mt_bicl_bank import canonical_bytes, content_hash
from core.mt_bicl_v2_decision import canonical_request as legacy_request
from core.mt_bicl_v2_teacher import BetaBernoulliTeacher
from core.mt_bicl_v3_context import prepare_variants
from core.mt_bicl_v3_contracts import validate_wire, wire_schema
from core.mt_bicl_v3_decision import build_anchored_prompt, canonical_request, fact_card, invoke_revision, revision_plan
from core.mt_bicl_v3_policy import apply_revision, facts_match, resolve_anchor, utility_only
from mt_bicl_v3_support import UUID, episode, original, packet, protocol, reply, shared, unsupported


class DecisionTests(unittest.TestCase):
    """Chỉ fake responses; không dùng key, HTTP, cache v2 hoặc upstream thật."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.episode = episode()
        cls.facts = cls.episode["v3"]["query_facts"]
        cls.prepared = prepare_variants(cls.episode, BetaBernoulliTeacher([1/16]*16), lambda e: .6 if e["m"] else .3)

    def anchor(self, a0: str = "LONG", *, invalid: bool = False) -> dict:
        """Nguồn gốc Original/Fact_Anchor có hash riêng và response độc lập."""
        raw = reply(self.facts, a0, anchor=True)
        if invalid: raw["fact_assertions"]["MACD_ZERO"] = "NEGATIVE"
        return resolve_anchor(self.facts, original("LONG"), raw, original_source_sha256="1"*64,
                              anchor_source_sha256="2"*64, request_id=UUID)

    def test_facts_enum_and_citations_exact_not_free_prose_claim(self) -> None:
        value = reply(self.facts)
        self.assertTrue(facts_match(value, self.facts))
        value["justification"] = "Văn xuôi chưa được validator ngữ nghĩa chứng minh."
        self.assertTrue(facts_match(value, self.facts))
        value["fact_assertions"]["MACD_SIGNAL"] = "BELOW"
        self.assertFalse(facts_match(value, self.facts))
        for ids in (["MACD_ZERO"]*3, ["MACD_SIGNAL", "PRICE_SMA20"], ["MACD_SIGNAL", "PRICE_SMA20", "HIDDEN"]):
            value["fact_ids"] = ids
            with self.assertRaises(ValueError): facts_match(value, self.facts)

    def test_locked_policy_fixtures_strict_zero_both_directions(self) -> None:
        fixtures = json.loads(Path("docs/plan/week11/protocol_fixtures_v3.json").read_text(encoding="utf-8"))
        for case in fixtures["policy_cases"]:
            anchor = self.anchor("LONG" if case["anchor"] == "LONG" else "SHORT")
            branch = deepcopy(self.prepared["branches"]["Full_utility_ICL"])
            branch["utility"].update(q10_U_net_fraction=case["q10_U"], q90_U_net_fraction=case["q90_U"])
            if not case["supported"]: branch = unsupported(branch, "MAGNITUDE_SUPPORT_BELOW_FIVE_PER_SIGN")
            response = reply(self.facts, "LONG" if case["proposed"] == "LONG" else "SHORT")
            if not case["facts"]: response["fact_assertions"]["MACD_SIGNAL"] = "BELOW"
            result = apply_revision(self.facts, anchor, branch, reply=response if case["supported"] else None,
                                    request_id=UUID if case["supported"] else None)
            self.assertEqual(result["final_action"], case["final"])
            validate_wire(result, "policy")

    def test_bad_anchor_bypasses_all_revisions_to_original_with_source_proof(self) -> None:
        anchor = self.anchor("SHORT", invalid=True)
        self.assertEqual(anchor["policy"]["final_action"], "LONG")
        self.assertEqual(anchor["policy"]["reason"], "ANCHOR_INVALID_USE_ORIGINAL")
        self.assertEqual(anchor["proof"]["anchor_source_sha256"], "2"*64)
        for name in ("Plain_revision", "Full_utility_ICL", "No_utility", "No_target", "Stats_only"):
            result = apply_revision(self.facts, anchor, self.prepared["branches"][name])
            self.assertEqual((result["final_action"], result["reason"], result["bypass"], result["request_id"]), ("LONG", "ANCHOR_INVALID_USE_ORIGINAL", True, None))

    def test_nonpositive_rejection_keeps_raw_and_final_actions_separate(self) -> None:
        branch = deepcopy(self.prepared["branches"]["Full_utility_ICL"])
        branch["utility"].update(q10_U_net_fraction=-.02, q90_U_net_fraction=.01)
        value = apply_revision(self.facts, self.anchor(), branch, reply=reply(self.facts, "SHORT"), request_id=UUID)
        self.assertEqual((value["raw_proposed_action"], value["anchor_action"], value["final_action"]), ("SHORT", "LONG", "LONG"))
        self.assertEqual(value["q10_delta_U_net_fraction"], -.01)
        self.assertEqual(value["reason"], "REJECT_NONPOSITIVE_Q10_DELTA_U")

    def test_plain_and_no_utility_allow_change_without_U_or_veto(self) -> None:
        for name in ("Plain_revision", "No_utility"):
            result = apply_revision(self.facts, self.anchor(), self.prepared["branches"][name], reply=reply(self.facts, "SHORT"), request_id=UUID)
            self.assertEqual((result["final_action"], result["reason"], result["q10_delta_U_net_fraction"]), ("CASH", "NO_NUMERIC_VETO", None))

    def test_same_proposed_kept_bad_facts_rejected_and_context_reason_checked(self) -> None:
        branch = self.prepared["branches"]["Full_utility_ICL"]
        value = apply_revision(self.facts, self.anchor(), branch, reply=reply(self.facts), request_id=UUID)
        self.assertEqual(value["reason"], "KEEP_PROPOSED_SAME")
        response = reply(self.facts, "SHORT")
        response["context_reason"] = "NOT_APPLICABLE"
        value = apply_revision(self.facts, self.anchor(), branch, reply=response, request_id=UUID)
        self.assertEqual((value["reason"], value["final_action"]), ("REJECT_FACT_ASSERTIONS", "LONG"))

    def test_missing_response_api_error_is_not_bypass_cash_or_fallback(self) -> None:
        branch = self.prepared["branches"]["Full_utility_ICL"]
        with self.assertRaisesRegex(ValueError, "Thiếu response"):
            apply_revision(self.facts, self.anchor(), branch)
        request = canonical_request(shared(self.facts), protocol(), branch_id="Fact_Anchor", packet=self.facts)
        llm = Mock()
        with patch("core.mt_bicl_v3_decision._invoke_with_retry", side_effect=RuntimeError("HTTP429/unknown")) as invoked:
            with self.assertRaisesRegex(RuntimeError, "HTTP429/unknown"):
                invoke_revision(llm, request, attempt_id=UUID, run_signature="3"*64, branch_id="Fact_Anchor")
        self.assertEqual(invoked.call_count, 1)

    def test_unsupported_keeps_anchor_not_default_cash_no_fake_request(self) -> None:
        branch = unsupported(self.prepared["branches"]["Full_utility_ICL"], "UNKNOWN_BUCKET")
        result = apply_revision(self.facts, self.anchor(), branch)
        self.assertEqual((result["final_action"], result["reason"], result["request_id"]), ("LONG", "BYPASS_UNKNOWN_BUCKET", None))
        with self.assertRaises(ValueError):
            apply_revision(self.facts, self.anchor(), branch, reply=reply(self.facts), request_id=UUID)

    def test_anchor_tamper_utility_wrong_membership_and_nonfinite_raise(self) -> None:
        anchor = self.anchor()
        anchor["policy"]["final_action"] = "CASH"
        with self.assertRaises(ValueError): apply_revision(self.facts, anchor, self.prepared["branches"]["Full_utility_ICL"])
        for mode in ("membership", "nan", "order", "support_mask"):
            branch = deepcopy(self.prepared["branches"]["Full_utility_ICL"])
            if mode == "membership": branch["utility"]["membership_sha256"] = "f"*64
            if mode == "nan": branch["utility"]["q90_U_net_fraction"] = float("nan")
            if mode == "order": branch["utility"].update(q10_U_net_fraction=1., q90_U_net_fraction=-1.)
            if mode == "support_mask": branch.update(eligible=False, reason="PRIOR_TASKS_BELOW_TWO", projection=None)
            for decision in ("LONG", "SHORT"):
                with self.subTest(mode=mode, decision=decision), self.assertRaises(ValueError):
                    apply_revision(self.facts, self.anchor(), branch, reply=reply(self.facts, decision), request_id=UUID)

    def test_utility_only_strict_positive_rule_and_native_JSON(self) -> None:
        branch = deepcopy(self.prepared["branches"]["Utility_only"])
        for q10, expected in ((-.01, "CASH"), (0., "CASH"), (1e-15, "LONG")):
            branch["utility"]["q10_U_net_fraction"] = q10
            value = utility_only(self.facts, branch)
            self.assertEqual(value["final_action"], expected)
            canonical_bytes(value)

    def test_original_A_body_schema_options_unchanged_and_input_not_mutated(self) -> None:
        reports, spec = shared(self.facts), protocol()
        before = content_hash(reports)
        for name, prefix in (("Original", ""), ("A_reference", "A fixture"), ("Original_duplicate", "")):
            new = canonical_request(reports, spec, branch_id=name, prefix=prefix, repeat=1)
            old = legacy_request(reports, prefix, {"decision": spec["decision"]["config"]}, 1)
            self.assertEqual(new, old)
        self.assertEqual(before, content_hash(reports))

    def test_fact_anchor_no_context_and_revisions_only_appropriate_inputs(self) -> None:
        reports = shared(self.facts)
        anchored = build_anchored_prompt(reports, self.facts, branch_id="Fact_Anchor")
        self.assertNotIn("MT3", anchored)
        self.assertNotIn("a0=", anchored)
        self.assertNotIn("p=P", anchored)
        for name, branch in self.prepared["branches"].items():
            if name == "Utility_only": continue
            prompt = build_anchored_prompt(reports, self.facts, branch_id=name, projection=branch["projection"], anchor=self.anchor())
            self.assertIn("a0=LONG", prompt)
            self.assertLess(len(prompt), 6500)
            self.assertEqual("U(mean" in prompt, name not in ("Plain_revision", "No_utility"))
        with self.assertRaises(ValueError):
            build_anchored_prompt(reports, self.facts, branch_id="Fact_Anchor", projection=self.prepared["branches"]["Full_utility_ICL"]["projection"])

    def test_long_reports_keep_distill_cap_and_prompt_overflow_fail_before_invoke(self) -> None:
        reports = shared(self.facts, "Nội dung tổng hợp. "*500)
        request = canonical_request(reports, protocol(), branch_id="Full_utility_ICL", packet=self.facts,
                                    projection=self.prepared["branches"]["Full_utility_ICL"]["projection"], anchor=self.anchor())
        self.assertLess(len(request["messages"][0]["content"]), 6500)
        self.assertEqual(request["structured"]["schema"], wire_schema()["$defs"]["reply"])
        too_long = deepcopy(self.facts)
        too_long["reported_warnings"] = ["x"*160]*5
        with self.assertRaisesRegex(ValueError, "fact card"):
            fact_card(too_long)
        with patch("core.mt_bicl_v3_decision.FACT_INSTRUCTION", "x"*6500), self.assertRaises(ValueError):
            build_anchored_prompt(shared(self.facts), self.facts, branch_id="Fact_Anchor")

    def test_wrapper_format_attempts_only_and_semantic_mismatch_not_retried(self) -> None:
        request = canonical_request(shared(self.facts), protocol(), branch_id="Fact_Anchor", packet=self.facts)
        response = reply(self.facts, anchor=True)
        response["fact_assertions"]["MACD_SIGNAL"] = "BELOW"
        llm = Mock()
        with patch("core.mt_bicl_v3_decision._invoke_with_retry", return_value={"parsed": response, "parsing_error": None}) as invoked:
            value = invoke_revision(llm, request, attempt_id=UUID, run_signature="3"*64, branch_id="Fact_Anchor")
        self.assertEqual(invoked.call_count, 1)
        self.assertEqual(value, response)
        with patch("core.mt_bicl_v3_decision._invoke_with_retry", return_value={"parsed": None}) as invoked:
            with self.assertRaises(ValueError):
                invoke_revision(llm, request, attempt_id=UUID, run_signature="3"*64, branch_id="Fact_Anchor")
        self.assertEqual(invoked.call_count, 2)

    def test_revision_plan_keeps_all_bypass_slots_without_HTTP_and_deepcopies_shared(self) -> None:
        reports = shared(self.facts)
        before = content_hash(reports)
        prepared = deepcopy(self.prepared)
        prepared["branches"] = {name: unsupported(branch) for name, branch in prepared["branches"].items()}
        with patch("core.mt_bicl_v3_decision.invoke_revision", side_effect=AssertionError("Không được HTTP")):
            plan = revision_plan(reports, self.facts, self.anchor(), prepared, protocol())
        self.assertEqual(len(plan), 5)
        self.assertTrue(all(slot["request"] is None and slot["bypass_policy"]["final_action"] == "LONG" for slot in plan.values()))
        self.assertEqual(content_hash(reports), before)
        plan = revision_plan(reports, self.facts, self.anchor(), self.prepared, protocol())
        plan["Full_utility_ICL"]["request"]["messages"][0]["content"] = "changed"
        self.assertNotEqual(plan["Stats_only"]["request"]["messages"][0]["content"], "changed")


if __name__ == "__main__":
    unittest.main()
