"""Oracle số học cho ngưỡng/ranking mới; fixture không là nomination thật."""

from copy import deepcopy
import unittest

from core.improvement_protocol import MATRIX, SYMBOL_ORDER, nomination_rules
from core.improvement_reports import evaluate_selection, selection_artifact


def fixture_report() -> dict:
    """Tạo metric tổng hợp có common support để kiểm selector, không mô phỏng LLM."""
    planned = nomination_rules()['planned']
    stocks = {}
    for symbol in SYMBOL_ORDER:
        points = [{'point_id': f'{symbol}-2023-01-{j+1:02d}', 'as_of_date': f'2023-01-{j+1:02d}',
            'branch_status': {n: 'complete' for n in MATRIX}, 'prior': {n: {'visible_metric_ids': ['win_rate_long'],
                'visible_example_ids': []} for n in MATRIX}} for j in range(planned[symbol])]
        stocks[symbol] = {'points': points, 'global_common_support': {'count': len(points), 'point_ids': [p['point_id'] for p in points]},
            'metrics': {n: {'account_metrics': {'total_return_pct': 0. if n == 'original' else 1., 'max_drawdown_pct': 1.}} for n in MATRIX},
            'coverage': {n: {'prior_visible_count': len(points)} for n in MATRIX}}
    return {'report_version': 'improvement_report_v1', 'matrix': list(MATRIX), 'repeat_id': 0, 'split': 'fixture',
        'primary_status': 'COMPLETE', 'stocks': stocks, 'binding': {'execution_mode': 'offline_fixture'}}


class ImprovementSelectionTests(unittest.TestCase):
    def test_tie_uses_mdd_then_fixed_full_prior_order(self) -> None:
        report = fixture_report()
        result = evaluate_selection(report, gates_passed=True)
        self.assertEqual(result['research_candidate'], 'C2')
        self.assertEqual(result['eligible_order'], ['C2', 'A_tp_pool', 'B_semantic'])
        for stock in report['stocks'].values():
            stock['metrics']['A_tp_pool']['account_metrics']['max_drawdown_pct'] = .5
        self.assertEqual(evaluate_selection(report, gates_passed=True)['research_candidate'], 'A_tp_pool')

    def test_positive_two_symbols_not_promoted_and_technical_gate_not_optional(self) -> None:
        report = fixture_report()
        for symbol in ('FPT', 'MWG'):
            for name in ('C2', 'A_tp_pool', 'B_semantic'):
                report['stocks'][symbol]['metrics'][name]['account_metrics']['total_return_pct'] = 0.
        result = evaluate_selection(report, gates_passed=True)
        self.assertEqual(result['nomination_status'], 'NOT_PROMOTED')
        self.assertEqual(result['deployment_choice'], 'original')
        self.assertEqual(result['research_candidate'], 'C2')
        self.assertEqual(evaluate_selection(report, gates_passed=False)['nomination_status'], 'BLOCKED')

    def test_exposure_incomplete_holdout_and_nonfinite_cannot_be_hidden_by_summary(self) -> None:
        source = fixture_report()
        for change in ('visibility', 'support', 'holdout', 'nonfinite'):
            report = deepcopy(source)
            stock = report['stocks']['FPT']
            if change == 'visibility':
                stock['points'][0]['prior']['C2']['visible_metric_ids'] = []
            elif change == 'support':
                stock['points'][0]['branch_status']['original'] = 'unknown'
            elif change == 'holdout':
                stock['points'][0]['as_of_date'] = '2024-01-01'
            else:
                stock['metrics']['C2']['account_metrics']['max_drawdown_pct'] = float('inf')
            with self.assertRaises(ValueError):
                evaluate_selection(report, gates_passed=True)

    def test_fixture_artifact_is_blocked_even_with_arithmetic_promotion(self) -> None:
        selected = selection_artifact(fixture_report(), {'status': 'PASS'}, 'a'*64)
        self.assertEqual(selected['nomination_status'], 'BLOCKED')
        self.assertIsNone(selected['research_candidate'])
        self.assertEqual(selected['fixture_protocol_result']['nomination_status'], 'PROMOTED')
