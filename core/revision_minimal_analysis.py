"""Phân tích T04 độc lập: không gọi API, refit baseline hoặc ghi bản thảo."""

from __future__ import annotations

from collections import Counter
from contextlib import ExitStack, contextmanager
import csv
import gzip
import hashlib
import json
from pathlib import Path
from typing import Iterator
from unittest.mock import patch
import zipfile

import numpy as np

from core.revision72_analysis import block_interval, target
from core.revision72_run import checked
from core.revision_baselines import daily_ledger, load_prices
from core.revision_call_archive import StudyLock
from core.revision_common_study import digest, native, read_json, write_json
from core.revision_minimal_audit import audit_attempts, audit_pairing, ledger_snapshot
from core.revision_minimal_bank import BANK, DEST, collect, require, runtime, sha, verify_manifest
from core.revision_minimal_run import status
from core.revision_r3_repeats import METRICS, describe, panel_identity, per_run_summary, resample
from core.revision_r4_factorial import VARIANTS, factorial_statistics
from utils.statistical_tests import binary_classification_metrics

OUTPUT = Path('outputs/revision/revision_minimal_final_v1')
CLASS_METRICS = METRICS[:-1]


@contextmanager
def offline_guard() -> Iterator[None]:
    """Chặn network, key loader, worker và fit; chỉ tái dùng predictions đã có."""
    with ExitStack() as stack:
        for name in ('socket.socket.connect', 'socket.create_connection', 'dotenv.load_dotenv',
                     'core.revision_minimal_run.worker', 'core.revision_minimal_run.run_queue',
                     'langchain_groq.ChatGroq.invoke', 'core.revision_baselines.logistic_predictions',
                     'core.revision_baselines.factor_vote', 'core.revision_baselines.numerical_features'):
            stack.enter_context(patch(name, side_effect=AssertionError('T04 chỉ được phân tích offline, không fit/inference')))
        yield


def output_path(root: Path, output: Path) -> Path:
    """Chỉ cho release con của outputs/revision; không nhận paper hoặc nguồn queue."""
    result = (output if output.is_absolute() else root / output).resolve()
    base = (root / 'outputs/revision').resolve()
    require(result.parent == base and result != (root / DEST).resolve(), 'Đường dẫn release T04 không hợp lệ')
    return result


def metric_groups(rows: list[dict]) -> dict:
    """Pooled và macro có mẫu số/lớp hỗ trợ; không gộp repeats thành thị trường mới."""
    require(bool(rows) and len({r['unit_id'] for r in rows}) == len(rows), 'Duplicate/rỗng classification support')
    pooled = binary_classification_metrics([r['label_net'] for r in rows], [r['prediction'] for r in rows])
    groups = {}
    for field in ('symbol', 'fold'):
        groups[field] = {value: binary_classification_metrics(
            [r['label_net'] for r in rows if r[field] == value], [r['prediction'] for r in rows if r[field] == value])
            for value in sorted({r[field] for r in rows})}
    macro = {metric: describe([r[metric] for r in groups['symbol'].values()]) for metric in CLASS_METRICS}
    return {'pooled': pooled, 'by_symbol': groups['symbol'], 'by_block': groups['fold'], 'macro_symbol': macro}


def checked_predictions(rows: list[dict], units: list[dict], labels: dict, inputs: dict) -> list[str]:
    """Từ chối baseline khác common support, target hoặc thông tin market đã khóa."""
    variants = sorted({r['variant'] for r in rows}); expected = {u['id'] for u in units}
    require(bool(variants), 'Thiếu numerical baselines')
    metadata = {u['id']: u for u in units}
    for variant in variants:
        part = [r for r in rows if r['variant'] == variant]
        require(len(part) == len(expected) and {r['unit_id'] for r in part} == expected, 'Baseline thiếu/trùng common support')
        for row in part:
            unit = metadata[row['unit_id']]
            require(all(row[k] == unit[k] for k in ('symbol', 'fold', 'date')), 'Baseline khác metadata')
            require(row['label_net'] == labels[unit['id']][0] and row['label_gross'] == labels[unit['id']][1], 'Baseline khác target')
            require(row['market_input_hash'] == inputs[unit['id']], 'Baseline khác market information hash')
            require(row['prediction'] in ('LONG', 'SHORT'), 'Baseline không phải binary prediction')
    return variants


