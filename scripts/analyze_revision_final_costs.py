"""T27: đối soát chi phí quan sát, retries, đồ thị dùng chung và chart cuối offline."""

from __future__ import annotations

import argparse
import base64
from collections import defaultdict
import contextlib
import io
from pathlib import Path
import re
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from langchain_core.messages import messages_to_dict
from PIL import Image

from core.revision_baselines import load_prices
from core.revision_common_study import digest as identity_hash, pack_state, point_state, restore_state
from core.revision_minimal_analysis import offline_guard as frozen_guard
from core.revision_minimal_audit import audit_attempts
from core.revision_minimal_bank import collect, verify_manifest
from core.revision72_provider import scientific_context
from core.revision72_run import checked
from core.revision_reproducibility import check_self_digest, digest, encoded, file_hash, offline_guard, read, require
from scripts.audit_chart_convention import fixture_frame, image_parts, render, text_parts
from scripts.audit_revision_lineage import verify
from scripts.export_revision_final_baselines import csv_bytes

OUTPUT = Path('outputs/revision/final_cost_integrity_v1')
FINAL = Path('outputs/revision/revision_minimal_final_v1')
QUEUE = Path('outputs/revision/revision_minimal_v1')
BANK = Path('outputs/revision/r1_72h_bank_v2')
CHART = Path('outputs/revision/chart_r1_run_v1')


def attempt_key(request: dict) -> str:
    """Routing/epoch khác vẫn cùng việc; prompt/schema/model khác là việc khác."""
    return identity_hash([scientific_context(request['context']), request['messages'],
                          request['model_metadata'], request['invocation_parameters']])


def retry_wait(message: str) -> float | None:
    """Chỉ đọc khoảng chờ provider nêu; không suy sleep thực từ timestamp."""
    match = re.search(r'(?:try again in|retry after)\s+((?:\d+(?:\.\d+)?[hms]\s*)+)', message, re.I)
    if match:
        return float(sum(float(n) * {'h': 3600, 'm': 60, 's': 1}[u.lower()]
                         for n, u in re.findall(r'(\d+(?:\.\d+)?)([hms])', match[1], re.I)))
    match = re.search(r'retry after\s+(\d+(?:\.\d+)?)\s+seconds', message, re.I)
    return float(match[1]) if match else None


def summarize(rows: list[dict]) -> dict:
    """Usage tổng chỉ trên trường quan sát; thiếu giữ mẫu số và null riêng."""
    result = {'attempts': len(rows), 'successes': sum(r['outcome'] == 'success' for r in rows),
              'errors': sum(r['outcome'] == 'error' for r in rows), 'monetary_cost': None}
    for field in ('prompt_tokens', 'completion_tokens', 'latency_seconds'):
        values = [r[field] for r in rows if r[field] is not None]
        result[field + '_n_observed'] = len(values)
        result[field + '_n_missing'] = len(rows) - len(values)
        result[field + '_observed_sum'] = sum(values) if values else None
        if field == 'latency_seconds':
            result['latency_seconds_p50'] = float(np.quantile(values, .5)) if values else None
            result['latency_seconds_p95'] = float(np.quantile(values, .95)) if values else None
    return result


