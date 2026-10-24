"""Chặn self/future append, snapshot 2025 và rò rỉ qua scaler/feature U-BICL."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from core.pit_price_features import extract_pit_price_features
from core.unified_bayes_memory import build_memory
from unified_memory_test_support import memory_inputs, upstream


class UnifiedMemoryLeakageTests(unittest.TestCase):
    """Các query chỉ đọc outcome sau khi metadata đã qua strict exit cutoff."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = memory_inputs()
        cls.memory = build_memory(**cls.inputs)

    def test_future_append_does_not_change_past_population_or_scaler(self) -> None:
        """Thêm upstream 2024 không đổi tập 2023, vector cũ hoặc fit OOS."""
        inputs = deepcopy(self.inputs)
        inputs["imported"] = [r for r in inputs["imported"] if r["as_of_date"] < "2024-01-01"]
        before = build_memory(**inputs)
        self.assertEqual(before.eligible("FPT", "2023-06-01"), self.memory.eligible("FPT", "2023-06-01"))
        self.assertEqual(before.example_pool("FPT", "2023-06-01", "BULL"),
                         self.memory.example_pool("FPT", "2023-06-01", "BULL"))
        self.assertEqual(before.index.payload["scalers"], self.memory.index.payload["scalers"])
        old = {r["episode_id"]: r for r in before.index.payload["records"]}
        for row in self.memory.index.payload["records"]:
            if row["episode_id"] in old:
                self.assertEqual(row, old[row["episode_id"]])

    def test_same_day_exit_and_query_self_match_are_excluded_before_outcome_read(self) -> None:
        """Poison outcome của self/future không được chạm tới trong query cũ."""
        class Poison(dict):
            def __deepcopy__(self, memo: dict) -> dict:
                raise AssertionError("Đã đọc outcome future/self")
        memory = build_memory(**self.inputs)
        for key, row in list(memory._records.items()):
            if row["symbol"] == "FPT" and row["exit_date"] >= "2023-01-06":
                memory._records[key] = Poison(row)
        visible = memory.eligible("FPT", "2023-01-06")
        self.assertNotIn("FPT:2023-01-03", {r["episode_id"] for r in visible})
        self.assertNotIn("FPT:2023-01-03", {r["episode_id"] for r in memory.eligible("FPT", "2023-01-03")})

    def test_declared_evidence_with_future_self_wrong_symbol_or_relabel_raises(self) -> None:
        """Đầu vào đã khai PIT vi phạm phải lỗi, không bị lọc âm thầm."""
        for row in (next(r for r in self.memory.payload["records"] if r["episode_id"] == "FPT:2023-01-03"),
                    next(r for r in self.memory.payload["records"] if r["symbol"] == "MWG")):
            with self.assertRaises(ValueError):
                self.memory.assert_evidence([row], "FPT", "2023-01-03")
        row = self.memory.eligible("FPT", "2025-01-02")[0]
        row["outcome"]["net_return_pct"] += 1.
        with self.assertRaises(ValueError):
            self.memory.assert_evidence([row], "FPT", "2025-01-02")

    def test_prior_features_refuse_self_future_or_wrong_fold(self) -> None:
        """Không đọc vector của cycle chưa đóng và không dùng scaler cuối train ở fold cũ."""
        for day, key in (("2023-01-03", "FPT:2023-01-03"), ("2023-01-06", "FPT:2023-01-03"),
                         ("2023-06-01", "FPT:2024-12-26")):
            with self.subTest(day=day), self.assertRaises(ValueError):
                self.memory.index.prior_features("FPT", day, [key])
        with self.assertRaises(ValueError):
            self.memory.index.scaler("FPT", "2021-06-01", fold_id="oos_2023_2025")

    def test_confirmation_outcomes_and_cross_year_exit_cannot_be_appended(self) -> None:
        """Snapshot dùng cho 2025 chỉ tới exit cuối 2024; không cập nhật online."""
        for cutoff in ("2025-01-02", "2024-12-31"):
            inputs = deepcopy(self.inputs)
            inputs["imported"].append(upstream("FPT", cutoff))
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                build_memory(**inputs)

    def test_future_prices_and_rights_cannot_change_memory_before_2025(self) -> None:
        """Cắt tại cutoff/exit trước kiểm giá, feature và fit; không mượn giá tương lai."""
        inputs = deepcopy(self.inputs)
        for frame, events in inputs["prices"].values():
            frame.loc[frame.Datetime.dt.year.eq(2025), "Open"] = float("inf")
            events.append({"exrightDate": "2025-02-03"})
        changed = build_memory(**inputs)
        self.assertEqual(changed.payload["records"], self.memory.payload["records"])
        self.assertEqual(changed.index.payload, self.memory.index.payload)

    def test_2025_query_uses_train_scaler_and_future_features_raise(self) -> None:
        """Query 2025 được transform đúng bốn chiều; không nhận feature ngày sau query."""
        frame, events = self.inputs["prices"]["FPT"]
        features = extract_pit_price_features(frame, events, self.inputs["calendar"], "2025-01-02", source=self.inputs["source"])
        result = self.memory.index.transform_query("FPT", "2025-01-02", features)
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertEqual(len(result["scaled_vector"]), 4)
        features["feature_end_date"] = "2025-01-03"
        with self.assertRaises(ValueError):
            self.memory.index.transform_query("FPT", "2025-01-02", features)

    def test_hot_queries_do_not_read_disk_extract_fit_or_generate_labels(self) -> None:
        """Cache đủ phục vụ query; không gọi producer/engine hoặc API lại."""
        with patch("pathlib.Path.read_bytes", side_effect=AssertionError("I/O")), \
             patch("core.unified_bayes_memory.extract_pit_price_features", side_effect=AssertionError("extract")), \
             patch("core.unified_bayes_memory.build_price_feature_index", side_effect=AssertionError("fit")), \
             patch("core.historical_outcomes.HistoricalOutcomeGenerator.generate", side_effect=AssertionError("label")):
            rows = self.memory.eligible("FPT", "2025-01-02")
            self.memory.index.prior_features("FPT", "2025-01-02", [r["episode_id"] for r in rows])
            self.memory.example_pool("FPT", "2025-01-02", "BULL")


if __name__ == "__main__":
    unittest.main()
