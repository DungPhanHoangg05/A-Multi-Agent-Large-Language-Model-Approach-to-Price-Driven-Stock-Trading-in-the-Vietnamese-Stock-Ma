"""Ma trận lỗi sáu ứng viên: intent, response durable và quota giữa nhánh."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from core import research_cohort
from core.candidate_cohort import CANDIDATES
from core.groq_pacing import GroqPacer, MODEL_LIMITS, PilotStop
from core.research_invocation import CURRENT
import test_candidate_cohort as support


class CandidateFaultMatrixTests(support.CandidateSetup, unittest.TestCase):
    """Dùng checkpoint thật/LLM giả; không đọc key hoặc gửi HTTP."""

    def setUp(self) -> None:
        super().setUp()
        for target in ("socket.socket.connect", "socket.getaddrinfo", "dotenv.load_dotenv",
                       "scripts.run_bayesian_ablation.dotenv_values", "httpx.HTTPTransport.handle_request"):
            guard = self.stack.enter_context(patch(target, side_effect=AssertionError("Cấm key/mạng")))
            self.addCleanup(lambda guard=guard: self.assertFalse(guard.called))

    def test_each_candidate_recovers_before_intent_and_after_durable_response(self) -> None:
        """Lỗi trước intent không gọi LLM; response đã durable không được gọi lại."""
        save = research_cohort.save_envelope
        for boundary in ("before_intent", "after_response"):
            for name in CANDIDATES:
                with self.subTest(boundary=boundary, candidate=name):
                    self.output = self.fx.root / f"{boundary}-{name}"
                    self.events.clear()
                    before = self.llm.calls
                    fired = []
                    def fail(path, payload):
                        attempts = payload.get("attempts", [])
                        status = attempts[-1]["status"] if attempts else None
                        selected = path.parent.name == name and not fired
                        if selected and boundary == "before_intent" and status == "unknown":
                            fired.append(True)
                            raise OSError("Fixture lỗi trước lưu intent")
                        save(path, payload)
                        if selected and boundary == "after_response" and status == "complete":
                            fired.append(True)
                            raise OSError("Fixture lỗi sau response durable")
                    with patch.object(research_cohort, "save_envelope", side_effect=fail), self.assertRaises(OSError):
                        self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
                    self.assertEqual(fired, [True])
                    offset = CANDIDATES.index(name)
                    self.assertEqual(self.llm.calls-before, 5+offset+(boundary == "after_response"))
                    durable = {candidate:self.checkpoint(candidate)[0].read_bytes() for candidate in CANDIDATES
                               if self.checkpoint(candidate)[1].get("attempts")
                               and self.checkpoint(candidate)[1]["attempts"][-1]["status"] == "complete"}
                    self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"], resume=True)
                    self.assertEqual(self.llm.calls-before, 11)
                    self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"])
                    documents = [self.checkpoint(candidate)[1] for candidate in CANDIDATES]
                    self.assertEqual(len({doc["shared_sha256"] for doc in documents}), 1)
                    for candidate, original in durable.items():
                        self.assertEqual(self.checkpoint(candidate)[0].read_bytes(), original)
                    for doc in documents:
                        self.assertEqual([attempt["status"] for attempt in doc["attempts"]], ["complete"])
                        self.assertLess(len(doc["prompt"]), 6500)
                        if doc["request"] is not None:
                            self.assertLessEqual(len(doc["request"]["prefix"]), 600)

    def test_quota_and_cooldown_inside_candidate_preserve_unknown_until_exact_replay(self) -> None:
        """Quota ở C3 giữ intent unknown, không tự gửi lại trước đối soát UUID."""
        invoke = self.llm.invoke
        for reason in ("DAILY_QUOTA", "COOLDOWN_BEFORE_POINT"):
            with self.subTest(reason=reason):
                self.output = self.fx.root / reason
                self.events.clear()
                before = self.llm.calls
                now = [100000.]
                pacer = GroqPacer(self.fx.root / f"{reason}-usage.json", clock=lambda:now[0],
                    sleep=lambda _:self.fail("Không nghỉ thật"), policy="request_admission_v2")
                rows = [{"model": model, "started_at": now[0]-100, "reserved_tokens": 8000, "status": "unknown"}
                        for model in MODEL_LIMITS for _ in range(25 if reason == "DAILY_QUOTA" else 1)]
                if reason == "COOLDOWN_BEFORE_POINT":
                    rows[0]["retry_until"] = now[0]+1000
                pacer.state["requests"] = rows
                pacer.save()
                def stop(prompt):
                    if CURRENT.get().branch_id == "C3":
                        pacer.before_point()
                    return invoke(prompt)
                with patch.object(self.llm, "invoke", side_effect=stop), self.assertRaisesRegex(PilotStop, reason):
                    self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
                self.assertEqual(self.llm.calls-before, 8)
                durable = {name:self.checkpoint(name)[0].read_bytes() for name in ("C0", "C1", "C2")}
                with self.assertRaisesRegex(ValueError, "unknown"):
                    self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"], resume=True)
                report = self.runner.run_cohort(self.plan, output_dir=self.output, reconcile=True)
                unknown = [row for row in report["decisions"] if row["status"] == "unknown"]
                self.assertEqual([(row["branch"], row["status"]) for row in unknown], [("C3", "unknown")])
                self.assertEqual(self.llm.calls-before, 8)
                history = deepcopy(pacer.state["requests"])
                now[0] += 86401
                reloaded = GroqPacer(pacer.path, clock=lambda:now[0], sleep=lambda _:self.fail("Không nghỉ thật"),
                    policy="request_admission_v2")
                reloaded.before_point()
                self.assertEqual(reloaded.state["requests"], history)
                self.runner.run_cohort(self.plan, output_dir=self.output, reconcile=True,
                    authorize_replay=unknown[0]["attempt_id"], replay_reason="Đối soát fixture quota; replay đúng UUID")
                self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"], resume=True)
                self.assertEqual(self.llm.calls-before, 11)
                self.assertEqual(self.events, ["indicator", "pattern", "trend", "full"])
                for name, original in durable.items():
                    self.assertEqual(self.checkpoint(name)[0].read_bytes(), original)
                attempts = self.checkpoint("C3")[1]["attempts"]
                self.assertEqual([row["status"] for row in attempts], ["unknown", "complete"])
                self.assertEqual(attempts[0]["attempt_id"], unknown[0]["attempt_id"])

    def test_rehashed_scaler_and_source_changes_between_stocks_block_before_llm(self) -> None:
        """Tự băm lại envelope không được làm mất pin nguồn/index của run cũ."""
        self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
        calls = self.llm.calls
        events = list(self.events)
        index_path = self.fx.root / "index.json"
        source_path = self.fx.root / "run/inputs/news/VNM.json"
        saved_index, saved_source = index_path.read_bytes(), source_path.read_bytes()
        for source in ("scaler", "feature", "news"):
            with self.subTest(source=source):
                if source in ("scaler", "feature"):
                    document = research_cohort.read_envelope(index_path)
                    if source == "scaler":
                        scaler = next(value for scalers in document["scalers"].values() for value in scalers.values()
                                      if value["mean"] is not None)
                        scaler["mean"][0] += .01
                    else:
                        row = next(value for value in document["records"] if value["features"]["vector"] is not None)
                        row["features"]["vector"][0] += .01
                    research_cohort.save_envelope(index_path, document)
                else:
                    source_path.write_bytes(saved_source+b"\n")
                with self.assertRaises(ValueError):
                    self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["MWG"], resume=True)
                self.assertEqual(self.llm.calls, calls)
                self.assertEqual(self.events, events)
                index_path.write_bytes(saved_index)
                source_path.write_bytes(saved_source)
