"""Hồi quy xuất bản: mẫu số, prior-off, nhóm rỗng và chống thay bundle/nguồn."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import export_improvement_holdout as exporter


def fixture() -> dict:
    """Dựng bốn điểm nhỏ chỉ để kiểm chiếu dữ liệu; không giả lập hiệu quả nghiên cứu."""
    names = list(exporter.LABELS)
    stocks, cases, points, checkpoints, ledger, bindings = {}, {n: [] for n in names}, {}, {}, [], {}
    for symbol in exporter.SYMBOLS:
        pid = symbol+'-2024-01-02'
        prior = {n: {'stats_ready': n != 'original', 'examples_ready': False,
            'visible_metric_ids': ['win_rate_long'] if n == 'bayesian' else [], 'visible_example_ids': []} for n in names}
        metrics = {n: {'sample_count': 1, 'accuracy': 1., 'balanced_accuracy': None, 'long_count': 0,
            'cash_count': 1, 'account_metrics': {'total_return_pct': 0., 'max_drawdown_pct': 0.}} for n in names}
        cov = {n: {'planned': 1, 'complete': 1, 'pending': 0, 'failed': 0, 'unknown': 0, 'missing_result': 0,
            'stats_ready': int(n != 'original'), 'examples_ready': 0, 'prior_visible_count': int(n == 'bayesian'),
            'prior_off_count': int(n != 'bayesian'), 'fallback_count': int(n not in ('original', 'bayesian')),
            'reason_counts': {}} for n in names}
        group = {'contrasts': {'A_tp_pool__original': {'count': 0, 'delta_return_pp': None,
            'delta_mdd_pp': None, 'status': 'NO_SUPPORT'}}}
        subset = {'count': 0, 'delta_return_pp': None, 'delta_mdd_pp': None}
        stocks[symbol] = {'metrics': metrics, 'coverage': cov, 'points': [{'point_id': pid,
            'as_of_date': '2024-01-02', 'regime': 'BULL', 'prior': prior}],
            'time_groups': {k: deepcopy(group) for k in ('Q1', 'Q2', 'Q3', 'Q4', 'H1', 'H2')},
            'regimes': {k: deepcopy(group) for k in ('BULL', 'BEAR', 'CHOPPY', 'CONSOLIDATION')},
            'ablation_both_ready': {'_stats_only': subset, '_examples_only': subset},
            'prior_off': {'A_tp_pool__original': subset}}
        points[pid] = {'source_proof': {'news': {'is_reliable': False}}}
        for n in names:
            action = 'LONG' if symbol == 'FPT' and n == 'A_tp_pool' else 'CASH'
            cases[n].append({'point_id': pid, 'prior_visible': n == 'bayesian', 'raw_action': 'LONG' if action == 'LONG' else 'SHORT',
                'execution_action': action, 'cycle_net_return': -.01 if action == 'LONG' else 0.,
                'economic_outcome': {'exit_date': '2024-01-05', 'net_return_long': -.01},
                'trace': {'status': 'NOT_APPLICABLE'}})
            checkpoints[pid, n] = {'prompt_sha256': 'same', 'shared_sha256': 'shared'}
            identity = pid+'-'+n; bindings['http:'+identity] = 'fixture'
            ledger.append({'id': identity, 'status': 200, 'improvement_audit': {
                'slot': {'point_id': pid, 'branch_id': n}, 'request': {'canonical_body_sha256': 'same'}}})
    contrasts = {'A_tp_pool__'+n: {'point_estimate_pp': 0., 'ci': [-1., 1.],
        'confidence_level': .95 if n == 'original' else .9875, 'interpretation': 'INCONCLUSIVE'}
        for n in ('original', 'C2', 'bayesian', 'A_tp_pool_stats_only', 'A_tp_pool_examples_only')}
    return {'report': {'matrix': names, 'cases': cases, 'stocks': stocks,
        'binding': {'checkpoint_sha256': bindings}, 'leave_one_symbol_out': dict.fromkeys(exporter.SYMBOLS, 0.)},
        'bootstrap': {'blocks': {'4': {'contrasts': contrasts}}}, 'points': points,
        'checkpoints': checkpoints, 'ledger': {'requests': ledger}}


class HoldoutPublicationTests(unittest.TestCase):
    def test_prior_off_identical_requests_can_disagree_without_becoming_causal_evidence(self) -> None:
        a = exporter.analyse(fixture())
        off = next(x for x in a['prior_off_audit'] if x['branch'] == 'A_tp_pool')
        self.assertEqual((off['off'], off['prompt_equal'], off['canonical_equal']), (4, 4, 4))
        self.assertEqual(off['identical_request_action_diff'], 1)
        self.assertEqual(a['disagreements'][0]['delta_cycle_return_pp'], -1.)
        self.assertEqual(a['paired_actions']['OFF']['count'], 4)
        self.assertEqual(a['trace'], {'NOT_APPLICABLE': 24})
        self.assertNotIn('NOT_USED', a['trace'])

    def test_actual_http_multiset_difference_is_not_claimed_identical(self) -> None:
        data = fixture()
        next(r for r in data['ledger']['requests'] if r['id'] == 'FPT-2024-01-02-A_tp_pool')[
            'improvement_audit']['request']['canonical_body_sha256'] = 'different'
        a = exporter.analyse(data)
        off = next(x for x in a['prior_off_audit'] if x['branch'] == 'A_tp_pool')
        self.assertEqual((off['prompt_equal'], off['canonical_equal'], off['identical_request_action_diff']), (4, 3, 0))

    def test_missing_http_or_wrong_shared_proof_blocks_attribution(self) -> None:
        data = fixture(); data['ledger']['requests'].pop()
        with self.assertRaisesRegex(ValueError, 'HTTP'): exporter.analyse(data)
        data = fixture(); data['checkpoints']['FPT-2024-01-02', 'A_tp_pool']['shared_sha256'] = 'other'
        with self.assertRaisesRegex(ValueError, 'upstream'): exporter.analyse(data)

    def test_ready_is_distinct_from_visible_and_empty_groups_stay_null(self) -> None:
        a = exporter.analyse(fixture())
        cov = next(x for x in a['coverage'] if x['branch'] == 'A_tp_pool')
        self.assertEqual((cov['stats_ready'], cov['prior_visible_count'], cov['visibility']['off']), (4, 0, 4))
        self.assertEqual(a['regime_counts']['BEAR'], 0)
        text = exporter.tables(a)['subgroups.tex']
        self.assertIn('-- (n=0)', text)
        self.assertEqual(exporter.number(None), '--')
        self.assertEqual(exporter.number(0), '0.000')

    def test_tex_escapes_data_and_keeps_all_methods_and_adverse_case(self) -> None:
        self.assertEqual(exporter.tex('A_1 & 5%'), r'A\_1 \& 5\%')
        tables = exporter.tables(exporter.analyse(fixture()))
        self.assertEqual(len(tables), 6)
        self.assertIn('A (examples)', tables['performance.tex'])
        self.assertIn('FPT-2024-01-02', tables['disagreements.tex'])
        self.assertIn('-1.000', tables['disagreements.tex'])
        self.assertIn('Bayesian v1 & 0 & 0 & 0 & 0', tables['attribution.tex'])

    def test_bundle_checks_rebuilds_and_rejects_tampering_missing_files_and_source_drift(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder); source = root/exporter.SOURCE
            source.parent.mkdir(); source.write_text('fixture', encoding='utf-8')
            output = root/'bundle'
            def write(a, destination):
                (destination/'one.svg').write_text(json.dumps(a), encoding='utf-8')
                return ['one.svg']
            with (patch.object(exporter, 'load_inputs', return_value=({}, {'report': 'accepted'})),
                  patch.object(exporter, 'analyse', return_value={'value': 1}), patch.object(exporter, 'write_assets', side_effect=write)):
                exporter.export(root, output); before = (output/'manifest.json').read_bytes()
                exporter.export(root, output, check=True)
                self.assertEqual(before, (output/'manifest.json').read_bytes())
                (output/'one.svg').write_text('tampered', encoding='utf-8')
                with self.assertRaises(ValueError): exporter.export(root, output, check=True)
                (output/'one.svg').write_text('{"value": 1}', encoding='utf-8')
                manifest = json.loads(before); manifest['files'] = {}
                (output/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'thiếu/thừa'): exporter.export(root, output, check=True)
                (output/'manifest.json').write_bytes(before); source.write_text('changed', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'nguồn'): exporter.export(root, output, check=True)

    def test_export_never_overwrites_unversioned_existing_directory(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder); source = root/exporter.SOURCE
            source.parent.mkdir(); source.write_text('fixture', encoding='utf-8')
            output = root/'bundle'; output.mkdir(); (output/'existing').write_text('keep')
            with (patch.object(exporter, 'load_inputs', return_value=({}, {})),
                  patch.object(exporter, 'analyse', return_value={})):
                with self.assertRaises(ValueError): exporter.export(root, output)
            self.assertEqual((output/'existing').read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
