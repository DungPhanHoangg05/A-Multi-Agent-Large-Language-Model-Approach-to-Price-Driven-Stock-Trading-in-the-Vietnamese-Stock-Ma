"""Chặn nhãn query/future/Decision, ranking theo nhãn và context tự reseal."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.unified_bayes_context import load_backbone_choice, select_demonstrations
from unified_context_test_support import dense_inputs, features, fixture_rows, make_context, query, reseal


class UnifiedContextLeakageTests(unittest.TestCase):
    """Giữ nguồn giả lập ở biên cold; toàn bộ PIT/ranking/renderer chạy production."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = dense_inputs()
        cls.context = make_context(cls.inputs)
        cls.features = features(cls.inputs)
        cls.evidence = cls.context.evidence(**query(), query_features=cls.features)

    def test_self_equal_exit_and_future_outcome_are_not_copied_or_read(self) -> None:
        class Poison(dict):
            """Đọc/copy record future làm ca kiểm thất bại ngay."""
            def __deepcopy__(self, memo: dict) -> dict:
                raise AssertionError("Đã đọc nhãn query/future")
        context = make_context(self.inputs)
        expected = context.evidence(**query(), query_features=self.features)
        for key, row in list(context.memory._records.items()):
            if row["symbol"] == "FPT" and row["exit_date"] >= query()["as_of_date"]:
                context.memory._records[key] = Poison(row)
        self.assertEqual(context.evidence(**query(), query_features=self.features), expected)
        self.assertNotIn("FPT:2023-01-03", sum(expected["selection"]["groups"].values(), []))

    def test_future_memory_append_preserves_old_membership_rank_and_posteriors(self) -> None:
        inputs = deepcopy(self.inputs)
        inputs["imported"] = [row for row in inputs["imported"] if row["as_of_date"] < "2024-01-01"]
        context = make_context(inputs)
        smaller = context.evidence(**query(), query_features=self.features)
        for key in ("selection", "task_groups", "examples", "posterior", "calendar"):
            self.assertEqual(smaller[key], self.evidence[key])

    def test_label_shuffle_changes_summary_oracle_but_not_ranking_or_mode(self) -> None:
        fixture = json.loads((Path(__file__).resolve().parents[1] /
            "docs/plan/week10/fixtures/unified_bic_contract_v1.json").read_text("utf-8"))
        results = []
        for case in fixture["task_selection_cases"][:2]:
            result = select_demonstrations(fixture_rows(case["records"]), population=20, symbol="FPT", regime="BULL")
            results.append(result)
            labels = {row["episode_id"]: row["net_return_pct"] for row in case["records"]}
            for block, counts in case["expected_selected_task_counts"].items():
                ids = result["groups"][f"FPT|BULL|b{int(block):04d}"]
                self.assertEqual((len(ids), sum(labels[key] > 0 for key in ids)), (counts["n"], counts["s"]))
        self.assertEqual(results[0], results[1])

    def test_declared_future_or_wrong_regime_pool_raises_before_selection(self) -> None:
        context = self.context
        original = context.memory.eligible
        future = context.memory._records["FPT:2024-12-26"]
        def corrupt(symbol: str, cutoff: str, **kwargs: str) -> list[dict]:
            return [deepcopy(future)] if kwargs else original(symbol, cutoff)
        with patch.object(context.memory, "eligible", side_effect=corrupt), self.assertRaises(ValueError):
            context.evidence(**query(), query_features=self.features)

    def test_nested_query_label_and_decision_contamination_raise(self) -> None:
        for key in ("outcome", "evaluation", "net_return_pct", "label", "confidence", "decision"):
            f = deepcopy(self.features)
            f["source_provenance"] = {"nested": {key: .9}}
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.context.evidence(**query(), query_features=f)

    def test_resealed_membership_score_alias_posterior_or_mode_fails_source_verifier(self) -> None:
        first = self.evidence["examples"][0]
        for kind in ("membership", "score", "example", "posterior", "mode"):
            e = deepcopy(self.evidence)
            if kind == "membership":
                e["task_groups"][first["task_id"]]["episode_ids"].append("future")
            elif kind == "score":
                e["selection"]["trace"][0]["rank_score"] = 1.
            elif kind == "example":
                e["examples"][0]["net_return_pct"] = 999.
            elif kind == "posterior":
                e["posterior"]["posterior_mean"] = .99
            else:
                e["context_mode"] = "episode_fallback"
            reseal(e)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.context.render(e, "U_full", self.features)

    def test_hot_context_and_renderer_have_no_file_io_fit_or_target_generation(self) -> None:
        with patch("pathlib.Path.read_bytes", side_effect=AssertionError("I/O")), \
             patch("pathlib.Path.read_text", side_effect=AssertionError("I/O")), \
             patch("core.price_feature_index._fit", side_effect=AssertionError("fit")), \
             patch("core.pit_price_features.extract_pit_price_features", side_effect=AssertionError("feature")), \
             patch("core.historical_outcomes.HistoricalOutcomeGenerator.generate", side_effect=AssertionError("target")):
            self.assertEqual(self.context.evidence(**query(), query_features=self.features), self.evidence)
            self.context.render(self.evidence, "U_full", self.features)

    def test_changed_query_feature_provenance_or_future_coverage_is_rejected(self) -> None:
        f = deepcopy(self.features)
        f["coverage"]["end_date"] = "2025-01-02"
        with self.assertRaises(ValueError):
            self.context.evidence(**query(), query_features=f)
        with self.assertRaises(ValueError):
            self.context.render(self.evidence, "U_full", {**self.features, "vector": [0., 0., 0., 0.]})

    def test_cold_loader_rejects_resealed_choice_before_trusting_status(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "backbone_choice_v1.json").write_text('{"status":"LOCKED","lambda":8}', encoding="utf-8")
            with patch("scripts.prepare_unified_bayes_pooling.NAMESPACE", path), self.assertRaises(ValueError):
                load_backbone_choice(self.context.memory)


if __name__ == "__main__":
    unittest.main()
