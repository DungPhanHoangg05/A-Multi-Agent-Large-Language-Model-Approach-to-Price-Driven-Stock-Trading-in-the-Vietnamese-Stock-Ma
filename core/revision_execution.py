"""Ledger sensitivity độc lập; giữ nguyên engine/ledger và predictions đã khóa."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def execution_ledger(frame: pd.DataFrame, cycles: list[tuple[int, int, int, str]],
                     scenario: dict[str, Any], initial: float, multiplier: float = 1000.) -> dict[str, Any]:
    """Chuyển trạng thái tiền/cổ phiếu theo events, không lặp từng dòng Pandas.

    Các proxy daily OHLCV là ràng buộc ex-post cho fills, không phải tín hiệu
    biết trước tại open. Cap planning chỉ dùng Volume tới phiên trước.
    """
    if not cycles or not np.isfinite(initial) or initial <= 0 or not np.isfinite(multiplier) or multiplier <= 0:
        raise ValueError("Lịch/vốn/multiplier không hợp lệ")
    fee, slip, charge = (float(scenario[k]) for k in ("fee_each_side", "slippage_each_side", "sell_charge"))
    if any(not np.isfinite(v) or not 0 <= v < 1 for v in (fee, slip, charge)) or fee + charge >= 1:
        raise ValueError("Chi phí không hợp lệ")
    if scenario["cash_mode"] not in ("immediate", "pending", "advance_auto", "advance_on_demand"):
        raise ValueError("Cash mode không được hỗ trợ")
    for key in ("settlement_lag", "stock_lag", "entry_delay", "tail_sessions", "lot_size"):
        if type(scenario[key]) is not int or scenario[key] < 0:
            raise ValueError("Tham số session/lot phải là integer không âm")
    if not np.isfinite(scenario["advance_annual_rate"]) or scenario["advance_annual_rate"] < 0:
        raise ValueError("Advance rate không hợp lệ")
    if scenario["participation"] is not None and not 0 < scenario["participation"] <= 1:
        raise ValueError("Participation phải trong (0,1]")
    previous = -1
    for entry, exit_index, action, _ in cycles:
        if entry <= previous or not 0 <= entry <= exit_index < len(frame) or action not in (0, 1):
            raise ValueError("Lịch chồng lấn hoặc không hợp lệ")
        previous = exit_index
    dates = pd.to_datetime(frame["date"]).to_numpy()
    if len(np.unique(dates)) != len(dates) or np.any(dates[1:] <= dates[:-1]):
        raise ValueError("Calendar phải tăng dần, không trùng")
    prices = frame[["Open", "High", "Low", "Close"]].to_numpy(float)
    volume = frame["Volume"].to_numpy(float)
    if not np.all(np.isfinite(prices)) or np.any(prices <= 0) or not np.all(np.isfinite(volume)) or np.any(volume < 0):
        raise ValueError("Giá/volume không hợp lệ")
    # Vector hóa proxy và capacity; vòng event bên dưới cần trạng thái tuần tự.
    blocked = (volume == 0) | np.isclose(prices[:, 1], prices[:, 2], atol=1e-10, rtol=0)
    cap = (pd.Series(volume).rolling(20, min_periods=20).mean().shift(1).to_numpy() *
           float(scenario["participation"])) if scenario["participation"] is not None else np.full(len(frame), np.inf)
    first = cycles[0][0]
    last = min(len(frame) - 1, cycles[-1][1] + int(scenario["tail_sessions"]))
    scheduled = {e: (e, x, a, key) for e, x, a, key in cycles}
    cash, shares = float(initial), 0.
    pending: list[tuple[int, float]] = []
    waiting: tuple[int, int, int, str] | None = None
    position: tuple[int, int, str] | None = None
    events, daily, equity = [], [], [float(initial)]
    totals = {"brokerage_fee_vnd": 0., "slippage_cost_vnd": 0., "sell_charge_vnd": 0., "advance_fee_vnd": 0.}
    n_orders = 0

    def event(index: int, phase: str, side: str, status: str, key: str, quantity: float = 0., **extra: Any) -> None:
        """Không biến bar timestamp 07:00 thành clock time của fill."""
        events.append({"date": str(pd.Timestamp(dates[index]).date()), "phase": phase, "timezone": "Asia/Ho_Chi_Minh",
                       "clock_time": None, "side": side, "status": status, "unit_id": key,
                       "quantity": float(quantity), **extra})

    def advance(amount: float, release: int, now: int) -> tuple[float, float] | None:
        """Chiết khấu receivable ACT/365, không đoán maturity ngoài calendar."""
        if release >= len(dates):
            return None
        days = max(0, int((dates[release] - dates[now]) / np.timedelta64(1, "D")))
        financing = amount * float(scenario["advance_annual_rate"]) * days / 365
        if financing >= amount:
            raise ValueError("Phí ứng trước vượt principal")
        return amount - financing, financing

    for index in range(first, last + 1):
        # Tiền settled trong buổi chiều T+2 không chi được tại open cùng ngày.
        cash += sum(amount for release, amount in pending if release < index)
        pending = [(release, amount) for release, amount in pending if release >= index]
        costs = {k: 0. for k in totals}
        if index in scheduled:
            if waiting is not None:
                event(index, "open", "BUY", "superseded", waiting[3])
            waiting = None
            candidate = scheduled[index]
            if candidate[2]:
                if shares > 0:
                    event(index, "open", "BUY", "position_not_flat", candidate[3])
                else:
                    waiting = candidate
        if waiting is not None:
            entry, planned_exit, _, key = waiting
            reason = None
            if scenario["all_entries_missed"]:
                reason = "all_entries_missed_bound"
            elif scenario["block_proxy"] and blocked[index]:
                reason = "zero_volume_or_flat_bar_proxy"
            elif scenario["participation"] is not None and (not np.isfinite(cap[index]) or cap[index] <= 0):
                reason = "capacity_unavailable"
            if reason is None and scenario["cash_mode"] == "advance_on_demand":
                remaining = []
                for release, amount in pending:
                    result = advance(amount, release, index)
                    if result is None:
                        remaining.append((release, amount))
                    else:
                        available, financing = result
                        cash += available
                        costs["advance_fee_vnd"] += financing
                        event(index, "open", "ADVANCE", "assigned_receivable", key, principal_vnd=float(amount), fee_vnd=float(financing))
                pending = remaining
            if reason is None:
                effective_open = prices[index, 0] * multiplier * (1 + slip)
                quantity = min(cash / (effective_open * (1 + fee)), float(cap[index]))
                lot = int(scenario["lot_size"])
                if lot:
                    quantity = float(np.floor(quantity / lot) * lot)
                if quantity <= 1e-12:
                    reason = "no_settled_cash_or_lot_capacity"
                else:
                    notional = quantity * effective_open
                    costs["brokerage_fee_vnd"] += notional * fee
                    costs["slippage_cost_vnd"] += quantity * prices[index, 0] * multiplier * slip
                    cash -= notional * (1 + fee)
                    if cash < -1e-7:
                        raise ArithmeticError("Cash âm sau BUY")
                    cash = max(0., cash)
                    shares = float(quantity)
                    position = (index, max(planned_exit, index + int(scenario["stock_lag"])), key)
                    event(index, "open", "BUY", "filled", key, shares, planned_entry=entry, planned_exit=planned_exit,
                          fill_price_vnd=float(effective_open))
                    n_orders += 1
                    waiting = None
            if reason is not None:
                event(index, "open", "BUY", reason, key)
                if index >= entry + int(scenario["entry_delay"]):
                    waiting = None
        held = int(shares > 0)
        if position is not None and index >= position[1]:
            entry, _, key = position
            reason = None
            if index < entry + int(scenario["stock_lag"]):
                reason = "stock_unsettled"
            elif scenario["block_proxy"] and blocked[index]:
                reason = "zero_volume_or_flat_bar_proxy"
            elif scenario["participation"] is not None and (not np.isfinite(cap[index]) or shares > cap[index] + 1e-9):
                reason = "exit_above_planning_capacity"
            if reason is not None:
                event(index, "close", "SELL", reason, key, shares)
            else:
                quoted = shares * prices[index, 3] * multiplier
                notional = quoted * (1 - slip)
                costs["brokerage_fee_vnd"] += notional * fee
                costs["slippage_cost_vnd"] += quoted * slip
                costs["sell_charge_vnd"] += notional * charge
                proceeds = notional * (1 - fee - charge)
                release = index + int(scenario["settlement_lag"])
                if scenario["cash_mode"] == "immediate":
                    cash += proceeds
                elif scenario["cash_mode"] == "advance_auto":
                    result = advance(proceeds, release, index)
                    if result is None:
                        pending.append((release, proceeds))
                        event(index, "close", "ADVANCE", "maturity_outside_snapshot", key)
                    else:
                        available, financing = result
                        cash += available
                        costs["advance_fee_vnd"] += financing
                else:
                    pending.append((release, proceeds))
                event(index, "close", "SELL", "filled", key, shares, fill_price_vnd=float(prices[index, 3] * multiplier * (1 - slip)),
                      proceeds_vnd=float(proceeds), settlement_bar_index=release)
                shares, position = 0., None
                n_orders += 1
        cash += sum(amount for release, amount in pending if release <= index)
        pending = [(release, amount) for release, amount in pending if release > index]
        pending_value = float(sum(amount for _, amount in pending))
        stock_value = float(shares * prices[index, 3] * multiplier)
        settled_shares = float(shares if position is not None and index >= position[0] + int(scenario["stock_lag"]) else 0.)
        wealth = float(cash + pending_value + stock_value)
        if not np.isfinite(wealth) or wealth <= 0:
            raise ArithmeticError("Wealth không hợp lệ")
        equity.append(wealth)
        for key in totals:
            totals[key] += costs[key]
        daily.append({"date": str(pd.Timestamp(dates[index]).date()), "settled_cash_vnd": float(cash),
                      "pending_cash_vnd": pending_value, "shares": float(shares), "stock_mtm_vnd": stock_value,
                      "settled_shares": settled_shares, "unsettled_shares": float(shares - settled_shares),
                      "equity_vnd": wealth, "held_during_session": held, **costs})
    values = np.asarray(equity)
    drawdown = 1 - values / np.maximum.accumulate(values)
    summary = {"net_return_pct": float((values[-1] / initial - 1) * 100), "daily_close_drawdown_pct": float(drawdown.max() * 100),
               "order_count": n_orders, "n_planned_cycles": len(cycles), "n_planned_long": sum(c[2] for c in cycles),
               "n_buy_fills": sum(e["side"] == "BUY" and e["status"] == "filled" for e in events),
               "n_sell_fills": sum(e["side"] == "SELL" and e["status"] == "filled" for e in events),
               "n_blocked_attempts": sum(e["status"] not in ("filled", "assigned_receivable") for e in events),
               "n_daily_rows": len(daily), "final_settled_cash_vnd": float(cash),
               "final_pending_cash_vnd": daily[-1]["pending_cash_vnd"], "final_shares": float(shares),
               "terminal_is_liquidated": bool(shares == 0), **totals}
    return {"summary": summary, "events": events, "daily": daily}
