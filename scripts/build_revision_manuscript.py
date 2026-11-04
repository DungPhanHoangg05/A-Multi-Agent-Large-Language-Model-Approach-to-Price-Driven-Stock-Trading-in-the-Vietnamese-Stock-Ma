"""Sinh bảng/hình T32 từ evidence đã khóa; không inference, refit hoặc sửa receipts cũ."""
from __future__ import annotations

import argparse
import base64
import csv
import io
import math
from pathlib import Path
import re
import sys
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.revision_reproducibility import check_self_digest,digest,encoded,file_hash,offline_guard,read,require

RELEASE=Path('outputs/revision/manuscript_rewrite_v1')
ORDER=('AS','B','constant_down_cash','train_majority','constant_up_cycles','momentum_20','logistic_price','logistic_matched_market_inputs','factor_only_vote')
LABELS={'AS':'Full','B':'Base','constant_down_cash':'CASH','train_majority':'Train-majority',
        'constant_up_cycles':'Always-LONG','momentum_20':'Momentum-20','logistic_price':'Logistic-price',
        'logistic_matched_market_inputs':'Logistic-matched','factor_only_vote':'Factor vote','continuous_hold_price_only':'Continuous hold'}


def esc(value: object) -> str:
    """Escape dữ liệu text, không áp lên công thức LaTeX đã khai báo."""
    mapping={'\\':r'\textbackslash{}','_':r'\_','%':r'\%','&':r'\&','#':r'\#','{':r'\{','}':r'\}','$':r'\$'}
    return ''.join(mapping.get(c,c) for c in str(value))


def num(value: object,scale: float=1,digits: int=2) -> str:
    """Undefined thành NA; không nhận NaN/Infinity hoặc âm zero trình bày."""
    if value is None or value=='NA':return 'NA'
    result=float(value)*scale
    require(math.isfinite(result),'Không xuất nonfinite vào bảng')
    if abs(result)<.5*10**(-digits):result=0.
    return f'{result:.{digits}f}'


def mean_sd(mean: object,sd: object,scale: float=100,digits: int=2) -> str:
    """Mean và sample SD cùng đơn vị, undefined vẫn hiện rõ."""
    return num(mean,scale,digits)+' ('+num(sd,scale,digits)+')'


def interval(low: object,high: object,scale: float=100) -> str:
    """Không suy khoảng tin cậy khi mất một endpoint."""
    return 'NA' if low in (None,'NA') or high in (None,'NA') else '['+num(low,scale)+', '+num(high,scale)+']'


def panel(title: str,headers: list[str],rows: list[list[str]],align: str|None=None) -> str:
    """Bảng nhỏ dùng toàn chiều ngang; không resizebox để ép font nhỏ."""
    require(bool(rows) and all(len(r)==len(headers) for r in rows),'Số cột không khớp')
    return '\n'.join([r'\textbf{'+title+r'}\par\smallskip',r'\begin{tabular}{'+(align or 'l'+'r'*(len(headers)-1))+'}',
        r'\hline',' & '.join(headers)+r' \\',r'\hline',*[' & '.join(r)+r' \\' for r in rows],r'\hline',r'\end{tabular}\par\medskip'])


def table(caption: str,label: str,panels: list[str],note: str) -> bytes:
    """Caption/denominator đầy đủ, không thêm outcome hoặc đổi giá trị nguồn."""
    return ('\n'.join([r'\begin{table}[p]',r'\centering\small',r'\setlength{\tabcolsep}{3pt}',r'\renewcommand{\arraystretch}{1.15}',
        r'\caption{'+caption+'}',r'\label{'+label+'}',*panels,r'\begin{minipage}{\textwidth}\footnotesize '+note+r'\end{minipage}',r'\end{table}',''])).encode()


def historical_bytes(root: Path,name: str,expected: str,archive: Path) -> tuple[bytes,str]:
    """Chỉ paper sources được chuyển kiểm sang ZIP đúng member/hash sau sửa bài."""
    path=root/name
    if path.is_file() and file_hash(path)==expected:return path.read_bytes(),'current'
    require(name.startswith('paper/') and '..' not in Path(name).parts,'Không cho historical fallback ngoài paper')
    with ZipFile(archive) as z:
        require(z.namelist().count(name)==1,'ZIP thiếu/trùng member lịch sử')
        value=z.read(name)
    require(digest(value)==expected,'ZIP member khác hash nguồn cũ')
    return value,'original_sources.zip'