def account_rows(rows: list[dict], units: list[dict], frames: dict, protocol: dict,
                 panel: str, execution: int) -> tuple[list[dict], list[dict], dict, dict]:
    """Tái lập ledger riêng từng symbol/block, SHORT=CASH; lưu tensors cùng support."""
    variants = sorted({r['variant'] for r in rows}); blocks = sorted({u['fold'] for u in units})
    predictions = {(r['unit_id'], r['variant']): r['prediction'] for r in rows}
    require(len(predictions) == len(rows) == len(units) * len(variants), 'Account support không đầy đủ')
    counts = {v: np.zeros((len(blocks), 4), dtype=int) for v in variants}
    returns = {v: np.zeros((len(blocks), 2), dtype=float) for v in variants}
    accounts, daily = [], []
    for variant in variants:
        for symbol, fold in sorted({(u['symbol'], u['fold']) for u in units}):
            selected = sorted([u for u in units if (u['symbol'], u['fold']) == (symbol, fold)], key=lambda u: u['decision'])
            key = {'panel': panel, 'execution': execution, 'variant': variant, 'symbol': symbol, 'fold': fold}
            cycles = [(u['decision'] + 1, u['decision'] + 3, int(predictions[(u['id'], variant)] == 'LONG')) for u in selected]
            ledger = daily_ledger(frames[symbol], cycles, protocol)
            daily.extend({**key, **r} for r in ledger.pop('daily'))
            accounts.append({**key, 'n_cycles': len(selected), **ledger})
            returns[variant][blocks.index(fold)] += [ledger['net_return_pct'], 1]
        for index, block in enumerate(blocks):
            part = [r for r in rows if r['fold'] == block and r['variant'] == variant]
            c = binary_classification_metrics([r['label_net'] for r in part], [r['prediction'] for r in part])['confusion']
            counts[variant][index] = [c[k] for k in ('tp', 'fn', 'tn', 'fp')]
    return accounts, daily, counts, returns


