"""T25 temporal/regime/dependence trên final T04; không inference hoặc sửa bài."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from datetime import datetime
import csv
import gzip
import json
import math
from pathlib import Path
import platform
import sys
from typing import Iterator
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import numpy as np
import pandas as pd
import scipy

from core.revision_baselines import load_prices
from core.revision_clean_metrics import classification
from core.revision_common_study import native
from core.revision_dependent_statistics import circular_weights, discordance, hac_summary, percentile_summary, score_samples
from core.revision_r2_panel import POLICY, audit_fold, calendar_panel, classify_context, cohort_dependence, context_features, group_metrics
from core.revision_r3_repeats import array_metrics
from core.revision_reproducibility import check_self_digest, digest, encoded, file_hash, offline_guard, read, require
from scripts.audit_revision_lineage import verify
from scripts.export_revision_final_baselines import COHORTS, VARIANTS, csv_bytes, flatten, subset, validate_panel

OUTPUT=Path('outputs/revision/final_temporal_v1')


@contextmanager
def analysis_guard() -> Iterator[None]:
    """Chặn network/key loader/classifier fit, chỉ fit median regime từ train."""
    with offline_guard(),ExitStack() as stack:
        for name in ('dotenv.load_dotenv','langchain_groq.ChatGroq.invoke','core.revision_baselines.logistic_predictions',
                     'core.revision_baselines.factor_vote','sklearn.linear_model.LogisticRegression.fit',
                     'sklearn.impute.SimpleImputer.fit','sklearn.preprocessing.StandardScaler.fit'):
            stack.enter_context(patch(name,side_effect=AssertionError('T25 chỉ phân tích offline, không fit classifier/API')))
        yield


def cohort(rows: list[dict], name: str) -> dict:
    """Tensor paired whole-block đúng universe/mask, không flatten symbols/repeats."""
    part=subset(rows,name); units=sorted([r for r in part if r['variant']=='AS'],key=lambda r:(r['date'],r['symbol']))
    require(len(units)==COHORTS[name],'Cohort sai support')
    blocks=sorted({r['fold'] for r in units},key=lambda b:min(r['date'] for r in units if r['fold']==b))
    indexed={(r['unit_id'],r['variant']):r for r in part}; require(len(indexed)==len(part),'Prediction trùng')
    truth=np.asarray([r['label_net']=='UP' for r in units]); indices=np.asarray([blocks.index(r['fold']) for r in units]); matrices=[]; predictions=[]
    for v in VARIANTS:
        require(all((u['unit_id'],v) in indexed for u in units),'Thiếu paired variant')
        p=np.asarray([indexed[(u['unit_id'],v)]['prediction']=='LONG' for u in units])
        cells=np.where(truth,np.where(p,0,1),np.where(p,3,2)); matrices.append(np.bincount(indices*4+cells,minlength=len(blocks)*4).reshape(len(blocks),4)); predictions.append(p)
    return {'name':name,'units':units,'blocks':blocks,'truth':truth,'predictions':np.asarray(predictions),'counts':np.asarray(matrices)}


def date_hac(rows: list[dict], lags: list[int]) -> tuple[list[dict],list[dict]]:
    """HAC chỉ cho hai rectangles fixed-universe theo selected-date order."""
    daily=[]; result=[]
    for name in ('common_eight_96','recent_nine_54'):
        data=cohort(rows,name); units=data['units']; dates=sorted({r['date'] for r in units}); symbols=sorted({r['symbol'] for r in units})
        require(len(units)==len(dates)*len(symbols) and len({(r['date'],r['symbol']) for r in units})==len(units),'Fixed-universe không rectangular')
        differences=(data['predictions'][0]==data['truth']).astype(float)-(data['predictions'][1]==data['truth'])
        series=differences.reshape(len(dates),len(symbols)).mean(axis=1)
        daily.extend({'cohort':name,'date':date,'n_symbols':len(symbols),'weight_per_symbol':1/len(symbols),'accuracy_difference':float(value)} for date,value in zip(dates,series))
        result.extend({'cohort':name,'contrast':'AS-B','metric':'accuracy','n_units':len(units),'n_symbols':len(symbols),**hac_summary(series,lag)} for lag in lags)
    return daily,result


def check(root: Path, output: Path) -> int:
    """Chỉ kiểm bytes/runtime/index, không tái chạy statistics/null simulation."""
    folder=root/output; manifest=read(folder/'manifest.json'); require(check_self_digest(manifest)=='pretty_sorted_utf8_lf','Self-digest T25 sai')
    require(manifest['runtime']=={'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'scipy':scipy.__version__},'Runtime T25 khác')
    count=0
    for group,base in (('sources',root),('outputs',folder)):
        for row in manifest[group]: require(file_hash(base/row['path'])==row['sha256'],'T25 hash khác: '+row['path']); count+=1
    require({p.name for p in folder.iterdir()}=={'manifest.json',*[r['path'] for r in manifest['outputs']]},'T25 file thừa/thiếu')
    return count


def build(root: Path, output: Path) -> dict:
    """Khóa parents, tính final diagnostics mới, giữ nguyên artifacts cũ."""
    folder=(root/output).resolve(); require(folder.parent==(root/'outputs/revision').resolve() and not folder.exists(),'Cần release mới, không paper/overwrite')
    with analysis_guard():
        parents={name:verify(root/'outputs/revision'/name) for name in ('revision_minimal_final_v1','final_baselines_v1','r2_panel_v1','dependent_statistics_v1','clean_replay_v1')}
        final=root/'outputs/revision/revision_minimal_final_v1'; bank=root/'outputs/revision/r1_72h_bank_v2'; old=root/'outputs/revision/r2_panel_v1'; previous=root/'outputs/revision/dependent_statistics_v1'
        source_names=['scripts/analyze_revision_final_dependence.py','tests/test_revision_final_dependence.py','tests/test_revision_r2_leakage.py',
            'core/revision_r2_panel.py','core/revision_dependent_statistics.py','core/revision_r3_repeats.py','utils/statistical_tests.py',
            'core/revision_baselines.py','core/revision72_analysis.py','scripts/export_revision_final_baselines.py','core/revision_reproducibility.py',
            'core/revision_clean_metrics.py','core/revision_common_study.py','scripts/audit_revision_lineage.py','revision/r5_statistics_policy.json']
        for name in parents: source_names.append(f'outputs/revision/{name}/manifest.json')
        source_names +=['outputs/revision/revision_minimal_final_v1/'+n for n in ('main_predictions.json','summary.json','daily_ledgers.json.gz','attempts.json')]
        source_names +=['outputs/revision/r1_72h_bank_v2/manifest.json','outputs/revision/r2_panel_v1/regime_labels.csv',
                         'outputs/revision/r2_panel_v1/folds.csv','outputs/revision/revision_minimal_v1/manifest.json',
                         'outputs/revision/clean_replay_v1/metrics_qa.json']
        source_names +=['outputs/revision/dependent_statistics_v1/'+n for n in ('null_coverage.json','policy.json','report.json','legacy_diagnostics.csv')]
        price_manifest=read(root/'outputs/revision/r1_prices_v1/manifest.json')
        source_names +=['outputs/revision/r1_prices_v1/manifest.json',*['outputs/revision/r1_prices_v1/'+r['path'] for r in price_manifest['symbols']]]
        sources=[{'path':n,'sha256':file_hash(root/n)} for n in sorted(set(source_names))]
        rows=read(final/'main_predictions.json'); validate_panel(rows); definition=read(bank/'manifest.json'); protocol=definition['protocol']; units=definition['units']
        frames,quality=load_prices(root/protocol['price_snapshot'],protocol['price_quality_policy']); scopes={(s['symbol'],s['fold']):s for s in definition['schedule']}
        features={s:context_features(frame) for s,frame in frames.items()}; folds=[audit_fold(frames[s['symbol']],s,protocol) for s in definition['schedule']]
        contexts={u['id']:{'unit_id':u['id'],'symbol':u['symbol'],'fold':u['fold'],'date':u['date'],'analysis_decision_index':u['decision'],
                            **classify_context(features[u['symbol']],scopes[(u['symbol'],u['fold'])]['train'],u['decision'])} for u in units}
        with (old/'regime_labels.csv').open(encoding='utf-8',newline='') as handle: old_contexts={r['unit_id']:r for r in csv.DictReader(handle)}
        require(old_contexts.keys()==contexts.keys(),'Regime source khác units')
        for uid,value in contexts.items():
            for field,actual in value.items():
                expected=old_contexts[uid][field]
                if isinstance(actual,(int,float)):
                    require(math.isclose(float(expected),actual,rel_tol=1e-10,abs_tol=1e-12) or not math.isfinite(actual) and not math.isfinite(float(expected)),'Regime numeric khác frozen source')
                else: require(expected==actual,'Regime label/metadata khác source')
        with (old/'folds.csv').open(encoding='utf-8',newline='') as handle: old_folds={(r['symbol'],r['fold']):r for r in csv.DictReader(handle)}
        for f in folds:
            original=old_folds[(f['symbol'],f['fold'])]
            require(all(str(v)==original[k] for k,v in f.items()),'Purge/fold khác source')
        panel=calendar_panel(units,rows,sorted(frames))
        require(len(panel)==972 and int((~panel['eligible']).sum())==54,'Panel mask khác 12×9×9/918')
        # Chỉ lấy main r0/n0 ledgers; repeats không là dữ liệu thị trường bổ sung.
        ledgers={(r['symbol'],r['fold'],r['variant'],r['date']):r for r in json.loads(gzip.decompress((final/'daily_ledgers.json.gz').read_bytes())) if r['panel']=='main' and r['execution']==0}
        meta={u['id']:u for u in units}; exposure={}; target_rows=[]
        for r in rows:
            u=meta[r['unit_id']]; dates=frames[u['symbol']]['date'].iloc[u['decision']+1:u['decision']+4].tolist()
            observed=[ledgers[(r['symbol'],r['fold'],r['variant'],day)] for day in dates]
            held=sum(d['held_during_session'] for d in observed); close=sum(d['close_exposure'] for d in observed)
            require(held==3*int(r['prediction']=='LONG') and close==2*int(r['prediction']=='LONG'),'Target exposure khác ledger')
            exposure[(r['unit_id'],r['variant'])]={'dates':dates,'target_sessions':3,'held_sessions':held,'close_sessions':close}
            target_rows.append({'unit_id':u['id'],'variant':r['variant'],'symbol':u['symbol'],'fold':u['fold'],'decision_date':u['date'],
                                'target_dates':'|'.join(dates),'target_sessions':3,'held_sessions':held,'close_sessions':close})
        regimes=[]
        for name in COHORTS: regimes.extend({'cohort':name,**r} for r in group_metrics(subset(rows,name),contexts,exposure))
        stratified=[{**{k:v for k,v in r.items() if k not in ('metrics','exposure_scope')},**flatten(r['metrics'])} for r in regimes]
        temporal=[]
        for dimension,field in [('date','date'),('block','fold')]:
            for group in sorted({r[field] for r in rows}):
                for v in VARIANTS:
                    part=[r for r in rows if r[field]==group and r['variant']==v]
                    temporal.append({'dimension':dimension,'group':group,'variant':v,'n_symbols':len({r['symbol'] for r in part}),
                        'n_dates':len({r['date'] for r in part}),**flatten(classification([r['label_net'] for r in part],[r['prediction'] for r in part]))})
        primary=cohort_dependence(rows); original=read(final/'summary.json')['main_BA_contrasts']
        require(primary['cohorts']['all_102']['intervals']==[{k:v for k,v in r.items() if k!='observed_BA_delta'} for r in original],'Primary T04 intervals không khớp')
        policy=read(root/'revision/r5_statistics_policy.json'); sensitivity=[]; disc=[]
        for name in COHORTS:
            data=cohort(rows,name); point=array_metrics(data['counts'].sum(axis=1))
            for length in policy['block_lengths']:
                weights=circular_weights(len(data['blocks']),length,policy['bootstrap_draws'],policy['seed']); samples=score_samples(data['counts'],weights)
                for index,v in enumerate(VARIANTS[1:],1):
                    for metric in ('balanced_accuracy','accuracy'):
                        sensitivity.append({'cohort':name,'contrast':'AS-'+v,'metric':metric,'n_units':len(data['units']),
                            'n_dates':len({u['date'] for u in data['units']}),'n_blocks':len(data['blocks']),'block_length':length,
                            'point_difference':float(point[metric][0]-point[metric][index]),**percentile_summary(samples[metric][0]-samples[metric][index])})
            disc.append({'cohort':name,'group':'pooled','contrast':'AS-B',**discordance(data['truth'],data['predictions'][0],data['predictions'][1])})
        for symbol in sorted(frames):
            part=[r for r in rows if r['symbol']==symbol]; indexed={(r['unit_id'],r['variant']):r for r in part}; us=sorted({r['unit_id'] for r in part})
            y=np.asarray([indexed[(u,'AS')]['label_net']=='UP' for u in us]); a=np.asarray([indexed[(u,'AS')]['prediction']=='LONG' for u in us]); b=np.asarray([indexed[(u,'B')]['prediction']=='LONG' for u in us])
            disc.append({'cohort':'all_102','group':symbol,'contrast':'AS-B',**discordance(y,a,b)})
        date_scores,hac=date_hac(rows,policy['hac']['lags'])
        null=read(previous/'null_coverage.json'); require(read(previous/'policy.json')==policy and len(null)==18,'Null audit policy/rows khác')
        null_reference={'source_release':'outputs/revision/dependent_statistics_v1','policy_sha256':file_hash(previous/'policy.json'),
            'null_coverage_sha256':file_hash(previous/'null_coverage.json'),'rows_reused':len(null),'new_simulated_panels':0,
            'coverage_range_given_defined':[min(r['coverage_given_defined'] for r in null),max(r['coverage_given_defined'] for r in null)],
            'scope':'Tái dùng nguyên null audit stylized; không chạy lại, không chọn length theo coverage hoặc xác nhận DGP/95% coverage của dữ liệu thật.',
            'legacy_support':read(previous/'report.json')['legacy_support']}
        freeze=read(root/'outputs/revision/revision_minimal_v1/manifest.json')['created_utc']; attempts=read(final/'attempts.json')
        contamination={'final_queue_freeze_utc':freeze,'first_request_utc':min(r['started_at_utc'] for r in attempts),'last_request_utc':max(r['started_at_utc'] for r in attempts),
            'n_decision_dates_after_final_queue_freeze':sum(u['date']>freeze[:10] for u in units),
            'n_label_dates_after_final_queue_freeze':sum(str(frames[u['symbol']]['date'].iloc[u['decision']+3])>freeze[:10] for u in units),
            'immutable_served_weight_revision':None,'observed_model_metadata_source':'outputs/revision/clean_replay_v1/metrics_qa.json',
            'prospective_holdout_certified':False,'scope':'Historical exploratory sau amendment; không xác minh training-data exclusion/memorization, PIT news/domain hoặc survivorship-free universe.'}
        report={'status':'PASS_EXPLORATORY_FINAL_TEMPORAL','parent_hashes':parents,'n_units':102,'n_selected_dates':12,'n_blocks':6,'n_symbols':9,
            'panel_cells':len(panel),'eligible_prediction_cells':int(panel['eligible'].sum()),'missing_prediction_cells':int((~panel['eligible']).sum()),
            'missing_market_cells':6,'regime_units_recomputed':len(contexts),'purged_folds_rechecked':len(folds),
            'cohorts':{n:{k:d[k] for k in ('n_units','n_dates','n_blocks','n_symbols')} for n,d in primary['cohorts'].items()},
            'temporal_rows':len(temporal),'regime_rows':len(regimes),'cbb_rows':len(sensitivity),'hac_rows':len(hac),'date_scores':len(date_scores),'discordance_rows':len(disc),
            'null_reused_not_rerun':True,'api_calls':0,'new_predictions':0,'classifier_fits':0,
            'scope':'R2/R5 descriptive audit cuối; không kiểm định superiority/alpha, không đóng reviewer hoặc T30.'}
        lines=['# Temporal, regime và dependence cuối (T25)','',
            'Chỉ main T04 realization 0/repeat 0 trên cùng T24; không trộn old chart study hoặc tăng N bằng repeats. 102 units/12 selected dates/sáu historical blocks, không là 102 market replications độc lập.','',
            '| Cohort | Units | Symbols | Dates | Blocks |','|---|---:|---:|---:|---:|']
        lines += [f"| {n} | {d['n_units']} | {d['n_symbols']} | {d['n_dates']} | {d['n_blocks']} |" for n,d in primary['cohorts'].items()]
        lines += ['', 'Grid 12 dates ×9 symbols có 108 market cells: 102 eligible, sáu BHN cells early blocks thiếu vì valid-suffix/warm-up. Prediction grid chín classifiers: 972 cells, 918 eligible, 54 NA; không backfill CASH. Cohorts chồng lấn, không cộng N.',
            '', '## Dependence', '', '| Cohort | Lag | Mean accuracy difference | SE | HAC p |','|---|---:|---:|---:|---:|']
        def fmt(x: float | None) -> str: return 'NA' if x is None else f'{x:.6f}'
        lines += [f"| {r['cohort']} | {r['lag']} | {fmt(r['mean'])} | {fmt(r['standard_error'])} | {fmt(r['p_value'])} |" for r in hac]
        for r in disc[:3]: lines.append(f"\n{r['cohort']} Full-only/Base-only correct = {r['full_only_correct']}/{r['base_only_correct']}; discordant {r['n_discordant']}, exact diagnostic p={fmt(r['exact_p_value'])} (giả định independent discordances chưa được chứng nhận).")
        lines += ['', 'HAC là accuracy difference theo ngày trên universe cố định 1/8 hoặc 1/9; lags 0/1/2 đếm selected-date order, không phiên giao dịch liên tiếp. SE/CI/p dùng Bartlett/t(df=dates−1), chỉ sensitivity với 12 hoặc sáu ngày; zero variance cho null/NA. Không pooled HAC cho all_102 vì universe thay đổi ở BHN.',
            '', 'Primary whole-block intervals T04 giữ nguyên; CBB bổ sung đầy đủ tám contrasts ×BA/accuracy ×ba lengths ×ba cohorts. Length đo bằng study blocks (wrap circular), không trading-day length. Recent cohort chỉ ba blocks: length=3 luôn lấy toàn bộ block set nên interval suy biến, không chứng minh precision. Sáu leave-one-block-out chỉ sensitivity, không chọn giai đoạn đẹp.',
            '', f"Tái dùng {len(null)} rows null audit đã khóa, không mô phỏng lại. Zero coverage conditional trong DGP stylized nằm [{null_reference['coverage_range_given_defined'][0]:.6f}, {null_reference['coverage_range_given_defined'][1]:.6f}], không đạt chứng nhận 95% coverage thị trường; không chọn length hoặc hiệu chỉnh interval thật theo kết quả này. Wilson MC intervals/defined/undefined đầy đủ tại nguồn cũ.",
            '', 'Legacy 180 records/chín mã/53 dates và zero date chung cho cả chín mã giữ trong audit legacy riêng; exact/NW diagnostics cũ không là final effect hoặc pooled HAC. Provenance legacy vẫn unverified theo T15.',
            '', '## Regime và provenance', '',
            'Tái tính 102 contexts và kiểm 51 purged folds, khớp labels/medians/folds R2 cũ; không fit lại classifier/preprocessor. Trend = Close/SMA60−1, bull >2%, bear <−2%, còn lại sideways; vol = SD20 returns ddof=1; liquidity proxy = MA20(Close×Volume) theo vendor units. High/low dùng median chỉ trên purged train; ngưỡng suy biến/thiếu lịch sử là unknown. Đây là post-inference descriptive strata, không regime-aware policy confirmatory hoặc chứng nhận PIT/corporate-action-adjusted universe.',
            '', 'Báo đủ observed strata/cohorts/variants, class supports và null metrics. Exposure đối soát trên ba target sessions/unit từ final daily ledger, không là exposure calendar/portfolio có gaps. Toàn bộ labels đã trưởng thành trước freeze cuối; historical points có thể bị model training contamination/memorization, không có untouched prospective holdout được xác nhận. Immutable hosted revisions, news PIT/domain validity và native row-wise causal gate vẫn chưa đạt; không suy alpha/profitability từ subgroup/CI/p.',
            '', '## Artifacts', '',
            '- [Temporal date/block](temporal_metrics.csv), [calendar panel](calendar_panel.csv), [regime contexts](regime_labels.csv), [purged folds](folds.csv).',
            '- [Stratified metrics](stratified_metrics.json), [regime table](regime_metrics.csv), [target exposure](target_sessions.csv).',
            '- [Primary/cohort/leave-block diagnostics](primary_dependence.json), [CBB](block_sensitivity.csv), [HAC](panel_hac.csv), [date scores](date_scores.csv), [discordance](discordance.csv).',
            '- [Null/legacy reuse](null_reuse.json), [contamination scope](contamination.json), [report](report.json), [hashes](manifest.json).',
            '', 'Chỉ thêm analysis độc lập, không API/inference/refit hoặc sửa paper/frozen outcomes. Kiểm tests theo phạm vi: regime/PIT leakage, dependent-statistics regressions và final cohort/HAC wiring; không full suite/E2E/null simulation rerun. R2/R5 còn bài/response/locators sau T30.',
            '', '```powershell','py -3.13 -X utf8 scripts/analyze_revision_final_dependence.py check',
            'py -3.13 -X utf8 scripts/analyze_revision_final_dependence.py build --output outputs/revision/final_temporal_recheck_v1','```','']
        outputs={'report.json':encoded(report),'protocol.json':encoded({'regime':POLICY,'statistics_policy_sha256':file_hash(root/'revision/r5_statistics_policy.json'),'analysis_timing':'Post-inference, không preregistered.'}),
            'regime_labels.csv':csv_bytes([native(v) for v in contexts.values()]),'folds.csv':csv_bytes(folds),'calendar_panel.csv':panel.to_csv(index=False,na_rep='NA',lineterminator='\n').encode('utf-8'),
            'temporal_metrics.csv':csv_bytes(temporal),'stratified_metrics.json':encoded(native(regimes)),'regime_metrics.csv':csv_bytes(native(stratified)),
            'target_sessions.csv':csv_bytes(target_rows),'primary_dependence.json':encoded(native(primary)),'block_sensitivity.csv':csv_bytes(sensitivity),
            'block_sensitivity.json':encoded(native(sensitivity)),'date_scores.csv':csv_bytes(date_scores),'panel_hac.csv':csv_bytes(hac),'panel_hac.json':encoded(native(hac)),
            'discordance.csv':csv_bytes(disc),'null_reuse.json':encoded(null_reference),'contamination.json':encoded(contamination),'report.md':'\n'.join(lines).encode('utf-8')}
        for row in sources: require(file_hash(root/row['path'])==row['sha256'],'Nguồn đổi lúc T25')
        folder.mkdir()
        for name,data in outputs.items(): (folder/name).write_bytes(data)
        manifest={'schema_version':'final_temporal_v1','runtime':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'scipy':scipy.__version__},
                  'sources':sources,'outputs':[{'path':n,'sha256':digest(b)} for n,b in sorted(outputs.items())]}
        manifest['sha256']=digest(encoded(manifest)); (folder/'manifest.json').write_bytes(encoded(manifest)); check(root,output)
        return report


def main() -> None:
    """Build release mới hoặc chỉ check byte/runtime cũ."""
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('command',choices=('build','check')); parser.add_argument('--output',type=Path,default=OUTPUT); args=parser.parse_args()
    if args.command=='check': print(f'T25 hashes PASS: {check(ROOT,args.output)}')
    else: print('T25 PASS: '+json.dumps(build(ROOT,args.output),ensure_ascii=False))


if __name__=='__main__': main()
