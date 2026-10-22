"""Chặn alias/checkpoint/source giả trước HTTP trong Decision revision."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from bic_icl_fixture import DecisionFixture
from core.bic_icl_decisions import DecisionBlock, ROOT, shared_stage_scope
from core.historical_signals import digest
from core.improvement_transport import body_contract
from core.research_cohort import read_envelope, save_envelope


class DecisionIntegrityTests(unittest.TestCase):
    """Băm lại file không thay nguồn khoa học hoặc HTTP đã audit."""

    def setUp(self) -> None:
        """Fixture không dùng API/key thật."""
        self.f = DecisionFixture()
        self.addCleanup(self.f.close)
        self.original = self.f.request("original")

    def test_full_canonical_identity_includes_model_options_messages_and_schema(self) -> None:
        """Không chỉ so prompt/prefix; mọi thay đổi body đều chặn shared-off."""
        body = {"model": "m", "messages": [{"role": "user", "content": "Cùng prompt."}],
            "temperature": 0., "response_format": {"type": "json_schema", "json_schema": {"name": "schema1"}}}
        original = {"branch_id": "original", "prefix": "", "contract": body_contract(body)}
        for field, value in (("model", "m2"), ("temperature", 1.),
                ("messages", [{"role": "system", "content": "Cùng prompt."}]),
                ("response_format", {"type": "json_schema", "json_schema": {"name": "schema2"}})):
            target = {"branch_id": "R_pool_full", "prefix": "", "contract": body_contract({**body, field: value})}
            self.assertIsNone(DecisionBlock._source([original, target], 1))

    def test_rehashed_alias_cannot_claim_duplicate_or_add_fake_attempt(self) -> None:
        """Cùng body không cho alias chọn response duplicate hoặc đếm HTTP giả."""
        block = self.f.block(1)
        rows = [self.original, self.f.request("original_duplicate"), self.f.request("R_pool_full")]
        self.f.run(self.f.block(), [self.original, self.f.request("R_pool_full")], create=True)
        result = self.f.run(block, rows, create=True)
        for variant in ("source", "attempt", "origin", "output"):
            doc = deepcopy(result); item = doc["branches"]["R_pool_full"]
            if variant == "source":
                duplicate = doc["branches"]["original_duplicate"]
                item.update(source={"branch_id": "original_duplicate", "sha256": digest(duplicate)}, output=deepcopy(duplicate["output"]))
            elif variant == "attempt":
                item["attempts"] = deepcopy(doc["branches"]["original"]["attempts"])
            elif variant == "origin":
                item["decision_origin"] = "llm"
            else:
                item["output"]["final_trade_decision"] = "{}"
            save_envelope(block.path, doc)
            with self.assertRaises(ValueError):
                self.f.run(block, rows)
        save_envelope(block.path, result)
        self.assertEqual(len(self.f.requests), 3)

    def test_repeat_requires_identical_primary_requests_base_and_shared_receipt(self) -> None:
        """Lượt lặp không được thay request/evidence hoặc nhận một primary chưa chạy."""
        rows = [self.original, self.f.request("original_duplicate"), self.f.request("R_pool_full")]
        with self.assertRaises(ValueError):
            self.f.run(self.f.block(1), rows, create=True)
        self.assertEqual(self.f.requests, [])
        primary = self.f.block()
        self.f.run(primary, [self.original, self.f.request("R_pool_full")], create=True)
        for variant in ("prompt", "base", "matrix", "shared"):
            changed = deepcopy(rows); shared = deepcopy(self.f.shared)
            if variant == "prompt":
                changed[0]["prompt"] = changed[1]["prompt"] = "Prompt repeat khác."
            elif variant == "base":
                changed[2]["base_evidence_sha256"] = "d"*64
            elif variant == "matrix":
                changed.pop()
            else:
                shared["reports"]["trend_report"] = "Shared repeat khác."
            with self.assertRaises(ValueError):
                self.f.block(1).run(shared, changed, verify_sources=lambda: None, create=True)
        result = self.f.run(self.f.block(1), rows, create=True)
        self.assertEqual(result["binding"]["primary_reference"]["path"], "decision_blocks/0/FPT-2023-01-06/state.json")
        self.assertEqual(len(self.f.requests), 3)
        primary.path.write_bytes(primary.path.read_bytes()+b" ")
        with self.assertRaises(ValueError):
            self.f.run(self.f.block(1), rows)
        self.assertEqual(len(self.f.requests), 3)

    def test_rehashed_raw_normalized_and_extra_outcome_fail_before_http(self) -> None:
        """Raw/normalized phải khớp nhau và response thật; không giấu evaluation."""
        block = self.f.block(); result = self.f.run(block, [self.original], create=True)
        for variant in ("normalized", "raw_and_normalized", "evaluation"):
            doc = deepcopy(result); item = doc["branches"]["original"]
            output = deepcopy(item["output"])
            if variant == "evaluation":
                output["evaluation"] = {"actual_direction": "UP"}
            else:
                value = json.loads(output["final_trade_decision"]); value["decision"] = "SHORT"
                output["final_trade_decision"] = json.dumps(value, ensure_ascii=False)
                if variant == "raw_and_normalized":
                    raw = json.loads(output["messages"][0]["data"]["content"])
                    raw["decision"] = "SHORT"
                    output["messages"][0]["data"]["content"] = json.dumps(raw, ensure_ascii=False)
            item["output"] = output; item["attempts"][0]["output"] = deepcopy(output)
            save_envelope(block.path, doc)
            with self.assertRaises(ValueError):
                self.f.run(block, [self.original])
        self.assertEqual(len(self.f.requests), 1)

    def test_rebinding_all_checkpoint_hashes_cannot_replace_audited_request(self) -> None:
        """Sửa cả identity/ready/state vẫn không đổi body HTTP đã lưu trong ledger."""
        block = self.f.block(); doc = self.f.run(block, [self.original], create=True)
        changed = self.f.request("original", prompt="Prompt tự băm lại.")
        binding = block._binding(deepcopy(self.f.shared), [changed])
        doc["binding"] = binding
        item = doc["branches"]["original"]
        item["output"]["decision_prompt"] = changed["prompt"]
        item["attempts"][0]["output"] = deepcopy(item["output"])
        save_envelope(block.directory/"identity.json", binding)
        save_envelope(block.directory/"ready.json", {"binding_sha256": digest(binding)})
        save_envelope(block.path, doc)
        with self.assertRaises(ValueError):
            self.f.run(block, [changed])
        self.assertEqual(len(self.f.requests), 1)

    def test_missing_durable_files_cannot_be_reset_with_create(self) -> None:
        """Mất state/identity/marker sau complete phải dừng, không replay Original."""
        block = self.f.block(); self.f.run(block, [self.original], create=True)
        for path in (block.path, block.directory/"identity.json", block.directory/"ready.json"):
            original = path.read_bytes(); path.unlink()
            with self.assertRaises(ValueError):
                self.f.run(block, [self.original], create=True)
            path.write_bytes(original)
        self.assertEqual(len(self.f.requests), 1)

    def test_ledger_loss_is_not_hidden_by_complete_checkpoint(self) -> None:
        """Loader đọc ledger durable thay vì tin bản RAM còn response thành công."""
        block = self.f.block(); self.f.run(block, [self.original], create=True)
        path = self.f.root/"usage.json"
        ledger = json.loads(path.read_text()); ledger["requests"] = []
        path.write_text(json.dumps(ledger), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.f.run(block, [self.original], verify_only=True)
        self.assertEqual(len(self.f.requests), 1)

    def test_durable_response_cache_tamper_blocks_after_fresh_client_restart(self) -> None:
        """Unknown chỉ dùng response đúng hash; cache bị sửa không được gửi lại HTTP."""
        block = self.f.block()
        original_save = save_envelope
        def crash(path, value):
            if value["branches"]["original"]["status"] == "complete":
                raise KeyboardInterrupt("Fixture trước checkpoint complete.")
            original_save(path, value)
        with patch("core.bic_icl_decisions.save_envelope", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                self.f.run(block, [self.original], create=True)
        path = next((self.f.root/"cache").glob("*.json"))
        original_cache, original_ledger = path.read_bytes(), (self.f.root/"usage.json").read_bytes()
        for variant in ("checksum", "rehashed_header_schema"):
            path.write_bytes(original_cache)
            (self.f.root/"usage.json").write_bytes(original_ledger)
            if variant == "checksum":
                path.write_bytes(original_cache+b" ")
            else:
                cached = read_envelope(path); cached["headers"] = []
                save_envelope(path, cached)
                ledger = json.loads(original_ledger)
                ledger["requests"][-1]["durable_response"] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                (self.f.root/"usage.json").write_text(json.dumps(ledger), encoding="utf-8")
            self.f.restart()
            with self.assertRaises(ValueError):
                self.f.run(self.f.block(), [self.original])
        self.assertEqual(len(self.f.requests), 1)

    def test_other_point_repeat_and_shared_change_fail_before_http(self) -> None:
        """Không reuse cache chỉ vì prompt giống giữa point/repeat hoặc shared khác."""
        block = self.f.block(); self.f.run(block, [self.original], create=True)
        changed = deepcopy(self.f.shared); changed["reports"]["trend_report"] = "Báo cáo khác."
        with self.assertRaises(ValueError):
            block.run(changed, [self.original], verify_sources=lambda: None)
        with self.assertRaises(ValueError):
            self.f.run(self.f.block(signature="b"*64), [self.original])
        with self.assertRaises(ValueError):
            self.f.run(self.f.block(1), [self.original, self.f.request("original_duplicate")])
        with self.assertRaises(ValueError):
            self.f.run(self.f.block(point_id="FPT-2023-01-09"), [self.original], create=True)
        self.assertEqual(len(self.f.requests), 1)

    def test_source_verifier_failure_stops_before_next_branch(self) -> None:
        """Nguồn drift sau Original giữ slot sau planned, không gọi thêm HTTP."""
        block = self.f.block(); rows = [self.original, self.f.request("R_pool_full", prompt="Prompt khác.")]
        count = []
        def verify():
            count.append(1)
            if len(count) == 3:
                raise ValueError("Fixture nguồn đổi checksum.")
        with self.assertRaises(ValueError):
            block.run(self.f.shared, rows, verify_sources=verify, create=True)
        result = read_envelope(block.path)
        self.assertEqual(result["branches"]["original"]["status"], "complete")
        self.assertEqual(result["branches"]["R_pool_full"]["status"], "planned")
        self.assertEqual(len(self.f.requests), 1)

    def test_future_feature_and_query_outcome_projection_are_rejected(self) -> None:
        """Shared future hoặc field outcome không được coi là đầu vào Decision hợp lệ."""
        for variant in ("future", "cutoff", "outcome", "numpy"):
            shared = deepcopy(self.f.shared)
            if variant == "future":
                shared["market_regime"]["feature_end_date"] = "2025-01-02"
            elif variant == "cutoff":
                shared["prior_provenance"]["context"]["as_of_date"] = "2025-01-02"
            elif variant == "outcome":
                shared["evaluation"] = {"net_return_long": .1}
            else:
                shared["current_signals"]["flag"] = np.bool_(True)
            with self.assertRaises(ValueError):
                self.f.block().run(shared, [self.original], verify_sources=lambda: None, create=True)
        self.assertEqual(self.f.requests, [])

    def test_limits_invalid_schema_duplicate_and_native_types_fail_closed(self) -> None:
        """Không gửi prompt vượt trần, request giả hoặc duplicate sai body."""
        rows = [[self.f.request("original", prompt="x"*6500)],
            [self.original, self.f.request("R_pool_full", prefix="x"*601, prompt="x"*601)],
            [self.original, self.original], [self.f.request("R_pool_full"), self.original],
            [{**self.original, "branch_id": ["original"]}], [self.original, {**self.f.request("R_pool_full"), "unknown": True}]]
        for requests in rows:
            with self.assertRaises(ValueError):
                self.f.run(self.f.block(), requests, create=True)
        with self.assertRaises(ValueError):
            self.f.run(self.f.block(1), [self.original, self.f.request("original_duplicate", prompt="Sai duplicate.")], create=True)
        self.assertEqual(self.f.requests, [])

    def test_client_options_and_namespace_cannot_bypass_protocol(self) -> None:
        """Khóa options/namespace; fixture không được ghi vào bằng chứng workspace."""
        self.f.llm.model_kwargs = {"seed": 42}
        with self.assertRaises(ValueError):
            self.f.run(self.f.block(), [self.original], create=True)
        self.f.llm.model_kwargs = {}
        for root in (ROOT, ROOT/"outputs/bayesian_benchmark/improvement_v1"):
            with self.assertRaises(ValueError):
                DecisionBlock(root, "a"*64, "FPT-2023-01-06", 0, self.f.llm)
            with self.assertRaises(ValueError):
                DecisionBlock(root, "a"*64, "FPT-2023-01-06", 0, self.f.llm, fixture=True)
        for point_id in ("../outside", "FPT-../../escape", "FPT-2023-02-30"):
            with self.assertRaises(ValueError):
                self.f.block(point_id=point_id)
        self.assertEqual(self.f.requests, [])

    def test_wrong_horizon_never_becomes_cash_or_complete(self) -> None:
        """Horizon sai còn unknown sau sửa format, không chấm kinh tế hoặc tự CASH."""
        self.f.payload["forecast_horizon"] = "T+1"
        block = self.f.block()
        with self.assertRaises(ValueError):
            self.f.run(block, [self.original], create=True)
        result = read_envelope(block.path)["branches"]["original"]
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["output"])
        self.assertEqual(len(result["attempts"]), 1)

    def test_upstream_missing_journal_after_durable_node_cannot_reinitialize(self) -> None:
        """Journal/marker đã dùng không được tạo lại để gọi upstream lần hai."""
        directory = self.f.root/"run/shared_stages/FPT-2023-01-06"
        with shared_stage_scope(self.f.root/"run", "a"*64, "FPT-2023-01-06", "d"*64,
                                create=True, fixture=True) as journal:
            journal.invoke("indicator", lambda state: {"indicator_report": "I"}, {"stock_name": "FPT"})
        for name in ("journal.json", "ready.json"):
            path = directory/name; original = path.read_bytes(); path.unlink()
            with self.assertRaises(ValueError):
                with shared_stage_scope(self.f.root/"run", "a"*64, "FPT-2023-01-06", "d"*64,
                                        create=True, fixture=True):
                    self.fail("Không được vào journal đã mất proof.")
            path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
