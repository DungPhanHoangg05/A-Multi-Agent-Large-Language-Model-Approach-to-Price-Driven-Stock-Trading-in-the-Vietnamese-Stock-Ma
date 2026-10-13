"""Protocol holdout tổng hợp, runner thật và LLM giả; không mở dữ liệu 2024 thật."""

from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.backtest_engine import PRIOR_BRANCH_MODES
from core.candidate_cohort import CANDIDATES, prepare_candidate_plan
from core.candidate_selection import evaluate_selection, write_selection
from core.holdout_protocol import _decision, _inherit, prepare_holdout_plan, selection_binding
from core.prior_backtest import PriorBacktestRunner
from core.research_cohort import read_envelope, save_envelope
from test_candidate_cohort import CandidateSetup


class HoldoutSetup(CandidateSetup):
    """Development fixture luôn BLOCKED; C3 chỉ là primary kiểm protocol offline."""

    def lock_development(self, *, cli: bool = False) -> None:
        """Khóa run nguồn riêng, giữ report/selection bất biến trước fixture holdout."""
        if cli:
            from core.groq_pacing import MODEL_LIMITS
            parent = read_envelope(self.parent)
            parent["inputs"].update(limits=MODEL_LIMITS, execution_dir="unused", news_dir="unused",
                execution_manifest_sha256="a", model={"freeze_as_of_date":"2022-12-30", "artifact_path":"unused",
                    "artifact_sha256":"a", "source_path":"unused2", "source_sha256":"a"},
                news_sources={s:{"snapshot_sha256":"a"} for s in self.plan["symbol_cutoffs"]})
            save_envelope(self.parent, parent)
            self.refresh_adapter()
            self.plan_path = self.fx.root / "cli_development.json"
            self.plan = prepare_candidate_plan(self.parent, self.plan_path, self.adapter, index_path="index.json")
        self.development_runner = self.runner
        self.development_output = self.output
        result = self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
        self.selection_path = self.output / "candidate_selection_v1.json"
        write_selection(self.selection_path, self.output / "report.json", result)
        self.binding = selection_binding(self.fx.root, self.plan_path, self.output, self.selection_path,
            None, self.fx.root / "ledger.json")
        self.output = self.fx.root / "holdout_results"
        self.holdout_path = self.fx.root / "holdout_plan.json"
        self.adapter = self.fx.adapter()
        self.runner = PriorBacktestRunner(self.engine, self.adapter, self.builder,
            execution_mode="offline_fixture", durable_stages=True)

    def prepare_holdout(self) -> None:
        """Chỉ tạo plan trong workspace tạm; nguồn development vẫn được verify thật."""
        self.holdout = prepare_holdout_plan(self.holdout_path, self.adapter, self.binding,
            development_runner=self.development_runner)

    def run_holdout(self, **options):
        """Giữ nguyên API chạy/resume/verify, thêm runner nguồn fixture riêng."""
        return self.runner.run_cohort(self.holdout, output_dir=self.output,
            development_runner=self.development_runner, **options)


