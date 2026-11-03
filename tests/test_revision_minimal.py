"""Kiểm whitelist, raw lineage, khóa xuyên run và interruption bằng mocks offline."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import socket
import sys
import tempfile
import threading
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from agents.decision_agent import TradeDecisionOutput
from core.revision72_run import checked, signed
from core.revision_call_archive import StudyLock
from core.revision_common_study import digest, read_json, write_json
from core.revision_minimal_bank import (
    R1, R4, collect, legacy_guard, parent_for, point_path, select_panel, sha, verify_record,
)
from core.revision_minimal_run import (
    SharedLedger, WhitelistArchive, analyze, recover_temporary, status, verify_calls, worker,
)

ROOT = Path(__file__).resolve().parents[1]
DECISION = {"decision": "LONG", "forecast_horizon": "T+2.5", "confidence": "Thấp", "risk_reward_ratio": 1.0,
            "evidence_for": "Dữ liệu giả lập", "evidence_against": "Dữ liệu giả lập", "justification": "Chỉ kiểm thử offline"}


class MinimalQueueTests(unittest.TestCase):
    """Không gọi SDK/network hoặc ghi vào evidence thật trong quá trình kiểm thử."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.run = self.root / "run"
        self.run.mkdir()
        source = next((ROOT / R4).glob("shards/org*/calls/*.request.json"))
        request = checked(source)
        contract = {k: request[k] for k in ("model_metadata", "invocation_parameters")}
        jobs = []
        for index in range(2):
            context = {"unit_id": "SYNTHETIC", "realization": 0, "variant": "B", "repeat": index,
                       "stage": "decision", "node": "Decision Maker", "model": "openai/gpt-oss-20b", "smoke": False}
            prompt = "Prompt giả lập kiểm thử offline"
            jobs.append({"id": f"fixture_{index}", "phase": "main", "unit": {"date": "2026-01-01"},
                         "context": context, "worker": 1, "reuse": None, "prompt": prompt, "prompt_hash": digest(prompt),
                         "request_contract": contract, "origin_parent": {"asset_hash": "asset", "upstream_hash": "upstream", "donor_hash": None}})
        self.manifest = signed({"jobs": jobs, "execution": {"model": "openai/gpt-oss-20b", "temperature": 0, "max_tokens": 2048}})
        self.ledger = SharedLedger(self.run / "quota.sqlite3", self.manifest["sha256"], self.root)
        self.network = patch.object(socket.socket, "connect", side_effect=AssertionError("Cấm network trong test offline"))
        self.network.start(); self.addCleanup(self.network.stop)
        self.factory_state = SimpleNamespace(calls=0, interrupt=False, bad_schema_once=False)

    def fake_factory(self, archive: WhitelistArchive, keys: list[str], slot: int, settings: dict, epoch: str) -> Any:
        """Mô phỏng callback trước/sau request và raw response như SDK thật."""
        state, manifest = self.factory_state, self.manifest

        class FakeRouted:
            """Không có client hoặc network; chỉ sinh response fixture được gắn rõ provenance."""

            def with_structured_output(self, *args: object, **kwargs: object) -> FakeRouted:
                """Giữ interface parser thực mà CachedLLM sử dụng."""
                return self

            def invoke(self, prompt: str) -> dict:
                """Ghi cả raw và ledger trước khi mô phỏng interruption."""
                owner = str(uuid4())
                org = archive.ledger.acquire(settings["model"], slot, owner, list(range(1, 6)))
                if org is None: raise AssertionError("Fixture cần key khả dụng")
                previous = archive.context
                archive.context = {**previous, "provider_org": org, "execution_epoch": epoch}
                attempt = uuid4()
                try:
                    contract = manifest["jobs"][0]["request_contract"]
                    archive.on_chat_model_start({}, [[HumanMessage(content=prompt)]], run_id=attempt,
                                                metadata=contract["model_metadata"], invocation_params=contract["invocation_parameters"])
                    state.calls += 1
                    decision = TradeDecisionOutput.model_validate(DECISION)
                    message = AIMessage(content=decision.model_dump_json())
                    if state.bad_schema_once and state.calls == 1:
                        message = AIMessage(content='{"decision":"NEUTRAL"}')
                    archive.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]), run_id=attempt)
                    if state.interrupt:
                        state.interrupt = False
                        raise KeyboardInterrupt()
                    if state.bad_schema_once and state.calls == 1:
                        return {"parsed": None, "raw": message, "parsing_error": ValueError("Schema giả lập sai")}
                    return {"parsed": decision, "raw": message, "parsing_error": None}
                finally:
                    archive.context = previous
                    archive.ledger.release(org, owner)

        return FakeRouted()

    def execute(self) -> None:
        """Chạy worker thật với factory giả, không đi vào CLI run hoặc SDK."""
        worker(self.root, self.run, self.manifest, 1, threading.Event(), ["fixture"] * 5, self.fake_factory)

    def test_whitelist_execution_and_resume_skip_successes(self) -> None:
        self.execute()
        self.assertEqual(self.factory_state.calls, 2)
        self.execute()
        self.assertEqual(self.factory_state.calls, 2)
        result = status(self.root, self.run, self.manifest)
        self.assertEqual((result["complete"], result["missing"], result["new_calls"]["new_attempts"]), (2, 0, 2))

    def test_interruption_after_raw_replays_without_new_request(self) -> None:
        self.factory_state.interrupt = True
        with self.assertRaises(KeyboardInterrupt): self.execute()
        self.assertEqual(len(collect(self.root, self.run, self.manifest)), 0)
        self.assertEqual(verify_calls(self.run, self.manifest)["new_attempts"], 1)
        self.execute()
        self.assertEqual(self.factory_state.calls, 2)
        self.assertEqual(len(collect(self.root, self.run, self.manifest)), 2)

    def test_temporary_checkpoint_recovers_without_calls(self) -> None:
        self.execute()
        path = point_path(self.run, self.manifest["jobs"][0])
        path.rename(path.with_suffix(".tmp"))
        recover_temporary(self.root, self.run, self.manifest)
        self.execute()
        self.assertTrue(path.exists())
        self.assertEqual(self.factory_state.calls, 2)

    def test_format_retry_is_counted_and_keeps_repeat_identity(self) -> None:
        self.factory_state.bad_schema_once = True
        self.execute()
        self.assertEqual(self.factory_state.calls, 3)
        record = checked(point_path(self.run, self.manifest["jobs"][0]))
        self.assertEqual(len(record["request_ids"]), 2)
        self.assertEqual(record["context"]["repeat"], 0)
        self.assertEqual(verify_calls(self.run, self.manifest)["new_attempts"], 3)

    def test_callback_refuses_outside_whitelist_before_reserve(self) -> None:
        shard = self.run / "shards/org1"
        archive = WhitelistArchive(shard, self.manifest["sha256"], "fixture", self.ledger, 1, 0, manifest=self.manifest)
        archive.context = {**self.manifest["jobs"][0]["context"], "repeat": 99}
        with self.assertRaisesRegex(ValueError, "ngoài whitelist"):
            archive.on_chat_model_start({}, [[HumanMessage(content="x")]], run_id=uuid4())
        self.assertEqual(verify_calls(self.run, self.manifest)["new_attempts"], 0)

    def test_callback_rejects_changed_model_parameters_and_message(self) -> None:
        archive = WhitelistArchive(self.run / "shards/org1", self.manifest["sha256"], "fixture", self.ledger, 1, 0, manifest=self.manifest)
        job = self.manifest["jobs"][0]
        archive.context = {**job["context"], "provider_org": 1, "execution_epoch": self.manifest["sha256"]}
        contract = deepcopy(job["request_contract"])
        contract["model_metadata"]["ls_max_tokens"] += 1
        with self.assertRaisesRegex(ValueError, "parameters/schema"):
            archive.on_chat_model_start({}, [[HumanMessage(content=job["prompt"])]], run_id=uuid4(),
                                        metadata=contract["model_metadata"], invocation_params=contract["invocation_parameters"])
        with self.assertRaisesRegex(ValueError, "message/budget"):
            archive.on_chat_model_start({}, [[HumanMessage(content=job["prompt"] + " changed")]], run_id=uuid4())
        self.assertEqual(verify_calls(self.run, self.manifest)["new_attempts"], 0)

    def test_tampered_raw_and_parent_fail_closed(self) -> None:
        self.execute()
        job = self.manifest["jobs"][0]; path = point_path(self.run, job)
        record = checked(path)
        raw_path = path.parent.parent / f"calls/{record['request_ids'][0]}.response.json"
        raw = read_json(raw_path); raw["ended_at_utc"] = "changed"
        write_json(raw_path, raw)
        with self.assertRaises(ValueError): collect(self.root, self.run, self.manifest)

    def test_resigned_parent_mismatch_and_duplicate_repeat_ids_rejected(self) -> None:
        self.execute()
        path = point_path(self.run, self.manifest["jobs"][0])
        original = checked(path)
        changed = deepcopy(original); changed.pop("sha256"); changed["parent"]["upstream_hash"] = "changed"
        write_json(path, signed(changed))
        with self.assertRaisesRegex(ValueError, "context/parent"):
            collect(self.root, self.run, self.manifest)
        write_json(path, original)
        duplicate = deepcopy(self.manifest["jobs"][0]); duplicate["id"] = "extra"
        duplicate["worker"] = 2
        # Hai identity khác nhau không được dùng chung một response/repeat.
        duplicate["reuse"] = {"path": path.relative_to(self.root).as_posix(), "sha256": sha(path)}
        duplicate["origin_parent"] = original["parent"]
        duplicate["origin_bank_id"] = self.manifest["sha256"]
        duplicate["origin_epoch"] = self.manifest["sha256"]
        self.manifest["jobs"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "nhiều jobs/repeats"):
            collect(self.root, self.run, self.manifest)

    def test_real_chatgroq_callbacks_and_provider_error_with_mock_transport(self) -> None:
        from langchain_groq import ChatGroq
        import httpx
        from groq import RateLimitError
        calls = []

        def construct(**kwargs: Any) -> Any:
            """Dùng serializer/callback thật, thay duy nhất transport SDK bằng mock."""
            model = ChatGroq(**kwargs)

            def completion(**payload: Any) -> dict:
                """Lần đầu báo quota, những lần sau trả response giả lập có schema hợp lệ."""
                calls.append(payload)
                if len(calls) == 1:
                    response = httpx.Response(429, request=httpx.Request("POST", "https://offline.invalid"))
                    raise RateLimitError("tokens per day; retry after 1h", response=response, body={})
                return {"id": "offline-fixture", "object": "chat.completion", "created": 0,
                        "model": "openai/gpt-oss-20b", "choices": [{"index": 0, "finish_reason": "stop",
                            "message": {"role": "assistant", "content": TradeDecisionOutput.model_validate(DECISION).model_dump_json()}}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}

            model.client.create = completion
            return model

        with patch("langchain_groq.ChatGroq", side_effect=construct):
            worker(self.root, self.run, self.manifest, 1, threading.Event(), ["offline-fixture"] * 5)
        result = status(self.root, self.run, self.manifest)
        self.assertEqual((result["complete"], result["new_calls"]["new_attempts"], result["new_calls"]["errors"]), (2, 3, 1))
        self.assertEqual(len(calls), 3)
        self.assertTrue(self.ledger.states("openai/gpt-oss-20b", [1])[0]["active"])

    def test_resigned_wrong_context_does_not_replay(self) -> None:
        self.execute()
        path = next(self.run.glob("shards/org*/calls/*.request.json"))
        request = checked(path); request.pop("sha256"); request["context"]["repeat"] = 77
        write_json(path, signed(request))
        with self.assertRaisesRegex(ValueError, "ngoài whitelist"):
            verify_calls(self.run, self.manifest)

    def test_one_key_shared_across_workers_and_origin_runs(self) -> None:
        other = SharedLedger(self.run / "quota.sqlite3", self.manifest["sha256"], self.root)
        self.assertEqual(self.ledger.acquire("model", 1, "first", [1]), 1)
        self.assertIsNone(other.acquire("model", 1, "second", [1]))
        self.ledger.release(1, "first")
        with StudyLock(self.root / R4 / "provider_locks/org1.lock"):
            self.assertIsNone(other.acquire("model", 1, "blocked", [1]))
        self.assertEqual(other.acquire("model", 1, "third", [1]), 1)
        other.release(1, "third")

    def test_provider_quota_state_prevents_early_reset(self) -> None:
        self.ledger.block(1, "model", "quota", 3600, "Fixture quota")
        self.assertIsNone(self.ledger.acquire("model", 1, "blocked", [1]))
        state = self.ledger.states("model", [1])[0]
        self.assertTrue(state["active"])
        self.assertEqual(state["kind"], "quota")

    def test_duplicate_coordinator_and_active_legacy_worker_are_blocked(self) -> None:
        with StudyLock(self.run / "runner.lock"):
            with self.assertRaises(RuntimeError):
                with StudyLock(self.run / "runner.lock"): pass
        with patch("core.revision_minimal_bank.legacy_processes", return_value=[{"pid": 123}]):
            with self.assertRaisesRegex(ValueError, "worker grid cũ"):
                with legacy_guard(self.root): pass

    def test_off_whitelist_checkpoint_and_partial_analysis_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Chưa đủ"):
            analyze(self.root, self.run, self.manifest)
        path = self.run / "shards/org1/decisions/outside.json"
        write_json(path, signed({"outside": True}))
        with self.assertRaisesRegex(ValueError, "ngoài whitelist"):
            collect(self.root, self.run, self.manifest)

    def test_missing_ledger_never_silently_resets(self) -> None:
        self.execute()
        self.ledger.path.rename(self.ledger.path.with_suffix(".saved"))
        with self.assertRaisesRegex(ValueError, "Thiếu ledger"):
            verify_calls(self.run, self.manifest)
        with self.assertRaisesRegex(ValueError, "Thiếu quota ledger"):
            SharedLedger(self.run / "quota.sqlite3", self.manifest["sha256"], self.root)


class MetadataSelectionTests(unittest.TestCase):
    """Panel cố định không nhận outcome hoặc chọn theo thứ tự hoàn thành."""

    def test_frozen_nine_metadata_units_and_outcome_invariance(self) -> None:
        manifest = checked(ROOT / "outputs/revision/chart_r4_bank_v1/manifest.json")
        selected = [u["unit"]["id"] for u in select_panel(manifest["units"])]
        self.assertEqual(selected, ["BHN_f2026_q3_1002", "FPT_f2026_q3_1675", "HVN_f2026_q2_1556", "MBB_f2026_q2_1556",
                                    "MWG_f2026_q3_1675", "VCB_f2026_q2_1613", "VJC_f2026_q2_1556", "VNM_f2025_q4_1490", "HVN_f2026_q2_1613"])
        rows = deepcopy(list(reversed(manifest["units"])))
        for index, row in enumerate(rows): row["prediction"] = "LONG" if index % 2 else "SHORT"
        self.assertEqual(selected, [u["unit"]["id"] for u in select_panel(rows)])


if __name__ == "__main__":
    unittest.main()
