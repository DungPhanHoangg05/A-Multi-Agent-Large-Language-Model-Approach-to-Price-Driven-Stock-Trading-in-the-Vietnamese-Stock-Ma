"""Kiểm lịch/repeat trước action và SDK/pacer/journal offline của preflight W11."""

from __future__ import annotations

from copy import deepcopy
from contextlib import nullcontext
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_adapter import VARIANTS
from core.mt_bicl_v2_api_preflight import (
    LIVE_VERSION, RECEIPT_PATH, RECEIPT_VERSION, client, dry_run, live_preflight, manifest_facts, offline_wire_preflight,
    verify, verify_live_preflight, wire_body,
)
from core.mt_bicl_v2_decision import canonical_request
from core.mt_bicl_v2_io import write_envelope
from core.mt_bicl_v2_release import RELEASE_PATH
from core.mt_bicl_v2_integration import OfflineDecisionFixture
from core.mt_bicl_v2_io import read_envelope
from core.mt_bicl_v2_run_manifest import (
    CODE, MANIFEST_PATH, MANIFEST_VERSION, OUTPUT, branch_order, repeat_selection, schedule,
)
from core.mt_bicl_v21_preparation import file_hash
from core.prior_context import REPORT_FIELDS


def fixture() -> dict:
    """Cohort thật và context giả không nhãn; không dùng artifact hoặc key production."""
    protocol = json.loads(Path("docs/plan/week10/protocol_v2.json").read_text(encoding="utf-8"))
    rows = []
    for symbol, dates in protocol["development"]["symbol_cutoffs"].items():
        for j, date in enumerate(dates):
            rows.append({"query": {"symbol": symbol, "as_of_date": date, "episode_id": symbol+"-"+date},
                         "K": 3, "m": (0, 2, 8)[j % 3], "status": "AVAILABLE"})
    layout = schedule(rows, protocol["development"], protocol["decision"]["symbol_order"])
    shared = {r["query"]["episode_id"]: {"stock_name": r["query"]["symbol"], "as_of_date": r["query"]["as_of_date"],
              "time_frame": "1d", "is_backtest": True, "language": "vi", **{k: "Báo cáo fixture trung tính." for k in REPORT_FIELDS}} for r in rows}
    variants = {pid: {v: {"prefix": "" if v in ("Original", "A_reference") else "K=3;m=2;p=0.500"} for v in VARIANTS} for pid in shared}
    requests = {}
    for block in layout["blocks"]:
        pid, repeat = block["point_id"], block["repeat_index"]
        for name in block["order"]:
            base = "Original" if name == "Original_duplicate" else name
            requests[(pid, repeat, name)] = canonical_request(shared[pid], variants[pid][base]["prefix"], protocol, repeat)
    return {"inputs": {"protocol": protocol, "rows": rows}, "release": {"decision": protocol["decision"],
             "runtime": {}, "candidate": {"seed": 42, "step": 3000}, "integration_identity_sha256": "fixture"},
            "layout": layout, "shared": shared, "variants": variants, "requests": requests, "upstream": {"fixture": True}}