def repeat_panel(name: str, units: list[dict], records: list[dict], requests: dict,
                 frames: dict, protocol: dict, labels: dict, upstream: bool) -> tuple[dict, list[dict], list[dict], dict]:
    """Phân tích đủ ba lần chạy, giữ native prompt identity và upstream pairing."""
    variants = ('B', 'AS') if upstream else VARIANTS
    identity = panel_identity(records, requests, [u['id'] for u in units], list(variants), upstream)
    index = {(r['context']['unit_id'], r['context']['variant'],
              r['context']['realization'] if upstream else r['context']['repeat']): r for r in identity['records']}
    all_accounts, all_daily, executions = [], [], []
    blocks = sorted({u['fold'] for u in units})
    counts = {v: np.zeros((3, len(blocks), 4), dtype=int) for v in variants}
    returns = {v: np.zeros((3, len(blocks), 2), dtype=float) for v in variants}
    for execution in range(3):
        rows = [{**u, 'unit_id': u['id'], 'variant': v, 'label_net': labels[u['id']][0],
                 'prediction': index[(u['id'], v, execution)]['prediction']} for u in units for v in variants]
        accounts, daily, c, a = account_rows(rows, units, frames, protocol, name, execution)
        all_accounts.extend(accounts); all_daily.extend(daily)
        for variant in variants:
            counts[variant][execution] = c[variant]; returns[variant][execution] = a[variant]
            metrics = metric_groups([r for r in rows if r['variant'] == variant])
            executions.append({'variant': variant, 'execution': execution, **metrics,
                               **{k: metrics['pooled'][k] for k in CLASS_METRICS},
                               'mean_account_net_return_pct': float(np.mean([r['net_return_pct'] for r in accounts if r['variant'] == variant]))})
    summaries = {v: per_run_summary([r for r in executions if r['variant'] == v]) for v in variants}
    stats = resample(counts, returns) if upstream else factorial_statistics(counts, returns)
    summary = {'panel': name, 'n_units_per_execution': len(units), 'n_executions': 3,
               'n_decisions': len(identity['records']), 'n_unique_successful_requests': identity['n_unique_successful_requests'],
               'n_dates': len({u['date'] for u in units}), 'n_symbols': len({u['symbol'] for u in units}),
               'blocks': blocks, 'support_per_execution': dict(Counter(labels[u['id']][0] for u in units)),
               'n_accounts_per_variant_execution': len(all_accounts) // (3 * len(variants)),
               'summaries': summaries, 'by_execution': executions, 'statistics': stats,
               'disagreement': identity['disagreement_by_cutoff'],
               'mean_pairwise_disagreement': {v: float(np.mean([r['pairwise_disagreement'] for r in identity['disagreement_by_cutoff'] if r['variant'] == v])) for v in variants},
               'scope': 'Mọi execution được giữ; không ensemble/best run. SD/CI chỉ thuộc panel, không phải variance của main 102 hoặc variance components.'}
    tensors = {**{f'{name}_counts_{v}': x for v, x in counts.items()}, **{f'{name}_accounts_{v}': x for v, x in returns.items()}}
    return summary, all_accounts, all_daily, tensors


def numeric_closure(root: Path) -> tuple[set[Path], list[dict]]:
    """Xác minh source numeric trước amendment bằng đúng ZIP lịch sử đã lưu."""
    numeric = root / BANK / 'numeric'; receipt = read_json(numeric / 'manifest.json')
    paths, archived = {numeric / 'manifest.json'}, []
    for group, base in (('sources', root), ('outputs', numeric)):
        for row in receipt[group]:
            path = base / row['path']
            if sha(path) != row['sha256']:
                require(group == 'sources' and row['path'] == 'core/revision72_analysis.py',
                        'Numerical source/output đã đổi: ' + row['path'])
                archive = root / 'outputs/revision/r1_72h_run_v2/runtime_history/original_sources.zip'
                with zipfile.ZipFile(archive) as handle:
                    require(hashlib.sha256(handle.read(row['path'])).hexdigest() == row['sha256'], 'Source numeric lịch sử không khớp ZIP')
                paths.add(archive)
                archived.append({**row, 'archive': archive.relative_to(root).as_posix(), 'member': row['path'],
                                 'scope': 'Source lúc sinh numeric trước amendment; không gán checksum này cho source hiện tại.'})
            else:
                paths.add(path)
    return paths, archived


def source_snapshot(root: Path, manifest: dict) -> list[dict]:
    """Khóa closure frozen cùng raw/checkpoints mới và numerical outputs đã tái dùng."""
    paths = {root / r['path'] for r in manifest['sources']}
    paths.add(root / DEST / 'manifest.json')
    for folder in ('calls', 'decisions'):
        paths.update((root / DEST).glob(f'shards/org*/{folder}/*.json'))
    numeric_paths, _ = numeric_closure(root); paths.update(numeric_paths)
    paths.update(root / p for p in ('core/revision_minimal_analysis.py', 'core/revision_minimal_audit.py',
                                   'scripts/analyze_revision_minimal.py', 'tests/test_revision_minimal_analysis.py',
                                   'core/revision_r3_repeats.py', 'core/revision_r4_factorial.py'))
    return [{'path': p.relative_to(root).as_posix(), 'sha256': sha(p)} for p in sorted(paths)]


