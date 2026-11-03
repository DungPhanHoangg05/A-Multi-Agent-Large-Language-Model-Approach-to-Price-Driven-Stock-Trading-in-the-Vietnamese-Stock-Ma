"""Kiểm mẫu số, aggregation, transitions và đối soát frozen selection, không API."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import alpha_compare as alpha
from core.revision_alpha_selection import (
    aggregate, analyse_cutoff, check_release, correlation, group_statistics, locked_units, ratio,
    run_audit, transitions, verify_selected,
)
from core.revision_baselines import load_prices
from core.revision_common_study import read_json, write_json
from core.revision_sentiment_inventory import BANK, RUN

ROOT = Path(__file__).resolve().parents[1]


def fixture_point(identity: str, symbol: str, block: str, date: str, decision: int, selected: list[str]) -> dict:
    """Sáu candidates với top-five khai báo, dùng đếm độc lập không lấy outcomes thật."""
    order = selected + sorted(set("ABCDEF") - set(selected))
    candidates = [{"alpha_id": key, "rank": rank, "composite": float(7 - rank), "selected": key in selected,
                   "diagnostic_eligible": key != "B", "ic_sign": 1, "current_signal": 1,
                   "history_long_exposure_toggle_rate": .1, "history_state_change_rate": .2} for rank, key in enumerate(order, 1)]
    return {"unit": {"id": identity, "symbol": symbol, "fold": block, "date": date, "decision": decision},
            "selected_ids": selected, "candidates": candidates, "registered_count": 6, "diagnostic_eligible_count": 5,
            "volume": {"uses_real_volume_branch": True, "raw_volume_nonmissing": 600, "raw_volume_zero_count": 0,
                       "price_fields_missing_before_fill": 0}, "history": {"rows": 600}}


class AlphaSelectionTests(unittest.TestCase):
    """Các fixtures số học phân biệt candidates/eligible/slots/units và scope thời gian."""

    def setUp(self) -> None:
        self.a = fixture_point("a", "AAA", "b1", "2024-01-01", 600, list("ABCDE"))
        self.b = fixture_point("b", "AAA", "b1", "2024-01-10", 607, list("ABCDF"))

    def test_locked_units_deduplicate_variants_and_ignore_repeats(self) -> None:
        unit = self.a["unit"]
        queue = {"jobs": [{"phase": phase, "unit": unit} for phase in ("main", "main", "factorial", "upstream")]}
        self.assertEqual(locked_units(queue), [unit])
        broken = deepcopy(queue); broken["jobs"][1]["unit"] = {**unit, "decision": unit["decision"] + 1}
        with self.assertRaisesRegex(ValueError, "khác cutoff"): locked_units(broken)

    def test_turnover_overlap_and_jaccard_have_distinct_denominators(self) -> None:
        row = transitions([self.b, self.a])[0]
        self.assertEqual(row["top5_common_count"], 4)
        self.assertAlmostEqual(row["top5_overlap_fraction"], .8)
        self.assertAlmostEqual(row["top5_jaccard"], 2 / 3)
        self.assertAlmostEqual(row["basket_replacement_turnover"], .2)
        self.assertEqual(row["entered"], ["F"])
        self.assertEqual(row["exited"], ["E"])
        self.assertEqual((row["calendar_day_gap"], row["observed_bar_gap"]), (9, 7))

    def test_no_transition_crosses_symbols_and_scope_between_blocks_is_explicit(self) -> None:
        other = fixture_point("c", "BBB", "b2", "2024-01-02", 601, list("ABCDE"))
        changed = deepcopy(self.b); changed["unit"]["fold"] = "b2"
        rows = transitions([other, changed, self.a])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["scope"], "between_blocks")
        self.assertEqual(rows[0]["symbol"], "AAA")

    def test_invalid_universe_duplicate_date_and_duplicate_unit_fail(self) -> None:
        broken = deepcopy(self.b); broken["candidates"].pop()
        with self.assertRaisesRegex(ValueError, "universe"): transitions([self.a, broken])
        duplicate = deepcopy(self.b); duplicate["unit"]["date"] = self.a["unit"]["date"]
        with self.assertRaisesRegex(ValueError, "không tăng"): transitions([self.a, duplicate])
        with self.assertRaisesRegex(ValueError, "Trùng cutoff"): aggregate([self.a, self.a])

    def test_frequency_slots_and_eligible_denominators_preserve_ineligible_selection(self) -> None:
        stats = group_statistics([self.a, self.b]); rows = {r["alpha_id"]: r for r in stats["factors"]}
        self.assertEqual((stats["registered_opportunities"], stats["diagnostic_eligible_opportunities"], stats["selected_slots"]), (12, 10, 10))
        self.assertEqual(rows["A"]["selected_cutoff_frequency"], 1)
        self.assertEqual(rows["A"]["selected_slot_share"], .2)
        self.assertEqual(rows["E"]["selected_cutoff_frequency"], .5)
        self.assertEqual(rows["B"]["selected_ineligible_count"], 2)
        self.assertIsNone(rows["B"]["selected_given_eligible"])
        self.assertAlmostEqual(sum(r["selected_slot_share"] for r in stats["factors"]), 1.)

    def test_ic_zero_undefined_and_sign_flip_support_are_separate(self) -> None:
        self.b["candidates"][0]["ic_sign"] = -1
        for point in (self.a, self.b):
            next(r for r in point["candidates"] if r["alpha_id"] == "B")["ic_sign"] = None
            next(r for r in point["candidates"] if r["alpha_id"] == "C")["ic_sign"] = 0
        rows = {r["alpha_id"]: r for r in group_statistics([self.a, self.b])["factors"]}
        self.assertEqual(rows["A"]["adjacent_nonzero_ic_flip_rate"], 1)
        self.assertEqual(rows["A"]["ic_nonzero_majority_share"], .5)
        self.assertEqual(rows["B"]["ic_undefined"], 2)
        self.assertEqual(rows["C"]["ic_zero"], 2)
        self.assertIsNone(rows["C"]["adjacent_nonzero_ic_flip_rate"])

    def test_rank_correlation_handles_ties_constants_and_missing(self) -> None:
        self.assertAlmostEqual(correlation([1, 1, 3], [2, 2, 6], ranked=True), 1)
        self.assertIsNone(correlation([1, 1], [2, 3], ranked=True))
        self.assertIsNone(correlation([np.nan, 1], [2, 3], ranked=True))
        self.assertIsNone(ratio(0, 0))

    def test_macro_symbols_does_not_reweight_bhn_like_large_support_symbols(self) -> None:
        other_a = fixture_point("c", "BBB", "b1", "2024-01-01", 600, list("ABCDE"))
        other_b = fixture_point("d", "BBB", "b1", "2024-01-10", 607, list("ABCDE"))
        other_c = fixture_point("e", "BBB", "b2", "2024-04-01", 664, list("ABCDE"))
        stats = aggregate([self.a, self.b, other_a, other_b, other_c])
        self.assertAlmostEqual(stats["pooled"]["mean_basket_replacement_turnover"], .2 / 3)
        self.assertAlmostEqual(stats["macro_unweighted_symbols"]["basket_replacement_turnover"], .1)
        self.assertEqual(stats["groups"]["symbol_block:AAA:b1"]["cutoffs"], 2)

    def test_proxy_and_missingness_are_counted_per_history_not_unique_sessions(self) -> None:
        self.b["volume"].update(uses_real_volume_branch=False, raw_volume_nonmissing=240, raw_volume_zero_count=20)
        stats = group_statistics([self.a, self.b])
        self.assertEqual(stats["proxy_volume_cutoffs"], 1)
        self.assertEqual(stats["raw_volume_missing_observations"], 360)
        self.assertEqual(stats["raw_volume_observation_opportunities"], 1200)
        self.assertEqual(stats["raw_volume_zero_observations"], 20)

    def test_existing_output_outside_scope_and_hash_tamper_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / "outputs/revision/fixture"; output.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "Release đã có"): run_audit(root, output)
            with self.assertRaisesRegex(ValueError, "release riêng"): run_audit(root, root / "paper")
            from core.revision_audit import sha256_file
            write_json(output / "summary.json", {"result": "fixture"})
            write_json(output / "manifest.json", {"sources": [], "outputs": [{"path": "summary.json", "sha256": sha256_file(output / "summary.json")}]})
            self.assertEqual(check_release(root, output), 1)
            (output / "summary.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Hash sai"): check_release(root, output)


class NativeSelectionReplayTests(unittest.TestCase):
    """Một cutoff frozen thật xác nhận đầy đủ 85 rows/top-five, không model/LLM."""

    @classmethod
    def setUpClass(cls) -> None:
        """Đọc đúng snapshot local và tạo kết quả một lần cho đối soát/tamper."""
        queue = read_json(ROOT / RUN / "manifest.json"); cls.unit = locked_units(queue)[0]
        bank = read_json(ROOT / BANK / "manifest.json"); cls.protocol = bank["protocol"]
        frames, _ = load_prices(ROOT / cls.protocol["price_snapshot"], cls.protocol["price_quality_policy"])
        cls.frame = frames[cls.unit["symbol"]]
        cls.asset = read_json(ROOT / BANK / f"features/{cls.unit['symbol']}_{cls.unit['decision']}.json")
        cls.point = analyse_cutoff(cls.frame, cls.unit, cls.protocol)

    def test_all_candidates_and_frozen_values_metrics_order_match(self) -> None:
        verify_selected(self.point, self.asset)
        self.assertEqual(self.point["registered_count"], 85)
        self.assertEqual(len(self.point["candidates"]), 85)
        self.assertTrue(all(row["native_n"] == 597 for row in self.point["candidates"]))
        self.assertEqual(self.point["history"]["native_warmup_rows_excluded"], 0)

    def test_frozen_metadata_or_value_tamper_fails(self) -> None:
        for changed in ("name", "value", "ic"):
            asset = deepcopy(self.asset)
            if changed == "name": asset["alpha_factors"][0]["name"] += " changed"
            if changed == "value": asset["alpha_factors"][0]["value"] += .1
            if changed == "ic": asset["alpha_factors"][0]["components"]["ic"] += .1
            with self.subTest(field=changed), self.assertRaises(ValueError): verify_selected(self.point, asset)

    def test_constant_ic_is_undefined_even_when_native_replaces_with_zero(self) -> None:
        def constant(data: pd.DataFrame) -> pd.Series:
            """Factor tổng hợp constant để kiểm undefined denominator, không tạo research prediction."""
            return pd.Series(1., index=data.index)
        with patch.dict(alpha.ALPHA_REGISTRY, {"CURRENT_1_FDM": (constant, "fixture")}):
            point = analyse_cutoff(self.frame, self.unit, self.protocol)
        row = next(r for r in point["candidates"] if r["alpha_id"] == "CURRENT_1_FDM")
        self.assertEqual(row["native_ic"], 0.)
        self.assertIsNone(row["ic_unrounded"])
        self.assertFalse(row["diagnostic_eligible"])
        self.assertEqual(point["native_ranking_count"], 85)

    def test_handler_error_is_reported_and_kept_in_native_denominator(self) -> None:
        def broken(_: pd.DataFrame) -> pd.Series:
            """Lỗi cố ý để chứng minh n=0 không bị giấu khỏi registry hoặc eligibility."""
            raise ValueError("fixture error")
        with patch.dict(alpha.ALPHA_REGISTRY, {"CURRENT_1_FDM": (broken, "fixture")}):
            point = analyse_cutoff(self.frame, self.unit, self.protocol)
        row = next(r for r in point["candidates"] if r["alpha_id"] == "CURRENT_1_FDM")
        self.assertEqual(row["native_n"], 0)
        self.assertIn("fixture error", row["handler_error"])
        self.assertFalse(row["diagnostic_eligible"])
        self.assertIsNone(row["history_long_exposure_toggle_rate"])
        self.assertEqual(point["native_ranking_count"], 85)


if __name__ == "__main__":
    unittest.main()
