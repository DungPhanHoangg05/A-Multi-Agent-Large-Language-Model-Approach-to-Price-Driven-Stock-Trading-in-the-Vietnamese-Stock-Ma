"""Kiểm fixture tái lập và cách smoke phân biệt nguồn thiếu với nguồn sai."""

from contextlib import ExitStack
import unittest
from unittest.mock import patch

from scripts.verify_prior_integration import REGIMES, observed_replay, offline_guard, sha, synthetic_fixture


class PriorIntegrationSmokeTests(unittest.TestCase):
    """Không cần archive local hoặc LLM; smoke đầy đủ được chạy bằng CLI riêng."""

    def test_synthetic_sources_reproducible_and_all_regimes_use_real_detector(self) -> None:
        for index, regime in enumerate(REGIMES):
            with self.subTest(regime=regime), ExitStack() as stack:
                first = synthetic_fixture(regime, "vi", index)
                stack.callback(first.close)
                second = synthetic_fixture(regime, "vi", index)
                stack.callback(second.close)
                paths = [p.relative_to(first.root) for p in first.root.rglob("*") if p.is_file()]
                self.assertTrue(paths)
                self.assertEqual({p.as_posix(): sha(first.root / p) for p in paths},
                                 {p.as_posix(): sha(second.root / p) for p in paths})
                adapter = first.adapter()
                point = adapter.prepare("FPT", first.cutoff)
                self.assertEqual(point._regime["regime_name"], regime)

    def test_missing_observed_archive_is_blocked_and_never_reported_as_synthetic(self) -> None:
        with patch("scripts.verify_prior_integration.PriorContextAdapter",
                   side_effect=FileNotFoundError(2, "Thiếu archive", "archive/regime.json")):
            result = observed_replay()
        self.assertEqual((result["status"], result["source_kind"]), ("BLOCKED", "observed"))
        self.assertFalse(result["oos_trading_result"])
        self.assertIn("archive/regime.json", result["reason"])

    def test_invalid_observed_proof_fails_instead_of_becoming_blocked(self) -> None:
        with patch("scripts.verify_prior_integration.PriorContextAdapter", side_effect=ValueError("Sai checksum")):
            with self.assertRaisesRegex(ValueError, "Sai checksum"):
                observed_replay()

    def test_offline_guard_detects_even_swallowed_network_attempt(self) -> None:
        import socket
        with self.assertRaisesRegex(AssertionError, "bắt rồi bỏ qua"):
            with offline_guard():
                try:
                    socket.getaddrinfo("example.invalid", 443)
                except AssertionError:
                    pass


if __name__ == "__main__":
    unittest.main()
