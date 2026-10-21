"""Xuất hình và bảng holdout từ bằng chứng đã nghiệm thu, không thay kết quả nghiên cứu."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np

from core.candidate_selection import read_technical_gates
from core.historical_signals import digest
from core.improvement_bootstrap import bootstrap_report, read_bootstrap
from core.improvement_holdout import NAMESPACE, _bound_files, code_identity, sha
from core.research_cohort import read_envelope
from core.research_input_lock import runtime_identity
from scripts.verify_improvement_holdout import read_verification, verification_artifact

VERSION = 'improvement_holdout_publication_v1'
DESTINATION = 'docs/figures/holdout_v1'
SOURCE = 'scripts/export_improvement_holdout.py'
SYMBOLS = ('FPT', 'MWG', 'VCB', 'VNM')
LABELS = {'original': 'Original', 'bayesian': 'Bayesian v1', 'C2': 'C2',
    'A_tp_pool': 'A (full)', 'A_tp_pool_stats_only': 'A (stats)',
    'A_tp_pool_examples_only': 'A (examples)'}
PRIMARY = 'A_tp_pool'


def load_inputs(root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Chặn nguồn/receipt/checkpoint/audit bị thay trước khi xuất hoặc kiểm tài liệu."""
    base = root/NAMESPACE; run = base/'run'
    paths = [base/'plan.json', base/'release.json', run/'report.json',
        run/'verification.json', run/'bootstrap.json', root/'outputs/oos_pilot/api_usage.json']
    plan, report = read_envelope(paths[0]), read_envelope(paths[2])
    if plan['code_sha256'] != code_identity() or plan['runtime'] != runtime_identity():
        raise ValueError('Code/runtime khác bằng chứng holdout đã khóa')
    gates_path = root/'docs/plan/week8/validation_gates/bound_holdout_v1/technical_gates.json'
    gates = read_technical_gates(gates_path, plan)
    read_verification(paths[3], verification_artifact(plan, report, gates, root=root))
    ledger = json.loads(paths[5].read_text(encoding='utf-8'))
    by_id = {row['id']: row for row in ledger['requests']}
    if len(by_id) != len(ledger['requests']):
        raise ValueError('Ledger trùng HTTP ID')
    _bound_files(root, report, run, by_id)
    for name, checksum in report['binding']['sources'].items():
        if sha(root/name) != checksum:
            raise ValueError('Nguồn khoa học khác report đã nghiệm thu')
    bootstrap = read_bootstrap(paths[4], bootstrap_report(plan, report, sha(paths[2])))
    if bootstrap['status'] != 'COMPLETE':
        raise ValueError('Chưa đủ bootstrap hợp lệ để xuất kết quả xác nhận')
    checkpoints = {}
    for path in (run/'decisions').rglob('*.json'):
        cp = read_envelope(path); key = (cp['point_id'], cp['branch_id'])
        if key in checkpoints:
            raise ValueError('Checkpoint trùng point/nhánh')
        checkpoints[key] = cp
    points = {}
    for path in (run/'points').glob('*.json'):
        point = read_envelope(path)
        if point['point_id'] in points:
            raise ValueError('Point shared trùng ID')
        points[point['point_id']] = point
    ids = {row['point_id'] for row in plan['schedule']}
    if set(points) != ids or set(checkpoints) != {(pid, name) for pid in ids for name in plan['matrix']}:
        raise ValueError('Point/checkpoint thiếu hoặc thừa lịch đã khóa')
    hashes = {str(path.relative_to(root).as_posix()): sha(path) for path in [*paths, gates_path]}
    return {'plan': plan, 'report': report, 'bootstrap': bootstrap, 'ledger': ledger,
        'checkpoints': checkpoints, 'points': points}, hashes


