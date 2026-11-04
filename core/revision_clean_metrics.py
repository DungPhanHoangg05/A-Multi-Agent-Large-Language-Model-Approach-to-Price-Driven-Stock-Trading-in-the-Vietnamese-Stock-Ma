"""Replay độc lập từ raw/prices: chỉ cần stdlib và NumPy trong venv sạch."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

METRICS=('accuracy','balanced_accuracy','mcc','macro_f1','long_rate','mean_account_net_return_pct')
VARIANTS=('B','A','S','AS','P')
CONTRASTS={'AS-B':{'AS':1,'B':-1},'A-B':{'A':1,'B':-1},'AS-S':{'AS':1,'S':-1},
           'S-B':{'S':1,'B':-1},'AS-A':{'AS':1,'A':-1},'AS-P':{'AS':1,'P':-1},
           'interaction':{'AS':1,'A':-1,'S':-1,'B':1}}


def require(value: bool, message: str) -> None:
    """Dừng khi bất kỳ support/contract/so sánh nào sai."""
    if not value: raise ValueError(message)


def read(path: Path) -> Any:
    """Chỉ đọc JSON trong package được guard bảo vệ."""
    return json.loads(path.read_bytes())


def sha(data: bytes) -> str:
    """Hash bytes và identity JSON, không suy model weights."""
    return hashlib.sha256(data).hexdigest()


def content_hash(value: Any) -> str:
    """Giữ serialization của frozen request identity."""
    return sha(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode())


def clean(value: Any) -> Any:
    """Loại narrative scope khỏi so sánh metrics, không loại số/undefined."""
    if isinstance(value,dict): return {k:clean(v) for k,v in value.items() if k!='scope'}
    if isinstance(value,list): return [clean(v) for v in value]
    return value


class Comparator:
    """Đối soát cả cấu trúc/null, tolerance nhỏ chỉ dành cho số thực."""
    def __init__(self) -> None:
        self.leaves=0; self.floats=0; self.max_absolute_error=0.0

    def check(self, expected: Any, actual: Any, path: str = '') -> None:
        if isinstance(expected,dict):
            require(isinstance(actual,dict) and expected.keys()==actual.keys(),'Khác keys: '+path)
            for k in expected: self.check(expected[k],actual[k],path+'/'+str(k))
        elif isinstance(expected,list):
            require(isinstance(actual,list) and len(expected)==len(actual),'Khác list support: '+path)
            for i,(a,b) in enumerate(zip(expected,actual)): self.check(a,b,path+'/'+str(i))
        elif isinstance(expected,float):
            require(isinstance(actual,(int,float)) and not isinstance(actual,bool) and math.isfinite(actual),'Số không hữu hạn: '+path)
            difference=abs(expected-actual); self.max_absolute_error=max(self.max_absolute_error,difference)
            require(math.isclose(expected,actual,rel_tol=1e-10,abs_tol=1e-8),'Metric không khớp: '+path)
            self.floats+=1; self.leaves+=1
        else:
            require(type(expected)==type(actual) and expected==actual,'Giá trị/undefined khác: '+path)
            self.leaves+=1


def classification(actual: list[str], predicted: list[str]) -> dict:
    """Tính confusion và chỉ số có mẫu số rõ ràng bằng đại số độc lập."""
    require(len(actual)==len(predicted),'Khác classification support')
    convert={'LONG':'UP','SHORT':'DOWN','UP':'UP','DOWN':'DOWN'}
    require(all(x in convert for x in actual+predicted),'Nhãn ngoài contract')
    pairs=[(convert[a],convert[p]) for a,p in zip(actual,predicted)]
    tp=sum(a==p=='UP' for a,p in pairs); tn=sum(a==p=='DOWN' for a,p in pairs)
    fp=sum(a=='DOWN' and p=='UP' for a,p in pairs); fn=len(pairs)-tp-tn-fp
    def ratio(a: float,b: float) -> float | None: return a/b if b else None
    def one(c: int,m: int,w: int) -> dict:
        return {'support':c+m,'predicted':c+w,'precision':ratio(c,c+w),'recall':ratio(c,c+m),'f1':ratio(2*c,2*c+m+w)}
    up=one(tp,fn,fp); down=one(tn,fp,fn); den=math.sqrt((tp+fp)*(tp+fn)*(tn+fp)*(tn+fn))
    return {'n_input':len(pairs),'n_valid':len(pairs),'n_excluded':0,'confusion':{'tp':tp,'fn':fn,'tn':tn,'fp':fp},
            'accuracy':ratio(tp+tn,len(pairs)),'balanced_accuracy':(up['recall']+down['recall'])/2 if tp+fn and tn+fp else None,
            'mcc':(tp*tn-fp*fn)/den if den else None,'macro_f1':(up['f1']+down['f1'])/2 if up['f1'] is not None and down['f1'] is not None else None,
            'long_rate':ratio(tp+fp,len(pairs)),'per_class':{'UP':up,'DOWN':down}}


def describe(values: list[float | None]) -> dict:
    """Giữ SD mẫu và denominator undefined đúng protocol."""
    import numpy as np
    a=np.asarray([v for v in values if v is not None and math.isfinite(v)])
    return {'n_planned':len(values),'n_defined':len(a),'mean':float(a.mean()) if len(a) else None,
            'sd':float(a.std(ddof=1)) if len(a)>1 else None,'median':float(np.median(a)) if len(a) else None,
            'min':float(a.min()) if len(a) else None,'max':float(a.max()) if len(a) else None}


def grouped(rows: list[dict]) -> dict:
    """Pooled, symbol, block và macro từ cùng rows, không lấy summary làm input."""
    require(bool(rows) and len({r['unit_id'] for r in rows})==len(rows),'Support trùng/rỗng')
    def metric(part: list[dict]) -> dict: return classification([r['label_net'] for r in part],[r['prediction'] for r in part])
    by={field:{v:metric([r for r in rows if r[field]==v]) for v in sorted({r[field] for r in rows})} for field in ('symbol','fold')}
    return {'pooled':metric(rows),'by_symbol':by['symbol'],'by_block':by['fold'],
            'macro_symbol':{m:describe([r[m] for r in by['symbol'].values()]) for m in METRICS[:-1]}}


def load_prices(root: Path, protocol: dict) -> dict:
    """Đọc đúng CSV đã khóa, giữ nguyên policy cắt prefix OHLC bất hợp lệ."""
    import numpy as np
    base=root/protocol['price_snapshot']; manifest=read(base/'manifest.json'); frames={}
    for item in manifest['symbols']:
        path=base/item['path']; require(sha(path.read_bytes())==item['sha256'],'Price hash sai')
        with path.open(encoding='utf-8',newline='') as handle: rows=list(csv.DictReader(handle))
        require(len(rows)==item['n_rows'],'Price row count sai')
        bad=[i for i,r in enumerate(rows) if float(r['High'])<max(float(r[k]) for k in ('Open','Close','Low')) or float(r['Low'])>min(float(r[k]) for k in ('Open','Close','High'))]
        if bad:
            require(protocol['price_quality_policy']=='valid_suffix_after_last_bad_ohlc','OHLC lỗi chưa có policy')
            rows=rows[bad[-1]+1:]
        frames[item['symbol']]={'date':[r['date'] for r in rows],**{k:np.asarray([float(r[k]) for r in rows]) for k in ('Open','Close')}}
    return frames


def target(frame: dict, index: int, protocol: dict) -> tuple[str,str]:
    """Net primary giữ phí/slippage hai chân và zero=DOWN, gross riêng."""
    ratio=float(frame['Close'][index+3]/frame['Open'][index+1])
    net=ratio*(1-protocol['fee_each_side'])*(1-protocol['slippage_each_side'])/((1+protocol['fee_each_side'])*(1+protocol['slippage_each_side']))-1
    return ('UP' if net>0 else 'DOWN','UP' if ratio>1 else 'DOWN')


def ledger(frame: dict, cycles: list[tuple[int,int,int]], protocol: dict) -> dict:
    """Tái lập fractional ledger từ giá và actions, có anchor và CASH gaps."""
    import numpy as np
    require(bool(cycles),'Lịch trống'); first,last=cycles[0][0],cycles[-1][1]
    require(first>=0 and last<len(frame['date']),'Lịch ngoài snapshot')
    cash=initial=float(protocol['initial_capital_vnd']); fee=protocol['fee_each_side']; slip=protocol['slippage_each_side']
    n=last-first+1; equity=np.full(n,initial); fees=np.zeros(n); slips=np.zeros(n); notional=np.zeros(n); held=np.zeros(n); exposed=np.zeros(n)
    cursor=first; orders=0
    for entry,exit_index,action in cycles:
        require(cursor<=entry<=exit_index and action in (0,1),'Lịch overlap/action sai')
        equity[cursor-first:entry-first]=cash; left,right=entry-first,exit_index-first
        if action:
            opening=float(frame['Open'][entry]); shares=cash/((1+fee)*(1+slip)*opening)
            buy=shares*opening; fees[left]+=buy*(1+slip)*fee; slips[left]+=buy*slip; notional[left]+=buy
            marks=frame['Close'][entry:exit_index+1]*shares; equity[left:right+1]=marks
            sell=marks[-1]; fees[right]+=sell*(1-slip)*fee; slips[right]+=sell*slip; notional[right]+=sell
            cash=float(sell*(1-slip)*(1-fee)); equity[right]=cash; held[left:right+1]=1; exposed[left:right]=1; orders+=2
        else: equity[left:right+1]=cash
        cursor=exit_index+1
    equity[cursor-first:]=cash
    anchor=np.concatenate(([initial],equity)); dd=1-anchor/np.maximum.accumulate(anchor); turn=notional/anchor[:-1]
    daily=[{'date':frame['date'][first+i],'equity_vnd':float(equity[i]),'turnover':float(turn[i]),'held_during_session':int(held[i]),
            'close_exposure':int(exposed[i]),'brokerage_fee_vnd':float(fees[i]),'slippage_cost_vnd':float(slips[i])} for i in range(n)]
    return {'net_return_pct':float((equity[-1]/initial-1)*100),'daily_close_drawdown_pct':float(dd.max()*100),'order_count':orders,
            'mean_daily_turnover':float(turn.mean()),'total_turnover':float(turn.sum()),'held_session_fraction':float(held.mean()),
            'mean_close_exposure':float(exposed.mean()),'brokerage_fee_vnd':float(fees.sum()),'slippage_cost_vnd':float(slips.sum()),'daily':daily}


def account_panel(rows: list[dict], units: list[dict], frames: dict, protocol: dict, panel: str, execution: int) -> tuple:
    """Dựng account/tensors có support giống nhau cho từng execution."""
    import numpy as np
    variants=sorted({r['variant'] for r in rows}); blocks=sorted({u['fold'] for u in units}); actions={(r['unit_id'],r['variant']):r['prediction'] for r in rows}
    require(len(actions)==len(rows)==len(units)*len(variants),'Panel support thiếu/trùng')
    accounts=[]; daily=[]; counts={v:np.zeros((len(blocks),4),dtype=int) for v in variants}; returns={v:np.zeros((len(blocks),2)) for v in variants}
    for v in variants:
        for symbol,fold in sorted({(u['symbol'],u['fold']) for u in units}):
            chosen=sorted([u for u in units if (u['symbol'],u['fold'])==(symbol,fold)],key=lambda u:u['decision'])
            value=ledger(frames[symbol],[(u['decision']+1,u['decision']+3,int(actions[(u['id'],v)]=='LONG')) for u in chosen],protocol)
            key={'panel':panel,'execution':execution,'variant':v,'symbol':symbol,'fold':fold}
            daily.extend({**key,**d} for d in value.pop('daily')); accounts.append({**key,'n_cycles':len(chosen),**value})
            returns[v][blocks.index(fold)]+=[value['net_return_pct'],1]
        for i,block in enumerate(blocks):
            part=[r for r in rows if r['fold']==block and r['variant']==v]; c=classification([r['label_net'] for r in part],[r['prediction'] for r in part])['confusion']
            counts[v][i]=[c[k] for k in ('tp','fn','tn','fp')]
    return accounts,daily,counts,returns


def array_metrics(c: Any) -> dict:
    """Đại số vector hóa cho các whole-block resamples, giữ NaN nội bộ."""
    import numpy as np
    tp,fn,tn,fp=(c[...,i].astype(float) for i in range(4))
    with np.errstate(divide='ignore',invalid='ignore'):
        return {'accuracy':(tp+tn)/(tp+fn+tn+fp),'balanced_accuracy':(tp/(tp+fn)+tn/(tn+fp))/2,
                'mcc':(tp*tn-fn*fp)/np.sqrt((tp+fp)*(tp+fn)*(tn+fp)*(tn+fn)),
                'macro_f1':(2*tp/(2*tp+fn+fp)+2*tn/(2*tn+fn+fp))/2,'long_rate':(tp+fp)/(tp+fn+tn+fp)}


def interval(values: Any) -> dict:
    """Percentile chỉ trên finite draws; không thay undefined bằng zero."""
    import numpy as np
    finite=values[np.isfinite(values)]
    return {'n_resamples':len(values),'n_defined':len(finite),'n_undefined':len(values)-len(finite),
            'percentile_95':np.quantile(finite,[.025,.975]).tolist() if len(finite) else None}


def bootstraps(counts: dict, returns: dict, bw: Any, rw: Any, factorial: bool) -> dict:
    """Tính lại draws từ tensors khôi phục, không dùng expected CI làm input."""
    import numpy as np
    samples={}; centers={}
    for v in counts:
        sums=np.einsum('bk,rkc->brc',bw,counts[v]); scores=array_metrics(sums); ret=np.einsum('bk,rkc->brc',bw,returns[v])
        scores[METRICS[-1]]=ret[...,0]/ret[...,1]
        samples[v]={}
        for m,a in scores.items():
            valid=np.all((rw==0)|np.isfinite(a),axis=1)
            samples[v][m]=np.where(valid,np.sum(np.where(np.isfinite(a),a,0)*rw,axis=1)/rw.sum(axis=1),np.nan)
        center=array_metrics(counts[v].sum(axis=1)); center[METRICS[-1]]=returns[v][...,0].sum(axis=1)/returns[v][...,1].sum(axis=1); centers[v]=center
    if not factorial:
        return {'n_runs':3,'n_blocks':counts['AS'].shape[1],'seed':20261102,
                'variants':{v:{m:interval(a) for m,a in values.items()} for v,values in samples.items()},
                'contrasts':{'AS-B':{m:interval(samples['AS'][m]-samples['B'][m]) for m in METRICS}}}
    results=[]; ba_samples=[]; ba_centers=[]
    for name,weights in CONTRASTS.items():
        values={m:sum(w*centers[v][m] for v,w in weights.items()) for m in METRICS}
        draws={m:sum(w*samples[v][m] for v,w in weights.items()) for m in METRICS}
        native={m:[float(x) if np.isfinite(x) else None for x in a] for m,a in values.items()}
        results.append({'contrast':name,'weights':weights,'by_execution':native,'summary':{m:describe(a) for m,a in native.items()},'intervals':{m:interval(a) for m,a in draws.items()}})
        ba_samples.append(draws['balanced_accuracy']); ba_centers.append(float(values['balanced_accuracy'].mean()))
    joint=np.asarray(ba_samples).T; finite=np.isfinite(joint).all(axis=1)
    radius=float(np.quantile(np.max(np.abs(joint[finite]-ba_centers),axis=1),.95)) if finite.any() else None
    return {'variants':{v:{'by_execution':{m:[float(x) if np.isfinite(x) else None for x in a] for m,a in centers[v].items()},
                          'summary':{m:describe([float(x) if np.isfinite(x) else None for x in a]) for m,a in centers[v].items()},
                          'intervals':{m:interval(a) for m,a in samples[v].items()}} for v in VARIANTS},
            'contrasts':results,'BA_family':{'n_contrasts':7,'n_joint_finite_draws':int(finite.sum()),'n_joint_undefined_draws':int((~finite).sum()),
                 'max_absolute_deviation_radius':radius,'descriptive_envelopes':{name:[c-radius,c+radius] if radius is not None else None for name,c in zip(CONTRASTS,ba_centers)}}}


def raw_prediction(response: dict) -> str:
    """Parse saved tool/content JSON, không SDK/fallback/inference."""
    message=response['response']['generations'][0][0]['message']
    if message.get('tool_calls'): value=message['tool_calls'][0]['args']
    elif not message.get('content') and message.get('additional_kwargs',{}).get('tool_calls'):
        value=json.loads(message['additional_kwargs']['tool_calls'][0]['function']['arguments'])
    else: value=json.loads(message['content'])
    require(value['decision'] in ('LONG','SHORT'),'Raw prediction không binary')
    return value['decision']


def numeric_replay(root: Path, frames: dict, protocol: dict, check: Comparator) -> dict:
    """Tính metrics/ledger của 23 saved controls, không refit hoặc chọn seed."""
    base=root/'outputs/revision/numeric_controls_v1'; units=read(base/'test_predictions.json'); strategies=list(units[0]['actions'])
    for u in units:
        require(('UP' if u['label'] else 'DOWN')==target(frames[u['symbol']],u['decision'],protocol)[0],'T13 label khác snapshot')
    groups={('pooled','all'):units}
    for level,field in [('symbol','symbol'),('block','fold'),('scope','scope_id')]:
        for group in sorted({u[field] for u in units}): groups[(level,group)]=[u for u in units if u[field]==group]
    expected=read(base/'test_metrics.json'); actual=[]
    # Tên group pooled là một phần schema, không thay đổi mẫu theo outcomes.
    pooled_name=next(r['group'] for r in expected if r['level']=='pooled')
    for (level,group),part in sorted(groups.items()):
        for s in strategies:
            actual.append({'level':level,'group':pooled_name if level=='pooled' else group,'strategy':s,
                           'metrics':classification(['UP' if u['label'] else 'DOWN' for u in part],['LONG' if u['actions'][s] else 'SHORT' for u in part])})
    check.check(expected,actual,'T13_test_metrics')
    ac=[]; daily=[]
    for (level,group),part in sorted(groups.items()):
        if level not in ('scope','symbol'): continue
        chosen=sorted(part,key=lambda u:u['decision']); symbol=chosen[0]['symbol']
        for s in strategies:
            value=ledger(frames[symbol],[(u['entry'],u['exit'],u['actions'][s]) for u in chosen],protocol)
            series=value.pop('daily'); ac.append({'level':level,'group':group,'symbol':symbol,'strategy':s,'cycles':len(chosen),**value})
            if level=='symbol': daily.append({'group':group,'strategy':s,'daily':series})
    check.check(read(base/'accounts.json'),ac,'T13_accounts')
    check.check(json.loads(gzip.decompress((base/'daily_ledgers.json.gz').read_bytes())),daily,'T13_daily')
    return {'prediction_units':len(units),'strategies':len(strategies),'classification_groups':len(actual),
            'accounts_rebuilt':len(ac),'daily_rows_rebuilt':sum(len(r['daily']) for r in daily),
            'scope':'Saved test predictions; không refit/validation selection hoặc chạy lại T13 p-values.'}


def risk_replay(root: Path, rebuilt_daily: list[dict], check: Comparator) -> dict:
    """Tính lại T20 risk từ T04 ledger vừa dựng và T19 ledger frozen."""
    import numpy as np
    groups=defaultdict(list)
    for r in rebuilt_daily: groups[('T04',r['panel'],r['execution'],r['variant'],r['symbol'],r['fold'],'NA')].append(r)
    with gzip.open(root/'outputs/revision/execution_final_v1/daily_ledger.csv.gz','rt',encoding='utf-8',newline='') as handle:
        for r in csv.DictReader(handle):
            require(math.isclose(float(r['equity_vnd']),sum(float(r[k]) for k in ('settled_cash_vnd','pending_cash_vnd','stock_mtm_vnd')),rel_tol=1e-12,abs_tol=1e-7),'T19 wealth không bảo toàn')
            groups[('T19','main',0,r['variant'],r['symbol'],r['fold'],r['scenario'])].append(r)
    def ratios(values: Any) -> dict:
        mean=float(values.mean()); sd=float(values.std(ddof=0)); neg=values[values<0]; downside=float(neg.std(ddof=0)) if len(neg) else None
        sh=mean/sd if sd>1e-12 else None; so=mean/downside if downside is not None and downside>1e-12 else None
        return {'sharpe_ratio':sh*math.sqrt(252) if sh is not None else None,'sortino_ratio':so*math.sqrt(252) if so is not None else None,
                'sharpe_unannualised':sh,'sortino_unannualised':so,'periods_per_year':252.0,'annualisation_scale':math.sqrt(252),
                'n_returns':len(values),'n_negative_returns':len(neg),'mean_return':mean,'population_sd':sd,'negative_population_sd':downside,
                'risk_free_per_period':0.0,'minimum_acceptable_return':0.0,'sd_ddof':0}
    with (root/'outputs/revision/final_contracts_v1/risk_daily.csv').open(encoding='utf-8',newline='') as handle: expected=list(csv.DictReader(handle))
    require(len(groups)==len(expected),'Risk account support khác')
    compared=0
    for row in expected:
        key=(row['release'],row['panel'],int(row['execution']),row['variant'],row['symbol'],row['fold'],row['scenario']); rows=groups[key]
        wealth=np.asarray([50_000_000.0,*[float(r['equity_vnd']) for r in rows]]); returns=wealth[1:]/wealth[:-1]-1
        actual=ratios(returns); actual.update(total_return_pct=float((wealth[-1]/wealth[0]-1)*100),daily_close_drawdown_pct=float((1-wealth/np.maximum.accumulate(wealth)).max()*100),n_zero_returns=int(np.sum(returns==0)))
        for field,value in actual.items():
            original=None if row[field]=='NA' else int(row[field]) if type(value) is int else float(row[field])
            check.check(original,value,'T20_risk/'+str(key)+'/'+field); compared+=1
    return {'accounts':len(groups),'daily_rows':sum(len(v) for v in groups.values()),'numeric_fields_compared':compared,
            'scope':'T04 wealth vừa tái lập; T19 risk từ frozen wealth, không chạy lại fill/settlement engine hoặc certify fills.'}


def run_metrics(root: Path, output: Path) -> dict:
    """Tái lập T04 đầy đủ metrics và ledger; bổ sung đối soát numeric/T20 risk."""
    import numpy as np
    final=root/'outputs/revision/revision_minimal_final_v1'; bank=root/'outputs/revision/r1_72h_bank_v2'
    queue=read(root/'outputs/revision/revision_minimal_v1/manifest.json'); source=read(bank/'manifest.json'); units=source['units']; protocol=source['protocol']
    frames=load_prices(root,protocol); labels={u['id']:target(frames[u['symbol']],u['decision'],protocol) for u in units}
    check=Comparator(); records=read(final/'records.json'); jobs={j['id']:j for j in queue['jobs']}; requests={}; parsed={}
    for record in records:
        checkpoint=read(root/record['path']); job=jobs[record['job_id']]
        path=Path(record['path']).parent.parent/'calls'/f"{record['request_ids'][-1]}.request.json"
        request=read(root/path); response=read(root/path.with_name(path.name.replace('.request.','.response.')))
        prediction=raw_prediction(response); require(prediction==record['prediction']==checkpoint['prediction'],'Raw/checkpoint/record prediction khác')
        require(request['messages'][0][0]['data']['content']==job['prompt'],'Actual prompt khác job')
        require(response['parent_request_hash']==request['sha256'] and request['attempt_id']==response['attempt_id'],'Raw parent khác')
        requests[record['request_ids'][-1]]=request; parsed[record['job_id']]=prediction
    require(len(parsed)==375 and len(requests)==375,'Thiếu/trùng successful requests')
    with (bank/'numeric/predictions.csv').open(encoding='utf-8',newline='') as handle: main=list(csv.DictReader(handle))
    meta={u['id']:u for u in units}
    for r in main:
        require((r['label_net'],r['label_gross'])==labels[r['unit_id']],'Numeric target khác giá')
    for r in records:
        if r['phase']!='main': continue
        u=meta[r['context']['unit_id']]
        main.append({'unit_id':u['id'],**{k:u[k] for k in ('symbol','fold','date')},'variant':r['context']['variant'],
                     'prediction':parsed[r['job_id']],'label_net':labels[u['id']][0],'label_gross':labels[u['id']][1],
                     'market_input_hash':read(bank/f"features/{u['symbol']}_{u['decision']}.json")['market_input_hash']})
    check.check(read(final/'main_predictions.json'),main,'main_predictions')
    variants=sorted({r['variant'] for r in main}); accounts,daily,counts,returns=account_panel(main,units,frames,protocol,'main',0)
    with (bank/'numeric/summary.csv').open(encoding='utf-8',newline='') as handle: old_accounts=list(csv.DictReader(handle))
    for old in old_accounts:
        if old['variant']!='continuous_hold_price_only': continue
        chosen=sorted([u for u in units if (u['symbol'],u['fold'])==(old['symbol'],old['fold'])],key=lambda u:u['decision'])
        value=ledger(frames[old['symbol']],[(chosen[0]['decision']+1,chosen[-1]['decision']+3,1)],protocol)
        key={'panel':'main','execution':0,'variant':old['variant'],'symbol':old['symbol'],'fold':old['fold']}
        daily.extend({**key,**d} for d in value.pop('daily')); accounts.append({**key,'n_cycles':1,**value})
    classes={v:grouped([r for r in main if r['variant']==v]) for v in variants}
    for v in variants: classes[v]['mean_account_net_return_pct']=float(np.mean([a['net_return_pct'] for a in accounts if a['variant']==v]))
    check.check(read(final/'summary.json')['main_classification'],classes,'main_classification')
    cohorts={}
    for name,subset in [('common_eight_six_blocks',[u for u in units if u['symbol']!='BHN']),('recent_nine_three_blocks',[u for u in units if u['fold'].startswith('f')])]:
        ids={u['id'] for u in subset}; cohorts[name]={v:grouped([r for r in main if r['variant']==v and r['unit_id'] in ids]) for v in variants}
    check.check(read(final/'main_cohorts.json'),cohorts,'main_cohorts')
    gross={v:classification([r['label_gross'] for r in main if r['variant']==v],[r['prediction'] for r in main if r['variant']==v]) for v in variants}
    check.check(read(final/'gross_diagnostic.json')['classification'],gross,'gross')
    archive=np.load(final/'resampling.npz',allow_pickle=False); tensors={**{f'main_counts_{v}':a for v,a in counts.items()},**{f'main_accounts_{v}':a for v,a in returns.items()}}
    rng=np.random.default_rng(20261102); bw=rng.multinomial(len(counts['AS']),np.full(len(counts['AS']),1/len(counts['AS'])),10000); tensors['main_block_weights']=bw
    contrasts=[]
    for v in variants:
        if v=='AS': continue
        a=array_metrics(bw@counts['AS'])['balanced_accuracy']; b=array_metrics(bw@counts[v])['balanced_accuracy']; ci=interval(a-b)
        contrasts.append({'contrast':'AS-'+v,'n_blocks':len(counts['AS']),'n_resamples':10000,'n_undefined':ci['n_undefined'],'percentile_95':ci['percentile_95'],
                          'observed_BA_delta':classes['AS']['pooled']['balanced_accuracy']-classes[v]['pooled']['balanced_accuracy']})
    check.check(clean(read(final/'summary.json')['main_BA_contrasts']),contrasts,'main_BA_contrasts')
    panels={}
    for name,selected,part,upstream in [('upstream',[u for u in units if u['upstream']],[r for r in records if r['phase'] in ('main','upstream')],True),
                                        ('factorial',queue['panel'],[r for r in records if r['phase']=='factorial'],False)]:
        vs=('B','AS') if upstream else VARIANTS; blocks=sorted({u['fold'] for u in selected})
        indexed={(r['context']['unit_id'],r['context']['variant'],r['context']['realization'] if upstream else r['context']['repeat']):r for r in part}
        ct={v:np.zeros((3,len(blocks),4),dtype=int) for v in vs}; rt={v:np.zeros((3,len(blocks),2)) for v in vs}; executions=[]
        for run in range(3):
            rows=[{**u,'unit_id':u['id'],'variant':v,'label_net':labels[u['id']][0],'prediction':parsed[indexed[(u['id'],v,run)]['job_id']]} for u in selected for v in vs]
            ac,da,co,re=account_panel(rows,selected,frames,protocol,name,run); accounts.extend(ac); daily.extend(da)
            for v in vs:
                ct[v][run]=co[v]; rt[v][run]=re[v]; metrics=grouped([r for r in rows if r['variant']==v])
                executions.append({'variant':v,'execution':run,**metrics,**{m:metrics['pooled'][m] for m in METRICS[:-1]},METRICS[-1]:float(np.mean([a['net_return_pct'] for a in ac if a['variant']==v]))})
        disagreement=[]
        for u in selected:
            for v in vs:
                rr=[indexed[(u['id'],v,i)] for i in range(3)]; values=[int(parsed[r['job_id']]=='LONG') for r in rr]
                disagreement.append({'unit_id':u['id'],'variant':v,'n_unique_prompt_hashes':len({content_hash(requests[r['request_ids'][-1]]['messages']) for r in rr}),
                    'n_successful_requests':3,'n_unique_successful_requests':len({r['request_ids'][-1] for r in rr}),'prediction_vector':['LONG' if x else 'SHORT' for x in values],
                    'pairwise_disagreement':float(np.mean([values[a]!=values[b] for a,b in ((0,1),(0,2),(1,2))])),'sample_variance_long_indicator':float(np.var(values,ddof=1))})
        rng=np.random.default_rng(20261102); bw=rng.multinomial(len(blocks),np.full(len(blocks),1/len(blocks)),10000); rw=rng.multinomial(3,np.full(3,1/3),10000)
        panel={'panel':name,'n_units_per_execution':len(selected),'n_executions':3,'n_decisions':len(selected)*len(vs)*3,'n_unique_successful_requests':len(selected)*len(vs)*3,
               'n_dates':len({u['date'] for u in selected}),'n_symbols':len({u['symbol'] for u in selected}),'blocks':blocks,'support_per_execution':dict(Counter(labels[u['id']][0] for u in selected)),
               'n_accounts_per_variant_execution':len({(u['symbol'],u['fold']) for u in selected}),
               'summaries':{v:{m:describe([r[m] for r in executions if r['variant']==v]) for m in METRICS} for v in vs},
               'by_execution':executions,'statistics':bootstraps(ct,rt,bw,rw,not upstream),'disagreement':disagreement,
               'mean_pairwise_disagreement':{v:float(np.mean([r['pairwise_disagreement'] for r in disagreement if r['variant']==v])) for v in vs}}
        check.check(clean(read(final/(name+'_panel.json'))),panel,name); panels[name]=panel
        tensors.update({**{f'{name}_counts_{v}':a for v,a in ct.items()},**{f'{name}_accounts_{v}':a for v,a in rt.items()},f'{name}_block_weights':bw,f'{name}_run_weights':rw})
    require(set(archive.files)==set(tensors),'Resampling tensor keys khác')
    for key,value in tensors.items(): require(np.allclose(archive[key],value,rtol=1e-10,atol=1e-8,equal_nan=True),'Tensor/draw không khớp: '+key)
    check.check(read(final/'accounts.json'),accounts,'accounts')
    check.check(json.loads(gzip.decompress((final/'daily_ledgers.json.gz').read_bytes())),daily,'daily')
    numeric=numeric_replay(root,frames,protocol,check); risk=risk_replay(root,daily,check)
    configured=read(root/'reproducibility/model.json')['hosted_models']; sdk=Counter(); provider=Counter(); fingerprints=Counter(); seeds=Counter()
    for r in read(final/'attempts.json'):
        request=read(root/r['path']); sdk[str(request['model_metadata'].get('ls_model_name'))]+=1; seeds[str(request['invocation_parameters'].get('seed'))]+=1
        response_path=(root/r['path']).with_name(Path(r['path']).name.replace('.request.','.response.'))
        if response_path.exists():
            response=read(response_path)['response'].get('llm_output') or {}; provider[str(response.get('model_name'))]+=1; fingerprints[str(response.get('system_fingerprint'))]+=1
    payload={'main_classification':classes,'main_cohorts':cohorts,'gross_classification':gross,'main_BA_contrasts':contrasts,'panels':panels}
    (output/'metrics.json').write_bytes((json.dumps(payload,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode())
    report={'status':'PASS','raw_predictions_reparsed':len(parsed),'main_prediction_rows':len(main),'main_units':len(units),'class_support':dict(Counter(v[0] for v in labels.values())),
            'accounts_rebuilt_from_prices':len(accounts),'daily_rows_rebuilt':len(daily),'resampling_tensors_checked':len(tensors),'bootstrap_draws_per_family':10000,
            'comparison':vars(check),'api_calls':0,'model_forwards':0,'baseline_fits':0,
            'numeric_controls':numeric,'risk_contracts':risk,
            'models':{'configured':configured,'sdk_alias_counts':dict(sdk),'response_model_counts':dict(provider),'response_fingerprint_counts':dict(fingerprints),
                      'request_seed_counts':dict(seeds),'immutable_served_weight_revision':None,'scope':'Alias/fingerprint là metadata quan sát, không immutable weight digest; không probe provider.'},
            'scope':'Metrics T04 từ saved raw predictions/prices; không inference mới/refit. Không xác thực PIT, causal gate hoặc immutable hosted weights.'}
    return report


def sandbox_main() -> None:
    """Chặn đọc ngoài package/runtime và mọi subprocess/network trước import NumPy."""
    import os
    import site
    import socket
    root=Path(sys.argv[1]).resolve(); output=Path(sys.argv[2]).resolve(); work=root.parent.resolve()
    require(sys.prefix!=sys.base_prefix and site.ENABLE_USER_SITE is False,'Worker cần venv mới, tắt user site')
    require(Path(sys.prefix).resolve().is_relative_to(work),'Venv ngoài sandbox')
    require(output.is_relative_to(work) and output.is_dir() and not list(output.iterdir()),'Output worker phải trống trong sandbox')
    sys.dont_write_bytecode=True; base=Path(sys.base_prefix).resolve(); prefix=Path(sys.prefix).resolve()
    runtime_roots=[base/'Lib',base/'DLLs',base/f'python{sys.version_info.major}{sys.version_info.minor}.zip']
    events=Counter(); opened=set(); probes=Counter()
    def audit(event: str,args: tuple) -> None:
        if event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.posix_spawn'):
            events['blocked_network_or_process']+=1; raise PermissionError('T23 cấm network/subprocess')
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            path=Path(os.fsdecode(args[0])).resolve(); mode=args[1]; flags=args[2]
            writing=isinstance(mode,str) and any(c in mode for c in 'wax+') or isinstance(flags,int) and bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            allowed=path.is_relative_to(work) or any(path==r or path.is_relative_to(r) for r in runtime_roots)
            if path.is_relative_to(base/'Lib/site-packages'): allowed=False
            if writing: allowed=path.is_relative_to(output)
            if not allowed:
                events['blocked_file_access']+=1; raise PermissionError('T23 cấm file ngoài package/runtime')
            events['file_writes' if writing else 'file_reads']+=1
            opened.add('sandbox/'+path.relative_to(work).as_posix() if path.is_relative_to(work) else 'python_runtime/'+path.relative_to(base).as_posix())
    sys.addaudithook(audit)
    try: socket.socket()
    except PermissionError: probes['network']+=1
    try: (work.parent/'t23_forbidden_probe.txt').read_bytes()
    except PermissionError: probes['outside_file']+=1
    require(probes=={'network':1,'outside_file':1},'Guard probes chưa chặn được')
    import numpy as np
    require(np.__version__=='2.1.2' and Path(np.__file__).resolve().is_relative_to(prefix),'NumPy ngoài venv/pin')
    result=run_metrics(root,output)
    require(events['blocked_network_or_process']==1 and events['blocked_file_access']==1,'Có truy cập ngoài guard probes')
    result['isolation']={'python':sys.version.split()[0],'numpy':np.__version__,'include_system_site_packages':False,'user_site_enabled':site.ENABLE_USER_SITE,
                         'numpy_loaded_from_fresh_venv':True,'guard_probes':dict(probes),'audit_counts':dict(events),'read_paths':sorted(opened),
                         'scope':'Venv mới chỉ có NumPy clone có hash; stdlib/interpreter Python đã cài được dùng chung, không wheel installation độc lập hoặc replay khác OS.'}
    (output/'metrics_qa.json').write_bytes((json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode())
    print('Replay sạch PASS: '+json.dumps({k:result[k] for k in ('raw_predictions_reparsed','accounts_rebuilt_from_prices','daily_rows_rebuilt','comparison')},ensure_ascii=False))


if __name__=='__main__':
    sandbox_main()
