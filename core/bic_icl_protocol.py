"""Protocol/schema/plan riêng cho cohort Bayesian ICL; không thay artifact W9."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

import jsonschema
import pandas as pd

from core.bic_icl_decisions import DEVELOPMENT, DEPENDENCIES
from core.bic_icl_memory import FrozenSources, METHOD_SHA, PREFIX, oos_adapter, verify_method
from core.bic_icl_prompt import build_context_evidence, capture_decision_prompt, render_profiles, verify_context_evidence
from core.bic_icl_tasks import TaskSelector
from core.historical_signals import digest
from core.improvement_prior import build_evidence, build_request
from core.prior_config import copy_prior_json
from core.prior_context import REPORT_FIELDS
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once, runtime_identity
from scripts.prepare_bic_icl_context import FrozenPreparation, check_budget_fixture, code_identity as context_code_identity

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = ROOT/'outputs/bayesian_benchmark/bic_icl_v2'
SCHEMA = 'docs/plan/week10/bic_icl_schema_v1.json'
ECONOMIC_FIXTURE = 'docs/plan/week10/economic_fixture_v1.json'
VERSION = 'bic_icl_cohort_plan_v1'
SYMBOLS = ('FPT', 'MWG', 'VCB', 'VNM')
POLICIES = ('VERIFIED_CACHE', 'FRESH_SHARED')
_AUTHORIZED = object()


class ExecutionAuthorization:
    """Receipt đã được consumer kiểm; không chấp nhận cờ bool thay technical gates."""

    def __init__(self, payload: dict[str, Any], *, verified: object,
                 path: Path | None = None, gates_path: Path | None = None) -> None:
        if verified is not _AUTHORIZED:
            raise ValueError('Authorization cần consumer release đã kiểm')
        self._payload, self.path, self.gates_path = deepcopy(payload), path, gates_path

    @property
    def payload(self) -> dict[str, Any]:
        """Caller chỉ nhận bản sao, không sửa release sau consumer."""
        return deepcopy(self._payload)

    def verify(self, plan: dict[str, Any]) -> None:
        """Gate/release còn nguyên trước API tiếp theo, không dùng cờ PASS cũ."""
        from core.candidate_selection import read_technical_gates
        gates = read_technical_gates(self.gates_path, plan)
        if (self.path is None or read_envelope(self.path) != self._payload or gates['status'] != 'PASS'
                or gates['sha256'] != self._payload['technical_gates_sha256']
                or self._payload['plan_sha256'] != digest(plan)):
            raise ValueError('Release/gate thay đổi sau khi cấp authorization')


def read_authorization(path: Path | None, gates_path: Path | None, plan: dict[str, Any]) -> ExecutionAuthorization:
    """Chặn trước credential; consumer release development, chưa có producer phát hành."""
    from core.candidate_selection import read_technical_gates
    if path is None or gates_path is None or path.name.startswith('.env'):
        raise ValueError('Chưa có release development và receipt bốn gate đúng code/runtime')
    gates = read_technical_gates(gates_path, plan)
    payload = read_envelope(path)
    keys = {'release_version', 'plan_sha256', 'technical_gates_sha256', 'upstream_policy',
            'code_sha256', 'runtime', 'decision_context_lock_sha256', 'confirmation_allowed'}
    context_hash = payload.get('decision_context_lock_sha256')
    if (set(payload) != keys or gates['status'] != 'PASS'
            or payload['release_version'] != 'bic_icl_development_release_v1'
            or payload['plan_sha256'] != digest(plan) or payload['technical_gates_sha256'] != gates['sha256']
            or payload['upstream_policy'] != plan['upstream_policy'] or payload['code_sha256'] != plan['code_sha256']
            or payload['runtime'] != plan['runtime'] or payload['confirmation_allowed'] is not False
            or context_hash is not None and (type(context_hash) is not str or len(context_hash) != 64
                or any(c not in '0123456789abcdef' for c in context_hash))):
        raise ValueError('Release development khác plan/nguồn/context/code/runtime/gates')
    return ExecutionAuthorization(payload, verified=_AUTHORIZED, path=path, gates_path=gates_path)


def validate_schema(value: Any, kind: str) -> None:
    """Schema JSON gốc cộng semantic verifier, không chỉ nhận checksum tự khai."""
    value = copy_prior_json(value)
    schema = read_envelope_json(ROOT/SCHEMA)
    try:
        jsonschema.Draft202012Validator({'$ref': '#/$defs/'+kind, '$defs': schema['$defs']}).validate(value)
    except (jsonschema.ValidationError, jsonschema.SchemaError) as exc:
        raise ValueError('Artifact Bayesian ICL sai schema '+kind) from exc


def read_envelope_json(path: Path) -> dict[str, Any]:
    """Đọc JSON fixture/schema thuần, không hiểu nhầm là envelope runtime."""
    import json
    return json.loads(path.read_text('utf8'))


def code_identity() -> dict[str, str]:
    """Bind dependency thực thi rõ tên; thêm analyzer độc lập không làm đổi plan cũ."""
    names = {*DEPENDENCIES, 'core/bic_icl_protocol.py', 'core/bic_icl_reports.py',
             'core/bic_icl_runtime.py', 'scripts/run_bic_icl.py', SCHEMA, ECONOMIC_FIXTURE,
             'docs/plan/week10/context_budget_fixture_v1.json',
             'docs/plan/week10/method_protocol_v1.md', '.python-version', 'requirements.txt'}
    return {**context_code_identity(),
            **{n: hashlib.sha256((ROOT/n).read_text('utf8').encode()).hexdigest() for n in sorted(names)}}


def protocol() -> dict[str, Any]:
    """Ánh xạ v1 đã khóa sang đối tượng canonical độc lập README."""
    return {'version': 'bic_icl_protocol_v1', 'method_sha256': METHOD_SHA,
        'decision_contract': 'decision_legacy_v1', 'risk_policy': 'OFF',
        'development_matrix': [*DEVELOPMENT, 'Numeric_only'], 'nomination_order': ['R_pool', 'R_task'],
        'confirmation_matrix': ['original', 'A_reference_shared_off', 'selected_full',
            'selected_stats_only', 'selected_examples_only', 'Numeric_only'],
        'lambda_candidates': [2, 4, 8], 'selected_lambda': 8,
        'task': {'anchor': '2018-01-02', 'sessions': 20, 'k_tasks': 3, 'examples_per_task': 2,
                 'max_age_days': 730, 'min_similarity': .625, 'min_gap_sessions': 5, 'seed': 42,
                 'signal_weight': .5, 'recency_half_life_days': 365},
        'prior_chars_max': 600, 'prompt_chars_exclusive': 6500, 'original_first': True,
        'rotation': 'left_j_mod_M', 'repeat_rotation': 'left_(3j+r-1)_mod_M_including_duplicate',
        'repeat_ids': [1, 2, 3], 'repeat_in_primary': False, 'duplicate_alias': False,
        'numeric': 'LONG_IFF_STATS_READY_AND_P_STRICTLY_GT_0.5_ELSE_SHORT_CASH',
        'economic': {'entry': 'Open(t+1)', 'exit': 'Close(t+3)', 'short': 'CASH',
            'fee_each_side': .0025, 'slippage_each_side': .001, 'capital_vnd_per_symbol': 50000000.,
            'price_multiplier': 1000., 'fractional_shares': True},
        'selection': {'prior_visible_total': 6, 'prior_visible_per_symbol': 1,
            'task_two_groups_total': 6, 'task_two_groups_per_symbol': 1, 'positive_symbols': 3,
            'mean_delta_mdd_max_pp': 2., 'max_delta_mdd_max_pp': 5., 'delta_vs_a_min_pp': 0.,
            'tie_tolerance_pp': 1e-9, 'tie': ['LOWER_MEAN_DELTA_MDD', 'R_pool']},
        'bootstrap': {'draws': 10000, 'seed': 20261021, 'rng': 'PCG64', 'block': 4,
            'sensitivity_blocks': [2, 8], 'minimum_valid': 9500, 'primary_ci': .95,
            'secondary_ci': .9875, 'quantile': 'linear', 'unit': 'CUTOFF_DATE_CLUSTER_ACCOUNT_REBUILD'}}


def schedule(cutoffs: dict[str, list[str]]) -> list[dict[str, str]]:
    """Lịch ngày/mã cố định, không sort bằng outcome hoặc readiness."""
    return sorted([{'point_id': f'{s}-{d}', 'symbol': s, 'as_of_date': d}
        for s in SYMBOLS for d in cutoffs[s]], key=lambda r: (r['as_of_date'], SYMBOLS.index(r['symbol'])))


def repeat_sample(packets: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Mỗi mã earliest both/one/off; thiếu stratum bù ngày sớm nhất chưa chọn."""
    result = []
    for symbol in SYMBOLS:
        rows = sorted((p for p in packets if p['point_id'].startswith(symbol+'-')), key=lambda p: p['point_id'])
        used = set()
        for target in ('BOTH', 'ONE', 'OFF'):
            def stratum(row: dict[str, Any]) -> str:
                gate = row['evidence']['gate']['R_pool']
                n = int(gate['stats_ready'])+int(gate['examples_ready'])
                return ('OFF', 'ONE', 'BOTH')[n]
            matches = [p for p in rows if p['point_id'] not in used and stratum(p) == target]
            fallback = not matches
            matches = matches or [p for p in rows if p['point_id'] not in used]
            if not matches:
                raise ValueError('Không đủ ba điểm khác nhau mỗi mã cho repeat')
            chosen = matches[0]; used.add(chosen['point_id'])
            result.append({'point_id': chosen['point_id'], 'requested_stratum': target,
                'actual_stratum': stratum(chosen), 'reason': 'EARLIEST_UNUSED_FALLBACK' if fallback else 'EARLIEST_MATCH'})
    return sorted(result, key=lambda r: (r['point_id'][4:], SYMBOLS.index(r['point_id'][:3])))


