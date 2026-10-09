"""Khóa dữ liệu không sinh Decision/outcome, không giả prompt đã kiểm chứng."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from core import research_input_lock as locking
import test_research_input_lock as support


class ResearchInputLockLeakageTests(unittest.TestCase):
    """Thực thi producer thật trên fixture với evaluator/API bị cấm."""

    def setUp(self) -> None:
        self.fixture = support.ResearchInputLockTests(methodName='test_prepare_verify_idempotent_and_smoke_plan_accepted_by_existing_runner')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_no_api_evaluator_or_refit_and_actual_prompt_remains_unverified(self) -> None:
        """Không gọi LLM, fit HMM hoặc chấm query trong quá trình khóa input."""
        with patch('utils.historical_api._invoke_with_retry', side_effect=AssertionError('Cấm LLM')), \
             patch('core.regime_detector.MarketRegimeDetector.fit', side_effect=AssertionError('Cấm fit')), \
             patch('core.prior_backtest.evaluate_point', side_effect=AssertionError('Cấm outcome')):
            lock = self.fixture.prepare()
        self.assertEqual(lock['dry_run']['actual_prefix_and_full_prompt'], 'NOT_GENERATED_NO_UPSTREAM')
        self.assertEqual(lock['dry_run']['query_outcome'], 'NOT_GENERATED')
        self.assertEqual(lock['dry_run']['gate_c'], 'PENDING')

    def test_future_split_and_cross_year_execution_rejected(self) -> None:
        """Ngày 2024 không thể đi vào smoke/development hoặc vượt năm exit."""
        lock = self.fixture.prepare()
        changed = deepcopy(lock)
        changed['cohorts']['smoke']['FPT'] = changed['cohorts']['holdout_2024']['FPT'][:1]
        with self.assertRaises(ValueError):
            locking.dry_run_points(changed, self.fixture.adapter)
        changed = deepcopy(lock)
        day = changed['cohorts']['holdout_2024']['FPT'][0]
        changed['points'][f'FPT-{day}']['exit_date'] = '2025-01-01'
        with self.assertRaises(ValueError):
            locking.dry_run_points(changed, self.fixture.adapter)


if __name__ == '__main__':
    unittest.main()
