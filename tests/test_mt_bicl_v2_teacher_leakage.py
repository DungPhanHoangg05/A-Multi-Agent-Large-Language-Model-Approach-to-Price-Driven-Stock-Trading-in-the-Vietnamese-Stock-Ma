"""Kiểm train-only, nhãn kinh tế, nhãn query ẩn và pool feature v2 không dùng outcome."""

from __future__ import annotations

from copy import deepcopy
import unittest

from core.backtest_engine import compute_round_trip_net_return
from core.mt_bicl_scaler import fit_scaler
from core.mt_bicl_v2_preparation import fixture_input
from core.mt_bicl_v2_simulator import train_feature_pool
from core.mt_bicl_v2_teacher import BetaBernoulliTeacher, train_task_counts
from scripts.verify_mt_bicl_protocol_v2 import training_membership
from mt_bicl_bank_support import scaler_bank


def fixture_bank() -> tuple[dict, dict]:
    """Bank nhỏ có ba cycle train và một query2021 bị cấm cho fit."""
    bank = scaler_bank()
    for j, row in enumerate(bank["records"]):
        row["task_id"] = row["symbol"]+":block0000"
        row["label_status"] = "AVAILABLE"
        net = float(compute_round_trip_net_return(100., 101. if j % 2 else 99.))
        row["outcome"] = {"entry_open": 100., "exit_close": 101. if j % 2 else 99.,
                          "r_net": net, "y": int(net > 0)}
    bank["frozen_scaler"] = fit_scaler(bank, "2021-01-01")
    return bank, training_membership(bank)


class TeacherLeakageTests(unittest.TestCase):
    """Dữ liệu ngoài train bị loại trước đọc nhãn; vi phạm membership thật phải raise."""

    def test_future_poisoned_labels_features_and_append_do_not_change_fit_inputs(self) -> None:
        bank, membership = fixture_bank()
        before_counts, before_pool = train_task_counts(bank, membership), train_feature_pool(bank, membership)
        changed = deepcopy(bank)
        future = changed["records"][-1]
        future["outcome"] = {"y": "Nhãn tương lai không được đọc"}
        future["features"]["vector"] = [float("nan")]*4
        added = deepcopy(future)
        added["episode_id"] = "future-added"
        changed["records"].append(added)
        self.assertEqual(train_task_counts(changed, membership), before_counts)
        self.assertEqual(train_feature_pool(changed, membership), before_pool)

    def test_future_mislabeled_train_or_duplicate_is_rejected(self) -> None:
        bank, membership = fixture_bank()
        future = deepcopy(bank)
        future["records"][-1]["split"] = "train"
        with self.assertRaisesRegex(ValueError, "ngoài split"):
            train_task_counts(future, membership)
        duplicate = deepcopy(bank)
        duplicate["records"].append(deepcopy(duplicate["records"][0]))
        with self.assertRaisesRegex(ValueError, "ID trùng"):
            train_task_counts(duplicate, membership)

    def test_train_labels_must_match_engine_not_close_to_close(self) -> None:
        bank, membership = fixture_bank()
        bank["records"][0]["outcome"]["r_net"] = -.01
        with self.assertRaisesRegex(ValueError, "helper kinh tế"):
            train_task_counts(bank, membership)

    def test_pool_never_reads_outcome_and_future_feature_date_raises(self) -> None:
        bank, membership = fixture_bank()
        before = train_feature_pool(bank, membership)
        for row in bank["records"]:
            row.pop("outcome")
        self.assertEqual(before, train_feature_pool(bank, membership))
        bank["records"][0]["features"]["feature_end_date"] = "2022-01-01"
        with self.assertRaises(ValueError):
            train_feature_pool(bank, membership)

    def test_missing_membership_or_changed_scaler_is_rejected(self) -> None:
        bank, membership = fixture_bank()
        changed = deepcopy(membership)
        changed["task_cycle_ids"].pop(next(iter(changed["task_cycle_ids"])))
        with self.assertRaisesRegex(ValueError, "Membership"):
            train_task_counts(bank, changed)
        bank["frozen_scaler"]["mean"][0] += 1
        with self.assertRaises(ValueError):
            train_feature_pool(bank, membership)

    def test_query_y_latent_and_duplicates_cannot_enter_teacher(self) -> None:
        teacher = BetaBernoulliTeacher([1/16]*16)
        for key in ("y", "theta", "outcome"):
            data = fixture_input([[4,4]], [1,1])
            data["query"][key] = 1
            with self.assertRaisesRegex(ValueError, "Query"):
                teacher.predict(data)
        data = fixture_input([[4,4]], [1,1])
        data["target"]["observations"][0]["observation_id"] = "Q"
        with self.assertRaisesRegex(ValueError, "ID thiếu hoặc trùng"):
            teacher.predict(data)

    def test_q_depends_only_on_visible_counts_not_query_features_or_sidecars(self) -> None:
        teacher = BetaBernoulliTeacher([1/16]*16)
        data = fixture_input([[6,0]], [0,2])
        expected = teacher.predict(data)
        data["query"]["x"] = [4., -4., 4., -4.]
        self.assertEqual(expected, teacher.predict(data))
        with self.assertRaises(ValueError):
            teacher.predict({"input": data, "query_y": 1, "theta": .999})
        self.assertEqual(teacher.pi.tolist(), [1/16]*16)


if __name__ == "__main__":
    unittest.main()
