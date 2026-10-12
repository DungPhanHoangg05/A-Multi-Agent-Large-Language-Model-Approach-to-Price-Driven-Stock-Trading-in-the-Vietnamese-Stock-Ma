"""Giao thức đo/verify offline và tính toàn vẹn bản sao JSON của API prior."""

from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from core import prior_performance as performance
from core.prior_config import copy_prior_json
from core.research_cohort import read_envelope


class PriorJsonCopyTests(unittest.TestCase):
    """Tối ưu sao chép phải giữ ownership, alias và kiểm kiểu JSON nguyên bản."""

    def test_nested_copy_matches_deepcopy_and_preserves_internal_aliases(self) -> None:
        shared = [{"signals": [True, None, 3, .5, "tăng"]}]
        original = {"left": shared, "right": shared, "empty": {}}
        actual = copy_prior_json(original)
        self.assertEqual(actual, deepcopy(original))
        self.assertIs(actual["left"], actual["right"])
        self.assertIsNot(actual["left"], original["left"])
        actual["left"][0]["signals"].append("đổi")
        self.assertEqual(len(original["left"][0]["signals"]), 5)

    def test_invalid_nested_json_types_and_cycles_are_rejected(self) -> None:
        class StringSubclass(str):
            """Key kế thừa str vẫn không phải kiểu Python gốc đã khóa."""
        cycle = []
        cycle.append(cycle)
        for invalid in (np.int64(1), np.float64(.5), np.bool_(True), float("nan"), float("inf"),
                        (1, 2), {StringSubclass("key"): 1}, cycle):
            with self.subTest(value=type(invalid).__name__), self.assertRaises(ValueError):
                copy_prior_json({"nested": [invalid]})


