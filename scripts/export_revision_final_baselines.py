"""Xuất T24 từ T04/T20 đã khóa; không refit, gọi API hoặc ghi nguồn bài."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from core.revision_clean_metrics import Comparator, grouped
from core.revision_reproducibility import check_self_digest, digest, encoded, file_hash, offline_guard, read, require
from scripts.audit_revision_lineage import verify

OUTPUT=Path('outputs/revision/final_baselines_v1')
VARIANTS=('AS','B','constant_down_cash','train_majority','constant_up_cycles','momentum_20','logistic_price','logistic_matched_market_inputs','factor_only_vote')
LABELS={'AS':'Full','B':'Base','constant_down_cash':'CASH','train_majority':'Train-majority','constant_up_cycles':'Always-LONG cycles',
        'momentum_20':'Momentum 20','logistic_price':'Logistic price','logistic_matched_market_inputs':'Logistic matched inputs',
        'factor_only_vote':'Factor vote','continuous_hold_price_only':'Continuous hold (price-only)'}
COHORTS={'all_102':102,'common_eight_96':96,'recent_nine_54':54}


def subset(rows: list[dict], cohort: str) -> list[dict]:
    """Cohort cố định theo lịch/universe, không lọc theo outcomes."""
    require(cohort in COHORTS,'Cohort ngoài đặc tả')
    return [r for r in rows if cohort=='all_102' or cohort=='common_eight_96' and r['symbol']!='BHN' or cohort=='recent_nine_54' and r['fold'].startswith('f')]


def validate_panel(rows: list[dict]) -> None:
    """Từ chối thiếu/trùng/mismatch common support hoặc hold trộn vào classifier."""
    require(len(rows)==918 and {r['variant'] for r in rows}==set(VARIANTS),'Cần 102 units ×chín classifiers')
    indexed={(r['unit_id'],r['variant']):r for r in rows}
    require(len(indexed)==len(rows),'Trùng prediction identity')
    ids={r['unit_id'] for r in rows}; require(len(ids)==102,'Sai unit support')
    for uid in ids:
        paired=[indexed.get((uid,v)) for v in VARIANTS]; require(all(paired),'Thiếu paired variant')
        for field in ('symbol','date','fold','label_net','label_gross','market_input_hash'):
            require(len({r[field] for r in paired})==1,'Pair khác metadata: '+field)
        require(all(r['prediction'] in ('LONG','SHORT') and r['label_net'] in ('UP','DOWN') for r in paired),'Nhãn ngoài contract')
    require(len({(r['symbol'],r['date']) for r in rows})==102,'Trùng calendar unit')


def csv_bytes(rows: list[dict]) -> bytes:
    """CSV raw rates, undefined=NA; không mất integer supports."""
    stream=io.StringIO(newline=''); fields=list(dict.fromkeys(k for r in rows for k in r))
    writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n'); writer.writeheader()
    writer.writerows({k:'NA' if v is None else v for k,v in r.items()} for r in rows)
    return stream.getvalue().encode('utf-8')


def flatten(metrics: dict) -> dict:
    """Phân biệt support thật và số predictions của từng class."""
    return {**{k:v for k,v in metrics.items() if k not in ('confusion','per_class')},**metrics['confusion'],
            'support_up':metrics['per_class']['UP']['support'],'support_down':metrics['per_class']['DOWN']['support'],
            'predicted_long':metrics['per_class']['UP']['predicted'],'predicted_short':metrics['per_class']['DOWN']['predicted']}


def tables(rows: list[dict], accounts: list[dict], risk: list[dict]) -> tuple[dict,list,list,list,list]:
    """Tạo pooled/symbol/block, per-class và macro với denominator tường minh."""
    validate_panel(rows); classification=[]; per_class=[]; macro=[]; financial=[]; payload={}
    main=[r for r in accounts if r['panel']=='main' and r['execution']==0]
    require(len(main)==510 and all(sum(a['variant']==v for a in main)==51 for v in (*VARIANTS,'continuous_hold_price_only')),'Account support khác 51 scopes ×10 strategies')
    require(len({(r['variant'],r['symbol'],r['fold']) for r in main})==510,'Account trùng')
    risk_index={(r['variant'],r['symbol'],r['fold']):r for r in risk if r['release']=='T04' and r['panel']=='main' and r['execution']=='0'}
    require(len(risk_index)==510,'Risk không cùng main account support')
    for cohort,n in COHORTS.items():
        selected=subset(rows,cohort); require(len(selected)==n*9,'Cohort sai denominator'); payload[cohort]={}
        for v in VARIANTS:
            part=[r for r in selected if r['variant']==v]; metrics=grouped(part); payload[cohort][v]=metrics
            for dimension,items in [('pooled',{'all':metrics['pooled']}),('symbol',metrics['by_symbol']),('block',metrics['by_block'])]:
                for group,m in items.items():
                    support=part if dimension=='pooled' else [r for r in part if r['symbol' if dimension=='symbol' else 'fold']==group]
                    key={'cohort':cohort,'dimension':dimension,'group':group,'variant':v,'label':LABELS[v],
                         'n_symbols':len({r['symbol'] for r in support}),'n_dates':len({r['date'] for r in support}),'n_blocks':len({r['fold'] for r in support})}
                    classification.append({**key,**flatten(m)})
                    per_class.extend({**key,'class':name,**values} for name,values in m['per_class'].items())
            for metric,stats in metrics['macro_symbol'].items():
                macro.append({'cohort':cohort,'variant':v,'metric':metric,'n_units':n,'aggregation':'trung bình không trọng số từng mã, không là pooled',**stats})
        for v in (*VARIANTS,'continuous_hold_price_only'):
            part=[a for a in subset(main,cohort) if a['variant']==v]; require(bool(part),'Thiếu accounts')
            ratios=[risk_index[(v,a['symbol'],a['fold'])] for a in part]
            financial.append({'cohort':cohort,'variant':v,'label':LABELS[v],'n_accounts':len(part),
                'classification_units':0 if v=='continuous_hold_price_only' else n,
                'mean_account_net_return_pct':sum(a['net_return_pct'] for a in part)/len(part),
                'mean_account_drawdown_pct':sum(a['daily_close_drawdown_pct'] for a in part)/len(part),
                'mean_account_held_session_fraction':sum(a['held_session_fraction'] for a in part)/len(part),
                'mean_account_close_exposure':sum(a['mean_close_exposure'] for a in part)/len(part),
                'mean_account_order_count':sum(a['order_count'] for a in part)/len(part),
                **{f'{metric}_n_defined':sum(r[metric]!='NA' for r in ratios) for metric in ('sharpe_ratio','sortino_ratio')},
                **{f'{metric}_mean_given_defined':sum(float(r[metric]) for r in ratios if r[metric]!='NA')/sum(r[metric]!='NA' for r in ratios) if any(r[metric]!='NA' for r in ratios) else None for metric in ('sharpe_ratio','sortino_ratio')},
                'return_aggregation':'trung bình đều các accounts mã/block riêng, không là portfolio','ledger':'fractional reference, chưa chứng nhận fills'})
    return payload,classification,per_class,macro,financial


def check(root: Path, output: Path) -> int:
    """Hash-only, không tính lại bảng hoặc inference."""
    manifest=read(root/output/'manifest.json'); require(check_self_digest(manifest)=='pretty_sorted_utf8_lf','Self-digest T24 sai')
    count=0
    for group,base in (('sources',root),('outputs',root/output)):
        for row in manifest[group]: require(file_hash(base/row['path'])==row['sha256'],'T24 hash khác: '+row['path']); count+=1
    require({p.name for p in (root/output).iterdir()}=={'manifest.json',*[r['path'] for r in manifest['outputs']]},'T24 file thừa/thiếu')
    return count


def build(root: Path, output: Path) -> dict:
    """Chỉ xuất release mới dưới outputs/revision, bảo toàn các parents."""
    target=(root/output).resolve(); require(target.parent==(root/'outputs/revision').resolve() and not target.exists(),'Cần release mới, không paper/overwrite')
    with offline_guard():
        parents={name:verify(root/'outputs/revision'/name) for name in ('revision_minimal_final_v1','final_contracts_v1','clean_replay_v1')}
        final=root/'outputs/revision/revision_minimal_final_v1'
        names=['scripts/export_revision_final_baselines.py','tests/test_revision_final_baselines.py','core/revision_clean_metrics.py',
               'core/revision_reproducibility.py','scripts/audit_revision_lineage.py',
               'outputs/revision/revision_minimal_final_v1/manifest.json','outputs/revision/final_contracts_v1/manifest.json','outputs/revision/clean_replay_v1/manifest.json',
               'outputs/revision/revision_minimal_final_v1/main_predictions.json','outputs/revision/revision_minimal_final_v1/summary.json',
               'outputs/revision/revision_minimal_final_v1/main_cohorts.json','outputs/revision/revision_minimal_final_v1/accounts.json',
               'outputs/revision/final_contracts_v1/risk_daily.csv','outputs/revision/r1_72h_bank_v2/manifest.json',
               'outputs/revision/r1_72h_bank_v2/numeric/models.json','core/revision_baselines.py','core/revision72_analysis.py']
        sources=[{'path':n,'sha256':file_hash(root/n)} for n in names]
        rows=read(final/'main_predictions.json'); accounts=read(final/'accounts.json')
        with (root/'outputs/revision/final_contracts_v1/risk_daily.csv').open(encoding='utf-8',newline='') as handle: risk=list(csv.DictReader(handle))
        payload,classes,per_class,macro,financial=tables(rows,accounts,risk)
        comparator=Comparator(); original=read(final/'summary.json')
        for v in VARIANTS:
            expected={k:value for k,value in original['main_classification'][v].items() if k!='mean_account_net_return_pct'}
            comparator.check(expected,payload['all_102'][v],v)
        for cohort,key in [('common_eight_96','common_eight_six_blocks'),('recent_nine_54','recent_nine_three_blocks')]:
            comparator.check(read(final/'main_cohorts.json')[key],payload[cohort],cohort)
        contracts={'AS':'Full: Indicator/Pattern/Trend cộng native selected alpha và frozen sentiment context; tổng hợp ở prompt.',
            'B':'Base: shared upstream bỏ alpha/sentiment bundle; Full−Base là bundle contrast.',
            'constant_down_cash':'Luôn SHORT; ledger long-only là CASH. Không fit từ test labels.',
            'train_majority':'Majority chỉ từ purged train net labels; train mean >0,5 => LONG, hòa => SHORT.',
            'constant_up_cycles':'LONG từng cycle ba bars đã đăng ký; exit và trả phí từng cycle, CASH qua gaps.',
            'continuous_hold_price_only':'Một LONG từ entry đầu đến exit cuối của mã/block, giữ qua gaps. Không có classification prediction; total return gồm cổ tức/corporate actions chưa xác minh.',
            'momentum_20':'Price return 20 phiên quá khứ >0 => LONG; zero => SHORT.',
            'factor_only_vote':'Vote đều mọi factors cố định; medians/orientations chỉ từ train, khác native top-five và controls T13.',
            'logistic_price':'Chọn C/threshold bằng validation BA; final refit imputer/scaler/classifier trên purged train+validation; tái dùng predictions đã lưu.',
            'logistic_matched_market_inputs':'Raw OHLCV cộng selected factor numeric inputs và sentiment/missingness; không LLM/vision report embeddings. Cùng recipe validation, không chứng minh semantic-input equivalence.'}
        models=read(root/'outputs/revision/r1_72h_bank_v2/numeric/models.json')
        require(len(models)==51 and all(m['models'][v]['converged'] for m in models for v in ('logistic_price','logistic_matched_market_inputs')),'Thiếu fit/convergence receipt')
        model_rows=[{'symbol':m['symbol'],'fold':m['fold'],'variant':v,'train_rows':m['n_train'],'validation_rows':m['n_validation'],
                     'C':m['models'][v]['C'],'threshold':m['models'][v]['threshold'],'validation_ba':m['models'][v]['validation_ba'],
                     'n_columns':len(m['models'][v]['columns']),'converged':m['models'][v]['converged'],'reused_price_factor':m['reused_price_factor']} for m in models for v in ('logistic_price','logistic_matched_market_inputs')]
        main=[r for r in classes if r['cohort']=='all_102' and r['dimension']=='pooled']
        fin={r['variant']:r for r in financial if r['cohort']=='all_102'}
        headline=[{**r,'mean_account_net_return_pct':fin[r['variant']]['mean_account_net_return_pct'],'n_accounts':fin[r['variant']]['n_accounts']} for r in main]
        lines=['# Baselines và metrics cuối (T24)','',
            'Primary: net target; 102 units, 25 UP/77 DOWN, 12 selected dates, sáu historical blocks. Mọi classifier có đúng common support; BA primary, các tỷ lệ JSON/CSV thang 0–1.','',
            '| Strategy | N | Accuracy % | BA % | MCC | LONG % | Mean account return % |','|---|---:|---:|---:|---:|---:|---:|']
        def fmt(x: float | None,scale: float=1) -> str: return 'NA' if x is None else f'{x*scale:.4f}'
        lines += [f"| {r['label']} | {r['n_valid']} | {fmt(r['accuracy'],100)} | {fmt(r['balanced_accuracy'],100)} | {fmt(r['mcc'])} | {fmt(r['long_rate'],100)} | {fmt(r['mean_account_net_return_pct'])} |" for r in headline]
        hold=fin['continuous_hold_price_only']
        lines += ['',f"Continuous hold price-only: classification NA; {hold['n_accounts']} accounts, mean account return {fmt(hold['mean_account_net_return_pct'])}%, held-session fraction {fmt(hold['mean_account_held_session_fraction'])}. Always-LONG cycles là comparator khác, không thay hold hoặc gán 102 classifier observations cho hold.",
            '', 'Full−Base BA = '+fmt(original['main_classification']['AS']['pooled']['balanced_accuracy']-original['main_classification']['B']['pooled']['balanced_accuracy'],100)+' percentage points. Full thấp hơn logistic-price về BA; mọi mean return khác CASH/train-majority trong bảng đều âm. Đây không phải evidence superiority, alpha hoặc profitability.',
            '', 'Pooled gộp confusion cells theo units; macro là trung bình không trọng số của metrics từng mã, kèm n_planned/n_defined. BA/MCC/F1 undefined giữ null/NA, không ép zero. CASH/train-majority có accuracy 77/102 nhờ imbalance, BA 0.5, MCC undefined. Train-majority coincides with CASH trên test không có nghĩa đã fit từ test majority.',
            '', 'Mean return là bình quân 51 symbol/block accounts với các cửa sổ lịch khác nhau, không portfolio return hoặc total-return index. Reference ledger chưa chứng nhận executable fills, settlement/tax/dividend realism; sensitivities T19 giữ riêng. Risk n_defined/mean_given_defined có denominator riêng; Sortino negative-subset SD legacy, không RMS.',
            '', 'Giữ giới hạn study historical exploratory: native row-wise causal T10 FAIL, news PIT/domain validation chưa xác thực, 40 paired groups lệch order và chín cross-epoch groups. Numeric train-fit không chứng nhận ngược native inputs; hosted immutable revisions chưa biết. Không gộp repeats vào main 102 hoặc trộn study trước/sau sửa chart.',
            '', '## Artifacts', '',
            '- [Classification pooled/symbol/block](classification.csv), [per-class](per_class.csv), [macro](macro.csv), [headline](main_comparison.csv).',
            '- [Financial aggregation](financial.csv), [510 main accounts](accounts.csv), [stored logistic fits](model_settings.csv), [contracts](baseline_contracts.json), [metrics JSON](metrics.json).',
            '- Cohorts all_102/common_eight_96/recent_nine_54 chồng lấn, không cộng thành observations độc lập; temporal/regime/dependence thuộc T25.',
            '', 'Chỉ thêm bảng phân tích, không inference/refit/sửa predictions hoặc paper. T04/T20/T23 parent hashes khớp; không chạy lại toàn suite/E2E/leakage vì không đổi producer/feature/PIT/ledger. Tests chỉ kiểm support, hold, undefined và CSV. R1 còn bài/response/locators sau T30; chưa đóng reviewer.',
            '', '## Tái xuất offline', '', '```powershell','py -3.13 -X utf8 scripts/export_revision_final_baselines.py check',
            'py -3.13 -X utf8 scripts/export_revision_final_baselines.py build --output outputs/revision/final_baselines_recheck_v1','```','']
        qa={'status':'PASS','parent_hashes':parents,'classifiers':9,'main_prediction_rows':918,'main_accounts':510,'comparison':vars(comparator),
            'classification_rows':len(classes),'per_class_rows':len(per_class),'macro_rows':len(macro),'financial_rows':len(financial),'stored_logistic_settings':len(model_rows),
            'api_calls':0,'baseline_fits':0,'new_predictions':0,'scope':'Chỉ export từ frozen outcomes, không nghiệm thu bản thảo/R1.'}
        outputs={'metrics.json':encoded(payload),'classification.csv':csv_bytes(classes),'per_class.csv':csv_bytes(per_class),
                 'macro.csv':csv_bytes(macro),'financial.csv':csv_bytes(financial),'main_comparison.csv':csv_bytes(headline),
                 'accounts.csv':csv_bytes([a for a in accounts if a['panel']=='main' and a['execution']==0]),'model_settings.csv':csv_bytes(model_rows),
                 'baseline_contracts.json':encoded(contracts),'qa.json':encoded(qa),'report.md':'\n'.join(lines).encode('utf-8')}
        for row in sources: require(file_hash(root/row['path'])==row['sha256'],'Nguồn đổi lúc export')
        target.mkdir()
        for name,data in outputs.items(): (target/name).write_bytes(data)
        manifest={'schema_version':'final_baselines_v1','sources':sources,'outputs':[{'path':n,'sha256':digest(b)} for n,b in sorted(outputs.items())]}
        manifest['sha256']=digest(encoded(manifest)); (target/'manifest.json').write_bytes(encoded(manifest)); check(root,output)
        return qa


def main() -> None:
    """Build release mới hoặc chỉ check hashes đã khóa."""
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('command',choices=('build','check')); parser.add_argument('--output',type=Path,default=OUTPUT); args=parser.parse_args()
    if args.command=='check': print(f'T24 hashes PASS: {check(ROOT,args.output)}')
    else: print('T24 PASS: '+json.dumps(build(ROOT,args.output),ensure_ascii=False))


if __name__=='__main__': main()