def verify_parents(root: Path,archive: Path) -> dict:
    """Đối soát receipts nguyên vẹn; ghi riêng current và historical paper references."""
    output={}
    for name in ('final_regression_v1','reviewer_crosswalk_v1','manuscript_blueprint_v1'):
        folder=root/'outputs/revision'/name; m=read(folder/'manifest.json'); require(bool(check_self_digest(m)),'Parent self-digest sai')
        current=0; historical=[]
        for group,base in (('sources',root),('outputs',folder)):
            for row in m[group]:
                if group=='sources':
                    _,where=historical_bytes(root,row['path'],row['sha256'],archive)
                    if where!='current':historical.append({'path':row['path'],'sha256':row['sha256'],'archive_member':row['path']})
                    else:current+=1
                else:require(file_hash(base/row['path'])==row['sha256'],'Parent output khác: '+row['path']);current+=1
        output[name]={'current_hashes':current,'historical_paper_hashes':historical,'total':current+len(historical)}
    return output


def build(root: Path,release: Path=RELEASE,artifact_only: bool=False) -> dict:
    """Sinh artifacts một lần sau source snapshot, không overwrite release đã có."""
    folder=(root/release).resolve(); archive=folder/'original_sources.zip'
    require(folder.parent==(root/'outputs/revision').resolve(),'Release phải là con trực tiếp outputs/revision')
    require(folder.is_dir() and {p.name for p in folder.iterdir()}=={'original_sources.zip'},'Cần snapshot mới, không overwrite output')
    with offline_guard():
        parents=verify_parents(root,archive); sources=set(); values=[]; generated={}
        def load(rel: str) -> object:
            name='outputs/revision/'+rel;sources.add(name)
            if name.endswith('.csv'):
                with (root/name).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
            return read(root/name)
        def select(rel: str,**mask: str) -> list[dict]:
            return [r for r in load(rel) if all(r.get(k)==v for k,v in mask.items())]
        def one(rows: list[dict],**keys: object) -> dict:
            found=[r for r in rows if all(r.get(k)==v for k,v in keys.items())];require(len(found)==1,'Identity thiếu/trùng: '+str(keys));return found[0]
        def record(table_id: str,identity: dict,field: str,value: object,scale: float=1,digits: int=2) -> str:
            text=num(value,scale,digits)
            values.append({'table':table_id,'identity':identity,'field':field,'source_literal':value,
                           'numeric_value':None if value in (None,'NA') else float(value),
                           'scale':scale,'digits':digits,'rendered':text})
            return text
        def output(name: str,content: bytes) -> None:generated[name]=content
        captions={t['id']:t['caption_en'] for t in load('manuscript_blueprint_v1/layout.json')['main_tables']}
        c=select('final_baselines_v1/classification.csv',cohort='all_102',dimension='pooled',group='all')
        require(len(c)==9 and {r['variant'] for r in c}==set(ORDER),'Main support sai')
        classes=select('final_baselines_v1/per_class.csv',cohort='all_102',dimension='pooled',group='all')
        macro=select('final_baselines_v1/macro.csv',cohort='all_102')
        economics=select('final_baselines_v1/financial.csv',cohort='all_102');require(len(economics)==10,'Thiếu account strategy')
        scope=[['Main','102','9','12','6','25/77','1','204'],['Upstream','9','9','3','3','2/7','3','54'],['Factorial','9','8','4','3','2/7','3','135']]
        variants=[['B','--','--','Shared price reports'],['A','Current','--','Five-row factorial'],['S','--','Current','Factorial'],['AS','Current','Current','Compact main / five-row factorial'],['P','Past donor','Current','Five-row factorial']]
        output('paper/generated/t01_scope.tex',table(captions['T1'],'tab:scope',[
            panel('A. Recorded supports',['Scope','$N$/exec.','Symbols','Dates','Blocks','UP/DOWN','Exec.','Decisions'],scope),
            panel('B. Prompt sections',['Variant','Factors','Sentiment','Representation'],variants,'llll')],
            'Main uses B/AS; upstream uses B/AS; factorial uses B/A/S/AS/P. Class counts are per execution. Upstream includes 18 main r0 calls: 204+54+135-18=375 unique Decisions. P preserves current names/schema/missingness and sentiment, replacing factor values/signals/skill metadata by one past train-only rank-vector donor.'))
        rows=[]
        for v in ORDER:
            r=one(c,variant=v);ident={'variant':v}
            require(r['n_valid']=='102' and r['support_up']=='25' and r['support_down']=='77','Class support khác')
            fields=[record('T2A',ident,k,r[k],1 if k=='mcc' else 100,3 if k=='mcc' else 2) for k in ('accuracy','balanced_accuracy','mcc')]
            for label in ('UP','DOWN'):
                per=one(classes,variant=v,**{'class':label})
                fields += [record('T2A',{**ident,'class':label},k,per[k],100) for k in ('precision','recall')]
            fields.append(record('T2A',ident,'long_rate',r['long_rate'],100));rows.append([LABELS[v],*fields])
        macro_rows=[]
        for v in ORDER:
            cells=[]
            for met in ('balanced_accuracy','mcc'):
                r=one(macro,variant=v,metric=met);cells += [record('T2B',{'variant':v,'metric':met},'mean',r['mean'],100 if met=='balanced_accuracy' else 1),r['n_defined']+'/'+r['n_planned']]
            macro_rows.append([LABELS[v],*cells])
        output('paper/generated/t02_classification.tex',table(captions['T2'],'tab:classification',[
            panel('A. Pooled (percent except MCC)',['Strategy','Acc.','BA','MCC','$P_U$','$R_U$','$P_D$','$R_D$','LONG'],rows),
            panel('B. Unweighted symbol macro summaries',['Strategy','BA (\\%)','Defined','MCC','Defined'],macro_rows)],
            '$N=102$, UP/DOWN=25/77. P/R denote class precision/recall. NA is undefined, including MCC for constant predictions. Train-majority is fit on purged train labels. Logistic-matched uses common numerical market inputs, not identical chart/text representations. Full per-symbol/class metrics are supplied in companion S1; hold has no classification prediction.'))
        erows=[]
        for v in (*ORDER,'continuous_hold_price_only'):
            r=one(economics,variant=v);require(r['n_accounts']=='51','Account denominator sai')
            erows.append([LABELS[v],*[record('T3',{'variant':v},k,r[k],100 if k=='mean_account_held_session_fraction' else 1,3 if k.endswith('return_pct') else 2)
                for k in ('mean_account_net_return_pct','mean_account_drawdown_pct','mean_account_held_session_fraction','mean_account_order_count')]])
        output('paper/generated/t03_accounts.tex',table(captions['T3'],'tab:accounts',[
            panel('Reference ledger',['Strategy','Return (\\%)','MDD (\\%)','Held (\\%)','Orders'],erows)],
            'Each row averages 51 independent-capital symbol--block accounts, not a portfolio. Held is the fraction of observed calendar sessions held, including scheduled CASH gaps; it differs from the LONG rate. Continuous hold buys once and sells once across gaps. Dividends/corporate actions and fills are not certified. Annualised cycle Sharpe/Sortino are omitted for irregular/gapped schedules.'))
        rep=load('final_repeats_v1/repeat_summary.csv');contr=load('final_repeats_v1/contrasts.csv');dis=load('final_repeats_v1/disagreement.csv'); rrows=[]
        for p,variants in [('upstream',('B','AS')),('factorial',('B','A','S','AS','P'))]:
            for v in variants:
                a=one(rep,panel=p,variant=v,metric='accuracy');b=one(rep,panel=p,variant=v,metric='balanced_accuracy');ret=one(rep,panel=p,variant=v,metric='mean_account_net_return_pct')
                d=[float(r['pairwise_disagreement']) for r in dis if r['panel']==p and r['variant']==v];require(len(d)==9,'Disagreement support sai')
                rrows.append([('U ' if p=='upstream' else 'F ')+v,mean_sd(a['mean'],a['sd']),mean_sd(b['mean'],b['sd']),interval(b['min'],b['max']),num(sum(d)/len(d),100),mean_sd(ret['mean'],ret['sd'],1)])
        cr=[]
        for r in [r for r in contr if r['metric']=='balanced_accuracy']:
            cr.append([('U ' if r['panel']=='upstream' else 'F ')+esc(r['contrast']),num(r['mean'],100),num(r['sd'],100),interval(r['min'],r['max']),interval(r['percentile_low'],r['percentile_high']),interval(r['descriptive_family_low'],r['descriptive_family_high'])])
        require(len(cr)==8 and len(rrows)==7,'Repeat rows thiếu')
        output('paper/generated/t04_repeats.tex',table(captions['T4'],'tab:repeats',[
            panel('A. Three executions: mean (sample SD)',['Panel/variant','Acc. (\\%)','BA (\\%)','BA range','Disagr. (\\%)','Return (\\%)'],rrows),
            panel('B. BA contrasts in percentage points',['Contrast','Mean','SD','Range','Percentile','Family env.'],cr)],
            'U: nine symbols/three dates/three blocks; F: eight symbols/four dates/three blocks. Each panel has nine units and UP/DOWN=2/7 per execution. Returns average nine U or eight F accounts per variant/execution. BA intervals retain 6,986 finite and 3,014 undefined draws of 10,000; envelopes are descriptive, not calibrated simultaneous coverage. U AS-B is separate from the seven F contrasts. Forty/147 groups deviate from listed variant order; nine span execution epochs.'))
        prim=load('final_temporal_v1/primary_dependence.json'); strata=load('final_temporal_v1/stratified_metrics.json'); head=select('final_baselines_v1/classification.csv',dimension='pooled',group='all');trows=[]
        for cohort,n,nd,nb,display in [('all_102',102,12,6,'All'),('eight_symbols_six_blocks',96,12,6,'Common eight'),('nine_symbols_three_recent_blocks',54,6,3,'Recent nine')]:
            # Alias chỉ đổi tên giữa hai receipts, không đổi mask/support dữ liệu.
            metric_cohort={'all_102':'all_102','eight_symbols_six_blocks':'common_eight_96','nine_symbols_three_recent_blocks':'recent_nine_54'}[cohort]
            a=one(head,cohort=metric_cohort,variant='AS');b=one(head,cohort=metric_cohort,variant='B');bounds=one(prim['cohorts'][cohort]['intervals'],contrast='AS-B')['percentile_95']
            require(int(a['n_valid'])==n and int(b['n_valid'])==n,'Cohort alias khác support')
            trows.append([display,str(n),str(nd),str(nb),num(a['balanced_accuracy'],100),num(b['balanced_accuracy'],100),num(float(a['balanced_accuracy'])-float(b['balanced_accuracy']),100),interval(*bounds)])
        trend=[]
        for name in ('bear','bull','sideways'):
            a=one(strata,cohort='all_102',dimension='trend',stratum=name,variant='AS');b=one(strata,cohort='all_102',dimension='trend',stratum=name,variant='B');m=a['metrics']
            trend.append([name.title(),str(a['n_units']),str(m['per_class']['UP']['support'])+'/'+str(m['per_class']['DOWN']['support']),num(m['balanced_accuracy'],100),num(b['metrics']['balanced_accuracy'],100),num(m['long_rate'],100),num(b['metrics']['long_rate'],100)])
        output('paper/generated/t05_temporal.tex',table(captions['T5'],'tab:temporal',[
            panel('A. Cohorts: BA percent; difference/interval in pp',['Cohort','$N$','Dates','Blocks','Full','Base','$\\Delta$','Interval'],trows),
            panel('B. Observed per-security trend contexts (percent)',['Trend','$N$','UP/DOWN','Full BA','Base BA','Full LONG','Base LONG'],trend)],
            'Cohorts overlap and are not pooled as extra samples. Trend uses past Close/SMA60 with strict +/-2\\% thresholds; it is not an index-regime policy. Primary intervals retain both dates, full cross-sections and pairing within blocks. HAC concerns accuracy rather than BA and is reported for both fixed-universe panels at lags 0/1/2 in S4.'))
        numeric=load('numeric_controls_v1/summary.json');rnd=load('numeric_controls_v1/random_dispersion.json');inf=load('numeric_controls_v1/inference.json');nrows=[]
        for label,strategy in [('Fixed custom five','fixed_custom5'),('Dynamic train top-five','dynamic_train_top5'),('Same IDs, no flip','dynamic_train_top5_no_flip')]:
            r=one(numeric['headline'],strategy=strategy)['pooled'];nrows.append([label,'1',num(r['accuracy'],100),num(r['balanced_accuracy'],100),num(r['mcc'],digits=3),'--'])
        d=rnd['pooled_trial_dispersion'];nrows.append(['Random eligible five','20',mean_sd(d['accuracy']['mean'],d['accuracy']['sd']),mean_sd(d['balanced_accuracy']['mean'],d['balanced_accuracy']['sd']),mean_sd(d['mcc']['mean'],d['mcc']['sd'],1,3),interval(d['balanced_accuracy']['min'],d['balanced_accuracy']['max'])])
        nr=[]
        for r in inf['contrasts'][:3]:
            label={'dynamic_vs_fixed':'Dynamic - fixed','dynamic_vs_random_mean':'Dynamic - random mean','dynamic_vs_no_flip':'Dynamic - no flip'}[r['contrast']]
            nr.append([label,num(r['balanced_accuracy_difference'],100),interval(*r['bootstrap_percentile_95']),num(r['p_exact_two_sided'],digits=4),num(r['p_holm_family_23'],digits=4)])
        output('paper/generated/t06_numeric.tex',table(captions['T6'],'tab:numeric',[
            panel('A. Pooled numeric results; random mean (SD)',['Strategy','Trials','Acc. (\\%)','BA (\\%)','MCC','Random BA range'],nrows),
            panel('B. Three primary contrasts; multiplicity family = 23',['Contrast','$\\Delta$BA (pp)','Percentile interval','Exact $p$','Holm $p$'],nr)],
            '$N=102$, UP/DOWN=25/77, 51 train-fit scopes. Numeric adapters/preprocessing are separate from the native LLM pipeline. All 20 random trials and all 23 contrasts remain in S3. Exact tests have 64 six-block sign assignments; percentile intervals are unadjusted, Holm uses the full 23-hypothesis family. No contrast rejects at 0.05.'))
        # Bảng khoa học appendix: không chép toàn code/state/schema vào bài.
        rules=[['MACD','Previous strict/current inclusive crossing first; otherwise histogram sign and change.','12/26/9; no Stochastic histogram.'],
               ['RSI',r'$\ge70$: bear; $\le30$: bull; $55\le x<70$: bull; $30<x\le45$: bear.','45--55 uses change against the third retained sample.'],
               ['Stochastic',r'Crossing precedes $\ge80$ bear / $\le20$ bull; interior fallback retained.','Legacy equality/zero-D truthiness is disclosed.'],
               [r'Williams \%R',r'$\ge-20$: bear; $\le-80$: bull; otherwise retained-sample direction.','Not a volatility vote.'],
               ['ROC',r'$>+0.5\%$: bull; $<-0.5\%$: bear; equality neutral.','Thresholds follow four-decimal rounding.']]
        output('paper/generated/a01_rules.tex',table('Indicator signal rules and missing-data conventions.','tab:indicator_rules',[
            panel('Five deterministic votes',['Signal','Priority and boundaries','Qualification'],rules,r'lp{7.1cm}p{5.2cm}')],
            'None/nonfinite values are removed, zero retained; rounding is to four decimals before classification. Retained samples need not be consecutive if missing. Missing/error gives a neutral vote within denominator five. Directional plurality, ties MIXED, and confidence are heuristics, not calibrated probabilities.'))
        formulas=[['FDM',r'$\tanh(0.5\,a_t V_t/ADV_{20,t})$','Native uses adjusted one-bar return, not the MACD display template.'],
                  ['SFA',r'$\tanh(1.5\tanh(H_t/(0.005C_t+\epsilon))+0.5a_t)$','Native uses MACD histogram and return, not sentiment; prototype has a distinct sentiment branch.'],
                  ['LVR',r'$\tanh(-0.8\,z_{20}((C_t-SMA_{5,t})/C_t))$','Rolling mean/SD conventions and partial windows are implementation-specific.'],
                  ['BFE',r'$\tanh(1.5(\%B_t-0.5)\,VolZ_{5,t})$','Negative VolZ reverses the sign; zero cancels. No squeeze or volume-expansion gate.'],
                  ['OFE',r'$\tanh(3a_t\,CP_t)$','OHLCV proxy, not measured signed order flow.']]
        output('paper/generated/a02_custom.tex',table('Custom native factor definitions and implementation distinctions.','tab:custom_definitions',[
            panel('Before global normalization and IC orientation',['ID','Native handler expression','Distinction'],formulas,r'lp{8.0cm}p{5.0cm}')],
            '$a_t$ is one-bar pct-change divided by rolling 20-bar sample SD (minimum five); $H_t$ is MACD(12,26,9) histogram; $CP_t$ is close location relative to the bar midpoint/range; ADV is mean Volume, not dollar volume. Guarded denominators and fills follow the registry. BFE registry sample-SD preprocessing differs from the rounded/population-SD prototype. Six selected metadata slots differ from their handler description, without the literal wrong formula in the affected prompts. A display rank of four does not identify BFE. Full expressions, guards and counterexamples are in the companion registry.'))
        symbols=select('final_baselines_v1/classification.csv',cohort='all_102',dimension='symbol');sr=[]
        for sym in sorted({r['group'] for r in symbols}):
            for v in ('AS','B'):
                r=one(symbols,group=sym,variant=v);per=load('final_baselines_v1/per_class.csv')
                sr.append([sym+'/'+LABELS[v],r['support_up']+'/'+r['support_down'],num(r['accuracy'],100),num(r['balanced_accuracy'],100),num(r['mcc'],digits=3),num(one(per,cohort='all_102',dimension='symbol',group=sym,variant=v,**{'class':'UP'})['recall'],100),num(one(per,cohort='all_102',dimension='symbol',group=sym,variant=v,**{'class':'DOWN'})['recall'],100)])
        output('paper/generated/a03_symbols.tex',table('Full and Base symbol-level results on their common historical support.','tab:symbol_results',[
            panel('Percent except MCC',['Symbol/variant','UP/DOWN','Acc.','BA','MCC','$R_U$','$R_D$'],sr)],
            'BHN contributes six eligible units, other symbols twelve; NA retains missing-class denominators. S1 additionally contains all nine classifiers for every symbol and both-class precision/recall/F1, with pooled and macro summaries.'))
        scenarios=load('execution_final_v1/scenario_summary.csv');xr=[]
        for s in dict.fromkeys(r['scenario'] for r in scenarios):
            a=one(scenarios,scenario=s,variant='AS');b=one(scenarios,scenario=s,variant='B')
            xr.append([esc(s),num(b['mean_account_net_return_pct'],digits=3),num(a['mean_account_net_return_pct'],digits=3),num(a['mean_difference_from_reference_pp'],digits=3),a['residual_stock_accounts'],a['pending_cash_accounts']])
        require(len(xr)==12,'Thiếu execution scenario')
        output('paper/generated/a04_execution.tex',table('All twelve account-execution sensitivities on unchanged predictions.','tab:execution',[
            panel('Means over 51 accounts per variant',['Scenario','Base (\\%)','Full (\\%)','$\\Delta$Full (pp)','Stock','Pending'],xr)],
            'Stock/Pending count Full accounts with residual shares/receivables; zero Full residuals do not imply none for other strategies. All 6,120 account executions are in the companion results. Fee/slippage, advance fees, sell charge, lots and capacity are assumptions. No-fill/delay proxies do not measure queue fills; all entries missed is not a mathematical worst bound.'))
        # Macros tránh chép tay headline numeric values trong abstract/results.
        a=one(c,variant='AS');b=one(c,variant='B');ec_a=one(economics,variant='AS');ec_b=one(economics,variant='B')
        bounds=one(prim['cohorts']['all_102']['intervals'],contrast='AS-B')['percentile_95']
        macros={'FullBA':num(a['balanced_accuracy'],100),'BaseBA':num(b['balanced_accuracy'],100),'FullAccuracy':num(a['accuracy'],100),'BaseAccuracy':num(b['accuracy'],100),
                'CashAccuracy':num(one(c,variant='constant_down_cash')['accuracy'],100),'LogisticPriceBA':num(one(c,variant='logistic_price')['balanced_accuracy'],100),
                'FullReturn':num(ec_a['mean_account_net_return_pct'],digits=3),'BaseReturn':num(ec_b['mean_account_net_return_pct'],digits=3),
                'DeltaBA':num(float(a['balanced_accuracy'])-float(b['balanced_accuracy']),100),'PrimaryLow':num(bounds[0],100),'PrimaryHigh':num(bounds[1],100)}
        output('paper/generated/summary_numbers.tex',('\n'.join(r'\newcommand{'+chr(92)+key+'}{'+value+'}' for key,value in macros.items())+'\n').encode())
        output('numeric_cells.json',encoded(values));output('headline_values.json',encoded(macros))
        # Đúng chart PNG bytes và calendar labels, không tạo/sửa empirical images.
        layout=load('manuscript_blueprint_v1/layout.json');f3=next(f for f in layout['figures'] if f['id']=='F3')
        for p in f3['panels']:
            sources.add(p['source']);png=base64.b64decode(read(root/p['source'])[p['field']],validate=True);require(digest(png)==p['png_sha256'],'Actual PNG khác')
            output('paper/figs/final_'+p['kind']+'.png',png)
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.colors import ListedColormap,BoundaryNorm
        import numpy as np
        calendar=select('final_temporal_v1/calendar_panel.csv',variant='B');require(len(calendar)==108,'Calendar support sai')
        dates=sorted({r['date'] for r in calendar});syms=sorted({r['symbol'] for r in calendar});grid=np.empty((9,12),dtype=int)
        for i,sym in enumerate(syms):
            for j,date in enumerate(dates):
                row=one(calendar,symbol=sym,date=date);grid[i,j]=0 if row['eligible']=='False' else 2 if row['label_net']=='UP' else 1
        require(int((grid==0).sum())==6 and int((grid==2).sum())==25,'Calendar mask/truth sai')
        fig,ax=plt.subplots(figsize=(9,4.8),layout='constrained');ax.imshow(grid,cmap=ListedColormap(['#eeeeee','#c9d9eb','#f3d3a0']),norm=BoundaryNorm([-.5,.5,1.5,2.5],3),aspect='auto')
        for i in range(9):
            for j in range(12):ax.text(j,i,['NA','D','U'][grid[i,j]],ha='center',va='center',fontsize=12)
        ax.set_xticks(range(12),[s for s in dates],rotation=45,ha='right');ax.set_yticks(range(9),syms)
        for x in (1.5,3.5,5.5,7.5,9.5):ax.axvline(x,color='white',linewidth=3)
        ax.set_title('Historical decision dates: U = UP, D = DOWN, NA = excluded',fontsize=12);ax.set_xlabel('Selected dates; gaps are not a continuous daily backtest')
        image=io.BytesIO();fig.savefig(image,format='png',dpi=180,metadata={'Software':'T32 frozen calendar export'});plt.close(fig)
        output('paper/figs/final_calendar.png',image.getvalue())
        # Scientific companions chỉ export dữ liệu đã có, không copy private reviewer text.
        companions={'S1_classification.csv':('final_baselines_v1/classification.csv',{'cohort':'all_102'}),'S1_per_class.csv':('final_baselines_v1/per_class.csv',{'cohort':'all_102'}),
                    'S1_macro.csv':('final_baselines_v1/macro.csv',{'cohort':'all_102'}),'S2_executions.csv':('final_repeats_v1/executions.csv',{}),
                    'S2_contrasts.csv':('final_repeats_v1/contrasts.csv',{}),'S2_disagreement.csv':('final_repeats_v1/disagreement.csv',{}),
                    'S4_calendar.csv':('final_temporal_v1/calendar_panel.csv',{}),'S4_HAC.csv':('final_temporal_v1/panel_hac.csv',{}),
                    'S4_block_sensitivity.csv':('final_temporal_v1/block_sensitivity.csv',{})}
        companion_counts={}
        for filename,(source,mask) in companions.items():
            rows=select(source,**mask);stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
            output('supplement/'+filename,stream.getvalue().encode());companion_counts[filename]=len(rows)
        for filename,source in {'S3_test_metrics.json':'numeric_controls_v1/test_metrics.json','S3_random_trials.json':'numeric_controls_v1/random_dispersion.json',
                                'S3_family.json':'numeric_controls_v1/inference.json','S4_regimes.json':'final_temporal_v1/stratified_metrics.json',
                                'S4_dependence.json':'final_temporal_v1/primary_dependence.json'}.items():output('supplement/'+filename,encoded(load(source)))
        # Metadata T21 là nguồn duy nhất cho bibliographic corrections đã duyệt.
        audit=load('reference_audit_v1/reference_audit.json');adds=load('reference_audit_v1/additions.json');entries={}
        for e in audit['entries']:
            proposed=e.get('proposed_bibliography')
            if proposed:entries[proposed['key']]=proposed
        for e in adds['entries']:entries[e['key']]=e
        settlement=load('execution_evidence_v1/sources.json')['sources']
        source=next(s for s in settlement if s['id']=='settlement_2022')
        entries['vsd2022settlement']={'entry_type':'misc','fields':{'author':'{Vietnam Securities Depository}',
            'title':'Settlement schedule announcement (19 August 2022)','year':'2022','url':source['url'],
            'note':'Historical settlement source reviewed in the execution-evidence audit; not a certification of account fills'}}
        bib=[]
        for key,e in sorted(entries.items()):
            lines=['@'+e['entry_type']+'{'+key+',']
            for field,val in e['fields'].items():
                if val is not None:lines.append('  '+field+' = {'+str(val)+'},')
            bib.append('\n'.join(lines+['}']))
        output('paper/references.bib',('\n\n'.join(bib)+'\n').encode())
        metadata={'parents':parents,'sources':[{'path':n,'sha256':file_hash(root/n)} for n in sorted(sources)],
                  'generated':[{'path':n,'sha256':digest(b)} for n,b in sorted(generated.items())],
                  'table_ids':['T1','T2','T3','T4','T5','T6','A1','A2','A3','A4'],'companion_counts':companion_counts,
                  'bibliography_entries':len(entries),'api_calls':0,'new_predictions':0,'statistics_refit':False}
        # Paths paper/ chỉ là generated tables/figures/bib, không ghi runtime/old outputs.
        for name,content in generated.items():
            target=root/name if name.startswith('paper/') and not artifact_only else folder/name
            target.parent.mkdir(parents=True,exist_ok=True);require(not target.exists() or name=='paper/references.bib','Không overwrite generated artifact: '+name)
            target.write_bytes(content)
        (folder/'generation.json').write_bytes(encoded(metadata))
        return metadata


