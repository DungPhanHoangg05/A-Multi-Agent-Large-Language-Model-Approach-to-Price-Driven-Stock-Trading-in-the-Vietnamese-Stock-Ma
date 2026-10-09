"""Kiểm khóa lịch/input và khả năng tái dùng plan smoke qua CLI cohort."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

from core import research_input_lock as locking
from core.cohort_calendar import design_calendar
from core.groq_pacing import MODEL_LIMITS
from core.historical_signals import digest
from core.prior_config import normalize_prior_config
from core.research_cohort import run_cohort, validate_plan
from test_cohort_calendar import coverage_fixture


def hash_file(path: Path) -> str:
    """Băm byte fixture không chứa credential hoặc kết quả giao dịch."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeAdapter:
    """Nguồn giá tổng hợp; proof xác định, không chứa nhãn hoặc lời gọi LLM."""

    def __init__(self, root: Path, inputs: dict, sources: dict):
        self._files = SimpleNamespace(root=root)
        self.prior_config = normalize_prior_config({'enable_bayesian_prior': True})
        self.signal_config = inputs['signal_config']
        self.source_hashes = sources
        self.frame = pd.DataFrame({'Datetime': pd.bdate_range('2020-01-01', '2025-01-10'),
            'Open': 10., 'High': 11., 'Low': 9., 'Close': 10., 'Volume': 100., 'Reference': 10.})

    def prepare(self, symbol: str, day: str) -> SimpleNamespace:
        """Trả proof synthetic để kiểm lịch và binding độc lập API/model."""
        return SimpleNamespace(source_provenance={'symbol': symbol, 'day': day}, market_regime={'day': day})

    def execution_data(self, symbol: str) -> tuple[pd.DataFrame, list]:
        """Cùng lịch giao dịch cho bốn mã tổng hợp."""
        return self.frame.copy(), []

    def verify_sources(self) -> None:
        """Kiểm mọi nguồn đã ghim trong fixture."""
        for name, expected in self.source_hashes.items():
            if hash_file(self._files.root / name) != expected:
                raise ValueError('Nguồn fixture thay đổi')


