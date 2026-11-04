"""Kiểm runner/checkpoints/cache/common support và analysis T13 bằng dữ liệu tổng hợp."""

from __future__ import annotations

from copy import deepcopy
import gzip
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import alpha_compare as alpha
from core.revision_alpha_contract import synthetic_frame
from core.revision_common_study import digest, read_json, write_json
from core.revision_numeric_controls import (
    checked, common_test, evaluate_scope, feature_cache, finalize, prepare, runtime, save_arrays,
    save_once, sealed, target_rows, validate_checkpoint, verify_sources,
)
from core.revision_numeric_design import PROTOCOL
from core.revision_sentiment_inventory import RUN
from test_revision_numeric_design import synthetic_scope
from test_revision_numeric_statistics import family

ROOT = Path(__file__).resolve().parents[1]


class NumericCheckpointTests(unittest.TestCase):
    """Scope fixture chạy core fit thật trên arrays giả, không inference/API hay outcomes thật."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = read_json(ROOT / PROTOCOL); cls.frame = synthetic_frame(720)
        cls.scope = synthetic_scope(); cls.run_record = {"sha256": "fixture_run"}; cls.receipt = {"sha256": "fixture_features"}
        cls.features = pd.DataFrame(np.random.default_rng(7).normal(size=(720, 85)), columns=sorted(alpha.ALPHA_REGISTRY))
        cls.design = {"protocol": cls.protocol, "strategy_ids": family()[0]}
        cls.record = evaluate_scope(cls.features, cls.frame, cls.scope, cls.design, cls.run_record, cls.receipt)

    def test_checkpoint_reuse_validates_semantics_without_refitting(self) -> None:
        with patch("core.revision_numeric_controls.fit_on_scope", side_effect=AssertionError("Không refit")):
            validate_checkpoint(self.record, self.features, self.frame, self.scope, self.design, self.run_record, self.receipt)
        self.assertEqual(len(self.record["predictions"]["test"]), 2)
        self.assertEqual(len(self.record["predictions"]["validation"]), 10)
        self.assertEqual(len(self.record["strategies"]), 23)

    def test_resigned_wrong_prediction_context_or_seed_is_rejected(self) -> None:
        for change in ("action", "context", "set"):
            record = deepcopy(self.record)
            if change == "action": record["predictions"]["test"][0]["actions"]["random_seed_00"] ^= 1
            if change == "context": record["context"]["scope_digest"] = "wrong"
            if change == "set": record["strategies"]["random_seed_00"]["ids"].reverse()
            record = sealed({k: v for k, v in record.items() if k != "sha256"})
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_checkpoint(record, self.features, self.frame, self.scope, self.design, self.run_record, self.receipt)

    def test_content_tamper_and_save_once_do_not_overwrite_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scope.json"; save_once(path, self.record); original = path.read_bytes()
            self.assertEqual(checked(path), self.record); save_once(path, self.record)
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaises(ValueError): save_once(path, {"changed": True})
            wrong = deepcopy(self.record); wrong["scope_id"] = "tampered"; write_json(path, wrong)
            with self.assertRaisesRegex(ValueError, "Content hash"): checked(path)

    def test_target_prices_invalid_are_not_turned_into_down_labels(self) -> None:
        frame = self.frame.copy(); frame.loc[702, "Close"] = np.nan
        with self.assertRaisesRegex(ValueError, "Target prices"): target_rows(frame, [699], self.protocol)

    def test_feature_cache_resume_and_partial_receipt_recovery_preserve_npz(self) -> None:
        design = {"scopes": [{**self.scope, "symbol": "FIXTURE"}], "protocol": self.protocol,
                  "protocol_digest": digest(self.protocol), "candidate_ids": sorted(alpha.ALPHA_REGISTRY)}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / "release"
            first, receipt = feature_cache(root, output, self.run_record, design, "FIXTURE", self.frame)
            path = output / "features/FIXTURE.npz"; original = path.read_bytes()
            with patch("core.revision_numeric_controls.causal_factors", side_effect=AssertionError("Không tính lại")):
                second, _ = feature_cache(root, output, self.run_record, design, "FIXTURE", self.frame)
            pd.testing.assert_frame_equal(first, second)
            path.with_suffix(".json").unlink()
            _, recovered = feature_cache(root, output, self.run_record, design, "FIXTURE", self.frame)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(receipt, recovered)
            path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
            with self.assertRaisesRegex(ValueError, "hash khác"): feature_cache(root, output, self.run_record, design, "FIXTURE", self.frame)

    def test_prepare_output_guards_and_source_freeze_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / "outputs/revision/existing"; output.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "Release đã có"): prepare(root, output)
            with self.assertRaisesRegex(ValueError, "release riêng"): prepare(root, root / "paper")
            source = root / "fixture.txt"; source.write_bytes(b"source")
            from core.revision_audit import sha256_file
            row = {"path": "fixture.txt", "sha256": sha256_file(source)}
            write_json(root / RUN / "manifest.json", {"sha256": "queue", "sources": [row]})
            run = {"runtime": runtime(), "queue_run_signature": "queue", "sources": [row]}
            verify_sources(root, run)
            source.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "Source guard"): verify_sources(root, run)

    def test_array_resume_compares_contents_including_undefined(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "arrays.npz"; arrays = {"numeric": np.array([1., np.nan]), "names": np.array(["A", "B"])}
            save_arrays(path, arrays); original = path.read_bytes(); save_arrays(path, arrays)
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaisesRegex(ValueError, "Array artifact khác"): save_arrays(path, {**arrays, "numeric": np.array([2., np.nan])})


def toy_results() -> tuple[dict, list[dict], dict[str, pd.DataFrame]]:
    """Sáu blocks giả, 12 units, mọi control CASH; oracle BA=.5/returns=0/p=1."""
    protocol = read_json(ROOT / PROTOCOL); protocol["scope"]["main_units"] = 12
    strategies, contrasts = family(); frame = synthetic_frame(90)
    frame[["Open", "Close"]] = 100.; frame["High"] = 103.; frame["Low"] = 99.
    scopes, records = [], []
    for block in range(6):
        indices = [block * 10, block * 10 + 5]
        frame.loc[indices[1] + 3, "Close"] = 102.
        units = [{"id": f"fixture_{i}", "symbol": "FIXTURE", "fold": f"b{block}", "decision": i, "date": str(frame["date"].iloc[i])} for i in indices]
        scope = {"scope_id": f"FIXTURE/b{block}", "symbol": "FIXTURE", "fold": f"b{block}", "test_indices": indices, "test_units": units}
        scopes.append(scope)
        rows = [{**row, "actions": {name: 0 for name in strategies}} for row in target_rows(frame, indices, protocol)]
        records.append({"scope_id": scope["scope_id"], "predictions": {"test": rows, "validation": rows},
                        "fitted": {"eligible_ids": sorted(alpha.ALPHA_REGISTRY)},
                        "strategies": {name: {"inactive_ids": []} for name in strategies}})
    design = {"protocol": protocol, "protocol_digest": digest(protocol), "scopes": scopes, "strategy_ids": strategies,
              "contrast_ids": contrasts, "expected_predictions": 12 * 23}
    return design, records, {"FIXTURE": frame}


class NumericAnalysisTests(unittest.TestCase):
    """Analysis/end-to-end serialization trên outcomes tổng hợp, không thay thực nghiệm thật."""

    def test_common_support_rejects_missing_seed_duplicate_scope_and_unit(self) -> None:
        design, records, _ = toy_results()
        units, truth, predicted = common_test(records, design)
        self.assertEqual((len(units), predicted.size), (12, 276))
        self.assertEqual(int(truth.sum()), 6)
        with self.assertRaisesRegex(ValueError, "scope"): common_test(records[:-1], design)
        wrong = deepcopy(records); wrong[0]["predictions"]["test"][0]["actions"].pop("random_seed_19")
        with self.assertRaisesRegex(ValueError, "mismatch"): common_test(wrong, design)
        with self.assertRaises(ValueError): common_test(records + records[:1], design)

    def test_finalization_all_cash_closed_form_and_deterministic_replay(self) -> None:
        design, records, frames = toy_results()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / "outputs/revision/results"; output.mkdir(parents=True)
            write_json(root / RUN / "manifest.json", {"sha256": "queue", "sources": []})
            run = {"sha256": "fixture", "sources": [], "runtime": runtime(), "queue_run_signature": "queue"}
            first = finalize(root, output, run, design, records, frames)
            manifest_before = (output / "manifest.json").read_bytes()
            second = finalize(root, output, run, design, records, frames)
            self.assertEqual(first, second); self.assertEqual((output / "manifest.json").read_bytes(), manifest_before)
            self.assertEqual(first["test_predictions"], 276)
            self.assertEqual(len(first["random_family"]["balanced_accuracy"]), 8)
            self.assertEqual(first["random_family"]["balanced_accuracy"]["mean"], .5)
            self.assertEqual(first["random_family"]["mean_symbol_return_pct"]["mean"], 0.)
            self.assertEqual(first["holm_rejections"], 0)
            self.assertTrue(all(r["p_holm_family_23"] == 1 for r in read_json(output / "inference.json")["contrasts"]))
            daily = gzip.decompress((output / "daily_ledgers.json.gz").read_bytes())
            self.assertIn(b'"equity_vnd":50000000.0', daily)


if __name__ == "__main__":
    unittest.main()
