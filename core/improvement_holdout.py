"""Manifest holdout mới kế thừa selection đã nghiệm thu và lịch W5 bất biến."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from core.candidate_selection import read_technical_gates
from core.historical_signals import digest
from core.improvement_bootstrap import specification
from core.improvement_protocol import SYMBOL_ORDER, code_identity as development_code, protocol, registry
from core.improvement_reports import read_report, read_selection, selection_artifact
from core.prior_run_lock import safe_path
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once, runtime_identity

VERSION = 'improvement_bound_holdout_v1'
NAMESPACE = 'outputs/bayesian_benchmark/improvement_v1/holdout'
DEVELOPMENT = 'outputs/bayesian_benchmark/improvement_v1/development'
REPEATS = 'outputs/bayesian_benchmark/improvement_v1/repeats'
DEVELOPMENT_GATES = 'docs/plan/week8/validation_gates/resilient_restart_v1/technical_gates.json'
FIXTURE = 'docs/plan/week8/fixtures/improvement_bootstrap_v1.json'
NEW_FILES = ('core/improvement_holdout.py', 'core/improvement_holdout_runtime.py',
             'core/improvement_bootstrap.py', 'scripts/run_improvement_holdout.py', FIXTURE)
# Đây là hash byte đã nghiệm thu, không phải checksum lấy từ input tự khai.
SEALED = {
    DEVELOPMENT+'/plan.json': 'f9745d946d81cb008e0a747f8367fe0c85a5fbd989e7148bde997227d651831e',
    DEVELOPMENT+'/run/report.json': '80f707e0f4ee62c384724085249f748e2e82cf6517ccf892ccb97b1603317314',
    DEVELOPMENT+'/run/selection.json': 'cd46ad855ccda8f95a7694e21c34e08c993f6ea110ddc38bab9db4018857b387',
    REPEATS+'/plan.json': 'bb429128c4f13297635778cf044d5a3a89639d4a7b1e6d2c2e507fba190d9b1b',
    REPEATS+'/run/report.json': 'db08fbb381d3837614b0cf6f00e6078c179d13f4a01d49fafb818562cf5cf9e2'}


def sha(path: Path) -> str:
    """Băm byte bằng chứng; code dùng LF theo contract development hiện hữu."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_identity() -> dict[str, str]:
    """Thêm consumer mới, giữ nguyên danh sách và hash 69 dependency development."""
    root = Path(__file__).resolve().parents[1]
    return {**development_code(), **{name: hashlib.sha256((root/name).read_text(encoding='utf-8').encode('utf-8')).hexdigest()
                                   for name in NEW_FILES}}


def _bound_files(root: Path, report: dict[str, Any], run: Path, ledger: dict[str, Any]) -> None:
    """Đối chiếu checkpoint/response/journal và từng HTTP đã bind, không reset ledger."""
    for name, expected in report['binding']['checkpoint_sha256'].items():
        if name.startswith('http:'):
            if name[5:] not in ledger or digest(ledger[name[5:]]) != expected:
                raise ValueError('HTTP audit development/repeat khác bằng chứng đã nghiệm thu')
        else:
            source = Path(name)
            source = source.resolve() if source.is_absolute() else safe_path(run, name)
            if not source.is_relative_to(root) or source.name.startswith('.env') or sha(source) != expected:
                raise ValueError('Checkpoint development/repeat khác byte đã nghiệm thu')


