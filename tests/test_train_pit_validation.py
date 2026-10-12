"""Kiểm purge/scaler, mẫu số, stability và report/CLI train offline."""

from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core.price_feature_index import build_price_feature_index
from core.research_input_lock import _write_once
from core.train_pit_validation import _candidate, diagnostic_summary, fold_schedule, run_train_validation, verify_regime_fit
from price_feature_index_support import index_inputs
from train_pit_support import regime_fixture
import test_prior_quality_gate as gate_support


class TrainValidationTests(unittest.TestCase):
    def test_fold_denominators_purge_actual_exit_and_unavailable_scaler(self) -> None:
        inputs = index_inputs()
        index = build_price_feature_index(**inputs)
        records = deepcopy(inputs["records"])
        for row in records:
            row["entry_date"] = inputs["calendar"][inputs["calendar"].get_loc(row["as_of_date"])+1].strftime("%Y-%m-%d")
        folds = fold_schedule(records, index, inputs["calendar"])
        early, late = (folds[name]["symbols"]["FPT"] for name in ("train_2021", "train_2022"))
        self.assertEqual(early["purged_ids"], ["FPT:2020-12-30"])
        self.assertEqual(late["purged_ids"], ["FPT:2022-01-03"])
        self.assertEqual([len(early["fit_ids"]), len(early["feature_fit_ids"])], [4, 3])
        self.assertEqual(folds["train_2021"]["symbols"]["VNM"]["scaler"]["status"], "SCALER_UNAVAILABLE")
        self.assertTrue(set(early["fit_ids"]).isdisjoint(early["query_ids"]))
        self.assertEqual(folds["train_2021"]["extra_embargo_sessions"], 0)

    def test_real_evidence_views_summary_missing_support_and_jaccard(self) -> None:
        fx = gate_support.populated_fixture()
        self.addCleanup(fx.close)
        evidence = fx.retriever.quality_evidence(**gate_support.gate_query(fx))
        before = deepcopy(evidence)
        full, stats, examples = (_candidate(evidence, name) for name in ("C3", "C3_stats_only", "C3_examples_only"))
        self.assertEqual(full["selected_ids"], stats["selected_ids"])
        self.assertEqual(stats["visible_ids"], [])
        self.assertTrue(stats["stats_ready"])
        self.assertFalse(examples["stats_ready"])
        full.update(selection_gap_sessions=[4], selection_exclusions={"LOW_SIMILARITY": 2})
        row = {"fold_id": "train_2021", "symbol": "FPT", "regime": "BULL", "feature_status": "AVAILABLE",
            "candidates": {"C3": full}}
        result = diagnostic_summary([row, deepcopy(row)], ["C3"])
        observed = next(r for r in result if r["query_count"])
        self.assertEqual(observed["query_count"], 2)
        self.assertEqual(observed["selection_jaccard_consecutive_same_group"]["mean"], 1.)
        self.assertEqual(observed["selection_gap_sessions"]["mean"], 4.)
        self.assertEqual(observed["selection_exclusion_counts"], {"LOW_SIMILARITY": 4})
        self.assertEqual(observed["metrics"]["pattern_false_bullish_rate"]["interval_width"]["missing"], 2)
        self.assertTrue(any(r["status"] == "NO_EXPOSURE" and r["population"]["mean"] is None for r in result))
        json.dumps(result, allow_nan=False)
        self.assertEqual(before, evidence)

    def test_recomputed_scaler_and_calibration_reject_numerical_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter, point = regime_fixture(root)
            self.assertTrue(verify_regime_fit(adapter, point)["scaler_calibration_recomputed"])
            original = (root/"model.json").read_text("utf-8")
            payload = json.loads(original)
            payload["payload"]["scaler"]["mean"][0] += .01
            (root/"model.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Scaler HMM"):
                verify_regime_fit(adapter, point)
            (root/"model.json").write_text(original, encoding="utf-8")
            point.source_provenance["regime"]["metadata"]["trend_threshold"] += .1
            with self.assertRaisesRegex(ValueError, "Calibration"):
                verify_regime_fit(adapter, point)

    def test_report_verify_rebuilds_semantics_rejects_rehashed_edit_and_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root/"outputs/bayesian_benchmark/train.json"
            index_path = "outputs/bayesian_benchmark/price_features/index.json"
            (root/index_path).parent.mkdir(parents=True)
            (root/index_path).write_text("index", encoding="utf-8")
            adapter = SimpleNamespace(_files=SimpleNamespace(root=root, path=lambda name:root/name, pin=lambda name:None),
                load_price_feature_index=lambda name:object())
            payload = {"query_count": 3, "decision_calls": 0}
            _write_once(report_path, payload)
            original = report_path.read_bytes()
            with patch("core.train_pit_validation.PriorContextAdapter", return_value=adapter), patch(
                    "core.train_pit_validation.build_train_diagnostics", return_value=payload) as build:
                self.assertEqual(run_train_validation(report_path, index_path=index_path, verify_only=True), payload)
                build.assert_called_once()
                self.assertEqual(report_path.read_bytes(), original)
                report_path.unlink()
                _write_once(report_path, {**payload, "query_count": 99})
                with self.assertRaisesRegex(ValueError, "Report train khác"):
                    run_train_validation(report_path, index_path=index_path, verify_only=True)
                with self.assertRaisesRegex(ValueError, "Index train"):
                    run_train_validation(report_path, index_path="outputs/historical_memory_run/model.json")

    def test_cli_offline_dispatch_and_reject_unrelated_modes_without_keys_or_network(self) -> None:
        import scripts.run_bayesian_ablation as cli
        with patch.object(socket.socket, "connect", side_effect=AssertionError("Cấm mạng")), patch.object(
                cli, "dotenv_values", side_effect=AssertionError("Cấm key")), patch(
                "core.train_pit_validation.run_train_validation", return_value={"replayed_count": 4, "query_count": 3}) as run:
            for flag in ("--validate-train", "--verify-train"):
                with patch("sys.argv", ["runner", flag]), redirect_stdout(StringIO()):
                    cli.main()
                self.assertEqual(run.call_args.kwargs["verify_only"], flag == "--verify-train")
            for flags in (("--validate-train", "--resume"), ("--train-report", "report.json"),
                          ("--validate-train", "--preflight")):
                with patch("sys.argv", ["runner", *flags]), self.assertRaises(SystemExit):
                    cli.main()

    def test_missing_provenance_never_writes_pass_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)/"report.json"
            with patch("core.train_pit_validation.PriorContextAdapter", side_effect=ValueError("Thiếu provenance")):
                with self.assertRaisesRegex(ValueError, "provenance"):
                    run_train_validation(destination)
            self.assertFalse(destination.exists())