def analyse(data: dict[str, Any]) -> dict[str, Any]:
    """Giữ đủ nhánh, mẫu số, nhóm rỗng và mọi bất đồng; không phân rã D thành cycle gain."""
    report = data['report']; names = report['matrix']
    cases = {name: {c['point_id']: c for c in report['cases'][name]} for name in names}
    bound = {k[5:] for k in report['binding']['checkpoint_sha256'] if k.startswith('http:')}
    bodies: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in data['ledger']['requests']:
        audit = row.get('improvement_audit') or {}; slot = audit.get('slot')
        if row['id'] in bound and slot is not None and row.get('status') == 200:
            bodies[slot['point_id'], slot['branch_id']].append(audit['request']['canonical_body_sha256'])
    performance, coverage, stock_coverage, points, disagreements, subgroups, off = [], [], [], [], [], [], []
    visibility = {n: Counter(dict.fromkeys(('both', 'stats', 'examples', 'off'), 0)) for n in names}
    for symbol in SYMBOLS:
        stock = report['stocks'][symbol]
        for name in names:
            metric = stock['metrics'][name]
            performance.append({'symbol': symbol, 'branch': name, **metric})
            stock_coverage.append({'symbol': symbol, 'branch': name, **stock['coverage'][name]})
        groups = [('time', n, g) for n, g in stock['time_groups'].items()]
        groups += [('regime', n, g) for n, g in stock['regimes'].items()]
        for family, name, group in groups:
            contrast = group['contrasts'][PRIMARY+'__original']
            subgroups.append({'symbol': symbol, 'family': family, 'group': name,
                'count': contrast['count'], 'delta_return_pp': contrast['delta_return_pp'],
                'delta_mdd_pp': contrast['delta_mdd_pp'], 'status': contrast['status']})
        for point in stock['points']:
            pid = point['point_id']; a = cases[PRIMARY][pid]; original = cases['original'][pid]
            view = point['prior'][PRIMARY]
            raw = data['points'][pid]
            points.append({'point_id': pid, 'symbol': symbol, 'date': point['as_of_date'],
                'exit_date': a['economic_outcome']['exit_date'], 'regime': point['regime'],
                'stats_ready': view['stats_ready'], 'examples_ready': view['examples_ready'],
                'prior_visible': a['prior_visible'],
                'news_reliable': raw['source_proof']['news']['is_reliable'],
                'net_return_long': a['economic_outcome']['net_return_long'],
                'actions': {n: cases[n][pid]['execution_action'] for n in names}})
            for name in names:
                prior = point['prior'][name]
                state = ('both' if prior['visible_metric_ids'] and prior['visible_example_ids'] else
                    'stats' if prior['visible_metric_ids'] else 'examples' if prior['visible_example_ids'] else 'off')
                visibility[name][state] += 1
            if a['raw_action'] != original['raw_action']:
                disagreements.append({'point_id': pid, 'symbol': symbol, 'date': point['as_of_date'],
                    'regime': point['regime'], 'prior_visible': a['prior_visible'],
                    'action_a': a['execution_action'], 'action_original': original['execution_action'],
                    'net_return_long_pp': 100.*a['economic_outcome']['net_return_long'],
                    'delta_cycle_return_pp': 100.*(a['cycle_net_return']-original['cycle_net_return'])})
    for name in names:
        rows = [x for x in stock_coverage if x['branch'] == name]
        keys = ('planned', 'complete', 'pending', 'failed', 'unknown', 'missing_result', 'stats_ready',
            'examples_ready', 'prior_visible_count', 'prior_off_count', 'fallback_count')
        coverage.append({'branch': name, **{k: sum(r[k] for r in rows) for k in keys},
            'visibility': dict(visibility[name]),
            'reason_counts': dict(sum((Counter(r['reason_counts']) for r in rows), Counter()))})
    for name in names[1:]:
        counts = Counter(dict.fromkeys(('off', 'prompt_equal', 'canonical_equal', 'action_diff',
            'identical_request_action_diff'), 0)); mismatch_ids = []
        for pid, case in cases[name].items():
            if case['prior_visible']:
                continue
            a, b = (data['checkpoints'][pid, n] for n in (name, 'original'))
            if not bodies[pid, name] or not bodies[pid, 'original']:
                raise ValueError('Thiếu HTTP audit thành công cho so prior-off')
            if a['shared_sha256'] != b['shared_sha256']:
                raise ValueError('Prior-off không chung upstream')
            prompt = a['prompt_sha256'] == b['prompt_sha256']
            body = sorted(bodies[pid, name]) == sorted(bodies[pid, 'original'])
            counts.update(off=1, prompt_equal=int(prompt), canonical_equal=int(body))
            if case['raw_action'] != cases['original'][pid]['raw_action']:
                counts['action_diff'] += 1
                counts['identical_request_action_diff'] += int(prompt and body)
                mismatch_ids.append(pid)
        off.append({'branch': name, **dict(counts), 'mismatch_ids': sorted(mismatch_ids),
            'reason': None if counts['off'] else 'NO_PRIOR_OFF_SUPPORT'})
    trace = dict(Counter(c['trace']['status'] for cs in cases.values() for c in cs.values()))
    paired = {}
    for group in ('ALL', 'VISIBLE', 'OFF'):
        selected = [p for p in points if group == 'ALL' or p['prior_visible'] == (group == 'VISIBLE')]
        matrix = Counter((p['actions'][PRIMARY], p['actions']['original']) for p in selected)
        paired[group] = {'count': len(selected), 'actions': {'__'.join(pair): matrix[pair] for pair in
            (('LONG', 'LONG'), ('LONG', 'CASH'), ('CASH', 'LONG'), ('CASH', 'CASH'))}}
    return {'analysis_version': VERSION, 'matrix': names, 'performance': performance, 'coverage': coverage,
        'stock_coverage': stock_coverage, 'points': sorted(points, key=lambda p: (p['date'], p['symbol'])),
        'disagreements': sorted(disagreements, key=lambda p: (p['date'], p['symbol'])),
        'subgroups': subgroups, 'prior_off_audit': off, 'paired_actions': paired,
        'trace': trace, 'leave_one_symbol_out': report['leave_one_symbol_out'],
        'regime_counts': {n: sum(p['regime'] == n for p in points) for n in
            ('BULL', 'BEAR', 'CHOPPY', 'CONSOLIDATION')},
        'news_reliable_count': sum(p['news_reliable'] for p in points),
        'both_ready': sum(p['stats_ready'] and p['examples_ready'] for p in points),
        'ablation_both_ready': {s: report['stocks'][s]['ablation_both_ready'] for s in SYMBOLS},
        'prior_off_accounts': {s: report['stocks'][s]['prior_off'][PRIMARY+'__original'] for s in SYMBOLS},
        'bootstrap': data['bootstrap']}


