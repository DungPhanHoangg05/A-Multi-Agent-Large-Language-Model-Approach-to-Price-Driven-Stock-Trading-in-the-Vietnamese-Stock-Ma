"""Cohort cải tiến dùng graph/journal hiện hữu, slot mới và lịch toàn cohort."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import math
from pathlib import Path
import time
from typing import Any
from uuid import UUID, uuid4

from agents import decision_agent
from core.backtest_engine import PRIOR_BRANCH_MODES
from core.candidate_cohort import _checked_response
from core.decision_prior import prepare_decision_prior
from core.historical_signals import digest, native_json
from core.improvement_prior import point_request
from core.improvement_protocol import MATRIX, SYMBOL_ORDER, calendar, branch_order, repeat_sample, validate_plan
from core.prior_config import copy_prior_json
from core.prior_context import REPORT_FIELDS
from core.prior_run_lock import PriorRunLock, safe_path, utc_now
from core.prior_stage_journal import StageJournal, encode_output
from core.research_cohort import read_envelope, save_envelope, _report_prior
from core.research_input_lock import _write_once
from core.research_invocation import ENABLED, invocation_scope
from utils import static_util

IDENTITY_VERSION = 'improvement_run_identity_v1'
CHECKPOINT_VERSION = 'improvement_decision_checkpoint_v1'


def _sha(path: Path) -> str:
    """Hash byte artifact, khác hash LF dùng cho source code."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decision_path(root: Path, point_id: str, name: str, repeat_id: int = 0) -> Path:
    """Slot khoa học gồm repeat ID, không dùng UUID HTTP làm lượt lặp."""
    return safe_path(root, f'decisions/{repeat_id}/{point_id}/{name}.json')


def _empty(signature: str, pid: str, name: str, repeat_id: int) -> dict[str, Any]:
    """Slot phải tồn tại trước request đầu tiên của run."""
    return {'checkpoint_version': CHECKPOINT_VERSION, 'run_signature': signature, 'point_id': pid,
        'branch_id': name, 'repeat_id': repeat_id, 'shared_sha256': None, 'evidence': None,
        'request': None, 'prompt': None, 'prompt_sha256': None, 'attempts': []}


def _attempts(attempts: Any) -> None:
    """Không replay complete; unknown cuối chỉ qua xác nhận UUID có audit."""
    if type(attempts) is not list:
        raise ValueError('Attempts cải tiến phải là list')
    ids = set()
    for i, a in enumerate(attempts):
        if set(a) != {'attempt_id', 'started_at', 'status', 'output', 'latency_seconds', 'authorization'}:
            raise ValueError('Schema attempt cải tiến không hợp lệ')
        UUID(a['attempt_id'])
        if a['attempt_id'] in ids or not a['started_at'].endswith('Z'):
            raise ValueError('UUID/timestamp attempt cải tiến trùng/sai')
        datetime.fromisoformat(a['started_at'])
        ids.add(a['attempt_id'])
        auth = a['authorization']
        if auth is not None:
            if set(auth) != {'at', 'reason'} or not auth['reason'].strip() or len(auth['reason']) > 1000 or not auth['at'].endswith('Z'):
                raise ValueError('Audit replay cải tiến không hợp lệ')
            datetime.fromisoformat(auth['at'])
        if a['status'] == 'complete':
            if (i != len(attempts)-1 or auth is not None or type(a['output']) is not dict
                    or type(a['latency_seconds']) is not float or not math.isfinite(a['latency_seconds']) or a['latency_seconds'] < 0):
                raise ValueError('Complete cải tiến không được replay hoặc thiếu output/timer')
        elif (a['status'] != 'unknown' or a['output'] is not None or a['latency_seconds'] is not None
              or i < len(attempts)-1 and auth is None):
            raise ValueError('Unknown cải tiến chưa đối soát hoặc chứa output giả')


def _journal(runner: Any, point: Any, root: Path, signature: str, pid: str, *, create: bool = False) -> StageJournal:
    """Journal upstream bind nguồn PIT và run mới, không nối journal W7."""
    proof = point.source_provenance
    return StageJournal(safe_path(root, f'responses/{pid}.json'),
        {'run_signature': signature, 'point_id': pid, 'source_sha256': digest(proof)}, create=create)


