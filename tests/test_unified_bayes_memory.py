"""Kiểm nhập upstream, economic label, dedup, source và scaler U-BICL."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core.price_feature_index import build_price_feature_index
from core.research_cohort import save_envelope
from core.unified_bayes_memory import build_memory, load_memory, save_memory
from unified_memory_test_support import memory_inputs, upstream


class UnifiedMemoryTests(unittest.TestCase):
    """Dùng nguồn tổng hợp để kiểm hợp đồng, không gọi API hoặc mở Decision."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = memory_inputs()
        cls.memory = build_memory(**cls.inputs)

    def test_union_labels_use_engine_and_original_stays_equal(self) -> None:
        """LONG dùng Open(t+1)/Close(t+3), nguyên nhãn và tín hiệu bank gốc."""
        payload = self.memory.payload
        self.assertEqual(payload["counts"]["total"], 32)
        self.assertEqual(payload["counts"]["imported"], 8)
        records = {row["episode_id"]: row for row in payload["records"]}
        for row in self.inputs["original"]:
            self.assertEqual(records[row["episode_id"]], row)
        row = records["FPT:2023-01-03"]
        frame = self.inputs["prices"]["FPT"][0].set_index("Datetime")
        expected = float(compute_round_trip_net_return(frame.loc[row["entry_date"], "Open"],
                                                       frame.loc[row["exit_date"], "Close"]) * 100.)
        self.assertEqual(row["outcome"]["net_return_pct"], expected)
        self.assertIs(payload["confirmation_allowed"], False)
        json.dumps(payload, allow_nan=False)

    def test_identical_id_and_cycle_are_deduplicated_with_reasons(self) -> None:
        """Không cộng support hai lần vì hai nguồn chỉ cùng một cycle."""
        inputs = deepcopy(self.inputs)
        same = deepcopy(inputs["imported"][0])
        inputs["imported"] += [same, {**deepcopy(same), "episode_id": "other-source-id"}]
        memory = build_memory(**inputs)
        self.assertEqual(memory.payload["counts"]["total"], 32)
        self.assertEqual({r["reason"] for r in memory.payload["excluded"]},
                         {"DUPLICATE_EPISODE_ID", "DUPLICATE_CYCLE"})

    def test_conflicting_duplicate_is_integrity_error(self) -> None:
        """ID/cycle giống nhau nhưng khác tín hiệu phải dừng, không chọn bản thuận lợi."""
        inputs = deepcopy(self.inputs)
        same = deepcopy(inputs["imported"][0])
        same["agent_signals"]["trend"] = "BEARISH"
        inputs["imported"].append(same)
        with self.assertRaisesRegex(ValueError, "mâu thuẫn"):
            build_memory(**inputs)

    def test_incompatible_models_options_and_semantics_have_explicit_reasons(self) -> None:
        """Model/schema ngữ nghĩa khác không được tự sửa để tăng số mẫu."""
        cases = (("model", "INCOMPATIBLE_SIGNAL_CONFIG"), ("options", "INCOMPATIBLE_CLIENT_OPTIONS"),
                 ("signals", "INCOMPATIBLE_SIGNAL_SEMANTICS"), ("alias", "NONCANONICAL_SIGNAL_SEMANTICS"))
        for kind, reason in cases:
            inputs = deepcopy(self.inputs)
            item = inputs["imported"][0]
            if kind == "model":
                item["source"]["signal_config"]["models"]["agent_llm_model"] = "other-model"
            elif kind == "options":
                item["source"]["client_options"]["agent"]["reasoning_effort"] = "other"
            else:
                item["agent_signals"]["trend"] = "UNKNOWN" if kind == "signals" else "UP"
            with self.subTest(kind=kind):
                result = build_memory(**inputs).payload
                self.assertEqual(result["counts"]["total"], 31)
                self.assertEqual(result["excluded"][0]["reason"], reason)

    def test_decision_and_outcome_fields_never_enter_import_projection(self) -> None:
        """Cấm Decision kể cả nằm sâu trong provenance và cấm nhãn do caller cấp."""
        for field in ("decision", "action", "confidence", "justification", "evidence_for", "evidence_against", "outcome"):
            inputs = deepcopy(self.inputs)
            inputs["imported"][0][field] = "forbidden"
            with self.subTest(field=field), self.assertRaises(ValueError):
                build_memory(**inputs)
        inputs = deepcopy(self.inputs)
        inputs["imported"][0]["source"]["signal_config"]["action"] = "LONG"
        with self.assertRaises(ValueError):
            build_memory(**inputs)

    def test_invalid_economics_is_not_downgraded_to_incompatible(self) -> None:
        """Giá/quyền sai phải ném lỗi ngay cả khi model cũng không tương thích."""
        inputs = deepcopy(self.inputs)
        inputs["imported"][0]["source"]["client_options"] = {}
        inputs["prices"]["FPT"][1].append({"exrightDate": "2023-01-05"})
        with self.assertRaisesRegex(ValueError, "quyền"):
            build_memory(**inputs)

    def test_original_wrong_label_or_overlap_is_rejected(self) -> None:
        """Không cho tái băm bank có nhãn Close-to-Close hoặc cycle trùng."""
        inputs = deepcopy(self.inputs)
        inputs["original"][0]["outcome"]["net_return_pct"] += 1.
        with self.assertRaises(ValueError):
            build_memory(**inputs)
        inputs = deepcopy(self.inputs)
        inputs["original"].append(deepcopy(inputs["original"][0]))
        with self.assertRaises(ValueError):
            build_memory(**inputs)

    def test_overlapping_imported_holding_intervals_are_rejected(self) -> None:
        """Hai cutoff khác nhau vẫn không được tạo hai khoảng nắm giữ chồng lấn."""
        inputs = deepcopy(self.inputs)
        inputs["imported"].append(upstream("FPT", "2023-01-04"))
        with self.assertRaisesRegex(ValueError, "chồng lấn"):
            build_memory(**inputs)

    def test_scalers_equal_legacy_train_and_oos_scope_extends_only(self) -> None:
        """Mở năm query không thay mean/variance/support train; OOS không góp fit."""
        fields = ("episode_id", "symbol", "as_of_date", "exit_date")
        legacy = build_price_feature_index(records=[{k: r[k] for k in fields} for r in self.inputs["original"]],
            **{k: self.inputs[k] for k in ("prices", "calendar", "source", "provenance")})
        for name in ("train_2021", "train_2022", "oos_2023_2024"):
            new_name = "oos_2023_2025" if name == "oos_2023_2024" else name
            for symbol, scaler in legacy.payload["scalers"][name].items():
                self.assertEqual(scaler, self.memory.index.payload["scalers"][new_name][symbol])
        scaler = self.memory.index.scaler("FPT", "2025-12-31")
        self.assertEqual(scaler["fit_max_exit_date"], "2022-12-30")
        self.assertNotIn("FPT:2023-01-03", scaler["fit_episode_ids"])
        self.assertNotIn("FPT:2020-12-30", self.memory.index.scaler("FPT", "2021-01-04")["fit_episode_ids"])

    def test_unavailable_features_do_not_remove_statistical_population(self) -> None:
        """Quyền trong cửa sổ feature làm thiếu vector, không xóa quan sát hợp lệ."""
        key = "FPT:2020-06-12"
        population = self.memory.eligible("FPT", "2023-01-03")
        self.assertIn(key, {r["episode_id"] for r in population})
        row = next(r for r in self.memory.index.payload["records"] if r["episode_id"] == key)
        self.assertEqual(row["features"]["status"], "UNAVAILABLE")

    def test_age_boundary_uses_cutoff_and_does_not_filter_stats(self) -> None:
        """Tuổi 730 nhận, 731 loại khỏi examples; stats vẫn thấy toàn bộ lịch sử."""
        key = "FPT:2023-01-03"
        self.assertIn(key, {r["episode_id"] for r in self.memory.example_pool("FPT", "2025-01-02", "BULL")["records"]})
        result = self.memory.example_pool("FPT", "2025-01-03", "BULL")
        self.assertNotIn(key, {r["episode_id"] for r in result["records"]})
        self.assertIn(key, {r["episode_id"] for r in self.memory.eligible("FPT", "2025-01-03")})
        self.assertEqual(next(r["age_days"] for r in result["excluded"] if r["episode_id"] == key), 731)

    def test_payload_and_query_results_are_owned(self) -> None:
        """Caller không thể thay cache bằng việc sửa object trả về."""
        identity = self.memory.identity
        self.memory.payload["records"][0]["outcome"]["net_return_pct"] = 999.
        self.memory.eligible("FPT", "2025-01-02")[0]["agent_signals"]["trend"] = "changed"
        self.assertEqual(self.memory.identity, identity)

    def test_source_metadata_and_calendar_anchor_are_required(self) -> None:
        """Thiếu hash/model/lịch không được coi là zero hoặc tự suy đoán."""
        for field, value in (("source_files", {}), ("protocol_sha256", "bad"), ("compatibility", {}),
                             ("calendar", pd.bdate_range("2019-01-02", "2025-12-31"))):
            inputs = deepcopy(self.inputs)
            inputs[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                build_memory(**inputs)

    def test_write_once_round_trip_and_resealed_tampering_are_rejected(self) -> None:
        """Loader đối chiếu semantic nguồn, không chỉ checksum do người sửa tự khai."""
        parent = Path(__file__).resolve().parents[1] / "outputs/bayesian_benchmark/unified_bic_v1"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            path = Path(directory) / "memory.json"
            save_memory(self.memory, path)
            original = path.read_bytes()
            save_memory(self.memory, path)
            self.assertEqual(original, path.read_bytes())
            self.assertEqual(load_memory(path, **self.inputs).identity, self.memory.identity)
            for part in ("label", "scaler", "metadata", "source"):
                payload = self.memory.payload
                if part == "label":
                    payload["records"][0]["outcome"]["net_return_pct"] += 1
                elif part == "scaler":
                    payload["index"]["scalers"]["oos_2023_2025"]["FPT"]["mean"][0] += 1
                elif part == "metadata":
                    payload["metadata"][0]["exit_date"] = "2018-01-02"
                else:
                    payload["source_files"]["fixture.json"] = "e" * 64
                save_envelope(path, payload)
                with self.subTest(part=part), self.assertRaises(ValueError):
                    load_memory(path, **self.inputs)
                with self.assertRaises(ValueError):
                    save_memory(self.memory, path)

    def test_output_cannot_overwrite_legacy(self) -> None:
        """Namespace độc lập là bắt buộc, kể cả payload hợp lệ."""
        with self.assertRaises(ValueError):
            save_memory(self.memory, Path("data_manager/regime_memory_store.json"))

    def test_production_rejects_protocol_and_source_tampering_before_adapter(self) -> None:
        """Cờ LOCKED hoặc hash tự khai không thay source anchor đã khóa trước nhập."""
        from scripts import prepare_unified_bayes_memory as producer
        root = Path(__file__).resolve().parents[1]
        protocol = json.loads((root / producer.PROTOCOL).read_text("utf-8"))
        for kind in ("protocol", "source"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                target = Path(directory)
                path = target / producer.PROTOCOL
                path.parent.mkdir(parents=True)
                if kind == "protocol":
                    value = deepcopy(protocol)
                    value["memory"]["maximum_union_count"] += 1
                else:
                    value = protocol
                    first = target / next(iter(value["source_anchors"]))
                    first.parent.mkdir(parents=True, exist_ok=True)
                    first.write_bytes(b"self-resealed-source")
                path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
                with patch.object(producer, "build_adapter", side_effect=AssertionError("adapter")), self.assertRaises(ValueError):
                    producer.verified_inputs(target)


if __name__ == "__main__":
    unittest.main()
