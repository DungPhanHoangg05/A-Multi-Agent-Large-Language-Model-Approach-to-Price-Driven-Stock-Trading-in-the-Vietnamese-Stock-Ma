"""Kiểm audit R4 final không nhầm prompt đủ rows với đúng nội dung treatment/donor."""

from __future__ import annotations

from copy import deepcopy
import unittest

from core.revision_r4_factorial import controlled_prompt,prompt_parts
from scripts.finalize_revision_r4 import check_content,factor_cells


def fixture(variant: str) -> tuple[dict,dict,dict,dict,dict]:
    """Actual message fixture độc lập, không ghi synthetic predictions vào outputs nghiên cứu."""
    base=prompt_parts('Mã FPT.\n3 BÁO CÁO:\n### [1] PHÂN TÍCH XU HƯỚNG\nt\n\n### [2] MÔ HÌNH NẾN\np\n\n### [3] CHỈ BÁO KỸ THUẬT\ni\n\nTHỨ TỰ ƯU TIÊN BẰNG CHỨNG:\nrules')
    a={'symbol':'FPT','sentiment_report':'score=-0.2; count=3','alpha_factors':[
        {'name':f'Factor {i}','value':i/10,'signal':'TĂNG','components':{'ic':.1,'accuracy':'60.0%','composite_score':.8}} for i in range(1,6)]}
    d=deepcopy(a)
    for f in d['alpha_factors']:f['value']*=-1;f['signal']='GIẢM'
    unit={'prompts':{variant:controlled_prompt(base,a,d,variant)}}
    job={'unit_id':'u','variant':variant,'repeat':0,'model':'openai/gpt-oss-20b'}
    request={'bank_id':'b','context':{**job,'provider_org':2,'execution_epoch':'e'},
        'messages':[[{'type':'human','data':{'content':unit['prompts'][variant]}}]],
        'model_metadata':{'ls_model_name':'openai/gpt-oss-20b','ls_temperature':1e-8,'ls_max_tokens':2048}}
    return request,job,unit,a,d


class FinalPromptAuditTests(unittest.TestCase):
    """Hash agreement chưa đủ nếu builder làm mất hoặc gán sai scalar."""

    def test_all_actual_variants_and_past_scalar_cells_match(self) -> None:
        """Phân biệt vắng section hợp lệ và năm rows đúng treatment/donor."""
        for v in ('B','A','S','AS','P'):
            request,job,unit,a,d=fixture(v);r=check_content(request,job,unit,a,d,'b')
            self.assertEqual(r['factor_rows'],5 if v in ('A','AS','P') else 0)
        request,job,unit,a,d=fixture('P')
        values=factor_cells(prompt_parts(unit['prompts']['P'])['alpha'])
        self.assertEqual(values[0]['name'],a['alpha_factors'][0]['name'])
        self.assertEqual(values[0]['value'],-.1)

    def test_scalar_tamper_rejected_even_when_frozen_prompt_string_agrees(self) -> None:
        """Không chỉ so hash: nội dung phải khớp asset/donor độc lập."""
        request,job,unit,a,d=fixture('AS')
        text=unit['prompts']['AS'].replace('| +0.1000 |','| +0.9000 |',1)
        unit['prompts']['AS']=text;request['messages'][0][0]['data']['content']=text
        with self.assertRaisesRegex(ValueError,'Factor cells'):check_content(request,job,unit,a,d,'b')

    def test_wrong_identity_model_caps_or_temperature_rejected(self) -> None:
        """Routing slot được phép khác, model/settings/repeat không được đổi."""
        for field in ('context','model','temperature','caps','bank'):
            request,job,unit,a,d=fixture('AS')
            if field=='context':request['context']['repeat']=1
            elif field=='model':request['model_metadata']['ls_model_name']='other'
            elif field=='temperature':request['model_metadata']['ls_temperature']=.1
            elif field=='caps':request['model_metadata']['ls_max_tokens']=4096
            else:request['bank_id']='old'
            with self.assertRaises(ValueError):check_content(request,job,unit,a,d,'b')

    def test_header_only_or_duplicated_factor_rows_rejected(self) -> None:
        """Không nghiệm thu header/consensus hoặc một row bị copy thành row khác."""
        request,job,unit,a,d=fixture('AS');alpha=prompt_parts(unit['prompts']['AS'])['alpha']
        for text in ('## 5 Alpha Factor\n| # | Alpha | Giá trị |',alpha.replace('| 5 |','| 4 |')):
            with self.assertRaises(ValueError):factor_cells(text)


if __name__=='__main__':unittest.main()
