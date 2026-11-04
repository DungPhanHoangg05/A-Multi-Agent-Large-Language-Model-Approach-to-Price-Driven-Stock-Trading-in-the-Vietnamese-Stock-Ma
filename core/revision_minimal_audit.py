"""Audit T04 trên raw thật, giữ nguyên queue và bằng chứng lịch sử."""

from __future__ import annotations

from collections import Counter
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3

from core.revision72_run import checked
from core.revision_common_study import digest, read_json
from core.revision_minimal_bank import BANK, DEST, require, verify_response
from core.revision_r4_factorial import (actual_text, controlled_prompt, factor_rows,
                                       prompt_parts, validate_donor)


def audit_attempts(root: Path, manifest: dict, records: list[dict]) -> tuple[list[dict], dict]:
    """Phân biệt raw nguồn kế thừa, calls mới và successes thực dùng trong whitelist."""
    paths = {root / r['path'] for r in manifest['sources'] if r['path'].endswith('.request.json')}
    paths.update((root / DEST).glob('shards/org*/calls/*.request.json'))
    selected = {attempt: r['job_id'] for r in records for attempt in r['request_ids']}
    require(len(selected) == sum(len(r['request_ids']) for r in records), 'Raw bị dùng cho nhiều executions')
    rows, seen = [], set()
    for path in sorted(paths):
        request = checked(path); attempt = request['attempt_id']; context = request['context']
        require(attempt not in seen, 'Request ID trùng giữa các archive'); seen.add(attempt)
        require(path.name == f'{attempt}.request.json', 'Request ID khác tên file')
        response_path = path.with_name(f'{attempt}.response.json')
        error_path = path.with_name(f'{attempt}.error.json')
        require(response_path.exists() != error_path.exists(), 'Attempt chưa có đúng một terminal artifact')
        response = verify_response(response_path, request) if response_path.exists() else None
        error = read_json(error_path) if error_path.exists() else None
        if error:
            require(error['attempt_id'] == attempt and error['context'] == context, 'Error sai context/parent')
        output = (response['response'].get('llm_output') or {}) if response else {}
        usage = output.get('token_usage')
        category = None
        if error:
            message = error.get('error', '')
            category = 'rate_or_quota' if '429' in message else 'schema' if 'json_validate_failed' in message else 'other'
        metadata = request['model_metadata']
        rows.append({'attempt_id': attempt, 'path': path.relative_to(root).as_posix(),
                     'selected_job_id': selected.get(attempt), 'stage': context['stage'],
                     'origin': 'new' if path.is_relative_to(root / DEST) else 'frozen_source',
                     'variant': context.get('variant'), 'node': context.get('node'),
                     'provider_org': context.get('provider_org'), 'execution_epoch': context.get('execution_epoch'),
                     'started_at_utc': request['started_at_utc'],
                     'ended_at_utc': response['ended_at_utc'] if response else None,
                     'sdk_model': metadata.get('ls_model_name'), 'sdk_temperature': metadata.get('ls_temperature'),
                     'sdk_max_tokens': metadata.get('ls_max_tokens'),
                     'provider_reported_model': output.get('model_name'),
                     'system_fingerprint': output.get('system_fingerprint'),
                     'api_seed_observed': request['invocation_parameters'].get('seed'),
                     'actual_messages_hash': digest(request['messages']),
                     'outcome': 'success' if response else 'error', 'error_category': category,
                     'error_type': error.get('type') if error else None,
                     'prompt_tokens': usage.get('prompt_tokens') if usage else None,
                     'completion_tokens': usage.get('completion_tokens') if usage else None,
                     'latency_seconds': (datetime.fromisoformat(response['ended_at_utc']) -
                                         datetime.fromisoformat(request['started_at_utc'])).total_seconds() if response else None})
    require(set(selected) <= seen, 'Thiếu raw của research execution')
    require(all(r['outcome'] == 'success' for r in rows if r['selected_job_id']), 'Execution dùng raw lỗi')
    require(all(r['selected_job_id'] for r in rows if r['outcome'] == 'success' and r['stage'] == 'decision'),
            'Có successful Decision ngoài scope trong closure')
    costs = {}
    for group in ('new', 'frozen_source'):
        part = [r for r in rows if r['origin'] == group]
        costs[group] = {'attempts': len(part), 'successes': sum(r['outcome'] == 'success' for r in part),
                        'errors': sum(r['outcome'] == 'error' for r in part),
                        'stages': dict(Counter(r['stage'] for r in part)),
                        'errors_by_category': dict(Counter(r['error_category'] for r in part if r['outcome'] == 'error')),
                        'usage_missing_successes': sum(r['outcome'] == 'success' and r['prompt_tokens'] is None for r in part),
                        'observed_prompt_tokens': sum(r['prompt_tokens'] or 0 for r in part),
                        'observed_completion_tokens': sum(r['completion_tokens'] or 0 for r in part),
                        'latency_seconds_sum': sum(r['latency_seconds'] or 0 for r in part)}
    costs.update({'n_selected_research_successes': len(selected), 'monetary_cost': None,
                  'served_weight_revision': 'unknown',
                  'scope': 'Usage SDK quan sát được; không suy billing hoặc usage của calls lỗi. Vision là nguồn kế thừa, không phải calls mới.'})
    return rows, costs


