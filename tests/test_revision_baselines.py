"""Kiểm thử R1: imbalance, undefined, replay độc lập và bảo toàn bằng chứng."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.backtest_engine import TestPoint, compute_account_metrics, compute_round_trip_net_return
from core.revision_audit import build_legacy_report, cycle_account_metrics, round_trip_net_return
from scripts.audit_revision_baselines import classification_csv, run_audit, verify_bundle
from utils.statistical_tests import binary_classification_metrics


def payload(symbol: str = "AAA", actuals: tuple[str, ...] = ("UP", "DOWN")) -> dict:
    """Fixture có overnight gap lớn để bắt lỗi dùng actual_prev_close làm entry."""
    points = []
    for index, actual in enumerate(actuals):
        entry = datetime(2024, 1, 2) + timedelta(days=index * 5)
        exit_price = 110.0 if actual == "UP" else 90.0
        points.append({
            "test_id": index + 1, "window_start": "2023-01-01",
            "window_end": (entry - timedelta(days=1)).date().isoformat(),
            "entry_time": entry.isoformat(), "exit_time": (entry + timedelta(days=2)).isoformat(),
            "entry_open": 100.0, "exit_close": exit_price,
            "actual_prev_close": 150.0, "actual_direction": actual,
            "pred_full": "LONG" if actual == "UP" else "SHORT",
            "pred_no_alpha": "SHORT", "correct_full": True,
            "correct_no_alpha": actual == "DOWN",
        })
    return {"symbol": symbol, "n_tests": len(points), "initial_capital_vnd": 1000.0,
            "test_points": points}


def write_payload(root: Path, data: dict) -> Path:
    """Ghi fixture riêng dưới root tạm để hash không phụ thuộc workspace tác giả."""
    path = root / "outputs/backtest_result" / f"backtest_{data['symbol']}_fixture.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class ClassificationMetricsTests(unittest.TestCase):
    def test_hand_calculated_imbalanced_confusion_and_per_class(self):
        result = binary_classification_metrics(
            ["UP", "UP", "DOWN", "DOWN", "DOWN"],
            ["LONG", "SHORT", "LONG", "SHORT", "SHORT"],
        )
        self.assertEqual(result["confusion"], {"tp": 1, "fn": 1, "tn": 2, "fp": 1})
        self.assertAlmostEqual(result["accuracy"], 3 / 5)
        self.assertAlmostEqual(result["balanced_accuracy"], (1 / 2 + 2 / 3) / 2)
        self.assertAlmostEqual(result["mcc"], 1 / 6)
        self.assertAlmostEqual(result["macro_f1"], (1 / 2 + 2 / 3) / 2)
        self.assertEqual(result["per_class"]["UP"]["support"], 2)
        self.assertAlmostEqual(result["per_class"]["DOWN"]["precision"], 2 / 3)

    def test_constant_cash_keeps_undefined_precision_and_mcc(self):
        result = binary_classification_metrics(["UP", "DOWN", "DOWN"], ["SHORT"] * 3)
        self.assertAlmostEqual(result["accuracy"], 2 / 3)
        self.assertEqual(result["balanced_accuracy"], 0.5)
        self.assertIsNone(result["mcc"])
        self.assertIsNone(result["per_class"]["UP"]["precision"])
        self.assertEqual(result["per_class"]["UP"]["recall"], 0.0)
        self.assertEqual(result["per_class"]["UP"]["f1"], 0.0)
        json.dumps(result, allow_nan=False)

    def test_absent_class_and_empty_support_are_not_perfect_ba(self):
        for actual, pred in ((["UP"], ["LONG"]), ([], [])):
            with self.subTest(actual=actual):
                result = binary_classification_metrics(actual, pred)
                self.assertIsNone(result["balanced_accuracy"])
                self.assertIsNone(result["macro_f1"])
                self.assertIsNone(result["mcc"])

    def test_unknown_is_counted_and_invalid_label_fails(self):
        result = binary_classification_metrics(["UP", "DOWN", "UNKNOWN"], ["LONG", "UNKNOWN", "SHORT"])
        self.assertEqual(result["n_input"], 3)
        self.assertEqual(result["n_valid"], 1)
        self.assertEqual(result["n_excluded"], 2)
        with self.assertRaises(ValueError):
            binary_classification_metrics(["UP"], ["CASH"])
        with self.assertRaises(ValueError):
            binary_classification_metrics(["UP"], [])


class CycleReplayTests(unittest.TestCase):
    def test_independent_formula_matches_engine_with_fees_both_sides(self):
        for fee, slip in ((0.0025, 0.001), (0.01, 0.02), (0.0, 0.0)):
            with self.subTest(fee=fee, slippage=slip):
                expected = 1.1 * (1 - fee) * (1 - slip) / ((1 + fee) * (1 + slip)) - 1
                self.assertAlmostEqual(round_trip_net_return(100, 110, fee, slip), expected)
                self.assertAlmostEqual(round_trip_net_return(100, 110, fee, slip),
                                       compute_round_trip_net_return(100, 110, fee, slip))

    def test_cycles_match_existing_ledger_without_mutating_input(self):
        source = payload(actuals=("UP", "DOWN", "UP"))["test_points"]
        original = deepcopy(source)
        replay = cycle_account_metrics(source, ["LONG", "SHORT", "LONG"], .01, .02, 1000)
        fields = []
        for p in source:
            fields.append(TestPoint(
                **p, actual_next_close=p["exit_close"], actual_pct_change=0,
                confidence_full="N/A", confidence_no_alpha="N/A", rr_full="N/A", rr_no_alpha="N/A",
                time_full_sec=0, time_no_alpha_sec=0))
        expected = compute_account_metrics(fields, fee=.01, slippage=.02,
                                           initial_capital_vnd=1000, price_multiplier=1)["full"]
        self.assertAlmostEqual(replay["net_return_pct"], expected.total_return_pct)
        self.assertEqual(replay["order_count"], 4)
        self.assertAlmostEqual(replay["brokerage_fee_vnd"], sum(p.transaction_fee_full_vnd for p in fields), places=3)
        self.assertAlmostEqual(replay["slippage_cost_vnd"], sum(p.slippage_cost_full_vnd for p in fields), places=3)
        self.assertEqual(source, original)
        self.assertIsNone(replay["daily_drawdown_pct"])

    def test_cash_zero_costs_and_failure_not_silently_cash(self):
        points = payload()["test_points"]
        cash = cycle_account_metrics(points, ["SHORT", "SHORT"], .01, .02, 1000)
        self.assertEqual(cash["net_return_pct"], 0.0)
        self.assertEqual(cash["brokerage_fee_vnd"], 0.0)
        self.assertEqual(cash["order_count"], 0)
        missing = cycle_account_metrics(points, ["LONG", "UNKNOWN"], .01, .02, 1000)
        self.assertEqual(missing["status"], "unavailable")
        self.assertIsNone(missing["net_return_pct"])

    def test_always_long_cycles_are_not_endpoint_buy_and_hold(self):
        points = payload(actuals=("UP", "UP"))["test_points"]
        replay = cycle_account_metrics(points, ["LONG", "LONG"], .01, 0, 1000)
        endpoint = round_trip_net_return(100, 110, .01, 0) * 100
        self.assertNotAlmostEqual(replay["net_return_pct"], endpoint)
        self.assertEqual(replay["order_count"], 4)

    def test_invalid_prices_and_costs_fail(self):
        for price in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                round_trip_net_return(price, 100, .01, 0)
        for fee, slip in ((-1, 0), (float("nan"), 0), (.5, .5)):
            with self.assertRaises(ValueError):
                round_trip_net_return(100, 110, fee, slip)

    def test_zero_net_return_is_down_and_gross_does_not_replace_net(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = payload(actuals=("DOWN",))
            data["test_points"][0]["exit_close"] = 100.0
            report = build_legacy_report([write_payload(root, data)], root, fee=0, slippage=0)
            self.assertEqual(report["pooled_classification"]["common_support"]["full"]["per_class"]["DOWN"]["support"], 1)
            # Giá tăng nhẹ nhưng lỗ sau phí vẫn là DOWN, không tự chuyển gross label.
            data["test_points"][0]["exit_close"] = 100.1
            report = build_legacy_report([write_payload(root, data)], root)
            self.assertEqual(report["pooled_classification"]["common_support"]["full"]["per_class"]["DOWN"]["support"], 1)


class AuditBundleTests(unittest.TestCase):
    def test_macro_differs_from_pooled_with_unequal_symbol_support(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = [write_payload(root, payload("AAA", ("UP",))),
                     write_payload(root, payload("BBB", ("DOWN", "DOWN", "DOWN")))]
            report = build_legacy_report(paths, root)
        cash = "constant_down_cash"
        self.assertEqual(report["pooled_classification"]["common_support"][cash]["accuracy"], .75)
        self.assertEqual(report["macro_over_symbols"][cash]["accuracy"]["mean"], .5)
        self.assertIsNone(report["macro_over_symbols"][cash]["balanced_accuracy"]["mean"])

    def test_groups_use_only_provided_metadata_and_common_support_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = payload()
            data["fold"] = "outer_1"
            data["test_points"][0]["regime"] = "known_at_cutoff"
            data["test_points"][0]["pred_full"] = "UNKNOWN"
            report = build_legacy_report([write_payload(root, data)], root)
        self.assertEqual(report["missing_group_fields"], ["repeat_id"])
        self.assertEqual(report["pooled_classification"]["n_common_support"], 1)
        self.assertEqual(report["pooled_classification"]["own_support"]["full"]["n_excluded"], 1)
        self.assertEqual(report["per_symbol"]["AAA"]["economics"]["full"]["status"], "unavailable")
        self.assertIn("NA", classification_csv(report))
        self.assertEqual({g["dimension"] for g in report["groups"]}, {"fold", "regime"})

    def test_rejects_missing_canonical_prices_bad_labels_duplicate_or_overlapping_cutoffs(self):
        mutations = [
            lambda d: d["test_points"][0].pop("entry_open"),
            lambda d: d["test_points"][0].update(actual_direction="DOWN"),
            lambda d: d["test_points"][1].update(test_id=1),
            lambda d: d["test_points"][1].update(entry_time=d["test_points"][0]["exit_time"]),
            lambda d: d["test_points"][0].update(entry_time=d["test_points"][0]["window_end"]),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                data = payload()
                mutation(data)
                with self.assertRaises((ValueError, KeyError)):
                    build_legacy_report([write_payload(root, data)], root)

    def test_bundle_hashes_detect_source_and_output_tampering_and_prevent_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = write_payload(root, payload())
            unrelated = root / "outputs/bayesian_benchmark/other.json"
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text("{}", encoding="utf-8")
            source_bytes = path.read_bytes()
            output = root / "outputs/revision/test"
            run_audit(path.parent, output, ["AAA"], root)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertNotIn("outputs/bayesian_benchmark/other.json", [s["path"] for s in manifest["sources"]])
            self.assertIn("paper/main.pdf", manifest["missing_expected_sources"])
            self.assertGreater(verify_bundle(output, root), 4)
            with self.assertRaises(FileExistsError):
                run_audit(path.parent, output, ["AAA"], root)
            path.write_bytes(source_bytes + b" ")
            with self.assertRaises(ValueError):
                verify_bundle(output, root)
            path.write_bytes(source_bytes)
            (output / "report.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_bundle(output, root)

    def test_multiple_candidate_results_fail_instead_of_picking_latest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = write_payload(root, payload())
            path.with_name("backtest_AAA_other.json").write_bytes(path.read_bytes())
            with self.assertRaises(ValueError):
                run_audit(path.parent, root / "new", ["AAA"], root)

    def test_frozen_180_points_reproduce_independent_imbalance_counts(self):
        root = Path(__file__).resolve().parents[1]
        report = build_legacy_report(sorted((root / "outputs/backtest_result").glob("*.json")), root)
        pooled = report["pooled_classification"]["common_support"]
        self.assertEqual(report["n_symbols"], 9)
        self.assertEqual(report["n_points"], 180)
        self.assertEqual(pooled["full"]["confusion"], {"tp": 16, "fn": 40, "tn": 101, "fp": 23})
        self.assertEqual(pooled["base_reports_legacy"]["confusion"], {"tp": 15, "fn": 41, "tn": 77, "fp": 47})
        self.assertAlmostEqual(pooled["constant_down_cash"]["accuracy"], 124 / 180)
        self.assertEqual(pooled["constant_down_cash"]["balanced_accuracy"], .5)
        self.assertEqual(report["legacy_discrepancies"], [])
        # Đối chiếu thêm vốn cuối đã lưu, không lấy mean các % đã làm tròn làm oracle.
        stored = [json.loads(path.read_bytes()) for path in (root / "outputs/backtest_result").glob("*.json")]
        equity_mean = sum((p["equity_full_vnd"] / p["initial_capital_vnd"] - 1) * 100 for p in stored) / 9
        self.assertAlmostEqual(report["mean_independent_account_return_pct"]["full"], equity_mean, places=6)
        self.assertEqual(round(report["mean_independent_account_return_pct"]["full"], 2), -1.68)
        self.assertEqual(round(report["mean_stored_rounded_account_return_pct"]["full"], 2), -1.69)
        json.dumps(report, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
