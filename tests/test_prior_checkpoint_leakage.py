"""Checkpoint băm lại vẫn phải qua PIT, replay retrieval/prompt và kinh tế thật."""

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from core.bayesian_memory import atomic_write_json
from core.prior_backtest import canonical_hash
from core.prior_checkpoint import CheckpointSession
import test_prior_checkpoint as support


class PriorCheckpointLeakageTests(unittest.TestCase):
    setUp = support.PriorCheckpointTests.setUp
    run_fixture = support.PriorCheckpointTests.run_fixture
    read_payload = support.PriorCheckpointTests.read_payload
    fresh_engine = support.PriorCheckpointTests.fresh_engine
    point_file = support.PriorCheckpointTests.point_file
    load_point = support.PriorCheckpointTests.load_point
    crash_at = support.PriorCheckpointTests.crash_at

    def tamper_and_reject(self, mutate) -> None:
        """Băm lại toàn envelope; checker phải chặn semantic sai trước LLM."""
        path = self.point_file()
        original = path.read_bytes()
        payload = json.loads(original)["payload"]
        mutate(payload)
        atomic_write_json(path, {"payload": payload, "sha256": canonical_hash(payload)})
        modified = path.read_bytes()
        before = self.llm.calls
        self.fresh_engine()
        with self.assertRaises(ValueError):
            self.run_fixture(cutoffs=(self.fx.cutoff,), resume=True)
        self.assertEqual(self.llm.calls, before)
        self.assertEqual(path.read_bytes(), modified)
        path.write_bytes(original)  # Phục hồi duy nhất fixture đã tự sửa.

    def test_forged_source_projection_snapshot_and_nested_query_outcomes_rejected(self) -> None:
        self.run_fixture(cutoffs=(self.fx.cutoff,))
        def future_source(doc):
            doc["source_proof"]["prices"]["snapshot_end_date"] = self.fx.day(645)
            doc["source_sha256"] = canonical_hash(doc["source_proof"])
        def future_projection(doc):
            doc["agent_projection"]["snapshot_ref"]["end_date"] = self.fx.day(645)
        def outcome(doc):
            bundle = doc["shared"]["full_bundle"]
            bundle["sentiment_data"]["tech_vars"]["outcome"] = {"actual_direction": "UP"}
            doc["shared"]["shared_sha256"] = canonical_hash(bundle)
        for mutate in (future_source, future_projection, outcome):
            with self.subTest(mutate=mutate.__name__):
                self.tamper_and_reject(mutate)

    def test_future_prior_equal_exit_boundary_metadata_scores_stats_and_prefix_rejected(self) -> None:
        self.run_fixture(cutoffs=(self.fx.cutoff,))
        def future(doc):
            doc["branches"]["random"]["input"]["prior_tasks"][0] = deepcopy(self.fx.records[-1])
        def boundary(doc):
            doc["branches"]["random"]["input"]["prior_tasks"][0]["exit_date"] = self.fx.cutoff
        def metadata(doc):
            doc["branches"]["recent"]["input"]["prior_metadata"]["selected_ids"].reverse()
        def scores(doc):
            doc["branches"]["similarity"]["input"]["prior_metadata"]["selected_scores"][0] = 0.123
        def stats(doc):
            doc["branches"]["bayesian"]["input"]["prior_stats"]["eligible_count"] = 999
        def prefix(doc):
            doc["branches"]["bayesian"]["input"]["bayesian_prior_context"] += " sai"
        for mutate in (future, boundary, metadata, scores, stats, prefix):
            with self.subTest(mutate=mutate.__name__):
                self.tamper_and_reject(mutate)

    def test_prompt_query_hash_config_mapping_and_recalculated_prompt_hash_refused(self) -> None:
        self.run_fixture(cutoffs=(self.fx.cutoff,))
        def prompt(doc):
            import hashlib
            value = doc["branches"]["original"]["input"]["prompt"]
            value["text"] += "\nPhần bị chèn sau khi gọi API."
            value["char_count"] = len(value["text"])
            value["sha256"] = hashlib.sha256(value["text"].encode()).hexdigest()
        def query(doc):
            doc["branches"]["random"]["input"]["query_sha256"] = "0" * 64
        def config(doc):
            doc["branches"]["random"]["input"]["prior_config"]["mode"] = "recent"
        def count(doc):
            doc["branches"]["random"]["input"]["prompt"]["char_count"] += 1
        for mutate in (prompt, query, config, count):
            with self.subTest(mutate=mutate.__name__):
                self.tamper_and_reject(mutate)

    def test_changed_decision_attempt_relations_and_evaluation_are_not_sealed_success(self) -> None:
        self.run_fixture(cutoffs=(self.fx.cutoff,))
        def decision(doc):
            value = doc["branches"]["original"]["decision"]
            decoded = json.loads(value["normalized_response"])
            decoded["decision"] = "SHORT"
            value["normalized_response"], value["action"] = json.dumps(decoded, ensure_ascii=False), "SHORT"
        def attempt(doc):
            doc["branches"]["random"]["attempts"][-1]["status"] = "running"
        def duplicate(doc):
            doc["branches"]["random"]["attempts"][-1]["attempt_id"] = doc["branches"]["original"]["attempts"][-1]["attempt_id"]
        def evaluation(doc):
            doc["evaluation"]["exit_close"] += 10
        for mutate in (decision, attempt, duplicate, evaluation):
            with self.subTest(mutate=mutate.__name__):
                self.tamper_and_reject(mutate)

    def test_resume_projection_does_not_supply_evaluation_to_any_decision(self) -> None:
        self.crash_at("branch_complete:random")
        original = self.builder.compile_report_decision
        seen = []
        def compile(**kwargs):
            callback = kwargs["before_decision"]
            def checked(state, prompt):
                self.assertTrue(set(state).isdisjoint({"evaluation", "outcome", "entry_open", "exit_close", "net_return_long"}))
                self.assertNotIn("point_in_time_df", state)
                self.assertNotIn("error", state)
                seen.append(state["prior_config"]["mode"])
                return callback(state, prompt)
            return original(**{**kwargs, "before_decision": checked})
        self.fresh_engine()
        with patch.object(self.builder, "compile_report_decision", side_effect=compile):
            self.run_fixture(cutoffs=(self.fx.cutoff,), resume=True)
        self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"])
        self.assertEqual(self.llm.calls, 5)
        self.assertEqual(len(seen), 5)  # Hai replay input offline và ba Decision còn thiếu.


if __name__ == "__main__":
    unittest.main()
