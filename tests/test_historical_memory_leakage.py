"""Kho lịch sử không trả chu kỳ còn mở hoặc thoát đúng ngày truy vấn."""

import unittest

import test_historical_memory as fixtures


class HistoricalMemoryLeakageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.HistoricalMemoryTests.setUpClass()

    def setUp(self):
        self.helper = fixtures.HistoricalMemoryTests()
        self.memory = self.helper.memory()
        self.record = self.helper.record()
        self.memory.add(self.record)

    def test_future_crossing_and_same_day_exit_excluded(self):
        for cutoff in (self.record["as_of_date"], self.record["entry_date"], self.record["exit_date"]):
            with self.subTest(cutoff=cutoff):
                self.assertEqual(self.memory.eligible(cutoff), [])
        result = self.memory.eligible(self.helper.record(1)["exit_date"], "FPT")
        self.assertEqual(result, [self.record])
        result[0]["exit_date"] = "2099-01-01"
        self.assertEqual(self.memory.records, [self.record])

    def test_invalid_cutoff_is_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            self.memory.eligible("2020-02-30")


if __name__ == "__main__":
    unittest.main()
