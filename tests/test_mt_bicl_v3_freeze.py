"""Kiểm lịch/template/schema SDK và projection quỹ v3, không nguồn thị trường/key thật."""

from __future__ import annotations

from copy import deepcopy
import unittest

import httpx

from core.mt_bicl_v2_api_preflight import wire_body as old_wire
from core.mt_bicl_v2_api_preflight import client as old_client
from core.mt_bicl_v2_teacher import BetaBernoulliTeacher
from core.mt_bicl_v3_context import prepare_variants
from core.mt_bicl_v3_contracts import wire_schema
from core.mt_bicl_v3_freeze import layout, templates
from core.mt_bicl_v3_preflight import controls, check_control_semantics, projected_seconds, feasibility
from core.mt_bicl_v3_wire import client, wire_body, schema_for_sdk, REPLY_NAME
from core.mt_bicl_v3_decision import canonical_request
from mt_bicl_v3_support import episode, protocol, shared


class FreezeTests(unittest.TestCase):
    """Serializer thật qua MockTransport không mạng; kiểm tên schema không đổi semantics."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = protocol()
        value = episode()
        cls.facts = value["v3"]["query_facts"]
        cls.point = {"facts": cls.facts, "shared": shared(cls.facts), "a_reference": {"prefix": "A fixture"},
                     "variants": prepare_variants(value, BetaBernoulliTeacher([1/16]*16), lambda _: .6)["branches"]}

    def test_locked804_order_repeat12_and_duplicate36(self) -> None:
        value = layout(self.protocol)
        self.assertEqual(len(value["blocks"]), 96)
        self.assertEqual(len(value["slots"]), 804)
        self.assertEqual(sum(s["branch_id"] == "Original_duplicate" for s in value["slots"]), 36)
        for b in value["blocks"]:
            self.assertEqual(b["order"][:3], ["Original", "A_reference", "Fact_Anchor"])
            self.assertEqual(b["point_id"], value["point_ids"][b["point_index"]])

    def test_serializer_original_matches_v2_and_anchored_has_name_only(self) -> None:
        def reject(request: httpx.Request) -> httpx.Response: raise AssertionError("Không network")
        with httpx.Client(transport=httpx.MockTransport(reject)) as http:
            decision = self.protocol["decision"]["config"]
            llm = client(decision, http, "offline-no-credential")
            original = canonical_request(self.point["shared"], self.protocol, branch_id="Original")
            self.assertEqual(wire_body(llm, original), old_wire(old_client(decision, http, "offline-no-credential"), original))
            request = canonical_request(self.point["shared"], self.protocol, branch_id="Fact_Anchor", packet=self.facts)
            response = wire_body(llm, request)["response_format"]["json_schema"]
            self.assertEqual(response["name"], REPLY_NAME)
            self.assertEqual({k: v for k, v in response["schema"].items() if k != "title"}, wire_schema()["$defs"]["reply"])
        with self.assertRaises(ValueError): schema_for_sdk({"type": "object", "properties": {}})

    def test_revision_templates_two_a0_unsupported_no_HTTP(self) -> None:
        value = templates(self.point, self.protocol)
        self.assertEqual(len(value["Full_utility_ICL"]), 2)
        self.assertIn("a0=LONG", value["Full_utility_ICL"][0]["messages"][0]["content"])
        self.assertIn("a0=CASH", value["Full_utility_ICL"][1]["messages"][0]["content"])
        changed = deepcopy(self.point)
        changed["variants"]["Full_utility_ICL"]["eligible"] = False
        self.assertEqual(templates(changed, self.protocol)["Full_utility_ICL"], [])

    def test_control_probes_no_cohort_or_market_point_two_schemas_lengths(self) -> None:
        manifest = {"request_bounds": {"fixture": {"branch": {"max_prompt_chars": 6100}}}}
        value = controls(manifest, {"protocol": self.protocol})
        self.assertEqual(len(value), 4)
        self.assertTrue(all(r["point_id"] == "API_PREFLIGHT_V3" for r in value))
        self.assertEqual(len(value[1]["messages"][0]["content"]), 6100)
        self.assertEqual(len(value[3]["messages"][0]["content"]), 6100)
        self.assertFalse(any(pid in r["messages"][0]["content"] for pid in self.protocol["development"]["point_ids"] for r in value))

    def test_projection_includes_61s_sliding_window_and_format_retry(self) -> None:
        self.assertEqual(projected_seconds([5000, 5000], 2.), 63.)
        self.assertEqual(projected_seconds([3000, 3000, 3000], 2.), 63.)
        self.assertEqual(projected_seconds([5000], 2., multiplier=2), 63.)
        for reserve in (0, 8001, True):
            with self.assertRaises(ValueError): projected_seconds([reserve], 2.)
        for latency in (float("nan"), -1.):
            with self.assertRaises(ValueError): projected_seconds([1000], latency)

    def test_no_live_control_cannot_be_claimed_feasible_release(self) -> None:
        manifest = {"layout": {"slots": [{"point_id": "fixture", "branch_id": "Original"}]},
                    "request_bounds": {"fixture": {"Original": {"reserved_tokens_upper": 3000}}}}
        value = feasibility(manifest, {"requests": []}, None, 64800.)
        self.assertEqual(value["status"], "AWAITING_LIVE_CONTROLS")
        self.assertEqual(value["conditional_confirmation"]["nominal_slots"], 1348)
        self.assertFalse(value["confirmation_allowed"])
        self.assertFalse(value["projection_is_guarantee"])


if __name__ == "__main__":
    unittest.main()
