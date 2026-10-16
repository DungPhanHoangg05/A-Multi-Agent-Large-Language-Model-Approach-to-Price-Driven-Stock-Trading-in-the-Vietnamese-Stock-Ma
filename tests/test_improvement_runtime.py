"""Cohort/repeat revision dùng graph, adapter, giá và journal thật với LLM offline."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from core.historical_signals import digest
from core.improvement_protocol import MATRIX, calendar, branch_order, prepare_plan, validate_plan
from core.improvement_runtime import run_primary, run_repeats, decision_path, prepare_repeat_plan, reconcile
from core.improvement_reports import read_report, read_selection, selection_artifact
from core.research_cohort import read_envelope, save_envelope
from core.research_input_lock import _write_once
from core.groq_pacing import PilotStop
from test_candidate_cohort import CandidateSetup, CandidateLlm


class ImprovementRuntimeTests(CandidateSetup, unittest.TestCase):
    """Fixture chỉ kiểm protocol, không là kết quả cải thiện hoặc nomination thật."""

    def setUp(self) -> None:
        super().setUp()
        self.builder.agent_llm = self.llm = CandidateLlm(structured=True)
        self.new_plan = prepare_plan(self.plan_path, self.fx.root/'improvement_plan.json', self.adapter)

    def execute(self, **options):
        """Luồng production riêng, không chạy sáu ứng viên W7 phụ trợ."""
        return run_primary(self.runner, self.new_plan, self.output, **options)

    def test_matrix_rotation_shared_once_off_bytes_and_complete_resume(self) -> None:
        parent_bytes = self.plan_path.read_bytes()
        report = self.execute()
        self.assertEqual(report['primary_status'], 'COMPLETE')
        self.assertEqual(self.llm.calls, 44)
        self.assertEqual(self.events, ['indicator', 'pattern', 'trend', 'full']*4)
        expected_order = [(row['point_id'], name) for j, row in enumerate(calendar(self.new_plan)) for name in branch_order(j)]
        self.assertEqual(self.llm.call_order, expected_order)
        self.assertEqual(report['selection_evidence_status'], 'NOT_APPLICABLE')
        for row in calendar(self.new_plan):
            slots = {n: read_envelope(decision_path(self.output, row['point_id'], n)) for n in MATRIX}
            self.assertEqual(len({d['shared_sha256'] for d in slots.values()}), 1)
            self.assertEqual(slots['C2']['evidence'], slots['B_semantic']['evidence'])
            self.assertEqual(slots['C2']['evidence']['selection'], slots['A_tp_pool']['evidence']['selection'])
            for doc in slots.values():
                self.assertLess(len(doc['prompt']), 6500)
                if doc['request']:
                    self.assertLessEqual(len(doc['request']['prefix']), 600)
                    self.assertEqual(doc['request']['decision_contract_version'], 'decision_legacy_v1')
                    if not doc['request']['prefix']:
                        self.assertEqual(doc['prompt'].encode(), slots['original']['prompt'].encode())
        self.assertEqual(self.execute(resume=True), report)
        self.assertEqual(self.execute(verify_only=True), report)
        self.assertEqual(self.llm.calls, 44)
        self.assertEqual(self.plan_path.read_bytes(), parent_bytes)
        _write_once(self.output/'report.json', report)
        read_report(self.output/'report.json', report)
        selected = selection_artifact(report, {'status': 'PASS'}, 'a'*64)
        self.assertEqual(selected['nomination_status'], 'BLOCKED')
        _write_once(self.output/'selection.json', selected)
        read_selection(self.output/'selection.json', selected)

    def test_three_repeats_duplicate_same_request_no_upstream_or_primary_mutation(self) -> None:
        report = self.execute()
        _write_once(self.output/'report.json', report)
        protected = {p: p.read_bytes() for p in self.output.rglob('*.json') if p.name != 'run.owner.json'}
        plan = prepare_repeat_plan(self.runner, self.new_plan, self.output, self.fx.root/'repeat_plan.json')
        repeat_root = self.fx.root/'repeats'
        repeated = run_repeats(self.runner, plan, repeat_root)
        self.assertEqual(repeated['status'], 'COMPLETE')
        self.assertEqual(self.llm.calls, 44+4*3*12)
        self.assertEqual(len(self.events), 16)
        self.assertFalse(repeated['in_primary'])
        self.assertEqual(repeated['disagreement']['C2']['observed_pairs'], 12)
        self.assertEqual(repeated['contrasts']['A_tp_pool__C2']['mean_three_repeats_pp'], 0.)
        self.assertEqual(run_repeats(self.runner, plan, repeat_root, verify_only=True), repeated)
        self.assertEqual(run_repeats(self.runner, plan, repeat_root, resume=True), repeated)
        for path, data in protected.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual(self.execute(verify_only=True), report)

    def test_unknown_requires_exact_uuid_and_does_not_replay_completed_upstream(self) -> None:
        original = self.llm.structured_call
        def fail(prompt, schema):
            if self.llm.calls == 2:
                raise RuntimeError('Mất response fixture')
            return original(prompt, schema)
        with patch.object(self.llm, 'structured_call', side_effect=fail):
            with self.assertRaises(PilotStop):
                self.execute()
        partial = self.execute(verify_only=True)
        self.assertEqual(partial['primary_status'], 'INCOMPLETE')
        pid = calendar(self.new_plan)[0]['point_id']
        path = decision_path(self.output, pid, branch_order(0)[2])
        attempt = read_envelope(path)['attempts'][-1]['attempt_id']
        calls = self.llm.calls
        with self.assertRaises(ValueError):
            self.execute(resume=True)
        self.assertEqual(self.llm.calls, calls)
        with self.assertRaises(ValueError):
            reconcile(self.runner, self.new_plan, self.output, attempt_id='00000000-0000-0000-0000-000000000001', reason='Đã đối soát')
        reconcile(self.runner, self.new_plan, self.output, attempt_id=attempt, reason='Fixture chứng minh cần replay')
        self.assertEqual(self.execute(resume=True)['primary_status'], 'COMPLETE')
        self.assertEqual(len(self.events), 16)
        self.assertEqual(self.llm.calls, 44)

    def test_rehashed_request_raw_response_registry_missing_slot_and_repeat_tamper(self) -> None:
        report = self.execute()
        calls = self.llm.calls
        pid = calendar(self.new_plan)[0]['point_id']
        path = decision_path(self.output, pid, 'A_tp_pool')
        original = path.read_bytes()
        for change in ('prompt', 'posterior', 'raw', 'repeat', 'projection'):
            doc = read_envelope(path)
            if change == 'prompt':
                doc['prompt'] += 'sai'
            elif change == 'posterior':
                doc['evidence']['statistics']['metrics']['win_rate_long']['posterior_mean'] = .123
                doc['evidence']['base_evidence_sha256'] = digest({k: v for k, v in doc['evidence'].items() if k != 'base_evidence_sha256'})
            elif change == 'raw':
                doc['attempts'][-1]['output']['messages'][0]['data']['tool_calls'][0]['args']['decision'] = 'SHORT'
            elif change == 'repeat':
                doc['repeat_id'] = 1
            else:
                doc['attempts'][-1]['output']['evaluation'] = {'outcome': 'Cấm đưa vào projection'}
            save_envelope(path, doc)
            with self.assertRaises(ValueError):
                self.execute(resume=True)
            path.write_bytes(original)
        path.unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.execute(resume=True)
        path.write_bytes(original)
        wrong = deepcopy(self.new_plan)
        wrong['registry']['quality']['min_population_count'] = 1
        with self.assertRaises(ValueError):
            validate_plan(wrong, self.adapter)
        self.assertEqual(self.llm.calls, calls)
        self.assertEqual(self.execute(verify_only=True), report)
