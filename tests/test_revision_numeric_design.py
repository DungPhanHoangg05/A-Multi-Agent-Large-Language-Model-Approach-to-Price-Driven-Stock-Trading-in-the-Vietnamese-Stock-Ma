"""Kiểm thiết kế numeric controls, seeds/support/vote và không fit dữ liệu thật ở T12."""

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
from core.revision_alpha_contract import synthetic_frame
from core.revision_baselines import load_prices
from core.revision_common_study import read_json, write_json
from core.revision_numeric_design import (
    PROTOCOL, build_design, check_release, fit_numeric, freeze_design, predict_vote,
    random_set, strategy_sets, validate_protocol, validate_scope,
)
from core.revision_sentiment_inventory import BANK, RUN

ROOT = Path(__file__).resolve().parents[1]


def synthetic_scope() -> dict:
    """Scope giả có 20 train/10 validation/hai test với label exits đã purge."""
    return {"scope_id": "FIXTURE/b1", "symbol": "FIXTURE", "fold": "b1", "train_indices": list(range(599, 659, 3)),
            "validation_indices": list(range(665, 695, 3)), "test_indices": [699, 705]}


class NumericDesignTests(unittest.TestCase):
    """Kiểm protocol và công thức synthetic, không chọn theo outcome T11/T13."""

    def setUp(self) -> None:
        self.protocol = read_json(ROOT / PROTOCOL)

    def test_protocol_rejects_changed_fixed_seeds_cost_or_family(self) -> None:
        validate_protocol(self.protocol)
        for field in ("fixed", "seeds", "cost", "family", "warmup"):
            protocol = deepcopy(self.protocol)
            if field == "fixed": protocol["strategies"]["fixed_custom5"]["ids"][0] = "WQ42_VwapCloseRatio"
            if field == "seeds": protocol["strategies"]["random_eligible5"]["seeds"].append(20)
            if field == "cost": protocol["target"]["fee_each_side"] = 0.
            if field == "family": protocol["inference"]["multiplicity_family_size"] = 3
            if field == "warmup": protocol["features"]["warmup_first_decision"] = 0
            with self.subTest(field=field), self.assertRaises(ValueError): validate_protocol(protocol)

    def test_hash_random_set_has_golden_order_and_is_input_order_independent(self) -> None:
        ids = self.protocol["strategies"]["fixed_custom5"]["ids"] + ["WQ02_PriceVolDiv", "WQ03_OpenVolCorr", "WQ06_OpenVol"]
        golden = ["WQ03_OpenVolCorr", "CURRENT_5_OFE", "CURRENT_1_FDM", "CURRENT_4_BFE", "WQ06_OpenVol"]
        self.assertEqual(random_set(ids, "FIXTURE/b1", 0, self.protocol), golden)
        self.assertEqual(random_set(list(reversed(ids)), "FIXTURE/b1", 0, self.protocol), golden)
        self.assertEqual(len(set(random_set(ids, "FIXTURE/b1", 19, self.protocol))), 5)

    def test_random_set_rejects_seed_outside_whitelist_and_insufficient_pool(self) -> None:
        ids = self.protocol["strategies"]["fixed_custom5"]["ids"]
        with self.assertRaisesRegex(ValueError, "Seed"): random_set(ids, "s", 20, self.protocol)
        with self.assertRaisesRegex(ValueError, "Seed"): random_set(ids, "s", False, self.protocol)
        with self.assertRaisesRegex(ValueError, "Seed"): random_set(ids, "s", 0.0, self.protocol)
        with self.assertRaisesRegex(ValueError, "eligible"): random_set(ids[:4], "s", 0, self.protocol)
        with self.assertRaisesRegex(ValueError, "eligible"): random_set(ids + ids[:1], "s", 0, self.protocol)

    def test_scope_support_and_strict_label_exit_purge(self) -> None:
        frame = synthetic_frame(720); scope = synthetic_scope()
        support = validate_scope(frame, scope, self.protocol)
        self.assertEqual((support["train_rows"], support["validation_rows"], support["test_rows"]), (20, 10, 2))
        train_overlap = deepcopy(scope); train_overlap["train_indices"][-1] = 662
        with self.assertRaisesRegex(ValueError, "Train label"): validate_scope(frame, train_overlap, self.protocol)
        validation_overlap = deepcopy(scope); validation_overlap["validation_indices"][-1] = 696
        with self.assertRaisesRegex(ValueError, "Validation label"): validate_scope(frame, validation_overlap, self.protocol)

    def test_scope_rejects_fractional_duplicate_or_under_warmup_indices(self) -> None:
        frame = synthetic_frame(720)
        for change in ("float", "duplicate", "warmup", "short"):
            scope = synthetic_scope()
            if change == "float": scope["train_indices"][0] = 599.5
            if change == "duplicate": scope["train_indices"][1] = scope["train_indices"][0]
            if change == "warmup": scope["train_indices"][0] = 598
            if change == "short": scope["train_indices"].pop()
            with self.subTest(change=change), self.assertRaises(ValueError): validate_scope(frame, scope, self.protocol)

    def test_train_fit_disables_constant_and_preserves_five_fixed_slots(self) -> None:
        rng = np.random.default_rng(7)
        train = pd.DataFrame(rng.normal(size=(40, 85)), columns=sorted(alpha.ALPHA_REGISTRY))
        train["CURRENT_1_FDM"] = 1.
        fitted = fit_numeric(train, rng.normal(size=40), self.protocol)
        self.assertFalse(fitted["factors"]["CURRENT_1_FDM"]["eligible"])
        self.assertEqual(fitted["factors"]["CURRENT_1_FDM"]["orientation"], 0)
        self.assertNotIn("CURRENT_1_FDM", fitted["eligible_ids"])
        self.assertEqual(len(fitted["dynamic_ids"]), 5)
        fixed = self.protocol["strategies"]["fixed_custom5"]["ids"]
        self.assertEqual(len(fixed), 5)
        self.assertEqual(len(predict_vote(train.iloc[:3], fitted, fixed, self.protocol)), 3)

    def test_no_eligible_pool_fails_without_fallback_or_resize(self) -> None:
        train = pd.DataFrame(1., index=range(30), columns=sorted(alpha.ALPHA_REGISTRY))
        with self.assertRaisesRegex(ValueError, "Ít hơn năm"): fit_numeric(train, np.linspace(-1, 1, 30), self.protocol)

    def test_no_flip_only_changes_orientation_and_does_not_mutate_fit(self) -> None:
        ids = self.protocol["strategies"]["fixed_custom5"]["ids"]
        fitted = {"factors": {key: {"eligible": True, "median": 0., "mean": 0., "scale": 1., "orientation": -1} for key in ids}}
        original = deepcopy(fitted); features = pd.DataFrame(1., index=range(2), columns=ids)
        self.assertEqual(predict_vote(features, fitted, ids, self.protocol).tolist(), [0, 0])
        self.assertEqual(predict_vote(features, fitted, ids, self.protocol, no_flip=True).tolist(), [1, 1])
        self.assertEqual(fitted, original)

    def test_vote_tie_is_cash_and_does_not_use_display_rounding(self) -> None:
        ids = self.protocol["strategies"]["fixed_custom5"]["ids"]
        fitted = {"factors": {key: {"eligible": True, "median": 0., "mean": 0., "scale": 1., "orientation": 1} for key in ids}}
        features = pd.DataFrame([[1., -1., 0., 0., 0.], [1., 0., 0., 0., 0.]], columns=ids)
        self.assertEqual(predict_vote(features, fitted, ids, self.protocol).tolist(), [0, 1])
        with self.assertRaisesRegex(ValueError, "năm IDs"): predict_vote(features, fitted, ids[:4], self.protocol)

    def test_strategy_family_preserves_all_seeds_and_same_fit_for_no_flip(self) -> None:
        fitted = {"eligible_ids": sorted(alpha.ALPHA_REGISTRY), "dynamic_ids": sorted(alpha.ALPHA_REGISTRY)[-5:],
                  "factors": {key: {"eligible": True} for key in alpha.ALPHA_REGISTRY}}
        original = deepcopy(fitted); strategies = strategy_sets(fitted, "FIXTURE/b1", self.protocol)
        self.assertEqual(len(strategies), 23)
        self.assertEqual([k for k in strategies if k.startswith("random_seed_")], [f"random_seed_{i:02d}" for i in range(20)])
        self.assertEqual(strategies["dynamic_train_top5"]["ids"], strategies["dynamic_train_top5_no_flip"]["ids"])
        self.assertEqual(len({r["fit_digest"] for r in strategies.values()}), 1)
        self.assertEqual(sum(r["no_flip"] for r in strategies.values()), 1)
        self.assertEqual(fitted, original)

    def test_output_guards_and_hash_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / "outputs/revision/fixture"; output.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "Release đã có"): freeze_design(root, output)
            with self.assertRaisesRegex(ValueError, "release riêng"): freeze_design(root, root / "paper")
            from core.revision_audit import sha256_file
            write_json(output / "summary.json", {"fit_count": 0})
            write_json(output / "manifest.json", {"sources": [], "outputs": [{"path": "summary.json", "sha256": sha256_file(output / "summary.json")}]})
            self.assertEqual(check_release(root, output), 1)
            (output / "summary.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Hash sai"): check_release(root, output)