def number(value: Any, digits: int = 3) -> str:
    """Giữ null tường minh, không đổi thiếu mẫu thành số 0."""
    return '--' if value is None else f'{value:.{digits}f}'


def tex(value: Any) -> str:
    """Escape ký tự dữ liệu, giữ nguyên tiếng Việt để biên dịch bằng XeLaTeX."""
    return ''.join({'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '_': r'\_',
        '#': r'\#', '$': r'\$', '{': r'\{', '}': r'\}'}.get(c, c) for c in str(value))


def table(headers: list[str], rows: list[list[Any]], caption: str, label: str, note: str = '') -> str:
    """Sinh bảng booktabs có nhãn/mẫu số và chú thích riêng ngoài khối resize."""
    content = '\n'.join(' & '.join(tex(x) for x in row)+r' \\' for row in rows)
    text_columns = {'Mã', 'Nhánh', 'Nhóm', 'Contrast', 'Point', 'Regime', 'Prior A',
        'A', 'Original', 'Kết luận', 'Bỏ mã'}
    alignment = ''.join('l' if h in text_columns else 'r' for h in headers)
    return ('\\begin{table}[htbp]\n\\centering\n\\caption{'+tex(caption)+'}\n\\label{tab:holdout_'+label+'}\n'
        '\\begingroup\\small\\setlength{\\tabcolsep}{6pt}\\sbox0{\\begin{tabular}{'+alignment+'}\n\\toprule\n'
        +' & '.join(tex(h) for h in headers)+r' \\'+'\n\\midrule\n'+content+'\n\\bottomrule\n\\end{tabular}}\n'
        +'\\ifdim\\wd0>\\linewidth\\relax\\resizebox{\\linewidth}{!}{\\usebox0}\\else\\usebox0\\fi\\par\\endgroup\n'
        +'\\par\\smallskip{\\footnotesize '+tex(note)+'}\n\\end{table}\n')


