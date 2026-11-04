"""Sensitivity T19 trên release T04: chỉ đọc nguồn, không ghi bản thảo/gọi API."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import date
import gzip
import hashlib
import io
import json
from math import isclose, isfinite
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.revision_baselines import load_prices
from core.revision_call_archive import StudyLock
from core.revision_minimal_analysis import check_release as check_t04, offline_guard, verify_hashes
from core.revision_minimal_bank import BANK, runtime
from core.revision_execution import execution_ledger

FINAL = Path('outputs/revision/revision_minimal_final_v1')
EVIDENCE = Path('outputs/revision/execution_evidence_v1')
OUTPUT = Path('outputs/revision/execution_final_v1')
POLICY = Path('revision/r15_execution_policy.json')
HOLD = 'continuous_hold_price_only'
VARIANTS = ('AS', 'B', 'constant_down_cash', 'constant_up_cycles', 'factor_only_vote',
            'logistic_matched_market_inputs', 'logistic_price', 'momentum_20', 'train_majority')
COSTS = ('brokerage_fee_vnd', 'slippage_cost_vnd', 'sell_charge_vnd', 'advance_fee_vnd')


def require(condition: bool, message: str) -> None:
    """Dừng khi hợp đồng nguồn, support hoặc kinh tế không được thỏa mãn."""
    if not condition:
        raise ValueError(message)


def read(path: Path) -> Any:
    """Đọc JSON nghiêm ngặt, không chấp nhận NaN/Infinity."""
    def invalid(value: str) -> None:
        raise ValueError('JSON không hữu hạn: ' + value)
    return json.loads(path.read_bytes(), parse_constant=invalid)


def json_bytes(value: Any) -> bytes:
    """Tuần tự hóa nguyên sinh, không âm thầm thay giá trị vô hạn bằng zero."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def sha(path: Path) -> str:
    """Hash byte gốc của nguồn hoặc đầu ra."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_bytes(rows: list[dict]) -> bytes:
    """Xuất NA cho undefined, không đưa kiểu NumPy vào trạng thái JSON."""
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(k for r in rows for k in r)), lineterminator='\n')
    writer.writeheader()
    writer.writerows({k: 'NA' if v is None else v for k, v in row.items()} for row in rows)
    return stream.getvalue().encode('utf-8')


def output_path(root: Path, output: Path) -> Path:
    """Chỉ cho release execution_final mới trực tiếp dưới outputs/revision."""
    result = (root / output).resolve()
    require(result.parent == (root / 'outputs/revision').resolve() and
            result.name.startswith('execution_final_'), 'Đường dẫn release T19 không hợp lệ')
    return result


def check_manifest(root: Path, folder: Path) -> int:
    """Kiểm hash/self-digest và tập file; không tái tạo bất kỳ artifact cũ nào."""
    manifest = read(folder / 'manifest.json')
    unsigned = {k: v for k, v in manifest.items() if k != 'sha256'}
    require(hashlib.sha256(json_bytes(unsigned)).hexdigest() == manifest['sha256'], 'Manifest sai self-digest')
    verify_hashes(root, manifest['sources'])
    verify_hashes(folder, manifest['outputs'])
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    require(actual == {'manifest.json', *[r['path'] for r in manifest['outputs']]}, 'Release có file thừa/thiếu')
    return len(manifest['sources']) + len(manifest['outputs'])


def check_parents(root: Path) -> dict[str, int]:
    """T04 kiểm cả runtime/raw closure; T18 kiểm nguồn và lịch đã khóa."""
    return {'T04': check_t04(root, root / FINAL), 'T18': check_manifest(root, root / EVIDENCE)}


def settlement(day: str, lag: int, calendar: np.busdaycalendar) -> str:
    """Ngày T+n theo lịch VSD/VSDC; không đồng nhất ngày về với open sáng."""
    require(bool(np.is_busday(day, busdaycal=calendar)), 'Ngày giao dịch ngoài lịch thanh toán: ' + day)
    return str(np.busday_offset(day, lag, busdaycal=calendar))


def check_calendar(frame: pd.DataFrame, first: int, last: int, config: dict) -> np.busdaycalendar:
    """Fail-closed nếu observed dates thiếu/thừa ngày trong cửa sổ execution."""
    dates = frame['date'].to_numpy().astype('datetime64[D]')
    calendar = np.busdaycalendar(weekmask=config['weekmask'], holidays=config['holidays'])
    require(0 <= first <= last < len(dates), 'Cửa sổ calendar ngoài snapshot')
    years = set(range(int(str(dates[first])[:4]), int(str(dates[last])[:4]) + 1))
    require(years.issubset(config['supported_years']), 'Calendar chưa có căn cứ cho năm này')
    expected = np.arange(dates[first], dates[last] + np.timedelta64(1, 'D'))
    expected = expected[np.is_busday(expected, busdaycal=calendar)]
    require(np.array_equal(dates[first:last + 1], expected), 'Observed bars khác lịch thanh toán T18')
    return calendar


def near(actual: float, expected: float, context: str) -> None:
    """Dung sai VND nhỏ, chặn sai thứ tự hoặc đếm trùng receivable."""
    require(isfinite(actual) and isclose(actual, expected, abs_tol=1e-5, rel_tol=1e-10),
            'Đối soát ledger không khớp: ' + context)


def audit_ledger(frame: pd.DataFrame, result: dict, config: dict, initial: float,
                 multiplier: float, calendar: np.busdaycalendar) -> int:
    """Oracle dòng tiền theo ngày pháp lý, độc lập với offset/bar state của engine.

    Tái dựng cash, inventory và receivable từ fill/advance events; kiểm mọi dòng,
    phí hai chân, thuế bán, ACT/365, maturity và MTM. Không xác nhận fill thị trường.
    """
    dates = frame['date'].to_numpy().astype('datetime64[D]').astype(str)
    index = {day: i for i, day in enumerate(dates)}
    prices = frame[['Open', 'Close']].to_numpy(float) * multiplier
    by_day: dict[str, list[dict]] = defaultdict(list)
    for event in result['events']:
        require(event['clock_time'] is None and event['timezone'] == 'Asia/Ho_Chi_Minh', 'Sai thời điểm event')
        by_day[event['date']].append(event)
    cash, shares, stock_due = float(initial), 0., None
    pending: list[tuple[str, float]] = []
    totals = dict.fromkeys(COSTS, 0.)
    equity = [initial]
    buy_count, sell_count = 0, 0
    fee, slip, tax = (config[k] for k in ('fee_each_side', 'slippage_each_side', 'sell_charge'))
    for row in result['daily']:
        day = row['date']
        costs = dict.fromkeys(COSTS, 0.)
        cash += sum(amount for due, amount in pending if due < day)
        pending = [(due, amount) for due, amount in pending if due >= day]
        held = int(shares > 0)
        for event in by_day[day]:
            if event['side'] == 'ADVANCE' and event['status'] == 'assigned_receivable':
                match = next((i for i, (_, amount) in enumerate(pending)
                              if np.isclose(amount, event['principal_vnd'], atol=1e-5, rtol=1e-10)), None)
                require(match is not None, 'Ứng trước khoản phải thu không tồn tại/đã chuyển nhượng')
                due, amount = pending.pop(match)
                charge = amount * config['advance_annual_rate'] * (date.fromisoformat(due) - date.fromisoformat(day)).days / 365
                near(event['fee_vnd'], charge, 'phí ứng trước theo yêu cầu')
                cash += amount - charge
                costs['advance_fee_vnd'] += charge
            if event['status'] != 'filled':
                continue
            quantity, price = event['quantity'], event['fill_price_vnd']
            require(quantity > 0, 'Fill không có quantity dương')
            notional = quantity * price
            if event['side'] == 'BUY':
                require(shares == 0 and event['phase'] == 'open', 'BUY không flat/open')
                near(price, prices[index[day], 0] * (1 + slip), 'giá BUY')
                require(notional * (1 + fee) <= cash + 1e-5, 'Dùng tiền pending ở open')
                cash -= notional * (1 + fee)
                shares, held = quantity, 1
                stock_due = settlement(day, config['stock_lag'], calendar)
                costs['brokerage_fee_vnd'] += notional * fee
                costs['slippage_cost_vnd'] += quantity * prices[index[day], 0] * slip
                buy_count += 1
            elif event['side'] == 'SELL':
                require(stock_due is not None and stock_due <= day and event['phase'] == 'close', 'Bán cổ phiếu chưa về')
                near(quantity, shares, 'quantity SELL')
                near(price, prices[index[day], 1] * (1 - slip), 'giá SELL')
                proceeds = notional * (1 - fee - tax)
                near(event['proceeds_vnd'], proceeds, 'tiền bán sau phí/thuế')
                costs['brokerage_fee_vnd'] += notional * fee
                costs['slippage_cost_vnd'] += quantity * prices[index[day], 1] * slip
                costs['sell_charge_vnd'] += notional * tax
                due = settlement(day, config['settlement_lag'], calendar)
                release = index[day] + config['settlement_lag']
                require(event['settlement_bar_index'] == release, 'Sai chỉ số maturity')
                if release < len(dates):
                    require(dates[release] == due, 'Maturity observed khác lịch T18')
                if config['cash_mode'] == 'immediate':
                    cash += proceeds
                elif config['cash_mode'] == 'advance_auto' and release < len(dates):
                    charge = proceeds * config['advance_annual_rate'] * (date.fromisoformat(due) - date.fromisoformat(day)).days / 365
                    cash += proceeds - charge
                    costs['advance_fee_vnd'] += charge
                else:
                    pending.append((due, proceeds))
                shares, stock_due = 0., None
                sell_count += 1
            else:
                raise ValueError('Fill side không hợp lệ')
        cash += sum(amount for due, amount in pending if due <= day)
        pending = [(due, amount) for due, amount in pending if due > day]
        pending_value = sum(amount for _, amount in pending)
        mtm = shares * prices[index[day], 1]
        settled = shares if stock_due is not None and stock_due <= day else 0.
        expected = {'settled_cash_vnd': cash, 'pending_cash_vnd': pending_value, 'shares': shares,
                    'stock_mtm_vnd': mtm, 'settled_shares': settled, 'unsettled_shares': shares - settled,
                    'equity_vnd': cash + pending_value + mtm, 'held_during_session': held, **costs}
        for field, value in expected.items():
            near(float(row[field]), value, day + '/' + field)
        for field in COSTS:
            totals[field] += costs[field]
        equity.append(expected['equity_vnd'])
    summary = result['summary']
    values = np.asarray(equity)
    for field, value in {**totals, 'order_count': buy_count + sell_count, 'n_buy_fills': buy_count,
                         'n_sell_fills': sell_count, 'n_daily_rows': len(result['daily']),
                         'net_return_pct': (values[-1] / initial - 1) * 100,
                         'daily_close_drawdown_pct': float((1 - values / np.maximum.accumulate(values)).max() * 100),
                         'final_settled_cash_vnd': cash, 'final_pending_cash_vnd': sum(v for _, v in pending),
                         'final_shares': shares}.items():
        near(float(summary[field]), float(value), 'summary/' + field)
    require(summary['terminal_is_liquidated'] == (shares == 0), 'Sai trạng thái residual')
    return len(result['daily'])


def cases_from_final(units: list[dict], predictions: list[dict], accounts: list[dict]) -> tuple[list[dict], dict]:
    """Chỉ nhận main execution 0 cuối; không lấy predictions/economics legacy."""
    indexed = {(r['unit_id'], r['variant']): r for r in predictions}
    unit_ids = {r['id'] for r in units}
    require(len(unit_ids) == len(units) == 102 and len(indexed) == len(predictions) == 918, 'Sai support T04')
    require(set(indexed) == {(u, v) for u in unit_ids for v in VARIANTS}, 'Thiếu/trùng variant T04')
    by_scope: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for unit in units:
        by_scope[(unit['symbol'], unit['fold'])].append(unit)
        for variant in VARIANTS:
            row = indexed[(unit['id'], variant)]
            require(all(row[k] == unit[k] for k in ('symbol', 'fold', 'date')) and
                    row['prediction'] in ('LONG', 'SHORT'), 'Prediction khác unit/action T04')
    reference_rows = [r for r in accounts if r['panel'] == 'main' and r['execution'] == 0]
    reference = {(r['symbol'], r['fold'], r['variant']): r for r in reference_rows}
    require(len(reference) == len(reference_rows) == 510 and len(by_scope) == 51, 'Sai support accounts T04')
    cases = []
    for (symbol, fold), selected in sorted(by_scope.items()):
        selected = sorted(selected, key=lambda r: r['decision'])
        require(len(selected) == 2, 'Mỗi scope phải có hai cutoffs')
        for variant in (*VARIANTS, HOLD):
            cycles = ([(selected[0]['decision'] + 1, selected[-1]['decision'] + 3, 1, f'hold_{symbol}_{fold}')]
                      if variant == HOLD else [(u['decision'] + 1, u['decision'] + 3,
                         int(indexed[(u['id'], variant)]['prediction'] == 'LONG'), u['id']) for u in selected])
            key = (symbol, fold, variant)
            require(key in reference, 'Thiếu reference account')
            cases.append({'symbol': symbol, 'fold': fold, 'variant': variant, 'cycles': cycles,
                          'n_units': 2, 'reference': reference[key]})
    require(len(cases) == 510, 'Phải có 510 cases')
    return cases, by_scope


def source_snapshot(root: Path, price_snapshot: str) -> list[dict]:
    """Khóa hash đầu vào và code trước tính toán, kiểm lại sau khi tính xong."""
    paths = [p for parent in (FINAL, EVIDENCE) for p in (root / parent).iterdir() if p.is_file()]
    paths += [root / BANK / 'manifest.json', root / POLICY, root / price_snapshot / 'manifest.json']
    paths += sorted((root / price_snapshot).glob('*.csv'))
    paths += [root / p for p in ('core/revision_execution.py', 'core/revision_baselines.py',
        'core/revision_minimal_analysis.py', 'core/revision_minimal_bank.py', 'core/revision_common_study.py',
        'core/revision_call_archive.py', 'core/revision72_run.py', 'core/revision_execution_final.py',
        'scripts/analyze_revision_execution_final.py', 'tests/test_revision_execution_final.py', '.python-version')]
    return [{'path': p.relative_to(root).as_posix(), 'sha256': sha(p)} for p in sorted(set(paths))]


def generate(root: Path) -> tuple[dict[str, bytes], list[dict]]:
    """Tính đủ 12 scenarios, đối soát reference và oracle trước khi xuất file."""
    parent_counts = check_parents(root)
    policy = read(root / POLICY)
    require(len(policy['scenarios']) == len({s['id'] for s in policy['scenarios']}) == 12, 'Sai family 12 scenarios')
    bank = read(root / BANK / 'manifest.json')
    protocol = bank['protocol']
    sources = source_snapshot(root, protocol['price_snapshot'])
    predictions = read(root / FINAL / 'main_predictions.json')
    ids = {r['unit_id'] for r in predictions}
    units = [u for u in bank['units'] if u['id'] in ids]
    cases, scopes = cases_from_final(units, predictions, read(root / FINAL / 'accounts.json'))
    frames, _ = load_prices(root / protocol['price_snapshot'], protocol['price_quality_policy'])
    calendar_config = read(root / EVIDENCE / 'calendar.json')
    calendars = {}
    for case in cases:
        frame = frames[case['symbol']]
        first, last = case['cycles'][0][0], min(len(frame) - 1, case['cycles'][-1][1] + policy['defaults']['tail_sessions'])
        calendars[(case['symbol'], case['fold'])] = check_calendar(frame, first, last, calendar_config)
    for unit in units:
        require(str(frames[unit['symbol']]['date'].iloc[unit['decision']]) == unit['date'], 'Sai decision index T04')
    parent_daily = defaultdict(list)
    for row in json.loads(gzip.decompress((root / FINAL / 'daily_ledgers.json.gz').read_bytes())):
        if row['panel'] == 'main' and row['execution'] == 0:
            parent_daily[(row['symbol'], row['fold'], row['variant'])].append(row)
    sample = read(root / EVIDENCE / 'sample_audit.json')
    flags = {r['unit_id']: r['hvn_status_review'] for r in sample['units']}
    affected_scopes = {(r['symbol'], r['fold']) for r in sample['units'] if r['hvn_status_review']}
    accounts, events, statuses = [], [], Counter()
    daily_buffer = io.BytesIO()
    reference_count, reference_days, oracle_days = 0, 0, 0
    fields = ['scenario', 'symbol', 'fold', 'variant', 'date', 'settled_cash_vnd', 'pending_cash_vnd', 'shares',
              'stock_mtm_vnd', 'settled_shares', 'unsettled_shares', 'equity_vnd', 'held_during_session', *COSTS]
    with gzip.GzipFile(fileobj=daily_buffer, mode='wb', mtime=0) as compressed:
        with io.TextIOWrapper(compressed, encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
            writer.writeheader()
            for chosen in policy['scenarios']:
                config = {**policy['defaults'], **chosen}
                for case in cases:
                    symbol, fold, variant = (case[k] for k in ('symbol', 'fold', 'variant'))
                    key = {'scenario': chosen['id'], 'symbol': symbol, 'fold': fold, 'variant': variant}
                    frame = frames[symbol]
                    result = execution_ledger(frame, case['cycles'], config, protocol['initial_capital_vnd'], policy['price_multiplier'])
                    oracle_days += audit_ledger(frame, result, config, protocol['initial_capital_vnd'],
                                                policy['price_multiplier'], calendars[(symbol, fold)])
                    summary, parent = result['summary'], case['reference']
                    if chosen['id'] == 'reference':
                        for metric in ('net_return_pct', 'daily_close_drawdown_pct', 'order_count', *COSTS[:2]):
                            near(summary[metric], parent[metric], str(key) + '/' + metric)
                        expected_days = parent_daily[(symbol, fold, variant)]
                        require(bool(expected_days), 'Thiếu daily reference T04')
                        for actual, expected in zip(result['daily'], expected_days):
                            require(actual['date'] == expected['date'], 'Lệch ngày reference')
                            for metric in ('equity_vnd', 'held_during_session', *COSTS[:2]):
                                near(actual[metric], expected[metric], 'daily reference/' + metric)
                            reference_days += 1
                        require(len(result['daily']) >= len(expected_days), 'Thiếu daily reference')
                        for row in result['daily'][len(expected_days):]:
                            near(row['equity_vnd'], expected_days[-1]['equity_vnd'], 'reference tail phải flat')
                        reference_count += 1
                    accounts.append({**key, 'n_units': case['n_units'], **summary,
                        'hvn_status_review': (symbol, fold) in affected_scopes,
                        'reference_net_return_pct': parent['net_return_pct'],
                        'difference_from_reference_pp': summary['net_return_pct'] - parent['net_return_pct']})
                    for event in result['events']:
                        maturity = (settlement(event['date'], 2,
                                               calendars[(symbol, fold)]) if event['status'] == 'filled' else None)
                        events.append({**key, **event, 'hvn_unit_status_review': flags.get(event['unit_id']),
                                       'hvn_scope_status_review': (symbol, fold) in affected_scopes,
                                       'legal_t2_maturity_date': maturity, 'execution_certified': False})
                        statuses[event['status']] += 1
                    writer.writerows({**key, **row} for row in result['daily'])
                print(f"Đã đối soát {chosen['id']}: 510 accounts.", flush=True)
    groups = []
    for scenario in policy['scenarios']:
        for variant in (*VARIANTS, HOLD):
            selected = [r for r in accounts if r['scenario'] == scenario['id'] and r['variant'] == variant]
            require(len(selected) == 51, 'Sai mẫu số mean accounts')
            groups.append({'scenario': scenario['id'], 'variant': variant, 'n_accounts': 51,
                'n_units': 102, 'n_planned_cycles': sum(r['n_planned_cycles'] for r in selected),
                'mean_account_net_return_pct': float(np.mean([r['net_return_pct'] for r in selected])),
                'mean_daily_close_drawdown_pct': float(np.mean([r['daily_close_drawdown_pct'] for r in selected])),
                'mean_difference_from_reference_pp': float(np.mean([r['difference_from_reference_pp'] for r in selected])),
                'buy_fills': sum(r['n_buy_fills'] for r in selected), 'sell_fills': sum(r['n_sell_fills'] for r in selected),
                'blocked_attempts': sum(r['n_blocked_attempts'] for r in selected),
                'residual_stock_accounts': sum(not r['terminal_is_liquidated'] for r in selected),
                'pending_cash_accounts': sum(r['final_pending_cash_vnd'] > 1e-5 for r in selected),
                **{k: float(sum(r[k] for r in selected)) for k in COSTS}})
    require(reference_count == 510 and len(accounts) == 6120, 'Không đủ scenario/account family')
    keyed = {(r['scenario'], r['symbol'], r['fold'], r['variant']): r for r in accounts}
    for case in cases:
        suffix = tuple(case[k] for k in ('symbol', 'fold', 'variant'))
        lo, ref, hi = [keyed[(s, *suffix)]['net_return_pct'] for s in ('lower_cost', 'reference', 'higher_cost')]
        require(hi - 1e-9 <= ref <= lo + 1e-9, 'Sai thứ tự fixed-fill cost')
    report = {'schema_version': 'execution_final_v1', 'analysis_timing': 'Sensitivity mô tả sau inference T04, không confirmatory.',
        'parent_hashes_verified': parent_counts, 'n_market_units': 102, 'n_prediction_rows_unchanged': 918,
        'n_scenarios': 12, 'n_account_executions': len(accounts), 'n_reference_accounts_reconciled': reference_count,
        'n_reference_daily_rows_reconciled': reference_days, 'n_oracle_daily_rows_reconciled': oracle_days,
        'n_event_records': len(events), 'event_status_counts': dict(statuses), 'new_api_jobs': 0, 'new_predictions': 0,
        'n_hvn_unit_reviews': sum(v is not None for v in flags.values()),
        'n_hvn_scope_reviews': len(affected_scopes), 'n_execution_certified_fills': 0,
        'support': '51 symbol–block accounts/variant, mỗi account 50 triệu VND riêng; mean không là portfolio. Hold có một cycle/account, không là always-LONG hai cycles.',
        'calendar': 'T18 đã đối soát observed bars trong toàn cửa sổ entry–tail; oracle kiểm maturity theo ngày VSD/VSDC cho mọi fill. Ngoài snapshot giữ pending theo policy cũ, không sinh bar/giá.',
        'reference_window': 'So daily T04 tới planned exit; tail tối đa năm observed bars chỉ nối cash/settlement/MTM, giới hạn bởi snapshot. Reference tail phải flat.',
        'cycle_spacing_observed_sessions': sorted({s[1]['decision'] - s[0]['decision'] for s in scopes.values()}),
        'target': 'Giữ nguyên Open[t+1] → Close[t+3] net và SHORT=CASH. L=3 là horizon cố định, không claim tối ưu; không tạo L=5/10.',
        'limits': ['Tái dùng đầy đủ assumptions/giới hạn T18; policy gốc giữ nguyên byte và những mục unverified lịch sử.',
                   'Tiền về chiều T+2 không dùng ở open sáng đó; stock maturity được kiểm trước close SELL.',
                   'HVN giữ mọi unit/scenario, cờ cần kiểm không phải failed fill được xác nhận. Bar phase không là giờ khớp.',
                   'Zero-volume/flat OHLC là proxy ex-post; không đo queue/partial fill. Không chọn tham số theo outcomes.',
                   'Volume units, giá ×1000 và corporate-action adjustment/eligibility chưa xác minh; cap/quantity chỉ có điều kiện.',
                   'Phí/slippage/15% ACT365 là tham số; sell_charge_10bp xét cá nhân cư trú giả định, reference chưa sau mọi thuế.',
                   'Envelope và all_entries_missed không là worst/best mathematical bounds hoặc chứng minh alpha/profitability.']}
    table = ['| Scenario | B mean return (%) | AS mean return (%) | AS − reference (pp) | AS BUY | AS residual |',
             '|---|---:|---:|---:|---:|---:|']
    for scenario in policy['scenarios']:
        values = {r['variant']: r for r in groups if r['scenario'] == scenario['id']}
        b, a = values['B'], values['AS']
        table.append(f"| {scenario['id']} | {b['mean_account_net_return_pct']:.6f} | {a['mean_account_net_return_pct']:.6f} | {a['mean_difference_from_reference_pp']:.6f} | {a['buy_fills']} | {a['residual_stock_accounts']} |")
    note = ('# Execution sensitivities trên predictions T04\n\n' + '\n'.join(table) + '\n\n'
        'Mỗi mean gồm 51 tài khoản symbol–block riêng, không phải portfolio; AS − reference là thay đổi kinh tế do scenario, không là predictive lift AS−B. '
        'Cả 12 scenarios, chín classifiers và continuous hold được giữ trong CSV. Hold có 51 cycles, classifiers có 102 cycles; không gán classification scores mới. '
        'Target/predictions/labels không đổi. Kết quả mô tả sau inference; không chứng nhận execution hoặc profitability.\n\n'
        'Lịch và giới hạn nguồn theo T18: [báo cáo căn cứ](../execution_evidence_v1/report.md). '
        'Giữ 10 cờ unit HVN, không tự đổi thành CASH hoặc áp một chế độ phiên cho toàn giai đoạn. '
        'Maturity thuộc chiều T+2; clock_time null. Đơn vị Volume/hệ số giá/corporate actions chưa đủ provenance, '
        'nên lot/cap là giả định điều kiện. all_entries_missed không là cận dưới toán học. '
        'Reference chưa bao gồm mọi thuế; sell_charge_10bp tách riêng theo giả định cá nhân cư trú. '
        'Không thay code/policy/ledger lịch sử, không ghi paper/, không fit hoặc gọi API.\n\n'
        'L=3 chỉ là ba observed bars gồm entry, tương đương exit sau entry hai phiên; close chỉ phù hợp settlement nếu được phân bổ và khớp lệnh. '
        'Không có so sánh horizon để kết luận tối ưu. Hai cutoffs/account cách nhau 57 observed sessions nên kết quả pending/on-demand trên mẫu này '
        'ít kiểm tra được nhu cầu tái dùng tiền nhanh. Tail cố định tối đa năm bars; residual shares được MTM, pending receivables thuộc wealth. '
        'report.json ghi các kiểm tra nguồn, reference từng dòng và oracle cash/shares/fees/maturity; logs là mô phỏng. '
        'R15 còn action bản thảo/response và locators sau gate hệ thống.\n')
    outputs = {'policy.json': json_bytes(policy), 'report.json': json_bytes(report),
               'account_results.csv': csv_bytes(accounts), 'scenario_summary.csv': csv_bytes(groups),
               'events.csv': csv_bytes(events), 'daily_ledger.csv.gz': daily_buffer.getvalue(), 'report.md': note.encode('utf-8')}
    return outputs, sources


def build_release(root: Path, output: Path) -> dict:
    """Tính/kiểm đầy đủ trước khi tạo release mới; không ghi đè bằng chứng."""
    output = output_path(root, output)
    require(not output.exists(), 'Không ghi đè release T19 đã có')
    with StudyLock(root / 'tmp/execution_final.lock'), offline_guard():
        outputs, sources = generate(root)
        check_parents(root)
        verify_hashes(root, sources)
        output.mkdir()
        for name, data in outputs.items():
            with (output / name).open('xb') as handle:
                handle.write(data)
        manifest = {'schema_version': 'execution_final_manifest_v1', 'runtime': runtime(), 'sources': sources,
                    'outputs': [{'path': name, 'sha256': sha(output / name)} for name in outputs]}
        manifest['sha256'] = hashlib.sha256(json_bytes(manifest)).hexdigest()
        (output / 'manifest.json').write_bytes(json_bytes(manifest))
    return read(output / 'report.json')


def check_release(root: Path, output: Path) -> dict[str, int]:
    """Chỉ kiểm runtime/nguồn/parents/output; không tính lại sensitivity hoặc gọi API."""
    output = output_path(root, output)
    with offline_guard():
        require(read(output / 'manifest.json')['runtime'] == runtime(), 'Runtime khác receipt T19')
        count = check_manifest(root, output)
        return {'T19': count, **check_parents(root)}
