"""Hồi quy R4 cho leakage, nội dung prompt thực, interaction và resume; không network."""

from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from core.revision_common_study import digest
from core.revision_r4_factorial import (VARIANTS, actual_text, controlled_prompt, donor_factors,
    factor_report, factor_rows, factorial_statistics, prompt_parts, validate_donor)


def fixture() -> tuple[dict,dict,dict]:
    """Upstream có marker độc lập; năm factor mang giá trị nhận diện riêng."""
    text='Mã FPT.\n3 BÁO CÁO:\n### [1] PHÂN TÍCH XU HƯỚNG\ntrend\n\n### [2] MÔ HÌNH NẾN\npattern\n\n### [3] CHỈ BÁO KỸ THUẬT\nindicator\n\nTHỨ TỰ ƯU TIÊN BẰNG CHỨNG:\nAlpha/sentiment được nhắc chung, không phải data.'
    a={'symbol':'FPT','sentiment_report':'sentiment marker count=3 score=-0.7',
       'alpha_factors':[{'name':f'Factor {i}','value':i/10,'signal':'TĂNG',
           'components':{'ic':.1,'accuracy':'60.0%','composite_score':.8}} for i in range(1,6)]}
    d=deepcopy(a)
    for f in d['alpha_factors']:f['value']*=-1;f['signal']='GIẢM'
    return prompt_parts(text),a,d


class PromptLeakageTests(unittest.TestCase):
    """Control phải giữ data isolation, rows, upstream và mask, không chỉ flags."""

    def test_legacy_table_separator_removes_values_but_new_renderer_keeps_five_rows(self) -> None:
        """Fixture tái hiện splitter --- trong table separator của code đã khóa."""
        from agents.decision_agent import _distill_report
        _,a,_=fixture();raw=factor_report(a['alpha_factors'],'FPT').replace('| : | : | : | : | : | : | : |','|---|---|---|---|---|---|---|')
        self.assertEqual(factor_rows(_distill_report('alpha',raw,'vi')),0)
        self.assertEqual(factor_rows(factor_report(a['alpha_factors'],'FPT')),5)

    def test_all_variant_sections_and_actual_content_are_isolated(self) -> None:
        """A không nhận sentiment; S không nhận factor values; rules chung không bị nhận nhầm."""
        base,a,d=fixture()
        outputs={v:prompt_parts(controlled_prompt(base,a,d,v)) for v in VARIANTS}
        for v,p in outputs.items():
            self.assertEqual('alpha' in p,v in ('A','AS','P'))
            self.assertEqual('sentiment' in p,v in ('S','AS','P'))
            for field in ('trend','pattern','indicator','rules'):self.assertEqual(p[field],base[field])
        self.assertEqual(outputs['A']['alpha'],outputs['AS']['alpha'])
        for v in ('S','AS','P'):self.assertEqual(outputs[v]['sentiment'],a['sentiment_report'])
        self.assertNotEqual(outputs['AS']['alpha'],outputs['P']['alpha'])
        self.assertNotIn('sentiment marker',outputs['A']['alpha'])
        self.assertNotIn('+0.1000',controlled_prompt(base,a,d,'S'))

    def test_all_five_values_reach_actual_human_message_and_budget_guard(self) -> None:
        """Prompt gửi model phải thật sự chứa giá trị từng factor, không chỉ dữ liệu trong bank."""
        b,a,d=fixture();text=controlled_prompt(b,a,d,'AS')
        req={'messages':[[{'type':'human','data':{'content':text}}]]}
        self.assertEqual(actual_text(req),text)
        self.assertEqual(factor_rows(prompt_parts(actual_text(req))['alpha']),5)
        for i in range(1,6):self.assertIn(f'{i/10:+.4f}',text)
        b['indicator']='x'*6500
        with self.assertRaisesRegex(ValueError,'6.500'):controlled_prompt(b,a,d,'AS')

    def test_donor_is_one_rank_vector_without_mutating_assets(self) -> None:
        """Không shuffle riêng từng scalar hoặc sửa cache đã khóa."""
        _,a,d=fixture();before=deepcopy(a);result=donor_factors(a,d)
        self.assertEqual(a,before)
        self.assertEqual([r['name'] for r in result],[r['name'] for r in a['alpha_factors']])
        self.assertEqual([r['value'] for r in result],[r['value'] for r in d['alpha_factors']])

    def test_nested_missingness_and_schema_mismatch_are_rejected(self) -> None:
        """Chỉ so set(keys) là chưa đủ để phát hiện thêm missingness signal."""
        for bad in ('null','key','count'):
            _,a,d=fixture()
            if bad=='null':d['alpha_factors'][1]['components']['ic']=None
            elif bad=='key':d['alpha_factors'][1]['components']['extra']=0
            else:d['alpha_factors'].pop()
            with self.assertRaises(ValueError):donor_factors(a,d)

    def test_future_or_label_overlapping_donor_is_rejected(self) -> None:
        """Train membership không đủ nếu label donor còn chồng lên validation/test."""
        scope={'train':[10,13,16],'validation':[20,23]};validate_donor(scope,13,30)
        for donor,decision in [(23,30),(16,19)]:
            with self.assertRaises(ValueError):validate_donor(scope,donor,decision)
        with self.assertRaises(ValueError):validate_donor({'train':[18],'validation':[20]},18,30)

    def test_unexpected_message_history_is_rejected(self) -> None:
        """Không ghép chat history khác với prompt đã khóa."""
        with self.assertRaises(ValueError):actual_text({'messages':[[],[]]})


