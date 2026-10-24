"""Oracle task/fallback/ranking, projection và ngân sách prompt U-BICL."""

from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from core.unified_bayes_context import select_demonstrations, task_block
from core.unified_bayes_prompt import BRANCHES, assemble_prompt, check_budget, render_context
from unified_context_test_support import dense_inputs, features, fixture_rows, make_context, query, reseal


class UnifiedContextCliTests(unittest.TestCase):
    """Biên artifact phải phân biệt kiểu counts dù envelope đã tự reseal."""

    def test_prepare_resume_verify_and_resealed_integer_type_drift(self) -> None:
        from core.research_cohort import save_envelope
        from scripts import prepare_unified_bayes_context as cli
        expected = {"query_count": 60, "modes": {"off": 60}, "max_prefix_chars": 0,
                    "points": [{"evidence": {"task_groups": {"task": {"n": 42}}}}]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "renderer.json"
            with patch.object(cli, "OUTPUT", path), patch.object(cli, "build_contract", return_value=expected), patch("builtins.print"):
                def run(mode: str) -> None:
                    with patch.object(sys, "argv", ["context", mode]):
                        cli.main()
                run("--prepare")
                raw = path.read_bytes()
                run("--prepare")
                run("--verify-only")
                self.assertEqual(raw, path.read_bytes())
                changed = deepcopy(expected)
                changed["points"][0]["evidence"]["task_groups"]["task"]["n"] = 42.0
                save_envelope(path, changed)
                for mode in ("--verify-only", "--prepare"):
                    with self.subTest(mode=mode), self.assertRaises(ValueError):
                        run(mode)


class UnifiedTaskSelectionTests(unittest.TestCase):
    """Rule thuần không nhận nhãn; fixture khóa trước implementation là oracle."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads((Path(__file__).resolve().parents[1] /
            "docs/plan/week10/fixtures/unified_bic_contract_v1.json").read_text("utf-8"))

    def select(self, rows: list[dict], population: int = 20) -> dict:
        """Chạy selector đúng mã/regime, không có seed hoặc tham số tune."""
        return select_demonstrations(rows, population=population, symbol="FPT", regime="BULL")

    def test_locked_task_blocks_and_all_selection_oracles(self) -> None:
        for case in self.fixture["task_block_cases"]:
            self.assertEqual(task_block(case["cutoff_session"]), case["expected_block"])
        for case in self.fixture["task_selection_cases"]:
            with self.subTest(case=case["case_id"]):
                result = self.select(fixture_rows(case["records"]), case["population"])
                self.assertEqual(result["selected_ids"], case["expected_ids"])
                self.assertEqual(result["context_mode"], case["expected_mode"])
                for block, ids in case.get("expected_membership", {}).items():
                    self.assertEqual(result["groups"][f"FPT|BULL|b{int(block):04d}"], sorted(ids))
                labels = {row["episode_id"]: row["net_return_pct"] for row in case["records"]}
                for block, counts in case.get("expected_selected_task_counts", {}).items():
                    ids = result["groups"][f"FPT|BULL|b{int(block):04d}"]
                    self.assertEqual((len(ids), sum(labels[key] > 0 for key in ids)), (counts["n"], counts["s"]))

    def test_conflicting_first_representative_tries_next_in_group(self) -> None:
        source = deepcopy(self.fixture["task_selection_cases"][0]["records"])
        next(row for row in source if row["episode_id"] == "b2").update(cutoff_session=100, entry_session=101, exit_session=103)
        result = self.select(fixture_rows(source))
        self.assertEqual(result["selected_ids"], ["a1", "c1", "b2"])
        self.assertEqual(len(result["groups"]["FPT|BULL|b0001"]), 2)

    def test_closed_interval_overlap_is_not_resolved_by_cutoff_gap_alone(self) -> None:
        rows = fixture_rows(self.fixture["task_selection_cases"][0]["records"])
        rows[0]["exit_session"] = 182
        result = self.select(rows)
        self.assertEqual(result["selected_ids"], ["a1"])

    def test_age_and_similarity_boundaries_keep_unscored_membership(self) -> None:
        rows = fixture_rows(self.fixture["task_selection_cases"][2]["records"])
        rows[0].update(age_days=730, base_score=.625)
        rows[1].update(age_days=731)
        result = self.select(rows)
        self.assertEqual(result["context_mode"], "episode_fallback")
        self.assertEqual(result["selected_ids"], ["a1"])
        self.assertNotIn("a2", sum(result["groups"].values(), []))
        rows[0]["base_score"] = .625 - 1e-12
        self.assertEqual(self.select(rows)["context_mode"], "off")

    def test_fallback_tie_uses_newest_exit_then_episode_id(self) -> None:
        rows = fixture_rows(self.fixture["task_selection_cases"][3]["records"])
        for row in rows:
            row["base_score"] = .9
        self.assertEqual(self.select(rows)["selected_ids"], ["f3", "f2"])

    def test_invalid_counts_non_native_duplicate_and_outcome_inputs_raise(self) -> None:
        row = fixture_rows(self.fixture["task_selection_cases"][2]["records"])[0]
        for changes in ({"net_return_pct": 1}, {"base_score": math.nan}, {"age_days": True},
                        {"cutoff_session": np.int64(1)}, {"age_days": 0}, {"entry_session": 88}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.select([{**row, **changes}])
        with self.assertRaises(ValueError):
            self.select([row, row])
        for value in (-1, True, np.int64(90)):
            with self.assertRaises(ValueError):
                task_block(value)


class UnifiedContextAndPromptTests(unittest.TestCase):
    """Chạy memory/index/stats thật trên giá tổng hợp và kiểm renderer ba task."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = dense_inputs()
        cls.fixture = json.loads((Path(__file__).resolve().parents[1] /
            "docs/plan/week10/fixtures/unified_bic_contract_v1.json").read_text("utf-8"))
        cls.context = make_context(cls.inputs)
        cls.features = features(cls.inputs)
        cls.evidence = cls.context.evidence(**query(), query_features=cls.features)

    def test_real_memory_path_has_three_tasks_and_full_summaries(self) -> None:
        e = self.evidence
        self.assertEqual(e["context_mode"], "task")
        self.assertEqual(len(e["examples"]), 3)
        self.assertTrue(e["posterior"]["gate"]["ready"])
        records = self.context.memory._records
        for group in e["task_groups"].values():
            self.assertEqual(group["n"], len(group["episode_ids"]))
            self.assertEqual(group["s"], sum(records[key]["outcome"]["net_return_pct"] > 0 for key in group["episode_ids"]))
        self.assertEqual(e["statistics"]["counts"]["nC"] + e["statistics"]["counts"]["n1"], len(e["selection"]["trace"]))

    def test_query_feature_missing_keeps_stats_and_membership_but_examples_off(self) -> None:
        f = deepcopy(self.features)
        f.update(status="UNAVAILABLE", reasons=["INSUFFICIENT_HISTORY"], vector=None)
        e = self.context.evidence(**query(), query_features=f)
        self.assertEqual(e["context_mode"], "off")
        self.assertEqual(e["task_groups"], self.evidence["task_groups"])
        self.assertEqual(e["posterior"], self.evidence["posterior"])
        self.assertTrue(render_context(e, "U_full")["prefix"])
        self.assertEqual(render_context(e, "U_examples")["prefix"], "")

    def test_all_visibility_combinations_match_locked_fixture(self) -> None:
        fixture = self.fixture
        for case in fixture["visibility_cases"]:
            e = deepcopy(self.evidence)
            e["posterior"]["gate"]["ready"] = case["stats_ready"]
            e["selection"]["gate"]["ready"] = bool(case["example_count"])
            if not case["example_count"]:
                e["examples"] = []
            reseal(e)
            for branch, expected_key in zip(BRANCHES, ("expected_full_visible", "expected_stats_visible", "expected_examples_visible")):
                view = render_context(e, branch)
                self.assertEqual(bool(view["prefix"]), case[expected_key])
                self.assertEqual(view["base_evidence_sha256"], e["base_evidence_sha256"])
                if branch == "U_stats":
                    self.assertEqual(view["aliases"], {})
                    self.assertIsNone(view["demonstrations"])
                    self.assertNotIn("context_mode", json.dumps(view))
                if branch == "U_examples":
                    self.assertIsNone(view["statistics"])
                    self.assertNotIn("CrI", view["prefix"])
                    self.assertNotIn("Beta", view["prefix"])

    def test_sidecar_aliases_map_uniquely_to_three_full_groups(self) -> None:
        view = self.context.render(self.evidence, "U_full", self.features)
        self.assertEqual(set(view["aliases"]), {"T1", "T2", "T3", "E1", "E2", "E3"})
        for i, row in enumerate(self.evidence["examples"], 1):
            self.assertEqual(view["aliases"][f"E{i}"]["episode_id"], row["episode_id"])
            self.assertEqual(view["aliases"][f"T{i}"]["episode_ids"], self.evidence["task_groups"][row["task_id"]]["episode_ids"])
        self.assertIn("T=task,E=cycle", view["prefix"])
        self.assertIn("s/n=", view["prefix"])
        self.assertIn("Open(t+1)→Close(t+3)", view["prefix"])
        self.assertIn("SHORT=CASH", view["prefix"])

    def test_episode_fallback_declares_mode_and_has_no_fake_task_summary(self) -> None:
        e = deepcopy(self.evidence)
        e["context_mode"] = "episode_fallback"
        reseal(e)
        view = render_context(e, "U_full")
        self.assertIn("mode=episode_fallback (không phải multi-task)", view["prefix"])
        self.assertEqual(set(view["aliases"]), {"E1", "E2", "E3"})
        self.assertNotIn("s/n=", view["prefix"])

    def test_longest_regime_three_tasks_large_counts_and_returns_fit_600(self) -> None:
        e = deepcopy(self.evidence)
        e["query"]["current_regime"] = "CONSOLIDATION"
        e["statistics"]["counts"].update(nC=333, sC=333, n1=333, n2=310)
        for example in e["examples"]:
            example["net_return_pct"] = -123456.789
            e["task_groups"][example["task_id"]].update(n=222, s=222)
        reseal(e)
        for branch in BRANCHES:
            view = render_context(e, branch)
            self.assertLessEqual(len(view["prefix"]), 600)
            self.assertEqual(view["prefix_chars"], len(view["prefix"]))
            self.assertTrue(view["prefix"].endswith("SHORT=CASH."))

    def test_unicode_budget_boundaries_and_atomic_insertion(self) -> None:
        for case in self.fixture["budget_cases"]:
            if case["expected_allowed"]:
                check_budget("Đ" * case["prefix_chars"], "Đ" * case["prompt_chars"])
            else:
                with self.assertRaises(ValueError):
                    check_budget("Đ" * case["prefix_chars"], "Đ" * case["prompt_chars"])
        prefix = render_context(self.evidence, "U_full")["prefix"]
        prompt = assemble_prompt("Hợp đồng\n### [1]\nBáo cáo", prefix)
        self.assertEqual(prompt.count(prefix), 1)
        self.assertEqual(assemble_prompt("Đ" * 6499, ""), "Đ" * 6499)
        with self.assertRaises(ValueError):
            assemble_prompt(prompt, prefix)
        with self.assertRaises(ValueError):
            assemble_prompt("Thiếu report", prefix)
        with self.assertRaises(ValueError):
            assemble_prompt("### [1]" + "Đ" * (6499 - 7), prefix)

    def test_saturated_reports_use_legacy_distill_caps_in_both_languages(self) -> None:
        import agents.decision_agent as decision
        prefix = render_context(self.evidence, "U_full")["prefix"]
        for lang in ("vi", "en"):
            reports = {key: decision._distill_report(key, "Đ" * 10000, lang, report_limits=decision._BACKTEST_REPORT_CHAR_LIMITS)
                       for key in ("trend", "pattern", "indicator", "alpha", "sentiment")}
            base = getattr(decision, f"_build_compact_prompt_{lang}")("FPT", "1d", 5, True, True,
                "Open(t+1)→Close(t+3)", "T+3", "Theo phiên; SHORT=CASH", **{key + "_report": value for key, value in reports.items()})
            for block in (prefix, prefix + " " * (600 - len(prefix))):
                result = assemble_prompt(base, block)
                self.assertLess(len(result), 6500)
                for report in reports.values():
                    self.assertIn(report, result)
                self.assertEqual(result.count(block), 1)


if __name__ == "__main__":
    unittest.main()
