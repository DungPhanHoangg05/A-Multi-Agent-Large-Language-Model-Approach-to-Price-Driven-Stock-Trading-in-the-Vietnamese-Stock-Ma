"""Đối soát nhãn và tài khoản MT-BICL bằng helper kinh tế hiện hành."""

from __future__ import annotations
from dataclasses import asdict
import math
from typing import Any
import pandas as pd
from core.backtest_engine import TestPoint, compute_account_metrics, compute_round_trip_net_return
from core.execution_prices import execution_prices_for_cycle
from core.research_metrics import cycle_risk

def evaluate_cycle(frame: pd.DataFrame, events: list[dict[str, Any]], cutoff: str) -> dict[str, Any]:
    """Mở giá query sau khi mọi action đã cố định; đúng phiên Open(t+1)/Close(t+3)."""
    dates = pd.DatetimeIndex(frame.Datetime)
    if not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError("Lịch giá không tăng duy nhất")
    index = int(dates.get_indexer([pd.Timestamp(cutoff)])[0])
    if index < 0 or index+3 >= len(dates):
        raise ValueError("Thiếu phiên thực thi T+2.5")
    entry, exit_date = (dates[index+i].strftime("%Y-%m-%d") for i in (1, 3))
    opening, closing = execution_prices_for_cycle(frame, events, cutoff, entry, exit_date)
    net = float(compute_round_trip_net_return(opening, closing))
    return {"entry_date": entry, "exit_date": exit_date, "entry_open": float(opening),
            "exit_close": float(closing), "net_return_long": net, "actual_direction": "UP" if net > 0 else "DOWN"}


def account(points: list[dict[str, Any]], branch: str) -> dict[str, Any]:
    """Một tài khoản/mã/nhánh/lượt; dùng nguyên engine và kiểm lãi kép độc lập."""
    if not points or len({p["point_id"] for p in points}) != len(points):
        raise ValueError("Tài khoản cần support không rỗng, không trùng point")
    if len({p["symbol"] for p in points}) != 1 or len({p["repeat_index"] for p in points}) != 1:
        raise ValueError("Không gộp mã hoặc repeat vào tài khoản primary")
    tests = []
    equity, peak, drawdown = 50_000_000., 50_000_000., 0.
    for i, point in enumerate(points):
        action = point["branches"][branch]["action"]
        if action not in ("LONG", "SHORT", "CASH"):
            raise ValueError("Action chưa hợp lệ, không chuyển lỗi thành CASH")
        evaluation = point["evaluation"]
        net = float(compute_round_trip_net_return(evaluation["entry_open"], evaluation["exit_close"]))
        equity *= 1+net if action == "LONG" else 1
        peak = max(peak, equity)
        drawdown = max(drawdown, (1-equity/peak)*100)
        decision = "LONG" if action == "LONG" else "SHORT"
        correct = bool((decision == "LONG") == (evaluation["actual_direction"] == "UP"))
        tests.append(TestPoint(test_id=i+1, window_start=point["as_of_date"], window_end=point["as_of_date"],
            actual_prev_close=0., actual_next_close=evaluation["exit_close"], actual_direction=evaluation["actual_direction"],
            actual_pct_change=net*100, pred_full=decision, pred_no_alpha=decision, correct_full=correct, correct_no_alpha=correct,
            confidence_full="", confidence_no_alpha="", rr_full="", rr_no_alpha="", time_full_sec=0., time_no_alpha_sec=0.,
            entry_open=evaluation["entry_open"], exit_close=evaluation["exit_close"],
            entry_time=evaluation["entry_date"], exit_time=evaluation["exit_date"]))
    metrics = asdict(compute_account_metrics(tests, fee=.0025, slippage=.001, initial_capital_vnd=50_000_000.)["full"])
    if not math.isclose(metrics["final_equity_vnd"], equity, abs_tol=1e-6, rel_tol=1e-12) or not math.isclose(metrics["max_drawdown_pct"], drawdown, abs_tol=1e-8):
        raise ValueError("Tài khoản engine lệch phép kiểm lãi kép độc lập")
    # Không xuất annualization mặc định của engine cho cohort lấy mẫu thưa.
    metrics = {k: v for k, v in metrics.items() if k not in ("sharpe_ratio", "sortino_ratio")}
    return {"point_ids": [p["point_id"] for p in points], "metrics": metrics,
            "risk": cycle_risk(metrics["period_returns"]),
            "cycles": [{"point_id": p["point_id"], "executed_action": t.executed_action_full,
                        "skip_reason": t.execution_skip_reason_full, "equity_vnd": t.equity_full_vnd,
                        "transaction_fee_vnd": t.transaction_fee_full_vnd, "slippage_cost_vnd": t.slippage_cost_full_vnd}
                       for p, t in zip(points, tests)]}


def check_labels(episode: dict[str, Any], bank: dict[str, Any],
                 sources: dict[str, tuple[pd.DataFrame, list[dict[str, Any]]]] | None = None) -> int:
    """Đọc nhãn chỉ của context đã đóng; đối chiếu helper kinh tế, không mở y query."""
    observations = [r for task in episode["prior"] for r in task["observations"]]+episode["target"]
    for row in observations:
        if row["exit_date"] >= episode["query"]["as_of_date"]:
            raise ValueError("Nhãn context chưa đóng trước query")
        original = bank.get(row["episode_id"])
        if sources is None:
            if original is None:
                raise ValueError("Cycle streaming cần nguồn giá đã xác minh")
            outcome = original["outcome"]
            net = float(compute_round_trip_net_return(outcome["entry_open"], outcome["exit_close"]))
        else:
            cycle = evaluate_cycle(*sources[row["symbol"]], row["as_of_date"])
            if row["entry_date"] != cycle["entry_date"] or row["exit_date"] != cycle["exit_date"]:
                raise ValueError("Context sai lịch phiên T+2.5")
            net = cycle["net_return_long"]
        if original is not None and (any(row[k] != original[k] for k in ("symbol", "as_of_date", "entry_date", "exit_date", "task_id"))
                or original["outcome"]["y"] != int(net > 0)
                or not math.isclose(original["outcome"]["r_net"], net, abs_tol=1e-12, rel_tol=0)):
            raise ValueError("Nhãn bank khác nguồn giá context")
        if row["y"] != int(net > 0) or not math.isclose(row["r_net"], net, abs_tol=1e-12, rel_tol=0):
            raise ValueError("Nhãn/membership context khác nguồn kinh tế hoặc vi phạm PIT")
    return len(observations)