def ledger_snapshot(root: Path, signature: str, attempts: list[dict]) -> dict:
    """Lưu reservations không chứa key, để audit release không cần SQLite vận hành."""
    path = root / DEST / 'quota.sqlite3'
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        require(db.execute('SELECT value FROM identity').fetchall() == [(signature,)], 'Ledger sai identity')
        rows = [dict(zip(('attempt_id', 'provider_org', 'stage', 'model', 'stamp'), r))
                for r in db.execute('SELECT id,org,stage,model,stamp FROM attempts ORDER BY id')]
    archived = {r['attempt_id']: r for r in attempts if r['origin'] == 'new'}
    require({r['attempt_id'] for r in rows} == set(archived), 'Reservations/raw mới không khớp')
    for row in rows:
        raw = archived[row['attempt_id']]
        require((row['provider_org'], row['stage'], row['model']) ==
                (raw['provider_org'], raw['stage'], raw['sdk_model']), 'Ledger routing/model khác raw')
    return {'run_signature': signature, 'reservations': rows,
            'scope': 'Snapshot read-only của bảng attempts; không thay hoặc reset SQLite gốc.'}


def audit_pairing(root: Path, manifest: dict, records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Kiểm prompt/parent thật cho main, upstream, factorial; order khác ghi công khai."""
    jobs = {j['id']: j for j in manifest['jobs']}
    groups: dict[tuple, list[dict]] = {}
    lineage = []
    for record in records:
        job = jobs[record['job_id']]; path = root / record['path']; actual = checked(path)
        request_path = path.parent.parent / f"calls/{record['request_ids'][-1]}.request.json"
        request = checked(request_path); text = actual_text(request); context = record['context']
        require(text == job['prompt'], 'Actual prompt khác whitelist')
        key = (record['phase'], context['unit_id'], context['realization'], context['repeat'])
        groups.setdefault(key, []).append({'record': record, 'job': job, 'parts': prompt_parts(text), 'request': request})
        lineage.append({**record, 'unit': job['unit'], 'checkpoint_hash': actual['sha256'],
                        'asset_hash': actual['parent']['asset_hash'], 'upstream_hash': actual['parent']['upstream_hash'],
                        'donor_hash': actual['parent'].get('donor_hash'),
                        'prompt_hash': digest(text), 'actual_messages_hash': digest(request['messages']),
                        'prompt_chars': len(text), 'factor_rows': factor_rows(text),
                        'actual_provider_org': request['context']['provider_org'],
                        'execution_epoch': request['context']['execution_epoch'],
                        'request_started_utc': request['started_at_utc'],
                        'request_path': request_path.relative_to(root).as_posix()})
    bank = read_json(root / BANK / 'manifest.json'); pairs = []
    for key, group in sorted(groups.items()):
        phase, uid, realization, repeat = key
        indexed = {r['record']['context']['variant']: r for r in group}
        variants = ('B', 'A', 'S', 'AS', 'P') if phase == 'factorial' else ('B', 'AS')
        require(set(indexed) == set(variants) and len(group) == len(variants), 'Thiếu/duplicate nhánh paired')
        require(len({r['job']['origin_parent']['upstream_hash'] for r in group}) == 1, 'Paired khác upstream parent')
        for field in ('trend', 'pattern', 'indicator', 'rules'):
            require(len({r['parts'][field] for r in group}) == 1, 'Paired khác shared report/rules')
        if phase == 'factorial':
            job = indexed['AS']['job']; unit = job['unit']; i = unit['decision']
            asset = checked(root / BANK / f"features/{unit['symbol']}_{i}.json")
            donor_index = unit['placebo_donor']
            donor = checked(root / BANK / f"features/{unit['symbol']}_{donor_index}.json")
            scope = next(s for s in bank['schedule'] if (s['symbol'], s['fold']) == (unit['symbol'], unit['fold']))
            validate_donor(scope, donor_index, i)
            for variant, row in indexed.items():
                expected = controlled_prompt(indexed['AS']['parts'], asset, donor, variant)
                require(actual_text(row['request']) == expected, 'Actual factorial scalar/donor/isolation khác nguồn')
            require(indexed['AS']['parts']['alpha'] != indexed['P']['parts']['alpha'], 'Placebo không perturb values')
        planned = [j['context']['variant'] for j in manifest['jobs'] if
                   (j['phase'], j['context']['unit_id'], j['context']['realization'], j['context']['repeat']) == key]
        observed = [r['record']['context']['variant'] for r in sorted(group, key=lambda r: r['request']['started_at_utc'])]
        pairs.append({'phase': phase, 'unit_id': uid, 'realization': realization, 'repeat': repeat,
                      'shared_upstream_reports_rules': True, 'factorial_content_verified': phase == 'factorial',
                      'planned_order': planned, 'observed_success_order': observed, 'order_matches': planned == observed,
                      'n_execution_epochs': len({r['request']['context']['execution_epoch'] for r in group}),
                      'n_provider_orgs': len({r['request']['context']['provider_org'] for r in group})})
    return lineage, pairs
