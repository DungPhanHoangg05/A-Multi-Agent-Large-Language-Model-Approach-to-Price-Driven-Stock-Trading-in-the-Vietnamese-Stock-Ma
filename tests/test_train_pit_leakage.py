"""Chặn ngày entry/exit sai và model full tương lai; prefix không đổi vì nến tương lai."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from core.price_feature_index import build_price_feature_index
from core.train_pit_validation import fold_schedule, verify_regime_fit
from price_feature_index_support import index_inputs
from train_pit_support import regime_fixture


class TrainPITLeakageTests(unittest.TestCase):
    def test_actual_entry_exit_timing_and_index_dates_fail_closed(self) -> None:
        inputs = index_inputs()
        index = build_price_feature_index(**inputs)
        records = deepcopy(inputs["records"])
        for row in records:
            row["entry_date"] = inputs["calendar"][inputs["calendar"].get_loc(row["as_of_date"])+1].strftime("%Y-%m-%d")
        for field, value in (("entry_date", records[0]["as_of_date"]), ("exit_date", "2020-06-05")):
            changed = deepcopy(records)
            changed[0][field] = value
            with self.assertRaises(ValueError):
                fold_schedule(changed, index, inputs["calendar"])
        changed = deepcopy(records)
        changed[0].update(as_of_date="2020-06-02", entry_date="2020-06-03", exit_date="2020-06-05")
        with self.assertRaisesRegex(ValueError, "bank khác index"):
            fold_schedule(changed, index, inputs["calendar"])

    def test_future_or_frozen_model_cannot_validate_early_fold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter, point = regime_fixture(Path(directory))
            original = deepcopy(point.source_provenance)
            for mutation in ("metadata", "component", "frozen"):
                point.source_provenance = deepcopy(original)
                proof = point.source_provenance["regime"]
                if mutation == "metadata":
                    proof["metadata"]["train_end_date"] = "2022-12-30"
                elif mutation == "component":
                    proof["component_train_end_dates"]["calibration"] = "2022-12-30"
                else:
                    proof["frozen_model"] = {"freeze_as_of_date": "2022-12-30"}
                with self.assertRaisesRegex(ValueError, "sai prefix"):
                    verify_regime_fit(adapter, point)

    def test_future_market_mutation_does_not_change_recomputed_prefix_fit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter, point = regime_fixture(Path(directory))
            expected = verify_regime_fit(adapter, point)
            future = adapter._vnindex.Datetime > "2021-01-04"
            adapter._vnindex.loc[future, "Close"] *= 7
            self.assertEqual(verify_regime_fit(adapter, point), expected)