def tables(a: dict[str, Any]) -> dict[str, str]:
    """Xuất đủ hiệu quả, inference, visibility, nhóm rỗng, prior-off và bảy ca bất đồng."""
    rows = []
    for p in a['performance']:
        m = p['account_metrics']
        rows.append([p['symbol'], LABELS[p['branch']], p['sample_count'], number(m['total_return_pct']),
            number(m['max_drawdown_pct']), p['long_count'], p['cash_count'],
            number(p['accuracy']*100), number(None if p['balanced_accuracy'] is None else p['balanced_accuracy']*100)])
    output = {'performance.tex': table(['Mã', 'Nhánh', 'n', 'R (%)', 'MDD (%)', 'LONG', 'CASH', 'Đúng (%)', 'BA (%)'],
        rows, 'Hiệu quả của đủ sáu nhánh trên từng mã', 'performance',
        'Mỗi mã 16 điểm; tài khoản riêng 50 triệu. SHORT=CASH; phí và slippage ở cả hai chiều. BA: balanced accuracy.')}
    b = a['bootstrap']['blocks']['4']; rows = []
    for name, c in b['contrasts'].items():
        left, right = name.split('__')
        rows.append([LABELS[left]+' - '+LABELS[right], number(c['point_estimate_pp']),
            number(c['confidence_level']*100, 2), '['+number(c['ci'][0])+'; '+number(c['ci'][1])+']', c['interpretation']])
    output['inference.tex'] = table(['Contrast', 'D (đpt)', 'Mức CI (%)', 'CI (đpt)', 'Kết luận'], rows,
        'Inference đã đăng ký: primary và bốn secondary', 'inference',
        'Block cutoff L=4, 10.000 draw; primary CI95%, secondary CI98,75% Bonferroni. CI điều kiện trên method/Decision đã lưu.')
    rows = [[LABELS[p['branch']], p['complete'], p['stats_ready'], p['examples_ready'],
        p['prior_visible_count'], p['prior_off_count'], p['fallback_count']] for p in a['coverage']]
    output['coverage.tex'] = table(['Nhánh', 'n', 'Stats ready', 'Examples ready', 'Visible', 'Off', 'Fallback'],
        rows, 'Coverage và readiness trên toàn G', 'coverage',
        'n=64/nhánh. Ready là trạng thái support; visible là nội dung thực sự được render. Không xem visibility là prior-use.')
    rows = [[p['symbol'], LABELS[p['branch']], p['stats_ready'], p['examples_ready'],
        p['prior_visible_count'], p['prior_off_count']] for p in a['stock_coverage'] if p['branch'] in ('C2', PRIMARY)]
    output['coverage.tex'] += table(['Mã', 'Nhánh', 'Stats ready', 'Examples ready', 'Visible', 'Off'],
        rows, 'Đối chiếu support C2 và A trên từng mã', 'stock_coverage', 'Mẫu số 16 điểm/mã, giữ cả fallback.')
    groups = []
    for family, names in [('time', ('Q1', 'Q2', 'Q3', 'Q4', 'H1', 'H2')),
                           ('regime', ('BULL', 'BEAR', 'CHOPPY', 'CONSOLIDATION'))]:
        rows = []
        for name in names:
            row = [name]
            for s in SYMBOLS:
                item = next(p for p in a['subgroups'] if (p['family'], p['group'], p['symbol']) == (family, name, s))
                row.append(number(item['delta_return_pp'])+' (n='+str(item['count'])+')')
            rows.append(row)
        groups.append(table(['Nhóm', *SYMBOLS], rows, 'ΔR A - Original theo '+('thời gian' if family == 'time' else 'regime'),
            'groups_'+family, 'Mỗi ô: đpt (n); tái khởi tạo vốn trong từng nhóm. -- là không có mẫu, không là return 0. Chỉ mô tả.'))
    rows = [[s, number(a['leave_one_symbol_out'][s])] for s in SYMBOLS]
    groups.append(table(['Bỏ mã', 'Mean ΔR ba mã còn lại (đpt)'], rows, 'Leave-one-symbol-out mô tả', 'loso',
        'Không chọn lại ứng viên hoặc kiểm định thêm theo subgroup.'))
    output['subgroups.tex'] = '\n'.join(groups)
    rows = [[LABELS[x['branch']], x['off'], x['prompt_equal'], x['canonical_equal'],
        x['identical_request_action_diff']] for x in a['prior_off_audit']]
    output['attribution.tex'] = table(['Nhánh', 'Off', 'Prompt bằng', 'Body bằng', 'Action khác dù request bằng'],
        rows, 'Kiểm request prior-off với Original', 'prior_off',
        'So UTF-8 prompt và multiset hash JSON canonical của HTTP200 thuộc attempt đã bind; không khẳng định raw byte/header. Không suy causal attribution.')
    rows = [[name, value['count'], *value['actions'].values()] for name, value in a['paired_actions'].items()]
    output['attribution.tex'] += table(['Nhóm', 'n', 'LONG/LONG', 'LONG/CASH', 'CASH/LONG', 'CASH/CASH'], rows,
        'Bảng action ghép cặp: A / Original', 'paired',
        'Hai ô chéo là bất đồng action. ALL=64, VISIBLE và OFF được xác định từ prefix A, không chọn theo return.')
    rows = [[s, g['count'], number(g['delta_return_pp']), number(g['delta_mdd_pp'])]
        for s, g in a['prior_off_accounts'].items()]
    output['attribution.tex'] += table(['Mã', 'n off', 'ΔR (đpt)', 'ΔMDD (đpt)'], rows,
        'Tài khoản mô tả trên riêng prior-off', 'off_accounts',
        'Tái khởi tạo vốn trong tập con; không cộng subgroup return thành primary D.')
    rows = []
    for s, groups in a['ablation_both_ready'].items():
        stats, examples = groups['_stats_only'], groups['_examples_only']
        rows.append([s, stats['count'], number(stats['delta_return_pp']), number(examples['delta_return_pp'])])
    output['attribution.tex'] += table(['Mã', 'n cả hai ready', 'Full - stats (đpt)', 'Full - examples (đpt)'], rows,
        'Ablation mô tả trên T cùng stats/examples ready', 'both_ready',
        'T nhỏ, không là kiểm định xác nhận mới. G đầy đủ đã dùng CI secondary theo protocol.')
    rows = [[p['point_id'], p['regime'], 'Có' if p['prior_visible'] else 'Off', p['action_a'],
        p['action_original'], number(p['net_return_long_pp']), number(p['delta_cycle_return_pp'])]
        for p in a['disagreements']]
    output['disagreements.tex'] = table(['Point', 'Regime', 'Prior A', 'A', 'Original', 'Net LONG (%)', 'Δcycle (đpt)'],
        rows, 'Toàn bộ điểm A khác action Original', 'disagreements',
        'Δcycle chỉ là chênh return vòng đơn lẻ, không là đóng góp cộng được vào D tài khoản. Giữ đủ ca có lợi và bất lợi.')
    return output