def main() -> None:
    """Chỉ tạo source artifacts, không chạy pdflatex/BibTeX hoặc API."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',type=Path,default=RELEASE)
    parser.add_argument('--artifact-only',action='store_true',help='Ghi bản tái sinh trong release mới, không sửa paper hiện tại')
    parser.add_argument('--check',action='store_true',help='Chỉ kiểm source/receipt/runtime; không build hoặc render')
    args=parser.parse_args()
    if args.check:
        print('T32 kiểm offline: '+str(check_release(ROOT,args.release)))
        return
    m=build(ROOT,args.release,args.artifact_only);print(f"T32 generated: {len(m['generated'])} files; không API/refit/PDF build")


def check_release(root: Path,release: Path=RELEASE) -> dict:
    """Hash-check bản thảo hiện hành; source lịch sử chỉ qua ZIP đã khóa."""
    with offline_guard():
        folder=root/release;m=read(folder/'manifest.json')
        require(check_self_digest(m)=='pretty_sorted_utf8_lf','T32 self-digest sai')
        count=0
        for group,base in (('sources',root),('outputs',folder)):
            for row in m[group]:
                require(file_hash(base/row['path'])==row['sha256'],'T32 byte khác: '+row['path']);count+=1
        actual={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
        require(actual=={'manifest.json',*[r['path'] for r in m['outputs']]},'T32 file thừa/thiếu')
        from core.revision_minimal_bank import runtime
        from importlib.metadata import version
        observed={**runtime(),'jsonschema':version('jsonschema')}
        require(observed==read(root/'outputs/revision/final_regression_v1/report.json')['runtime_after'],'Runtime khác T28')
        parents=verify_parents(root,folder/'original_sources.zip')
        return {'source_output_hashes':count,'parent_references':{k:v['total'] for k,v in parents.items()},
                'historical_paper_references':{k:len(v['historical_paper_hashes']) for k,v in parents.items()},
                'scope':'Chỉ byte/runtime/ZIP bridge, không PDF QA hoặc chạy lại tests/inference'}


if __name__=='__main__':main()
