"""Sinh nhãn LONG T+2.5 từ giá thực thi đã xác minh và hàm kinh tế của engine."""

from __future__ import annotations

from typing import Any

from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_memory import (
    DEFAULT_DATA_DIR, SYMBOLS, ExecutionLoader, is_bullish, iso_date, validate_signals,
)
from core.execution_prices import execution_prices_for_cycle, load_verified_execution_data


class HistoricalOutcomeGenerator:
    """Sinh kết quả giả định LONG; SHORT giữ tiền mặt, không tạo vị thế bán khống."""

    def __init__(self, execution_loader: ExecutionLoader | None = None) -> None:
        self.execution_loader = execution_loader or (
            lambda symbol: load_verified_execution_data(DEFAULT_DATA_DIR, symbol)
        )

    def generate(
        self, symbol: str, as_of_date: str, entry_date: str, exit_date: str,
        agent_signals: dict[str, str], *, settled_as_of: str,
    ) -> dict[str, Any]:
        """Chỉ gắn nhãn khi đã có Close(t+3); dùng lợi nhuận sau phí cả hai chiều."""
        if type(symbol) is not str or symbol not in SYMBOLS:
            raise ValueError("Mã cổ phiếu không hợp lệ")
        dates = [iso_date(value) for value in (as_of_date, entry_date, exit_date)]
        completed = iso_date(settled_as_of)
        if not dates[0] < dates[1] < dates[2] or dates[2] > completed:
            raise ValueError("Chu kỳ sai thứ tự ngày hoặc chưa tất toán tại settled_as_of")
        validate_signals(agent_signals)
        frame, events = self.execution_loader(symbol)
        entry, exit_close = execution_prices_for_cycle(frame, events, *dates)
        net_return = float(compute_round_trip_net_return(entry, exit_close, fee=0.0025, slippage=0.001))
        profitable = bool(net_return > 0.0)
        bullish = any(is_bullish(agent_signals[key]) for key in ("trend", "pattern"))
        return {
            "actual_direction": "UP" if profitable else "DOWN",
            "net_return_pct": float(net_return * 100.0),
            "was_bull_trap": bool(bullish and not profitable),
            "result": "WIN_IF_LONG" if profitable else "LOSS_IF_LONG",
        }