class CohortSources:
    """Kiểm nguồn W10-04 độc lập và khả năng reuse toàn cohort trước Decision."""

    def __init__(self) -> None:
        self.frozen, self.sources = FrozenPreparation(), FrozenSources()
        self.parent = self.sources.envelope(f'{PREFIX}/development/plan.json')
        self.adapter = oos_adapter(self.parent)
        self.selector = TaskSelector(self.frozen.index, pd.DatetimeIndex(self.adapter._vnindex.Datetime))

    def verify(self) -> None:
        """Nguồn thay byte phải dừng, kể cả giữa hai request."""
        self.frozen.verify(); self.sources.verify(); self.adapter.verify_sources()

    def cached(self, row: dict[str, str]) -> tuple[Any, dict[str, Any], dict[str, Any]]:
        """Full/journal lịch sử đã được adapter memory kiểm; không lấy action cũ."""
        point = self.adapter.prepare(row['symbol'], row['as_of_date'])
        doc = self.sources.envelope(f"{PREFIX}/development/run/points/{row['point_id']}.json")
        bundle = doc['full_bundle']
        return point, point.restore_full_bundle(bundle), deepcopy(bundle)

    def plan(self, upstream_policy: str = 'VERIFIED_CACHE') -> dict[str, Any]:
        """Khóa phương pháp/lịch/input/runtime; chưa khóa request fresh hoặc cấp release."""
        verify_method()
        if upstream_policy not in POLICIES:
            raise ValueError('Chính sách upstream chưa đăng ký')
        rows = schedule(self.parent['symbol_cutoffs'])
        if len(rows) != 60 or {s: len(self.parent['symbol_cutoffs'][s]) for s in SYMBOLS} != {'FPT': 12, 'MWG': 16, 'VCB': 16, 'VNM': 16}:
            raise ValueError('Lịch development khác 60 point đã khóa')
        self.verify()
        return copy_prior_json({'plan_version': VERSION, 'split': 'development_2023',
            'method_sha256': METHOD_SHA, 'protocol': protocol(), 'inputs': self.parent['inputs'],
            'schedule': rows, 'upstream_policy': upstream_policy, 'language': 'vi',
            'code_sha256': code_identity(), 'runtime': runtime_identity(),
            'source_hashes': {**self.frozen.hashes},
            'confirmation_allowed': False})

    def validate(self, plan: dict[str, Any]) -> None:
        """Dựng lại plan từ nguồn, không nhận đổi schema/lịch/matrix rồi tự băm lại."""
        validate_schema(plan, 'plan')
        if plan != self.plan(plan['upstream_policy']):
            raise ValueError('Plan khác protocol, lịch, code/runtime hoặc nguồn đã kiểm')

    def packet(self, row: dict[str, str], point: Any, shared: dict[str, Any],
               bundle: dict[str, Any]) -> dict[str, Any]:
        """A/R/Numeric dùng đúng retriever/index revision; không đọc outcome query."""
        point.verify_source(shared)
        options = {'selector': self.selector, 'query_features': point.price_features(),
            'symbol': row['symbol'], 'as_of_date': row['as_of_date'],
            'current_regime': shared['market_regime']['regime_name'], 'current_signals': shared['current_signals']}
        evidence = build_context_evidence(self.frozen.retriever, strength=8, **options)
        rendered = render_profiles(evidence, shared['language'], verifier=lambda e:
            verify_context_evidence(e, self.frozen.retriever, strength=8, **options))
        if rendered['R_pool']['status'] != 'AVAILABLE':
            raise ValueError('R_pool không đạt kỹ thuật; dừng revision trước Decision')
        ae = build_evidence(self.frozen.retriever, 'A_tp_pool', requested_k=3,
            enable_bayesian_prior=True, **options)
        ar = build_request(ae, 'A_tp_pool', self.frozen.retriever,
            selector=self.selector, query_features=options['query_features'])
        def capture(prefix: str) -> str:
            return capture_decision_prompt(shared, prefix, verifier=point.verify_source)
        requests = {'original': {'branch_id': 'original', 'prompt': capture(''), 'prefix': '', 'base_evidence_sha256': None},
            'A_reference_shared_off': {'branch_id': 'A_reference_shared_off', 'prompt': capture(ar['prefix']),
                'prefix': ar['prefix'], 'base_evidence_sha256': ae['base_evidence_sha256']}}
        for method, part in rendered.items():
            for mode, request in part['profiles'].items():
                name = method+{'full_prior': '_full', 'stats_only': '_stats_only', 'examples_only': '_examples_only'}[mode]
                requests[name] = {'branch_id': name, 'prompt': capture(request['prefix']),
                    'prefix': request['prefix'], 'base_evidence_sha256': evidence['base_evidence_sha256']}
        result = {'packet_version': 'bic_icl_point_packet_v1', 'point_id': row['point_id'],
            'bundle': deepcopy(bundle), 'source_proof': point.source_provenance,
            'evidence': evidence, 'a_evidence': ae, 'a_request': ar, 'requests': requests,
            'task_technical_available': rendered['R_task']['status'] == 'AVAILABLE'}
        validate_schema(result, 'packet')
        return copy_prior_json(result)


