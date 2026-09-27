"""Kiểm backoff, thời gian Groq yêu cầu và việc không retry lỗi liêm chính."""

import unittest
from unittest.mock import Mock, patch

from utils.historical_api import RetryingLLM, _invoke_with_retry


class HistoricalAPITests(unittest.TestCase):
    def test_exponential_backoff_and_proxy(self):
        delegate = Mock()
        delegate.invoke.side_effect = [RuntimeError("Lỗi tạm"), RuntimeError("Lỗi tạm"), "ok"]
        with patch("utils.historical_api.time.sleep") as sleep:
            self.assertEqual(RetryingLLM(delegate).invoke("prompt"), "ok")
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [5., 10.])

    def test_groq_retry_hint_is_not_capped_below_required_wait(self):
        for message, expected in [("retry after 72 seconds", [60., 13.]), ("Please try again in 1m2.5s", [60., 3.5])]:
            with self.subTest(message=message):
                call = Mock(side_effect=[RuntimeError(message), "ok"])
                with patch("utils.historical_api.time.sleep") as sleep:
                    self.assertEqual(_invoke_with_retry(call), "ok")
                self.assertEqual([item.args[0] for item in sleep.call_args_list], expected)

    def test_integrity_error_is_immediate_without_retry_or_sleep(self):
        call = Mock(side_effect=ValueError("Vi phạm cutoff"))
        with patch("utils.historical_api.time.sleep") as sleep, self.assertRaises(ValueError):
            _invoke_with_retry(call)
        self.assertEqual(call.call_count, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
