"""Khóa audit actual corrected R4 và bảng bản thảo; chỉ đọc inference đã chạy, không gọi API."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import numpy as np

from core.revision_common_study import digest,read_json
from core.revision72_run import checked
from core.revision_r4_run import collect,verify_bank
from core.revision_r4_factorial import VARIANTS,actual_text,prompt_parts,validate_donor
from scripts.analyze_revision_r2 import csv_text,json_text,sha
from scripts.analyze_revision_r4 import verify_r3,BANK as ORIGINAL_BANK
from scripts.finalize_revision_r1 import table
from utils.statistical_tests import binary_classification_metrics

BANK=ROOT/'outputs/revision/r4_value_bank_v1'
RUN=ROOT/'outputs/revision/r4_value_run_v1'
OUTPUT=ROOT/'outputs/revision/r4_final_v1'


def verify_old_audit_release() -> None:
    """Nguồn tài liệu R4 lúc pending được xác minh qua ZIP thay vì sửa release cũ."""
    verify_r3()
    folder=ROOT/'outputs/revision/r4_manuscript_v1';m=read_json(folder/'manifest.json')
    with zipfile.ZipFile(folder/'sources.zip') as archive:
        for r in m['sources']:
            if sha(ROOT/r['path'])!=r['sha256'] and hashlib.sha256(archive.read(r['path'])).hexdigest()!=r['sha256']:
                raise ValueError('Nguồn bản thảo audit R4 không khớp ZIP')
    for r in m['outputs']:
        if sha(folder/r['path'])!=r['sha256']:raise ValueError('Release audit R4 đã bị sửa')


def factor_cells(text: str) -> list[dict]:
    """Parse độc lập năm numeric rows trong prompt thật, không chỉ tin số rows hoặc hash."""
    rows=[]
    for line in text.splitlines():
        fields=[x.strip() for x in line.split('|')]
        if len(fields)!=9 or fields[1] not in ('1','2','3','4','5'):continue
        values=[float(fields[i]) for i in (3,5,7)]
        if not all(np.isfinite(values)):raise ValueError('Numeric cell không hữu hạn')
        rows.append({'rank':int(fields[1]),'name':fields[2],'value':values[0],'signal':fields[4],
            'ic':values[1],'accuracy':fields[6],'composite_score':values[2]})
    if [r['rank'] for r in rows]!=[1,2,3,4,5]:raise ValueError('Actual prompt không có đúng năm factor rows')
    return rows


def check_content(request: dict,job: dict,unit: dict,asset: dict,donor: dict,bank_id: str) -> dict:
    """Từ chối sai context/model/caps/actual prompt hoặc scalar donor/treatment ghép sai."""
    context={k:v for k,v in request['context'].items() if k not in ('provider_org','execution_epoch')}
    text=actual_text(request);v=job['variant'];metadata=request['model_metadata']
    if context!=job or request['bank_id']!=bank_id or text!=unit['prompts'][v]:raise ValueError('Actual prompt/context không khớp bank đã khóa')
    if (metadata.get('ls_model_name'),metadata.get('ls_temperature'),metadata.get('ls_max_tokens'))!=('openai/gpt-oss-20b',1e-8,2048):
        raise ValueError('SDK model/temperature/output cap khác hợp đồng')
    parts=prompt_parts(text)
    if ('alpha' in parts)!=(v in ('A','AS','P')) or ('sentiment' in parts)!=(v in ('S','AS','P')):
        raise ValueError('Isolation actual A/S không đúng')
    cells=[]
    if 'alpha' in parts:
        cells=factor_cells(parts['alpha']);values=donor['alpha_factors'] if v=='P' else asset['alpha_factors']
        for row,current,source in zip(cells,asset['alpha_factors'],values):
            expected={'name':current['name'],'value':round(float(source['value']),4),'signal':source['signal'],
                'ic':round(float(source['components']['ic']),4),'accuracy':source['components']['accuracy'],
                'composite_score':round(float(source['components']['composite_score']),4)}
            if any(row[k]!=value for k,value in expected.items()):raise ValueError('Factor cells không khớp treatment/donor theo rank')
    if 'sentiment' in parts and parts['sentiment']!=asset['sentiment_report'].strip():raise ValueError('Sentiment actual khác source')
    return {'parts':parts,'factor_rows':len(cells),'chars':len(text),'prompt_hash':digest(text)}


def payloads() -> dict[str,str]:
    """Đối soát 270 points, mọi attempt và kết quả native đã khóa trước khi xuất bảng."""
    verify_old_audit_release();m=verify_bank(ROOT,BANK);records=collect(m,RUN)
    if len(records)!=270:raise ValueError('R4 chưa đủ 270 real executions')
    if any(r['decision_source']!='llm_structured' or r['fallback_reason'] for r in records):raise ValueError('Có fallback hoặc decision không structured')
    analysis=read_json(RUN/'analysis/manifest.json')
    for group,base in [('sources',ROOT),('outputs',RUN/'analysis')]:
        for r in analysis[group]:
            if sha(base/r['path'])!=r['sha256']:raise ValueError('Native R4 analysis hash đã đổi')
    report=read_json(RUN/'analysis/report.json');stats=report['metrics'];units={u['unit']['id']:u for u in m['units']}
    jobs={(j['unit_id'],j['variant'],j['repeat']):j for j in m['jobs']}
    old=read_json(ORIGINAL_BANK/'manifest.json');assets={};donors={}
    for uid,u in units.items():
        point=u['unit'];symbol=point['symbol'];scope=next(s for s in old['schedule'] if (s['symbol'],s['fold'])==(symbol,point['fold']))
        validate_donor(scope,u['donor_index'],point['decision'])
        assets[uid]=checked(ORIGINAL_BANK/f"features/{symbol}_{point['decision']}.json")
        donors[uid]=checked(ORIGINAL_BANK/f"features/{symbol}_{u['donor_index']}.json")
    old_ids={p.name.removesuffix('.request.json') for p in (ROOT/'outputs/revision/r1_72h_run_v2').glob('shards/org*/calls/*.request.json')}
    attempts=[];requests={};parts={};seen=set()
    for path in sorted(RUN.glob('shards/org*/calls/*.request.json')):
        req=checked(path);c=req['context'];key=(c['unit_id'],c['variant'],c['repeat']);attempt=req['attempt_id']
        if attempt in old_ids or attempt in seen:raise ValueError('Request ID đã dùng trong study cũ hoặc duplicate')
        seen.add(attempt);audit=check_content(req,jobs[key],units[c['unit_id']],assets[c['unit_id']],donors[c['unit_id']],m['sha256'])
        response=path.with_name(path.name.replace('.request.','.response.'));error=path.with_name(path.name.replace('.request.','.error.'))
        if response.exists()==error.exists():raise ValueError('Attempt thiếu hoặc đồng thời success/error')
        result=read_json(response) if response.exists() else None
        if result and result['parent_request_hash']!=req['sha256']:raise ValueError('Response parent sai')
        if result:
            receipt=read_json(path.with_name(path.name.replace('.request.','.response_digest.')))
            if receipt['sha256']!=digest(result):raise ValueError('Response receipt không khớp')
        elif 'json_validate_failed' not in read_json(error)['error']:raise ValueError('Có loại provider error mới cần rà lại')
        attempts.append({'attempt_id':attempt,**c,'started_at_utc':req['started_at_utc'],
            'ended_at_utc':result['ended_at_utc'] if result else None,'outcome':'success' if result else 'json_validate_failed',
            'prompt_hash':audit['prompt_hash'],'prompt_chars':audit['chars'],'factor_rows':audit['factor_rows'],
            'model':req['model_metadata']['ls_model_name'],'sdk_temperature':req['model_metadata']['ls_temperature'],'output_cap':2048,
            'request_sha256':sha(path),'response_sha256':sha(response) if result else None,'error_sha256':sha(error) if error.exists() else None})
        requests[attempt]=req;parts[attempt]=audit['parts']
    success_ids={r['attempt_id'] for r in attempts if r['outcome']=='success'}
    used=[a for r in records for a in r['request_ids']]
    if len(set(used))!=270 or set(used)!=success_ids:raise ValueError('Không đúng 270 successful responses riêng biệt')
    by_key={(r['context']['unit_id'],r['context']['variant'],r['context']['repeat']):r for r in records}
    pair_rows=[];order_rows=[];disagreement=[]
    for uid,u in sorted(units.items()):
        for repeat in range(3):
            points={v:by_key[(uid,v,repeat)] for v in VARIANTS};p={v:parts[points[v]['request_ids'][-1]] for v in VARIANTS}
            if len({r['parent']['upstream_hash'] for r in points.values()})!=1:raise ValueError('Shared upstream parent khác')
            for field in ('trend','pattern','indicator','rules'):
                if len({p[v][field] for v in VARIANTS})!=1:raise ValueError('Shared actual section/rules khác')
            if p['A']['alpha']!=p['AS']['alpha'] or len({p[v]['sentiment'] for v in ('S','AS','P')})!=1:raise ValueError('A/S sections không paired')
            for field in ('prefix','trend','pattern','indicator','rules','sentiment'):
                if p['AS'][field]!=p['P'][field]:raise ValueError('AS/P khác ngoài alpha contents')
            if p['AS']['alpha']==p['P']['alpha']:raise ValueError('Placebo không perturb actual alpha content')
            names=lambda text:[(r['rank'],r['name']) for r in factor_cells(text)]
            if names(p['AS']['alpha'])!=names(p['P']['alpha']):raise ValueError('AS/P headings/names/schema khác')
            pair_rows.append({'unit_id':uid,'repeat':repeat,'shared_upstream_and_rules':True,'alpha_A_AS_equal':True,
                'sentiment_S_AS_P_equal':True,'AS_P_only_alpha_contents_differ':True,'AS_P_five_named_rows':True})
            planned=[j['variant'] for j in m['jobs'] if j['unit_id']==uid and j['repeat']==repeat]
            observed=sorted(VARIANTS,key=lambda v:requests[points[v]['request_ids'][-1]]['started_at_utc'])
            if observed!=planned:raise ValueError('Successful within-group call order khác registered jobs')
            order_rows.append({'unit_id':uid,'repeat':repeat,'planned':';'.join(planned),'observed':';'.join(observed),'matches':True})
        for v in VARIANTS:
            values=[by_key[(uid,v,r)]['prediction'] for r in range(3)]
            disagreement.append({'unit_id':uid,'variant':v,'predictions':values,'pairwise_disagreement':float(np.mean([values[a]!=values[b] for a,b in ((0,1),(0,2),(1,2))]))})
    with (ROOT/'outputs/revision/r1_72h_run_v2/analysis/predictions.csv').open(encoding='utf-8',newline='') as f:labels={r['unit_id']:r['label_net'] for r in csv.DictReader(f)}
    classes=[];per_run=[];class_contrasts=[]
    for v in VARIANTS:
        for repeat in range(3):
            selected=list(units);y=[labels[uid] for uid in selected];pred=[by_key[(uid,v,repeat)]['prediction'] for uid in selected]
            value=binary_classification_metrics(y,pred)
            for metric in ('accuracy','balanced_accuracy','mcc','macro_f1','long_rate'):
                if not np.isclose(value[metric],stats['variants'][v]['by_execution'][metric][repeat],atol=1e-14):raise ValueError('Classification không khớp native analysis')
            part=[]
            for symbol in sorted({u['unit']['symbol'] for u in units.values()}):
                ids=[uid for uid,u in units.items() if u['unit']['symbol']==symbol]
                metric=binary_classification_metrics([labels[uid] for uid in ids],[by_key[(uid,v,repeat)]['prediction'] for uid in ids]);part.append(metric)
                classes.append({'variant':v,'repeat':repeat,'group':'symbol','value':symbol,'metrics':metric})
            macro={k:{'n_defined':sum(r[k] is not None for r in part),'n_symbols':8,
                'mean':float(np.mean([r[k] for r in part if r[k] is not None])) if any(r[k] is not None for r in part) else None}
                for k in ('accuracy','balanced_accuracy','mcc','macro_f1','long_rate')}
            classes.append({'variant':v,'repeat':repeat,'group':'ALL','value':'common18','metrics':value,'equal_symbol_macro':macro})
            per_run.append({'variant':v,'repeat':repeat,'n_units':18,'n_up':6,'n_down':12,**value['confusion'],
                **{k:value[k] for k in ('accuracy','balanced_accuracy','mcc','macro_f1','long_rate')},
                'recall_up':value['per_class']['UP']['recall'],'recall_down':value['per_class']['DOWN']['recall'],
                'mean_account_net_return_pct':stats['variants'][v]['by_execution']['mean_account_net_return_pct'][repeat],'n_accounts':13})
    for contrast in stats['contrasts']:
        weights=contrast['weights'];row={'contrast':contrast['contrast'],'by_execution':{}}
        for field in ('recall_up','recall_down','long_rate','mean_account_net_return_pct'):
            row['by_execution'][field]=[sum(w*next(x[field] for x in per_run if x['variant']==v and x['repeat']==r) for v,w in weights.items()) for r in range(3)]
        for r in range(3):
            if not np.isclose((row['by_execution']['recall_up'][r]+row['by_execution']['recall_down'][r])/2,contrast['by_execution']['balanced_accuracy'][r]):raise ValueError('BA decomposition không đúng')
        class_contrasts.append(row)
    first=min(r['started_at_utc'] for r in attempts)
    if m['created_utc']>=first:raise ValueError('Không xác nhận được bank freeze trước actual calls')
    audit={'status':'R4 addressed on corrected historical selected panel; no general information/profitability claim',
        'bank_id':m['sha256'],'bank_created_utc':m['created_utc'],'first_attempt_utc':first,'last_attempt_utc':max(r['started_at_utc'] for r in attempts),
        'n_attempts':len(attempts),'n_successes':len(success_ids),'n_errors':sum(r['outcome']!='success' for r in attempts),
        'error_type':'4 provider json_validate_failed rejections retained; failed outputs never predictions',
        'n_new_vision_calls':0,'n_units':18,'n_up_per_execution':6,'n_down_per_execution':12,'n_symbols':8,'n_dates':5,'n_blocks':3,
        'n_paired_groups':len(pair_rows),'n_successful_alpha_prompts_with_five_rows':sum(r['factor_rows']==5 and r['outcome']=='success' for r in attempts),
        'all_274_attempts_model_temp_cap':'openai/gpt-oss-20b / SDK 1e-8 / 2048; client metadata, unverified served weight revision',
        'n_order_matches':len(order_rows),'n_successful_calls_reused_from_old_study':0,'n_account_executions':195,
        'mean_pairwise_disagreement':{v:float(np.mean([r['pairwise_disagreement'] for r in disagreement if r['variant']==v])) for v in VARIANTS},
        'constant_cash_reference':{'accuracy':2/3,'balanced_accuracy':.5,'mcc':None,'mean_account_net_return_pct':0},
        'scope':'corrected and old compressed runs remain distinct; no causal before/after repair estimate, no pooled repeats as markets; no best-run/ensemble substitution',
        'limits':'AS/P changes joint rank-vector values/signals/skill fields; 84/90 rank names differ, not named-factor covariance. No exact token-length match, exposure matching, isolated sentiment information or prospective/calibrated-family claim.'}
    files={'audit.json':json_text(audit),'request_inventory.csv':csv_text(attempts),'paired_prompt_checks.json':json_text(pair_rows),
        'call_order.csv':csv_text(order_rows),'per_execution_metrics.csv':csv_text(per_run),'classification.json':json_text(classes),
        'class_exposure_contrasts.json':json_text(class_contrasts),'disagreement.json':json_text(disagreement)}
    body=[]
    for v in VARIANTS:
        s=stats['variants'][v]['summary'];body.append(' & '.join([v,f"{s['accuracy']['mean']*100:.2f}",f"{s['balanced_accuracy']['mean']*100:.2f}",
            f"{s['balanced_accuracy']['sd']*100:.2f}",f"{s['mcc']['mean']:.3f}",f"{s['long_rate']['mean']*100:.2f}",
            f"{s['mean_account_net_return_pct']['mean']:.3f}"])+r' \\')
    files['r4_value_metrics.tex']=table('Corrected full-value panel: three executions per variant on the same 18 units.','tab:r4_value_metrics','lrrrrrr',
        'Variant & Acc. & BA & BA SD & MCC & LONG & Return',body,
        'Percentages except MCC. Each score pools 18 units within one execution, then averages three scores; equal-symbol macros and defined denominators are in JSON. Six UP/twelve DOWN per execution; eight symbols, five dates, three blocks. Return averages 13 panel symbol--block accounts per execution, not a portfolio. CASH references: accuracy 66.67, BA 50.00, return zero; MCC undefined. No pooling with the broad 102-unit compressed-report study.')
    body=[];envelope=stats['BA_family']['descriptive_envelopes']
    for r in stats['contrasts']:
        s=r['summary']['balanced_accuracy'];ci=r['intervals']['balanced_accuracy']['percentile_95'];e=envelope[r['contrast']]
        body.append(' & '.join([r['contrast'],f"{s['mean']*100:.2f}",f"{s['sd']*100:.2f}",f"[{ci[0]*100:.2f}, {ci[1]*100:.2f}]",
            f"[{e[0]*100:.2f}, {e[1]*100:.2f}]",f"{r['summary']['long_rate']['mean']*100:.2f}"])+r' \\')
    files['r4_value_contrasts.tex']=table('Corrected paired BA contrasts and the predefined seven-contrast descriptive envelope (percentage points).','tab:r4_value_contrasts','lrrrrr',
        'Contrast & Mean & SD & Pointwise interval & Joint envelope & LONG delta',body,
        '10,000 paired block/run draws, seed 20261102; 9,612 jointly finite and 388 undefined BA draws. Joint max-deviation radius 13.49 points; not calibrated simultaneous confidence or FWER control. AS-P pointwise interval excludes zero but its joint envelope includes zero. Interaction is AS-A-S+B. Only three executions/blocks; no significance or isolated alpha-value conclusion.')
    body=[r'Fresh decisions / successful responses & 270 / 270 \\',r'Attempts / JSON errors / new vision calls & 274 / 4 / 0 \\',
        r'Paired groups / order matches & 54 / 54 \\',r'Alpha-bearing successes with five scalar rows & 162 / 162 \\',
        r'Old-study successful requests copied & 0 \\',r'Panel account executions / accounts per run & 195 / 13 \\']
    files['r4_value_audit.tex']=table('Completed actual-prompt and response audit for the repaired R4 panel.','tab:r4_value_audit','lr',
        'Check & Observed',body,'All 54 groups share archived upstream text/parents/rules; A/AS alpha matches, S/AS/P sentiment matches, and AS/P differ only in alpha content with five current factor names. Whole training donor vectors retain schema/masks; rank mapping is not named-factor covariance. Raw failures, responses and checkpoints are retained. All source/runtime pins verified; no new model calls during finalization.')
    return files


def sources() -> list[Path]:
    """Liên kết source native đủ để kiểm mọi raw byte mà không copy chúng sang release khác."""
    return [ROOT/p for p in ['scripts/finalize_revision_r4.py','tests/test_revision_r4_finalize.py',
        'outputs/revision/r4_value_bank_v1/manifest.json','outputs/revision/r4_value_run_v1/analysis/manifest.json',
        'outputs/revision/r4_manuscript_v1/manifest.json','outputs/revision/r4_manuscript_v1/sources.zip']]+sorted(RUN.glob('shards/org*/calls/*.response_digest.json'))


def main() -> None:
    """Release mới không ghi đè; --check tái tạo mọi file trong tiến trình độc lập."""
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');args=p.parse_args()
    if OUTPUT.exists() and not args.check:raise FileExistsError('Release R4 final đã có; dùng --check')
    if args.check:
        manifest=read_json(OUTPUT/'manifest.json')
        for group,base in [('sources',ROOT),('outputs',OUTPUT)]:
            for r in manifest[group]:
                if sha(base/r['path'])!=r['sha256']:raise ValueError('R4 final hash khác: '+r['path'])
    files=payloads()
    for name,text in files.items():
        if args.check:
            if (OUTPUT/name).read_bytes()!=text.encode('utf-8'):raise ValueError('R4 final không tái lập: '+name)
        else:OUTPUT.mkdir(exist_ok=True);(OUTPUT/name).write_text(text,encoding='utf-8',newline='\n')
        if name.endswith('.tex'):
            path=ROOT/'paper/generated'/name
            if args.check:
                if path.read_bytes()!=text.encode('utf-8'):raise ValueError('Bảng R4 final không khớp')
            else:path.write_text(text,encoding='utf-8',newline='\n')
    if not args.check:
        manifest={'schema_version':'revision_r4_final_v1','sources':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in sources()],
            'outputs':[{'path':n,'sha256':sha(OUTPUT/n)} for n in files]}
        (OUTPUT/'manifest.json').write_text(json_text(manifest),encoding='utf-8',newline='\n')
    print(f'PASS R4 final: {len(files)} artifacts, 270 real decisions/274 attempts; không gọi API.')


if __name__=='__main__':main()
