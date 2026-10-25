"""Diagnostics nguồn và producer receipt bốn gate; mọi log tổng hợp đều là fixture."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from core.research_cohort import read_envelope, save_envelope
from core.unified_bayes_contracts import sha
from core.unified_bayes_validation import COMMANDS, read_diagnostics, read_validation, run_gates
from unified_validation_test_support import ValidationFixture


class ValidationTests(ValidationFixture, unittest.TestCase):
    """Số liệu mô tả phải tái dựng được và không mở readiness hoặc API."""

    def test_diagnostics_roundtrip_has_no_http_or_query_evaluation(self) -> None:
        result = self.diagnostic()
        path = self.fx.root / "diagnostics.json"
        save_envelope(path, result)
        self.assertEqual(read_diagnostics(path, self.diagnostic()), result)
        self.assertEqual(result["overall"]["point_count"], 4)
        self.assertEqual(sum(v["point_count"] for v in result["by_symbol"].values()), 4)
        self.assertEqual(self.fx.calls, [])
        self.assertEqual(self.fx.evaluations, [])
        self.assertFalse(result["confirmation_allowed"])
        self.assertFalse(result["nomination_allowed"])
        self.assertEqual(result["readiness_stage"], "PENDING_U10_09")

    def test_branch_budgets_aliases_and_off_are_independently_counted(self) -> None:
        result = self.diagnostic()
        for row in result["points"]:
            for branch, actual in row["branches"].items():
                packet = self.plan["requests"][row["point_id"]]["packets"][branch]
                self.assertEqual(actual["prefix_chars"], len(packet["prefix"]))
                self.assertLess(actual["prompt_chars"], 6500)
                self.assertLessEqual(actual["prefix_chars"], 600)
                if branch in ("Original", "A_reference", "U_stats"):
                    self.assertEqual(actual["alias_count"], 0)
                if actual["canonical_off_eligible"]:
                    self.assertFalse(actual["prior_visible"])
                    self.assertEqual(packet["body"], self.plan["requests"][row["point_id"]]["packets"]["Original"]["body"])
        self.assertEqual(result["overall"]["branches"]["Original"]["visible_count"], 0)

    def test_upstream_bundle_and_restored_full_have_distinct_hash_domains(self) -> None:
        for upstream in self.cohort.upstream.values():
            upstream["shared_sha256"] = "b" * 64
        self.plan = self.cohort.plan(self.fx.llm)
        result = self.diagnostic()
        self.assertEqual(result["overall"]["point_count"], 4)
        for pid, request in self.plan["requests"].items():
            self.assertNotEqual(request["upstream"]["shared_sha256"], self.cohort.prepared[pid].shared_sha256)
            self.assertEqual(len({p["shared_sha256"] for p in request["packets"].values()}), 1)

    def test_saved_diagnostics_cannot_reseal_counts_or_claim_readiness(self) -> None:
        expected = self.diagnostic()
        for field, value in (("http_attempts", 999), ("readiness_stage", "READY"), ("confirmation_allowed", True)):
            with self.subTest(field=field):
                changed = deepcopy(expected)
                changed[field] = value
                path = self.fx.root / "changed.json"
                save_envelope(path, changed)
                with self.assertRaises(ValueError):
                    read_diagnostics(path, expected)

    def test_cli_prepare_and_default_verify_do_not_create_run_or_ledger(self) -> None:
        from scripts import validate_unified_bayes as cli
        source = self.fx.root / "source"
        source.mkdir()
        save_envelope(source / "plan.json", {"inputs": {"signal_config": {"models": self.plan["models"]}}})
        path = self.fx.root / "plan.json"
        save_envelope(path, self.plan)
        memory = self.fx.root / "memory.json"
        save_envelope(memory, self.context.memory.payload)
        output = self.fx.root / "validation"
        with patch.multiple(cli, ROOT=self.fx.root, SOURCE=source, PLAN_PATH=path, MEMORY_PATH=memory, OUTPUT=output), \
             patch.object(cli, "load_source", return_value=self.cohort), \
             patch("dotenv.dotenv_values", side_effect=AssertionError("Đọc key")), patch("builtins.print"):
            for flags in (("--prepare",), ()):
                with patch.object(sys, "argv", ["validation", "--diagnostics", str(output / "diag.json"), *flags]):
                    cli.main()
        self.assertEqual(list(output.iterdir()), [output / "diag.json"])
        self.assertEqual(self.fx.calls, [])
        self.assertEqual(self.fx.evaluations, [])

    def fixture_process(self, command, **kwargs):
        """Thay subprocess để test giao thức; không nhận làm log hồi quy dự án."""
        self.assertEqual(command[0], sys.executable)
        index = self.process_index
        self.process_index += 1
        name = list(COMMANDS)[index]
        self.assertEqual(command[1:], ["-X", "utf8", *COMMANDS[name]])
        logs = {"compileall": "\n".join(f"Listing '{part}'..." for part in ("agents", "core", "data_manager", "scripts", "tests", "utils")),
                "unit": "Ran 1 test in 0.1s\n\nOK\n", "leakage": "Ran 1 test in 0.1s\n\nOK\n",
                "e2e": "ALL PIPELINE CHECKS SUCCESSFUL"}
        kwargs["stdout"].write(logs[name].encode("utf-8"))
        return SimpleNamespace(returncode=0)

    def fixture_audit(self) -> tuple[Path, dict]:
        """Receipt chỉ thuộc temp test, với log fixture ghi rõ trong docstring."""
        expected = self.diagnostic()
        self.process_index = 0
        with patch("core.unified_bayes_validation.subprocess.run", side_effect=self.fixture_process):
            path = run_gates(self.plan, expected, self.fx.root / "validation", notify=lambda _: None)
        return path, expected

    def test_receipt_binds_four_commands_and_can_be_verified(self) -> None:
        path, expected = self.fixture_audit()
        audit = read_validation(path, self.plan, expected)
        self.assertEqual(self.process_index, 4)
        self.assertEqual(audit["technical_gates_sha256"], sha(path.parent / "technical_gates.json"))
        self.assertFalse((self.fx.root / "cohort").exists())
        self.assertEqual(self.fx.calls, [])
        self.assertEqual(self.fx.evaluations, [])

    def test_failed_gate_stops_without_publishing_pass_receipt(self) -> None:
        expected = self.diagnostic()
        self.process_index = 0
        def fail(command, **kwargs):
            result = self.fixture_process(command, **kwargs)
            return SimpleNamespace(returncode=1) if self.process_index == 2 else result
        root = self.fx.root / "failed"
        with patch("core.unified_bayes_validation.subprocess.run", side_effect=fail), self.assertRaises(ValueError):
            run_gates(self.plan, expected, root, notify=lambda _: None)
        self.assertEqual(self.process_index, 2)
        self.assertEqual(list(root.rglob("technical_gates.json")), [])
        self.assertEqual(list(root.rglob("validation_audit.json")), [])
        self.assertEqual(read_envelope(next(root.rglob("progress.json")))["checks"]["unit"]["status"], "FAIL")

    def test_zero_exit_with_invalid_log_is_not_accepted(self) -> None:
        expected = self.diagnostic()
        def invalid(command, **kwargs):
            kwargs["stdout"].write(b"fixture: no verification performed\n")
            return SimpleNamespace(returncode=0)
        root = self.fx.root / "invalid"
        with patch("core.unified_bayes_validation.subprocess.run", side_effect=invalid), self.assertRaises(ValueError):
            run_gates(self.plan, expected, root, notify=lambda _: None)
        self.assertEqual(list(root.rglob("validation_audit.json")), [])

    def test_audit_rejects_log_receipt_diagnostic_and_command_tamper(self) -> None:
        path, expected = self.fixture_audit()
        for name in ("unit.log", "technical_gates.json", "diagnostics.json"):
            with self.subTest(file=name):
                target = path.parent / name
                original = target.read_bytes()
                target.write_bytes(original + b" ")
                with self.assertRaises(ValueError):
                    read_validation(path, self.plan, expected)
                target.write_bytes(original)
        value = read_envelope(path)
        value["runs"]["leakage"]["command"] = ["python", "-c", "pass"]
        save_envelope(path, value)
        with self.assertRaises(ValueError):
            read_validation(path, self.plan, expected)


if __name__ == "__main__":
    unittest.main()