def verified_development(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """Kiểm seal tin cậy, nguồn và consumer selection; không replay prompt đã nghiệm thu."""
    for name, checksum in SEALED.items():
        if sha(safe_path(root, name)) != checksum:
            raise ValueError('Bằng chứng development/repeat/selection khác seal đã nghiệm thu')
    development = read_envelope(root/DEVELOPMENT/'plan.json')
    primary = read_envelope(root/DEVELOPMENT/'run/report.json')
    repeat = read_envelope(root/REPEATS/'run/report.json')
    repeat_plan = read_envelope(root/REPEATS/'plan.json')
    if (development['code_sha256'] != development_code() or development['runtime'] != runtime_identity()
            or primary['primary_status'] != 'COMPLETE' or primary['selection_evidence_status'] != 'DEVELOPMENT'
            or repeat['status'] != 'COMPLETE' or repeat['in_primary'] is not False
            or repeat['binding']['primary_binding'] != primary['binding']
            or repeat_plan['primary_plan'] != development):
        raise ValueError('Development/repeat thiếu completion hoặc khác code/runtime/primary')
    for name, checksum in primary['binding']['sources'].items():
        if sha(safe_path(root, name)) != checksum:
            raise ValueError('Nguồn development khác seal')
    records = json.loads((root/'outputs/oos_pilot/api_usage.json').read_text(encoding='utf-8'))['requests']
    ledger = {r['id']: r for r in records}
    if len(ledger) != len(records):
        raise ValueError('Ledger có HTTP ID trùng')
    _bound_files(root, primary, root/DEVELOPMENT/'run', ledger)
    _bound_files(root, repeat, root/REPEATS/'run', ledger)
    gates = read_technical_gates(root/DEVELOPMENT_GATES, development)
    selected = read_selection(root/DEVELOPMENT/'run/selection.json',
        selection_artifact(primary, gates, SEALED[DEVELOPMENT+'/run/report.json']))
    if (selected['research_candidate'] != 'A_tp_pool' or selected['nomination_status'] != 'PROMOTED'
            or selected['selection_evidence_status'] != 'DEVELOPMENT' or selected['risk_policy'] != 'OFF'):
        raise ValueError('Selection không khớp quyết định development đã khóa')
    return development, selected, {**SEALED, DEVELOPMENT_GATES: sha(root/DEVELOPMENT_GATES)}


def _fixture_development(path: Path, runner: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """Đường fixture dùng runner production offline, tuyệt đối không cấp nomination thật."""
    from core.improvement_runtime import run_primary
    plan = read_envelope(path)
    if plan['split'] != 'fixture' or runner.mode != 'offline_fixture':
        raise ValueError('Runner tiêm chỉ được dùng với fixture offline')
    report = run_primary(runner, plan, runner._holdout_fixture_run, verify_only=True)
    read_report(runner._holdout_fixture_run/'report.json', report)
    expected = selection_artifact(report, {'status': 'NOT_VERIFIED'}, sha(runner._holdout_fixture_run/'report.json'))
    selection = read_selection(runner._holdout_fixture_run/'selection.json', expected)
    return plan, selection, {path.relative_to(runner.adapter._files.root).as_posix(): sha(path)}


def _derive(adapter: Any, *, fixture_plan: Path | None = None, fixture_runner: Any = None) -> dict[str, Any]:
    """Tạo manifest mong đợi chỉ từ nguồn đã khóa, không đọc action/outcome holdout."""
    root = adapter._files.root.resolve()
    fixture = fixture_plan is not None or fixture_runner is not None
    if fixture:
        if fixture_plan is None or fixture_runner is None or fixture_runner.adapter is not adapter:
            raise ValueError('Fixture cần plan/runner cùng adapter, không nhận override một phần')
        dev, selected, proofs = _fixture_development(fixture_plan, fixture_runner)
        cutoffs = deepcopy(dev['symbol_cutoffs']); sources = deepcopy(dev['parent']['sources'])
        primary = 'A_tp_pool'
    else:
        dev, selected, proofs = verified_development(root)
        old = read_envelope(safe_path(root, dev['parent']['path']))
        smoke = read_envelope(safe_path(root, old['parent']['path']))
        lock_proof = smoke['inputs']['input_lock']; lock_path = safe_path(root, lock_proof['path'])
        if sha(lock_path) != lock_proof['sha256']:
            raise ValueError('Input lock W5 khác byte đã khóa')
        lock = read_envelope(lock_path)
        cutoffs = deepcopy(lock['cohorts']['holdout_2024'])
        sources = {**dev['parent']['sources'], lock_proof['path']: lock_proof['sha256']}
        if {s: len(days) for s, days in cutoffs.items()} != dict.fromkeys(SYMBOL_ORDER, 16):
            raise ValueError('Holdout phải kế thừa đủ 64 ngày W5, 16/mã')
        primary = selected['research_candidate']
    stats = specification(primary)
    rows = sorted([{'point_id': s+'-'+d, 'symbol': s, 'as_of_date': d} for s in SYMBOL_ORDER for d in cutoffs[s]],
                  key=lambda r: (r['as_of_date'], SYMBOL_ORDER.index(r['symbol'])))
    schedule = [{**r, 'branches': stats['matrix'][j % len(stats['matrix']):]+stats['matrix'][:j % len(stats['matrix'])]}
                for j, r in enumerate(rows)]
    return {'plan_version': VERSION, 'cohort_id': dev['cohort_id']+'-bound-holdout-v1',
        'split': 'fixture' if fixture else 'holdout_2024', 'symbol_cutoffs': cutoffs,
        'matrix': stats['matrix'], 'schedule': schedule, 'repeat_id': 0,
        'inputs': deepcopy(dev['inputs']), 'registry': registry(), 'protocol': protocol(),
        'protocol_sha256': digest(protocol()), 'price_index': deepcopy(dev['price_index']),
        'development_proof': proofs, 'parent_sources': sources,
        'selection_decision': {'scope': 'FIXTURE_PROTOCOL_ONLY' if fixture else 'DEVELOPMENT_SELECTION',
            'research_candidate': selected['research_candidate'], 'primary_branch': primary,
            'nomination_status': selected['nomination_status'], 'deployment_choice': selected['deployment_choice'],
            'risk_policy': 'OFF'}, 'statistics': stats, 'code_sha256': code_identity(), 'runtime': runtime_identity()}


def _calendar(plan: dict[str, Any], adapter: Any) -> Any:
    """Kiểm PIT/scaler/warm-up/lịch; không tạo nhãn hoặc tính P&L holdout."""
    if adapter.signal_config != plan['inputs']['signal_config'] or any(adapter.prior_config[k] != v for k, v in
        {'enable_bayesian_prior': True, 'mode': 'bayesian_regime', 'k': 3, 'seed': 42, 'scope': 'same_symbol'}.items()):
        raise ValueError('Adapter holdout khác signal config/K/seed/scope')
    proof = plan['price_index']
    index = adapter.load_price_feature_index(proof['path'], expected_sha256=proof['sha256'])
    if index.identity != proof['identity']:
        raise ValueError('Index/scaler holdout khác development')
    for name, checksum in plan['parent_sources'].items():
        adapter._files.pin(name, checksum)
    for symbol, days in plan['symbol_cutoffs'].items():
        if not days or days != sorted(set(days)):
            raise ValueError('Ngày holdout trùng/rỗng/không tăng')
        frame, _ = adapter.execution_data(symbol)
        positions = pd.DatetimeIndex(frame.Datetime).get_indexer(pd.to_datetime(days))
        if (positions < 599).any() or (positions+3 >= len(frame)).any() or (positions[1:]-positions[:-1] < 3).any():
            raise ValueError('Lịch holdout thiếu warm-up/exit hoặc chồng chu kỳ')
        for day, pos in zip(days, positions):
            if plan['split'] == 'holdout_2024' and any(not str(frame.Datetime.iloc[pos+k])[:10].startswith('2024-') for k in (0, 1, 3)):
                raise ValueError('Chu kỳ holdout vượt năm 2024')
            index.scaler(symbol, day)
            adapter.prepare(symbol, day)
    return index


def prepare_plan(destination: Path, adapter: Any, *, fixture_plan: Path | None = None,
                 fixture_runner: Any = None) -> dict[str, Any]:
    """Khóa manifest mới, không tạo run/checkpoint hoặc gọi API."""
    result = _derive(adapter, fixture_plan=fixture_plan, fixture_runner=fixture_runner)
    root = adapter._files.root.resolve(); path = destination.resolve()
    if (not path.is_relative_to(root) or path.name.startswith('.env') or path.exists()
            and read_envelope(path) != result or result['split'] != 'fixture'
            and path != root/NAMESPACE/'plan.json' or path.relative_to(root).as_posix() in result['parent_sources']):
        raise ValueError('Manifest cần namespace mới, không ghi đè nguồn/selection')
    _calendar(result, adapter)
    _write_once(path, result)
    return result


def validate_plan(plan: dict[str, Any], adapter: Any, *, fixture_plan: Path | None = None,
                  fixture_runner: Any = None) -> Any:
    """Tự băm lại input không vượt được seal, lịch/ma trận/spec/code/runtime."""
    if digest(plan) != digest(_derive(adapter, fixture_plan=fixture_plan, fixture_runner=fixture_runner)):
        raise ValueError('Manifest holdout khác selection/nguồn/lịch/protocol/statistics/code/runtime')
    return _calendar(plan, adapter)
