"""Phục hồi node durable, đối soát unknown và audit replay không dùng API thật."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.bayesian_memory import read_json
from core.prior_backtest import PriorBacktestRunner
from core.prior_stage_journal import StageJournal, encode_output, decode_output
import test_prior_backtest_integration as support


class Crash(BaseException):
    """Ngắt đúng sau commit durable, không ghi trạng thái lỗi bổ sung."""


class StageRecoveryTests(unittest.TestCase):
    setUp = support.PriorBacktestIntegrationTests.setUp

    def runner(self) -> PriorBacktestRunner:
        """Runner mới cùng identity, bật journal cho fixture."""
        return PriorBacktestRunner(self.engine, self.adapter, self.builder,
                                   execution_mode="offline_fixture", durable_stages=True)

    def run_one(self, **kwargs):
        return self.runner().run("FPT", output_dir=self.output, cutoffs=(self.fx.cutoff,), **kwargs)

    def journal_path(self) -> Path:
        return self.output / "responses" / f"FPT-{self.fx.cutoff}.json"

    def test_resume_after_each_durable_node_never_invokes_that_node_again(self) -> None:
        save = StageJournal.save
        for name in ("indicator", "pattern", "trend", "full"):
            with self.subTest(name=name):
                self.output = self.fx.root / f"durable-{name}"
                self.events.clear()
                before = self.llm.calls
                crashed = []
                def stop(journal, candidate):
                    save(journal, candidate)
                    node = candidate["nodes"].get(name)
                    if node and node["attempts"][-1]["status"] == "complete" and not crashed:
                        crashed.append(True)
                        raise Crash()
                with patch.object(StageJournal, "save", stop), self.assertRaises(Crash):
                    self.run_one()
                result = self.run_one(resume=True)
                self.assertEqual(result["status"], "complete")
                self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"])
                self.assertEqual(self.llm.calls - before, 5)
                saved = self.journal_path().read_bytes()
                self.run_one(verify_only=True)
                self.assertEqual(self.journal_path().read_bytes(), saved)

    def test_unknown_stops_until_specific_authorization_and_retains_attempt_history(self) -> None:
        save = StageJournal.save
        def lose(journal, candidate):
            node = candidate["nodes"].get("pattern")
            if node and node["attempts"][-1]["status"] == "complete":
                raise OSError("Mất output fixture trước durable")
            save(journal, candidate)
        with patch.object(StageJournal, "save", lose), self.assertRaises(OSError):
            self.run_one()
        events = list(self.events)
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_PATTERN"):
            self.run_one(resume=True)
        report = self.run_one(reconcile=True)
        self.assertEqual(self.events, events)
        unknown = report["points"][0]["nodes"][-1]
        self.assertEqual(unknown["status"], "unknown")
        self.assertNotIn("output", unknown)
        with self.assertRaises(ValueError):
            self.run_one(reconcile=True, authorize_replay=unknown["attempt_id"], replay_reason="")
        self.run_one(reconcile=True, authorize_replay=unknown["attempt_id"], replay_reason="Đã đối soát fixture")
        self.run_one(resume=True)
        self.assertEqual(self.events, ["indicator", "pattern", "pattern", "trend", "full"])
        attempts = read_json(self.journal_path())["payload"]["nodes"]["pattern"]["attempts"]
        self.assertEqual([a["status"] for a in attempts], ["unknown", "complete"])
        self.assertTrue(attempts[0]["authorization"]["reason"])
        with self.assertRaises(ValueError):
            self.run_one(reconcile=True, authorize_replay=unknown["attempt_id"], replay_reason="Không hợp lệ")

    def test_journal_hash_or_missing_durable_output_stops_before_agents(self) -> None:
        self.run_one()
        original = self.journal_path().read_bytes()
        before = self.llm.calls
        self.journal_path().write_bytes(original.replace(b'"version"', b'"bad_key"', 1))
        with self.assertRaises(ValueError):
            self.run_one(verify_only=True)
        self.journal_path().unlink()
        with self.assertRaisesRegex(ValueError, "journal"):
            self.run_one(resume=True)
        self.assertEqual(self.llm.calls, before)

    def test_input_mismatch_blocks_replay_and_message_roundtrip(self) -> None:
        from langchain_core.messages import AIMessage
        message = AIMessage(content="Báo cáo fixture", id="message-fixture")
        output = {"indicator_report": "Tăng", "messages": [message]}
        self.assertEqual(decode_output(encode_output(output)), output)
        with tempfile.TemporaryDirectory() as directory:
            journal = StageJournal(Path(directory) / "journal.json", {"run_signature": "fixture"}, create=True)
            journal.invoke("indicator", lambda state: output, {"stock_name": "FPT", "messages": []})
            with self.assertRaisesRegex(ValueError, "Input node"):
                journal.invoke("indicator", lambda state: self.fail("Cấm gọi lại"), {"stock_name": "VNM", "messages": []})

    def test_full_unknown_is_blocked_and_reconcile_obeys_live_run_lock(self) -> None:
        from core.prior_run_lock import PriorRunLock
        save = StageJournal.save
        def lose(journal, candidate):
            if candidate["nodes"].get("full", {}).get("attempts", [{}])[-1].get("status") == "complete":
                raise OSError("Full chưa durable")
            save(journal, candidate)
        with patch.object(StageJournal, "save", lose), self.assertRaises(OSError):
            self.run_one()
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_FULL"):
            self.run_one(resume=True)
        before = list(self.events)
        report = self.run_one(reconcile=True)
        with PriorRunLock(self.output, report["run_signature"]):
            with self.assertRaises(RuntimeError):
                self.run_one(reconcile=True)
        self.assertEqual(self.events, before)
        self.assertEqual(report["points"][0]["nodes"][-1]["node"], "full")

    def test_reconcile_refuses_changed_identity_and_wrong_attempt(self) -> None:
        self.run_one()
        before = self.llm.calls
        with self.assertRaises(ValueError):
            self.run_one(reconcile=True, authorize_replay="not-an-attempt", replay_reason="fixture")
        changed = PriorBacktestRunner(self.engine, self.adapter, self.builder, execution_mode="offline_fixture",
                                      durable_stages=True, quota_policy="request_admission_v2")
        with self.assertRaisesRegex(ValueError, "(?i)signature"):
            changed.run("FPT", output_dir=self.output, cutoffs=(self.fx.cutoff,), reconcile=True)
        self.assertEqual(self.llm.calls, before)

    def test_cli_reconcile_never_reads_key_and_transport_rejects_network(self) -> None:
        from scripts import run_bayesian_ablation as cli
        def execute(args, plan, adapter, config, key, pacer, client):
            self.assertTrue(args.reconcile)
            self.assertEqual(key, "offline-verifier-no-network")
            with self.assertRaises(AssertionError):
                client.get("https://api.groq.com/must-not-send")
        with patch("sys.argv", ["runner", "--reconcile"]), \
             patch.object(cli, "verify_inputs", return_value={"cutoffs": [self.fx.cutoff], "signal_config": {}}), \
             patch.object(cli, "build_adapter"), patch.object(cli, "tokenizer_cached", return_value=False), \
             patch.object(cli, "dotenv_values", side_effect=AssertionError("Cấm đọc key")), \
             patch.object(cli, "GroqPacer"), patch.object(cli, "PriorRunLock"), \
             patch.object(cli, "execute", side_effect=execute) as run:
            cli.main()
        run.assert_called_once()
