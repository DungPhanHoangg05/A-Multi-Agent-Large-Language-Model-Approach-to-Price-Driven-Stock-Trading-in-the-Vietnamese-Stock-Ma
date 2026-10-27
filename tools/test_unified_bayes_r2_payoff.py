"""Oracle NIG, metric/gate và consumer R2; chỉ dùng nguồn tổng hợp."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy.special import gammaln
from scipy.stats import t

from core.research_input_lock import _write_once
from tools import prepare_unified_bayes_r2_payoff as cli
from tools.unified_bayes_r2_payoff import estimate_payoff, evaluate_gate, load_protocol, point_metrics


def good_panels() -> dict:
    """Tám ô đủ support; metric ngay biên rule, không phụ thuộc kết quả thật."""
    metrics = {"absolute_error_nig": .01, "absolute_error_zero": .02, "absolute_error_m0": .01,
               "nll_nig": -1., "nll_prior": -1., "predictive_covered": .85, "predictive_width": .1}
    panel = {"planned": 10, "common_count": 10, "excluded_count": 0, "metrics": metrics}
    return {"overall": deepcopy(panel), "by_symbol": {s:deepcopy(panel) for s in cli.SYMBOLS},
            "by_fold_symbol": {f"{f}/{s}":deepcopy(panel) for f in ("train_2021","train_2022") for s in cli.SYMBOLS}}


class PayoffMathTests(unittest.TestCase):
    """Công thức tham chiếu độc lập bằng tổng bình phương chưa centered và log density."""

    def setUp(self) -> None:
        self.c = [-.02,-.01,0.,.01,.02]
        self.b = [-.03,-.01,.01,.02]*5

    def test_conjugate_parameters_match_uncentered_oracle(self) -> None:
        p = estimate_payoff(self.c,self.b,stats_ready=True)
        m0 = sum(self.b)/len(self.b)
        variance = sum((v-m0)**2 for v in self.b)/(len(self.b)-1)
        mn = (4*m0+sum(self.c))/(4+len(self.c))
        beta = variance+(sum(v*v for v in self.c)+4*m0*m0-(4+len(self.c))*mn*mn)/2
        self.assertAlmostEqual(p["prior"]["beta"],variance,15)
        self.assertAlmostEqual(p["posterior"]["beta"],beta,15)
        self.assertAlmostEqual(p["posterior"]["mean"],mn,15)
        self.assertEqual(p["posterior"]["alpha"],4.5)
        self.assertTrue(p["gate"]["ready"])

    def test_mean_and_predictive_scales_and_quantiles_are_distinct(self) -> None:
        p = estimate_payoff(self.c,self.b,stats_ready=True)["posterior"]
        self.assertAlmostEqual(p["predictive_scale"]/p["mean_scale"],math.sqrt(10),14)
        for name,level,scale in (("mean_credible_interval",.95,p["mean_scale"]),("predictive_interval",.9,p["predictive_scale"])):
            interval=p[name]
            self.assertAlmostEqual(t.cdf(interval["lower"],p["df"],loc=p["mean"],scale=scale),(1-level)/2,delta=1e-10)
            self.assertAlmostEqual(t.cdf(interval["upper"],p["df"],loc=p["mean"],scale=scale),(1+level)/2,delta=1e-10)

    def test_prior_predictive_uses_kappa0_and_alpha0(self) -> None:
        p=estimate_payoff(self.c,self.b,stats_ready=True)["prior"]
        self.assertEqual(p["df"],4.)
        self.assertAlmostEqual(p["predictive_scale"]**2,p["beta"]*5/8,15)

    def test_uniform_background_has_variance_floor_not_trading_threshold(self) -> None:
        p=estimate_payoff([.01]*5,[.01]*20,stats_ready=True)
        self.assertEqual(p["prior"]["beta"],1e-6)
        self.assertAlmostEqual(p["posterior"]["mean"],.01)
        self.assertTrue(p["gate"]["ready"])

    def test_missing_and_small_support_keep_reasons_without_zero_imputation(self) -> None:
        p=estimate_payoff([],self.b,stats_ready=False)
        self.assertIsNone(p["posterior"])
        self.assertIn("LOW_CONDITIONAL_SUPPORT",p["gate"]["reason_codes"])
        p=estimate_payoff(self.c,[],stats_ready=True)
        self.assertIsNone(p["prior"])
        self.assertFalse(p["gate"]["ready"])
        p=estimate_payoff(self.c[:4],self.b,stats_ready=True)
        self.assertIsNotNone(p["posterior"])
        self.assertFalse(p["gate"]["ready"])

    def test_gate_boundary_20_background_and_5_conditional(self) -> None:
        self.assertFalse(estimate_payoff(self.c,self.b[:-1],stats_ready=True)["gate"]["ready"])
        self.assertTrue(estimate_payoff(self.c,self.b,stats_ready=True)["gate"]["ready"])
        self.assertFalse(estimate_payoff(self.c,self.b,stats_ready=False)["gate"]["ready"])

    def test_corrupt_nonfinite_bool_numpy_and_impossible_return_raise(self) -> None:
        for bad in (float("nan"),float("inf"),True,np.float64(.1),-1.,-2.):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                estimate_payoff([bad],self.b,stats_ready=True)
        with self.assertRaises(ValueError):
            estimate_payoff(tuple(self.c),self.b,stats_ready=True)
        with self.assertRaises(ValueError):
            estimate_payoff(self.c,self.b,stats_ready=1)

    def test_overflow_is_error_not_cash(self) -> None:
        with self.assertRaises(ValueError):
            estimate_payoff([1e308]*5,[1e308]*20,stats_ready=True)

    def test_density_metric_matches_manual_student_t_logpdf(self) -> None:
        prediction=estimate_payoff(self.c,self.b,stats_ready=True)
        result=point_metrics(prediction,.03)
        p=prediction["posterior"];df=p["df"];scale=p["predictive_scale"];z=(.03-p["mean"])/scale
        logpdf=gammaln((df+1)/2)-gammaln(df/2)-.5*math.log(df*math.pi)-math.log(scale)-(df+1)/2*math.log1p(z*z/df)
        self.assertAlmostEqual(result["nll_nig"],-logpdf,13)
        self.assertEqual(result["absolute_error_zero"],.03)
        self.assertIsNone(point_metrics(estimate_payoff([],self.b,stats_ready=False),.03))

    def test_outlier_stress_keeps_all_observations(self) -> None:
        clean=estimate_payoff(self.c,self.b,stats_ready=True)
        changed=estimate_payoff(self.c[:-1]+[.5],self.b,stats_ready=True)
        self.assertEqual(changed["nC"],5)
        self.assertGreater(changed["posterior"]["mean"],clean["posterior"]["mean"])
        self.assertGreater(changed["posterior"]["predictive_interval"]["width"],clean["posterior"]["predictive_interval"]["width"])


class PayoffGateAndConsumerTests(unittest.TestCase):
    """Không hạ biên, bỏ ô thiếu support hoặc tin JSON tự reseal."""

    def test_registered_protocol_has_one_model_no_sweep_and_five_secondary(self) -> None:
        p=load_protocol()
        self.assertEqual(p["payoff"]["model_count"],1)
        self.assertFalse(p["payoff"]["sweep"])
        self.assertEqual(p["statistics"]["secondary_family_size"],5)
        self.assertEqual(p["statistics"]["secondary_ci"],.99)

    def test_exact_gate_boundaries_pass(self) -> None:
        self.assertEqual(evaluate_gate(good_panels())["status"],"PASS")

    def test_strict_improvement_not_rounded_equality(self) -> None:
        p=good_panels();p["overall"]["metrics"]["absolute_error_zero"]=.01
        self.assertIn("strict_mae_improvement",evaluate_gate(p)["failed_checks"])
        p["overall"]["metrics"]["absolute_error_nig"]=math.nextafter(.01,0.)
        self.assertEqual(evaluate_gate(p)["status"],"PASS")

    def test_each_economic_check_can_fail_without_changing_support(self) -> None:
        cases=(("absolute_error_nig",.03,"mae_le_zero"),("nll_nig",-.9,"nll_le_prior"),
               ("predictive_covered",math.nextafter(.85,0.),"predictive_coverage_ge_0_85"))
        for key,value,reason in cases:
            p=good_panels();p["overall"]["metrics"][key]=value
            with self.subTest(key=key):
                self.assertIn(reason,evaluate_gate(p)["failed_checks"])
                self.assertFalse(evaluate_gate(p)["development_allowed"])

    def test_symbol_guard_and_missing_cell_are_not_masked_by_average(self) -> None:
        p=good_panels();p["by_symbol"]["FPT"]["metrics"]["absolute_error_nig"]+=.0011
        self.assertIn("symbol_mae_increase_le_0_001",evaluate_gate(p)["failed_checks"])
        p=good_panels();cell=p["by_fold_symbol"]["train_2021/FPT"];cell["common_count"]=0;cell["metrics"]=None
        self.assertEqual(evaluate_gate(p)["status"],"INCONCLUSIVE")
        del p["by_fold_symbol"]["train_2021/FPT"]
        with self.assertRaises(ValueError):evaluate_gate(p)

    def test_nan_metrics_are_integrity_error(self) -> None:
        p=good_panels();p["overall"]["metrics"]["absolute_error_nig"]=float("nan")
        with self.assertRaises(ValueError):evaluate_gate(p)

    def test_panels_keep_empty_groups_and_identical_common_support(self) -> None:
        prediction=estimate_payoff([.01]*5,[.01]*20,stats_ready=True)
        rows=[{"symbol":"FPT","fold_id":"train_2021","metrics":point_metrics(prediction,.01)},
              {"symbol":"FPT","fold_id":"train_2021","metrics":None}]
        p=cli.make_panels(rows)
        self.assertEqual(p["overall"]["common_count"],1)
        self.assertEqual(p["overall"]["planned"],2)
        self.assertIsNone(p["by_symbol"]["VNM"]["metrics"])
        self.assertEqual(evaluate_gate(p)["status"],"INCONCLUSIVE")

    def test_write_once_and_consumer_reject_resealed_metrics(self) -> None:
        with tempfile.TemporaryDirectory(dir=cli.ROOT/"outputs/bayesian_benchmark") as directory:
            path=Path(directory)/"report.json"
            expected={"gate":{"status":"FAIL"},"metrics":{"mae":.01}}
            _write_once(path,expected)
            self.assertEqual(cli.read_report(path,expected),expected)
            with self.assertRaises(ValueError):_write_once(path,{"gate":"PASS"})
            altered=deepcopy(expected);altered["metrics"]["mae"]=0.
            with self.assertRaises(ValueError):cli.read_report(path,altered)

    def test_source_code_and_protocol_tamper_are_detected(self) -> None:
        with tempfile.TemporaryDirectory(dir=cli.ROOT/"outputs/bayesian_benchmark") as directory:
            path=Path(directory)/"source.json";path.write_text("{}","utf-8")
            pins={path.relative_to(cli.ROOT).as_posix():cli.sha(path)}
            cli.source_guard(pins);path.write_text('{"changed":true}',"utf-8")
            with self.assertRaises(ValueError):cli.source_guard(pins)
        with patch("tools.unified_bayes_r2_payoff.canonical_hash",return_value="changed"):
            with self.assertRaises(ValueError):load_protocol()


if __name__ == "__main__":
    unittest.main()
