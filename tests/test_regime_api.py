"""Kiểm tra API regime trên artifact thật và hợp đồng schema W1."""

import json
from pathlib import Path
import unittest

import pandas as pd

from core.regime_detector import MarketRegimeDetector, REGIME_NAMES, validate_regime_state

REPO_ROOT = Path(__file__).resolve().parents[1]


class RegimeApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.detector = MarketRegimeDetector.load(REPO_ROOT / "data_manager/regime_model.json")
        cls.history = pd.read_csv(REPO_ROOT / "data/historical/VNINDEX.csv", parse_dates=["Datetime"])

    def test_archive_and_snapshot_apis_return_same_native_json(self) -> None:
        cutoff = "2023-01-10"
        snapshot = self.history.loc[self.history.Datetime <= cutoff]
        result = self.detector.classify_regime(snapshot, cutoff)
        self.assertEqual(result, self.detector.get_market_regime(cutoff, self.history))
        self.assertEqual(result, self.detector.get_market_regime(cutoff))
        self.assertEqual(result, json.loads(json.dumps(result, allow_nan=False)))
        self.assertIs(type(result["regime_id"]), int)
        self.assertIs(type(result["trend_strength"]), float)
        schema = json.loads((REPO_ROOT / "docs/plan/week1/market_regime_state.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(set(result), set(schema["required"]))
        self.assertIn(result["regime_name"], schema["properties"]["regime_name"]["enum"])
        self.assertEqual(result["regime_id"], REGIME_NAMES.index(result["regime_name"]))

    def test_nontrading_day_reports_last_available_feature(self) -> None:
        state = self.detector.get_market_regime("2023-01-07", self.history)
        self.assertEqual(state["as_of_date"], "2023-01-07")
        self.assertEqual(state["feature_end_date"], "2023-01-06")

    def test_schema_rejects_bad_name_id_types_and_date(self) -> None:
        state = self.detector.get_market_regime("2023-01-10", self.history)
        for key, value in (("regime_name", "CRASH"), ("regime_id", 4), ("regime_id", True),
                           ("trend_strength", float("nan")), ("source_symbol", "FPT"),
                           ("feature_end_date", "2023-01-11"), ("as_of_date", "2023/01/10")):
            invalid = {**state, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_regime_state(invalid)
        with self.assertRaises(ValueError):
            validate_regime_state({**state, "confidence": 1.0})

    def test_before_training_end_and_wrong_prefix_raise(self) -> None:
        with self.assertRaises(ValueError):
            self.detector.get_market_regime("2021-12-31", self.history)
        modified = self.history.loc[self.history.Datetime <= "2023-01-10"].copy()
        modified.loc[100, "Close"] *= 1.01
        with self.assertRaises(ValueError):
            self.detector.classify_regime(modified, "2023-01-10")
