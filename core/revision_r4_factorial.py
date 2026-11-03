"""Audit prompt thực và dựng đối chứng giá trị R4; không thay runtime nghiên cứu cũ."""

from __future__ import annotations

from copy import deepcopy
import re

import numpy as np

from core.revision_common_study import digest
from core.revision_r3_repeats import METRICS, array_metrics, describe, interval, weighted_runs

VARIANTS = ('B', 'A', 'S', 'AS', 'P')
CONTRASTS = {
    'AS-B': {'AS': 1, 'B': -1},
    'A-B': {'A': 1, 'B': -1},
    'AS-S': {'AS': 1, 'S': -1},
    'S-B': {'S': 1, 'B': -1},
    'AS-A': {'AS': 1, 'A': -1},
    'AS-P': {'AS': 1, 'P': -1},
    'interaction': {'AS': 1, 'A': -1, 'S': -1, 'B': 1},
}
POLICY = {
    'schema_version': 'revision_r4_value_control_v1',
    'scope': 'new historical exploratory value-control panel; not prospective confirmation',
    'units': 'same frozen 18 sentiment-available units; no outcome-based reselection',
    'executions': '18 units x B/A/S/AS/P x 3 fresh Decision calls = 270; zero new vision calls',
    'primary_metric': 'balanced_accuracy',
    'contrast_family': CONTRASTS,
    'multiplicity': 'seven BA contrasts declared together before new calls; descriptive joint finite-draw max-deviation envelope, no p-values or calibrated family-wise coverage claim; old interaction added after old inference',
    'other_metrics': 'accuracy/MCC/macro-F1/LONG frequency/account return are descriptive secondary endpoints, not additional significance discoveries',
    'placebo': 'one whole past training donor rank-vector, no per-factor independent shuffle; same current names/headings/schema, donor values/signals/skill fields by rank; not name-matched factor covariance',
    'seed': 20261102,
    'reuse': 'only archived upstream reports, numerical assets and donor map; every Decision response is new in this study',
    'prompt': 'five explicit factor rows bypass legacy alpha distillation; same AS/P skeleton and limits, exact token length not asserted',
    'limits': 'three runs/three blocks; coverage-selected panel; unverified served weights/news PIT/domain validity; prompt/consensus and CASH propensity can still confound information claims',
}


def prompt_parts(text: str) -> dict:
    """Tách đúng sections thực gửi API, không nhận câu nhắc alpha trong rules là alpha data."""
    marker = '\n\nTHỨ TỰ ƯU TIÊN BẰNG CHỨNG:'
    if text.count(marker) != 1:
        raise ValueError('Prompt không có đúng một khối rules')
    reports, rules = text.split(marker)
    matches = list(re.finditer(r'### \[(\d)\] ([^\n]+)\n', reports))
    if not matches or [int(m[1]) for m in matches] != list(range(1, len(matches)+1)):
        raise ValueError('Sections prompt thiếu hoặc sai thứ tự')
    names = {'PHÂN TÍCH XU HƯỚNG': 'trend', 'MÔ HÌNH NẾN': 'pattern',
             'CHỈ BÁO KỸ THUẬT': 'indicator', 'ALPHA FACTORS ĐỊNH LƯỢNG': 'alpha',
             'TIN TỨC & TÂM LÝ THỊ TRƯỜNG': 'sentiment'}
    result = {'prefix': reports[:matches[0].start()], 'rules': marker+rules}
    for i, m in enumerate(matches):
        result[names[m[2]]] = reports[m.end():matches[i+1].start() if i+1 < len(matches) else len(reports)].strip()
    if not {'trend', 'pattern', 'indicator'} <= result.keys():
        raise ValueError('Thiếu ba báo cáo upstream')
    return result


def actual_text(request: dict) -> str:
    """Chỉ chấp nhận một human prompt, không âm thầm gộp history khác hợp đồng."""
    messages = request['messages']
    if len(messages) != 1 or len(messages[0]) != 1 or messages[0][0]['type'] != 'human':
        raise ValueError('Request không đúng một human message')
    return messages[0][0]['data']['content']


