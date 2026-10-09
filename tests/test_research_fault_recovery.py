"""Fault/resume cohort bốn mã trên file thật và LLM giả, cấm key/mạng."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from typing import Any
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage

from core.backtest_engine import PRIOR_BRANCH_MODES
from core.bayesian_memory import SYMBOLS
from core.groq_pacing import GroqPacer, MODEL_LIMITS, PilotStop
from core.prior_backtest import PriorBacktestRunner, canonical_hash
from core.prior_checkpoint import CheckpointSession
from core.prior_evidence_v2 import normalize_evidence_config
from core.prior_run_lock import PriorRunLock
from core.prior_stage_journal import StageJournal
from core import research_cohort
import test_atomic_checkpoint_io as atomic_support
import test_prior_backtest_integration as support


class Crash(BaseException):
    """Ngắt sau commit durable, không cho handler ghi thêm trạng thái."""


class CohortFaultRecoveryTests(unittest.TestCase):
    """Lỗi ở mã thứ hai phải giữ mã complete và toàn bộ lịch bốn mã."""

    def setUp(self) -> None:
        support.PriorBacktestIntegrationTests.setUp(self)
        for target in ("socket.socket.connect", "socket.getaddrinfo", "dotenv.load_dotenv",
                       "scripts.run_bayesian_ablation.dotenv_values", "httpx.HTTPTransport.handle_request"):
            guard = self.stack.enter_context(patch(target, side_effect=AssertionError("Cấm key/mạng")))
            self.addCleanup(lambda guard=guard: self.assertFalse(guard.called))
        self.plan = {"plan_version": "research_cohort_plan_v2", "cohort_id": "fault-four",
            "split": "fixture", "matrix": "smoke_v1",
            "symbol_cutoffs": {s: [self.fx.cutoff] for s in sorted(SYMBOLS)},
            "evidence_config": normalize_evidence_config(),
            "inputs": {"signal_config": self.adapter.signal_config}}
        self.runner = PriorBacktestRunner(self.engine, self.adapter, self.builder,
            execution_mode="offline_fixture", quota_policy="request_admission_v2", durable_stages=True)

    def point_path(self, symbol: str) -> Path:
        """Đường checkpoint v1 trong thư mục tạm của cohort."""
        return self.output / f"v1/{symbol}/points/{symbol}-{self.fx.cutoff}.json"

    def run_cohort(self, **kwargs: Any) -> dict[str, Any]:
        """Chạy đường điều phối production với nguồn và client fixture."""
        return self.runner.run_cohort(self.plan, output_dir=self.output, **kwargs)

    def assert_complete(self, result: dict[str, Any]) -> None:
        """Kiểm common support, shared hash và cap trên cả bốn mã."""
        self.assertEqual(set(result["stocks"]), SYMBOLS)
        for symbol, stock in result["stocks"].items():
            self.assertEqual((stock["completed"], stock["pending"]), (1, []))
            document = research_cohort.read_envelope(self.point_path(symbol))
            self.assertEqual(set(document["branches"]), set(PRIOR_BRANCH_MODES))
            shared = document["shared"]["shared_sha256"]
            self.assertEqual(shared, canonical_hash(document["shared"]["full_bundle"]))
            for branch in document["branches"].values():
                self.assertEqual(branch["status"], "complete")
                self.assertEqual(branch["input"]["shared_sha256"], shared)
                self.assertLess(branch["input"]["prompt"]["char_count"], 6500)
                self.assertLessEqual(len(branch["input"]["bayesian_prior_context"]), 600)
            if self.plan["matrix"] == "research_v2":
                saved = research_cohort.read_envelope(self.output / f"v2/{symbol}-{self.fx.cutoff}.json")
                self.assertEqual(saved["shared_sha256"], shared)
                self.assertEqual(saved["attempts"][-1]["status"], "complete")
                self.assertLess(len(saved["prompt"]), 6500)
        self.assertEqual(len(result["matrix"]), 6 if self.plan["matrix"] == "research_v2" else 5)

    def test_daily_quota_and_long_cooldown_stop_between_stocks_then_resume(self) -> None:
        """Quota thật trên ledger fixture dừng trước upstream mã thứ hai."""
        for reason in ("DAILY_QUOTA", "COOLDOWN_BEFORE_POINT"):
            with self.subTest(reason=reason):
                self.output = self.fx.root / reason
                self.events.clear()
                before = self.llm.calls
                now = [100000.]
                pacer = GroqPacer(self.output.parent / f"{reason}-usage.json",
                    clock=lambda: now[0], sleep=lambda _: self.fail("Không nghỉ thật"),
                    policy="request_admission_v2")
                admissions = []
                def admit() -> None:
                    admissions.append(True)
                    if len(admissions) == 2:
                        rows = [{"model": model, "started_at": now[0] - 100,
                            "reserved_tokens": 8000, "status": "unknown"}
                            for model in MODEL_LIMITS
                            for _ in range(25 if reason == "DAILY_QUOTA" else 1)]
                        if reason == "COOLDOWN_BEFORE_POINT":
                            rows[0]["retry_until"] = now[0] + 1000
                        pacer.state["requests"] = rows
                        pacer.save()
                    pacer.before_point()
                self.runner.before_point = admit
                with self.assertRaisesRegex(PilotStop, reason):
                    self.run_cohort()
                fpt = self.point_path("FPT").read_bytes()
                self.assertEqual(self.llm.calls - before, 5)
                self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"])
                for symbol in SYMBOLS - {"FPT"}:
                    doc = research_cohort.read_envelope(self.point_path(symbol))
                    self.assertEqual(doc["shared"]["stage"], "not_started")
                    self.assertTrue(all(not b["attempts"] for b in doc["branches"].values()))
                history = deepcopy(pacer.state["requests"])
                self.assertIsNotNone(pacer.state["last_stop"]["resume_not_before_utc"])
                now[0] += 86401
                reloaded = GroqPacer(pacer.path, clock=lambda: now[0],
                    sleep=lambda _: self.fail("Không nghỉ thật"), policy="request_admission_v2")
                self.runner.before_point = reloaded.before_point
                self.assert_complete(self.run_cohort(resume=True))
                self.assertEqual(reloaded.state["requests"], history)
                self.assertEqual(self.llm.calls - before, 20)
                self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"] * 4)
                self.assertEqual(self.point_path("FPT").read_bytes(), fpt)

    def test_crash_after_durable_node_on_second_stock_reuses_every_node(self) -> None:
        """Mỗi node MWG durable được phục hồi một lần, FPT không bị gọi lại."""
        save = StageJournal.save
        for name in ("indicator", "pattern", "trend", "full"):
            with self.subTest(node=name):
                self.output = self.fx.root / f"node-{name}"
                self.events.clear()
                before = self.llm.calls
                fired = []
                def stop(journal: StageJournal, candidate: dict[str, Any]) -> None:
                    save(journal, candidate)
                    node = candidate["nodes"].get(name)
                    if journal.path.name.startswith("MWG-") and node and node["attempts"][-1]["status"] == "complete" and not fired:
                        fired.append(True)
                        raise Crash()
                with patch.object(StageJournal, "save", stop), self.assertRaises(Crash):
                    self.run_cohort()
                fpt = self.point_path("FPT").read_bytes()
                journal = self.output / f"v1/MWG/responses/MWG-{self.fx.cutoff}.json"
                durable = json.loads(journal.read_text("utf-8"))["payload"]["nodes"][name]
                self.assert_complete(self.run_cohort(resume=True))
                self.assertEqual(json.loads(journal.read_text("utf-8"))["payload"]["nodes"][name], durable)
                self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"] * 4)
                self.assertEqual(self.llm.calls - before, 20)
                self.assertEqual(self.point_path("FPT").read_bytes(), fpt)

    def test_crash_after_partial_branch_keeps_completed_attempts_and_prompts(self) -> None:
        """Hai nhánh pending chạy tiếp từ Full; ba nhánh durable nguyên vẹn."""
        def stop(session: CheckpointSession, event: str) -> None:
            if session.document["context"]["symbol"] == "MWG" and event == "branch_complete:recent":
                raise Crash()
        with patch.object(CheckpointSession, "_after_commit", stop), self.assertRaises(Crash):
            self.run_cohort()
        document = research_cohort.read_envelope(self.point_path("MWG"))
        complete = {name: branch for name, branch in document["branches"].items() if branch["status"] == "complete"}
        self.assertEqual(set(complete), {"original", "random", "recent"})
        self.assertEqual(self.llm.calls, 8)
        self.assert_complete(self.run_cohort(resume=True))
        document = research_cohort.read_envelope(self.point_path("MWG"))
        self.assertEqual({name: document["branches"][name] for name in complete}, complete)
        self.assertEqual(self.llm.calls, 20)
        self.assertEqual(len(self.events), 16)

    def test_unknown_second_stock_stops_all_agents_until_exact_fixture_replay(self) -> None:
        """Mất response trước durable phải giữ unknown và yêu cầu audit UUID."""
        save = StageJournal.save
        def lose(journal: StageJournal, candidate: dict[str, Any]) -> None:
            node = candidate["nodes"].get("pattern")
            if journal.path.name.startswith("MWG-") and node and node["attempts"][-1]["status"] == "complete":
                raise OSError("Không lưu được response fixture")
            save(journal, candidate)
        with patch.object(StageJournal, "save", lose), self.assertRaises(OSError):
            self.run_cohort()
        fpt = self.point_path("FPT").read_bytes()
        calls, events = self.llm.calls, list(self.events)
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_PATTERN"):
            self.run_cohort(resume=True)
        report = self.run_cohort(reconcile=True)
        unknown = report["upstream"]["MWG"]["points"][0]["nodes"][-1]
        self.assertEqual(unknown["status"], "unknown")
        self.assertEqual((self.llm.calls, self.events), (calls, events))
        self.run_cohort(reconcile=True, authorize_replay=unknown["attempt_id"],
            replay_reason="Chỉ xác nhận replay trong fixture offline")
        self.assert_complete(self.run_cohort(resume=True))
        self.assertEqual(self.llm.calls, 20)
        self.assertEqual(self.events.count("pattern"), 5)
        self.assertEqual(self.point_path("FPT").read_bytes(), fpt)
        journal = self.output / f"v1/MWG/responses/MWG-{self.fx.cutoff}.json"
        attempts = json.loads(journal.read_text("utf-8"))["payload"]["nodes"]["pattern"]["attempts"]
        self.assertEqual([a["status"] for a in attempts], ["unknown", "complete"])
        self.assertEqual(attempts[0]["attempt_id"], unknown["attempt_id"])
        self.assertTrue(attempts[0]["authorization"]["reason"])

    def test_atomic_intent_failure_stops_http_and_safe_resume_keeps_first_stock(self) -> None:
        """WinError 32 hết retry trước intent không được gửi Decision tương ứng."""
        replace = os.replace
        failures = []
        def locked(source: str, target: str) -> None:
            if Path(target) == self.point_path("MWG"):
                doc = json.loads(Path(source).read_text("utf-8"))["payload"]
                if doc["branches"]["random"]["status"] == "running":
                    failures.append(self.llm.calls)
                    raise atomic_support.windows_error(32)
            replace(source, target)
        with patch("core.bayesian_memory.os.replace", side_effect=locked), \
             patch("core.bayesian_memory.time.sleep"), self.assertRaises(OSError):
            self.run_cohort()
        self.assertEqual(failures, [6] * 5)
        fpt = self.point_path("FPT").read_bytes()
        mwg = research_cohort.read_envelope(self.point_path("MWG"))
        self.assertEqual(mwg["branches"]["original"]["status"], "complete")
        self.assertEqual(mwg["branches"]["random"]["attempts"], [])
        self.assert_complete(self.run_cohort(resume=True))
        self.assertEqual(self.llm.calls, 20)
        self.assertEqual(self.point_path("FPT").read_bytes(), fpt)

    def test_malformed_decision_never_becomes_cash_or_loses_pending_points(self) -> None:
        """Output sai hai lần ở MWG phải còn failed, không tính vào common support."""
        invoke = self.llm.invoke
        def malformed(prompt: Any) -> AIMessage:
            if self.llm.calls >= 6:
                self.llm.calls += 1
                return AIMessage(content="Không có phán quyết hợp lệ trong fixture.")
            return invoke(prompt)
        with patch.object(self.llm, "invoke", side_effect=malformed), self.assertRaises(RuntimeError):
            self.run_cohort()
        mwg = research_cohort.read_envelope(self.point_path("MWG"))
        self.assertEqual(mwg["branches"]["random"]["status"], "failed")
        self.assertIsNone(mwg["branches"]["random"]["decision"])
        self.assertIsNone(mwg["evaluation"])
        calls = self.llm.calls
        report = self.run_cohort(verify_only=True)
        self.assertEqual([report["stocks"][s]["completed"] for s in sorted(SYMBOLS)], [1, 0, 0, 0])
        self.assertEqual(sum(len(s["pending"]) for s in report["stocks"].values()), 3)
        self.assertIsNone(report["primary_delta_return_pp"])
        with self.assertRaisesRegex(ValueError, "Decision chưa rõ"):
            self.run_cohort(resume=True)
        self.assertEqual(self.llm.calls, calls)

    def test_unselected_corrupt_point_and_source_block_before_any_new_agent(self) -> None:
        """Chọn MWG vẫn phải phát hiện VNM bị sửa trước HTTP đầu tiên."""
        self.run_cohort(symbols=["FPT"])
        fpt = self.point_path("FPT").read_bytes()
        path = self.point_path("VNM")
        original = path.read_bytes()
        doc = research_cohort.read_envelope(path)
        doc["context"]["as_of_date"] = self.cutoffs[1]
        research_cohort.save_envelope(path, doc)
        with self.assertRaises(ValueError):
            self.run_cohort(symbols=["MWG"], resume=True)
        self.assertEqual(self.llm.calls, 5)
        path.write_bytes(original)
        source = self.fx.root / "run/inputs/news/VNM.json"
        original_source = source.read_bytes()
        source.write_bytes(original_source + b"\n")
        with self.assertRaises(ValueError):
            self.run_cohort(symbols=["MWG"], resume=True)
        self.assertEqual(self.llm.calls, 5)
        source.write_bytes(original_source)
        self.assert_complete(self.run_cohort(resume=True))
        self.assertEqual(self.point_path("FPT").read_bytes(), fpt)

    def test_active_cohort_lock_blocks_and_released_lock_resumes(self) -> None:
        """OS lock sống bị chặn, metadata released được tái dùng không xóa file."""
        self.run_cohort(symbols=["FPT"])
        identity = research_cohort.read_envelope(self.output / "cohort.json")
        with PriorRunLock(self.output, canonical_hash(identity)), self.assertRaises(RuntimeError):
            self.run_cohort(resume=True)
        self.assertEqual(self.llm.calls, 5)
        self.assert_complete(self.run_cohort(resume=True))
        self.assertEqual(self.llm.calls, 20)

    def test_v2_durable_response_after_crash_reuses_both_completed_stocks(self) -> None:
        """V2 gọi riêng nhưng dùng Full v1; response đã lưu không bị gọi lại."""
        self.plan["matrix"] = "research_v2"
        save = research_cohort.save_envelope
        def stop(path: Path, payload: dict[str, Any]) -> None:
            save(path, payload)
            if path.parent.name == "v2" and path.name.startswith("MWG-") and payload.get("attempts", [{}])[-1].get("status") == "complete":
                raise Crash()
        with patch.object(research_cohort, "save_envelope", side_effect=stop), self.assertRaises(Crash):
            self.run_cohort()
        self.assertEqual(self.llm.calls, 12)
        saved = {p: p.read_bytes() for p in (self.point_path("FPT"), self.point_path("MWG"),
            self.output / f"v2/FPT-{self.fx.cutoff}.json", self.output / f"v2/MWG-{self.fx.cutoff}.json")}
        result = self.run_cohort(resume=True)
        self.assert_complete(result)
        self.assertEqual(result["primary_status"], "COMPLETE")
        self.assertEqual(self.llm.calls, 24)
        self.assertEqual(len(self.events), 16)
        with patch.object(self.llm, "invoke", side_effect=AssertionError("Không gọi lại complete")):
            self.assertEqual(self.run_cohort(verify_only=True), result)
        for path, original in saved.items():
            self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