class PriorPerformanceProtocolTests(unittest.TestCase):
    """Không chạy phép đo wall-clock trong unit test và không cần artifact thật."""

    def test_hot_guard_rejects_file_network_key_and_fit(self) -> None:
        import socket
        import dotenv
        from sklearn.preprocessing import StandardScaler
        with performance.hot_guard():
            for operation in (lambda:Path("unused").read_bytes(), lambda:open("unused"),
                              lambda:socket.getaddrinfo("unused", 443), dotenv.load_dotenv,
                              lambda:StandardScaler().fit([[1.], [2.]])):
                with self.subTest(operation=operation), self.assertRaises(AssertionError):
                    operation()
            self.assertEqual(copy_prior_json({"x": [1, .2]}), {"x": [1, .2]})

    def test_complete_train_roster_is_required_and_sorted_without_latency_filter(self) -> None:
        records = [{"episode_id": f"e{i}", "symbol": "FPT", "as_of_date": (date(2021, 1, 1)+timedelta(days=i)).isoformat(),
                    "regime": "SIDEWAYS"} for i in range(651)]
        train = {"report_version": "train_pit_diagnostics_v1", "status": "COMPLETE", "query_count": 651,
            "registry": performance.registry(), "points": list(reversed(deepcopy(records))),
            "folds": {"train": {"symbols": {"FPT": {"query_ids": [r["episode_id"] for r in records]}}}},
            "regime_fits": {r["as_of_date"]: {"train_end_date": r["as_of_date"]} for r in records}}
        self.assertEqual(performance.train_contexts(train, records), records)
        changes = (lambda d:d["points"].pop(), lambda d:d["points"][0].update(symbol="MWG"),
                   lambda d:d["folds"]["train"]["symbols"]["FPT"]["query_ids"].pop(),
                   lambda d:d["regime_fits"][records[0]["as_of_date"]].update(train_end_date="2099-01-01"))
        for change in changes:
            changed = deepcopy(train)
            change(changed)
            with self.assertRaises(ValueError):
                performance.train_contexts(changed, records)

    def test_fail_report_is_immutable_and_verify_never_measures_or_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.object(performance, "ROOT", Path(directory)):
            path = Path(directory)/"outputs/bayesian_benchmark/failure.json"
            expected = {"report_version": performance.VERSION, "status": "FAIL"}
            with patch.object(performance, "benchmark", return_value=expected) as measure:
                self.assertEqual(performance.run_performance(path), expected)
                self.assertEqual(read_envelope(path), expected)
                before = path.read_bytes()
                with self.assertRaises(ValueError):
                    performance.run_performance(path)
                measure.assert_called_once_with()
            with patch.object(performance, "benchmark", side_effect=AssertionError("Không đo lại")), \
                 patch.object(performance, "_write_once", side_effect=AssertionError("Không ghi verify")), \
                 patch.object(performance, "verify_report") as verify:
                self.assertEqual(performance.run_performance(path, verify_only=True), expected)
                verify.assert_called_once_with(expected)
            self.assertEqual(path.read_bytes(), before)
            for wrong in (Path(directory)/"outside.json", path.parent/"report.txt", path.parent/".env.json"):
                with self.assertRaises(ValueError):
                    performance.run_performance(wrong)

    def test_performance_cli_dispatches_before_key_and_rejects_unrelated_flags(self) -> None:
        from scripts import run_bayesian_ablation as cli
        with patch.object(cli, "dotenv_values", side_effect=AssertionError("Cấm key")), \
             patch("socket.socket.connect", side_effect=AssertionError("Cấm mạng")), \
             patch.object(performance, "run_performance", return_value={"status": "PASS"}) as run:
            for mode in ("--benchmark-prior", "--verify-performance"):
                with patch("sys.argv", ["runner", mode]):
                    cli.main()
                self.assertEqual(run.call_args.kwargs["verify_only"], mode == "--verify-performance")
            for arguments in (["--benchmark-prior", "--symbol", "FPT"], ["--verify-performance", "--resume"],
                              ["--performance-report", "unused.json"]):
                before = run.call_count
                with patch("sys.argv", ["runner", *arguments]), self.assertRaises(SystemExit):
                    cli.main()
                self.assertEqual(run.call_count, before)

    def test_report_rejects_forged_raw_percentile_gate_and_method_before_source_load(self) -> None:
        stage = {"samples_ns": [1]*1000, "summary": performance.summarize([1]*1000)}
        report = {"report_version": performance.VERSION, "runtime": {}, "code_sha256": {},
            "method": {"warmup": 100, "samples": 1000, "threshold_ns": performance.THRESHOLD_NS,
                       "percentile": "nearest_rank_ceil_0.95_n", "scope": "same_symbol", "k": 3, "seed": 42,
                       "query_rotation": "sample_index % 651; reset sau warm-up"}, "feature_extraction": stage,
            "modes": {name: {"stages": {key:deepcopy(stage) for key in performance.STAGES}, "gate_passed": True}
                      for name in ("v1_train_same_symbol", *performance.registry()["order"])},
            "legacy": {"status": "PASS", "modes": {name: {"gate_passed": True,
                **{key:deepcopy(stage) for key in ("retrieval", "formatter", "retrieval_and_format")}}
                for name in ("bayesian_regime", "random", "recent", "similarity")}}}
        changes = (lambda d:d["feature_extraction"]["samples_ns"].pop(),
                   lambda d:d["feature_extraction"]["summary"].update(p95_ns=0),
                   lambda d:d["modes"]["C0"].update(gate_passed=False),
                   lambda d:d["method"].update(threshold_ns=performance.THRESHOLD_NS+1),
                   lambda d:d["method"].update(scope="pooled"), lambda d:d["method"].update(seed=1),
                   lambda d:d["method"].update(k=1), lambda d:d["modes"].pop("C3"),
                   lambda d:d["modes"]["C0"].update(gate_passed=1),
                   lambda d:d["feature_extraction"]["summary"].update(p95_ns=1.),
                   lambda d:d["legacy"]["modes"].pop("similarity"))
        with patch.object(performance, "runtime_identity", return_value={}), \
             patch.object(performance, "code_identity", return_value={}), \
             patch.object(performance, "PerformanceInputs", side_effect=AssertionError("Không nạp nguồn trước kiểm số đo")):
            for change in changes:
                changed = deepcopy(report)
                change(changed)
                with self.assertRaises(ValueError):
                    performance.verify_report(changed)