def shared_point(runner: Any, row: dict[str, str], root: Path, signature: str, *, verify_only: bool) -> tuple[Any, Any, Any]:
    """Upstream một lần; durable journal phục hồi từng node, verifier không gọi node mới."""
    point = runner.adapter.prepare(row['symbol'], row['as_of_date'])
    pid = row['point_id']
    journal = _journal(runner, point, root, signature, pid)
    path = safe_path(root, f'points/{pid}.json')
    doc = read_envelope(path)
    binding = {'point_version': 'improvement_shared_point_v1', 'run_signature': signature,
        'point_id': pid, 'context': {'symbol': row['symbol'], 'as_of_date': row['as_of_date']},
        'source_proof': point.source_provenance}
    if set(doc) != {*binding, 'full_bundle', 'shared_sha256', 'journal_sha256'} or any(doc[k] != v for k, v in binding.items()):
        raise ValueError('Shared point cải tiến khác source/plan')
    if doc['full_bundle'] is not None:
        if doc['shared_sha256'] != digest(doc['full_bundle']) or doc['journal_sha256'] != _sha(journal.path):
            raise ValueError('Shared/journal cải tiến khác hash đã seal')
        if list(journal.document['nodes']) != ['indicator', 'pattern', 'trend', 'full']:
            raise ValueError('Shared cải tiến thiếu bốn stage durable')
        for name, node in journal.document['nodes'].items():
            if node['attempts'][-1]['status'] != 'complete':
                raise ValueError('Shared cải tiến chứa unknown upstream')
            output = node['attempts'][-1]['output']
            reports = REPORT_FIELDS[3:] if name == 'full' else (name+'_report',)
            if any(output[key] != doc['full_bundle']['reports'][key] for key in reports):
                raise ValueError('Shared khác output upstream/Full durable')
        if journal.document['nodes']['full']['attempts'][-1]['output']['sentiment_data'] != doc['full_bundle']['sentiment_data']:
            raise ValueError('Shared sentiment khác journal')
        return point, point.restore_full_bundle(doc['full_bundle']), doc
    if doc['shared_sha256'] is not None or doc['journal_sha256'] is not None:
        raise ValueError('Shared planned có hash/output chưa seal')
    if verify_only:
        return point, None, doc
    journal.assert_resumable()
    initial = point.agent_state()
    initial['pattern_image'] = static_util.generate_kline_image(deepcopy(initial['kline_data']), write_artifacts=False).get('pattern_image')
    initial['trend_image'] = static_util.generate_trend_image(deepcopy(initial['kline_data']), write_artifacts=False).get('trend_image')
    if any(type(initial[k]) is not str or not initial[k] for k in ('pattern_image', 'trend_image')):
        raise ValueError('Upstream cải tiến thiếu ảnh PIT')
    upstream = runner.builder.compile_upstream(stage_checkpoint=journal.invoke).invoke(deepcopy(initial))
    expected = point.agent_state()
    for key in ('stock_name', 'as_of_date', 'time_frame', 'is_backtest', 'language', 'window_end_date',
                'alpha_norm_method', 'alpha_weights', 'kline_data'):
        if digest(upstream.get(key)) != digest(expected[key]):
            raise ValueError('Upstream cải tiến thay input PIT')
    if not upstream['point_in_time_df'].equals(expected['point_in_time_df']):
        raise ValueError('Upstream cải tiến thay snapshot giá')
    upstream['sentiment_store'] = expected['sentiment_store']
    full = runner.builder.compile_full_preparation(strict_research_mode=True, stage_checkpoint=journal.invoke).invoke(deepcopy(upstream))
    shared = point.bind_full(full)
    bundle = {**{k: shared[k] for k in ('current_signals', 'market_regime', 'prior_provenance')},
        'reports': {k: shared[k] for k in REPORT_FIELDS}, 'alpha_factors': native_json(full['sentiment_data']['alpha_results']),
        'sentiment_data': native_json(full['sentiment_data'])}
    doc.update(full_bundle=bundle, shared_sha256=digest(bundle), journal_sha256=_sha(journal.path))
    save_envelope(path, doc)
    return point, shared, doc


