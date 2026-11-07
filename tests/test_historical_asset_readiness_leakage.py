"""Kiểm biên input/nhãn readiness, không chạy forecast hoặc đọc query payoff vào state."""

from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import pandas as pd

from core.historical_asset_readiness import (
    ARCHIVE, BANK, DONOR, OUTPUT, PRICES, check_bridge, destination, encode,
    frozen_assets, git, grid_audit, label_oracle, news_audit, preserve, price_view, sha,
)

ROOT = Path(__file__).resolve().parents[1]


class ReadinessTests(unittest.TestCase):
    """Đối chiếu trên input donor và poison có chủ đích ở đúng hợp đồng H02."""

    @classmethod
    def setUpClass(cls) -> None:
        """Chỉ đọc Git pin; không phụ thuộc receipt readiness được sinh sẵn."""
        cls.oracle = staticmethod(label_oracle(git(ROOT, "show", f"{DONOR}:utils/target_contract.py")))
        cls.bank = json.loads(git(ROOT, "show", f"{DONOR}:{BANK}/manifest.json"))
        manifest = json.loads(git(ROOT, "show", f"{DONOR}:{PRICES}/manifest.json"))
        cls.frames, cls.views = {}, {}
        for row in manifest["symbols"]:
            data = git(ROOT, "show", f"{DONOR}:{PRICES}/{row['path']}")
            cls.frames[row["symbol"]], cls.views[row["symbol"]] = price_view(data)
        cls.news = json.loads(git(ROOT, "show", f"{DONOR}:{BANK}/news.json"))
        cls.scores = json.loads(git(ROOT, "show", f"{DONOR}:{BANK}/local_scores.json"))
        cls.articles = json.loads(git(ROOT, "show", f"{DONOR}:{BANK}/article_audit.json"))

    def test_raw_bhn_suffix_retains_index_offset(self) -> None:
        """Không sửa nến lỗi hoặc dùng raw index làm suffix index."""
        self.assertEqual(self.views["BHN"]["excluded_prefix_rows"], 673)
        self.assertEqual(self.views["BHN"]["bad_ohlc_dates"], ["2022-09-13"])
        self.assertEqual(self.frames["BHN"]["date"].iloc[0], "2022-09-14")

    def test_bad_dates_and_nonfinite_prices_stop(self) -> None:
        """Không âm thầm bỏ input mâu thuẫn ngoài policy OHLC suffix."""
        frame = self.frames["FPT"].iloc[:5].copy()
        frame.loc[1, "date"] = frame.loc[0, "date"]
        with self.assertRaises(ValueError):
            price_view(frame.to_csv(index=False).encode())
        frame = self.frames["FPT"].iloc[:5].copy()
        frame.loc[1, "Close"] = float("inf")
        with self.assertRaises(ValueError):
            price_view(frame.to_csv(index=False).encode())

    def test_grid_scope_and_no_query_outcomes(self) -> None:
        """Xuất mapping input, chỉ tổng hợp parity trong scoring boundary."""
        grid, bridge = grid_audit(self.frames, self.views, self.bank, self.oracle)
        self.assertEqual((len(grid), sum(r["core4"] for r in grid), sum(r["anchor"] for r in grid)), (1020, 480, 102))
        self.assertEqual(len({r["date"] for r in grid}), 120)
        self.assertEqual(bridge["status"], "PASS")
        self.assertFalse(bridge["execution_data_certified"])
        self.assertFalse(bridge["historical_bank_membership_certified"])
        self.assertTrue(all(not {"net_return", "label_net", "query_y", "entry_open", "exit_close"}.intersection(r) for r in grid))
        bhn = next(r for r in grid if r["symbol"] == "BHN")
        self.assertEqual(bhn["raw_decision_index"] - bhn["suffix_decision_index"], 673)

    def test_stride_three_accepts_exit_equal_next_decision(self) -> None:
        """Ledger yêu cầu exit trước entry kế tiếp, không cấm exit bằng decision kế."""
        grid, _ = grid_audit(self.frames, self.views, self.bank, self.oracle)
        self.assertEqual(grid[0]["exit_date"], grid[1]["date"])
        self.assertLess(grid[0]["exit_date"], grid[1]["entry_date"])

    def test_anchor_index_date_poison_stops(self) -> None:
        """Từ chối anchor lệch ngày thay vì sửa ID để tiếp tục."""
        bank = deepcopy(self.bank)
        bank["units"][0]["date"] = "2099-01-01"
        with self.assertRaisesRegex(ValueError, "anchor"):
            grid_audit(self.frames, self.views, bank, self.oracle)

    def test_train_exit_equal_validation_is_leakage(self) -> None:
        """Nhãn train phải trưởng thành trước validation nghiêm ngặt."""
        bank = deepcopy(self.bank)
        scope = bank["schedule"][0]
        scope["train"][-1] = min(scope["validation"]) - 3
        with self.assertRaisesRegex(ValueError, "trưởng thành"):
            grid_audit(self.frames, self.views, bank, self.oracle)

    def test_bridge_uses_next_open_third_close_and_both_costs(self) -> None:
        """Phân biệt rõ Open(t+1), Close(t+3) với Close-to-Close."""
        frame = pd.DataFrame({"Open": [1., 100., 400., 900.], "Close": [500., 90., 800., 110.]})
        self.assertLessEqual(check_bridge(frame, 0, self.oracle), 1e-12)
        wrong = lambda *args: {**self.oracle(*args), "net_return": .1}
        with self.assertRaises(ValueError):
            check_bridge(frame, 0, wrong)

    def test_zero_net_is_down_and_missing_horizon_rejected(self) -> None:
        """Zero không UP; không rút ngắn horizon hoặc chấp nhận bool làm index."""
        frame = pd.DataFrame({"Open": [100.] * 4, "Close": [100.] * 4})
        oracle_zero = self.oracle(frame, 1, 3, fee=0, slippage=0)
        self.assertEqual((oracle_zero["net_return"], oracle_zero["label_net"]), (0., "DOWN"))
        self.assertLessEqual(check_bridge(frame, 0, self.oracle), 1e-12)
        for decision in (True, -1, 1):
            with self.assertRaises(ValueError):
                check_bridge(frame, decision, self.oracle)

    def test_news_frozen_scores_have_limited_pit_claim(self) -> None:
        """Không đồng nhất đúng hash scorer với archived publication content."""
        result = news_audit(self.news, self.scores, self.articles, self.bank)
        self.assertEqual((result["membership_count"], result["unique_scored_articles"]), (155, 154))
        self.assertFalse(result["content_pit_certified"])

    def test_undated_or_early_news_poison_stops(self) -> None:
        """Ngay cả khi reseal news hash, metadata tin sai vẫn phải ném lỗi."""
        for field, value in (("date_parsed", None), ("available_at", "2000-01-01"), ("numeric_score", 99.)):
            news = deepcopy(self.news)
            next(rows[0] for rows in news.values() if rows)[field] = value
            bank = {**self.bank, "news_hash": sha(json.dumps(news, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())}
            with self.assertRaises(ValueError):
                news_audit(news, self.scores, self.articles, bank)

    def test_archive_exact_recovery_and_missing_checkpoint(self) -> None:
        """Chỉ phục hồi đúng byte; thiếu candidate không được thay bằng replica."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / ARCHIVE).parent.mkdir(parents=True)
            data = b"teacher frozen bytes"
            with zipfile.ZipFile(root / ARCHIVE, "w") as archive:
                archive.writestr("prefix/model/teacher.json", data)
            release = {"artifact_trees": {"model": {"teacher.json": {"bytes": len(data), "sha256": sha(data)},
                                                   "candidate.pt": {"bytes": 2, "sha256": sha(b"pt")}}}}
            with patch("core.historical_asset_readiness.git", return_value=b""):
                result = frozen_assets(root, release, False)
                self.assertEqual((result["expected_files"], result["ready_files"]), (2, 1))
                self.assertEqual(result["files"][1]["status"], "BLOCKED_ASSET")
                self.assertEqual(frozen_assets(root, release, True), result)

    def test_local_asset_hash_mismatch_stops(self) -> None:
        """Không đánh dấu thiếu để che checkpoint local sai hash."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / ARCHIVE).parent.mkdir(parents=True)
            with zipfile.ZipFile(root / ARCHIVE, "w"):
                pass
            (root / "candidate.pt").write_bytes(b"wrong")
            release = {"artifact_trees": {".": {"candidate.pt": {"bytes": 2, "sha256": sha(b"pt")}}}}
            with patch("core.historical_asset_readiness.git", return_value=b""):
                with self.assertRaises(ValueError):
                    frozen_assets(root, release, False)

    def test_immutable_resume_verify_and_namespace(self) -> None:
        """Không ghi đè receipt, verify không tạo file, path traversal bị chặn."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path = destination(root, "manifests/example.json")
            preserve(path, b"one")
            preserve(path, b"one", verify=True)
            with self.assertRaises(ValueError):
                preserve(path, b"two")
            with self.assertRaises(ValueError):
                preserve(root / "missing", b"one", verify=True)
            self.assertFalse((root / "missing").exists())
            with self.assertRaises(ValueError):
                destination(root, "../../../outside")
            self.assertEqual(path.read_bytes(), b"one")

    def test_receipt_rejects_nonfinite_json(self) -> None:
        """Không phát hành receipt chứa NaN không đúng JSON chuẩn."""
        with self.assertRaises(ValueError):
            encode({"bad": float("nan")})


if __name__ == "__main__":
    unittest.main()