def render_figures(a: dict[str, Any], output: Path) -> list[str]:
    """Vẽ dữ liệu nguồn bằng Matplotlib; SVG vector và PNG 300 DPI có byte tái lập."""
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'svg.hashsalt': VERSION,
        'svg.fonttype': 'path', 'axes.spines.top': False, 'axes.spines.right': False})
    names = a['matrix']; files = []
    def save(fig: Any, name: str) -> None:
        for extension in ('svg', 'png'):
            path = output/(name+'.'+extension)
            fig.savefig(path, dpi=300, metadata={'Date': None} if extension == 'svg' else {'Software': VERSION},
                facecolor='white')
            files.append(path.name)
        plt.close(fig)
    def heat(ax: Any, values: np.ndarray, title: str, columns: list[str], rows: list[str],
             *, diverging: bool = True) -> None:
        limit = max(float(np.nanmax(np.abs(values))), .01)
        image = ax.imshow(values, cmap='RdBu' if diverging else 'YlOrBr',
            norm=TwoSlopeNorm(0., -limit, limit) if diverging else None, vmin=None if diverging else 0.)
        ax.set_xticks(range(len(columns)), columns, rotation=18, ha='right')
        ax.set_yticks(range(len(rows)), rows); ax.set_title(title, loc='left', pad=12)
        for j in range(values.shape[0]):
            for k in range(values.shape[1]):
                value = values[j, k]
                ax.text(k, j, number(float(value), 2) if np.isfinite(value) else '--', ha='center', va='center',
                    fontsize=9, color='white' if abs(value) > limit*.65 else '#18222e')
        ax.figure.colorbar(image, ax=ax, shrink=.78, pad=.025)
    metrics = {(p['symbol'], p['branch']): p for p in a['performance']}
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.8), layout='constrained')
    for ax, field, title, diverging in zip(axes, ('total_return_pct', 'max_drawdown_pct'),
        ('Return ròng tài khoản (%)', 'Maximum drawdown (%)'), (True, False)):
        heat(ax, np.array([[metrics[s, n]['account_metrics'][field] for n in names] for s in SYMBOLS]),
            title, [LABELS[n] for n in names], list(SYMBOLS), diverging=diverging)
    save(fig, 'performance')
    contrasts = a['bootstrap']['blocks']['4']['contrasts']; fig, ax = plt.subplots(figsize=(10.5, 5.3), layout='constrained')
    for j, (pair, c) in enumerate(contrasts.items()):
        value = c['point_estimate_pp']; lower, upper = c['ci']; color = '#166a9b' if j == 0 else '#64717d'
        ax.errorbar(value, j, xerr=[[value-lower], [upper-value]], fmt='o', color=color, capsize=5, linewidth=2)
    ax.set_yticks(range(len(contrasts)), [LABELS[k.split('__')[0]]+' - '+LABELS[k.split('__')[1]]
        +' ('+number(c['confidence_level']*100, 2)+'%)' for k, c in contrasts.items()])
    ax.invert_yaxis(); ax.axvline(0., color='#a34c36', linestyle='--', linewidth=1.)
    ax.set_xlabel('Chênh return trung bình đều bốn tài khoản (điểm phần trăm)')
    ax.set_title('CI block-bootstrap: primary 95%, secondary Bonferroni 98,75%', loc='left', pad=12)
    ax.grid(axis='x', alpha=.18); save(fig, 'inference')
    fig, ax = plt.subplots(figsize=(11, 5.2), layout='constrained'); left = np.zeros(len(names))
    colors = ('#276b8f', '#75a4c0', '#d7a953', '#dde1e5')
    for state, label, color in zip(('both', 'stats', 'examples', 'off'),
        ('Stats + examples', 'Chỉ stats', 'Chỉ examples', 'Prior off'), colors):
        counts = np.array([p['visibility'][state] for p in a['coverage']])
        ax.barh(range(len(names)), counts, left=left, color=color, label=label)
        for j, count in enumerate(counts):
            if count: ax.text(left[j]+count/2, j, str(count), ha='center', va='center', fontsize=10,
                color='white' if state == 'both' else '#18222e')
        left += counts
    ax.set_yticks(range(len(names)), [LABELS[n] for n in names]); ax.invert_yaxis(); ax.set_xlim(0, 64)
    ax.set_xlabel('Số điểm có nội dung thực sự visible / 64'); ax.set_title('Visibility theo content mode; không là prior-use', loc='left')
    ax.legend(loc='upper center', bbox_to_anchor=(.5, -.16), ncol=4, frameon=False); save(fig, 'coverage')
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained'); colors = plt.get_cmap('tab10').colors
    for ax, symbol in zip(axes.flat, SYMBOLS):
        points = [p for p in a['points'] if p['symbol'] == symbol]
        dates = [datetime.fromisoformat(points[0]['date']), *[datetime.fromisoformat(p['exit_date']) for p in points]]
        for j, name in enumerate(names):
            curve = np.asarray(metrics[symbol, name]['account_metrics']['equity_curve_vnd'])/1e6
            ax.plot(dates, curve, color=colors[j], linewidth=1.5, label=LABELS[name],
                linestyle='-' if j < 4 else '--', drawstyle='steps-post')
        ax.set_title(symbol, loc='left'); ax.set_ylabel('Vốn (triệu VND)'); ax.grid(alpha=.18)
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3)); ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%Y'))
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside upper center', ncol=6, frameon=False)
    fig.supxlabel('Equity tại exit từng chu kỳ; không phải mark-to-market hằng ngày', fontsize=10)
    save(fig, 'equity')
    fig, (ax, right) = plt.subplots(1, 2, figsize=(13, 5.8), layout='constrained')
    groups = ('Q1', 'Q2', 'Q3', 'Q4', 'H1', 'H2')
    heat(ax, np.array([[next(p['delta_return_pp'] for p in a['subgroups'] if
        (p['symbol'], p['family'], p['group']) == (s, 'time', g)) for s in SYMBOLS] for g in groups]),
        'ΔR A - Original theo nhóm (đpt)', list(SYMBOLS), list(groups))
    regimes = list(a['regime_counts']); visible = [sum(p['regime'] == r and p['prior_visible'] for p in a['points']) for r in regimes]
    absent = [a['regime_counts'][r]-v for r, v in zip(regimes, visible)]
    right.barh(regimes, visible, color='#276b8f', label='A visible')
    right.barh(regimes, absent, left=visible, color='#dde1e5', label='A off')
    for j, r in enumerate(regimes): right.text(a['regime_counts'][r]+.5, j, 'n='+str(a['regime_counts'][r]), va='center')
    right.set_xlim(0, 44); right.set_xlabel('Số điểm'); right.set_title('Phân bố regime và visibility A', loc='left')
    right.legend(frameon=False, loc='lower right'); save(fig, 'diagnostics')
    return files


