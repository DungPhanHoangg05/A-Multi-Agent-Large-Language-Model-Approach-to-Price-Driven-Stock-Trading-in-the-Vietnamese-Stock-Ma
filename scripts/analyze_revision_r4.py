"""Audit factorial R4 từ archive đã khóa và chuẩn bị prompt giá trị mới, không gọi API."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from core.revision_common_study import digest, read_json, write_json
from core.revision72_run import checked, signed
from core.revision_r4_factorial import (POLICY, VARIANTS, actual_text, availability,
    controlled_prompt, donor_factors, factor_rows, factorial_statistics, prompt_parts, validate_donor)
from scripts.analyze_revision_r2 import csv_text, json_text, sha
from scripts.analyze_revision_r3 import verify_prior_manuscript
from scripts.finalize_revision_r1 import table
from utils.statistical_tests import binary_classification_metrics

BANK = ROOT/'outputs/revision/r1_72h_bank_v2'
RUN = ROOT/'outputs/revision/r1_72h_run_v2'
R3 = ROOT/'outputs/revision/r3_repeats_v1'
OUTPUT = ROOT/'outputs/revision/r4_audit_v1'
CANDIDATE = ROOT/'outputs/revision/r4_value_bank_v1'


def verify_r3() -> None:
    """Đối soát release R3 và chuỗi R1/R2; nguồn tài liệu cũ đọc từ ZIP lịch sử."""
    verify_prior_manuscript()
    for folder in (R3, ROOT/'outputs/revision/r3_manuscript_v1'):
        m=read_json(folder/'manifest.json')
        archive=zipfile.ZipFile(folder/'sources.zip') if (folder/'sources.zip').exists() else None
        try:
            for r in m['sources']:
                if sha(ROOT/r['path']) != r['sha256']:
                    if archive is None or hashlib.sha256(archive.read(r['path'])).hexdigest()!=r['sha256']:
                        raise ValueError('Nguồn R3 đã thay đổi ngoài source ZIP')
            for r in m['outputs']:
                if sha(folder/r['path'])!=r['sha256']:raise ValueError('Đầu ra R3 đã bị sửa')
        finally:
            if archive:archive.close()


def tensors(lineage: list[dict], units: list[dict], accounts: list[dict]) -> tuple[dict, dict]:
    """Dựng tensor common support bằng nhãn net đã khóa, không coi 3N là độc lập."""
    with (RUN/'analysis/predictions.csv').open(encoding='utf-8',newline='') as f:
        labels={r['unit_id']:r['label_net'] for r in csv.DictReader(f)}
    blocks=sorted({u['fold'] for u in units});index={(r['unit_id'],r['variant'],r['repeat']):r for r in lineage}
    if len(index)!=18*5*3:raise ValueError('Panel không đủ hoặc duplicate execution')
    counts={v:np.zeros((3,len(blocks),4),int) for v in VARIANTS}
    ledger={v:np.zeros((3,len(blocks),2),float) for v in VARIANTS}
    for v in VARIANTS:
        for run in range(3):
            for b,fold in enumerate(blocks):
                part=[u for u in units if u['fold']==fold]
                c=binary_classification_metrics([labels[u['id']] for u in part], [index[(u['id'],v,run)]['prediction'] for u in part])['confusion']
                counts[v][run,b]=[c[k] for k in ('tp','fn','tn','fp')]
                a=[r for r in accounts if r['panel']=='decision' and r['variant']==v and int(r['execution'])==run and r['fold']==fold]
                ledger[v][run,b]=[sum(float(r['net_return_pct']) for r in a),len(a)]
    return counts,ledger


def inventory() -> tuple[dict, list[Path], list[dict]]:
    """Audit 270 raw prompts, 18 donors và 54 paired groups trước khi tạo ứng viên."""
    verify_r3()
    bank=read_json(BANK/'manifest.json')
    if bank['gate']!='factorial':raise ValueError('Sentiment gate không phải factorial')
    units=[next(u for u in bank['units'] if u['id']==uid) for uid in bank['panel']]
    lineage=[r for r in read_json(R3/'decision_lineage.json') if r['panel']=='decision']
    requests={p.name.removesuffix('.request.json'):p for p in RUN.glob('shards/org*/calls/*.request.json')}
    rows,pairs,donors,sources,prepared=[],[],[],[],[]
    parsed={};actual={}
    for r in lineage:
        path=requests[r['request_id']];req=checked(path);text=actual_text(req);parts=prompt_parts(text)
        key=(r['unit_id'],r['variant'],r['repeat']);parsed[key]=parts;actual[key]=(req,path)
        expected_alpha=r['variant'] in ('A','AS','P');expected_sent=r['variant'] in ('S','AS','P')
        if ('alpha' in parts)!=expected_alpha or ('sentiment' in parts)!=expected_sent:raise ValueError('Sai isolation section A/S')
        rows.append({'unit_id':r['unit_id'],'variant':r['variant'],'repeat':r['repeat'],'request_id':r['request_id'],
            'prompt_hash':digest(text),'prompt_chars':len(text),'alpha_present':expected_alpha,'sentiment_present':expected_sent,
            'factor_value_rows':factor_rows(parts.get('alpha','')),'alpha_section':parts.get('alpha'),
            'sentiment_hash':digest(parts.get('sentiment')),'upstream_sections_hash':digest({k:parts[k] for k in ('trend','pattern','indicator')}),
            'upstream_parent_hash':r['upstream_hash'],'node_hashes':';'.join(r['node_hashes'])})
        sources.append(path)
    for rank,u in enumerate(units):
        scope=next(s for s in bank['schedule'] if (s['symbol'],s['fold'])==(u['symbol'],u['fold']))
        selected=int(np.random.default_rng(20261102+int(digest(u['id'])[:8],16)).choice(scope['train']))
        donor_index=u['placebo_donor']
        validate_donor(scope,donor_index,u['decision'])
        if selected!=donor_index:raise ValueError('Donor sai seed map đã khóa')
        ap=BANK/f"features/{u['symbol']}_{u['decision']}.json";dp=BANK/f"features/{u['symbol']}_{donor_index}.json"
        asset,donor=checked(ap),checked(dp);factors=donor_factors(asset,donor);sources.extend([ap,dp])
        if u['verified_articles']<3 or asset['sentiment_data'].get('is_unavailable',True):raise ValueError('Panel có sentiment unavailable')
        mapping=[{'rank':i+1,'current_name':a['name'],'donor_name':d['name'],'same_factor_name':a['name']==d['name'],
            'treatment':{k:a[k] for k in ('value','signal','components')},'placebo':{k:f[k] for k in ('value','signal','components')}}
            for i,(a,d,f) in enumerate(zip(asset['alpha_factors'],donor['alpha_factors'],factors))]
        donors.append({'unit_id':u['id'],'symbol':u['symbol'],'fold':u['fold'],'cutoff':u['date'],'decision_index':u['decision'],
            'donor_index':donor_index,'donor_label_exit_index':donor_index+3,'train_last_index':scope['train'][-1],
            'validation_first_index':scope['validation'][0],'seed':20261102+int(digest(u['id'])[:8],16),
            'mask_equal':availability(asset['alpha_factors'][0]['components'])==availability(donor['alpha_factors'][0]['components']),
            'asset_hash':asset['sha256'],'donor_hash':donor['sha256'],'mapping':mapping})
        for run in range(3):
            part=[r for r in rows if r['unit_id']==u['id'] and r['repeat']==run]
            if len({r['upstream_parent_hash'] for r in part})!=1 or len({r['node_hashes'] for r in part})!=1 or len({r['upstream_sections_hash'] for r in part})!=1:
                raise ValueError('Shared upstream khác giữa factorial variants')
            p={v:parsed[(u['id'],v,run)] for v in VARIANTS}
            if p['A']['alpha']!=p['AS']['alpha'] or p['AS']['sentiment']!=p['S']['sentiment'] or p['P']['sentiment']!=p['AS']['sentiment']:
                raise ValueError('Nội dung alpha/sentiment không cùng giữa nhánh')
            pairs.append({'unit_id':u['id'],'repeat':run,'shared_upstream_and_nodes':True,'same_alpha_A_AS':True,
                'same_sentiment_S_AS_P':True,'same_rules_all':len({p[v]['rules'] for v in VARIANTS})==1,
                'AS_P_alpha_identical':p['AS']['alpha']==p['P']['alpha'],
                'AS_P_prompt_identical':actual_text(actual[(u['id'],'AS',run)][0])==actual_text(actual[(u['id'],'P',run)][0])})
        base=parsed[(u['id'],'AS',0)];prompts={v:controlled_prompt(base,asset,donor,v) for v in VARIANTS}
        prepared.append({'unit':{k:u[k] for k in ('id','symbol','fold','decision','date','verified_articles')},'org':rank%5+1,
            'asset_hash':asset['sha256'],'donor_hash':donor['sha256'],'donor_index':donor_index,
            'original_request_id':actual[(u['id'],'AS',0)][0]['attempt_id'],
            'upstream_parent_hash':next(r['upstream_parent_hash'] for r in rows if r['unit_id']==u['id']),
            'prompts':prompts,'prompt_hashes':{v:digest(t) for v,t in prompts.items()}})
    with (R3/'account_returns.csv').open(encoding='utf-8',newline='') as f:
        accounts=list(csv.DictReader(f))
    stats=factorial_statistics(*tensors(lineage,units,accounts))
    coverage=[]
    for path in sorted(requests.values()):
        req=checked(path);c=req['context']
        if c['stage']!='decision' or c['smoke'] or not path.with_name(path.name.replace('.request.','.response.')).exists():continue
        parts=prompt_parts(actual_text(req));alpha=parts.get('alpha')
        coverage.append({**c,'attempt_id':req['attempt_id'],'alpha_present':alpha is not None,
            'factor_value_rows':factor_rows(alpha or ''),'prompt_chars':len(actual_text(req))})
        sources.append(path)
    if len(coverage)!=474:raise ValueError('Research prompt inventory không đủ 474 successes')
    panel=[{k:u[k] for k in ('id','symbol','fold','date','decision','verified_articles')} for u in units]
    findings={'status':'R4 incomplete: value-bearing matched placebo requires fresh Decision inference',
        'n_units':18,'n_variants':5,'n_executions':3,'n_actual_prompts':len(rows),'n_alpha_prompts':sum(r['alpha_present'] for r in rows),
        'n_alpha_prompts_with_five_factor_rows':sum(r['factor_value_rows']==5 for r in rows),
        'n_pair_groups':len(pairs),'n_identical_AS_P_prompt_pairs':sum(r['AS_P_prompt_identical'] for r in pairs),
        'n_research_successful_decision_prompts':len(coverage),
        'n_research_alpha_prompts':sum(r['alpha_present'] for r in coverage),
        'n_research_alpha_prompts_with_five_rows':sum(r['factor_value_rows']==5 for r in coverage),
        'n_donor_rank_names_mismatched':sum(not m['same_factor_name'] for r in donors for m in r['mapping']),
        'cause':'legacy _distill_report splits on --- inside the Markdown table separator, retaining header and signal consensus but removing numerical factor rows',
        'interpretation':'existing A/AS/P results concern report/consensus presence and perturbation; not a complete factor-value information placebo',
        'missingness':'all selected units have >=3 locally scored articles; scorer/PIT/domain validity unverified; unavailable units are not called sentiment effects',
        'claims':'Full-Base is a bundle contrast; no isolated alpha/sentiment information, synergy, CASH-independent alpha or full-factor placebo validity claim',
        'legacy_interaction':'Full-max(A,S) is best-single improvement, not AS-A-S+B',
        'multiplicity':'old six contrasts were reported previously; exact family preregistration cannot be authenticated from frozen executable protocol; interaction/joint envelope added after old inference',
        'new_run':'270 fresh text Decision calls, no new vision; old results never relabelled as corrected prompts'}
    files={'policy.json':json_text(POLICY),'panel.csv':csv_text(panel),'prompt_audit.csv':csv_text(rows),
        'research_prompt_coverage.csv':csv_text(coverage),
        'paired_isolation.json':json_text(pairs),'donor_map.json':json_text(donors),'contrasts.json':json_text(stats),'findings.json':json_text(findings)}
    body=[]
    for r in stats['contrasts']:
        d=r['summary']['balanced_accuracy'];ci=r['intervals']['balanced_accuracy']['percentile_95'];lr=r['summary']['long_rate']['mean']
        body.append(f"{r['contrast']} & {d['mean']*100:.2f} & {d['sd']*100:.2f} & [{ci[0]*100:.2f}, {ci[1]*100:.2f}] & {lr*100:.2f}"+r' \\')
    files['r4_contrasts.tex']=table('Existing 18-unit report/consensus contrasts, not full factor-value effects (percentage points).','tab:r4_contrasts','lrrrr',
        'Contrast & Mean BA & SD & Descriptive interval & Mean LONG',body,
        'Three paired executions; 10,000 joint block/run draws. BA uses 9,612 finite draws. Interaction is AS-A-S+B, added after inference. Only three blocks/runs; no calibrated coverage or significance claim. Full factor-value rows were absent from all alpha-bearing archived prompts.')
    return files,sources,prepared


def source_paths(extra: list[Path]) -> list[Path]:
    """Nguồn audit/code mới và chuỗi release cũ; không đưa tài liệu hiện hành vào scientific input."""
    paths=[ROOT/p for p in ['core/revision_r4_factorial.py','core/revision_r4_run.py','scripts/analyze_revision_r4.py',
        'scripts/run_revision_r4.py','tests/test_revision_r4_factorial.py','core/revision_r3_repeats.py',
        'outputs/revision/r3_repeats_v1/manifest.json','outputs/revision/r3_manuscript_v1/manifest.json',
        'outputs/revision/r3_manuscript_v1/sources.zip','outputs/revision/r1_72h_bank_v2/manifest.json']]
    paths.extend(R3/r['path'] for r in read_json(R3/'manifest.json')['outputs'])
    return sorted(set(paths+extra))


def analyze_new(manifest: dict, records: list[dict], run: Path, bank: Path = CANDIDATE) -> None:
    """Chỉ xuất khi đủ corrected panel; dựng lại ledger từ prediction mới và giá frozen."""
    from core.revision_baselines import daily_ledger, load_prices
    verify_r3()
    if len(records)!=270:raise ValueError('Corrected panel chưa đủ 270 executions')
    units=[u['unit'] for u in manifest['units']]
    old=read_json(BANK/'manifest.json');protocol=old['protocol']
    frames,_=load_prices(ROOT/protocol['price_snapshot'],protocol['price_quality_policy'])
    lineage=[{**r['context'],'prediction':r['prediction'],'request_ids':r['request_ids'],'parent':r['parent']} for r in records]
    index={(r['unit_id'],r['variant'],r['repeat']):r['prediction'] for r in lineage}
    accounts,daily=[],[]
    for v in VARIANTS:
        for repeat in range(3):
            for symbol,fold in sorted({(u['symbol'],u['fold']) for u in units}):
                part=sorted([u for u in units if (u['symbol'],u['fold'])==(symbol,fold)],key=lambda u:u['decision'])
                ledger=daily_ledger(frames[symbol],[(u['decision']+1,u['decision']+3,int(index[(u['id'],v,repeat)]=='LONG')) for u in part],protocol)
                key={'panel':'decision','variant':v,'execution':repeat,'symbol':symbol,'fold':fold}
                daily.extend({**key,**r} for r in ledger.pop('daily'))
                accounts.append({**key,'n_panel_cycles':len(part),**ledger})
    stats=factorial_statistics(*tensors(lineage,units,accounts))
    files={'report.json':json_text({'status':'corrected value-bearing panel complete; historical exploratory only',
        'n_units':18,'n_executions':270,'metrics':stats,'policy':manifest['policy']}),
        'decision_lineage.json':json_text(lineage),'account_returns.csv':csv_text(accounts),'daily_ledgers.csv':csv_text(daily)}
    output=run/'analysis';existed=output.exists()
    if existed:
        prior=read_json(output/'manifest.json')
        for group,base in [('sources',ROOT),('outputs',output)]:
            for r in prior[group]:
                if sha(base/r['path'])!=r['sha256']:raise ValueError('Analysis R4 đã bị sửa')
    for name,text in files.items():
        if existed:
            if (output/name).read_bytes()!=text.encode('utf-8'):raise ValueError('Analysis R4 không tái lập')
        else:output.mkdir(exist_ok=True);(output/name).write_text(text,encoding='utf-8',newline='\n')
    if not existed:
        sources=[bank/'manifest.json',*sorted(run.glob('shards/org*/decisions/*.json'))]
        sources += [p for p in sorted(run.glob('shards/org*/calls/*.json')) if p.name.endswith(('.request.json','.response.json','.error.json'))]
        m={'sources':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in sources],
           'outputs':[{'path':n,'sha256':sha(output/n)} for n in files]}
        (output/'manifest.json').write_text(json_text(m),encoding='utf-8',newline='\n')
    print('PASS corrected R4: 270 calls, 195 account executions; report/contrasts/ledgers đã xuất hoặc tái lập.')


def main() -> None:
    """--check không ghi đè audit; --prepare chỉ đóng băng prompt, không sinh prediction."""
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');p.add_argument('--prepare',action='store_true');args=p.parse_args()
    if OUTPUT.exists() and not args.check:raise FileExistsError('Audit đã có; dùng --check, thêm --prepare nếu cần')
    if args.check:
        m=read_json(OUTPUT/'manifest.json')
        for group,base in [('sources',ROOT),('outputs',OUTPUT)]:
            for r in m[group]:
                if sha(base/r['path'])!=r['sha256']:raise ValueError('Hash audit R4 đã đổi: '+r['path'])
    files,extra,prepared=inventory()
    for name,text in files.items():
        if args.check:
            if (OUTPUT/name).read_bytes()!=text.encode('utf-8'):raise ValueError('Audit R4 không tái lập: '+name)
        else:
            OUTPUT.mkdir(exist_ok=True);(OUTPUT/name).write_text(text,encoding='utf-8',newline='\n')
        if name.endswith('.tex'):
            target=ROOT/'paper/generated'/name
            if args.check:
                if target.read_bytes()!=text.encode('utf-8'):raise ValueError('Bảng R4 không khớp')
            else:target.write_text(text,encoding='utf-8',newline='\n')
    if not args.check:
        m={'schema_version':'revision_r4_audit_v1','sources':[{'path':x.relative_to(ROOT).as_posix(),'sha256':sha(x)} for x in source_paths(extra)],
           'outputs':[{'path':n,'sha256':sha(OUTPUT/n)} for n in files]}
        (OUTPUT/'manifest.json').write_text(json_text(m),encoding='utf-8',newline='\n')
    if args.prepare:
        from core.revision_r4_run import prepare
        prepare(ROOT,CANDIDATE,prepared,source_paths(extra))
    print(f'PASS audit R4: {len(files)} artifacts; 270 archived prompts; chưa có corrected inference; không gọi API.')


if __name__=='__main__':main()