def availability(value: object) -> object:
    """Mask thiếu giữ nguyên cấu trúc; không coi zero, False hoặc chuỗi rỗng là null."""
    if isinstance(value, dict):
        return {k: availability(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [availability(v) for v in value]
    return value is not None


def donor_factors(asset: dict, donor: dict) -> list[dict]:
    """Giữ tên treatment, thay cùng một vector past theo rank và kiểm mask sâu."""
    factors = deepcopy(asset['alpha_factors'])
    if len(factors) != 5 or len(donor['alpha_factors']) != 5:
        raise ValueError('Cần đúng năm factors ở treatment và donor')
    for current, past in zip(factors, donor['alpha_factors']):
        for key in ('value', 'signal', 'components'):
            if availability(current[key]) != availability(past[key]):
                raise ValueError('Donor khác schema hoặc availability mask')
            current[key] = deepcopy(past[key])
    return factors


def validate_donor(scope: dict, donor: int, decision: int) -> None:
    """Donor và label exit phải nằm trong train đã purge, trước validation/test."""
    if donor not in scope['train'] or donor+3>=scope['validation'][0] or scope['train'][-1]+3>=decision:
        raise ValueError('Donor không thuộc train purged trước cutoff')


def factor_report(factors: list[dict], symbol: str) -> str:
    """Năm dòng giá trị được render trực tiếp, không đi qua splitter markdown legacy."""
    if len(factors) != 5:
        raise ValueError('Báo cáo phải có năm factor rows')
    lines = [f'## 5 Alpha Factor — {symbol}', '| # | Alpha | Giá trị | Tín hiệu | IC | Acc | Score |',
             '| : | : | : | : | : | : | : |']
    for i, f in enumerate(factors, 1):
        c = f['components']
        values = [float(f['value']), float(c['ic']), float(c['composite_score'])]
        if not all(np.isfinite(values)) or f['signal'] not in ('TĂNG', 'GIẢM', 'TRUNG TÍNH'):
            raise ValueError('Factor thiếu giá trị hữu hạn hoặc signal hợp lệ')
        lines.append(f"| {i} | {f['name']} | {values[0]:+.4f} | {f['signal']} | {values[1]:+.4f} | {c['accuracy']} | {values[2]:+.4f} |")
    up = sum(f['signal'] == 'TĂNG' for f in factors)
    down = sum(f['signal'] == 'GIẢM' for f in factors)
    consensus = 'TĂNG' if up > down else 'GIẢM' if down > up else 'TRUNG TÍNH'
    lines.append(f'**TỔNG HỢP: {consensus} ({up} TĂNG / {down} GIẢM / {5-up-down} TRUNG TÍNH)**')
    text = '\n'.join(lines)
    if len(text) > 1800:
        raise ValueError('Alpha block vượt ngân sách 1.800 ký tự; không cắt mất rows')
    return text


def factor_rows(text: str) -> int:
    """Đếm rows có số thứ tự thực, không đếm header hoặc consensus."""
    return len(re.findall(r'^\| [1-5] \| ', text, re.M))


def controlled_prompt(parts: dict, asset: dict, donor: dict, variant: str) -> str:
    """Dùng nguyên upstream/rules; AS/P chỉ khác các scalar và signal trong alpha block."""
    if variant not in VARIANTS:
        raise ValueError('Variant ngoài factorial/placebo đã khóa')
    alpha = variant in ('A', 'AS', 'P')
    sentiment = variant in ('S', 'AS', 'P')
    count = 3 + int(alpha) + int(sentiment)
    prefix = re.sub(r'\d BÁO CÁO:\s*$', f'{count} BÁO CÁO:\n', parts['prefix'])
    if prefix == parts['prefix'] and not prefix.rstrip().endswith(f'{count} BÁO CÁO:'):
        raise ValueError('Không tìm thấy số báo cáo trong prefix')
    reports = [('PHÂN TÍCH XU HƯỚNG', parts['trend']), ('MÔ HÌNH NẾN', parts['pattern']),
               ('CHỈ BÁO KỸ THUẬT', parts['indicator'])]
    if alpha:
        factors = donor_factors(asset, donor) if variant == 'P' else asset['alpha_factors']
        reports.append(('ALPHA FACTORS ĐỊNH LƯỢNG', factor_report(factors, asset['symbol'])))
    if sentiment:
        reports.append(('TIN TỨC & TÂM LÝ THỊ TRƯỜNG', asset['sentiment_report']))
    text = prefix + '\n\n'.join(f'### [{i}] {h}\n{v}' for i, (h, v) in enumerate(reports, 1)) + parts['rules']
    if len(text) >= 6500 or (alpha and factor_rows(prompt_parts(text)['alpha']) != 5):
        raise ValueError('Prompt vượt 6.500 ký tự hoặc mất factor rows; không gọi API')
    return text


def factorial_statistics(counts: dict[str, np.ndarray], accounts: dict[str, np.ndarray]) -> dict:
    """Bảy linear contrasts cùng whole-block/run draws; interaction khác best-single gap."""
    if set(counts) != set(VARIANTS) or set(accounts) != set(VARIANTS):
        raise ValueError('Thiếu một nhánh factorial/placebo')
    # Dùng validator của R3 trước khi tái dùng đúng estimand và quy tắc undefined.
    from core.revision_r3_repeats import resample
    resample(counts, accounts, repeats=1)
    runs, blocks, _ = counts['B'].shape
    rng = np.random.default_rng(20261102)
    bw = rng.multinomial(blocks, np.full(blocks, 1/blocks), 10000)
    rw = rng.multinomial(runs, np.full(runs, 1/runs), 10000)
    scores, samples = {}, {}
    for v in VARIANTS:
        scores[v] = array_metrics(counts[v].sum(axis=1))
        scores[v]['mean_account_net_return_pct'] = accounts[v][..., 0].sum(axis=1) / accounts[v][..., 1].sum(axis=1)
        draws = array_metrics(np.einsum('bk,rkc->brc', bw, counts[v]))
        ret = np.einsum('bk,rkc->brc', bw, accounts[v])
        draws['mean_account_net_return_pct'] = ret[..., 0] / ret[..., 1]
        samples[v] = {m: weighted_runs(a, rw) for m, a in draws.items()}
    results, ba_samples, ba_centers = [], [], []
    for name, weights in CONTRASTS.items():
        values = {m: sum(w*scores[v][m] for v, w in weights.items()) for m in METRICS}
        draws = {m: sum(w*samples[v][m] for v, w in weights.items()) for m in METRICS}
        clean = {m: [float(x) if np.isfinite(x) else None for x in a] for m, a in values.items()}
        results.append({'contrast': name, 'weights': weights, 'by_execution': clean,
                        'summary': {m: describe(a) for m, a in clean.items()},
                        'intervals': {m: interval(a) for m, a in draws.items()}})
        ba_samples.append(draws['balanced_accuracy'])
        ba_centers.append(float(np.mean(values['balanced_accuracy'])))
    joint = np.asarray(ba_samples).T
    finite = np.isfinite(joint).all(axis=1)
    radius = float(np.quantile(np.max(np.abs(joint[finite] - ba_centers), axis=1), .95)) if finite.any() else None
    return {'variants': {v: {'by_execution': {m: [float(x) if np.isfinite(x) else None for x in a] for m,a in scores[v].items()},
                'summary': {m:describe([float(x) if np.isfinite(x) else None for x in a]) for m,a in scores[v].items()},
                'intervals': {m:interval(a) for m,a in samples[v].items()}} for v in VARIANTS},
        'contrasts': results, 'BA_family': {'n_contrasts': len(CONTRASTS),
        'n_joint_finite_draws': int(finite.sum()), 'n_joint_undefined_draws': int((~finite).sum()),
        'max_absolute_deviation_radius': radius,
        'descriptive_envelopes': {name: [c-radius, c+radius] if radius is not None else None for name, c in zip(CONTRASTS, ba_centers)},
        'scope': 'joint finite-draw max-deviation sensitivity envelope; no calibrated simultaneous coverage or significance claim'}}
