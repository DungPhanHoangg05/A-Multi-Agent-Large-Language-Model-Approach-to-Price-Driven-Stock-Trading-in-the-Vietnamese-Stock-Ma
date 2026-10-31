"""Khóa amendment v4.1: ngân hàng numeric có mask và panel Original256."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from core.mt_bicl_v4_dataset import immutable
from core.mt_bicl_v4_protocol import canonical, checksum, git, read, verify as verify_parent

ROOT_DOC = Path('docs/plan/week11')
PROTOCOL = ROOT_DOC / 'protocol_v4_1.json'
LOCK = ROOT_DOC / 'protocol_lock_v4_1.json'
PARENT = ROOT_DOC / 'protocol_v4.json'
PANEL_SHA = 'a2ee95af8d2bc817a495c1fa26cae37a70dacafe2dad36c0fd364d6fd3e2145c'
NAMESPACE = Path('outputs/bayesian_benchmark/mt_bicl_v4_1')
CORE = (0, 7, 8)
SOURCES = ('core/mt_bicl_v41_protocol.py', 'scripts/prepare_mt_bicl_v4_1.py',
           'tests/test_mt_bicl_v41_protocol.py')


def expected_spec(parent: dict[str, Any]) -> dict[str, Any]:
    """Chỉ áp thay đổi đã đăng ký tại mục26; giữ registry/economics/model và cutoff."""
    def rename(value: Any) -> Any:
        if isinstance(value, dict):
            return {rename(k): rename(v) for k, v in value.items()}
        if isinstance(value, list):
            return [rename(v) for v in value]
        return value.replace('No_agent_features', 'Complete_case_MT').replace('_v4.', '_v4_1.') if isinstance(value, str) else value
    spec = rename(deepcopy(parent))
    spec.update(version='conditional_mt_bicl_protocol_v4_1', status='SPEC_ONLY', namespace=NAMESPACE.as_posix(),
                next_stage='W11_18_NUMERIC_BANK_AND_PANEL256')
    spec['amendment'] = {'authority': 'USER_IMPLEMENT_UPDATED_W11_18A_TO_18F_2026_11_01',
                         'parent_protocol_sha256': checksum(canonical(parent)),
                         'learner_agent_features': False, 'Original_policy_only': True}
    spec['operation'].update(target_collection_days=[3, 5], target_is_runtime_cap=False,
                             coordinator='ONE_WRITER_FOUR_INDEPENDENT_SCOPES_FIXED_SHARDS',
                             credential_variables=[f'GROQ_API_KEY_{i}' for i in range(1, 5)],
                             daily_points_target_per_scope=16)
    minimum = spec['data']['minimum_support']
    for key in ('agent_valid_fraction_each_outer_symbol', 'agent_valid_train_cycles_per_symbol', 'inner_agent_valid_train_cycles_per_symbol'):
        minimum.pop(key)
    minimum.update(core_fraction_each_outer_symbol=.7, failure='INSUFFICIENT_NUMERIC_DATA_NO_AUTO_RESPLIT')
    spec['data']['agent_generation'] = 'PANEL256_ONLY_SHARED_UPSTREAM_ONCE_DURABLE_ORIGINAL_NO_LEGACY_REPORT_REUSE'
    spec['features'].update(agent_categories={}, conflict_features=[], agent_parser='NOT_LEARNER_INPUT',
        confidence='EXCLUDED', sentiment='ONLY_IN_ORIGINAL_NO_LEARNER_FEATURE',
        core_indices=list(CORE), optional_indices=[1, 2, 3, 4, 5, 6],
        scaling='OBSERVED_PER_DIMENSION_TRAIN_MATURE_PREFIX_SAMPLE_STD_FLOOR_1e-8_MIN_TWO_VALUES_ELSE_DIM_UNAVAILABLE',
        missing='ZERO_AFTER_OBSERVED_STANDARDIZATION_PLUS_NINE_BOOLEAN_MASKS_NO_OUTCOME_IMPUTATION',
        query_fallback='MISSING_CORE_OR_OBSERVED_DIM_WITHOUT_SCALER_OR_OOD_KEEP_DURABLE_ORIGINAL_ON_PANEL',
        no_agent_ablation='REPLACED_BY_COMPLETE_CASE_MT_SAME_SELECTION_BUDGET',
        complete_case='ALL_NINE_OBSERVED_IN_FIT_D_C_QUERY_OTHERWISE_COMMON_FORECAST_FALLBACK_AND_PANEL_A0')
    spec['reference']['phi'] = 'INTERCEPT_STANDARDIZED_NUMERIC9_MASK9_REGIME_ONEHOT_ONLY'
    for name in ('pooled_ridge', 'small_nonlinear'):
        spec['baselines'][name]['feature_maps'] = ['NUMERIC_MASK_REGIME']
    spec['learner']['comparators'] = 'K0_POOLED_COMPLETE_CASE_RETRAIN_MATCHED_CAPACITY_SEEDS_STEPS_SEARCH_SPACE;NO_TARGET_EMPTY_C_TRAIN_DOMAIN'
    spec['mechanism_fixtures']['generation'] = spec['mechanism_fixtures']['generation'].replace(
        'AGENT_ONEHOT_UNIFORM_VALID_LEVELS_CONFLICTS_RECOMPUTED',
        'MASK9_FIXED_INDEPENDENT_MCAR_OPTIONAL_DIMENSIONS_ONLY_CORE_ALWAYS_OBSERVED;ZERO_FILL_AFTER_SCALING;NO_AGENT_OR_A0')
    spec['mechanism_fixtures']['missingness'] = 'FIXED_SYNTHETIC_MCAR_IS_A_TEST_ASSUMPTION_NOT_A_MARKET_ASSUMPTION;POISON_MASKED_VALUES_AND_QUERY_LABELS_MUST_NOT_CHANGE_INPUT_OR_MEMBERSHIP'
    spec['context'].update(
        task_distance='SHARED_OBSERVED_STANDARDIZED_CENTROID_QUERY_MEAN_SQUARE_MIN_THREE_CORE_PLUS_0.25_MASK_MISMATCH_FRACTION_PLUS_0.25_KNOWN_REGIME_DIFF',
        observation_distance='SHARED_OBSERVED_STANDARDIZED_MEAN_SQUARE_PLUS_0.25_MASK_MISMATCH_FRACTION',
        centroid='PER_DIMENSION_MEAN_OF_OBSERVED_VALUES_ONLY',
        eligibility=spec['context']['eligibility']+';LABEL_ELIGIBLE_AND_CORE_OBSERVED_ONLY')
    spec['panel'] = {'years': [2019, 2020, 2021, 2022], 'symbols': parent['data']['symbols'],
        'strata': 'YEAR_SYMBOL_HALF_YEAR_AS_OF', 'per_stratum': 8,
        'pool': 'LABEL_ELIGIBLE_METADATA_ONLY_NO_NUMERIC_OR_OUTCOME_FILTER',
        'positions': 'floor((j+0.5)*n/8), j=0..7', 'sort': 'AS_OF_DATE_THEN_EPISODE_ID',
        'points': 256, 'id_sha256_sorted_LF_terminal_LF': PANEL_SHA,
        'shards': 'SORTED_IDS_ROUND_ROBIN_FOUR_SHARDS_64_EACH',
        'nominal_research_HTTP': 768, 'controls_per_scope': 3,
        'acceptance': '256_UNIQUE_DURABLE_ORIGINAL_SHARED_UPSTREAM_ZERO_UNRESOLVED_UNKNOWN',
        'account': 'FOUR_ACCOUNTS_ON_SPARSE_PANEL_SCHEDULE_CASH_BETWEEN_SETTLED_CYCLES_NO_ANNUALIZATION_OR_GRID_MULTIPLIER'}
    spec['metrics']['forecast_population'] = 'FULL_GRID_WITH_COMMON_FALLBACK_PLUS_CORE_COMMON_SUPPORT_SEPARATE'
    spec['metrics']['policy_population'] = 'PANEL256_ONLY_NO_SYNTHETIC_ACTIONS_OFF_PANEL'
    spec['metrics']['groups'] = [*spec['metrics']['groups'], 'missing_mask', 'observed_dimension_count']
    spec['calibration_policy'].update(
        fit='DENSE_INNER_OOF_DISTRIBUTION_MAP_FORWARD_CROSSFIT_UNCHANGED',
        policy_config_selection='PANEL_INNER_ACCOUNT_REGRET_VS_ORIGINAL_WITH_UNCHANGED_MDD_GUARDS_GRID_TIES',
        final_fit='INNER2020_OOF_ONLY_NO_2021_2022_OR_2023_SELECTION',
        artifact_key='FOLD_ID_PLUS_POINT_ID_NOT_POINT_ID_ALONE')
    spec['gates']['W11_18'] = 'NUMERIC_CORE_SUPPORT_AND_COLD_LABEL_PIT_MASK_LINEAGE_PASS_PLUS_PANEL256_RAW_ACCEPTED'
    spec['gates']['W11_21']['oof_D_population'] = 'PANEL_OUTER_2020_2021_2022'
    spec['confirmation']['agent_feature_claim'] = 'REPLACED_BY_MASKED_VS_COMPLETE_CASE_CLAIM_ONLY_IF_MATCHED_CONTRAST_PASSES'
    return spec


def validate(spec: dict[str, Any], parent: dict[str, Any]) -> dict[str, Any]:
    """Không nhận sửa thêm cutoff, ngưỡng, model hay family ngoài amendment."""
    if spec != expected_spec(parent):
        raise ValueError('Protocol v4.1 khác amendment numeric/mask/panel đã đăng ký')
    if any(spec['permissions'].values()) or spec['development']['total_action_rows'] != 996 or spec['development']['total_nominal_llm_slots'] != 324:
        raise ValueError('Spec không cấp quyền train/API và không được đổi số slot development')
    return spec


def source_binding(root: Path, commit: str) -> dict[str, str]:
    """Nguồn và spec phải đã commit trước seal; kiểm lại đúng object Git khi cold."""
    git(root, 'merge-base', '--is-ancestor', commit, 'HEAD')
    result = {}
    for name in (*SOURCES, PROTOCOL.as_posix()):
        raw = (root / name).read_bytes()
        if raw != git(root, 'show', commit + ':' + name):
            raise ValueError('Nguồn spec v4.1 chưa commit hoặc đã đổi: '+name)
        result[name] = checksum(raw)
    return result


def freeze(root: Path) -> dict[str, Any]:
    """Khóa một lần sau commit; chưa cấp release collection hoặc fit predictor."""
    if (root / LOCK).exists():
        return verify(root)
    verify_parent(root)
    spec = validate(read((root/PROTOCOL).read_bytes()), read((root/PARENT).read_bytes()))
    commit = git(root, 'rev-parse', 'HEAD').decode().strip()
    payload = {'status': 'SPEC_LOCK_PASS', 'source_commit': commit, 'sources': source_binding(root, commit),
        'protocol_sha256': checksum((root/PROTOCOL).read_bytes()), 'parent_byte_sha256': checksum((root/PARENT).read_bytes()),
        'permissions': spec['permissions']}
    immutable(root/LOCK, payload)
    return payload


def verify(root: Path) -> dict[str, Any]:
    """Chấp nhận đúng revision mới; parent v4 và bằng chứng cũ vẫn được kiểm riêng."""
    verify_parent(root)
    spec = validate(read((root/PROTOCOL).read_bytes()), read((root/PARENT).read_bytes()))
    receipt = read((root/LOCK).read_bytes())
    if ((root/LOCK).read_bytes() != git(root, 'show', 'HEAD:'+LOCK.as_posix())
            or receipt['status'] != 'SPEC_LOCK_PASS' or receipt['sources'] != source_binding(root, receipt['source_commit'])
            or receipt['protocol_sha256'] != checksum((root/PROTOCOL).read_bytes())
            or receipt['parent_byte_sha256'] != checksum((root/PARENT).read_bytes()) or receipt['permissions'] != spec['permissions']):
        raise ValueError('Lock v4.1 khác Git/source/scope')
    return spec
