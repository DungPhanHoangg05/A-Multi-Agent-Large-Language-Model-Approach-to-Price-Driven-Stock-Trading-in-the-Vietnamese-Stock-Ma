"""Kiểm pairing, undefined metrics và identity của phân tích lặp R3; không API."""

from __future__ import annotations

import unittest

import numpy as np

from core.revision_r3_repeats import array_metrics, describe, panel_identity, resample
from utils.statistical_tests import binary_classification_metrics


class RepeatStatisticsTests(unittest.TestCase):
    """Resampling không được tạo thêm độc lập hoặc điền metric undefined bằng zero."""

    def fixture(self) -> tuple[dict, dict]:
        """Ba executions có cùng support nhưng dự đoán khác nhau."""
        c=np.asarray([[[1,1,1,1]]*3,[[2,0,1,1]]*3,[[0,2,2,0]]*3])
        a=np.zeros((3,3,2));a[...,0]=np.arange(9).reshape(3,3)-4;a[...,1]=1
        return {"AS":c.copy(),"B":c.copy()},{"AS":a.copy(),"B":a.copy()}

    def test_vector_metrics_match_reference_including_undefined(self) -> None:
        """Chuẩn phân loại R1 phải giữ nguyên khi vector hóa confusion counts."""
        for y,p in [(["UP","DOWN"],["LONG","SHORT"]),(["UP","DOWN"],["SHORT","SHORT"]),
                    (["UP","UP"],["LONG","LONG"]),(["DOWN","DOWN"],["LONG","SHORT"])]:
            reference=binary_classification_metrics(y,p);c=reference["confusion"]
            actual=array_metrics(np.asarray([c[k] for k in ("tp","fn","tn","fp")]))
            for metric,value in actual.items():
                if reference[metric] is None:self.assertFalse(np.isfinite(value))
                else:self.assertAlmostEqual(float(value),reference[metric])

    def test_undefined_run_summary_keeps_denominator_and_sample_sd(self) -> None:
        """Một execution undefined không âm thầm bị tính thành điểm zero."""
        s=describe([None,.2,.4]);self.assertEqual(s["n_planned"],3);self.assertEqual(s["n_defined"],2)
        self.assertAlmostEqual(s["mean"],.3);self.assertAlmostEqual(s["sd"],np.sqrt(.02))
        self.assertEqual(describe([None,None,None])["mean"],None)

    def test_paired_identical_variants_have_zero_contrast_interval(self) -> None:
        """Cùng block/run draws cho hai nhánh phải triệt tiêu biến thiên chung."""
        c,a=self.fixture();r=resample(c,a,repeats=2048)
        for metric,s in r["contrasts"]["AS-B"].items():
            self.assertGreater(s["n_defined"],0,metric)
            np.testing.assert_allclose(s["percentile_95"],[0,0],atol=1e-14)

    def test_correlated_symbol_copies_do_not_narrow_intervals(self) -> None:
        """Nhân bản cả cross-section không tạo thêm temporal clusters."""
        c,a=self.fixture();original=resample(c,a,repeats=2048)
        copied=resample({k:v*5 for k,v in c.items()},{k:v*5 for k,v in a.items()},repeats=2048)
        for variant in original["variants"]:
            for metric in original["variants"][variant]:
                np.testing.assert_allclose(original["variants"][variant][metric]["percentile_95"],
                    copied["variants"][variant][metric]["percentile_95"],atol=1e-13)

    def test_class_loss_draws_report_undefined_instead_of_zero(self) -> None:
        """Resample chỉ một lớp làm BA/MCC undefined và phải được đếm."""
        c,a=self.fixture();matrix=np.asarray([[[2,0,0,0],[0,0,2,0],[1,0,1,0]]]*3)
        r=resample({k:matrix.copy() for k in c},a,repeats=4096)
        metric=r["variants"]["AS"]["balanced_accuracy"]
        self.assertGreater(metric["n_undefined"],0)
        self.assertEqual(metric["n_defined"]+metric["n_undefined"],4096)
        np.testing.assert_allclose(metric["percentile_95"],[1,1])

    def test_changed_support_or_truth_rejected(self) -> None:
        """Không gộp variants có khác unit count hoặc nhãn thật."""
        for bad in (True,False):
            c,a=self.fixture()
            if bad:c["B"][0,0,0]+=1
            else:c["B"][0,0,0]+=1;c["B"][0,0,2]-=1
            with self.assertRaises(ValueError):resample(c,a,repeats=16)


class RepeatIdentityTests(unittest.TestCase):
    """Prediction trùng có thể hợp lệ, nhưng response ID/parent phải có đúng provenance."""

    def fixture(self,upstream:bool=False) -> tuple[list[dict],dict]:
        """Các calls độc lập về ID, cùng prompt có chủ đích trong Decision panel."""
        records=[];requests={}
        for run in range(3):
            for variant in ("B","AS"):
                context={"unit_id":"unit","realization":run if upstream else 0,"variant":variant,
                    "repeat":0 if upstream else run,"stage":"decision","model":"m","smoke":False}
                attempt=f"{run}-{variant}";requests[attempt]={"context":context.copy(),"messages":[variant]}
                records.append({"context":context,"request_ids":[attempt],"prediction":"SHORT",
                    "decision_source":"llm_structured","fallback_reason":"",
                    "parent":{"upstream_hash":str(run) if upstream else "shared"}})
        return records,requests

    def test_identical_predictions_with_unique_real_requests_are_allowed(self) -> None:
        """Đồng thuận không tự đồng nghĩa với sao chép execution."""
        records,requests=self.fixture();result=panel_identity(records,requests,["unit"],["B","AS"],False)
        self.assertEqual(result["n_unique_successful_requests"],6)
        self.assertTrue(all(r["pairwise_disagreement"]==0 for r in result["disagreement_by_cutoff"]))

    def test_reusing_raw_response_for_a_repeat_is_rejected(self) -> None:
        """Cùng prediction vẫn cần response ID riêng cho mỗi repeat."""
        records,requests=self.fixture();records[2]["request_ids"]=records[0]["request_ids"][:]
        with self.assertRaisesRegex(ValueError,"successful request"):
            panel_identity(records,requests,["unit"],["B","AS"],False)

    def test_prompt_parent_or_missing_execution_rejected(self) -> None:
        """Không nhận grid thiếu, prompt thay đổi hoặc upstream khác khi lặp Decision."""
        for error in ("prompt","parent","missing"):
            records,requests=self.fixture()
            if error=="prompt":requests[records[2]["request_ids"][0]]["messages"]=["changed"]
            elif error=="parent":records[2]["parent"]["upstream_hash"]="wrong"
            else:records.pop()
            with self.assertRaises(ValueError):panel_identity(records,requests,["unit"],["B","AS"],False)

    def test_upstream_can_vary_between_realizations_but_not_between_branches(self) -> None:
        """B/AS phải paired trong mỗi realization dù upstream được tái tạo."""
        records,requests=self.fixture(True)
        self.assertEqual(panel_identity(records,requests,["unit"],["B","AS"],True)["n_records"],6)
        records[3]["parent"]["upstream_hash"]="other"
        with self.assertRaises(ValueError):panel_identity(records,requests,["unit"],["B","AS"],True)


if __name__=="__main__":unittest.main()