class ScheduleTests(unittest.TestCase):
    """Các điểm chưa có outcome vẫn chọn đủ cohort/repeat và xoay đúng quy tắc."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = fixture()

    def test_exact360_primary252_repeat_and_original_first(self) -> None:
        layout = self.data["layout"]
        self.assertEqual(sum(s["repeat_index"] == 0 for s in layout["slots"]), 360)
        self.assertEqual(sum(s["repeat_index"] > 0 for s in layout["slots"]), 252)
        self.assertEqual(len({r["point_id"] for r in layout["repeat_selection"]}), 12)
        for b in layout["blocks"]:
            self.assertEqual(b["order"][0], "Original")
            self.assertEqual(set(b["order"]), {*VARIANTS, *(["Original_duplicate"] if b["repeat_index"] else [])})

    def test_known_rotation_uses_global_j_for_repeat(self) -> None:
        self.assertEqual(branch_order(1), ["Original", "Plain_ICL", "Full_MT_BICL", "No_target", "Stats_only", "A_reference"])
        self.assertEqual(branch_order(5, 2), ["Original", "Stats_only", "Original_duplicate", "A_reference", "Plain_ICL", "Full_MT_BICL", "No_target"])
        self.assertEqual(branch_order(2, 1)[1:], [*VARIANTS[1:], "Original_duplicate"])

    def test_invalid_indices_fail(self) -> None:
        for j, r in ((-1, 0), (True, 0), (0, 4), (0, True)):
            with self.subTest(j=j, r=r), self.assertRaises(ValueError):
                branch_order(j, r)

    def test_order_independent_input_and_no_query_outcomes_needed(self) -> None:
        data = self.data
        actual = schedule(list(reversed(data["inputs"]["rows"])), data["inputs"]["protocol"]["development"], data["inputs"]["protocol"]["decision"]["symbol_order"])
        self.assertEqual(actual, data["layout"])

    def test_missing_stratum_fallback_does_not_steal_existing_first_date(self) -> None:
        rows = [{"query": {"symbol": "FPT", "as_of_date": f"2023-01-{j+1:02d}", "episode_id": f"FPT-{j}"}, "m": m}
                for j, m in enumerate((2, 8, 2, 8))]
        selected = repeat_selection(rows, ["FPT"])
        self.assertEqual([r["point_id"] for r in selected], ["FPT-2", "FPT-0", "FPT-1"])
        self.assertEqual(selected[0]["reason"], "MISSING_STRATUM_FIRST_UNSELECTED_DATE")

    def test_all_strata_missing_except_high_fills_earliest_unused(self) -> None:
        rows = [{"query": {"symbol": "FPT", "as_of_date": f"2023-01-{j+1:02d}", "episode_id": f"FPT-{j}"}, "m": 8} for j in range(3)]
        self.assertEqual([r["point_id"] for r in repeat_selection(rows, ["FPT"])], ["FPT-1", "FPT-2", "FPT-0"])

    def test_cohort_missing_duplicate_and_2025_rejected(self) -> None:
        original = self.data["inputs"]["rows"]
        for mode in ("missing", "duplicate", "2025"):
            rows = deepcopy(original)
            if mode == "missing": rows.pop()
            if mode == "duplicate": rows[-1] = deepcopy(rows[0])
            if mode == "2025": rows[0]["query"]["as_of_date"] = "2025-01-01"
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                schedule(rows, self.data["inputs"]["protocol"]["development"], self.data["inputs"]["protocol"]["decision"]["symbol_order"])

    def test_support_gate_checks_each_symbol_before_requests(self) -> None:
        rows = deepcopy(self.data["inputs"]["rows"])
        for row in rows:
            if row["query"]["symbol"] == "FPT": row["K"] = 0
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_CONTEXT"):
            schedule(rows, self.data["inputs"]["protocol"]["development"], self.data["inputs"]["protocol"]["decision"]["symbol_order"])

    def test_unavailable_point_retained_even_if_context_off(self) -> None:
        rows = deepcopy(self.data["inputs"]["rows"])
        rows[0].update(status="UNAVAILABLE", K=0, m=0)
        result = schedule(rows, self.data["inputs"]["protocol"]["development"], self.data["inputs"]["protocol"]["decision"]["symbol_order"])
        self.assertIn(rows[0]["query"]["episode_id"], result["point_ids"])
        self.assertEqual(len(result["slots"]), 612)


class PreflightTests(unittest.TestCase):
    """Serializer và transport thật qua mock HTTP, checkpoint durable giữ duplicate độc lập."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = fixture()

    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        release = self.root/RELEASE_PATH
        release.parent.mkdir(parents=True)
        release.write_text("{}", encoding="utf-8")
        for n in CODE:
            p = self.root/n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("fixture", encoding="utf-8")

    def test_serializer_preserves_schema_model_options_no_seed_or_sdk_retry(self) -> None:
        with httpx.Client(transport=httpx.MockTransport(lambda r: self.fail("Không được HTTP"))) as http:
            llm = client(self.data["release"]["decision"], http, "fixture-no-key")
            body = wire_body(llm, next(iter(self.data["requests"].values())))
        self.assertEqual(body["model"], "openai/gpt-oss-20b")
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertEqual(body["service_tier"], "on_demand")
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertNotIn("seed", body)

    def test_seven_mock_requests_use_retry_pacer_and_audit_without_network(self) -> None:
        result = offline_wire_preflight(self.data)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["mock_http_calls"], 7)
        self.assertEqual(result["real_api_calls"], 0)
        self.assertEqual(result["requests"][-1]["branch_id"], "Original_duplicate")

    def test_all612_durable_replay_and36_duplicates_not_shared_off(self) -> None:
        before = deepcopy(self.data["shared"])
        first = dry_run(self.root, self.data)
        self.assertEqual(first, dry_run(self.root, self.data))
        self.assertEqual(first["slots"], 612)
        self.assertEqual(first["duplicate_invocations"], 36)
        self.assertEqual(first["shared_off"], 96)
        self.assertEqual(len(first["journals_sha256"]), 96)
        self.assertEqual(self.data["shared"], before)

    def test_wire_body_repeats_identical_but_canonical_repeat_distinct(self) -> None:
        facts = manifest_facts(self.root, self.data)
        first = facts["requests"][0]
        repeat = next(s for s in facts["requests"] if s["point_id"] == first["point_id"] and s["branch_id"] == "Original" and s["repeat_index"] == 1)
        self.assertNotEqual(first["canonical_sha256"], repeat["canonical_sha256"])
        self.assertEqual(first["http_contract"], repeat["http_contract"])
        duplicate = next(s for s in facts["requests"] if s["point_id"] == first["point_id"] and s["branch_id"] == "Original_duplicate" and s["repeat_index"] == 1)
        self.assertFalse(duplicate["shared_off_eligible"])

    def test_tokenizer_missing_fails_without_network(self) -> None:
        with patch("core.mt_bicl_v2_api_preflight.tokenizer_cached", return_value=False), self.assertRaisesRegex(ValueError, "tokenizer"):
            manifest_facts(self.root, self.data)

    def test_no_live_receipt_is_not_API_pass(self) -> None:
        with self.assertRaises(OSError):
            verify_live_preflight(self.root, {"offline": "PASS"})

    def mock_live(self) -> tuple[dict, list]:
        """Đường live thật với inner HTTP giả; lock/credential fixture không chạm máy production."""
        from core.improvement_recovery import ResilientTransport
        calls = []
        manifest = {"decision": self.data["release"]["decision"], "fixture": True}
        def respond(request: httpx.Request) -> httpx.Response:
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "fixture", "object": "chat.completion", "created": 0,
                "model": "openai/gpt-oss-20b", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(OfflineDecisionFixture().invoke("")["parsed"], ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})
        self.addCleanup(patch.stopall)
        patch("core.mt_bicl_v2_api_preflight.verify", return_value=(manifest, {})).start()
        patch("core.prior_run_lock.PriorRunLock", side_effect=lambda *a, **k: nullcontext()).start()
        patch("dotenv.dotenv_values", return_value={"GROQ_API_KEY": "fixture-no-real-key"}).start()
        patch("core.improvement_recovery.ResilientTransport", side_effect=lambda p, c: ResilientTransport(p, c, httpx.MockTransport(respond))).start()
        return manifest, calls

    def test_user_live_preflight_binds_durable_raw_and_idempotent_no_second_http(self) -> None:
        manifest, calls = self.mock_live()
        saved = live_preflight(self.root, self.root/"absent.env")
        self.assertEqual(saved["status"], "PASS")
        self.assertEqual(len(calls), 1)
        self.assertEqual(verify_live_preflight(self.root, manifest), saved)
        self.assertEqual(live_preflight(self.root, self.root/"absent.env"), saved)
        self.assertEqual(len(calls), 1)

    def test_live_unknown_never_automatically_replayed(self) -> None:
        manifest, calls = self.mock_live()
        path = self.root/OUTPUT/"live_api_preflight.json"
        write_envelope(path, LIVE_VERSION, {"manifest_sha256": content_hash(manifest), "status": "unknown"})
        with self.assertRaisesRegex(ValueError, "unknown"):
            live_preflight(self.root, self.root/"absent.env")
        self.assertEqual(calls, [])

    def test_live_receipt_decision_cannot_diverge_from_raw_http(self) -> None:
        manifest, _ = self.mock_live()
        saved = live_preflight(self.root, self.root/"absent.env")
        saved["decision"]["decision"] = "LONG"
        write_envelope(self.root/OUTPUT/"live_api_preflight.json", LIVE_VERSION, saved)
        with self.assertRaisesRegex(ValueError, "raw response"):
            verify_live_preflight(self.root, manifest)

    def test_cold_verifier_rejects_missing_evidence_before_recreation(self) -> None:
        facts = manifest_facts(self.root, self.data)
        manifest = {**facts, "source_commit": "fixture"}
        dry = dry_run(self.root, self.data)
        receipt = {"manifest_payload_sha256": content_hash(manifest), "source_sha256": facts["source_sha256"],
                   "status": "OFFLINE_PASS_AWAITING_USER_LIVE_API_PREFLIGHT", "real_api_calls": 0,
                   "live_api_preflight": "NOT_RUN_USER_EXECUTES_BEFORE_PRIMARY", "dry_run": dry,
                   "wire_preflight": offline_wire_preflight(self.data)}
        write_envelope(self.root/MANIFEST_PATH, MANIFEST_VERSION, manifest)
        write_envelope(self.root/RECEIPT_PATH, RECEIPT_VERSION, receipt)
        path = self.root/OUTPUT/next(iter(dry["journals_sha256"]))
        path.unlink()
        with patch("core.mt_bicl_v2_api_preflight.collect", return_value=self.data), patch("core.mt_bicl_v2_api_preflight.git_value"), self.assertRaises(OSError):
            verify(self.root, require_anchor=False)
        self.assertFalse(path.exists())

    def test_self_resealed_order_rejected_from_source_rebuild(self) -> None:
        facts = manifest_facts(self.root, self.data)
        manifest = {**facts, "source_commit": "fixture"}
        manifest["layout"] = deepcopy(manifest["layout"])
        manifest["layout"]["slots"][0]["branch_id"] = "Full_MT_BICL"
        write_envelope(self.root/MANIFEST_PATH, MANIFEST_VERSION, manifest)
        write_envelope(self.root/RECEIPT_PATH, RECEIPT_VERSION, {})
        with patch("core.mt_bicl_v2_api_preflight.collect", return_value=self.data), self.assertRaisesRegex(ValueError, "Manifest khác"):
            verify(self.root, require_anchor=False)


if __name__ == "__main__":
    unittest.main()
