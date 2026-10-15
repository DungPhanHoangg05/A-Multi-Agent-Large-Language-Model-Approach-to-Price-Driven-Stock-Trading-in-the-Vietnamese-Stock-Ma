"""Amendment không mở holdout, sửa nguồn hoặc xóa bằng chứng của lượt development."""

from contextlib import ExitStack
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.bayesian_memory import atomic_write_json, read_json
from core.groq_pacing import MODEL_LIMITS
from core.provider_quota import (AMENDMENT_FILE, EXTENSION_FILES, TECHNICAL_GATES, ProviderQuotaPacer,
    prepare_amendment, verify_amendment)
from core.research_cohort import read_envelope, save_envelope


class AmendmentFixture(unittest.TestCase):
    """Fixture nhỏ chỉ kiểm bảo toàn cutover; không là kết quả validation thật."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.run = self.root / "outputs/bayesian_benchmark/run"
        self.run.mkdir(parents=True)
        self.ledger = self.root / "outputs/oos_pilot/api_usage.json"
        self.plan_path = self.root / "outputs/bayesian_benchmark/plan.json"
        actual_root = Path(__file__).resolve().parents[1]
        for name in EXTENSION_FILES:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((actual_root / name).read_bytes())
        self.method = self.root / "method.py"
        self.method.write_text("frozen = True\n", encoding="utf-8")
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("core.candidate_cohort._code", side_effect=self.code))
        self.stack.enter_context(patch("core.research_input_lock.runtime_identity", return_value={"python":"3.13.5"}))
        self.plan = {"plan_version":"research_cohort_plan_v3","split":"development_2023",
            "code_sha256":self.code(),"runtime":{"python":"3.13.5"}}
        save_envelope(self.plan_path, self.plan)
        save_envelope(self.run / "cohort.json", {"plan":self.plan,"ledger_path":str(self.ledger)})
        self.complete = self.run / "v1/FPT/points/FPT-2023-04-12.json"
        save_envelope(self.complete,{"point_id":"FPT-2023-04-12","status":"complete"})
        self.response = self.run / "v1/FPT/responses/FPT-2023-04-12.json"
        atomic_write_json(self.response,{"version":"agent_stage_journal_v1","nodes":{
            name:{"attempts":[{"status":"complete"}]} for name in ("indicator","pattern","trend","full")}})
        atomic_write_json(self.ledger,{"version":1,"limits":MODEL_LIMITS,"requests":[{
            "id":"legacy-request","model":"openai/gpt-oss-20b","status":200,
            "started_at":1.,"reserved_tokens":8000,"total_tokens":100}]})
        self.original_ledger = self.ledger.read_bytes()
        gate_path=self.root/TECHNICAL_GATES
        gate_path.parent.mkdir(parents=True,exist_ok=True)
        texts={"unit":"Ran 1 test in 0.1s\n\nOK\n","leakage":"Ran 1 test in 0.1s\n\nOK\n",
            "e2e":"ALL PIPELINE CHECKS SUCCESSFUL\n",
            "compileall":"\n".join(f"Listing '{part}'" for part in ("agents","core","data_manager","scripts","tests","utils"))}
        checks={}
        for name,text in texts.items():
            path=gate_path.parent/f"{name}.log"
            path.write_text(text,encoding="utf-8")
            checks[name]={"status":"PASS","exit_code":0,"log":{"path":path.name,
                "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}}
        save_envelope(gate_path,{"gate_version":"research_technical_gates_v1","code_sha256":self.code(),
            "runtime":self.plan["runtime"],"checks":checks})
        prepare_amendment(self.root,self.plan_path,self.run,self.ledger)

    def code(self) -> dict[str, str]:
        """Băm file phương pháp thật của fixture để phát hiện thay đổi nguồn."""
        return {"method.py":hashlib.sha256(self.method.read_text(encoding="utf-8").encode()).hexdigest()}

    def verify(self) -> dict:
        """Gọi verifier thật của amendment, không mô phỏng checksum."""
        return verify_amendment(self.root,self.plan_path,self.run,self.ledger)


class ProviderAmendmentLeakageTests(AmendmentFixture):
    """Sai nguồn/identity/usage chặn trước API, kể cả envelope đã băm lại."""

    def test_cutover_preserves_raw_ledger_and_complete_points_and_all_four_nodes(self) -> None:
        doc = self.verify()
        self.assertEqual(self.ledger.read_bytes(),self.original_ledger)
        self.assertIn(self.complete.relative_to(self.run).as_posix(),doc["protected_files"])
        self.assertIn(self.response.relative_to(self.run).as_posix(),doc["protected_files"])
        before = (self.run / AMENDMENT_FILE).read_bytes()
        prepare_amendment(self.root,self.plan_path,self.run,self.ledger)
        self.assertEqual((self.run / AMENDMENT_FILE).read_bytes(),before)

    def test_rehashed_complete_checkpoint_tamper_is_blocked(self) -> None:
        doc = read_envelope(self.complete)
        doc["status"] = "planned"
        save_envelope(self.complete,doc)
        with self.assertRaisesRegex(ValueError,"Checkpoint complete"):
            self.verify()

    def test_method_or_extension_change_is_blocked(self) -> None:
        for path in (self.method,self.root / EXTENSION_FILES[0]):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original + b"\n# fixture\n")
                with self.assertRaisesRegex(ValueError,"code/runtime"):
                    self.verify()
                path.write_bytes(original)

    def test_deleting_or_rewriting_old_usage_is_blocked(self) -> None:
        original = read_json(self.ledger)
        for requests in ([],[{**original["requests"][0],"total_tokens":0}]):
            atomic_write_json(self.ledger,{**original,"requests":requests})
            with self.assertRaisesRegex(ValueError,"Usage"):
                self.verify()

    def test_new_request_requires_matching_operational_audit(self) -> None:
        checksum = hashlib.sha256((self.run / AMENDMENT_FILE).read_bytes()).hexdigest()
        pacer = ProviderQuotaPacer(self.ledger,credential="fixture-key",amendment_sha256=checksum,
            clock=lambda:100000.,sleep=lambda seconds:None,policy="request_admission_v2")
        pacer.reserve("openai/gpt-oss-20b",1)
        self.verify()
        ledger = read_json(self.ledger)
        del ledger["requests"][-1]["daily_policy"]
        atomic_write_json(self.ledger,ledger)
        with self.assertRaisesRegex(ValueError,"thiếu audit"):
            self.verify()

    def test_rehashed_holdout_relabel_and_policy_change_are_blocked(self) -> None:
        plan = {**self.plan,"split":"holdout_2024"}
        save_envelope(self.plan_path,plan)
        with self.assertRaises(ValueError):
            self.verify()
        save_envelope(self.plan_path,self.plan)
        target = self.run / AMENDMENT_FILE
        doc = read_envelope(target)
        doc["policy"]["unknown_replay"] = "AUTOMATIC_ALL"
        save_envelope(target,doc)
        with self.assertRaisesRegex(ValueError,"policy"):
            self.verify()

    def test_protected_path_cannot_read_credentials_or_escape_run(self) -> None:
        target = self.run / AMENDMENT_FILE
        original = read_envelope(target)
        for name in (".env","../private.json"):
            doc = {**original,"protected_files":{name:"a"*64}}
            save_envelope(target,doc)
            with self.assertRaises(ValueError):
                self.verify()


if __name__ == "__main__":
    unittest.main()
