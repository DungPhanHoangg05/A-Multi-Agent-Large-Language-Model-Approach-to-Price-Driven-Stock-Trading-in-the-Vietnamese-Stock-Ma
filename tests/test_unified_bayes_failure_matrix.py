"""Ma trận ngắt/resume toàn cohort, gồm nhánh độc lập, bốn mã và repeat duplicate."""

from copy import deepcopy
import unittest
from unittest.mock import patch

import httpx

from core.groq_pacing import PilotStop
from core.research_cohort import read_envelope
from unified_validation_test_support import MATRIX, ValidationFixture


class FailureMatrixTests(ValidationFixture, unittest.TestCase):
    """Ngắt ở durable boundary rồi mở handle mới; không gọi lại upstream hoặc slot xong."""

    def boundary(self, case: dict) -> None:
        """Mỗi fixture chỉ gây lỗi một lần, giữ toàn journal/usage để khôi phục thực."""
        run = self.handle()
        repeat = bool(case["repeat_id"])
        primary = deepcopy(run.run()["primary"]) if repeat else None
        path = run.journal.path(case["point_id"], case["repeat_id"], case["branch"])
        fired = []
        save = run.journal.save
        def crash(target, value):
            responses = bool(value["attempts"] and value["attempts"][0]["responses"])
            name = case["name"]
            trigger = target == path and not fired and (
                name in ("before_intent", "after_intent") and value["status"] == "unknown" and not responses
                or name == "after_response" and responses and value["status"] == "unknown"
                or name in ("before_complete", "after_complete") and value["status"] == "complete")
            if trigger and name.startswith("before_"):
                fired.append(True)
                raise OSError("Ngắt fixture trước durable")
            save(target, value)
            if trigger:
                fired.append(True)
                raise OSError("Ngắt fixture sau durable")
        store = self.fx.transport._store
        def crash_cache(request, response):
            store(request, response)
            slot = read_envelope(path)
            if slot["attempts"] and not fired:
                fired.append(True)
                raise OSError("Ngắt fixture sau HTTP cache của duplicate")
        operation = patch.object(self.fx.transport, "_store", side_effect=crash_cache) if case["name"] == "after_http_cache" else patch.object(run.journal, "save", side_effect=crash)
        with operation, self.assertRaises((OSError, PilotStop)):
            run.run(repeats=repeat)
        self.assertTrue(fired)
        interrupted = read_envelope(path)
        completed = {str(p): p.read_bytes() for p in (run.root / "journal/decisions").rglob("*.json")
                     if read_envelope(p)["status"] == "complete"}
        requests = deepcopy(self.fx.pacer.state["requests"])
        recovered = self.handle(create=False)
        result = recovered.run(repeats=repeat)
        final = read_envelope(path)
        self.assertEqual(final["status"], "complete")
        if interrupted["attempts"]:
            self.assertEqual(final["attempts"][0]["attempt_id"], interrupted["attempts"][0]["attempt_id"])
        if interrupted["status"] == "unknown":
            self.assertEqual(final["attempts"][0]["recoveries"][0]["reason"], "SAME_UUID_RETRY_WITH_AUDIT")
        for name, raw in completed.items():
            from pathlib import Path
            self.assertEqual(Path(name).read_bytes(), raw)
        self.assertEqual(self.fx.pacer.state["requests"][:len(requests)], requests)
        self.assertEqual(result["repeats" if repeat else "primary"]["status"], "COMPLETE")
        if primary:
            self.assertEqual(result["primary"], primary)
            original = read_envelope(recovered.journal.path(case["point_id"], 1, "Original"))
            self.assertNotEqual(final["attempts"][0]["attempt_id"], original["attempts"][0]["attempt_id"])
        # Mỗi UUID/slot có đúng một HTTP thành công, kể cả khi checkpoint SDK mất.
        success = [row["checkpoint_attempt_id"] for row in self.fx.pacer.state["requests"] if row["status"] == 200]
        self.assertEqual(len(success), len(set(success)))

    def test_cohort_transient_retry_and_duplicate_keep_same_uuid_and_body(self) -> None:
        run = self.handle()
        statuses = MATRIX["transient_http"]
        def respond(_):
            status = statuses[min(len(self.fx.calls) - 1, len(statuses) - 1)]
            return self.fx.response() if status == 200 else httpx.Response(status, headers={"retry-after": "135"},
                json={"error": {"message": "TPM; retry after 135 seconds"}})
        self.fx.handler = respond
        result = run.run()
        rows = self.fx.pacer.state["requests"][:3]
        self.assertEqual([r["status"] for r in rows], statuses)
        self.assertEqual(len({r["checkpoint_attempt_id"] for r in rows}), 1)
        self.assertEqual(self.fx.calls[0], self.fx.calls[1])
        self.assertEqual(self.fx.calls[1], self.fx.calls[2])
        self.assertGreaterEqual(self.fx.now, 100135.)
        primary = deepcopy(result["primary"])
        self.assertEqual(run.run(repeats=True)["primary"], primary)

    def test_cohort_auth_and_daily_quota_stop_without_cash_then_resume(self) -> None:
        for status in MATRIX["stop_http"]:
            with self.subTest(status=status):
                # Mỗi lần dừng dùng point kế tiếp còn planned trong cùng run.
                run = self.handle(create=status == MATRIX["stop_http"][0])
                self.fx.handler = lambda _, code=status: httpx.Response(code, headers={"retry-after": "3600"},
                    json={"error": {"message": "Quota TPD per day" if code == 429 else "Unauthorized fixture"}})
                with self.assertRaises(PilotStop):
                    run.run()
                planned = next(p for p in run.root.rglob("Original.json") if read_envelope(p)["status"] == "unknown")
                before = read_envelope(planned)
                self.assertIsNone(before["output"])
                self.fx.now += 86401
                self.fx.handler = None
                # Chỉ hoàn tất point đang lỗi, giữ point sau cho ca quota tiếp theo.
                run.journal.run_point(before["point_id"], execute=True)
                after = read_envelope(planned)
                self.assertEqual(before["attempts"][0]["attempt_id"], after["attempts"][0]["attempt_id"])
        self.assertEqual(self.handle(create=False).run()["primary"]["status"], "COMPLETE")


def _case_test(case: dict):
    """Nạp JSON fixture thành từng test riêng để thấy chính xác boundary lỗi."""
    def test(self):
        self.boundary(case)
    test.__doc__ = "Khôi phục boundary " + case["name"] + " qua journal durable của cohort."
    return test


for _case in MATRIX["boundaries"]:
    setattr(FailureMatrixTests, "test_boundary_" + _case["name"], _case_test(_case))


if __name__ == "__main__":
    unittest.main()