class ResearchInputLockTests(unittest.TestCase):
    """Chống sửa lịch/config/hash sau khóa, không tự nâng quota pending."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / 'outputs/bayesian_benchmark'
        self.directory.mkdir(parents=True)
        self.calendar_path = self.directory / 'calendar.json'
        self.input_path = self.root / 'outputs/oos_pilot/inputs/plan.json'
        self.legacy = {field: {} for field in locking.INPUT_FIELDS}
        self.legacy.update(execution_dir='prices', news_dir='news', limits=deepcopy(MODEL_LIMITS),
            signal_config={'window_size': 45}, model={'freeze_as_of_date': '2022-12-31'})
        locking._write_once(self.input_path, self.legacy)
        self.sources = {'outputs/oos_pilot/inputs/plan.json': hash_file(self.input_path)}
        self.adapter = FakeAdapter(self.root, self.legacy, self.sources)
        coverage = coverage_fixture()
        for symbol, stock in coverage['stocks'].items():
            for row in stock['calendar']:
                row['proof_sha256'] = digest({'symbol': symbol, 'day': row['as_of_date']})
                row['regime_state_sha256'] = digest({'day': row['as_of_date']})
        coverage.update(sources=self.sources, code_sha256={})
        self.coverage_path = self.directory / 'coverage.json'
        self.coverage_path.write_text(json.dumps({'payload': coverage, 'sha256': digest(coverage)}), encoding='utf-8')
        self.calendar = design_calendar(coverage, {s: [] for s in coverage['stocks']})
        self.calendar.update(sources={**self.sources, 'outputs/bayesian_benchmark/coverage.json': hash_file(self.coverage_path)},
            code_sha256={}, verification={'selected_pit_and_execution': 'PASS'})
        self.calendar_path.write_text(json.dumps({'payload': self.calendar, 'sha256': digest(self.calendar)}), encoding='utf-8')
        (self.root / 'code.py').write_text('code', encoding='utf-8')
        for target, options in (
            ('core.pilot_readiness.verify_inputs', {'return_value': self.legacy}),
            ('core.pilot_readiness.build_adapter', {'return_value': self.adapter}),
            ('core.research_input_lock.runtime_identity', {'return_value': {'python': '3.13.5'}})):
            mock = patch(target, **options)
            mock.start()
            self.addCleanup(mock.stop)
        for target, value in (('ROOT', self.root), ('CODE_PATHS', ('code.py',))):
            mock = patch.object(locking, target, value)
            mock.start()
            self.addCleanup(mock.stop)

    def prepare(self) -> dict:
        """Gọi đúng producer bằng file fixture đã băm, không giả validator."""
        return locking.prepare_inputs(self.calendar_path, root=self.root)

    def test_prepare_verify_idempotent_and_smoke_plan_accepted_by_existing_runner(self) -> None:
        """Hai file runtime đủ cho luồng chính; verify không sửa byte."""
        lock = self.prepare()
        self.assertEqual(lock['dry_run']['verified_points'], 132)
        self.assertEqual(lock['dry_run']['by_cohort'], {'smoke':4, 'development_2023':64, 'holdout_2024':64})
        self.assertEqual(lock['budget_status'], 'DEFERRED_BY_USER')
        self.assertEqual(lock['benchmark_protocol'], 'PENDING_W7')
        before = {p: p.read_bytes() for p in self.directory.glob('*.json')}
        self.assertEqual(lock, self.prepare())
        self.assertEqual(lock, locking.verify_inputs(root=self.root))
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)
        plan = locking._read(self.directory / 'smoke_plan.json')
        validate_plan(plan, self.adapter)
        self.assertEqual(plan['matrix'], 'smoke_v1')
        self.assertFalse((self.directory / 'holdout_plan.json').exists())

    def test_hash_valid_plan_date_model_and_seed_changes_are_rejected(self) -> None:
        """Băm lại plan không cho phép đổi nội dung smoke đã ràng buộc."""
        self.prepare()
        original = locking._read(self.directory / 'smoke_plan.json')
        for field in ('date', 'model', 'seed', 'matrix'):
            changed = deepcopy(original)
            if field == 'date':
                changed['symbol_cutoffs']['FPT'] = self.calendar['cohorts']['development_2023']['symbol_cutoffs']['FPT'][:1]
            elif field == 'model':
                changed['inputs']['model']['freeze_as_of_date'] = '2024-01-01'
            elif field == 'seed':
                changed['evidence_config']['seed'] = 0
            else:
                changed['matrix'] = 'research_v2'
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_plan(changed, self.adapter)
        runner = SimpleNamespace(adapter=self.adapter, quota_policy='whole_point_v1')
        ledger = self.root / 'outputs/oos_pilot/api_usage.json'
        with self.assertRaisesRegex(ValueError, 'policy hoặc ledger'):
            run_cohort(runner, original, self.directory / 'unused_run', ledger_path=ledger)
        runner.quota_policy = 'request_admission_v2'
        with self.assertRaisesRegex(ValueError, 'policy hoặc ledger'):
            run_cohort(runner, original, self.directory / 'unused_run', ledger_path=self.root / 'other_ledger.json')

    def test_source_code_runtime_schema_and_gate_changes_rejected(self) -> None:
        """Dependency và policy đã khóa; không bỏ checksum hoặc tự đổi pending thành PASS."""
        lock = self.prepare()
        for field, value in (('code_sha256', {}), ('budget_status', 'PASS'), ('gate_c', 'PASS'),
                             ('quota_policy', 'whole_point_v1'), ('economic_contract', {'short':'SHORT_SELL'})):
            changed = {**lock, field:value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                locking.validate_lock(changed, self.root)
        with patch.object(locking, 'runtime_identity', return_value={'python':'3.14.0'}), self.assertRaises(ValueError):
            locking.validate_lock(lock, self.root)
        (self.root / 'code.py').write_text('changed', encoding='utf-8')
        with self.assertRaises(ValueError):
            locking.validate_lock(lock, self.root)

    def test_manifest_cannot_change_holdout_dates_or_drop_sources(self) -> None:
        """Khóa dữ liệu 2024 độc lập cấu hình ứng viên W7."""
        lock = self.prepare()
        changed = deepcopy(lock)
        changed['cohorts']['holdout_2024']['FPT'].pop()
        with self.assertRaises(ValueError):
            locking.validate_lock(changed, self.root)
        changed = deepcopy(lock)
        changed['sources'].pop('outputs/bayesian_benchmark/coverage.json')
        with self.assertRaises(ValueError):
            locking.validate_lock(changed, self.root)

    def test_write_once_rejects_other_identity_and_invalid_json(self) -> None:
        """Ghi nguyên tử và envelope strict không biến file cũ thành identity mới."""
        path = self.directory / 'one.json'
        locking._write_once(path, {'value':1})
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            locking._write_once(path, {'value':2})
        self.assertEqual(path.read_bytes(), before)
        path.write_text('{"payload":1,"payload":2,"sha256":"bad"}', encoding='utf-8')
        with self.assertRaises(ValueError):
            locking._read(path)

    def test_failed_pit_proof_or_wrong_selection_never_writes_lock(self) -> None:
        """Lỗi liêm chính phải dừng trước khi khóa artifact."""
        with patch.object(self.adapter, 'prepare', return_value=SimpleNamespace(source_provenance={}, market_regime={})), self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse((self.directory / 'input_lock.json').exists())
        self.calendar['cohorts']['holdout_2024']['symbol_cutoffs']['FPT'].pop()
        self.calendar_path.write_text(json.dumps({'payload':self.calendar, 'sha256':digest(self.calendar)}), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.prepare()

    def test_existing_execution_blocks_first_lock_and_credential_is_never_opened(self) -> None:
        """Không khóa hồi tố sau run hoặc đọc .env bằng path tùy chỉnh."""
        run = self.directory / 'some_run'
        run.mkdir()
        (run / 'cohort.json').write_text('{}', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.prepare()
        with patch.object(Path, 'read_text', side_effect=AssertionError('Cấm đọc key')), self.assertRaises(ValueError):
            locking._read(self.root / '.env')


if __name__ == '__main__':
    unittest.main()
