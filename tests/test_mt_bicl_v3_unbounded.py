"""Kiểm bỏ trần giờ với counter đã đầy, giữ source/ledger/UUID và lịch độc lập."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v3_budget import BudgetStop
from core.mt_bicl_v3_transport import BudgetHTTP
from core.mt_bicl_v3_unbounded import (RuntimeSession, POLICY, SOURCES, USER_REPLY,
    ENTRYPOINT, OUTPUT, VERSION, CODE, byte_sha, verify_policy, legacy_module, main, verify)
from core.mt_bicl_v2_io import read_envelope, write_envelope


class UnboundedTests(unittest.TestCase):
    """Mỗi test fixture riêng, không key/API thật hoặc counter tài khoản."""

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = [datetime(2026, 11, 1, tzinfo=timezone.utc)]
        self.policy = {"data_stop": "2026-11-07T23:59:59+07:00"}
        self.counter = self.root/"outputs/bayesian_benchmark/mt_bicl_v3/runtime_budget.json"
        self.counter.parent.mkdir(parents=True)
        self.counter.write_bytes(b'{"elapsed_seconds":64800,"active_since":null}')
        self.original = self.counter.read_bytes()

    def session(self) -> RuntimeSession:
        return RuntimeSession(self.root, "development", now=lambda: self.now[0])

    def test_full_counter_and_25h_wait_no_longer_stop_HTTP_or_write_history(self) -> None:
        with patch("core.mt_bicl_v3_unbounded.verify_policy", return_value=self.policy):
            with self.session() as session:
                session.check(25*3600)
                sent = []
                transport = BudgetHTTP(session, httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(200)))
                self.assertEqual(transport.handle_request(httpx.Request("POST", "https://offline.invalid")).status_code, 200)
                self.now[0] += timedelta(days=2)
                session.check()
                session.checkpoint()
                self.assertEqual(len(sent), 1)
        self.assertEqual(self.counter.read_bytes(), self.original)

    def test_overnight_resume_and_CtrlC_do_not_charge_or_reset(self) -> None:
        with patch("core.mt_bicl_v3_unbounded.verify_policy", return_value=self.policy):
            with self.assertRaises(KeyboardInterrupt):
                with self.session(): raise KeyboardInterrupt
            self.now[0] += timedelta(days=1)
            with self.session() as session: session.check(86400)
        self.assertEqual(self.counter.read_bytes(), self.original)

    def test_calendar_and_invalid_wait_remain_independent(self) -> None:
        with patch("core.mt_bicl_v3_unbounded.verify_policy", return_value=self.policy):
            with self.session() as session:
                for value in (-1., float("nan"), float("inf"), True):
                    with self.assertRaises(ValueError): session.check(value)
                with self.assertRaises(BudgetStop): session.check(99*86400)
                self.now[0] = datetime(2026, 11, 8, tzinfo=timezone.utc)
                with self.assertRaises(BudgetStop): session.check()
            with self.assertRaises(BudgetStop): self.session().__enter__()
        self.assertEqual(self.counter.read_bytes(), self.original)

    def test_same_OS_lock_blocks_concurrent_session_and_releases(self) -> None:
        with patch("core.mt_bicl_v3_unbounded.verify_policy", return_value=self.policy):
            with self.session():
                with self.assertRaises(RuntimeError): self.session().__enter__()
            with self.session() as session: session.check()

    def fixture_policy(self) -> dict:
        """Dựng receipt/Git giả cho kiểm các ràng buộc hash, không đổi source repository."""
        parent = "docs/plan/week11/budget_v3.json"
        path = self.root/parent
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"data_stop": self.policy["data_stop"], "release_and_start_by": "2026-11-05T23:59:59+07:00"}), encoding="utf-8")
        for name in SOURCES:
            file = self.root/name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("source fixture", encoding="utf-8")
        slot = self.root/OUTPUT/"run/research/slots/0000.json"
        slot.parent.mkdir(parents=True)
        slot.write_text("complete fixture", encoding="utf-8")
        rows = [{"id": "fixture", "status": "unknown", "reserved_tokens": 4000}]
        ledger = self.root/"outputs/oos_pilot/api_usage.json"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(json.dumps({"requests": rows}), encoding="utf-8")
        policy = {"authority": "EXPLICIT_USER_INSTRUCTION_2026_10_31", "user_reply": USER_REPLY,
            "scope": "SAME_V3_RUN_OPERATIONAL_ONLY", "runtime_hour_limit_enabled": False,
            "elapsed_counter_enabled": False, "crash_gap_charging_enabled": False,
            "calendar_changed": False, "scientific_protocol_changed": False,
            "source_commit": "fixture", "source_sha256": {n: byte_sha(self.root/n) for n in SOURCES},
            "parent_sha256": {parent: byte_sha(path)}, "retired_counter": {"path": self.counter.relative_to(self.root).as_posix(), "sha256": byte_sha(self.counter)},
            "complete_slots_sha256": {"0000.json": byte_sha(slot)}, "ledger_baseline": {"count": 1, "requests_prefix_sha256": content_hash(rows)},
            "data_stop": self.policy["data_stop"], "release_and_start_by": "2026-11-05T23:59:59+07:00"}
        write_envelope(self.root/POLICY, VERSION, policy)
        return policy

    def test_policy_allows_append_but_rejects_mutated_ledger_or_completed_slot(self) -> None:
        self.fixture_policy()
        with patch("core.mt_bicl_v3_unbounded.git_bytes", side_effect=lambda root, rev, name: (root/name).read_bytes()):
            verify_policy(self.root)
            path = self.root/"outputs/oos_pilot/api_usage.json"
            ledger = json.loads(path.read_text())
            ledger["requests"].append({"id": "new", "status": 200})
            path.write_text(json.dumps(ledger))
            verify_policy(self.root)
            ledger["requests"][0]["reserved_tokens"] = 0
            path.write_text(json.dumps(ledger))
            with self.assertRaises(ValueError): verify_policy(self.root)
            ledger["requests"][0]["reserved_tokens"] = 4000
            path.write_text(json.dumps(ledger))
            (self.root/OUTPUT/"run/research/slots/0000.json").write_text("changed")
            with self.assertRaises(ValueError): verify_policy(self.root)

    def test_policy_rejects_source_parent_history_or_authority_change(self) -> None:
        policy = self.fixture_policy()
        with patch("core.mt_bicl_v3_unbounded.git_bytes", side_effect=lambda root, rev, name: (root/name).read_bytes()):
            for name in (SOURCES[0], next(iter(policy["parent_sha256"])), self.counter.relative_to(self.root).as_posix()):
                path = self.root/name
                old = path.read_bytes()
                path.write_bytes(old+b" ")
                with self.assertRaises(ValueError): verify_policy(self.root)
                path.write_bytes(old)
            for key in ("runtime_hour_limit_enabled", "elapsed_counter_enabled", "crash_gap_charging_enabled", "scientific_protocol_changed"):
                changed = deepcopy(policy)
                changed[key] = True
                write_envelope(self.root/POLICY, VERSION, changed)
                with self.assertRaises(ValueError): verify_policy(self.root)
            write_envelope(self.root/POLICY, VERSION, policy)
            with patch("core.mt_bicl_v3_unbounded.git_bytes", return_value=b"not committed"):
                with self.assertRaises(ValueError): verify_policy(self.root)

    def test_frozen_cli_has_same_main_with_only_session_and_verifier_replaced(self) -> None:
        root = Path(__file__).resolve().parents[1]
        manifest = read_envelope(root/"docs/plan/week11/development_manifest_v3.json", "utility_icl_development_manifest_v3")
        module = legacy_module(root, manifest)
        self.assertIs(module.RuntimeBudget, RuntimeSession)
        self.assertEqual(module.verify.__module__, "core.mt_bicl_v3_unbounded")
        self.assertEqual(module.main.__code__.co_filename, str(root/ENTRYPOINT))

    def test_verified_entrypoint_override_cannot_override_scientific_sources(self) -> None:
        snapshot = {"protocol": {"fixture": True}}
        checksum = __import__("hashlib").sha256(b"frozen").hexdigest()
        manifest = {"snapshot_sha256": content_hash(snapshot), "layout": "fixture", "source_commit": "fixture",
                    "source_sha256": {name: checksum for name in CODE}}
        for name in CODE:
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"changed" if name == ENTRYPOINT else b"frozen")
        with patch("core.mt_bicl_v3_unbounded.verify_policy"), patch("core.mt_bicl_v3_unbounded.collect", return_value=snapshot), patch("core.mt_bicl_v3_unbounded.layout", return_value="fixture"):
            with patch("core.mt_bicl_v3_unbounded.read_envelope", side_effect=lambda path, version: manifest if version == "utility_icl_development_manifest_v3" else snapshot):
                with patch("core.mt_bicl_v3_unbounded.git_bytes", return_value=b"frozen"):
                    self.assertEqual(verify(self.root, require_anchor=False), (manifest, snapshot))
                    (self.root/"core/mt_bicl_v3_run.py").write_bytes(b"changed")
                    with self.assertRaises(ValueError): verify(self.root, require_anchor=False)

    def test_verify_only_entrypoint_does_not_load_live_cli(self) -> None:
        with patch("sys.argv", ["continue_mt_bicl_v3.py", "--verify-only"]), redirect_stdout(io.StringIO()):
            with patch("core.mt_bicl_v3_unbounded.verify_only", return_value={"status": "PASS", "complete_slots": 568, "next_slot": None}):
                with patch("core.mt_bicl_v3_unbounded.legacy_module", side_effect=AssertionError("Cấm live CLI")):
                    self.assertEqual(main(self.root), 0)

    def test_unknown_HTTP_same_UUID_recovers_with_exhausted_counter(self) -> None:
        import test_mt_bicl_v3_recovery as recovery
        fixture = recovery.RecoveryTests("test_unknown_HTTP_reserve_kept_and_same_UUID_retried")
        fixture.setUpClass()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.manifest["layout"]["slots"] = fixture.manifest["layout"]["slots"][:1]
        fixture.interrupt_HTTP = True
        counter = fixture.root/"outputs/bayesian_benchmark/mt_bicl_v3/runtime_budget.json"
        counter.parent.mkdir(parents=True)
        counter.write_bytes(self.original)
        with patch("core.mt_bicl_v3_unbounded.verify_policy", return_value=self.policy):
            with self.assertRaises(KeyboardInterrupt):
                with RuntimeSession(fixture.root, "development", now=lambda: self.now[0]) as session:
                    fixture.budget = fixture.http._transport.runtime = session
                    fixture.execute()
            old = deepcopy(fixture.pacer.state["requests"][0])
            fixture.interrupt_HTTP = False
            fixture.now[0] += 86400.
            self.now[0] += timedelta(days=1)
            with RuntimeSession(fixture.root, "development", now=lambda: self.now[0]) as session:
                fixture.budget = fixture.http._transport.runtime = session
                fixture.execute()
            self.assertEqual(fixture.pacer.state["requests"][0], old)
            self.assertEqual(fixture.calls[-1]["checkpoint_attempt_id"], old["checkpoint_attempt_id"])
        self.assertEqual(counter.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
