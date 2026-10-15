"""Entrypoint quota mới giữ parser/runner cũ, tự preflight khi key đổi và không dùng API thật."""

import hashlib
from unittest.mock import patch

from core.bayesian_memory import read_json
from core.provider_quota import ProviderQuotaPacer
from core.research_cohort import save_envelope
from test_provider_quota_leakage import AmendmentFixture
from scripts import run_provider_validation as cli


class ProviderValidationCliTests(AmendmentFixture):
    """Kiểm adapter factory thực với CLI giả không gọi mạng hoặc thay Decision."""

    def setUp(self) -> None:
        super().setUp()
        self.stack.enter_context(patch.object(cli,"ROOT",self.root))
        self.env = self.stack.enter_context(patch.object(cli.legacy,"dotenv_values",return_value={"GROQ_API_KEY":"fixture-A"}))
        self.builder = self.stack.enter_context(patch.object(cli.legacy,"make_builder",return_value=object()))
        self.calls = []
        self.pacers = []
        self.stack.enter_context(patch.object(cli.legacy,"main",side_effect=self.legacy_main))
        self.preflight = self.stack.enter_context(patch.object(cli.legacy,"preflight",side_effect=self.preflight_response))
        self.stack.enter_context(patch("socket.socket.connect",side_effect=AssertionError("Không gọi mạng trong fixture")))

    def arguments(self, mode: str) -> list[str]:
        """Đối số CLI ở cùng plan/run/ledger đã khóa."""
        return [mode,"--plan",str(self.plan_path),"--output-dir",str(self.run),"--ledger",str(self.ledger),
                "--quota-policy","request_admission_v2"]

    def legacy_main(self) -> None:
        """Mô phỏng ranh giới parser/credential/factory; không mô phỏng thuật toán agent."""
        import sys
        self.calls.append(list(sys.argv[1:]))
        online = "--run" in sys.argv or "--preflight" in sys.argv
        key = cli.legacy.dotenv_values(self.root/".env")["GROQ_API_KEY"] if online else "offline"
        pacer = cli.legacy.GroqPacer(self.ledger,policy="request_admission_v2",clock=lambda:100000.)
        self.pacers.append(pacer)
        if online:
            cli.legacy.make_builder({},key,None)

    def preflight_response(self, builder: object) -> None:
        """Hai response fixture thành công được ghi bởi pacer thật."""
        pacer = self.pacers[-1]
        for model in ("openai/gpt-oss-20b","qwen/qwen3.8-27b"):
            row = pacer.reserve(model,1)
            row.update(status=200,total_tokens=1)
            pacer.save()

    def test_offline_verify_never_reads_key_and_restores_factories(self) -> None:
        original = cli.legacy.GroqPacer
        cli.execute(self.arguments("--verify-only"))
        self.env.assert_not_called()
        self.preflight.assert_not_called()
        self.assertIs(cli.legacy.GroqPacer,original)

    def test_new_key_auto_preflights_once_same_key_resume_reuses_proof(self) -> None:
        arguments = [*self.arguments("--run"),"--resume"]
        cli.execute(arguments)
        self.assertEqual(self.preflight.call_count,1)
        self.assertEqual(len(read_json(self.ledger)["requests"]),3)
        cli.execute(arguments)
        self.assertEqual(self.preflight.call_count,1)
        self.env.return_value={"GROQ_API_KEY":"fixture-B"}
        cli.execute(arguments)
        self.assertEqual(self.preflight.call_count,2)
        records=read_json(self.ledger)["requests"]
        self.assertEqual(len(records),5)
        self.assertEqual(len({r["credential_scope"] for r in records[1:]}),2)
        self.assertNotIn("fixture-A",self.ledger.read_text())
        self.assertNotIn("fixture-B",self.ledger.read_text())

    def test_missing_or_tampered_amendment_blocks_before_credentials(self) -> None:
        target=self.run / cli.AMENDMENT_FILE
        target.unlink()
        with self.assertRaises(FileNotFoundError):
            cli.execute(self.arguments("--run"))
        self.env.assert_not_called()

    def test_restores_factories_and_argv_after_legacy_exception(self) -> None:
        import sys
        previous=sys.argv
        original=cli.legacy.GroqPacer
        cli.legacy.main.side_effect=ValueError("Lỗi fixture")
        with self.assertRaisesRegex(ValueError,"Lỗi fixture"):
            cli.execute(self.arguments("--verify-only"))
        self.assertIs(cli.legacy.GroqPacer,original)
        self.assertIs(sys.argv,previous)

    def test_unsupported_holdout_or_prepare_rejected_before_credentials(self) -> None:
        with self.assertRaises(ValueError):
            cli.execute([*self.arguments("--run"),"--holdout-plan","holdout.json"])
        self.env.assert_not_called()

    def test_proven_429_is_audited_through_legacy_reconcile_before_run(self) -> None:
        pacer = ProviderQuotaPacer(self.ledger,credential="fixture-previous",amendment_sha256=
            hashlib.sha256((self.run / cli.AMENDMENT_FILE).read_bytes()).hexdigest(),policy="request_admission_v2")
        row = pacer.reserve("openai/gpt-oss-20b",1)
        row.update(status=429,checkpoint_attempt_id="quota-attempt",point_id="FPT-2023-05-11",run_signature="s")
        pacer.save()
        save_envelope(self.run/"candidates/C3/FPT-2023-05-11.json",{
            "point_id":"FPT-2023-05-11","run_signature":"s",
            "attempts":[{"attempt_id":"quota-attempt","status":"unknown","authorization":None}]})
        cli.execute([*self.arguments("--run"),"--resume"])
        self.assertIn("--reconcile",self.calls[0])
        self.assertIn("quota-attempt",self.calls[0])
        self.assertIn("--run",self.calls[1])
