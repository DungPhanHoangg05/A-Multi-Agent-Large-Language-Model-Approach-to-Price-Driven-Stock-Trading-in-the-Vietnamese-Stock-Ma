"""Hồi quy consumer holdout và CLI offline, không dùng key hoặc run nghiên cứu thật."""

from contextlib import nullcontext, redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core.historical_signals import digest
from core.research_cohort import read_envelope, save_envelope
from scripts import verify_improvement_holdout as verifier
from scripts.run_improvement_holdout import release_artifact


class HoldoutOfflineVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        """Dựng đủ support tối thiểu trong workspace tạm, không gọi runner/LLM."""
        self.folder = TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.output = self.root/verifier.NAMESPACE/'run'
        self.source = self.root/verifier.SOURCE
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(Path(verifier.__file__).read_bytes())
        self.names = ['original', 'bayesian', 'C2', 'A_tp_pool',
            'A_tp_pool_stats_only', 'A_tp_pool_examples_only']
        cutoffs = {s: [f'2024-01-{i:02}' for i in range(1, 17)] for s in ('FPT', 'MWG', 'VCB', 'VNM')}
        self.plan = {'split': 'holdout_2024', 'schedule': [{'point_id': s+'-'+d}
            for s, days in cutoffs.items() for d in days], 'matrix': self.names,
            'symbol_cutoffs': cutoffs, 'code_sha256': {'frozen.py': 'a'*64}, 'runtime': {'python': 'fixture'}}
        self.report = {'report_version': verifier.REPORT_VERSION, 'primary_status': 'COMPLETE',
            'matrix': self.names, 'binding': {'plan_sha256': digest(self.plan), 'run_signature': 'b'*64},
            'stocks': {s: {'global_common_support': {'point_ids': [s+'-'+d for d in days],
                'count': 16, 'excluded': []}, 'points': [{'point_id': s+'-'+d,
                'branch_status': dict.fromkeys(self.names, 'complete')} for d in days]}
                for s, days in cutoffs.items()}, 'metric': {'cash_return': 0., 'long_return': 2.5}}
        self.gates = {'status': 'PASS', 'sha256': 'c'*64}
        self.plan_path = self.root/verifier.NAMESPACE/'plan.json'
        save_envelope(self.plan_path, self.plan)
        save_envelope(self.output/'report.json', self.report)
        save_envelope(self.root/verifier.NAMESPACE/'release.json', release_artifact(self.plan, self.gates, self.plan_path))

    def call_main(self, *args: str) -> None:
        """Chỉ giả lập tái dựng; reader, release, receipt và định tuyến CLI chạy thật."""
        with (patch.object(verifier, 'ROOT', self.root),
              patch.object(verifier, 'read_technical_gates', return_value=self.gates),
              patch.object(verifier, 'rebuild', return_value=self.report),
              patch('sys.argv', ['verify_improvement_holdout.py', *args]),
              redirect_stdout(StringIO()), redirect_stderr(StringIO())):
            verifier.main()

    def test_reader_accepts_matching_holdout_without_accepting_legacy_versions(self) -> None:
        self.assertEqual(verifier.read_holdout_report(self.output/'report.json', self.report), self.report)
        for version in ('improvement_report_v1', 'improvement_repeat_report_v1', 'unknown'):
            wrong = {**self.report, 'report_version': version}
            save_envelope(self.output/'report.json', wrong)
            with self.assertRaisesRegex(ValueError, 'version'):
                verifier.read_holdout_report(self.output/'report.json', wrong)

    def test_reader_rejects_rehashed_metric_support_type_and_binding_changes(self) -> None:
        for field in ('metric', 'support', 'binding', 'type'):
            wrong = deepcopy(self.report)
            if field == 'metric': wrong['metric']['long_return'] = 99.
            elif field == 'support': wrong['stocks']['FPT']['global_common_support']['point_ids'].pop()
            elif field == 'binding': wrong['binding']['run_signature'] = 'd'*64
            else: wrong['metric']['cash_return'] = False
            save_envelope(self.output/'report.json', wrong)
            with self.assertRaises(ValueError):
                verifier.read_holdout_report(self.output/'report.json', self.report)

    def test_incomplete_unknown_and_mismatched_schedule_cannot_be_certified(self) -> None:
        for field in ('incomplete', 'unknown', 'missing', 'schedule'):
            wrong = deepcopy(self.report)
            if field == 'incomplete': wrong['primary_status'] = 'INCOMPLETE'
            elif field == 'unknown': wrong['stocks']['FPT']['points'][0]['branch_status']['original'] = 'unknown'
            elif field == 'missing': wrong['stocks']['FPT']['points'][0]['branch_status'].pop('original')
            else: wrong['stocks']['FPT']['points'].reverse()
            with self.assertRaises(ValueError):
                verifier.verification_artifact(self.plan, wrong, self.gates, root=self.root)

    def test_cli_default_certifies_full_payload_and_repeats_without_rewriting_report(self) -> None:
        before = (self.output/'report.json').read_bytes()
        self.call_main()
        self.call_main('--verify-report')
        receipt = read_envelope(self.output/'verification.json')
        self.assertEqual((receipt['points'], receipt['decisions']), (64, 384))
        self.assertEqual(receipt['report_payload_sha256'], digest(self.report))
        self.assertEqual((self.output/'report.json').read_bytes(), before)
        self.assertFalse((self.output/'bootstrap.json').exists())

    def test_cli_verify_only_never_creates_acceptance_or_bootstrap(self) -> None:
        self.report['primary_status'] = 'INCOMPLETE'
        self.call_main('--verify-only')
        self.assertFalse((self.output/'verification.json').exists())
        self.assertFalse((self.output/'bootstrap.json').exists())

    def test_bootstrap_requires_current_receipt_and_consumes_fixed_functions(self) -> None:
        with patch.object(verifier, 'bootstrap_report') as bootstrap:
            with self.assertRaises(FileNotFoundError): self.call_main('--bootstrap')
            bootstrap.assert_not_called()
        self.call_main('--verify-report')
        expected = {'statistics_version': 'improvement_bootstrap_v1', 'status': 'COMPLETE'}
        with patch.object(verifier, 'bootstrap_report', return_value=expected) as bootstrap:
            self.call_main('--bootstrap'); self.call_main('--verify-bootstrap')
            self.assertEqual(bootstrap.call_count, 2)
        self.assertEqual(read_envelope(self.output/'bootstrap.json'), expected)
        wrong = {**expected, 'status': 'BLOCKED'}; save_envelope(self.output/'bootstrap.json', wrong)
        with patch.object(verifier, 'bootstrap_report', return_value=expected):
            with self.assertRaises(ValueError): self.call_main('--verify-bootstrap')

    def test_receipt_code_report_or_seal_drift_blocks_bootstrap_before_statistics(self) -> None:
        self.call_main('--verify-report')
        before = self.source.read_bytes(); self.source.write_bytes(before+'\n# Thay đổi consumer\n'.encode('utf-8'))
        with patch.object(verifier, 'bootstrap_report') as bootstrap:
            with self.assertRaisesRegex(ValueError, 'Receipt'): self.call_main('--bootstrap')
            bootstrap.assert_not_called()
        self.source.write_bytes(before)
        receipt = read_envelope(self.output/'verification.json'); receipt['report_file_sha256'] = 'f'*64
        save_envelope(self.output/'verification.json', receipt)
        with patch.object(verifier, 'bootstrap_report') as bootstrap:
            with self.assertRaisesRegex(ValueError, 'Receipt'): self.call_main('--bootstrap')
            bootstrap.assert_not_called()

    def test_release_drift_blocks_rebuild_and_online_options_are_rejected(self) -> None:
        save_envelope(self.root/verifier.NAMESPACE/'release.json', {'wrong': True})
        with self.assertRaisesRegex(ValueError, 'release'): self.call_main('--verify-report')
        for flag in ('--run', '--resume', '--preflight', '--env-file'):
            with self.assertRaises(SystemExit): self.call_main(flag)

    def test_rebuild_forces_verify_only_with_rejecting_transport(self) -> None:
        self.plan['inputs'] = {'signal_config': {'models': {}, 'language': 'vi',
            'norm_method': 'zscore', 'alpha_weights': {}}}
        clients = []
        def builder(inputs, key, client):
            self.assertEqual(key, 'offline-verifier-no-network'); clients.append(client)
            return SimpleNamespace(agent_llm=object(), graph_llm=object())
        def runtime(*args, **kwargs):
            self.assertTrue(kwargs['verify_only'])
            self.assertEqual(kwargs['ledger_path'], self.root/'outputs/oos_pilot/api_usage.json')
            with self.assertRaisesRegex(AssertionError, 'không được gọi mạng'):
                clients[0].get('https://offline.invalid/')
            return self.report
        with (patch.object(verifier, 'PriorRunLock', return_value=nullcontext()),
              patch.object(verifier, 'make_builder', side_effect=builder),
              patch.object(verifier, 'validate_client'), patch.object(verifier, 'BacktestEngine'),
              patch.object(verifier, 'build_adapter'), patch.object(verifier, 'PriorBacktestRunner'),
              patch.object(verifier, 'run_holdout', side_effect=runtime)):
            self.assertEqual(verifier.rebuild(self.plan, self.gates, self.root), self.report)


if __name__ == '__main__':
    unittest.main()
