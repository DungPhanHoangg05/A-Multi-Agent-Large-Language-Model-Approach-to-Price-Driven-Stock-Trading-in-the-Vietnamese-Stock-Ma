"""Kiểm goldens/oracle độc lập, provenance và release T10; không API hoặc nhãn thị trường."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import alpha_compare as alpha
from core.revision_alpha_contract import (
    FIXTURE, check_release, feature_cases, matches, metadata_impact, operator_cases, prototype_cases,
    run_audit, safe, surrogate_cases, synthetic_frame, translation_cases,
)
from core.revision_common_study import read_json, write_json
from core.revision_sentiment_inventory import BANK

ROOT = Path(__file__).resolve().parents[1]


class AlphaContractTests(unittest.TestCase):
    """Các assertions bao phủ chính hàm native, không chỉ AST hoặc mô phỏng selector."""

    def test_twenty_two_declared_operator_goldens(self) -> None:
        rows = operator_cases(read_json(ROOT / FIXTURE))
        self.assertEqual(len(rows), 22)
        self.assertTrue(all(row["result"] == "PASS" for row in rows))

    def test_wrong_expected_operator_or_nan_mask_fails(self) -> None:
        cases = deepcopy(read_json(ROOT / FIXTURE))
        cases["operators"][0]["expected"][1] = .5
        with self.assertRaises(AssertionError): operator_cases(cases)
        with self.assertRaises(AssertionError): matches([None, 1.], [0., 1.])

    def test_volume_availability_boundary_proxy_and_partial_adv(self) -> None:
        rows = feature_cases(read_json(ROOT / FIXTURE))
        self.assertEqual(len(rows), 7)
        by_id = {row["id"]: row for row in rows}
        self.assertFalse(by_id["forty_percent_boundary"]["real_volume"])
        self.assertTrue(by_id["above_forty_percent"]["real_volume"])
        self.assertIn("đơn vị giá", by_id["absent_volume"]["units"])

    def test_price_volume_units_and_vwap_adv_are_not_dollar_volume(self) -> None:
        frame = synthetic_frame()
        first = alpha.build_features(frame)
        scaled = frame.copy(); scaled["Volume"] *= 100
        second = alpha.build_features(scaled)
        matches(second["adv20"], first["adv20"] * 100)
        matches(second["vwap"], (frame["High"] + frame["Low"] + frame["Close"]) / 3)
        matches(alpha.alpha_bfe(first), alpha.alpha_bfe(second))
        self.assertNotAlmostEqual(first["adv20"].iloc[-1], np.mean((frame["Volume"] * frame["Close"]).iloc[-20:]))

    def test_custom_and_worldquant_independent_oracles(self) -> None:
        rows = translation_cases()
        self.assertEqual([row["id"] for row in rows], read_json(ROOT / FIXTURE)["translation_cases"])
        by_id = {row["id"]: row for row in rows}
        self.assertNotAlmostEqual(by_id["WQ7"]["observed"], by_id["WQ7"]["source_window_counterfactual"])
        self.assertNotAlmostEqual(by_id["WQ54"]["observed"], by_id["WQ54"]["original_power5_counterfactual"])
        self.assertEqual(by_id["WQ61"]["source_corr_floor"], 17)
        self.assertEqual(by_id["WQ65"]["source_adv_sum_floor"], 8)

    def test_changed_native_formula_is_detected_by_oracle(self) -> None:
        def wrong_handler(_: pd.DataFrame) -> pd.Series:
            """Thay đúng handler đã bind trong registry để chứng minh oracle bắt được sai công thức."""
            return pd.Series(np.zeros(96))
        with patch.dict(alpha.ALPHA_REGISTRY, {"CURRENT_4_BFE": (wrong_handler, "fixture")}):
            with self.assertRaises(AssertionError): translation_cases()

    def test_prototype_sfa_and_alpha4_pre_rounding_threshold(self) -> None:
        rows = prototype_cases()
        self.assertEqual(len(rows), 6)
        positive = [row for row in rows if row["id"].startswith("prototype_Alpha4_0")]
        self.assertEqual([row["observed_display"] for row in positive], [.1, .1])
        self.assertEqual([row["observed_signal"] for row in positive], ["TRUNG TÍNH", "TĂNG"])

    def test_rank_and_neutralization_surrogates_have_explicit_limits(self) -> None:
        rows = surrogate_cases()
        self.assertEqual(rows[0]["cross_sectional_ranks_with_changed_peer"], [.5, 1.])
        self.assertEqual(rows[1]["id"], "WQ89_no_industry_inputs")

    def test_json_undefined_is_null_and_numpy_types_are_native(self) -> None:
        value = safe({"flag": np.bool_(True), "integer": np.int64(2), "values": np.array([np.nan, np.inf, -np.inf, 1.])})
        self.assertEqual(json.loads(json.dumps(value, allow_nan=False)), {"flag": True, "integer": 2, "values": [None, None, None, 1.]})

    def test_metadata_scope_distinguishes_asset_and_actual_prompt_formula(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = "CURRENT_2_SFA"; template = alpha.get_alpha_template(key)
            unit = {"id": "fixture", "symbol": "FIXTURE", "decision": 1}
            write_json(root / BANK / "features/FIXTURE_1.json", {"alpha_factors": [{"name": template["name"], "formula": template["formula"]}]})
            queue = {"jobs": [{"id": "job", "phase": "main", "unit": unit, "context": {"variant": "AS"}, "prompt": "fixture"}]}
            with patch("core.revision_alpha_contract.prompt_parts", return_value={"alpha": "Compact name/value only"}):
                impact, _ = metadata_impact(root, queue)
            self.assertEqual(impact["main_units_with_metadata_mismatch"], 1)
            self.assertEqual(impact["jobs_with_literal_wrong_formula"], 0)
            with patch("core.revision_alpha_contract.prompt_parts", return_value={"alpha": template["formula"]}):
                impact, _ = metadata_impact(root, queue)
            self.assertEqual(impact["jobs_with_literal_wrong_formula"], 1)

    def test_output_guards_and_hash_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / "outputs/revision/fixture"
            output.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "Release đã có"): run_audit(root, output)
            with self.assertRaisesRegex(ValueError, "release riêng"): run_audit(root, root / "paper")
            write_json(output / "summary.json", {"result": "fixture"})
            from core.revision_audit import sha256_file
            write_json(output / "manifest.json", {"sources": [], "outputs": [{"path": "summary.json", "sha256": sha256_file(output / "summary.json")}]})
            self.assertEqual(check_release(root, output), 1)
            (output / "summary.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Hash sai"): check_release(root, output)


if __name__ == "__main__":
    unittest.main()