class FactorialStatisticsTests(unittest.TestCase):
    """Interaction theo linear contrast và resampling paired phải giữ cùng estimand."""

    def tensors(self) -> tuple[dict,dict]:
        """B và A/S/AS có accuracy tăng đều, nhưng interaction bằng zero."""
        matrix={v:np.asarray([[[k,4-k,k,4-k]]*3]*3) for v,k in zip(VARIANTS,[1,2,2,3,3])}
        account={v:np.broadcast_to([float(i),1.],(3,3,2)).copy() for i,v in enumerate(VARIANTS)}
        return matrix,account

    def test_interaction_is_not_improvement_over_best_single(self) -> None:
        """AS-A-S+B=0 dù AS-max(A,S)>0; không gọi hai đại lượng là cùng synergy."""
        c,a=self.tensors();result=factorial_statistics(c,a)
        i=next(r for r in result['contrasts'] if r['contrast']=='interaction')
        self.assertAlmostEqual(i['summary']['balanced_accuracy']['mean'],0)
        np.testing.assert_allclose(i['intervals']['balanced_accuracy']['percentile_95'],[0,0])
        self.assertGreater(result['variants']['AS']['summary']['balanced_accuracy']['mean']-result['variants']['A']['summary']['balanced_accuracy']['mean'],0)
        self.assertEqual(result['BA_family']['n_contrasts'],7)

    def test_joint_resampling_is_invariant_to_correlated_symbol_copies(self) -> None:
        """Nhân bản toàn cross-section không thu hẹp intervals hoặc joint envelope."""
        c,a=self.tensors();r=factorial_statistics(c,a);s=factorial_statistics({v:x*7 for v,x in c.items()},{v:x*7 for v,x in a.items()})
        self.assertEqual(r['BA_family'],s['BA_family'])
        for x,y in zip(r['contrasts'],s['contrasts']):
            for metric in x['intervals']:np.testing.assert_allclose(x['intervals'][metric]['percentile_95'],y['intervals'][metric]['percentile_95'])

    def test_missing_variant_or_changed_true_support_is_rejected(self) -> None:
        """Không tính interaction từ grid thiếu hoặc class support khác nhau."""
        c,a=self.tensors();c.pop('S')
        with self.assertRaises(ValueError):factorial_statistics(c,a)
        c,a=self.tensors();c['AS'][0,0,0]+=1
        with self.assertRaises(ValueError):factorial_statistics(c,a)


