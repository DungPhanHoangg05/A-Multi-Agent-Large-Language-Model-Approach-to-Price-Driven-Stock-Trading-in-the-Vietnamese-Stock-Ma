"""Giá và quyền tương lai không được sửa snapshot thô của agent."""

import json
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from core.execution_prices import (
    execution_prices_for_cycle, load_verified_execution_data, raw_point_in_time_snapshot,
)
from scripts.verify_execution_price_gate import REPO_ROOT, verify_bundle
from test_execution_prices import fixture_frame


class ExecutionPriceLeakageTests(unittest.TestCase):
    """Kiểm tra cutoff trước kiểm tra giá và từ chối gate chưa xác minh."""

    def test_appending_future_adjustments_does_not_change_snapshot(self) -> None:
        """Không suy ngược lịch sử từ cột điều chỉnh hồi tố."""
        original = fixture_frame()
        expected = raw_point_in_time_snapshot(original, "2022-06-10")
        changed = original.copy()
        changed.loc[2:, ["Open", "High", "Low", "Close"]] = float("nan")
        changed["closePriceAdjusted"] = 0.001
        pd.testing.assert_frame_equal(raw_point_in_time_snapshot(changed, "2022-06-10"), expected)
        self.assertEqual(expected.columns.tolist(), ["Datetime", "Open", "High", "Low", "Close", "Volume"])

    def test_snapshot_after_archive_or_missing_session_raises(self) -> None:
        """Không dùng nến gần nhất để giả lập phiên chưa có dữ liệu."""
        for date in ("2022-06-16", "2022-06-12", "2022-06-08"):
            with self.subTest(date=date), self.assertRaises(ValueError):
                raw_point_in_time_snapshot(fixture_frame(), date)

    def test_event_after_exit_cannot_change_execution_pair(self) -> None:
        """Dữ liệu quyền chỉ là kiểm tra nhãn sau chu kỳ, không là tín hiệu."""
        frame = fixture_frame()
        expected = execution_prices_for_cycle(frame, [], "2022-06-09", "2022-06-10", "2022-06-14")
        self.assertEqual(execution_prices_for_cycle(
            frame, [{"exrightDate": "2022-06-15", "publicDate": "2022-06-15"}],
            "2022-06-09", "2022-06-10", "2022-06-14"
        ), expected)

    def test_invalid_prices_after_exit_do_not_change_execution_pair(self) -> None:
        """Giá chỉ được kiểm tra đến phiên tất toán của chu kỳ đang xác minh."""
        frame = fixture_frame()
        expected = execution_prices_for_cycle(frame, [], "2022-06-09", "2022-06-10", "2022-06-14")
        frame.loc[4, ["Open", "High", "Low", "Close"]] = float("inf")
        self.assertEqual(execution_prices_for_cycle(
            frame, [], "2022-06-09", "2022-06-10", "2022-06-14"
        ), expected)

    def test_unverified_manifest_never_unlocks_prices(self) -> None:
        """Giá điều chỉnh hoặc gate PENDING không được dùng như dữ liệu đã kiểm toán."""
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for status, basis in (("PENDING", "UNADJUSTED_EXECUTION"), ("PASS", "ADJUSTED")):
                (folder / "manifest.json").write_text(json.dumps({
                    "price_gate": status, "price_basis": basis, "price_unit": "thousand_VND",
                    "primary_source": "VCI",
                }), encoding="utf-8")
                with self.subTest(status=status, basis=basis), self.assertRaisesRegex(ValueError, "chưa qua gate"):
                    load_verified_execution_data(folder, "FPT")

    def test_rehashed_csv_cannot_replace_raw_evidence(self) -> None:
        """Sửa CSV rồi cập nhật hash vẫn phải bị chặn nếu lệch bằng chứng thô."""
        source = REPO_ROOT / "data/execution_prices"
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
            for item in manifest["files"]["FPT"].values():
                if isinstance(item, dict) and "file" in item:
                    shutil.copyfile(source / item["file"], folder / item["file"])
            csv_path = folder / manifest["files"]["FPT"]["csv"]["file"]
            frame = pd.read_csv(csv_path)
            frame["Open"] *= 0.5
            frame["Low"] *= 0.5
            frame.to_csv(csv_path, index=False)
            manifest["files"]["FPT"]["csv"]["sha256"] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
            (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "evidence"):
                load_verified_execution_data(folder, "FPT")

    def test_verified_bundle_reproduces_gate_without_network(self) -> None:
        """Corpus đã chốt phải tái lập được đủ mẫu và 852 ứng viên qua gate giá."""
        manifest = verify_bundle(REPO_ROOT / "data/execution_prices")
        self.assertEqual(sum(item["eligible"] for item in manifest["files"].values()), 852)
        self.assertEqual(sum(len(item["excluded_cycles"]) for item in manifest["files"].values()), 16)


if __name__ == "__main__":
    unittest.main()
