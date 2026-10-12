"""Kiểm ranh giới model/policy/nhãn kinh tế khi numeric risk policy được hoãn."""

from copy import deepcopy
import json
import unittest

import pandas as pd

from core.backtest_engine import PRIOR_BRANCH_MODES
from core.candidate_cohort import CANDIDATES, registry
from core.prior_backtest import evaluate_point
from core.research_metrics import action_attribution, candidate_report


class ActionAttributionTests(unittest.TestCase):
    """Dùng evaluator thật; lợi nhuận xấu không được ép LONG thành SHORT."""

    def point(self, close: float = 90.) -> tuple[dict, list[str]]:
        """Tạo một chu kỳ đủ ba phiên và quyết định trái nhau trên các nhánh."""
        matrix = [*PRIOR_BRANCH_MODES, *CANDIDATES]
        frame = pd.DataFrame({"Datetime": pd.bdate_range("2023-01-02", periods=4),
            "Open": [100.] * 4, "Close": [100., 100., 100., close],
            "High": [max(100., close)] * 4, "Low": [min(100., close)] * 4,
            "Volume": [1000.] * 4, "Reference": [100.] * 4})
        branches = {name: {"status": "complete", "decision": {"action": "LONG" if i % 2 == 0 else "SHORT"}}
                    for i, name in enumerate(matrix)}
        evaluation = evaluate_point(frame, [], "2023-01-02", {n: branches[n] for n in PRIOR_BRANCH_MODES})
        for name in CANDIDATES:
            extra = evaluate_point(frame, [], "2023-01-02", {n: branches[name] for n in PRIOR_BRANCH_MODES})
            evaluation["branches"][name] = extra["branches"]["original"]
        return {"context": {"as_of_date": "2023-01-02"}, "branches": branches, "evaluation": evaluation}, matrix

    def test_off_preserves_long_and_short_even_when_long_loses(self) -> None:
        point, matrix = self.point()
        before = deepcopy(point)
        report = action_attribution([point], matrix)
        self.assertEqual(report["risk_policy"], "OFF")
        self.assertEqual(report["policy_status"], "DEFERRED")
        self.assertIsNone(report["policy_hash"])
        self.assertEqual(report["override_count"], 0)
        row = report["points"][0]
        self.assertEqual(row["economic_label"]["actual_direction"], "DOWN")
        for name, result in row["branches"].items():
            raw = before["branches"][name]["decision"]["action"]
            self.assertEqual(result["raw_action"], raw)
            self.assertEqual(result["executed_action"], raw)
            self.assertEqual(result["execution_action"], "BUY_SELL" if raw == "LONG" else "CASH")
            self.assertEqual(result["policy_reason"], "RISK_POLICY_OFF")
        self.assertEqual(point, before)
        self.assertEqual(json.loads(json.dumps(report, allow_nan=False)), report)

    def test_flat_price_is_down_after_both_legs_costs_and_label_ignores_action(self) -> None:
        point, matrix = self.point(100.)
        row = action_attribution([point], matrix)["points"][0]
        self.assertLess(row["economic_label"]["net_return_long"], -.0069)
        self.assertEqual(row["economic_label"]["actual_direction"], "DOWN")
        for branch in point["branches"].values():
            branch["decision"]["action"] = "SHORT"
        for result in point["evaluation"]["branches"].values():
            result.update(executed_action="CASH", cycle_net_return=0., correct=True)
        cash = action_attribution([point], matrix)["points"][0]
        self.assertEqual(cash["economic_label"], row["economic_label"])
        self.assertTrue(all(b["cycle_net_return"] == 0. for b in cash["branches"].values()))

    def test_profitable_long_label_remains_up_with_cash_comparator(self) -> None:
        point, matrix = self.point(110.)
        row = action_attribution([point], matrix)["points"][0]
        self.assertEqual(row["economic_label"]["actual_direction"], "UP")
        self.assertTrue(row["branches"][matrix[0]]["correct"])
        self.assertFalse(row["branches"][matrix[1]]["correct"])

    def test_silent_override_or_invalid_cycle_result_is_rejected(self) -> None:
        point, matrix = self.point()
        for change in ({"executed_action": "CASH"}, {"cycle_net_return": 0.},
                       {"correct": True}, {"cycle_net_return": float("nan")}):
            with self.subTest(change=change):
                modified = deepcopy(point)
                modified["evaluation"]["branches"][matrix[0]].update(change)
                with self.assertRaisesRegex(ValueError, "Policy OFF"):
                    action_attribution([modified], matrix)

    def test_forged_economic_label_or_return_is_rejected(self) -> None:
        point, matrix = self.point()
        for change in ({"actual_direction": "UP"}, {"net_return_long": .1},
                       {"net_return_long": float("nan")}):
            with self.subTest(change=change):
                modified = deepcopy(point)
                modified["evaluation"].update(change)
                with self.assertRaises(ValueError):
                    action_attribution([modified], matrix)

    def test_report_does_not_score_pending_and_rejects_unregistered_policy(self) -> None:
        point, _ = self.point()
        plan = {"candidate_registry": registry(), "symbol_cutoffs": {"FPT": ["2023-01-02"]},
                "cohort_id": "fixture", "split": "fixture"}
        point["branches"]["C3"]["status"] = "pending"
        report = candidate_report(plan, {"FPT": [point]})
        self.assertEqual(report["stocks"]["FPT"]["action_attribution"]["points"], [])
        self.assertEqual(report["stocks"]["FPT"]["completed"], 0)
        self.assertIsNone(report["candidate_delta_return_pp"]["C3"])
        plan["candidate_registry"]["risk_policy"] = "ON"
        with self.assertRaisesRegex(ValueError, "ablation"):
            candidate_report(plan, {})


if __name__ == "__main__":
    unittest.main()