class HoldoutProtocolTests(HoldoutSetup, unittest.TestCase):
    def test_four_stocks_one_full_caps_versions_roles_and_readonly_resume(self) -> None:
        self.lock_development()
        self.prepare_holdout()
        calls, events = self.llm.calls, len(self.events)
        # Metadata owner/phục hồi khóa OS đổi sau mỗi lượt verify; checkpoint không đổi.
        before = {p:p.read_bytes() for p in self.development_output.rglob("*.json")
            if p.name not in ("run.owner.json", "run.recovery.json")}
        self.assertFalse(self.output.exists())
        result = self.run_holdout()
        self.assertEqual(self.llm.calls-calls, 44)
        self.assertEqual(self.events[events:], ["indicator", "pattern", "trend", "full"]*4)
        self.assertEqual(result["matrix"], [*PRIOR_BRANCH_MODES, *CANDIDATES])
        self.assertEqual(result["report_version"], "research_report_v6")
        self.assertEqual(result["selection_evidence_status"], "NOT_APPLICABLE")
        self.assertEqual(result["research_primary"], "C3")
        self.assertIsNone(result["selection_decision"]["research_candidate"])
        self.assertEqual(result["selection_decision"]["scope"], "FIXTURE_PROTOCOL_ONLY")
        self.assertEqual(result["branch_roles"]["C3"], "RESEARCH_PRIMARY")
        self.assertEqual(result["branch_roles"]["original"], "CONTROL")
        self.assertEqual(result["branch_roles"]["C3_stats_only"], "ABLATION")
        self.assertEqual(read_envelope(self.output/"cohort.json")["identity_version"], "research_cohort_identity_v4")
        for name in CANDIDATES:
            doc = self.checkpoint(name)[1]
            self.assertEqual(doc["checkpoint_version"], "holdout_candidate_decision_v1")
            self.assertLess(len(doc["prompt"]), 6500)
            self.assertLessEqual(len(doc["request"]["prefix"]) if doc["request"] else 0, 600)
        with patch.object(self.llm, "invoke", side_effect=AssertionError("Không gọi lại LLM")):
            self.assertEqual(self.run_holdout(verify_only=True), result)
            self.assertEqual(self.run_holdout(resume=True), result)
        self.assertEqual({p:p.read_bytes() for p in before}, before)
        with self.assertRaises(ValueError):
            evaluate_selection(result, gates_passed=True)
        from core.paired_candidate_report import read_report
        read_report(self.output/"report.json", result)
        changed = deepcopy(result)
        changed["research_primary"] = "C0"
        save_envelope(self.output/"report.json", changed)
        with self.assertRaises(ValueError):
            read_report(self.output/"report.json", result)

    def test_saved_response_crash_resumes_without_repeating_full_or_decision(self) -> None:
        self.lock_development()
        self.prepare_holdout()
        import core.research_cohort as cohort
        save = cohort.save_envelope
        def crash(path, payload):
            save(path, payload)
            if path.is_relative_to(self.output) and path.parent.name == "C2" and payload.get("attempts", [{}])[-1].get("status") == "complete":
                raise OSError("Fixture crash sau response durable")
        calls = self.llm.calls
        with patch.object(cohort, "save_envelope", side_effect=crash), self.assertRaises(OSError):
            self.run_holdout(symbols=["FPT"])
        self.assertEqual(self.llm.calls-calls, 8)
        events = list(self.events)
        report = self.run_holdout(verify_only=True)
        self.assertEqual(report["stocks"]["FPT"]["coverage"]["C2"]["complete"], 1)
        self.assertEqual(report["primary_status"], "INCOMPLETE")
        self.run_holdout(resume=True, symbols=["FPT"])
        self.assertEqual(self.llm.calls-calls, 11)
        self.assertEqual(self.events, events)

    def test_unknown_blocks_other_stock_until_exact_uuid_authorized(self) -> None:
        self.lock_development()
        self.prepare_holdout()
        import core.research_cohort as cohort
        save = cohort.save_envelope
        def crash(path, payload):
            if path.is_relative_to(self.output) and path.parent.name == "C2" and payload.get("attempts", [{}])[-1].get("status") == "complete":
                raise OSError("Fixture mất response trước durable")
            save(path, payload)
        with patch.object(cohort, "save_envelope", side_effect=crash), self.assertRaises(OSError):
            self.run_holdout(symbols=["FPT"])
        calls, events = self.llm.calls, list(self.events)
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.run_holdout(resume=True, symbols=["MWG"])
        unknown = [r for r in self.run_holdout(reconcile=True)["decisions"] if r["status"] == "unknown"]
        self.assertEqual([(r["branch"]) for r in unknown], ["C2"])
        self.assertEqual(self.llm.calls, calls)
        self.run_holdout(reconcile=True, authorize_replay=unknown[0]["attempt_id"], replay_reason="Đối soát fixture")
        self.run_holdout(resume=True, symbols=["FPT"])
        self.assertEqual(self.llm.calls, calls+4)
        self.assertEqual(self.events, events)

    def test_schema_registry_calendar_economics_and_missing_selection_block_before_llm(self) -> None:
        self.lock_development()
        self.prepare_holdout()
        calls = self.llm.calls
        mutations = (lambda p:p.pop("selection_binding"), lambda p:p.update(plan_version="research_cohort_plan_v3"),
            lambda p:p["selection_decision"].update(primary_branch="C0"),
            lambda p:p["candidate_registry"]["economic_contract"].update(fee=.0),
            lambda p:p["inputs"]["signal_config"]["models"].update(agent_llm_model="other/model"),
            lambda p:p["symbol_cutoffs"]["FPT"].append(self.cutoffs[1]),
            lambda p:p["price_index"].update(identity="0"*64))
        for mutate in mutations:
            changed = deepcopy(self.holdout)
            mutate(changed)
            with self.assertRaises(ValueError):
                self.runner.run_cohort(changed, output_dir=self.output, development_runner=self.development_runner)
        with self.assertRaises(ValueError):
            self.runner.run_cohort(self.holdout, output_dir=self.output)
        self.assertEqual(self.llm.calls, calls)
        self.assertFalse(self.output.exists())

    def test_cli_prepare_dryrun_verify_and_invalid_selection_never_read_key_or_http(self) -> None:
        self.lock_development(cli=True)
        from scripts import run_bayesian_ablation as cli
        import core.holdout_protocol as protocol
        verify = protocol._verify_development
        def fixture_verify(root, binding, development_runner=None):
            return verify(root, binding, self.development_runner)
        with patch.object(protocol, "_verify_development", side_effect=fixture_verify), \
             patch.object(cli, "ROOT", self.fx.root), patch.object(cli, "build_adapter", return_value=self.adapter), \
             patch("core.pilot_readiness.sha_file", return_value="a"), patch.object(cli, "make_builder", return_value=self.builder), \
             patch.object(cli, "PriorBacktestRunner", return_value=self.runner), \
             patch.object(cli, "dotenv_values", side_effect=AssertionError("Cấm key")), \
             patch("socket.socket.connect", side_effect=AssertionError("Cấm HTTP")):
            argv = ["runner", "--prepare", "--plan", str(self.plan_path), "--holdout-plan", str(self.holdout_path),
                "--development-run", str(self.development_output), "--output-dir", str(self.output), "--ledger", str(self.fx.root/"ledger.json")]
            with patch("sys.argv", argv):
                cli.main()
            self.holdout = read_envelope(self.holdout_path)
            self.assertFalse(self.output.exists())
            result = self.run_holdout(symbols=["FPT"], ledger_path=self.fx.root/"ledger.json")
            from core.research_metrics import http_telemetry
            result["telemetry"] = http_telemetry([], result["run_signatures"], {})
            save_envelope(self.output/"report.json", result)
            calls = self.llm.calls
            for mode in ("--dry-run", "--verify-only", "--verify-report", "--reconcile"):
                with patch("sys.argv", ["runner", mode, "--plan", str(self.holdout_path), "--output-dir", str(self.output),
                        "--ledger", str(self.fx.root/"ledger.json")]):
                    cli.main()
            self.selection_path.unlink()
            with patch("sys.argv", ["runner", "--preflight", "--plan", str(self.holdout_path), "--output-dir", str(self.output)]), self.assertRaises(ValueError):
                cli.main()
            self.assertEqual(self.llm.calls, calls)


