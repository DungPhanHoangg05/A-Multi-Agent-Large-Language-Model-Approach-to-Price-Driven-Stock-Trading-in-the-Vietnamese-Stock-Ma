"""Kiểm tra fit đóng băng, JSON artifact và định danh tập train."""

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from core.regime_detector import MarketRegimeDetector, _payload_hash, training_data_hash
from test_regime_features import make_history


class RegimeModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.history = make_history()
        cls.detector = MarketRegimeDetector().fit(cls.history)

    def test_fit_metadata_and_refit_guard(self) -> None:
        meta = self.detector.metadata
        self.assertEqual(meta["training_rows"], 650)
        self.assertEqual(meta["feature_rows"], 451)
        self.assertEqual(meta["training_data_sha256"], training_data_hash(self.history))
        meta["training_rows"] = 1
        self.assertEqual(self.detector.metadata["training_rows"], 650)
        with self.assertRaises(ValueError):
            self.detector.fit(self.history)

    def test_invalid_training_ranges_and_sample_size(self) -> None:
        for frame in (make_history(650, "2022-01-03"), make_history(650, "2017-01-02"), make_history(498)):
            with self.subTest(start=str(frame.Datetime.iloc[0])), self.assertRaises(ValueError):
                MarketRegimeDetector().fit(frame)

    def test_roundtrip_preserves_parameters_and_expected_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            self.detector.save(path)
            loaded = MarketRegimeDetector.load(path, expected_training_hash=training_data_hash(self.history))
            self.assertEqual(loaded.metadata, self.detector.metadata)
            np.testing.assert_array_equal(loaded._model.means_, self.detector._model.means_)
            np.testing.assert_array_equal(loaded._scaler.scale_, self.detector._scaler.scale_)
            with self.assertRaises(ValueError):
                MarketRegimeDetector.load(path, expected_training_hash="0" * 64)

    def test_corrupt_checksum_shape_and_version_raise(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            for kind in ("checksum", "shape", "version", "probability", "features"):
                self.detector.save(path)
                data = json.loads(path.read_text(encoding="utf-8"))
                payload = data["payload"]
                if kind == "checksum":
                    data["sha256"] = "0" * 64
                elif kind == "shape":
                    payload["model"]["means"] = [[0.0]]
                elif kind == "version":
                    payload["metadata"]["versions"]["hmmlearn"] = "0.0.0"
                elif kind == "probability":
                    payload["model"]["startprob"] = [0.0] * 4
                else:
                    payload["metadata"]["feature_columns"] = ["future_return"]
                if kind != "checksum":
                    data["sha256"] = _payload_hash(payload)
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    MarketRegimeDetector.load(path)

    def test_same_seed_produces_same_parameters(self) -> None:
        other = MarketRegimeDetector().fit(self.history)
        np.testing.assert_allclose(other._model.means_, self.detector._model.means_, rtol=0, atol=1e-12)

    def test_near_constant_features_preserve_standard_scaler_convention(self) -> None:
        history = make_history()
        history["Close"] = 1000.0 * np.exp(.001 * np.arange(len(history)))
        detector = MarketRegimeDetector().fit(history)
        self.assertTrue(((detector._scaler.var_ > 0) & (detector._scaler.scale_ == 1)).any())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "constant.json"
            detector.save(path)
            loaded = MarketRegimeDetector.load(path)
            self.assertEqual(detector.classify_regime(history, history.Datetime.iloc[-1]),
                             loaded.classify_regime(history, history.Datetime.iloc[-1]))
