"""Kiểm lịch dense, primitive feature, nhãn engine và lý do loại MT-BICL."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core.mt_bicl_bank import PROTOCOL_SHA256, SOURCE, SYMBOLS, build_dense_bank, canonical_bytes
from core.mt_bicl_scaler import fit_scaler, transform_features
from core.pit_price_features import extract_pit_price_features
from scripts.build_mt_bicl_bank import verify_records
from scripts.verify_mt_bicl_protocol import PROTOCOL_SHA256 as LOCKED_PROTOCOL
from mt_bicl_bank_support import bank, feature, prices, scaler_bank


class DenseBankTests(unittest.TestCase):
    """Kiểm số liệu độc lập với công thức vector hóa và giữ lịch khi bị loại."""

    def test_anchor_and_block_boundary_preserve_candidate_ids(self) -> None:
        frame, calendar = prices()
        result = bank(frame, calendar)
        rows = [row for row in result["records"] if row["symbol"] == "FPT"]
        self.assertEqual([row["calendar_index"] for row in rows], list(range(20, 97, 3)))
        blocked = next(row for row in rows if row["calendar_index"] == 62)
        self.assertEqual(blocked["reasons"], ["CROSS_BLOCK_HOLDING"])
        self.assertIsNone(blocked["outcome"])
        self.assertEqual(blocked["block_end_calendar_index"], 62)
        self.assertEqual(PROTOCOL_SHA256, LOCKED_PROTOCOL)

    def test_all_features_equal_existing_pit_primitive(self) -> None:
        frame, calendar = prices()
        result = bank(frame, calendar)
        for row in result["records"]:
            if row["symbol"] != "FPT":
                continue
            expected = extract_pit_price_features(frame, [], calendar, row["as_of_date"], source=SOURCE)
            np.testing.assert_allclose(row["features"]["vector"], expected["vector"], rtol=0, atol=1e-12)
            self.assertEqual(row["features"]["coverage"], expected["coverage"])

    def test_labels_call_engine_helper_not_close_to_close(self) -> None:
        frame, calendar = prices(flat=True)
        frame.loc[21, ["Open", "High"]] = 200.
        with patch("core.mt_bicl_bank.compute_round_trip_net_return", wraps=compute_round_trip_net_return) as helper:
            result = bank(frame, calendar)
        row = result["records"][0]
        expected = compute_round_trip_net_return(200., 100.)
        self.assertEqual(row["outcome"]["r_net"], expected)
        self.assertEqual(row["outcome"]["y"], 0)
        self.assertEqual(helper.call_count, sum(r["label_status"] == "AVAILABLE" for r in result["records"]))
        self.assertLess(expected, -0.5)

    def test_corporate_action_and_zero_volume_have_separate_reasons(self) -> None:
        frame, calendar = prices(flat=True)
        frame.loc[22, "Volume"] = 0
        result = bank(frame, calendar, [{"exrightDate": str(calendar[22].date())}])
        first = result["records"][0]
        self.assertEqual(first["label_reasons"], ["NO_MATCHED_VOLUME_AT_EXECUTION", "CORPORATE_ACTION_DURING_HOLDING"])
        self.assertEqual(first["features"]["status"], "AVAILABLE")
        self.assertIsNone(first["outcome"])
        following = result["records"][4]
        self.assertIn("CORPORATE_ACTION_WINDOW", following["features"]["reasons"])

    def test_missing_sessions_are_not_compressed_or_filled(self) -> None:
        frame, calendar = prices(flat=True)
        result = bank(frame.drop(index=[10, 22]), calendar)
        row = result["records"][0]
        self.assertEqual(row["calendar_index"], 20)
        self.assertIn("MISSING_SESSION", row["features"]["reasons"])
        self.assertIn("MISSING_EXECUTION_SESSION", row["label_reasons"])
        self.assertIsNone(row["features"]["vector"])
        self.assertIsNone(row["outcome"])

    def test_buy_on_exright_is_allowed_but_reference_gap_during_holding_is_not(self) -> None:
        frame, calendar = prices(flat=True)
        first = bank(frame, calendar, [{"exrightDate": str(calendar[21].date())}])["records"][0]
        self.assertEqual(first["label_reasons"], [])
        self.assertIsNotNone(first["outcome"])
        frame.loc[22, "Reference"] += .1
        blocked = bank(frame, calendar)["records"][0]
        self.assertEqual(blocked["label_reasons"], ["CORPORATE_ACTION_DURING_HOLDING"])

    def test_leading_history_and_missing_cutoff_match_primitive(self) -> None:
        frame, calendar = prices(flat=True)
        for subset in (frame.iloc[10:], frame.drop(index=20)):
            row = bank(subset, calendar)["records"][0]
            expected = extract_pit_price_features(subset, [], calendar, row["as_of_date"], source=SOURCE)
            self.assertEqual(row["features"], expected)

    def test_empty_symbol_is_explicit_missing_not_fabricated(self) -> None:
        frame, calendar = prices(flat=True)
        data = {s: (frame, []) for s in SYMBOLS}
        data["FPT"] = (frame.iloc[:0], [])
        result = build_dense_bank(data, calendar, end_date=str(calendar[-1].date()))
        row = result["records"][0]
        self.assertEqual(row["features"]["reasons"], ["INSUFFICIENT_HISTORY", "MISSING_CUTOFF"])
        self.assertEqual(row["label_reasons"], ["MISSING_EXECUTION_SESSION"])

    def test_splits_purge_cycles_crossing_year_without_resampling(self) -> None:
        frame, calendar = prices(periods=800, flat=True)
        result = bank(frame, calendar)
        crossed = [row for row in result["records"] if row["as_of_date"][:4] == "2020" and row["exit_date"][:4] == "2021"]
        self.assertTrue(crossed)
        for row in crossed:
            self.assertIsNone(row["split"])
            self.assertIn("PURGED_SPLIT_BOUNDARY", row["reasons"])
            self.assertIsNone(row["outcome"])

    def test_bad_raw_source_and_unreleased_year_raise(self) -> None:
        frame, calendar = prices()
        broken = frame.copy()
        broken.loc[10, "Close"] = np.nan
        with self.assertRaises(ValueError):
            bank(broken, calendar)
        with self.assertRaises(ValueError):
            build_dense_bank({s: (frame, []) for s in SYMBOLS}, calendar, end_date="2023-01-01")

    def test_json_is_native_and_summary_missing_support_does_not_release_train(self) -> None:
        frame, calendar = prices()
        result = bank(frame, calendar)
        self.assertEqual(json.loads(canonical_bytes(result)), result)
        self.assertEqual(result["summary"]["minimum_support_status"], "STOP_INSUFFICIENT_TRAIN_SUPPORT")
        self.assertFalse(result["summary"]["training_allowed"])
        with self.assertRaises(ValueError):
            canonical_bytes({"bad": np.bool_(True)})

    def test_independent_verifier_rejects_changed_feature_and_label(self) -> None:
        frame, calendar = prices()
        result = bank(frame, calendar)
        sources = {s: (frame, []) for s in SYMBOLS}
        altered = deepcopy(result)
        altered["records"][0]["outcome"]["r_net"] += .1
        with self.assertRaisesRegex(ValueError, "Nhãn khác"):
            verify_records(altered, sources)
        altered = deepcopy(result)
        altered["records"][0]["features"]["vector"][0] += .1
        with self.assertRaisesRegex(ValueError, "feature khác"):
            verify_records(altered, sources)


class ScalerTests(unittest.TestCase):
    """Đối chiếu population variance, scale=1 và clip bằng số tính tay."""

    def test_population_variance_and_closed_fit(self) -> None:
        result = fit_scaler(scaler_bank(), "2020-12-28")
        self.assertEqual(result["fit_count"], 2)
        self.assertEqual(result["mean"], [2., 3., 4., 5.])
        self.assertEqual(result["variance"], [1.]*4)
        self.assertEqual(result["scale"], [1.]*4)
        self.assertEqual(result["fit_max_exit_date"], "2020-12-25")
        transformed = transform_features(feature("2020-12-28", [12., -7., 4., 5.]), result)
        self.assertEqual(transformed["z"], [10., -10., 0., 0.])
        self.assertEqual(transformed["model_vector"], [4., -4., 0., 0.])

    def test_zero_variance_and_no_history_have_explicit_states(self) -> None:
        data = scaler_bank()
        data["records"][1]["features"]["vector"] = [1., 2., 3., 4.]
        scaler = fit_scaler(data, "2020-12-28")
        self.assertEqual(scaler["scale"], [1.]*4)
        self.assertEqual(scaler["zero_variance"], [True]*4)
        absent = fit_scaler(data, "2020-12-21")
        self.assertEqual(absent["reasons"], ["SCALER_NO_CLOSED_HISTORY"])
        self.assertIsNone(absent["mean"])

    def test_past_context_uses_episode_query_scaler(self) -> None:
        data = scaler_bank()
        scaler = fit_scaler(data, "2020-12-28")
        context = data["records"][0]["features"]
        transformed = transform_features(context, scaler, query_date="2020-12-28")
        self.assertEqual(transformed["model_vector"], [-1.]*4)
        with self.assertRaises(ValueError):
            transform_features(context, scaler)