class HoldoutCalendarTests(unittest.TestCase):
    def test_w5_checksum_calendar_inheritance_and_not_promoted_primary(self) -> None:
        from core.research_input_lock import _smoke_plan
        from core.prior_evidence_v2 import normalize_evidence_config
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calendar = {s:[f"2024-{month:02d}-{day:02d}" for month in range(1, 5) for day in (2,9,16,23)]
                for s in ("FPT", "MWG", "VCB", "VNM")}
            lock = {"cohorts":{"smoke":{s:["2023-01-02"] for s in calendar}, "development_2023":{s:["2023-02-02"] for s in calendar},
                "holdout_2024":calendar}, "inputs":{}, "sources":{}, "evidence_config_technical_defaults":normalize_evidence_config()}
            lock_path = root/"lock.json"
            save_envelope(lock_path, lock)
            parent = _smoke_plan(lock)
            parent["inputs"]["input_lock"] = {"path":"lock.json", "sha256":hashlib.sha256(lock_path.read_bytes()).hexdigest()}
            save_envelope(root/"parent.json", parent)
            development = {"split":"development_2023", "parent":{"path":"parent.json", "split":"development_2023"}}
            before = lock_path.read_bytes()
            base, sources = _inherit(root, development)
            self.assertEqual(base["symbol_cutoffs"], calendar)
            self.assertEqual(base["split"], "holdout_2024")
            self.assertEqual(sources["lock.json"], hashlib.sha256(before).hexdigest())
            self.assertEqual(_decision(development, {"nomination_status":"NOT_PROMOTED", "research_candidate":"C1", "deployment_choice":"original"}),
                {"scope":"DEVELOPMENT_SELECTION", "nomination_status":"NOT_PROMOTED", "research_candidate":"C1", "primary_branch":"C1", "deployment_choice":"original", "risk_policy":"OFF"})
            lock["cohorts"]["holdout_2024"]["FPT"][0] = "2024-01-03"
            save_envelope(lock_path, lock)
            with self.assertRaises(ValueError):
                _inherit(root, development)