class FrozenControlMetadataTests(unittest.TestCase):
    """Kiểm toàn bộ 51 scopes bằng dates/indices đã có; không chạy feature/scoring thật."""

    @classmethod
    def setUpClass(cls) -> None:
        """Chỉ đọc metadata và snapshot hash, không đọc outcome để chọn thiết kế."""
        cls.protocol = read_json(ROOT / PROTOCOL); cls.queue = read_json(ROOT / RUN / "manifest.json")
        cls.bank = read_json(ROOT / BANK / "manifest.json")
        cls.frames, _ = load_prices(ROOT / cls.bank["protocol"]["price_snapshot"], cls.bank["protocol"]["price_quality_policy"])

    def test_all_frozen_roles_draws_and_hypotheses_are_planned_without_fitting(self) -> None:
        with patch("core.revision_numeric_design.fit_numeric", side_effect=AssertionError("Cấm fit")), \
             patch("core.revision_numeric_design.causal_factors", side_effect=AssertionError("Cấm features")), \
             patch("core.revision_numeric_design.predict_vote", side_effect=AssertionError("Cấm inference controls")):
            design = build_design(self.queue, self.bank, self.frames, self.protocol)
        self.assertEqual(len(design["scopes"]), 51)
        self.assertEqual(len(design["random_draws"]), 1020)
        self.assertEqual(len({d["draw_id"] for d in design["random_draws"]}), 1020)
        self.assertEqual(len(design["strategy_ids"]), 23)
        self.assertEqual(len(design["contrast_ids"]), 23)
        self.assertEqual(design["expected_predictions"], 2346)
        self.assertEqual(design["T12_real_data_fits"], 0)
        self.assertEqual(design["T13_status"], "not_run")
        self.assertEqual({role: sum(len(s[f"{role}_indices"]) for s in design["scopes"]) for role in ("train", "validation", "test")},
                         {"train": 10521, "validation": 994, "test": 102})

    def test_changed_or_duplicate_bank_scope_cannot_change_common_support(self) -> None:
        bank = deepcopy(self.bank); bank["schedule"][0]["test"][0] += 1
        with self.assertRaisesRegex(ValueError, "Bank test"): build_design(self.queue, bank, self.frames, self.protocol)
        bank = deepcopy(self.bank); bank["schedule"].append(deepcopy(bank["schedule"][0]))
        with self.assertRaisesRegex(ValueError, "Scope thiếu/trùng"): build_design(self.queue, bank, self.frames, self.protocol)


if __name__ == "__main__":
    unittest.main()
