"""Hợp đồng số, tính toàn vẹn và cache của scaler/index; không dùng API."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from core.pit_price_features import extract_pit_price_features
from core.price_feature_index import (
    PriceFeatureIndex, _fit, _hash, build_price_feature_index,
    load_price_feature_index, save_price_feature_index,
)
from price_feature_index_support import index_inputs
from prior_context_test_support import ContextFixture


class PriceFeatureIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = index_inputs()
        cls.index = build_price_feature_index(**cls.inputs)

    def features(self, symbol: str = "FPT", cutoff: str = "2021-01-04") -> dict:
        frame, events = self.inputs["prices"][symbol]
        return extract_pit_price_features(frame, events, self.inputs["calendar"], cutoff,
                                          source=self.inputs["source"])

    def test_manual_population_variance_zero_dimension_and_two_sample_minimum(self) -> None:
        rows = [{"episode_id": str(i), "symbol": "FPT", "exit_date": f"2020-06-0{i + 1}",
                 "features": {"status": "AVAILABLE", "vector": [value, 5., value * 2, 0.]}}
                for i, value in enumerate((1., 3.))]
        scaler = _fit(rows, "FPT", {"fit_cutoff": "2021-01-04", "fit_inclusive": False,
                                    "freeze_date": "2021-01-04"})
        self.assertEqual(scaler["mean"], [2., 5., 4., 0.])
        self.assertEqual(scaler["variance"], [1., 0., 4., 0.])
        self.assertEqual(scaler["scale"], [1., 1., 2., 1.])
        self.assertEqual(scaler["zero_variance"], [False, True, False, True])
        self.assertEqual(((np.array([4., 7., 8., 2.]) - scaler["mean"]) / scaler["scale"]).tolist(),
                         [2., 2., 2., 2.])
        with self.assertRaises(ValueError):
            _fit([{**row, "features": {"status": "AVAILABLE", "vector": [1e308] * 4}}
                  for row in rows], "FPT", {"fit_cutoff": "2021-01-04", "fit_inclusive": False,
                                            "freeze_date": "2021-01-04"})

    def test_frozen_fit_counts_ids_purge_and_oos_cutoff(self) -> None:
        early = self.index.scaler("FPT", "2021-01-04")
        later = self.index.scaler("FPT", "2022-01-06")
        oos = self.index.scaler("FPT", "2023-01-03")
        self.assertEqual([early["fit_count"], later["fit_count"], oos["fit_count"]], [3, 6, 9])
        self.assertNotIn("FPT:2020-12-30", early["fit_episode_ids"])
        self.assertNotIn("FPT:2022-01-03", later["fit_episode_ids"])
        self.assertIn("FPT:2022-12-27", oos["fit_episode_ids"])
        self.assertNotIn("FPT:2020-06-12", oos["fit_episode_ids"])
        self.assertEqual(oos["freeze_date"], "2022-12-31")
        self.assertEqual(oos["fit_max_exit_date"], "2022-12-30")
        self.assertEqual(early, self.index.scaler("FPT", "2021-12-31"))
        self.assertEqual(oos, self.index.scaler("FPT", "2024-12-31"))

    def test_same_query_scaler_for_query_and_priors_no_clipping(self) -> None:
        feature = self.features()
        scaler = self.index.scaler("FPT", "2021-01-04")
        actual = self.index.transform_query("FPT", "2021-01-04", feature)
        expected = (np.array(feature["vector"]) - scaler["mean"]) / scaler["scale"]
        np.testing.assert_array_equal(actual["scaled_vector"], expected)
        ids = self.index.closed_episode_ids("FPT", "2022-01-06")
        selected = self.index.prior_features("FPT", "2022-01-06", ids)
        later = self.index.scaler("FPT", "2022-01-06")
        raw = {row["episode_id"]: row["features"] for row in self.index.payload["records"]}
        for row in selected:
            if row["feature_status"] == "AVAILABLE":
                np.testing.assert_array_equal(row["scaled_vector"],
                    (np.array(raw[row["episode_id"]]["vector"]) - later["mean"]) / later["scale"])
            self.assertEqual(row["fold_id"], "train_2022")
        feature["vector"] = [999.] * 4
        self.assertGreater(max(self.index.transform_query("FPT", "2021-01-04", feature)["scaled_vector"]), 10.)

    def test_constant_prices_are_valid_and_symbols_do_not_borrow_scalers(self) -> None:
        scaler = self.index.scaler("VCB", "2021-01-04")
        self.assertEqual(scaler["mean"], [0.] * 4)
        self.assertEqual(scaler["scale"], [1.] * 4)
        self.assertEqual(scaler["zero_variance"], [True] * 4)
        unavailable = self.index.scaler("VNM", "2021-01-04")
        self.assertEqual(unavailable["status"], "SCALER_UNAVAILABLE")
        self.assertEqual(unavailable["fit_count"], 1)
        self.assertEqual(unavailable["fit_episode_ids"], ["VNM:2020-06-01"])
        result = self.index.transform_query("VNM", "2021-01-04", self.features("VNM"))
        self.assertEqual(result["feature_status"], "AVAILABLE")
        self.assertEqual(result["status"], "SCALER_UNAVAILABLE")
        self.assertIsNone(result["scaled_vector"])

    def test_unavailable_feature_kept_in_population_not_fit(self) -> None:
        key = "FPT:2020-06-12"
        self.assertIn(key, self.index.closed_episode_ids("FPT", "2021-01-04"))
        result = self.index.prior_features("FPT", "2021-01-04", [key])[0]
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIsNone(result["raw_vector"])
        self.assertIsNone(result["scaled_vector"])
        self.assertEqual(result["feature_reasons"], ["CORPORATE_ACTION_WINDOW"])
        frame, _ = self.inputs["prices"]["FPT"]
        # Nhiều sự kiện quyền cùng phiên là chứng cứ hợp lệ từ nguồn VCI.
        query = extract_pit_price_features(frame, [{"exrightDate": "2021-01-04"}] * 2,
            self.inputs["calendar"], "2021-01-04", source=self.inputs["source"])
        result = self.index.transform_query("FPT", "2021-01-04", query)
        self.assertEqual(result["status"], "UNAVAILABLE")

    def test_wrong_fold_symbol_dates_and_ids_fail_loudly(self) -> None:
        for symbol, day, fold in (("FPT", "2021-01-04", "train_2022"),
                                  ("FPT", "2022-01-06", "train_2021"),
                                  ("FPT", "2020-12-31", None), ("FPT", "2022-01-04", None),
                                  ("VNINDEX", "2021-01-04", None), ("FPT", "20210104", None),
                                  ("FPT", "2025-01-01", None)):
            with self.subTest(symbol=symbol, day=day), self.assertRaises(ValueError):
                self.index.scaler(symbol, day, fold_id=fold)
        for ids in (["missing"], ["MWG:2020-06-01"], ["FPT:2020-06-01"] * 2,
                    [None], "FPT:2020-06-01"):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.index.prior_features("FPT", "2021-01-04", ids)

    def test_query_version_source_nonfinite_dimension_and_cutoff_errors(self) -> None:
        changes = ({"feature_version": "bad"}, {"price_policy_version": "bad"},
                   {"feature_columns": []}, {"source": {}}, {"symbol": "MWG"},
                   {"as_of_date": "2021-01-05"}, {"feature_end_date": "2022-01-04"},
                   {"vector": [1.] * 3}, {"vector": [True] * 4}, {"vector": [np.nan] * 4},
                   {"vector": [np.float64(1.)] * 4}, {"coverage": {}}, {"status": "missing"},
                   {"outcome": "WIN"},
                   {"status": "UNAVAILABLE", "vector": None, "reasons": []})
        for change in changes:
            with self.subTest(change=str(change)), self.assertRaises(ValueError):
                self.index.transform_query("FPT", "2021-01-04", {**self.features(), **change})

    def test_determinism_owned_results_and_no_outcome(self) -> None:
        inputs = deepcopy(self.inputs)
        inputs["records"].reverse()
        other = build_price_feature_index(**inputs)
        self.assertEqual(self.index.identity, other.identity)
        before = self.index.identity
        payload = self.index.payload
        payload["records"][0]["features"]["vector"][0] = 999.
        payload["scalers"]["train_2021"]["FPT"]["mean"][0] = 999.
        selected = self.index.prior_features("FPT", "2021-01-04", ["FPT:2020-06-01"])
        selected[0]["scaled_vector"][0] = 999.
        self.assertEqual(self.index.identity, before)
        self.assertEqual(self.index.payload, other.payload)
        encoded = json.dumps(self.index.payload, allow_nan=False)
        for forbidden in ("outcome", "net_return", "entry_open", "exit_close", "agent_signals"):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(self.inputs["records"], inputs["records"][::-1])
        with self.assertRaises(ValueError):
            PriceFeatureIndex({}, _verified=None)

    def test_producer_rejects_duplicate_missing_future_bad_source_and_labels(self) -> None:
        bad_rows = [self.inputs["records"] + self.inputs["records"][:1],
                    [{**self.inputs["records"][0], "episode_id": ""}],
                    [{**self.inputs["records"][0], "outcome": "WIN"}],
                    [{**self.inputs["records"][0], "exit_date": "2023-01-03"}],
                    [{**self.inputs["records"][0], "symbol": "VNINDEX"}]]
        for records in bad_rows:
            with self.subTest(records=str(records)[:80]), self.assertRaises(ValueError):
                build_price_feature_index(**{**self.inputs, "records": records})
        for source in ({}, {**self.inputs["source"], "price_unit": "VND"}):
            with self.assertRaises(ValueError):
                build_price_feature_index(**{**self.inputs, "source": source})
        with self.assertRaises(ValueError):
            build_price_feature_index(**{**self.inputs, "provenance": {}})

    def test_round_trip_byte_hash_write_once_and_semantic_rehashed_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            checksum = save_price_feature_index(self.index, path)
            self.assertEqual(checksum, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(save_price_feature_index(self.index, path), checksum)
            self.assertEqual(load_price_feature_index(path, expected_sha256=checksum, **self.inputs).payload,
                             self.index.payload)
            with self.assertRaises(ValueError):
                load_price_feature_index(path, expected_sha256="0" * 64, **self.inputs)
            original = json.loads(path.read_text("utf-8"))
            def change_vector(payload: dict) -> None:
                payload["records"][0]["features"]["vector"][0] += .001
            def remove_row(payload: dict) -> None:
                payload["records"].pop()
            def duplicate_row(payload: dict) -> None:
                payload["records"].append(payload["records"][0])
            def change_scaler(payload: dict) -> None:
                payload["scalers"]["train_2021"]["FPT"]["mean"][0] += .001
            def fake_unavailable(payload: dict) -> None:
                payload["scalers"]["train_2021"]["FPT"].update(status="SCALER_UNAVAILABLE", fit_count=1)
            def remove_fit_id(payload: dict) -> None:
                payload["scalers"]["train_2021"]["FPT"]["fit_episode_ids"].pop()
            def change_source(payload: dict) -> None:
                payload["provenance"]["prices"]["FPT"]["csv_sha256"] = "d" * 64
            def change_code(payload: dict) -> None:
                payload["runtime"]["code_sha256"]["core/price_feature_index.py"] = "d" * 64
            for mutate in (change_vector, remove_row, duplicate_row, change_scaler,
                           fake_unavailable, remove_fit_id, change_source, change_code):
                envelope = deepcopy(original)
                mutate(envelope["payload"])
                envelope["sha256"] = _hash(envelope["payload"])
                path.write_text(json.dumps(envelope), encoding="utf-8")
                with self.subTest(mutate=mutate.__name__), self.assertRaises(ValueError):
                    load_price_feature_index(path, **self.inputs)
                with self.assertRaises(ValueError):
                    save_price_feature_index(self.index, path)
            path.write_text('{"payload": {}, "payload": {}, "sha256": "x"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_price_feature_index(path, **self.inputs)
            path.write_text('{"payload": {"x": NaN}, "sha256": "x"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_price_feature_index(path, **self.inputs)
            with self.assertRaises(FileNotFoundError):
                load_price_feature_index(path.parent / "missing.json", **self.inputs)

    def test_hot_queries_no_io_extraction_fit_or_source_verification(self) -> None:
        feature = self.features()
        with (patch.object(Path, "read_bytes", side_effect=AssertionError("Cấm I/O")),
              patch.object(Path, "read_text", side_effect=AssertionError("Cấm I/O")),
              patch("core.price_feature_index._fit", side_effect=AssertionError("Cấm refit")),
              patch("core.price_feature_index.extract_pit_price_features", side_effect=AssertionError("Cấm trích lại")),
              patch.object(self.index, "verify_query_sources", side_effect=AssertionError("Chỉ kiểm trước loop"))):
            for _ in range(10):
                self.index.scaler("FPT", "2021-01-04")
                ids = self.index.closed_episode_ids("FPT", "2021-01-04")
                self.index.prior_features("FPT", "2021-01-04", ids)
                self.index.transform_query("FPT", "2021-01-04", feature)


class PriceFeatureIndexAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = ContextFixture()
        self.addCleanup(self.fx.close)

    def test_public_build_load_does_not_touch_bank_state_or_evaluator(self) -> None:
        adapter = self.fx.adapter()
        records = deepcopy(self.fx.records)
        point = adapter.prepare("FPT", self.fx.cutoff)
        full = point.bind_full(self.fx.full(point))
        prior = point.retrieve(full)
        before = adapter.source_hashes
        with patch.object(adapter, "execution_data", side_effect=AssertionError("Cấm evaluator")):
            built = adapter.build_price_feature_index()
            loaded = adapter.load_price_feature_index()
        self.assertEqual(built.identity, loaded.identity)
        self.assertEqual(adapter.source_hashes, before)
        self.assertEqual(self.fx.records, records)
        self.assertEqual(point.retrieve(full), prior)
        with self.assertRaises(ValueError):
            point.scaled_price_features(loaded)  # Điểm fixture 2020 chỉ bootstrap.
        self.assertNotIn("price_features", full)

    def test_production_source_tamper_fails_before_producer_or_loader(self) -> None:
        adapter = self.fx.adapter()
        adapter.build_price_feature_index()
        path = self.fx.root / "data/execution_prices/FPT.events.json"
        path.write_bytes(path.read_bytes() + b" ")
        with patch("core.price_feature_index.build_price_feature_index") as producer:
            with self.assertRaises(ValueError):
                adapter.build_price_feature_index()
            with self.assertRaises(ValueError):
                adapter.load_price_feature_index()
            producer.assert_not_called()

    def test_query_adapter_uses_verified_extractor_and_binds_index_once(self) -> None:
        adapter = self.fx.adapter()
        index = adapter.build_price_feature_index()
        adapter._price_index_bindings.clear()
        with (patch.object(index, "verify_query_sources", wraps=index.verify_query_sources) as bind,
              patch.object(index, "transform_query", wraps=index.transform_query) as transform):
            for _ in range(2):
                with self.assertRaises(ValueError):
                    adapter.scaled_price_features(index, "FPT", self.fx.cutoff)
            self.assertEqual(bind.call_count, 1)
            self.assertEqual(transform.call_count, 2)
            self.assertEqual(transform.call_args.args[2], adapter.price_features("FPT", self.fx.cutoff))
        with self.assertRaises(ValueError):
            adapter.build_price_feature_index("../outside.json")
