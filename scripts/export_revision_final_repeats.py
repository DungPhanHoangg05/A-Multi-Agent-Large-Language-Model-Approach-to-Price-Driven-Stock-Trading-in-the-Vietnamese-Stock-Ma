"""T26: xuất repeats/factorial/placebo đúng final support và actual raw parents."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import numpy as np

from core.revision_baselines import load_prices
from core.revision_clean_metrics import Comparator, clean, raw_prediction
from core.revision_common_study import digest as identity_hash, native
from core.revision_minimal_analysis import offline_guard as frozen_guard, repeat_panel
from core.revision_minimal_audit import audit_pairing
from core.revision_minimal_bank import collect, verify_manifest
from core.revision72_analysis import target
from core.revision72_run import checked
from core.revision_r3_repeats import METRICS, describe
from core.revision_r4_factorial import CONTRASTS, VARIANTS, actual_text, availability, donor_factors, factor_rows, prompt_parts, validate_donor
from core.revision_reproducibility import check_self_digest, digest, encoded, file_hash, offline_guard, read, require
from scripts.audit_revision_lineage import verify
from scripts.export_revision_final_baselines import csv_bytes, flatten

OUTPUT=Path('outputs/revision/final_repeats_v1')


def validate_panel_summary(panel: dict, variants: tuple[str,...]) -> None:
    """Từ chối thiếu run/variant hoặc gộp 27 decisions thành 27 market units."""
    require(panel['n_units_per_execution']==9 and panel['n_executions']==3,'Cần đúng chín units và ba executions')
    require(panel['support_per_execution']=={'UP':2,'DOWN':7},'Panel khác true support')
    require(panel['n_decisions']==9*3*len(variants) and panel['n_unique_successful_requests']==panel['n_decisions'],'Raw response support khác')
    keys={(r['variant'],r['execution']) for r in panel['by_execution']}
    require(keys=={(v,i) for v in variants for i in range(3)} and len(panel['by_execution'])==len(keys),'Thiếu/trùng execution')
    require(set(panel['summaries'])==set(variants),'Thiếu variant summary')
    for v in variants:
        selected=[r for r in panel['by_execution'] if r['variant']==v]
        for row in selected:
            require(row['pooled']['n_valid']==9 and row['pooled']['per_class']['UP']['support']==2 and row['pooled']['per_class']['DOWN']['support']==7,'Execution sai denominator')
        for m in METRICS:
            expected=describe([r[m] for r in selected])
            require(expected==panel['summaries'][v][m],'Summary đã bỏ/chọn execution')
    require(len(panel['disagreement'])==9*len(variants),'Disagreement không đủ cutoffs')


def best_single_diagnostic(executions: list[dict]) -> dict:
    """Best-single gap là diagnostic khác interaction, không thêm vào family bảy contrasts."""
    index={(r['variant'],r['execution']):r['balanced_accuracy'] for r in executions}
    require(all((v,i) in index for v in ('B','A','S','AS') for i in range(3)),'Thiếu factorial executions')
    values={v:[index[(v,i)] for i in range(3)] for v in ('B','A','S','AS')}
    gaps=[values['AS'][i]-max(values['A'][i],values['S'][i]) for i in range(3)]
    interaction=[values['AS'][i]-values['A'][i]-values['S'][i]+values['B'][i] for i in range(3)]
    return {'metric':'balanced_accuracy','gap_of_means':float(np.mean(values['AS'])-max(np.mean(values['A']),np.mean(values['S']))),
            'gap_by_execution':gaps,'gap_summary':describe(gaps),'interaction_by_execution':interaction,
            'interaction_summary':describe(interaction),
            'scope':'Gap dùng observed best single chỉ là post-hoc diagnostic; không chọn branch/run, không thuộc bảy linear contrasts hoặc chứng minh synergy.'}


def panel_tables(panels: dict) -> tuple[list,list,list,list,list,list]:
    """Giữ raw scale, support, n_defined và hai loại interval tách riêng."""
    summaries=[]; executions=[]; per_class=[]; disagreements=[]; intervals=[]; contrast_rows=[]
    for name,panel in panels.items():
        variants=('B','AS') if name=='upstream' else VARIANTS; validate_panel_summary(panel,variants)
        support={'panel':name,'n_units_per_execution':9,'n_executions':3,'n_dates':panel['n_dates'],'n_symbols':panel['n_symbols'],
                 'n_blocks':len(panel['blocks']),'support_up_per_execution':2,'support_down_per_execution':7,
                 'n_accounts_per_variant_execution':panel['n_accounts_per_variant_execution']}
        for v in variants:
            for m,stats in panel['summaries'][v].items(): summaries.append({**support,'variant':v,'metric':m,'unit':'percent' if m==METRICS[-1] else 'fraction_or_index',**stats})
        for row in panel['by_execution']:
            key={**support,'variant':row['variant'],'execution':row['execution']}
            executions.append({**key,**flatten(row['pooled']),METRICS[-1]:row[METRICS[-1]]})
            per_class.extend({**key,'class':label,**values} for label,values in row['pooled']['per_class'].items())
        for row in panel['disagreement']:
            disagreements.append({'panel':name,**{k:v for k,v in row.items() if k!='prediction_vector'},
                                  **{f'prediction_{i}':v for i,v in enumerate(row['prediction_vector'])}})
        stats=panel['statistics']
        for v,values in stats['variants'].items():
            values=values if name=='upstream' else values['intervals']
            for m,interval in values.items(): intervals.append({'panel':name,'variant':v,'metric':m,
                **{k:interval[k] for k in ('n_resamples','n_defined','n_undefined')},
                'percentile_low':interval['percentile_95'][0] if interval['percentile_95'] is not None else None,
                'percentile_high':interval['percentile_95'][1] if interval['percentile_95'] is not None else None})
        family=stats.get('BA_family')
        source=stats['contrasts'] if name=='factorial' else [
            {'contrast':'AS-B','weights':{'AS':1,'B':-1},'by_execution':{m:[next(r[m] for r in panel['by_execution'] if r['variant']=='AS' and r['execution']==i)-next(r[m] for r in panel['by_execution'] if r['variant']=='B' and r['execution']==i)
                if all(next(r[m] for r in panel['by_execution'] if r['variant']==v and r['execution']==i) is not None for v in ('AS','B')) else None for i in range(3)] for m in METRICS},
             'intervals':stats['contrasts']['AS-B']}]
        for row in source:
            for m,interval in row['intervals'].items():
                envelope=family['descriptive_envelopes'][row['contrast']] if family and m=='balanced_accuracy' else None
                summary=describe(row['by_execution'][m])
                contrast_rows.append({'panel':name,'contrast':row['contrast'],'metric':m,
                    'weights':json.dumps(row['weights'],sort_keys=True),'execution_0':row['by_execution'][m][0],
                    'execution_1':row['by_execution'][m][1],'execution_2':row['by_execution'][m][2],
                    'n_executions_planned':summary['n_planned'],'n_executions_defined':summary['n_defined'],
                    **{k:v for k,v in summary.items() if k not in ('n_planned','n_defined')},
                    'n_resamples':interval['n_resamples'],'n_draws_defined':interval['n_defined'],'n_draws_undefined':interval['n_undefined'],
                    'percentile_low':interval['percentile_95'][0] if interval['percentile_95'] is not None else None,
                    'percentile_high':interval['percentile_95'][1] if interval['percentile_95'] is not None else None,
                    'descriptive_family_low':envelope[0] if envelope is not None else None,'descriptive_family_high':envelope[1] if envelope is not None else None})
    return summaries,executions,per_class,disagreements,intervals,contrast_rows


def check(root: Path, output: Path) -> int:
    """Đối soát byte/self-digest, không chạy lại bootstrap hoặc đọc quota DB."""
    manifest=read(root/output/'manifest.json'); require(check_self_digest(manifest)=='pretty_sorted_utf8_lf','T26 self-digest sai')
    count=0
    for group,base in (('sources',root),('outputs',root/output)):
        for row in manifest[group]: require(file_hash(base/row['path'])==row['sha256'],'T26 hash khác: '+row['path']); count+=1
    require({p.name for p in (root/output).iterdir()}=={'manifest.json',*[r['path'] for r in manifest['outputs']]},'T26 file thừa/thiếu')
    return count


def build(root: Path, output: Path) -> dict:
    """Kiểm actual jobs/raw/pairing rồi xuất bảng T26 mới, không sửa study."""
    folder=(root/output).resolve(); require(folder.parent==(root/'outputs/revision').resolve() and not folder.exists(),'Cần release mới, không paper/overwrite')
    with offline_guard(),frozen_guard():
        parents={name:verify(root/'outputs/revision'/name) for name in ('revision_minimal_final_v1','sentiment_contract_v1','fusion_prompt_audit_v1','clean_replay_v1')}
        queue=root/'outputs/revision/revision_minimal_v1'; final=root/'outputs/revision/revision_minimal_final_v1'; bank=root/'outputs/revision/r1_72h_bank_v2'
        manifest=verify_manifest(root,queue); records=collect(root,queue,manifest); comparator=Comparator()
        comparator.check(read(final/'records.json'),records,'records')
        lineage,pairing=audit_pairing(root,manifest,records)
        comparator.check(read(final/'lineage.json'),lineage,'lineage'); comparator.check(read(final/'pairing.json'),pairing,'pairing')
        request_map={r['request_ids'][-1]:checked(root/l['request_path']) for r,l in zip(records,lineage)}
        source=read(bank/'manifest.json'); frames,_=load_prices(root/source['protocol']['price_snapshot'],source['protocol']['price_quality_policy'])
        labels={}
        for u in source['units']:
            y,g=target(frames[u['symbol']],[u['decision']],source['protocol']); labels[u['id']]=('UP' if y[0] else 'DOWN','UP' if g[0] else 'DOWN')
        panels={}; selected_predictions=[]; support=[]; all_tensors={}; accounts=[]; main_ids={r['job_id'] for r in records if r['phase']=='main'}
        for name,units,part,upstream in (
            ('upstream',[u for u in source['units'] if u['upstream']],[r for r in records if r['phase'] in ('main','upstream')],True),
            ('factorial',manifest['panel'],[r for r in records if r['phase']=='factorial'],False)):
            panel,a,_,tensors=repeat_panel(name,units,[checked(root/r['path']) for r in part],request_map,frames,source['protocol'],labels,upstream)
            comparator.check(clean(read(final/(name+'_panel.json'))),clean(native(panel)),name); panels[name]=native(panel); accounts.extend(a); all_tensors.update(tensors)
            ids={u['id'] for u in units}
            chosen=[r for r in part if r['context']['unit_id'] in ids]
            require(len(chosen)==panel['n_decisions'],'Panel đã giữ thừa/thiếu executions')
            unit_meta={u['id']:u for u in units}
            for r in chosen:
                req=request_map[r['request_ids'][-1]]; checkpoint=root/r['path']; response_path=checkpoint.parent.parent/'calls'/f"{r['request_ids'][-1]}.response.json"
                require(raw_prediction(read(response_path))==r['prediction'],'Prediction khác actual raw')
                parts=prompt_parts(actual_text(req)); item=unit_meta[r['context']['unit_id']]
                selected_predictions.append({'panel':name,'unit_id':item['id'],'symbol':item['symbol'],'fold':item['fold'],'date':item['date'],
                    'variant':r['context']['variant'],'execution':r['context']['realization'] if upstream else r['context']['repeat'],
                    'prediction':r['prediction'],'label_net':labels[item['id']][0],'job_id':r['job_id'],'source_phase':r['phase'],
                    'minimal_origin':r['origin'],'also_in_main':r['job_id'] in main_ids,'request_id':r['request_ids'][-1],
                    'actual_prompt_hash':identity_hash(req['messages']),'prompt_chars':len(actual_text(req)),
                    'explicit_factor_rows':factor_rows(parts.get('alpha','')),'sentiment_section':bool(parts.get('sentiment')),
                    'sdk_model':req['model_metadata'].get('ls_model_name'),'sdk_temperature':req['model_metadata'].get('ls_temperature'),
                    'provider_org':req['context'].get('provider_org'),'execution_epoch':req['context'].get('execution_epoch')})
            support.extend({'panel':name,**u,'label_net':labels[u['id']][0]} for u in units)
        with np.load(final/'resampling.npz',allow_pickle=False) as frozen:
            for key,value in all_tensors.items(): require(np.allclose(value,frozen[key],rtol=1e-12,atol=1e-10,equal_nan=True),'Tensor khác T04: '+key)
        summaries,executions,per_class,disagreements,intervals,contrasts=panel_tables(panels)
        diagnostic=best_single_diagnostic(panels['factorial']['by_execution']); family=panels['factorial']['statistics']['BA_family']
        family_zero_count=sum(lo<=0<=hi for lo,hi in family['descriptive_envelopes'].values())
        donors=[]; asset_paths=[]
        factorial_units={j['unit']['id']:j['unit'] for j in manifest['jobs'] if j['phase']=='factorial'}
        for selected in manifest['panel']:
            u=factorial_units[selected['id']]
            require(all(u[k]==v for k,v in selected.items()),'Whitelist metadata khác full factorial job unit')
            scope=next(s for s in source['schedule'] if (s['symbol'],s['fold'])==(u['symbol'],u['fold']))
            i=u['decision']; d=u['placebo_donor']; validate_donor(scope,d,i)
            asset_path=bank/f"features/{u['symbol']}_{i}.json"; donor_path=bank/f"features/{u['symbol']}_{d}.json"
            asset=checked(asset_path); donor=checked(donor_path); placebo=donor_factors(asset,donor); asset_paths.extend((asset_path,donor_path))
            require([f['name'] for f in placebo]==[f['name'] for f in asset['alpha_factors']],'Placebo đổi current names')
            mask=lambda fs:availability([{k:f[k] for k in ('value','signal','components')} for f in fs])
            require(mask(asset['alpha_factors'])==mask(placebo),'Placebo đổi schema/missingness')
            require(not asset['sentiment_data']['is_unavailable'] and asset['sentiment_data']['verified_article_count']>=3,'Factorial panel thiếu sentiment đầu vào đã khóa')
            donors.append({'unit_id':u['id'],'symbol':u['symbol'],'fold':u['fold'],'decision_index':i,'decision_date':u['date'],
                'donor_index':d,'donor_date':str(frames[u['symbol']]['date'].iloc[d]),'donor_label_exit_date':str(frames[u['symbol']]['date'].iloc[d+3]),
                'first_validation_date':str(frames[u['symbol']]['date'].iloc[scope['validation'][0]]),'donor_in_purged_train':d in scope['train'],
                'donor_label_mature_before_validation':d+3<scope['validation'][0],'factor_slots':5,'names_preserved':True,
                'rank_vector_availability_hash':identity_hash(mask(placebo)),'current_sentiment_article_count':asset['sentiment_data']['verified_article_count'],
                'normalizer_is_reliable':asset['sentiment_norm']['is_reliable'],'sentiment_unchanged_AS_P':True,
                'asset_file_sha256':file_hash(asset_path),'donor_file_sha256':file_hash(donor_path),
                'scope':'Donor theo rank, không name-matched; chronology không chứng nhận native row-wise causality hoặc news PIT/domain.'})
        selected_ids={r['job_id'] for r in selected_predictions}; relevant_lineage=[r for r in lineage if r['job_id'] in selected_ids]
        order={phase:{'groups':sum(p['phase']==phase for p in pairing),'order_mismatches':sum(p['phase']==phase and not p['order_matches'] for p in pairing),
                      'cross_epoch_groups':sum(p['phase']==phase and p['n_execution_epochs']>1 for p in pairing)} for phase in ('main','upstream','factorial')}
        names=['scripts/export_revision_final_repeats.py','tests/test_revision_final_repeats.py','core/revision_minimal_analysis.py',
            'core/revision_minimal_audit.py','core/revision_minimal_bank.py','core/revision72_run.py','core/revision_baselines.py',
            'core/revision_r3_repeats.py','core/revision_r4_factorial.py','core/revision_clean_metrics.py','core/revision_common_study.py',
            'core/revision_reproducibility.py','scripts/audit_revision_lineage.py','scripts/export_revision_final_baselines.py',
            'tests/test_revision_r3_repeats.py','tests/test_revision_r4_factorial.py']
        names +=[f'outputs/revision/{name}/manifest.json' for name in parents]
        names +=[(queue/'manifest.json').relative_to(root).as_posix(),(bank/'manifest.json').relative_to(root).as_posix()]
        names +=[(final/n).relative_to(root).as_posix() for n in ('records.json','lineage.json','pairing.json','upstream_panel.json','factorial_panel.json','resampling.npz')]
        names +=[p.relative_to(root).as_posix() for p in asset_paths]
        for r in relevant_lineage:
            names.extend((r['path'],r['request_path'],str(Path(r['request_path']).with_name(Path(r['request_path']).name.replace('.request.','.response.'))).replace('\\','/')))
        sources=[{'path':n,'sha256':file_hash(root/n)} for n in sorted(set(names))]
        report={'status':'PASS_EXPLORATORY_FINAL_REPEATS','parent_hashes':parents,'frozen_queue_sources_checked':len(manifest['sources']),
            'successful_jobs_revalidated':len(records),'paired_groups_revalidated':len(pairing),'selected_panel_decisions':len(selected_predictions),
            'selected_unique_raw_requests':len({r['request_id'] for r in selected_predictions}),'upstream_shared_with_main':sum(r['panel']=='upstream' and r['also_in_main'] for r in selected_predictions),
            'selected_minimal_origins':dict(Counter(r['minimal_origin'] for r in selected_predictions)),
            'summary_rows':len(summaries),'execution_rows':len(executions),'per_class_rows':len(per_class),'disagreement_rows':len(disagreements),
            'variant_interval_rows':len(intervals),'contrast_metric_rows':len(contrasts),'panel_accounts':len(accounts),'panel_tensors_checked':len(all_tensors),
            'donor_units':len(donors),'paired_order':order,'comparison':vars(comparator),'api_calls':0,'new_predictions':0,'baseline_fits':0,
            'BA_family_envelopes_containing_zero':family_zero_count,
            'scope':'Không thêm LLM experiment, không ensemble/best run, không inference causal/synergy hoặc đóng R3/R4/T30.'}
        protocol={'run_signature':manifest['sha256'],'selection':manifest['selection'],'contrast_family':CONTRASTS,'bootstrap_seed':20261102,
            'bootstrap_draws':10000,'sd_ddof':1,'scorer_availability':'Số bài/scorer provenance, không independent financial validation hoặc PIT certification.',
            'B':'Shared upstream/rules, bỏ alpha và sentiment report sections; rules vẫn có thể nhắc hai khái niệm.',
            'A':'Thêm current selected factor table, không sentiment section.','S':'Thêm current sentiment section, không factor table.',
            'AS':'Current factors cộng current sentiment.','P':'Giữ current names/schema/missingness và sentiment, thay factor scalars/signals/skill fields bằng một donor past theo rank.',
            'main_prompt_family':'Main/upstream compact alpha, không explicit five-row table; không gộp effect với R4 full-value family.',
            'immutable_hosted_revision':None,'scope':'Historical exploratory sau amendment; prompt/routing/CASH effects và native causal/PIT/domain limits vẫn tồn tại.'}
        lines=['# Repeats, factorial và placebo cuối (T26)','',
            'Chỉ final T04 sau sửa chart; tái kiểm toàn bộ actual raw/checkpoints/parent/prompt, không trộn Decision outcomes trước sửa chart. Không gọi API/inference, không đổi frozen source/prompts hoặc lựa chọn executions.','',
            '| Panel | Units/execution | Symbols | Dates | Blocks | UP/DOWN | Variants | Executions | Decisions |','|---|---:|---:|---:|---:|---|---|---:|---:|']
        for name,p in panels.items(): lines.append(f"| {name} | 9 | {p['n_symbols']} | {p['n_dates']} | 3 | 2/7 | {'B/AS' if name=='upstream' else 'B/A/S/AS/P'} | 3 | {p['n_decisions']} |")
        lines += ['', 'Upstream 54 Decisions gồm 18 main r0 dùng chung và 36 executions bổ sung, không là 54 calls mới. Hai panels có support/prompt family khác nhau; không chọn panel BA cao thay main 102 hoặc trừ hai SD để nhận diện variance components. Mean return là bình quân symbol/block accounts riêng (upstream chín, factorial tám mỗi variant/execution), không portfolio return.',
            '', '| Panel | Variant | BA mean % | Sample SD (pp) | BA min–max % | Mean account return % |','|---|---|---:|---:|---|---:|']
        def fmt(v: float | None, scale: float=1) -> str: return 'NA' if v is None else f'{v*scale:.4f}'
        for name,p in panels.items():
            for v,stats in p['summaries'].items():
                ba=stats['balanced_accuracy']; lines.append(f"| {name} | {v} | {fmt(ba['mean'],100)} | {fmt(ba['sd'],100)} | {fmt(ba['min'],100)}–{fmt(ba['max'],100)} | {fmt(stats['mean_account_net_return_pct']['mean'])} |")
        lines += ['', '## Contrasts factorial', '', '| Contrast | BA mean (pp) | SD (pp) | Conditional percentile interval (pp) | Descriptive family envelope (pp) | Defined/draws |',
            '|---|---:|---:|---|---|---|']
        for r in contrasts:
            if r['panel']=='factorial' and r['metric']=='balanced_accuracy': lines.append(f"| {r['contrast']} | {fmt(r['mean'],100)} | {fmt(r['sd'],100)} | [{fmt(r['percentile_low'],100)}, {fmt(r['percentile_high'],100)}] | [{fmt(r['descriptive_family_low'],100)}, {fmt(r['descriptive_family_high'],100)}] | {r['n_draws_defined']}/{r['n_resamples']} |")
        lines += ['', f"Interaction AS−A−S+B = {fmt(diagnostic['interaction_summary']['mean'],100)} pp; AS−max(A,S) gap of means = {fmt(diagnostic['gap_of_means'],100)} pp. Đây là hai estimands khác nhau; best-single diagnostic không thêm thành contrast thứ tám hoặc làm cơ sở chọn branch/seed.",
            '', f"BA family có {family['n_joint_finite_draws']} joint finite và {family['n_joint_undefined_draws']} mất class trên 10.000 draws; max-deviation radius {fmt(family['max_absolute_deviation_radius'],100)} pp. Có {family_zero_count}/7 family envelopes chứa zero; chưa hiệu chuẩn simultaneous coverage/FWER, không suy p-value, synergy hoặc chứng minh không có effect. Undefined giữ null/NA, không zero. Mọi factorial mean account return âm; upstream mean dương không chứng minh profitability trên main/support khác.",
            '', '## Pairing và placebo', '',
            'Tái kiểm 375 jobs/147 paired groups: actual upstream reports/rules và full factorial scalar/signal/donor content khớp assets. Donor chín units thuộc purged train, label exit trước validation, giữ current factor names, rank-slot schema/deep missingness và current sentiment; một predetermined donor vector/cutoff, không là placebo distribution hoặc name-matched covariance. Normalizer is_reliable=false không tự nghĩa thiếu sentiment: availability dựa actual report và số bài/scorer provenance, không domain/PIT validation.',
            '', 'Successful-call order khác planned listing ở main 3/102, upstream 10/18, factorial 27/27; tổng 40 groups. Cross-epoch groups main ba/upstream hai/factorial bốn, tổng chín. Không sửa order, bỏ outcomes hoặc gọi bù; hosted immutable revisions unknown, alias/configured temperature không chứng nhận served weights/determinism. Source Pattern reuse nguyên input theo protocol không là gộp old Decision outcomes.',
            '', 'Giữ native row-wise causal T10 FAIL, news PIT/domain validity và fill/settlement limits. Main/upstream compact alpha khác explicit five-row factorial; Full−Base là bundle contrast, AS−P không tự định danh causal information effect, scalar integrity không chứng minh semantic compliance. Repeat disagreement/SD chỉ mô tả ba executions trên panel nhỏ, không SD của main 102 hoặc variance decomposition.',
            '', '## Artifacts', '',
            '- [Mean/SD/range](repeat_summary.csv), [per-execution metrics](executions.csv), [per-class](per_class.csv), [disagreement](disagreement.csv), [variant intervals](variant_intervals.csv).',
            '- [Contrasts](contrasts.csv), [BA family](ba_family.json), [best-single diagnostic](best_single_diagnostic.json), [full panel metrics](panels.json).',
            '- [189 actual predictions](predictions.csv), [unit support](support.csv), [donor chronology/mask](donors.csv), [pairing/order](pairing.csv), [parent lineage](lineage.csv), [accounts](accounts.csv).',
            '- [Protocol](protocol.json), [QA](report.json), [manifest](manifest.json). R3/R4 còn sửa bài/response/locators sau T30.',
            '', 'Kiểm theo phạm vi: repeat identity/undefined/statistics, factorial prompt/leakage/donor/statistics/resume và final table estimands. Không full suite/E2E; không đổi producer/selection/inputs hoặc ghi paper. Parent bytes và frozen sources được kiểm lại; T23 independent replay vẫn là bằng chứng riêng, không ghi đã chạy lại ở đây.',
            '', '```powershell','py -3.13 -X utf8 scripts/export_revision_final_repeats.py check',
            'py -3.13 -X utf8 scripts/export_revision_final_repeats.py build --output outputs/revision/final_repeats_recheck_v1','```','']
        pair_csv=[{**{k:v for k,v in r.items() if k not in ('planned_order','observed_success_order')},'planned_order':' > '.join(r['planned_order']),
                   'observed_success_order':' > '.join(r['observed_success_order'])} for r in pairing]
        lineage_csv=[{k:r[k] for k in ('job_id','phase','prediction','origin','path','checkpoint_hash','asset_hash','upstream_hash','donor_hash','prompt_hash',
                     'actual_messages_hash','prompt_chars','factor_rows','actual_provider_org','execution_epoch','request_started_utc','request_path')} for r in relevant_lineage]
        outputs={'report.json':encoded(report),'protocol.json':encoded(protocol),'panels.json':encoded(panels),
            'repeat_summary.csv':csv_bytes(summaries),'executions.csv':csv_bytes(executions),'per_class.csv':csv_bytes(per_class),
            'disagreement.csv':csv_bytes(disagreements),'variant_intervals.csv':csv_bytes(intervals),'contrasts.csv':csv_bytes(contrasts),
            'ba_family.json':encoded(family),'best_single_diagnostic.json':encoded(diagnostic),'predictions.csv':csv_bytes(selected_predictions),
            'support.csv':csv_bytes(support),'donors.csv':csv_bytes(donors),'pairing.csv':csv_bytes(pair_csv),'lineage.csv':csv_bytes(lineage_csv),
            'accounts.csv':csv_bytes(accounts),'report.md':'\n'.join(lines).encode('utf-8')}
        for r in sources: require(file_hash(root/r['path'])==r['sha256'],'Source thay đổi trong T26')
        folder.mkdir()
        for name,data in outputs.items(): (folder/name).write_bytes(data)
        receipt={'schema_version':'final_repeats_v1','sources':sources,'outputs':[{'path':n,'sha256':digest(b)} for n,b in sorted(outputs.items())]}
        receipt['sha256']=digest(encoded(receipt)); (folder/'manifest.json').write_bytes(encoded(receipt)); check(root,output)
        return report


def main() -> None:
    """Build output mới hoặc chỉ hash-check release đã khóa."""
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('command',choices=('build','check')); parser.add_argument('--output',type=Path,default=OUTPUT); args=parser.parse_args()
    if args.command=='check': print(f'T26 hashes PASS: {check(ROOT,args.output)}')
    else: print('T26 PASS: '+json.dumps(build(ROOT,args.output),ensure_ascii=False))


if __name__=='__main__': main()