def verify_hashes(root: Path, rows: list[dict]) -> None:
    """Không sửa nguồn để khớp receipt; fail khi có thay đổi ngoài phân tích."""
    for row in rows:
        path = (root / row['path']).resolve()
        require(path.is_relative_to(root.resolve()) and sha(path) == row['sha256'], 'Hash thay đổi: ' + row['path'])


def check_release(root: Path, output: Path) -> int:
    """Kiểm release đã khóa mà không cần credentials, live ledger hoặc refit."""
    output = output_path(root, output); receipt = checked(output / 'manifest.json')
    require(receipt['runtime'] == runtime(), 'Runtime khác receipt T04')
    verify_hashes(root, receipt['sources']); verify_hashes(output, receipt['outputs'])
    actual = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
    require(actual == {'manifest.json', *[r['path'] for r in receipt['outputs']]}, 'Release có file thừa/thiếu')
    return len(receipt['sources']) + len(receipt['outputs'])


def build_release(root: Path, output: Path) -> dict:
    """Chỉ xuất release mới sau khi mọi scope, raw, pairing và baseline đều hợp lệ."""
    output = output_path(root, output)
    require(not output.exists(), 'Không ghi đè release T04; dùng check hoặc output mới')
    with StudyLock(root / 'tmp/revision_minimal_analysis.lock'), offline_guard():
        manifest = verify_manifest(root, root / DEST)
        completion = status(root, root / DEST, manifest)
        require(completion['complete'] == 375 and completion['missing'] == 0 and not completion['temporary_checkpoints'], 'Queue chưa đủ 375')
        require(not completion['new_calls']['interrupted_request_ids'] and not completion['new_calls']['reserved_before_archive_ids'], 'Queue còn attempt dở')
        sources = source_snapshot(root, manifest)
        records = collect(root, root / DEST, manifest)
        lineage, pairing = audit_pairing(root, manifest, records)
        attempts, costs = audit_attempts(root, manifest, records)
        ledger = ledger_snapshot(root, manifest['sha256'], attempts)
        bank = read_json(root / BANK / 'manifest.json'); protocol = bank['protocol']; units = bank['units']
        frames, quality = load_prices(root / protocol['price_snapshot'], protocol['price_quality_policy'])
        labels, inputs = {}, {}
        for unit in units:
            y, g = target(frames[unit['symbol']], [unit['decision']], protocol)
            labels[unit['id']] = ('UP' if y[0] else 'DOWN', 'UP' if g[0] else 'DOWN')
            inputs[unit['id']] = checked(root / BANK / f"features/{unit['symbol']}_{unit['decision']}.json")['market_input_hash']
        with (root / BANK / 'numeric/predictions.csv').open(encoding='utf-8', newline='') as handle:
            main_rows = list(csv.DictReader(handle))
        numeric_variants = checked_predictions(main_rows, units, labels, inputs)
        require(len(numeric_variants) == 7 and not {'B', 'AS'}.intersection(numeric_variants), 'Sai numerical baseline family')
        unit_index = {u['id']: u for u in units}
        for record in records:
            if record['phase'] != 'main': continue
            unit = unit_index[record['context']['unit_id']]
            main_rows.append({'unit_id': unit['id'], **{k: unit[k] for k in ('symbol', 'fold', 'date')},
                              'variant': record['context']['variant'], 'prediction': record['prediction'],
                              'label_net': labels[unit['id']][0], 'label_gross': labels[unit['id']][1],
                              'market_input_hash': inputs[unit['id']]})
        variants = checked_predictions(main_rows, units, labels, inputs)
        accounts, daily, main_counts, main_returns = account_rows(main_rows, units, frames, protocol, 'main', 0)
        with (root / BANK / 'numeric/summary.csv').open(encoding='utf-8', newline='') as handle:
            old_accounts = list(csv.DictReader(handle))
        for old in old_accounts:
            if old['variant'] == 'continuous_hold_price_only':
                selected = sorted([u for u in units if (u['symbol'], u['fold']) == (old['symbol'], old['fold'])], key=lambda u: u['decision'])
                value = daily_ledger(frames[old['symbol']], [(selected[0]['decision']+1, selected[-1]['decision']+3, 1)], protocol)
                key = {'panel': 'main', 'execution': 0, 'variant': old['variant'], 'symbol': old['symbol'], 'fold': old['fold']}
                daily.extend({**key, **r} for r in value.pop('daily'))
                actual = {**key, 'n_cycles': 1, **value}; accounts.append(actual)
            else:
                actual = next(r for r in accounts if all(r[k] == old[k] for k in ('symbol', 'fold', 'variant')))
            for key, value in old.items():
                if key in ('symbol', 'fold', 'variant', 'n_test'): continue
                require(np.isclose(actual[key], float(value), rtol=1e-11, atol=1e-8), 'Baseline ledger khác snapshot: ' + key)
        classes = {v: metric_groups([r for r in main_rows if r['variant'] == v]) for v in variants}
        for v, metrics in classes.items():
            metrics['mean_account_net_return_pct'] = float(np.mean([r['net_return_pct'] for r in accounts if r['variant'] == v]))
        cohorts = {}
        for name, selected in (('common_eight_six_blocks', [u for u in units if u['symbol'] != 'BHN']),
                               ('recent_nine_three_blocks', [u for u in units if u['fold'].startswith('f')])):
            ids = {u['id'] for u in selected}
            cohorts[name] = {v: metric_groups([r for r in main_rows if r['variant'] == v and r['unit_id'] in ids]) for v in variants}
        contrasts = [block_interval(main_rows, ('AS', v)) for v in variants if v != 'AS']
        for row in contrasts:
            control = row['contrast'][3:]
            row['observed_BA_delta'] = classes['AS']['pooled']['balanced_accuracy'] - classes[control]['pooled']['balanced_accuracy']
        request_map = {r['request_ids'][-1]: checked(root / row['request_path']) for r, row in zip(records, lineage)}
        tensors = {**{f'main_counts_{v}': x for v, x in main_counts.items()}, **{f'main_accounts_{v}': x for v, x in main_returns.items()}}
        panels = {}
        for name, selected, part, upstream in (
            ('upstream', [u for u in units if u['upstream']], [checked(root / r['path']) for r in records if r['phase'] in ('main', 'upstream')], True),
            ('factorial', manifest['panel'], [checked(root / r['path']) for r in records if r['phase'] == 'factorial'], False)):
            panel, a, d, tensor = repeat_panel(name, selected, part, request_map, frames, protocol, labels, upstream)
            panels[name] = panel; accounts.extend(a); daily.extend(d); tensors.update(tensor)
        rng = np.random.default_rng(20261102)
        tensors['main_block_weights'] = rng.multinomial(len(main_counts['AS']), np.full(len(main_counts['AS']), 1/len(main_counts['AS'])), 10000)
        for name, panel in panels.items():
            n = len(panel['blocks']); rng = np.random.default_rng(20261102)
            tensors[f'{name}_block_weights'] = rng.multinomial(n, np.full(n, 1/n), 10000)
            tensors[f'{name}_run_weights'] = rng.multinomial(3, np.full(3, 1/3), 10000)
        summary = {'result': 'PASS_EXPLORATORY_MINIMAL_RELEASE', 'run_signature': manifest['sha256'],
                   'research_executions': len(records), 'reused': completion['reused'], 'new_successes': costs['new']['successes'],
                   'new_attempts': costs['new']['attempts'], 'new_errors': costs['new']['errors'], 'new_vision_calls': 0,
                   'analysis_api_calls': 0, 'baseline_fits': 0, 'main_units': len(units),
                   'main_class_support': dict(Counter(v[0] for v in labels.values())),
                   'main_dates': len({u['date'] for u in units}), 'main_blocks': sorted({u['fold'] for u in units}),
                   'main_classification': classes, 'main_BA_contrasts': contrasts,
                   'panel_support': {name: {k: p[k] for k in ('n_units_per_execution', 'n_executions', 'n_decisions', 'n_dates', 'n_symbols', 'blocks', 'support_per_execution')} for name, p in panels.items()},
                   'n_accounts': len(accounts), 'baseline_accounts_reproduced': len(old_accounts),
                   'pair_order_mismatches': sum(not p['order_matches'] for p in pairing),
                   'pair_order_by_phase': {phase: {'groups': sum(p['phase'] == phase for p in pairing),
                                                   'mismatches': sum(p['phase'] == phase and not p['order_matches'] for p in pairing)}
                                           for phase in ('main', 'upstream', 'factorial')},
                   'cross_epoch_pairs': sum(p['n_execution_epochs'] > 1 for p in pairing),
                   'order_scope': 'So sánh thứ tự liệt kê jobs trong manifest với thời gian successful request; queue LPT/reuse/quota không bảo đảm counterbalance. Giữ mọi outcome, không sửa lịch sử hoặc gọi bù để đổi order.',
                   'scope': 'Historical exploratory sau amendment; broad main prompt R1 rút gọn khác factorial R4 đủ giá trị. Ba repeats/ba blocks panel không xác nhận variance main hoặc causal attribution. CI mô tả, không p-value/superiority. Native row-wise causal gate T10 vẫn FAIL. PIT/domain/served weights và execution feasibility chưa xác thực; T04 không đóng R1–R18 hoặc gate T30.'}
        gross = {v: binary_classification_metrics([r['label_gross'] for r in main_rows if r['variant'] == v],
                                                 [r['prediction'] for r in main_rows if r['variant'] == v]) for v in variants}
        payloads = {'summary.json': summary, 'completion.json': {k: v for k, v in completion.items() if k != 'missing_jobs'},
                    'records.json': records, 'lineage.json': lineage, 'pairing.json': pairing, 'attempts.json': attempts,
                    'costs.json': costs, 'ledger_snapshot.json': ledger, 'main_predictions.json': main_rows,
                    'main_cohorts.json': cohorts, 'upstream_panel.json': panels['upstream'], 'factorial_panel.json': panels['factorial'],
                    'gross_diagnostic.json': {'classification': gross, 'scope': 'Diagnostic gross riêng; mọi prediction được elicited cho target net đã khóa.'},
                    'accounts.json': accounts, 'price_quality.json': quality,
                    'numeric_provenance.json': {'archived_sources': numeric_closure(root)[1],
                                                'prediction_policy': 'Tái dùng nguyên predictions/models/baseline manifests đã khóa; không refit.'}}
        verify_hashes(root, sources); verify_manifest(root, root / DEST)
        output.mkdir(parents=True)
        for name, value in payloads.items(): write_json(output / name, value, True)
        with (output / 'daily_ledgers.json.gz').open('xb') as handle:
            handle.write(gzip.compress(json.dumps(native(daily), ensure_ascii=False, allow_nan=False).encode('utf-8'), mtime=0))
        with (output / 'resampling.npz').open('xb') as handle: np.savez_compressed(handle, **tensors)
        verify_hashes(root, sources)
        receipt = {'schema_version': 'revision_minimal_final_v1', 'run_signature': manifest['sha256'],
                   'runtime': runtime(), 'sources': sources,
                   'outputs': [{'path': p.name, 'sha256': sha(p)} for p in sorted(output.iterdir())],
                   'frozen_queue_sources_verified': len(manifest['sources']),
                   'analysis_timing': 'Thủ tục T04 sau inference; tái dùng descriptive bootstrap R1/R3/R4 đã có, không gọi preregistered.'}
        write_json(output / 'manifest.json', {**receipt, 'sha256': digest(receipt)}, True)
        check_release(root, output)
        return summary
