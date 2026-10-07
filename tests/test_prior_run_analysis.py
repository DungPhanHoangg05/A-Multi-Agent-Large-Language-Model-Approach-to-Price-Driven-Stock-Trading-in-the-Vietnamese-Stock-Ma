"""Kiểm audit offline: usage thiếu, ghép attempt, PIT và byte đóng băng."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.analyze_prior_run import (analyze_run, audit_points, canonical_hash,
                                      summarize_ledger, _reason_fingerprints)
from core.prior_checkpoint import safe_error
import test_prior_backtest_integration as support

TEXT = "openai/gpt-oss-20b"
VISION = "qwen/qwen3.8-27b"


def ledger_fixture() -> dict:
    """Ledger nhỏ có usage thật và unknown; không chứa prompt/key."""
    return {"version": 1, "limits": {TEXT: {}, VISION: {}}, "requests": [
        {"id": "preflight", "model": TEXT, "started_at": 1., "completed_at": 2.,
         "latency_seconds": 1., "status": 200, "reserved_tokens": 100,
         "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        {"id": "decision", "model": TEXT, "started_at": 11., "completed_at": 12.,
         "latency_seconds": 1., "status": 200, "reserved_tokens": 200,
         "prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        {"id": "unknown", "model": VISION, "started_at": 13.,
         "status": "transport_error", "reserved_tokens": 5535}],
        "preflight": {"request_ids": ["preflight"]}}


class LedgerAnalysisTests(unittest.TestCase):
    def analyze(self, ledger: dict, attempts: list | None = None) -> dict:
        """Cửa sổ Decision fixture chỉ bao phủ một request text."""
        return summarize_ledger(ledger, run_started_at=10., attempts=attempts if attempts is not None else [
            {"attempt_id": "a", "start": 10., "finish": 12.5}])

    def test_unknown_keeps_reserve_without_inventing_usage_or_latency(self) -> None:
        result = self.analyze(ledger_fixture())
        vision = result["models"][VISION]
        self.assertEqual((vision["actual_total_tokens"], vision["missing_usage_count"],
                          vision["held_reserve_tokens"], vision["charged_tokens"]), (0, 1, 5535, 5535))
        self.assertIsNone(vision["http_latency_seconds"]["sum"])
        self.assertEqual(vision["missing_latency_count"], 1)
        self.assertIsNone(result["pacing_seconds"])
        self.assertIsNone(result["format_retry_count"])
        self.assertEqual(result["decision_http_attempts"], 1)

    def test_zero_actual_is_measured_but_charged_matches_guard_v1(self) -> None:
        ledger = ledger_fixture()
        ledger["requests"][1].update(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        text = self.analyze(ledger)["models"][TEXT]
        self.assertEqual(text["actual_usage_count"], 2)
        self.assertEqual(text["actual_total_tokens"], 15)
        self.assertEqual(text["charged_tokens"], 215)

    def test_http_200_without_usage_is_not_free(self) -> None:
        ledger = ledger_fixture()
        row = ledger["requests"][1]
        for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
            del row[field]
        text = self.analyze(ledger)["models"][TEXT]
        self.assertEqual(text["http_200"], 2)
        self.assertEqual(text["missing_usage_count"], 1)
        self.assertEqual(text["charged_tokens"], 215)

    def test_old_pre_run_requests_are_not_guessed_as_preflight(self) -> None:
        ledger = ledger_fixture()
        ledger["preflight"]["request_ids"] = []
        result = self.analyze(ledger)
        self.assertEqual(result["request_phases"]["before_run_unclassified"], 1)
        self.assertNotIn("known_preflight", result["request_phases"])

    def test_overlapping_attempts_and_conflicting_preflight_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "nhiều attempt"):
            self.analyze(ledger_fixture(), [{"attempt_id": name, "start": 10., "finish": 12.5} for name in ("a", "b")])
        ledger = ledger_fixture()
        ledger["preflight"]["request_ids"].append("decision")
        with self.assertRaisesRegex(ValueError, "Preflight"):
            self.analyze(ledger)

    def test_corrupt_counts_ids_status_and_times_are_rejected(self) -> None:
        mutations = [("prompt_tokens", True), ("total_tokens", 31), ("started_at", float("nan")),
                     ("completed_at", 9.), ("reserved_tokens", 0), ("status", "secret-not-for-output")]
        for field, value in mutations:
            with self.subTest(field=field):
                ledger = ledger_fixture()
                ledger["requests"][1][field] = value
                with self.assertRaises(ValueError):
                    self.analyze(ledger)
        ledger = ledger_fixture()
        ledger["requests"][1]["id"] = "preflight"
        with self.assertRaises(ValueError):
            self.analyze(ledger)

    def test_empty_ledger_has_no_invented_timing(self) -> None:
        ledger = ledger_fixture()
        ledger["requests"], ledger["preflight"]["request_ids"] = [], []
        result = self.analyze(ledger)
        self.assertIsNone(result["ledger_wall_span_seconds"])
        self.assertEqual(result["decision_attempts_without_http"], 1)


class PriorRunAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        """Sinh checkpoint bằng runner thật một lần, không phụ thuộc pilot local."""
        fixture = support.PriorBacktestIntegrationTests()
        try:
            fixture.setUp()
            # Kho fixture gốc chỉ có record cùng regime chưa đóng tại query;
            # thêm bằng chứng đã đóng để kiểm tuổi/score/cutoff trên đường thật.
            for record in fixture.fx.records[:3]:
                record["regime"] = fixture.fx.regime["regime_name"]
            fixture.fx.publish_bank("a" * 64)
            fixture.adapter = fixture.fx.adapter()
            fixture.run_fixture()
            cls.files = {path.relative_to(fixture.output).as_posix(): path.read_bytes()
                         for path in fixture.output.rglob("*.json") if path.name not in (
                             "run.owner.json", "run.recovery.json")}
        finally:
            fixture.doCleanups()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative, content in self.files.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.ledger_path = self.root / "ledger.json"
        self.ledger_path.write_text(json.dumps({"version": 1, "limits": {TEXT: {}, VISION: {}}, "requests": []}), encoding="utf-8")
        self.points = [json.loads((self.root / name).read_text(encoding="utf-8"))["payload"]
                       for name in sorted(self.files) if name.startswith("points/")]

    def test_analysis_does_not_write_or_call_network_or_read_env(self) -> None:
        snapshot = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob("*.json")}
        with patch("socket.socket.connect", side_effect=AssertionError("Cấm mạng")), patch(
                "dotenv.dotenv_values", side_effect=AssertionError("Cấm đọc key")):
            result = analyze_run(self.root, self.ledger_path)
        self.assertEqual(result["paired_audit"]["point_count"], 2)
        self.assertEqual(result["paired_audit"]["decision_attempt_statuses"], {"complete": 10})
        self.assertEqual(result["telemetry"]["decision_attempts_without_http"], 10)
        self.assertEqual(snapshot, {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob("*.json")})
        json.dumps(result, allow_nan=False)

    def test_actual_checkpoint_tamper_and_partial_run_are_rejected(self) -> None:
        path = self.root / "points" / f"{self.points[0]['point_id']}.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "Byte checkpoint"):
            analyze_run(self.root, self.ledger_path)
        path.write_bytes(self.files[path.relative_to(self.root).as_posix()])
        result_path = self.root / "results.json"
        doc = json.loads(result_path.read_text(encoding="utf-8"))
        doc["payload"]["completed_point_ids"] = doc["payload"]["completed_point_ids"][:1]
        doc["payload"]["status"] = "partial"
        doc["sha256"] = canonical_hash(doc["payload"])
        result_path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Run còn dở"):
            analyze_run(self.root, self.ledger_path)

    def test_paired_shared_hash_and_economic_labels_are_checked(self) -> None:
        for field in ("shared", "return", "label", "correct"):
            points = deepcopy(self.points)
            point = points[0]
            if field == "shared":
                point["branches"]["bayesian"]["input"]["shared_sha256"] = "a" * 64
            elif field == "return":
                point["evaluation"]["net_return_long"] += .01
            elif field == "label":
                point["evaluation"]["actual_direction"] = "DOWN" if point["evaluation"]["actual_direction"] == "UP" else "UP"
            else:
                row = point["evaluation"]["branches"]["original"]
                row["correct"] = not row["correct"]
            with self.subTest(field=field), self.assertRaises(ValueError):
                audit_points(points)

    def test_trace_disagreement_uses_engine_and_keeps_all_points(self) -> None:
        points = deepcopy(self.points)
        point = points[0]
        branch = point["branches"]["bayesian"]
        action = "SHORT" if branch["decision"]["action"] == "LONG" else "LONG"
        branch["decision"]["action"] = action
        outcome = point["evaluation"]
        outcome["branches"]["bayesian"].update(cycle_net_return=outcome["net_return_long"] if action == "LONG" else 0.,
                                                correct=(action == "LONG") == (outcome["actual_direction"] == "UP"))
        result = audit_points(points)
        self.assertEqual((result["point_count"], result["disagreement_count"]), (2, 1))
        self.assertTrue(result["rows"][0]["disagrees"])
        self.assertIsNone(result["timing"]["retrieval_seconds"])
        self.assertGreater(result["rows"][0]["selected_priors"][0]["exit_age_calendar_days"], 0)

    def test_prior_exit_equal_to_query_is_rejected(self) -> None:
        points = deepcopy(self.points)
        points[0]["branches"]["bayesian"]["input"]["prior_tasks"][0]["exit_date"] = points[0]["context"]["as_of_date"]
        with self.assertRaisesRegex(ValueError, "Prior vi phạm"):
            audit_points(points)

    def test_reasons_are_fingerprinted_without_exporting_free_text(self) -> None:
        reason = {"evidence_for": "Nội dung chỉ ở checkpoint", "justification": "gsk_key_khong_duoc_in"}
        result = _reason_fingerprints({"normalized_response": json.dumps(reason)})
        self.assertEqual(result["status"], "available")
        self.assertNotIn("gsk_key", json.dumps(result))
        self.assertEqual(result["fields"]["justification"]["sha256"], hashlib.sha256(reason["justification"].encode()).hexdigest())

    def test_credential_file_and_path_escape_are_rejected(self) -> None:
        env = self.root / ".env"
        env.write_text("Không được mở", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "credential"):
            analyze_run(self.root, env)
        result_path = self.root / "results.json"
        doc = json.loads(result_path.read_text(encoding="utf-8"))
        doc["payload"]["point_files"][0]["path"] = "../outside.json"
        doc["sha256"] = canonical_hash(doc["payload"])
        result_path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises((ValueError, FileNotFoundError)):
            analyze_run(self.root, self.ledger_path)

    def test_replay_keeps_unknown_reserve_and_allows_later_planned_to_complete(self) -> None:
        folder = self.root / "reconciliation"
        folder.mkdir()
        point = self.points[0]
        backup = deepcopy(point)
        backup["status"], backup["evaluation"] = "failed", None
        backup["error"] = safe_error(ValueError("AMBIGUOUS_UPSTREAM"))
        backup["shared"] = {"stage": "upstream_started", "upstream_reports": None,
                            "full_bundle": None, "shared_sha256": None}
        for branch in backup["branches"].values():
            branch.update(status="planned", input=None, attempts=[], decision=None, error=None)
        backup_path = folder / f"{point['point_id']}.before-replay.json"
        backup_path.write_text(json.dumps({"payload": backup, "sha256": canonical_hash(backup)}), encoding="utf-8")
        proof = {"run_signature": point["run_signature"], "point_id": point["point_id"],
            "action": "USER_AUTHORIZED_REPLAY_OF_UNKNOWN_UPSTREAM_ONCE", "status": "APPLIED",
            "previous_point_backup": backup_path.name,
            "previous_point_file_sha256": hashlib.sha256(backup_path.read_bytes()).hexdigest(),
            "previous_payload_sha256": canonical_hash(backup),
            "unknown_http_request_record_id": "unknown", "unknown_request_reserve_kept": 5535,
            # Điểm sau replay từng planned: hash cũ khác hash complete hiện tại là hợp lệ.
            "other_point_file_sha256": {f"{self.points[1]['point_id']}.json": "a" * 64},
            "completion": {"status": "VERIFIED_COMPLETE", "old_complete_points_byte_unchanged": 0,
                "result_file_sha256": hashlib.sha256((self.root / "results.json").read_bytes()).hexdigest(),
                "point_file_sha256": hashlib.sha256((self.root / "points" / f"{point['point_id']}.json").read_bytes()).hexdigest()}}
        (folder / f"{point['point_id']}.json").write_text(json.dumps({"payload": proof, "sha256": canonical_hash(proof)}), encoding="utf-8")
        ledger = ledger_fixture()
        self.ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
        result = analyze_run(self.root, self.ledger_path, reconciliation_dir=folder)
        self.assertEqual(result["graph_evidence"]["authorized_upstream_replays"], 1)
        self.assertEqual(result["telemetry"]["models"][VISION]["held_reserve_tokens"], 5535)
        ledger["requests"][-1]["reserved_tokens"] = 1
        self.ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Reserve unknown"):
            analyze_run(self.root, self.ledger_path, reconciliation_dir=folder)


if __name__ == "__main__":
    unittest.main()