def _request_state(point: Any, shared: dict[str, Any], index: Any, name: str) -> tuple[Any, Any, Any, str]:
    """Original/duplicate nguyên request; Bayesian v1 giữ formatter/validator cũ."""
    state = deepcopy(shared)
    if name in ('original', 'original_duplicate', 'bayesian'):
        state['prior_config']['k'] = 3 if name == 'bayesian' else 0
        retrieved = point.retrieve(state)
        state.update(prior_tasks=retrieved['tasks'], prior_stats=retrieved['stats'], prior_metadata=retrieved['metadata'])
        state, prefix = prepare_decision_prior(state, source_validator=point.verify_source, build_prefix=True)
        return state, None, None, prefix
    evidence, request = point_request(point, state, index, name)
    return state, evidence, request, request['prefix']


def decision(runner: Any, point: Any, shared: dict[str, Any], index: Any, path: Path, signature: str,
             pid: str, name: str, repeat_id: int, *, verify_only: bool,
             authorize_replay: str | None = None, replay_reason: str | None = None) -> dict[str, Any]:
    """Lưu intent/raw trước evaluation; dựng lại prompt và response khi nạp slot."""
    saved = read_envelope(path)
    initial = _empty(signature, pid, name, repeat_id)
    if set(saved) != set(initial) or any(saved[k] != initial[k] for k in
        ('checkpoint_version', 'run_signature', 'point_id', 'branch_id', 'repeat_id')):
        raise ValueError('Slot Decision cải tiến khác identity/point/branch/repeat')
    _attempts(saved['attempts'])
    if shared is None:
        if saved != initial:
            raise ValueError('Decision cải tiến đã bắt đầu trước shared')
        return saved
    state, evidence, request, prefix = _request_state(point, shared, index, name)
    class Captured(Exception):
        """Dừng trước invocation để tái dựng prompt offline."""
    prompts = []
    def prepare(actual: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if digest(actual) != digest(state):
            raise ValueError('Decision cải tiến thay Full projection')
        point.verify_source(actual)
        runner.adapter.verify_sources()
        return deepcopy(actual), prefix
    def capture(actual: dict[str, Any], prompt: str) -> None:
        prompts.append(prompt)
        raise Captured()
    try:
        decision_agent.create_final_trade_decider(runner.builder.agent_llm, _prior_preparer=prepare,
            _prior_request=request, _before_invoke=capture)(deepcopy(state))
    except Captured:
        pass
    if len(prompts) != 1:
        raise ValueError('Không tái dựng được prompt cải tiến')
    binding = {**initial, 'shared_sha256': digest(shared), 'evidence': evidence, 'request': request,
               'prompt': prompts[0], 'prompt_sha256': hashlib.sha256(prompts[0].encode('utf-8')).hexdigest()}
    if saved == initial:
        saved = binding
    elif any(digest(saved[k]) != digest(v) for k, v in binding.items() if k != 'attempts'):
        raise ValueError('Decision cải tiến khác shared/evidence/request/prompt đã tái dựng')
    attempts = saved['attempts']
    last = attempts[-1] if attempts else None
    if authorize_replay is not None and last is not None and last['attempt_id'] == authorize_replay:
        if (last['status'] != 'unknown' or last['authorization'] is not None or not replay_reason
                or not replay_reason.strip() or len(replay_reason.strip()) > 1000):
            raise ValueError('Chỉ xác nhận unknown cuối chưa được duyệt bằng UUID/lý do')
        last['authorization'] = {'at': utc_now(), 'reason': replay_reason.strip()}
        save_envelope(path, saved)
    if last is None or last['status'] != 'complete':
        if verify_only:
            return saved
        if last is not None and last['authorization'] is None:
            raise ValueError(f"Decision {name} unknown {last['attempt_id']}; cần reconcile UUID")
        attempt = {'attempt_id': str(uuid4()), 'started_at': utc_now(), 'status': 'unknown',
                   'output': None, 'latency_seconds': None, 'authorization': None}
        attempts.append(attempt)
        save_envelope(path, saved)
        started = time.monotonic()
        from core.improvement_transport import SLOT
        token = SLOT.set({'run_signature': signature, 'point_id': pid, 'branch_id': name, 'repeat_id': repeat_id,
                          'checkpoint_attempt_id': attempt['attempt_id'], 'prompt_sha256': saved['prompt_sha256']})
        def before(actual: dict[str, Any], prompt: str) -> None:
            if prompt != saved['prompt']:
                raise ValueError('Prompt thay đổi trước invocation cải tiến')
        try:
            with invocation_scope('decision_'+name) as budget:
                if budget is not None:
                    budget.run_signature, budget.point_id, budget.branch_id = signature, pid, name
                    budget.checkpoint_attempt_id = attempt['attempt_id']
                output = decision_agent.create_final_trade_decider(runner.builder.agent_llm, _prior_preparer=prepare,
                    _prior_request=request, _before_invoke=before)(deepcopy(state))
        finally:
            SLOT.reset(token)
        encoded = encode_output(output)
        _checked_response(encoded, request, runner.config['language'])
        attempt.update(status='complete', output=encoded, latency_seconds=float(time.monotonic()-started))
        save_envelope(path, saved)
        last = attempt
    output = last['output']
    expected_keys = {'messages', 'final_trade_decision', 'decision_prompt',
        *[k for k in decision_agent.PRIOR_STATE_FIELDS if k in state], *(['prior_decision_trace'] if request is not None else [])}
    if (set(output) != expected_keys or output.get('decision_prompt') != saved['prompt'] or any(output.get(k) != state[k]
        for k in decision_agent.PRIOR_STATE_FIELDS if k in state)):
        raise ValueError('Output Decision cải tiến khác prompt/shared')
    _checked_response(output, request, runner.config['language'])
    return saved


def project(runner: Any, point: Any, shared_doc: dict[str, Any], saved: dict[str, Any], name: str) -> tuple[Any, Any, Any]:
    """Chỉ sau Decision mới chấm nhãn/P&L bằng hàm kinh tế duy nhất."""
    from core.prior_backtest import evaluate_point
    attempts = saved['attempts']
    if not attempts or attempts[-1]['status'] != 'complete':
        return {'status': 'unknown' if attempts else 'planned', 'decision': None}, None, _report_prior()
    output = attempts[-1]['output']
    normalized = _checked_response(output, saved['request'], runner.config['language'])
    branch = {'status': 'complete', 'decision': {'action': normalized['decision'], 'confidence': normalized['confidence'],
        'risk_reward_ratio': normalized['risk_reward_ratio'], 'normalized_response': output['final_trade_decision'],
        'latency_seconds': attempts[-1]['latency_seconds']}}
    frame, events = runner.adapter.execution_data(point.source_provenance['context']['symbol'])
    evaluated = evaluate_point(frame, events, point.source_provenance['context']['as_of_date'], {n: branch for n in PRIOR_BRANCH_MODES})
    if saved['request'] is not None:
        view = _report_prior(saved=saved)
    else:
        view = _report_prior({k: output[k] for k in ('prior_config', 'prior_tasks', 'prior_stats', 'prior_metadata', 'bayesian_prior_context')})
    return branch, evaluated, view


def _snapshot(runner: Any, plan: dict[str, Any], root: Path, index: Any, signature: str, *,
              orders: list[tuple[dict[str, Any], int, list[str]]], shared_root: Path | None = None,
              shared_signature: str | None = None) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Verifier toàn snapshot trước API tiếp theo; nguồn/shared/request/raw đều tái kiểm."""
    rows, hashes = [], {}
    ledger = None
    if runner.mode == 'research':
        import json
        ledger = json.loads(Path(read_envelope(root/'cohort.json')['ledger_path']).read_text(encoding='utf-8'))
    for row, repeat_id, names in orders:
        pid = row['point_id']
        source_root = shared_root or root
        point, shared, doc = shared_point(runner, row, source_root, shared_signature or signature, verify_only=True)
        features = point.price_features()
        record = {'point_id': pid, 'context': doc['context'], 'repeat_id': repeat_id, 'branches': {}, 'evaluation': None,
            'source_proof': doc['source_proof'],
            'report_context': {'regime': point.market_regime['regime_name'], 'feature_status': features['status'],
                               'feature_reasons': features['reasons'], 'prior': {}}}
        for name in names:
            path = decision_path(root, pid, name, repeat_id)
            saved = decision(runner, point, shared, index, path, signature, pid, name, repeat_id, verify_only=True)
            if shared_root is not None:
                primary = read_envelope(decision_path(shared_root, pid, 'original' if name == 'original_duplicate' else name))
                if any(saved[k] != primary[k] for k in ('prompt', 'prompt_sha256', 'evidence', 'request', 'shared_sha256')):
                    raise ValueError('Repeat khác request/shared cố định của primary')
            branch, evaluated, view = project(runner, point, doc, saved, name)
            if runner.mode == 'research' and branch['status'] == 'complete':
                from core.improvement_transport import expected_contract, verify_attempt_audit
                slot = {'run_signature': signature, 'point_id': pid, 'branch_id': name, 'repeat_id': repeat_id,
                    'checkpoint_attempt_id': saved['attempts'][-1]['attempt_id'], 'prompt_sha256': saved['prompt_sha256']}
                records = verify_attempt_audit(ledger, slot, expected=expected_contract(runner.builder.agent_llm, saved['prompt']),
                    raw_message=saved['attempts'][-1]['output']['messages'][0]['data'])
                for http in records:
                    hashes['http:'+http['id']] = digest(http)
            record['branches'][name] = branch
            record['report_context']['prior'][name] = view
            if evaluated is not None:
                if record['evaluation'] is None:
                    record['evaluation'] = {**evaluated, 'branches': {}}
                record['evaluation']['branches'][name] = evaluated['branches']['original']
            hashes[path.relative_to(root).as_posix()] = _sha(path)
        rows.append(record)
        for path in (safe_path(source_root, f'points/{pid}.json'), safe_path(source_root, f'responses/{pid}.json')):
            hashes[str(path.resolve())] = _sha(path)
    return rows, hashes


def run_primary(runner: Any, plan: dict[str, Any], root: Path, *, resume: bool = False,
                verify_only: bool = False, ledger_path: Path | None = None, gates: dict[str, Any] | None = None) -> dict[str, Any]:
    """Luồng mới tái dùng runner/builder; không gọi năm Decision thừa của luồng W7."""
    from core.improvement_reports import build_report
    index = validate_plan(plan, runner.adapter)
    root = root.resolve()
    if not runner.durable_stages or plan['split'] == 'fixture' and runner.mode != 'offline_fixture':
        raise ValueError('Cải tiến cần journal durable và fixture không được dùng API')
    if runner.mode == 'research':
        namespace = runner.adapter._files.root/'outputs/bayesian_benchmark/improvement_v1'
        expected_ledger = runner.adapter._files.root/'outputs/oos_pilot/api_usage.json'
        if (not root.is_relative_to(namespace.resolve()) or ledger_path is None or ledger_path.resolve() != expected_ledger.resolve()
                or runner.quota_policy != 'request_admission_v2' or gates is None or gates['status'] != 'PASS'):
            raise ValueError('Run thật cần namespace/ledger chung/policy và bốn gate mới PASS')
        from core.improvement_transport import validate_client
        for role, llm in (('agent', runner.builder.agent_llm), ('graph', runner.builder.graph_llm)):
            validate_client(llm, role, runner.config['models'], online=not verify_only)
    if root == runner.adapter._files.root.resolve() or any((runner.adapter._files.root/p).resolve().is_relative_to(root)
        for p in runner.adapter.source_hashes):
        raise ValueError('Output cải tiến chồng lên nguồn đã khóa')
    identity = {'identity_version': IDENTITY_VERSION, 'plan': plan, 'execution_mode': runner.mode,
        'ledger_path': str(ledger_path.resolve()) if ledger_path else None, 'gates': gates,
        'sources': runner.adapter.source_hashes, 'upstream_reuse': False}
    signature = digest(identity)
    manifest, ready = root/'cohort.json', root/'ready.json'
    orders = [(row, 0, branch_order(j)) for j, row in enumerate(calendar(plan))]
    token = ENABLED.set(True)
    try:
        with PriorRunLock(root, signature):
            exists = manifest.exists()
            if exists:
                if not (resume or verify_only) or read_envelope(manifest) != identity:
                    raise ValueError('Run cải tiến khác identity hoặc thiếu resume')
            else:
                if resume or verify_only or any(p.name not in ('run.lock', 'run.owner.json') for p in root.iterdir()):
                    raise ValueError('Run mới cần output trống; không migrate W7')
                _write_once(manifest, identity)
            if not ready.exists():
                if verify_only:
                    raise ValueError('Run cải tiến chưa initialized đủ slot')
                for row, r, names in orders:
                    point = runner.adapter.prepare(row['symbol'], row['as_of_date'])
                    _journal(runner, point, root, signature, row['point_id'], create=True)
                    _write_once(root/'points'/f"{row['point_id']}.json", {
                        'point_version': 'improvement_shared_point_v1', 'run_signature': signature, 'point_id': row['point_id'],
                        'context': {'symbol': row['symbol'], 'as_of_date': row['as_of_date']}, 'source_proof': point.source_provenance,
                        'full_bundle': None, 'shared_sha256': None, 'journal_sha256': None})
                    for name in names:
                        _write_once(decision_path(root, row['point_id'], name, r), _empty(signature, row['point_id'], name, r))
                _write_once(ready, {'run_signature': signature, 'slot_count': len(orders)*len(MATRIX)})
            if read_envelope(ready) != {'run_signature': signature, 'slot_count': len(orders)*len(MATRIX)}:
                raise ValueError('Ready marker cải tiến sai')
            rows, hashes = _snapshot(runner, plan, root, index, signature, orders=orders)
            pending = {p['point_id']: [n for n in p['branches'] if p['branches'][n]['status'] != 'complete'] for p in rows}
            if not verify_only and any(pending.values()):
                for row, r, names in orders:
                    if not pending[row['point_id']]:
                        continue
                    if runner.engine._stop_event.is_set():
                        raise InterruptedError('Dừng trước point cải tiến; giữ checkpoint')
                    if runner.before_point:
                        runner.before_point()
                    point, shared, doc = shared_point(runner, row, root, signature, verify_only=False)
                    for name in names:
                        if name not in pending[row['point_id']]:
                            continue
                        if runner.engine._stop_event.is_set():
                            raise InterruptedError('Dừng trước Decision cải tiến')
                        decision(runner, point, shared, index, decision_path(root, row['point_id'], name),
                                 signature, row['point_id'], name, 0, verify_only=False)
                rows, hashes = _snapshot(runner, plan, root, index, signature, orders=orders)
            hashes['cohort.json'], hashes['ready.json'] = _sha(manifest), _sha(ready)
            binding = {'run_signature': signature, 'execution_mode': runner.mode, 'plan_sha256': digest(plan),
                'protocol_sha256': plan['protocol_sha256'], 'code_sha256': plan['code_sha256'], 'runtime': plan['runtime'],
                'sources': runner.adapter.source_hashes, 'checkpoint_sha256': hashes}
            return build_report(plan, {s: [p for p in rows if p['context']['symbol'] == s] for s in SYMBOL_ORDER}, binding)
    finally:
        ENABLED.reset(token)


def prepare_repeat_plan(runner: Any, plan: dict[str, Any], primary_root: Path, destination: Path, *,
                        ledger_path: Path | None = None, gates: dict[str, Any] | None = None) -> dict[str, Any]:
    """Producer repeat chỉ nối primary COMPLETE đã verify, sample cố định trước API."""
    from core.improvement_reports import read_report
    from core.improvement_protocol import REPEAT_IDS
    expected = run_primary(runner, plan, primary_root, verify_only=True, ledger_path=ledger_path, gates=gates)
    read_report(primary_root/'report.json', expected)
    if expected['primary_status'] != 'COMPLETE':
        raise ValueError('Chỉ chuẩn bị repeat sau đủ primary')
    sample = repeat_sample(plan)
    if plan['split'] == 'development_2023':
        strata = {pid: ('S', 'E_ONLY', 'OFF')[j % 3] for j, pid in enumerate(REPEAT_IDS)}
    else:
        strata = {p['point_id']: 'S' if p['prior']['C2']['stats_ready'] else
                  'E_ONLY' if p['prior']['C2']['examples_ready'] else 'OFF'
                  for stock in expected['stocks'].values() for p in stock['points']}
    result = {'plan_version': 'improvement_repeat_plan_v1', 'primary_plan': plan,
        'primary_run': primary_root.resolve().relative_to(runner.adapter._files.root.resolve()).as_posix(),
        'primary_signature': expected['binding']['run_signature'], 'primary_report_sha256': digest(expected),
        'primary_report_file_sha256': _sha(primary_root/'report.json'),
        'sample': sample, 'strata': strata, 'repeat_ids': [1, 2, 3], 'in_primary': False,
        'matrix': [*MATRIX, 'original_duplicate']}
    _write_once(destination, result)
    return result


def validate_repeat_plan(runner: Any, plan: dict[str, Any], *, ledger_path: Path | None = None,
                         gates: dict[str, Any] | None = None) -> dict[str, Any]:
    """Loader repeat tái dựng primary và kiểm mẫu, strata, matrix, mọi binding."""
    from core.improvement_reports import read_report
    from core.improvement_protocol import REPEAT_IDS
    plan = copy_prior_json(plan)
    keys = {'plan_version', 'primary_plan', 'primary_run', 'primary_signature', 'primary_report_sha256',
            'primary_report_file_sha256', 'sample', 'strata', 'repeat_ids', 'in_primary', 'matrix'}
    if set(plan) != keys or plan['plan_version'] != 'improvement_repeat_plan_v1':
        raise ValueError('Schema repeat plan không hợp lệ')
    primary_root = safe_path(runner.adapter._files.root, plan['primary_run'])
    primary = run_primary(runner, plan['primary_plan'], primary_root, verify_only=True, ledger_path=ledger_path, gates=gates)
    read_report(primary_root/'report.json', primary)
    sample = repeat_sample(plan['primary_plan'])
    strata = {pid: ('S', 'E_ONLY', 'OFF')[j % 3] for j, pid in enumerate(REPEAT_IDS)} if plan['primary_plan']['split'] == 'development_2023' else {
        p['point_id']: 'S' if p['prior']['C2']['stats_ready'] else 'E_ONLY' if p['prior']['C2']['examples_ready'] else 'OFF'
        for stock in primary['stocks'].values() for p in stock['points']}
    if (primary['primary_status'] != 'COMPLETE' or plan['sample'] != sample or plan['strata'] != strata
            or plan['primary_signature'] != primary['binding']['run_signature']
            or plan['primary_report_sha256'] != digest(primary) or plan['primary_report_file_sha256'] != _sha(primary_root/'report.json')
            or plan['repeat_ids'] != [1, 2, 3] or plan['in_primary'] is not False or plan['matrix'] != [*MATRIX, 'original_duplicate']):
        raise ValueError('Repeat plan khác primary/sample/order/identity đã khóa')
    return primary


def run_repeats(runner: Any, plan: dict[str, Any], root: Path, *, resume: bool = False, verify_only: bool = False,
                ledger_path: Path | None = None, gates: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ba lượt mới, cùng upstream/request primary; không sửa hoặc nhập action primary."""
    from core.improvement_reports import build_repeat_report
    primary = validate_repeat_plan(runner, plan, ledger_path=ledger_path, gates=gates)
    root = root.resolve()
    primary_root = safe_path(runner.adapter._files.root, plan['primary_run'])
    if root.is_relative_to(primary_root) or primary_root.is_relative_to(root):
        raise ValueError('Repeat phải dùng namespace tách khỏi primary')
    if runner.mode == 'research' and not root.is_relative_to((runner.adapter._files.root/'outputs/bayesian_benchmark/improvement_v1').resolve()):
        raise ValueError('Repeat thật cần namespace cải tiến mới')
    index = validate_plan(plan['primary_plan'], runner.adapter)
    identity = {'identity_version': IDENTITY_VERSION, 'repeat_plan': plan, 'execution_mode': runner.mode,
        'ledger_path': str(ledger_path.resolve()) if ledger_path else None, 'gates': gates,
        'primary_binding': primary['binding']}
    signature = digest(identity)
    rows = [row for row in calendar(plan['primary_plan']) if row['point_id'] in plan['sample']]
    orders = [(row, r, branch_order(j, r)) for j, row in enumerate(rows) for r in (1, 2, 3)]
    token = ENABLED.set(True)
    try:
        with PriorRunLock(primary_root, plan['primary_signature']), PriorRunLock(root, signature):
            if (primary_root/'report.json').exists() and _sha(primary_root/'report.json') != plan['primary_report_file_sha256']:
                raise ValueError('Primary thay đổi sau kiểm repeat')
            manifest, ready = root/'cohort.json', root/'ready.json'
            if manifest.exists():
                if not (resume or verify_only) or read_envelope(manifest) != identity:
                    raise ValueError('Repeat khác identity hoặc thiếu resume')
            else:
                if resume or verify_only or any(p.name not in ('run.lock', 'run.owner.json') for p in root.iterdir()):
                    raise ValueError('Repeat mới cần output trống')
                _write_once(manifest, identity)
            if not ready.exists():
                if verify_only:
                    raise ValueError('Repeat chưa initialized đủ slot')
                for row, r, names in orders:
                    for name in names:
                        _write_once(decision_path(root, row['point_id'], name, r), _empty(signature, row['point_id'], name, r))
                _write_once(ready, {'run_signature': signature, 'slot_count': len(orders)*(len(MATRIX)+1)})
            if read_envelope(ready) != {'run_signature': signature, 'slot_count': len(orders)*(len(MATRIX)+1)}:
                raise ValueError('Ready marker repeat sai')
            blocks, hashes = _snapshot(runner, plan['primary_plan'], root, index, signature, orders=orders,
                shared_root=primary_root, shared_signature=plan['primary_signature'])
            pending = {(p['point_id'], p['repeat_id']): [n for n in p['branches'] if p['branches'][n]['status'] != 'complete'] for p in blocks}
            if not verify_only and any(pending.values()):
                for row, r, names in orders:
                    if not pending[(row['point_id'], r)]:
                        continue
                    point, shared, doc = shared_point(runner, row, primary_root, plan['primary_signature'], verify_only=True)
                    if runner.before_point:
                        runner.before_point()
                    for name in names:
                        if name not in pending[(row['point_id'], r)]:
                            continue
                        if runner.engine._stop_event.is_set():
                            raise InterruptedError('Dừng trước Decision repeat')
                        decision(runner, point, shared, index, decision_path(root, row['point_id'], name, r),
                            signature, row['point_id'], name, r, verify_only=False)
                blocks, hashes = _snapshot(runner, plan['primary_plan'], root, index, signature, orders=orders,
                    shared_root=primary_root, shared_signature=plan['primary_signature'])
            hashes['cohort.json'], hashes['ready.json'] = _sha(manifest), _sha(ready)
            return build_repeat_report(plan, blocks, {'run_signature': signature, 'execution_mode': runner.mode,
                'repeat_plan_sha256': digest(plan), 'primary_binding': primary['binding'],
                'checkpoint_sha256': hashes, 'code_sha256': plan['primary_plan']['code_sha256'],
                'runtime': plan['primary_plan']['runtime']})
    finally:
        ENABLED.reset(token)


def reconcile(runner: Any, plan: dict[str, Any], root: Path, *, attempt_id: str | None = None,
              reason: str | None = None, ledger_path: Path | None = None, gates: dict[str, Any] | None = None) -> dict[str, Any]:
    """Đối soát offline theo UUID duy nhất; không tự replay request chưa rõ kết quả."""
    if plan.get('plan_version') == 'improvement_repeat_plan_v1':
        run_repeats(runner, plan, root, verify_only=True, ledger_path=ledger_path, gates=gates)
        base, primary_root = plan['primary_plan'], safe_path(runner.adapter._files.root, plan['primary_run'])
    else:
        run_primary(runner, plan, root, verify_only=True, ledger_path=ledger_path, gates=gates)
        base, primary_root = plan, root
    signature = digest(read_envelope(root/'cohort.json'))
    with PriorRunLock(root, signature):
        rows, matches = [], []
        for path in (root/'decisions').rglob('*.json'):
            doc = read_envelope(path)
            for a in doc['attempts']:
                rows.append({'point_id': doc['point_id'], 'branch_id': doc['branch_id'], 'repeat_id': doc['repeat_id'],
                             'attempt_id': a['attempt_id'], 'status': a['status'], 'authorization': a['authorization']})
            if doc['attempts'] and doc['attempts'][-1]['attempt_id'] == attempt_id:
                matches.append(('decision', path, doc))
        if primary_root == root:
            for row in calendar(base):
                point = runner.adapter.prepare(row['symbol'], row['as_of_date'])
                journal = _journal(runner, point, root, signature, row['point_id'])
                rows += journal.reconcile()
                if any(n['attempts'][-1]['attempt_id'] == attempt_id for n in journal.document['nodes'].values()):
                    matches.append(('journal', journal, None))
        if attempt_id is not None:
            UUID(attempt_id)
            if len(matches) != 1 or type(reason) is not str or not reason.strip() or len(reason.strip()) > 1000:
                raise ValueError('Đối soát cần đúng một UUID và lý do hợp lệ')
            kind, target, doc = matches[0]
            if kind == 'journal':
                target.reconcile(attempt_id=attempt_id, reason=reason)
            else:
                a = doc['attempts'][-1]
                if a['status'] != 'unknown' or a['authorization'] is not None:
                    raise ValueError('Chỉ xác nhận unknown cuối chưa duyệt')
                a['authorization'] = {'at': utc_now(), 'reason': reason.strip()}
                save_envelope(target, doc)
        return {'run_signature': signature, 'attempts': rows, 'authorized_uuid': attempt_id}
