"""Dò rỉ thời gian ở đặc trưng, model/scaler/calibration và suy luận regime."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from core.regime_detector import MarketRegimeDetector, _payload_hash, validate_regime_state
from test_regime_features import make_history

REPO_ROOT = Path(__file__).resolve().parents[1]


class RegimeLeakageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.history = pd.read_csv(REPO_ROOT / "data/historical/VNINDEX.csv", parse_dates=["Datetime"])
        cls.detector = MarketRegimeDetector.load(REPO_ROOT / "data_manager/regime_model.json")

    def test_future_mutations_do_not_change_hmm_endpoint(self) -> None:
        self.assertEqual(self.detector.metadata["classification_method"], "HMM")
        cutoff = "2023-03-15"
        expected = self.detector.get_market_regime(cutoff, self.history)
        for value in (float("nan"), float("inf"), 1e9):
            changed = self.history.copy()
            changed.loc[changed.Datetime > cutoff, "Close"] = value
            self.assertEqual(self.detector.get_market_regime(cutoff, changed), expected)

    def test_uncut_snapshot_and_future_trained_model_raise(self) -> None:
        with self.assertRaisesRegex(ValueError, "sau as_of_date"):
            self.detector.classify_regime(self.history, "2023-03-15")
        with self.assertRaisesRegex(ValueError, "Model/scaler/calibration"):
            self.detector.get_market_regime("2020-06-01", self.history)
        with self.assertRaisesRegex(ValueError, "2018–2022"):
            MarketRegimeDetector().fit(self.history)

    def test_prefix_fit_keeps_model_scaler_mapping_and_thresholds_causal(self) -> None:
        cutoff = "2020-06-01"
        changed = self.history.copy()
        changed.loc[changed.Datetime > cutoff, "Close"] = 1e9
        prefix = self.history.loc[self.history.Datetime <= cutoff]
        other_prefix = changed.loc[changed.Datetime <= cutoff]
        before = MarketRegimeDetector().fit(prefix)
        after = MarketRegimeDetector().fit(other_prefix)
        self.assertEqual(before.metadata, after.metadata)
        np.testing.assert_allclose(before._model.means_, after._model.means_, rtol=0, atol=1e-12)
        np.testing.assert_array_equal(before._scaler.mean_, after._scaler.mean_)
        self.assertEqual(before.classify_regime(prefix, cutoff), after.classify_regime(other_prefix, cutoff))

    def test_fallback_endpoint_is_invariant_to_future_mutations(self) -> None:
        archive = make_history(700)
        index = np.arange(len(archive))
        archive["Close"] = 1000.0 + 2 * index + 0.1 * np.sin(index / 14)
        prefix = archive.iloc[:650]
        detector = MarketRegimeDetector().fit(prefix)
        self.assertEqual(detector.metadata["classification_method"], "MULTI_FACTOR")
        cutoff = archive.Datetime.iloc[675]
        expected = detector.get_market_regime(cutoff, archive)
        archive.loc[archive.Datetime > cutoff, "Close"] = float("inf")
        self.assertEqual(detector.get_market_regime(cutoff, archive), expected)

    def test_queries_never_modify_frozen_parameters(self) -> None:
        meta = self.detector.metadata
        means = self.detector._model.means_.copy()
        transitions = self.detector._model.transmat_.copy()
        scale = self.detector._scaler.scale_.copy()
        for cutoff in ("2023-01-10", "2024-06-20", "2025-12-31"):
            self.detector.get_market_regime(cutoff, self.history)
        self.assertEqual(meta, self.detector.metadata)
        np.testing.assert_array_equal(means, self.detector._model.means_)
        np.testing.assert_array_equal(transitions, self.detector._model.transmat_)
        np.testing.assert_array_equal(scale, self.detector._scaler.scale_)

    def test_insufficient_and_changed_training_prefix_raise(self) -> None:
        prefix = self.history.loc[self.history.Datetime <= "2023-01-10"]
        with self.assertRaises(ValueError):
            self.detector.classify_regime(prefix.tail(199), "2023-01-10")
        with self.assertRaisesRegex(ValueError, "prefix train"):
            self.detector.classify_regime(prefix.drop(index=100), "2023-01-10")
        with self.assertRaisesRegex(ValueError, "prefix train"):
            self.detector.classify_regime(prefix.iloc[1:], "2023-01-10")

    def test_bad_calibration_or_convergence_metadata_raise(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            for key, value in (("latent_state_names", ["BULL"] * 4), ("classification_method", "UNKNOWN"),
                               ("fallback_reasons", ["Bỏ qua kiểm toán"]), ("em_converged", "True"),
                               ("last_gain", float("inf")), ("iterations", 0)):
                self.detector.save(path)
                envelope = json.loads(path.read_text(encoding="utf-8"))
                envelope["payload"]["metadata"][key] = value
                if key == "last_gain":
                    with self.assertRaises(ValueError):
                        _payload_hash(envelope["payload"])
                    continue
                envelope["sha256"] = _payload_hash(envelope["payload"])
                path.write_text(json.dumps(envelope), encoding="utf-8")
                with self.subTest(key=key), self.assertRaises(ValueError):
                    MarketRegimeDetector.load(path)

    def test_bad_model_parameters_and_numpy_json_values_raise(self) -> None:
        detector = deepcopy(self.detector)
        detector._model.startprob_[0] = float("nan")
        with self.assertRaises(ValueError):
            detector.get_market_regime("2023-01-10", self.history)
        state = self.detector.get_market_regime("2023-01-10", self.history)
        for key, value in (("regime_id", np.int64(state["regime_id"])),
                           ("trend_strength", np.float64(state["trend_strength"]))):
            with self.assertRaises(ValueError):
                validate_regime_state({**state, key: value})