def namespace_path(path: Path, kind: str) -> Path:
    """Chỉ ghi con trực tiếp development_*; tránh chồng input/memory/train/context cũ."""
    resolved = path.resolve()
    if (resolved.parent != NAMESPACE.resolve() or not resolved.name.startswith('development_')
            or kind == 'plan' and resolved.suffix != '.json' or kind == 'run' and resolved.suffix):
        raise ValueError('Cần namespace development_* riêng, ngay dưới bic_icl_v2')
    return resolved


def prepare_plan(destination: Path, sources: CohortSources, *, upstream_policy: str = 'VERIFIED_CACHE') -> dict[str, Any]:
    """Producer plan offline ghi một lần, không tạo run hoặc đọc credential."""
    destination = namespace_path(destination, 'plan')
    plan = sources.plan(upstream_policy)
    validate_schema(plan, 'plan')
    _write_once(destination, plan)
    return plan


def dry_run(plan: dict[str, Any], sources: CohortSources) -> dict[str, Any]:
    """Dựng context toàn cohort cache hoặc kiểm nguồn fresh; không gọi LLM."""
    sources.validate(plan)
    fixture = check_budget_fixture()
    packets = [sources.packet(row, *sources.cached(row)) for row in plan['schedule']] if plan['upstream_policy'] == 'VERIFIED_CACHE' else []
    sources.validate(plan)
    from core.bic_icl_runtime import context_lock
    return {'status': 'PASS', 'upstream_policy': plan['upstream_policy'], 'decision_calls': 0,
        'confirmation_allowed': False, 'fixture': fixture,
        'lock': context_lock(plan, packets) if packets else None,
        'fresh_requests_pending': not bool(packets)}