def retries(rows: list[dict], requests: dict[str, dict]) -> list[dict]:
    """Chặn nhóm mất success/trùng success; thứ tự theo raw, không bỏ errors."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[attempt_key(requests[row['attempt_id']])].append(row)
    output = []
    for key, part in sorted(groups.items()):
        ordered = sorted(part, key=lambda r: r['started_at_utc'])
        successes = [r for r in part if r['outcome'] == 'success']
        require(len(successes) == 1, 'Nhóm retry thiếu hoặc trùng success')
        require(ordered[-1]['outcome'] == 'success', 'Attempt sau success chưa được giải thích')
        for index, row in enumerate(ordered):
            row.update({'retry_group': key, 'attempt_ordinal': index + 1,
                        'resolved_job_id': successes[0]['selected_job_id']})
        output.append({'retry_group': key, 'node': part[0]['node'], 'attempts': len(part),
                       'failed_attempts_before_success': len(part) - 1,
                       'success_attempt_id': successes[0]['attempt_id'],
                       'resolved_job_id': successes[0]['selected_job_id'],
                       'first_started_at_utc': ordered[0]['started_at_utc'],
                       'last_started_at_utc': ordered[-1]['started_at_utc'],
                       'cross_epoch': len({r['execution_epoch'] for r in part}) > 1,
                       'actual_sleep_seconds': None})
    return output


def capture_text(kind: str, language: str) -> list[str]:
    """Thu template thật bằng model giả; không có client hoặc SDK call."""
    from agents.pattern_agent import create_pattern_agent
    from agents.trend_agent import create_trend_agent
    calls = []

    class Capture:
        """Giữ đúng messages và trả đủ các trường parser, không fallback."""
        def invoke(self, messages: list) -> SimpleNamespace:
            calls.append(messages)
            reply = ('**Pattern:** Up\n**Confidence:** High\n**Directional bias:** Up\n'
                     '**Evidence:** Higher highs\n**Key candles:** Last candle\n**Trading implication:** Buy') if kind == 'pattern' else (
                         '**Trend direction:** Up\n**Support level:** 95\n**Resistance level:** 110\n'
                         '**Trendline slope:** Rising\n**Price vs support:** Bouncing\n**Detailed analysis:** Near support\n'
                         '**Trend forecast:** Up\n**Confidence:** Medium')
            return SimpleNamespace(content=reply)

    factory = create_pattern_agent if kind == 'pattern' else create_trend_agent
    state = {'language': language, 'time_frame': '1 ngày', 'kline_data': fixture_frame().to_dict('list'),
             kind + '_image': 'ZmFrZQ==', 'messages': []}
    with contextlib.redirect_stdout(io.StringIO()):
        factory(None, Capture(), None)(state)
    require(len(calls) == 1, 'Thu template bị retry/fallback')
    return text_parts(messages_to_dict(calls[0]))


def compare_png(actual: bytes, expected: bytes) -> None:
    """Chặn cả khác byte metadata lẫn khác pixel; không thay ảnh raw bằng ảnh mới."""
    require(actual == expected, 'PNG khác byte renderer cuối')
    require(np.array_equal(np.asarray(Image.open(io.BytesIO(actual))),
                           np.asarray(Image.open(io.BytesIO(expected)))), 'PNG khác pixel')


def validate_upstream_jobs(jobs: list[dict], node_hashes: list[str], run_signature: str, shared_hash: str) -> None:
    """R1 hash full state, R4 hash run+nodes; kiểm từng hợp đồng trước khi gộp calls."""
    for job in jobs:
        parent = job['origin_parent']
        if job['phase'] == 'factorial':
            expected = identity_hash({'run_signature': run_signature, 'node_hashes': node_hashes})
        else:
            require(parent['node_hashes'] == node_hashes and parent['run_signature'] == run_signature, 'Node hashes khác R1')
            expected = shared_hash
        require(parent['upstream_hash'] == expected, 'Upstream khác hợp đồng parent của phase')


def check(root: Path, output: Path) -> int:
    """Chỉ kiểm hash receipt/code/artifacts; không render lại hoặc đọc SQLite."""
    folder = root / output
    manifest = read(folder / 'manifest.json')
    require(check_self_digest(manifest) == 'pretty_sorted_utf8_lf', 'T27 self-digest sai')
    count = 0
    for name, base in (('sources', root), ('outputs', folder)):
        for row in manifest[name]:
            require(file_hash(base / row['path']) == row['sha256'], 'T27 hash khác: ' + row['path'])
            count += 1
    require({p.name for p in folder.iterdir()} == {'manifest.json', *[r['path'] for r in manifest['outputs']]}, 'T27 file thừa/thiếu')
    return count


def build(root: Path, output: Path) -> dict:
    """Đọc closure T04, kiểm cache/đồ thị/ảnh cuối rồi xuất release riêng bất biến."""
    folder = (root / output).resolve()
    require(folder.parent == (root / 'outputs/revision').resolve() and not folder.exists(), 'Cần output mới, không paper/overwrite')
    with offline_guard(), frozen_guard():
        parents = {name: verify(root / 'outputs/revision' / name) for name in
                   ('revision_minimal_final_v1', 'final_repeats_v1', 'clean_replay_v1')}
        manifest = verify_manifest(root, root / QUEUE)
        records = collect(root, root / QUEUE, manifest)
        require(records == read(root / FINAL / 'records.json'), 'Final records khác checkpoint thật')
        rows, costs = audit_attempts(root, manifest, records)
        require(rows == read(root / FINAL / 'attempts.json') and costs == read(root / FINAL / 'costs.json'), 'Closure/costs khác T04')
        names = {r['path'] for r in read(root / FINAL / 'manifest.json')['sources']}
        names.update((FINAL / n).as_posix() for n in ('manifest.json', 'records.json', 'attempts.json', 'costs.json', 'completion.json', 'ledger_snapshot.json', 'pairing.json'))
        names.update({'scripts/analyze_revision_final_costs.py', 'tests/test_revision_final_costs.py',
                      'scripts/audit_chart_convention.py', 'scripts/export_revision_final_baselines.py',
                      'scripts/audit_revision_lineage.py', 'core/revision_reproducibility.py',
                      'core/revision72_provider.py', (CHART / 'chart_rerun_preparation.json').as_posix()})
        names.update('outputs/revision/' + n + '/manifest.json' for n in parents)
        requests = {r['attempt_id']: checked(root / r['path']) for r in rows}
        preparation = checked(root / CHART / 'chart_rerun_preparation.json')
        copies = {c['path']: c for c in preparation['copies']}
        replay = []
        for row in rows:
            request = requests[row['attempt_id']]
            row['cost_scope'] = ('pattern_replay_original_request' if row['node'] == 'Pattern Agent' else
                                 'minimal_continuation' if row['origin'] == 'new' else 'corrected_chart_source')
            row['provider_requested_wait_seconds'] = None
            row['error_message_sha256'] = None
            if row['outcome'] == 'error':
                error = read((root / row['path']).with_name(row['attempt_id'] + '.error.json'))
                row['provider_requested_wait_seconds'] = retry_wait(error.get('error', ''))
                row['error_message_sha256'] = digest(error.get('error', '').encode())
            if row['node'] == 'Pattern Agent':
                for suffix in ('request', 'response'):
                    path = (root / row['path']).with_name(row['attempt_id'] + '.' + suffix + '.json')
                    copy = copies[path.relative_to(root / CHART).as_posix()]
                    require(file_hash(path) == copy['sha256'] == file_hash(root / copy['origin']), 'Pattern replay đổi byte')
                    names.add(copy['origin'])
                    replay.append({'attempt_id': row['attempt_id'], 'kind': suffix, 'path': path.relative_to(root).as_posix(),
                                   'original_path': copy['origin'], 'sha256': copy['sha256']})
        retry_rows = retries(rows, requests)
        reservations = read(root / FINAL / 'ledger_snapshot.json')['reservations']
        new = {r['attempt_id']: r for r in rows if r['origin'] == 'new'}
        require({r['attempt_id'] for r in reservations} == set(new), 'Reservations/raw thiếu hoặc thừa')
        for reservation in reservations:
            row = new[reservation['attempt_id']]
            require((reservation['provider_org'], reservation['stage'], reservation['model']) ==
                    (row['provider_org'], row['stage'], row['sdk_model']), 'Routing khác frozen ledger')
        bank = read(root / BANK / 'manifest.json')
        frames, _ = load_prices(root / bank['protocol']['price_snapshot'], bank['protocol']['price_quality_policy'])
        units = {j['unit']['id']: j['unit'] for j in manifest['jobs']}
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for job in manifest['jobs']:
            groups[(job['context']['unit_id'], job['context']['realization'])].append(job)
        dependencies = []; charts = {}; states = {}; used_vision = set()
        for _, jobs in sorted(groups.items()):
            job = next(j for j in jobs if 'node_hashes' in j['origin_parent'])
            upstream = job['origin_parent']['upstream_hash']
            shard = (root / job['origin_path']).parent.parent
            uid = job['context']['unit_id']; realization = job['context']['realization']; unit = units[uid]
            chart_path = shard / 'charts' / (uid + '.json'); chart = checked(chart_path)
            names.add(chart_path.relative_to(root).as_posix())
            require(chart['asset_hash'] == job['origin_parent']['asset_hash'], 'Chart asset khác upstream')
            if uid not in states:
                states[uid] = point_state(frames[unit['symbol']], unit['symbol'], unit['decision'], bank['protocol'], None)
            initial = {**states[uid], 'pattern_image': chart['pattern_image'], 'trend_image': chart['trend_image']}
            state = initial.copy(); node_hashes = []; ids = []
            for node in ('Indicator', 'Pattern', 'Trend'):
                path = shard / 'nodes' / f'{uid}_r{realization}_{node}.json'; cache = checked(path)
                names.add(path.relative_to(root).as_posix())
                require(cache['parent']['input_hash'] == identity_hash(pack_state(state)), 'Node input chain khác')
                require(cache['parent']['asset_hash'] == chart['asset_hash'] and
                        cache['parent']['run_signature'] == job['origin_parent']['run_signature'], 'Node parent khác')
                for entry in cache['call_hashes']:
                    require(file_hash(shard / entry['path']) == entry['sha256'], 'Node raw hash khác')
                require(len(cache['request_ids']) == (0 if node == 'Indicator' else 1) and not cache['failed_request_ids'], 'Node calls khác closure')
                ids.extend(cache['request_ids']); node_hashes.append(cache['sha256'])
                state.update(restore_state(cache['state'], initial))
            require(node_hashes == job['origin_parent']['node_hashes'] and identity_hash(pack_state(state)) == upstream, 'Shared upstream hash khác')
            require(all(j['origin_parent']['asset_hash'] == chart['asset_hash'] for j in jobs), 'Phase có asset khác')
            validate_upstream_jobs(jobs, node_hashes, job['origin_parent']['run_signature'], upstream)
            used_vision.update(ids)
            dependencies.append({'upstream_hash': upstream, 'unit_id': uid, 'realization': realization,
                                 'factorial_parent_hash': next((j['origin_parent']['upstream_hash'] for j in jobs if j['phase'] == 'factorial'), None),
                                 'dependent_decisions': len(jobs), 'indicator_calls': 0, 'vision_calls': len(ids),
                                 'pattern_attempt_id': ids[0], 'trend_attempt_id': ids[1]})
            if uid in charts:
                require(charts[uid] == chart, 'Một unit có chart khác giữa shards')
            charts[uid] = chart
        require(used_vision == {r['attempt_id'] for r in rows if r['stage'] == 'upstream'}, 'Graph dùng thiếu/thừa Vision')
        templates = {k: capture_text(k, 'vi') for k in ('pattern', 'trend')}
        actual_images = []
        for row in rows:
            if row['stage'] != 'upstream':
                continue
            request = requests[row['attempt_id']]; uid = request['context']['unit_id']
            kind = 'pattern' if row['node'] == 'Pattern Agent' else 'trend'
            images = image_parts(request['messages']); expected = base64.b64decode(charts[uid][kind + '_image'], validate=True)
            require(images == [expected], 'Ảnh request khác chart cache')
            require(text_parts(request['messages']) == templates[kind], 'Text Vision khác template Việt đã khóa')
            actual_images.append({'attempt_id': row['attempt_id'], 'unit_id': uid, 'kind': kind,
                                  'image_sha256': digest(expected), 'text_sha256': digest(encoded(templates[kind])),
                                  'matches_cache': True, 'matches_template': True})
        chart_rows = []
        for i, (uid, chart) in enumerate(sorted(charts.items()), 1):
            for kind in ('pattern', 'trend'):
                png, metadata = render(states[uid]['kline_data'], kind)
                compare_png(base64.b64decode(chart[kind + '_image'], validate=True), png)
                chart_rows.append({'unit_id': uid, 'kind': kind, 'byte_and_pixel_match': True, **metadata})
            if i % 20 == 0:
                print(f'T27: đã đối soát {i}/{len(charts)} cặp chart', flush=True)
        outputs = {}; fixtures = {}
        for kind in ('pattern', 'trend'):
            png, metadata = render(fixture_frame().to_dict('list'), kind)
            fixtures[kind] = metadata; outputs['fixture_' + kind + '.png'] = png
        scopes = {scope: summarize([r for r in rows if r['cost_scope'] == scope]) for scope in sorted({r['cost_scope'] for r in rows})}
        scopes['closure_total'] = summarize(rows)
        scopes['corrected_chart_requests_excluding_replayed_pattern'] = summarize([r for r in rows if r['node'] != 'Pattern Agent'])
        epoch_groups: dict[tuple, list[dict]] = defaultdict(list)
        for row in rows:
            epoch_groups[(row['cost_scope'], row['execution_epoch'], row['provider_org'], row['node'], row['sdk_model'])].append(row)
        epochs = [{'cost_scope': k[0], 'execution_epoch': k[1], 'provider_org': k[2], 'node': k[3], 'sdk_model': k[4], **summarize(v)}
                  for k, v in sorted(epoch_groups.items(), key=lambda x: str(x[0]))]
        completion = read(root / FINAL / 'completion.json')
        require(len(records) == len(manifest['jobs']) == completion['complete'] == completion['expected'] and completion['missing'] == 0, 'Jobs thiếu')
        pairing = read(root / FINAL / 'pairing.json')
        report = {'status': 'PASS_FINAL_COST_INTEGRITY_AUDIT', 'parents_checked_hashes': parents,
                  'complete_jobs': len(records), 'missing_jobs': 0, 'completion': completion, 'scope_costs': scopes,
                  'retry_groups': len(retry_rows), 'groups_with_retries': sum(r['attempts'] > 1 for r in retry_rows),
                  'failed_attempts_before_success': sum(r['failed_attempts_before_success'] for r in retry_rows),
                  'upstream_realizations': len(dependencies), 'dependent_decisions': sum(r['dependent_decisions'] for r in dependencies),
                  'actual_vision_requests': len(actual_images), 'unique_unit_charts': len(charts), 'rerendered_images': len(chart_rows),
                  'pattern_replay_files_verified': len(replay), 'minimal_reservations_verified': len(reservations),
                  'unknown_epoch_attempts': sum(r['execution_epoch'] is None for r in rows),
                  'unknown_provider_org_attempts': sum(r['provider_org'] is None for r in rows),
                  'system_fingerprints': len({r['system_fingerprint'] for r in rows if r['system_fingerprint']}),
                  'served_weight_revision': None, 'billing_cost': None, 'api_calls': 0, 'model_forwards': 0,
                  'paired_order_mismatches': sum(not p['order_matches'] for p in pairing),
                  'cross_epoch_paired_groups': sum(p['n_execution_epochs'] > 1 for p in pairing),
                  'fixtures': fixtures,
                  'limits': ['Usage calls lỗi và latency lỗi không có raw; null, không zero. Latency là tổng/quantiles thời gian request thành công, không walltime hoặc sleep.',
                             'Pattern tokens/latency thuộc call gốc, không replay lookup. Mỗi request chỉ tính một lần dù shared nhiều Decisions; không là toàn bộ chi phí dự án/smoke/archive.',
                             '91 Pattern requests thiếu epoch/org; alias/fingerprint không xác minh immutable served weights. Không suy org từ shard hoặc ngân sách tiền từ token counts.',
                             'Fixture xác minh màu thân Close/Open: green #006340, red #A02128, doji red; không phải màu so previous Close hay forecast. Support blue #0000ff, Resistance red #ff0000, legend handles đúng.',
                             'Actual Vision dùng template Việt: từ xanh không phân biệt blue/green rõ bằng English. Kiểm pixel/template không xác thực cách VLM hiểu ngữ nghĩa. Không sửa hồi tố raw hoặc ảnh legacy có legend sai.',
                             'Chỉ whitelist cuối 375 jobs đầy đủ; không tuyên bố hoàn tất các grid legacy 474/270. R9/R14 còn response/locator/quyền public/PID T34, T30 chưa đạt.']}
        lines = ['# Chi phí và integrity cuối (T27)', '', 'Phạm vi: closure của release T04, phân tích offline; không gọi API, không sửa raw hoặc paper.', '',
                 '| Phạm vi | Attempts | Success | Errors | Prompt tokens quan sát | Completion tokens quan sát | Latency success tổng (s) |',
                 '|---|---:|---:|---:|---:|---:|---:|']
        for scope, values in scopes.items():
            lines.append(f"| {scope} | {values['attempts']} | {values['successes']} | {values['errors']} | {values['prompt_tokens_observed_sum']} | {values['completion_tokens_observed_sum']} | {values['latency_seconds_observed_sum']:.6f} |")
        lines += ['', 'Các hàng scope có hàng tổng/chồng lắp; không cộng lại. Chi phí tiền: NA; usage/latency 34 errors: NA, không giả định bằng zero.', '',
                  f"375/375 jobs, missing=0; {len(retry_rows)} nhóm công việc, {report['groups_with_retries']} nhóm retry, 34 attempts lỗi trước success. retry_groups.csv giữ ID, số attempts và cross-epoch; không coi time gap là sleep thực.", '',
                  f"{len(dependencies)} upstream realizations dùng chung cho 375 Decisions; Indicator deterministic không API, 120 Pattern replay +120 Trend calls thực. Xác minh 240 files Pattern với nguồn gốc byte, 194 reservations từ snapshot T04 (không mở SQLite).", '',
                  f"Đối soát 240 Vision requests với cache và template Việt, render lại {len(chart_rows)} PNG từ 102 cửa sổ giá đóng băng: byte/pixel, geometry/màu nến, support/resistance và legend đều khớp. Fixture có gap, 22 up/22 down/một doji. Xem fixture_pattern.png và fixture_trend.png.", '',
                  'execution_epochs.csv tách scope/epoch/provider/node/model; attempts.csv giữ aliases, fingerprints, seed và timestamps raw. Có 91 attempts không quan sát epoch/org, 40 fingerprints; immutable served-weight revision vẫn unknown. 40 paired order deviations và chín cross-epoch groups giữ nguyên.', '',
                  *report['limits'], '',
                  'Kiểm: `py -3.13 -X utf8 scripts/analyze_revision_final_costs.py check`. Build lại phải dùng `build --output outputs/revision/final_cost_integrity_replay_v1` chưa tồn tại. Không API/key/model probe; không overwrite release cũ.', '']
        outputs.update({'report.json': encoded(report), 'report.md': '\n'.join(lines).encode(),
                        'attempts.csv': csv_bytes(rows), 'scope_costs.json': encoded(scopes), 'execution_epochs.csv': csv_bytes(epochs),
                        'retry_groups.csv': csv_bytes(retry_rows), 'dependencies.csv': csv_bytes(dependencies),
                        'pattern_replay_origins.csv': csv_bytes(replay), 'actual_images.csv': csv_bytes(actual_images),
                        'chart_replay.json': encoded(chart_rows), 'prompt_templates.json': encoded(templates)})
        sources = [{'path': n, 'sha256': file_hash(root / n)} for n in sorted(names)]
        # Khóa lại closure bằng hashes T04 trước khi ghi output; không nhận raw đổi giữa chừng.
        verify(root / FINAL)
        for source in sources:
            require(file_hash(root / source['path']) == source['sha256'], 'Source đổi khi build T27')
        folder.mkdir()
        for name, data in outputs.items():
            (folder / name).write_bytes(data)
        receipt = {'schema_version': 'final_cost_integrity_v1', 'sources': sources,
                   'outputs': [{'path': n, 'sha256': digest(b)} for n, b in sorted(outputs.items())]}
        receipt['sha256'] = digest(encoded(receipt))
        (folder / 'manifest.json').write_bytes(encoded(receipt))
        check(root, output)
        return report


def main() -> None:
    """Build release mới hoặc hash-check receipt, không có chế độ gọi API."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build', 'check'))
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.command == 'check':
        print(f'T27 hashes PASS: {check(ROOT, args.output)}')
    else:
        result = build(ROOT, args.output)
        print(f"T27 PASS: {result['complete_jobs']} jobs; {result['rerendered_images']} ảnh; không API")


if __name__ == '__main__':
    main()
