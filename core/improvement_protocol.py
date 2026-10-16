"""Registry, protocol và plan revision riêng; không sửa binding nghiên cứu cũ."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

from core.candidate_cohort import CODE_FILES, inherited_plan, registry as legacy_registry
from core.candidate_selection import RULES
from core.historical_signals import digest
from core.improvement_prior import BASES, PROFILES, PREFIXES, EVIDENCE_VERSION, STATISTICS_VERSION
from core.prior_config import copy_prior_json
from core.prior_run_lock import safe_path
from core.research_cohort import read_envelope
from core.research_input_lock import runtime_identity, _write_once

PLAN_VERSION = 'improvement_cohort_plan_v1'
REGISTRY_VERSION = 'improvement_candidates_v1'
MATRIX = ('original', 'bayesian', *BASES, 'C2_stats_only', 'C2_examples_only',
          'A_tp_pool_stats_only', 'A_tp_pool_examples_only', 'B_semantic_stats_only', 'B_semantic_examples_only')
SYMBOL_ORDER = ('FPT', 'MWG', 'VCB', 'VNM')
REPEAT_IDS = ('FPT-2023-06-27', 'FPT-2023-10-04', 'FPT-2023-12-22',
              'MWG-2023-06-30', 'MWG-2023-03-06', 'MWG-2023-12-22',
              'VCB-2023-03-06', 'VCB-2023-08-29', 'VCB-2023-12-22',
              'VNM-2023-01-06', 'VNM-2023-06-30', 'VNM-2023-12-19')
CLIENT_OPTIONS = {'agent': {'reasoning_effort': 'low', 'reasoning_format': 'hidden'},
                  'graph': {'reasoning_effort': 'none', 'reasoning_format': 'hidden'}}
NEW_CODE = ('core/improvement_prior.py', 'core/improvement_protocol.py', 'core/improvement_runtime.py',
            'core/improvement_reports.py', 'core/improvement_diagnostics.py', 'core/improvement_transport.py',
            'scripts/run_improvement.py', 'core/provider_quota.py', 'scripts/run_provider_validation.py')


def registry() -> dict[str, Any]:
    """Hồ sơ cố định 11 nhánh, chỉ ba full-prior tham gia nomination."""
    old = legacy_registry()
    profiles = {'original': {'decision': 'decision_legacy_v1', 'prior_k': 0},
                'bayesian': {'decision': 'decision_legacy_v1', 'prior_k': 3, 'prefix': 'compact_brpp_v1'}}
    for name in MATRIX[2:]:
        base, mode = PROFILES[name]
        profiles[name] = {'base': base, 'evidence': EVIDENCE_VERSION if base == 'A_tp_pool' else 'prior_evidence_v3',
            'statistics': STATISTICS_VERSION if base == 'A_tp_pool' else 'conditional_disjoint_beta_v1',
            'gate': 'split_quality_gate_v2', 'prefix': PREFIXES[base], 'decision': 'decision_legacy_v1', 'content_mode': mode}
    return {'registry_version': REGISTRY_VERSION, 'order': list(MATRIX), 'nomination_order': list(BASES),
        'profiles': profiles, **{k: deepcopy(old[k]) for k in
            ('selection', 'statistics', 'quality', 'feature_versions', 'economic_contract', 'risk_policy')}}


def nomination_rules() -> dict[str, Any]:
    """Chỉ đổi version/danh sách ứng viên; bảo toàn ngưỡng kinh tế và tie."""
    return {**deepcopy(RULES), 'rule_version': 'improvement_nomination_rules_v1', 'candidate_order': list(BASES)}


def protocol() -> dict[str, Any]:
    """Đối tượng phương pháp bất biến, độc lập tiến độ và nội dung README."""
    return {'protocol_version': 'improvement_protocol_v1', 'registry': registry(), 'rules': nomination_rules(),
        'symbol_order': list(SYMBOL_ORDER), 'primary_repeat_id': 0, 'rotation': 'left_j_mod_M',
        'repeat_ids': list(REPEAT_IDS), 'repeat_count': 3, 'repeat_rotation': 'left_(3j+r-1)_mod_(M+1)',
        'repeat_duplicate': 'original_duplicate', 'repeat_selection': 'C2_readiness_S_first_E_ONLY_lower_median_OFF_last',
        'repeat_in_primary': False, 'prior_chars': 600, 'prompt_chars_exclusive': 6500,
        'client_options': deepcopy(CLIENT_OPTIONS), 'client_max_retries': 0, 'client_service_tier': 'on_demand',
        'retry': 'invocation_budget_v2', 'quota': 'provider_daily_quota_v1',
        'train': {'queries': 651, 'folds': [2021, 2022], 'bootstrap': 2020, 'llm_calls': 0,
                  'probability': 'win_rate_long', 'loss_clip': [1e-6, 1-1e-6], 'support': 'finite_A_intersect_C2'},
        'subgroups': ['Q1', 'Q2', 'Q3', 'Q4', 'H1', 'H2', 'leave_one_symbol_out', 'prior_off', 'both_off', 'both_ready'],
        'holdout': {'count': 64, 'per_symbol': 16, 'block': 4, 'sensitivity_blocks': [2, 8],
                    'bootstrap': 'circular_cutoff_date_clusters_account_rebuild', 'draws': 10000,
                    'rng': 'PCG64', 'seed': 20261016, 'minimum_valid': 9500, 'ci': .95,
                    'quantile_method': 'linear', 'secondary': 'Bonferroni'},
        'stop': {'new_methods': 2, 'rounds': 1, 'end': 'W8', 'allow_AB_combination': False}}


def code_identity() -> dict[str, str]:
    """Băm LF toàn dependency phương pháp/transport/CLI mới, giữ hash cũ nguyên trạng."""
    root = Path(__file__).resolve().parents[1]
    return {name: hashlib.sha256((root/name).read_text(encoding='utf-8').encode('utf-8')).hexdigest()
            for name in sorted(set((*CODE_FILES, *NEW_CODE, 'core/train_pit_validation.py')))}


def calendar(plan: dict[str, Any]) -> list[dict[str, str]]:
    """Lịch toàn cohort theo cutoff rồi thứ tự mã đã đăng ký."""
    return sorted([{'point_id': f'{s}-{d}', 'symbol': s, 'as_of_date': d}
                   for s in SYMBOL_ORDER for d in plan['symbol_cutoffs'][s]],
                  key=lambda row: (row['as_of_date'], SYMBOL_ORDER.index(row['symbol'])))


def branch_order(j: int, repeat_id: int = 0) -> list[str]:
    """Xoay nhánh xác định; HTTP retry không thay chỉ số lượt khoa học."""
    if type(j) is not int or j < 0 or type(repeat_id) is not int or repeat_id not in (0, 1, 2, 3):
        raise ValueError('Chỉ số point/lượt không hợp lệ')
    names = [*MATRIX, *(['original_duplicate'] if repeat_id else [])]
    shift = (3*j+repeat_id-1 if repeat_id else j) % len(names)
    return names[shift:] + names[:shift]


def _parent(path: Path, adapter: Any) -> tuple[dict[str, Any], dict[str, str]]:
    """Kế thừa lịch/nguồn cũ, không giả rằng code hiện tại có identity W7."""
    if path.name.startswith('.env'):
        raise ValueError('Parent không được trỏ vào credential')
    old = read_envelope(path)
    if old.get('split') == 'development_2023' and hashlib.sha256(path.read_bytes()).hexdigest() != \
            'e0c32d272d93bd7b3fa87c08c6a70b4851d2cdcbd620675976b4e9c8f7e95960':
        raise ValueError('Parent development W7 khác plan đã khóa; tự băm lại không tạo provenance mới')
    if old.get('plan_version') != 'research_cohort_plan_v3' or old['candidate_registry'] != legacy_registry():
        raise ValueError('Parent phải là plan ứng viên W7, registry cũ nguyên trạng')
    if old['split'] not in ('fixture', 'development_2023'):
        raise ValueError('Cải tiến chưa nhận holdout')
    parent = old['parent']
    base, sources = inherited_plan(safe_path(adapter._files.root, parent['path']), adapter._files.root, parent['split'])
    if old['inputs'] != base['inputs'] or old['symbol_cutoffs'] != base['symbol_cutoffs'] or sources != parent['sources']:
        raise ValueError('Parent W7 khác lịch/nguồn đã khóa')
    sources[path.resolve().relative_to(adapter._files.root.resolve()).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if old['split'] == 'development_2023':
        references = {
            'outputs/bayesian_benchmark/development_candidate_run_v2/report.json':
                '57026e012e3fa6032ad81bbe6100af580fd0a59900f3d1f9370fdb32941ed1c8',
            'outputs/bayesian_benchmark/development_candidate_run_v2/candidate_selection_v1.json':
                '82f5926ac44f1d9263ac49d0bc2cbb2f11066db11a9e842f009bfca4588592a4'}
        for name, checksum in references.items():
            if hashlib.sha256(safe_path(adapter._files.root, name).read_bytes()).hexdigest() != checksum:
                raise ValueError('Bằng chứng chọn mẫu W7 khác byte đã khóa trước cải tiến')
            sources[name] = checksum
    return old, sources


def prepare_plan(parent_path: Path, destination: Path, adapter: Any) -> dict[str, Any]:
    """Producer plan offline, không tạo run hoặc sửa nguồn/index W7."""
    root = adapter._files.root.resolve()
    if destination.name.startswith('.env') or destination.resolve() == parent_path.resolve() or not destination.resolve().is_relative_to(root):
        raise ValueError('Plan cải tiến cần đường mới trong workspace')
    old, sources = _parent(parent_path, adapter)
    if old['split'] == 'development_2023' and not destination.resolve().is_relative_to(
            (root/'outputs/bayesian_benchmark/improvement_v1').resolve()):
        raise ValueError('Plan thật cần namespace cải tiến riêng')
    index = old['price_index']
    plan = {'plan_version': PLAN_VERSION, 'cohort_id': old['cohort_id'] + '-improvement-v1',
        'split': old['split'], 'symbol_cutoffs': deepcopy(old['symbol_cutoffs']), 'inputs': deepcopy(old['inputs']),
        'registry': registry(), 'protocol': protocol(), 'protocol_sha256': digest(protocol()),
        'price_index': deepcopy(index), 'parent': {'path': parent_path.resolve().relative_to(root).as_posix(), 'sources': sources},
        'code_sha256': code_identity(), 'runtime': runtime_identity()}
    validate_plan(plan, adapter)
    _write_once(destination, plan)
    return plan


def validate_plan(plan: dict[str, Any], adapter: Any) -> Any:
    """Loader semantic kiểm parent/lịch/index/config/code trước mọi API/resume."""
    plan = copy_prior_json(plan)
    keys = {'plan_version', 'cohort_id', 'split', 'symbol_cutoffs', 'inputs', 'registry', 'protocol',
            'protocol_sha256', 'price_index', 'parent', 'code_sha256', 'runtime'}
    if (set(plan) != keys or plan['plan_version'] != PLAN_VERSION or plan['registry'] != registry()
            or plan['protocol'] != protocol() or plan['protocol_sha256'] != digest(protocol())
            or plan['code_sha256'] != code_identity() or plan['runtime'] != runtime_identity()
            or set(plan['parent']) != {'path', 'sources'}):
        raise ValueError('Plan cải tiến khác version/registry/protocol/code/runtime')
    old, sources = _parent(safe_path(adapter._files.root, plan['parent']['path']), adapter)
    if (plan['parent']['sources'] != sources or plan['inputs'] != old['inputs'] or plan['split'] != old['split']
            or plan['symbol_cutoffs'] != old['symbol_cutoffs'] or plan['price_index'] != old['price_index']
            or plan['cohort_id'] != old['cohort_id']+'-improvement-v1' or adapter.signal_config != plan['inputs']['signal_config']):
        raise ValueError('Plan cải tiến khác parent/signal config')
    if any(adapter.prior_config[k] != v for k, v in
           {'enable_bayesian_prior': True, 'mode': 'bayesian_regime', 'k': 3, 'seed': 42, 'scope': 'same_symbol'}.items()):
        raise ValueError('Adapter cải tiến khác K/seed/scope')
    if plan['split'] == 'development_2023':
        if ({s: len(days) for s, days in plan['symbol_cutoffs'].items()} != RULES['planned']
                or plan['inputs'].get('client_options') != CLIENT_OPTIONS):
            raise ValueError('Development phải giữ 60 point và client options W7')
    proof = plan['price_index']
    if set(proof) != {'path', 'sha256', 'identity'} or Path(proof['path']).name.startswith('.env'):
        raise ValueError('Binding index cải tiến không hợp lệ')
    index = adapter.load_price_feature_index(proof['path'], expected_sha256=proof['sha256'])
    if index.identity != proof['identity']:
        raise ValueError('Identity index khác plan cải tiến')
    for name, checksum in {**sources, proof['path']: proof['sha256']}.items():
        adapter._files.pin(name, checksum)
    for row in calendar(plan):
        index.scaler(row['symbol'], row['as_of_date'])
        adapter.prepare(row['symbol'], row['as_of_date'])
    import pandas as pd
    from core.execution_prices import execution_prices_for_cycle
    for symbol in SYMBOL_ORDER:
        frame, events = adapter.execution_data(symbol)
        dates = pd.DatetimeIndex(frame.Datetime)
        positions = dates.get_indexer(pd.to_datetime(plan['symbol_cutoffs'][symbol]))
        if (positions < 599).any() or (positions+3 >= len(frame)).any() or (positions[1:]-positions[:-1] < 3).any():
            raise ValueError('Lịch cải tiến thiếu warm-up/exit hoặc cycle chồng lấn')
        for day, position in zip(plan['symbol_cutoffs'][symbol], positions):
            execution_prices_for_cycle(frame, events, day, dates[position+1].strftime('%Y-%m-%d'), dates[position+3].strftime('%Y-%m-%d'))
    return index


def read_plan(path: Path, adapter: Any) -> dict[str, Any]:
    """Đọc envelope rồi bắt buộc kiểm ngữ nghĩa plan revision."""
    plan = read_envelope(path)
    validate_plan(plan, adapter)
    return plan


def repeat_sample(plan: dict[str, Any]) -> list[str]:
    """Mẫu thật khóa trước API; fixture chỉ dùng lịch fixture, không nhận là 12 mẫu thật."""
    ids = [row['point_id'] for row in calendar(plan)]
    selected = list(REPEAT_IDS) if plan['split'] == 'development_2023' else ids
    if not set(selected).issubset(ids):
        raise ValueError('Mẫu repeat không nằm trong lịch primary')
    return [key for key in ids if key in selected]