class ArchiveResumeTests(unittest.TestCase):
    """Gọi fixture qua callback thật; crash/resume không được sinh lại response hoặc copy identity."""

    def test_raw_response_resume_and_tamper_guard(self) -> None:
        """Raw success trước checkpoint được replay, giữ count và source/schema đúng."""
        from langchain_core.language_models.fake_chat_models import FakeListChatModel
        from agents.decision_agent import TradeDecisionOutput
        from core.revision72_run import CachedLLM
        from core.revision72_quota import PoolArchive,PoolLedger
        from core.revision_r4_run import perform_call,verify_point
        b,a,d=fixture();prompt=controlled_prompt(b,a,d,'AS')
        data={'decision':'LONG','forecast_horizon':'T+2.5','confidence':'Thấp','risk_reward_ratio':1.,'evidence_for':'f','evidence_against':'a','justification':'j'}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);shard=root/'shards/org1';shard.mkdir(parents=True)
            archive=PoolArchive(shard,'fixture','secret',PoolLedger(root/'q.sqlite','fixture'),1,0)
            delegate=FakeListChatModel(responses=[json.dumps(data)],callbacks=[archive])
            class Structured:
                def invoke(self,text):
                    raw=delegate.invoke(text)
                    return {'parsed':TradeDecisionOutput.model_validate_json(raw.content),'raw':raw,'parsing_error':None}
            job={'org':1,'stage':'decision','model':'text','unit_id':'u','variant':'AS','repeat':0}
            parent={'bank_id':'fixture','prompt_hash':digest(prompt)};path=shard/'decisions/u.json'
            with redirect_stdout(io.StringIO()),patch('core.revision_r4_run.write_json',side_effect=OSError('fixture crash')):
                with self.assertRaises(OSError):perform_call(CachedLLM(Structured(),archive,structured=True),archive,job,prompt,parent,path)
            self.assertEqual(archive.count,1)
            class Bomb:
                def invoke(self,*args,**kwargs):raise AssertionError('Không được gọi lại network')
            with redirect_stdout(io.StringIO()):
                r=perform_call(CachedLLM(Bomb(),archive,structured=True),archive,job,prompt,parent,path)
            self.assertEqual(archive.count,1);self.assertEqual(r['prediction'],'LONG')
            self.assertEqual(verify_point(path,job,parent)['prediction'],'LONG')
            with self.assertRaises(ValueError):verify_point(path,{**job,'repeat':1},parent)
            response=next((shard/'calls').glob('*.response.json'))
            response.write_bytes(response.read_bytes().replace(b'LONG',b'SHORT'))
            with self.assertRaisesRegex(ValueError,'Raw R4'):verify_point(path,job,parent)


class NewAnalysisIntegrationTests(unittest.TestCase):
    """Fixture trong thư mục tạm xác minh completed-panel guard và ledger/undefined thật."""

    def test_incomplete_rejected_and_constant_cash_has_zero_return_null_mcc(self) -> None:
        """Không xuất từ lượt dở; pipeline hoàn chỉnh không đổ NaN khi mọi dự đoán CASH."""
        from scripts.analyze_revision_r4 import analyze_new, BANK
        from core.revision_common_study import read_json
        old=read_json(BANK/'manifest.json')
        units=[next(u for u in old['units'] if u['id']==uid) for uid in old['panel']]
        manifest={'policy':{'scope':'unit-test fixture only'},'units':[{'unit':u} for u in units]}
        records=[{'context':{'unit_id':u['id'],'variant':v,'repeat':r},'prediction':'SHORT',
            'request_ids':['fixture'],'parent':{}} for u in units for v in VARIANTS for r in range(3)]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);bank=root/'bank';bank.mkdir();(bank/'manifest.json').write_text('{}',encoding='utf-8')
            run=root/'run';run.mkdir()
            # Analysis artifact manifest dùng root-relative paths; giữ fixture trong ROOT qua patch.
            with patch('scripts.analyze_revision_r4.verify_r3'),patch('scripts.analyze_revision_r4.ROOT',root):
                with self.assertRaisesRegex(ValueError,'270'):analyze_new(manifest,records[:-1],run,bank)
            import scripts.analyze_revision_r4 as module
            original_root=module.ROOT
            from core.revision_baselines import load_prices
            frames=load_prices(original_root/old['protocol']['price_snapshot'],old['protocol']['price_quality_policy'])
            with patch('scripts.analyze_revision_r4.verify_r3'),patch('scripts.analyze_revision_r4.ROOT',root),patch('core.revision_baselines.load_prices',return_value=frames),redirect_stdout(io.StringIO()):
                analyze_new(manifest,records,run,bank)
                analyze_new(manifest,records,run,bank)
            report=read_json(run/'analysis/report.json')
            metrics=report['metrics']['variants']['AS']
            self.assertIsNone(metrics['summary']['mcc']['mean'])
            self.assertEqual(metrics['summary']['mean_account_net_return_pct']['mean'],0)
            import csv
            with (run/'analysis/account_returns.csv').open(encoding='utf-8',newline='') as f:accounts=list(csv.DictReader(f))
            self.assertEqual(len(accounts),195)
            self.assertTrue(all(float(a['net_return_pct'])==0 for a in accounts))


if __name__=='__main__':unittest.main()