def write_assets(a: dict[str, Any], destination: Path) -> list[str]:
    """Ghi cùng một tập file xác định; khóa chuyển đổi newline Git cho byte bằng chứng."""
    names = render_figures(a, destination)
    for name, content in tables(a).items():
        (destination/name).write_text(content, encoding='utf-8', newline='\n'); names.append(name)
    (destination/'analysis.json').write_text(json.dumps(a, ensure_ascii=False, indent=2, allow_nan=False)+'\n',
        encoding='utf-8', newline='\n')
    (destination/'.gitattributes').write_text('* -text\n', encoding='ascii', newline='\n')
    return [*names, 'analysis.json', '.gitattributes']


def export(root: Path, destination: Path, *, check: bool = False) -> dict[str, Any]:
    """Sinh bundle versioned; từ chối ghi đè hoặc nhận nguồn/ảnh/bảng đã đổi."""
    data, inputs = load_inputs(root); a = analyse(data)
    source_hash = hashlib.sha256((root/SOURCE).read_text(encoding='utf-8').encode()).hexdigest()
    identity = {'publication_version': VERSION, 'sources': inputs, 'exporter_sha256': source_hash, 'analysis_sha256': digest(a)}
    manifest_path = destination/'manifest.json'
    if check or manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if {k: manifest.get(k) for k in identity} != identity:
            raise ValueError('Bundle khác nguồn, exporter hoặc dữ liệu phân tích')
        with TemporaryDirectory() as folder:
            rebuilt = Path(folder); names = write_assets(a, rebuilt)
            if set(names) != set(manifest['files']):
                raise ValueError('Bundle thiếu/thừa hình, bảng hoặc dữ liệu phân tích')
            if any(sha(rebuilt/name) != manifest['files'][name] for name in names):
                raise ValueError('Nội dung xuất bản không khớp dữ liệu vừa tái dựng')
        for name, checksum in manifest['files'].items():
            file = destination/name
            if file.resolve().parent != destination.resolve() or sha(file) != checksum:
                raise ValueError('File xuất bản khác checksum hoặc vượt thư mục')
        return manifest
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Chỉ xuất vào thư mục mới/trống; không ghi đè tài liệu đã có')
    destination.mkdir(parents=True, exist_ok=True)
    names = write_assets(a, destination)
    manifest = {**identity, 'files': {name: sha(destination/name) for name in sorted(names)}}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return manifest


def main() -> None:
    """CLI xuất/check dữ liệu và hình offline, không có đường gọi LLM hoặc đọc key."""
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    manifest = export(ROOT, ROOT/DESTINATION, check=args.check)
    print(json.dumps({'status': 'PASS', 'publication_version': VERSION, 'files': len(manifest['files']),
        'output': str(ROOT/DESTINATION)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
