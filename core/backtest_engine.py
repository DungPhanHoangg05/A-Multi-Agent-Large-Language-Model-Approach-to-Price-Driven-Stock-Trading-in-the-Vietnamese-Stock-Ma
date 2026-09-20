import json
import os
import time
import threading
from copy import deepcopy
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from utils import static_util
from default_config import DEFAULT_CONFIG
from data_manager.sentiment_cache import BacktestSentimentStore
from utils.statistical_tests import calculate_metrics_with_significance
from utils.graph_setup import ABLATION_CONFIGS


ALPHA_HISTORY_CANDLES = 600


def required_backtest_rows(
    n_tests: int,
    window_size: int,
    step: int,
    lookahead: int,
    alpha_history: int = ALPHA_HISTORY_CANDLES,
) -> int:
    """Số nến tối thiểu để mọi test point có đủ lịch sử Alpha."""
    if n_tests < 1 or window_size < 1 or step < 1 or lookahead < 1:
        raise ValueError("n_tests, window_size, step và lookahead phải là số dương")
    decision_history = max(window_size, alpha_history)
    return decision_history + lookahead + (n_tests - 1) * step


def build_walk_forward_end_indices(
    total: int,
    n_tests: int,
    window_size: int,
    step: int,
    lookahead: int,
    alpha_history: int = ALPHA_HISTORY_CANDLES,
) -> List[int]:
    """Tạo đúng N mốc walk-forward, không cho phép Alpha fallback."""
    required = required_backtest_rows(
        n_tests, window_size, step, lookahead, alpha_history
    )
    if total < required:
        raise ValueError(
            "Không đủ dữ liệu cho dynamic alpha trong backtest: "
            f"cần ít nhất {required} nến để {n_tests} test point "
            f"có {max(window_size, alpha_history)} nến tiền kiểm tra; "
            f"hiện có {total}."
        )

    max_end = total - lookahead
    min_end = max(window_size, alpha_history)
    latest_first = [max_end - offset * step for offset in range(n_tests)]
    if latest_first[-1] < min_end:
        raise ValueError(
            f"Mốc test sớm nhất chỉ có {latest_first[-1]} nến; "
            f"dynamic alpha cần {min_end}."
        )
    return list(reversed(latest_first))


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class TestPoint:
    test_id: int
    window_start: str
    window_end: str
    actual_prev_close: float
    actual_next_close: float
    actual_direction: str           # "UP" nếu net return LONG > 0, ngược lại "DOWN"
    actual_pct_change: float        # % return Open-to-Close sau phí

    # Full system (có Alpha Agent)
    pred_full: str                  # Hợp đồng output: "LONG" | "SHORT"
    correct_full: bool
    confidence_full: str
    rr_full: str

    # No-Alpha system
    pred_no_alpha: str
    correct_no_alpha: bool
    confidence_no_alpha: str
    rr_no_alpha: str

    # Thời gian chạy
    time_full_sec: float
    time_no_alpha_sec: float

    # Giá tham chiếu của điểm dự báo: Open(e) và Close(e-1+L).
    # Mỗi điểm là một chu kỳ khép kín: LONG mua tại Open(e) và bán tại
    # Close(e-1+L); SHORT giữ tiền mặt. Không mang vị thế sang điểm kế tiếp.
    entry_open: float = 0.0
    exit_close: float = 0.0
    entry_price_vnd: float = 0.0
    exit_price_vnd: float = 0.0
    entry_time: str = ""
    exit_time: str = ""
    execution_pct_change: float = 0.0  # gross return Open(e) -> Close(exit)
    executed_action_full: str = "CASH"
    executed_action_no_alpha: str = "CASH"
    execution_skip_reason_full: str = ""
    execution_skip_reason_no_alpha: str = ""
    account_return_full: float = 0.0
    account_return_no_alpha: float = 0.0
    equity_full: float = 1.0
    equity_no_alpha: float = 1.0
    cash_full_vnd: float = 0.0
    cash_no_alpha_vnd: float = 0.0
    shares_full: float = 0.0
    shares_no_alpha: float = 0.0
    position_value_full_vnd: float = 0.0
    position_value_no_alpha_vnd: float = 0.0
    equity_full_vnd: float = 0.0
    equity_no_alpha_vnd: float = 0.0
    transaction_fee_full_vnd: float = 0.0
    transaction_fee_no_alpha_vnd: float = 0.0
    slippage_cost_full_vnd: float = 0.0
    slippage_cost_no_alpha_vnd: float = 0.0

    # P&L lãi kép tại thời điểm này
    pnl_full: float = 0.0           # % lợi nhuận lũy kế Full system
    pnl_no_alpha: float = 0.0       # % lợi nhuận lũy kế No-Alpha system

    # Lỗi
    error_full: str = ""
    error_no_alpha: str = ""
    decision_source_full: str = ""
    decision_source_no_alpha: str = ""
    decision_fallback_reason_full: str = ""
    decision_fallback_reason_no_alpha: str = ""


@dataclass
class PartialSummary:
    n_completed: int = 0
    n_valid_full: int = 0
    n_valid_no: int = 0
    acc_full: float = 0.0
    acc_no_alpha: float = 0.0
    alpha_lift: float = 0.0
    n_correct_full: int = 0
    n_correct_no: int = 0
    pnl_full: float = 0.0
    pnl_no_alpha: float = 0.0
    pnl_full_vnd: float = 0.0
    pnl_no_alpha_vnd: float = 0.0
    equity_full_vnd: float = 50_000_000.0
    equity_no_alpha_vnd: float = 50_000_000.0
    initial_capital_vnd: float = 50_000_000.0
    sharpe_full: float = 0.0
    sharpe_no_alpha: float = 0.0
    mdd_full: float = 0.0
    mdd_no_alpha: float = 0.0
    equity_curve_full: List[float] = field(default_factory=lambda: [1.0])
    equity_curve_no_alpha: List[float] = field(default_factory=lambda: [1.0])


@dataclass
class AccountMetrics:
    """Các chỉ số kinh tế tính trên đường vốn tài khoản lãi kép."""

    total_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    hit_rate_pct: float
    avg_trade_pct: float
    equity_curve: List[float]
    period_returns: List[float]
    initial_capital_vnd: float
    final_equity_vnd: float
    total_pnl_vnd: float
    final_cash_vnd: float
    final_shares: float
    equity_curve_vnd: List[float]

@dataclass
class BacktestSummary:
    symbol: str
    timeframe: str
    n_tests: int
    window_size: int
    step: int
    started_at: str
    ended_at: str
    data_start: str
    data_end: str

    # Full system
    acc_full: float
    long_win_full: float
    short_win_full: float
    n_long_full: int
    n_short_full: int

    # No-Alpha system
    acc_no_alpha: float
    long_win_no_alpha: float
    short_win_no_alpha: float
    n_long_no_alpha: int
    n_short_no_alpha: int

    # So sánh Alpha contribution
    alpha_lift: float               # acc_full - acc_no_alpha (%)
    alpha_helps: bool               # True nếu alpha tốt hơn

    # Kiểm định ý nghĩa thống kê trên common support Full/No-Alpha
    mcnemar_p_value: float = 1.0
    is_significant_05: bool = False
    alpha_lift_ci_95: List[float] = field(default_factory=lambda: [0.0, 0.0])
    newey_west_statistic: float = 0.0
    newey_west_p_value: float = 1.0

    # Advanced PnL metrics Full
    pnl_full: float = 0.0
    sharpe_full: float = 0.0
    sortino_full: float = 0.0
    mdd_full: float = 0.0
    hit_rate_full: float = 0.0
    avg_trade_full: float = 0.0

    # Advanced PnL metrics No-Alpha
    pnl_no_alpha: float = 0.0
    sharpe_no_alpha: float = 0.0
    sortino_no_alpha: float = 0.0
    mdd_no_alpha: float = 0.0
    hit_rate_no_alpha: float = 0.0
    avg_trade_no_alpha: float = 0.0
    equity_curve_full: List[float] = field(default_factory=lambda: [1.0])
    equity_curve_no_alpha: List[float] = field(default_factory=lambda: [1.0])
    initial_capital_vnd: float = 50_000_000.0
    equity_full_vnd: float = 50_000_000.0
    equity_no_alpha_vnd: float = 50_000_000.0
    pnl_full_vnd: float = 0.0
    pnl_no_alpha_vnd: float = 0.0
    cash_full_vnd: float = 50_000_000.0
    cash_no_alpha_vnd: float = 50_000_000.0
    shares_full: float = 0.0
    shares_no_alpha: float = 0.0
    equity_curve_full_vnd: List[float] = field(default_factory=lambda: [50_000_000.0])
    equity_curve_no_alpha_vnd: List[float] = field(default_factory=lambda: [50_000_000.0])

    test_points: List[dict] = field(default_factory=list)


def _validate_account_costs(fee: float, slippage: float) -> Tuple[float, float, float]:
    """Chuẩn hóa chi phí và trả về (fee, slippage, total_cost)."""

    def validate_cost(name: str, value: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} phải là số hữu hạn không âm") from exc
        if not np.isfinite(parsed) or parsed < 0.0:
            raise ValueError(f"{name} phải là số hữu hạn không âm")
        return parsed

    parsed_fee = validate_cost("fee", fee)
    parsed_slippage = validate_cost("slippage", slippage)
    total_cost = parsed_fee + parsed_slippage
    if total_cost >= 1.0:
        raise ValueError("Tổng fee + slippage phải nhỏ hơn 100%")
    return parsed_fee, parsed_slippage, total_cost


def compute_round_trip_net_return(
    entry_open: float,
    exit_close: float,
    fee: float = 0.0025,
    slippage: float = 0.001,
) -> float:
    """Return của một vòng BUY rồi SELL, tính phí và trượt giá từng chiều."""
    fee, slippage, _ = _validate_account_costs(fee, slippage)
    entry_open = float(entry_open)
    exit_close = float(exit_close)
    if (
        not np.isfinite(entry_open)
        or not np.isfinite(exit_close)
        or entry_open <= 0.0
        or exit_close <= 0.0
    ):
        raise ValueError("Giá entry/exit phải là số dương hữu hạn")
    buy_factor = (1.0 + slippage) * (1.0 + fee)
    sell_factor = (1.0 - slippage) * (1.0 - fee)
    return exit_close / entry_open * sell_factor / buy_factor - 1.0


def compute_account_metrics(
    test_points: List[TestPoint],
    allow_shorting: bool = False,
    fee: float = 0.0025,
    slippage: float = 0.001,
    initial_capital_vnd: float = 50_000_000.0,
    price_multiplier: float = 1_000.0,
) -> Dict[str, AccountMetrics]:
    """Mô phỏng hai tài khoản theo các chu kỳ Open-to-Close khép kín.

    Mỗi LONG dùng toàn bộ tiền để BUY tại Open rồi tự động SELL tại target Close.
    Mỗi SHORT giữ CASH trong toàn bộ horizon vì không bán khống cổ phiếu cơ sở.
    Phí môi giới và trượt giá được áp dụng riêng trên cả hai chiều BUY/SELL.
    Cách thực thi này đồng nhất tuyệt đối horizon của P&L với horizon chấm nhãn.
    """

    del allow_shorting  # Giữ tham số tương thích; hợp đồng mới luôn là long-only.
    fee, slippage, _ = _validate_account_costs(fee, slippage)
    initial_capital_vnd = float(initial_capital_vnd)
    price_multiplier = float(price_multiplier)
    if not np.isfinite(initial_capital_vnd) or initial_capital_vnd <= 0.0:
        raise ValueError("initial_capital_vnd phải là số dương hữu hạn")
    if not np.isfinite(price_multiplier) or price_multiplier <= 0.0:
        raise ValueError("price_multiplier phải là số dương hữu hạn")

    def compute_variant(prediction_field: str, variant: str) -> AccountMetrics:
        cash_vnd = initial_capital_vnd
        previous_equity_vnd = initial_capital_vnd
        equity_curve_vnd = [initial_capital_vnd]
        equity_curve = [1.0]
        period_returns: List[float] = []
        executed_returns: List[float] = []
        previous_entry_time: Optional[pd.Timestamp] = None
        previous_exit_time: Optional[pd.Timestamp] = None

        for point in test_points:
            prediction = getattr(point, prediction_field)
            try:
                entry_open = float(point.entry_open)
                exit_close = float(point.exit_close)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"TestPoint {point.test_id}: giá entry/exit phải là số dương hữu hạn"
                ) from exc
            if (
                not np.isfinite(entry_open)
                or not np.isfinite(exit_close)
                or entry_open <= 0.0
                or exit_close <= 0.0
            ):
                raise ValueError(
                    f"TestPoint {point.test_id}: giá entry/exit phải là số dương hữu hạn"
                )

            try:
                entry_time = pd.Timestamp(point.entry_time)
                exit_time = pd.Timestamp(point.exit_time)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"TestPoint {point.test_id}: thời điểm entry/exit không hợp lệ"
                ) from exc
            if pd.isna(entry_time) or pd.isna(exit_time) or exit_time < entry_time:
                raise ValueError(
                    f"TestPoint {point.test_id}: thời điểm entry/exit không hợp lệ"
                )
            if previous_entry_time is not None and entry_time < previous_entry_time:
                raise ValueError("TestPoint phải được sắp xếp theo entry_time tăng dần")
            if previous_exit_time is not None and entry_time <= previous_exit_time:
                raise ValueError(
                    "Các test point chồng lấn thời gian; chu kỳ giao dịch yêu cầu "
                    "step >= lookahead"
                )
            previous_entry_time = entry_time
            previous_exit_time = exit_time

            long_gross_return = exit_close / entry_open - 1.0
            point.execution_pct_change = round(long_gross_return * 100.0, 8)
            entry_price_vnd = entry_open * price_multiplier
            exit_price_vnd = exit_close * price_multiplier
            point.entry_price_vnd = round(entry_price_vnd, 4)
            point.exit_price_vnd = round(exit_price_vnd, 4)
            executed_action = "CASH"
            skip_reason = ""
            transaction_fee_vnd = 0.0
            slippage_cost_vnd = 0.0
            shares_bought = 0.0

            if prediction == "LONG":
                capital_before_trade = cash_vnd
                effective_buy_price = entry_price_vnd * (1.0 + slippage)
                buy_notional_vnd = capital_before_trade / (1.0 + fee)
                shares_bought = buy_notional_vnd / effective_buy_price
                buy_fee_vnd = buy_notional_vnd * fee
                buy_slippage_vnd = shares_bought * entry_price_vnd * slippage

                quoted_sell_value_vnd = shares_bought * exit_price_vnd
                sell_notional_vnd = quoted_sell_value_vnd * (1.0 - slippage)
                sell_fee_vnd = sell_notional_vnd * fee
                sell_slippage_vnd = quoted_sell_value_vnd - sell_notional_vnd
                cash_vnd = sell_notional_vnd - sell_fee_vnd

                transaction_fee_vnd = buy_fee_vnd + sell_fee_vnd
                slippage_cost_vnd = buy_slippage_vnd + sell_slippage_vnd
                trade_return = cash_vnd / capital_before_trade - 1.0
                expected_return = compute_round_trip_net_return(
                    entry_open,
                    exit_close,
                    fee=fee,
                    slippage=slippage,
                )
                if not np.isclose(trade_return, expected_return, atol=1e-12):
                    raise ArithmeticError(
                        f"TestPoint {point.test_id}: P&L vòng LONG lệch mục tiêu nhãn"
                    )
                executed_returns.append(trade_return)
                executed_action = "BUY_SELL"
            elif prediction == "SHORT":
                executed_action = "CASH"
                skip_reason = "SHORT_STAYS_CASH"
            else:
                skip_reason = "INVALID_PREDICTION"

            # Chu kỳ luôn kết thúc bằng CASH; shares_bought chỉ phục vụ audit
            # phép tính và không được mang sang điểm kiểm định kế tiếp.
            position_value_vnd = 0.0
            shares = 0.0
            equity_vnd = cash_vnd
            if not np.isfinite(equity_vnd) or equity_vnd < 0.0:
                raise ValueError(
                    f"TestPoint {point.test_id}: equity sau giao dịch không hợp lệ"
                )
            period_return = equity_vnd / previous_equity_vnd - 1.0
            previous_equity_vnd = equity_vnd
            period_returns.append(period_return)
            equity_ratio = equity_vnd / initial_capital_vnd
            equity_curve_vnd.append(round(equity_vnd, 4))
            equity_curve.append(round(equity_ratio, 12))

            cumulative_return_pct = (equity_ratio - 1.0) * 100.0
            pnl_vnd = equity_vnd - initial_capital_vnd
            if variant == "full":
                point.executed_action_full = executed_action
                point.execution_skip_reason_full = skip_reason
                point.account_return_full = round(period_return * 100.0, 8)
                point.equity_full = round(equity_ratio, 12)
                point.pnl_full = round(cumulative_return_pct, 8)
                point.cash_full_vnd = round(cash_vnd, 4)
                point.shares_full = round(shares, 8)
                point.position_value_full_vnd = round(position_value_vnd, 4)
                point.equity_full_vnd = round(equity_vnd, 4)
                point.transaction_fee_full_vnd = round(transaction_fee_vnd, 4)
                point.slippage_cost_full_vnd = round(slippage_cost_vnd, 4)
            else:
                point.executed_action_no_alpha = executed_action
                point.execution_skip_reason_no_alpha = skip_reason
                point.account_return_no_alpha = round(period_return * 100.0, 8)
                point.equity_no_alpha = round(equity_ratio, 12)
                point.pnl_no_alpha = round(cumulative_return_pct, 8)
                point.cash_no_alpha_vnd = round(cash_vnd, 4)
                point.shares_no_alpha = round(shares, 8)
                point.position_value_no_alpha_vnd = round(position_value_vnd, 4)
                point.equity_no_alpha_vnd = round(equity_vnd, 4)
                point.transaction_fee_no_alpha_vnd = round(transaction_fee_vnd, 4)
                point.slippage_cost_no_alpha_vnd = round(slippage_cost_vnd, 4)

        returns_array = np.asarray(period_returns, dtype=float)
        if returns_array.size:
            mean_return = float(np.mean(returns_array))
            std_return = float(np.std(returns_array))
            sharpe = (
                mean_return / std_return * np.sqrt(252.0)
                if std_return > 1e-12
                else 0.0
            )
            downside = returns_array[returns_array < 0.0]
            downside_std = float(np.std(downside)) if downside.size else 0.0
            sortino = (
                mean_return / downside_std * np.sqrt(252.0)
                if downside_std > 1e-12
                else 0.0
            )
        else:
            sharpe = sortino = 0.0

        equity_array = np.asarray(equity_curve, dtype=float)
        running_peak = np.maximum.accumulate(equity_array)
        drawdowns = 1.0 - np.divide(
            equity_array,
            running_peak,
            out=np.ones_like(equity_array),
            where=running_peak > 0.0,
        )
        max_drawdown_pct = float(np.max(drawdowns) * 100.0)
        hit_rate_pct = (
            sum(value > 0.0 for value in executed_returns)
            / len(executed_returns)
            * 100.0
            if executed_returns
            else 0.0
        )
        avg_trade_pct = (
            float(np.mean(executed_returns) * 100.0)
            if executed_returns
            else 0.0
        )

        final_equity_vnd = previous_equity_vnd
        return AccountMetrics(
            total_return_pct=(final_equity_vnd / initial_capital_vnd - 1.0) * 100.0,
            sharpe_ratio=float(sharpe),
            sortino_ratio=float(sortino),
            max_drawdown_pct=max_drawdown_pct,
            hit_rate_pct=hit_rate_pct,
            avg_trade_pct=avg_trade_pct,
            equity_curve=equity_curve,
            period_returns=[float(value) for value in period_returns],
            initial_capital_vnd=initial_capital_vnd,
            final_equity_vnd=final_equity_vnd,
            total_pnl_vnd=final_equity_vnd - initial_capital_vnd,
            final_cash_vnd=cash_vnd,
            final_shares=0.0,
            equity_curve_vnd=equity_curve_vnd,
        )

    return {
        "full": compute_variant("pred_full", "full"),
        "no_alpha": compute_variant("pred_no_alpha", "no_alpha"),
    }


# ── Engine ─────────────────────────────────────────────────────────────────────

class BacktestEngine:
    """
    Walk-forward backtest engine.
    Mỗi test point:
      1. Cắt window [end_idx - window_size : end_idx]
      2. Chạy Indicator/Pattern/Trend đúng một lần để tạo shared snapshot
      3. Deep-copy snapshot sang Full và No-Alpha decision graphs
      4. Kiểm tra nến [end_idx] để xác định đúng/sai
    """

    # Rate-limit safety delays (giây)
    DELAY_BETWEEN_VARIANTS = 10.0   # Giữa Full và No-Alpha trong cùng test
    DELAY_BETWEEN_TESTS    = 8.0    # Giữa 2 test points

    def __init__(self, config: dict = None):
        self.config          = {**DEFAULT_CONFIG, **(config or {})}
        self._graph_upstream = None
        self._graph_decision_variants = {}
        self._graph_decision_full = None
        self._graph_decision_no_alpha = None
        self._stop_event     = threading.Event()
        self._started_at     = ""
        self._sentiment_store = None
        self._use_historical_sentiment = config.get("use_historical_sentiment", True)

    def _init_sentiment_store(self, symbol: str, force_recrawl: bool = False):
        """
        Khởi tạo và preload BacktestSentimentStore.
        Gọi một lần trước khi chạy vòng lặp backtest.
        """
        from data_manager.sentiment_cache import BacktestSentimentStore
 
        print(f"\n[BacktestEngine] Đang preload sentiment lịch sử cho {symbol}...")
        self._sentiment_store = BacktestSentimentStore(cache_dir=".")
        self._sentiment_store.preload_symbol(symbol, force_recrawl=force_recrawl)
        print(f"[BacktestEngine] ✓ Sentiment store sẵn sàng cho {symbol}")

    # ── Graph initialization ───────────────────────────────────────────────────

    def _init_graphs(self):
        import os
        from langchain_groq import ChatGroq
        from utils.graph_setup import SetGraph
        from utils.graph_util import TechnicalTools

        api_key = self.config.get("groq_api_key") or os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise ValueError("Groq API key chưa được cấu hình.")

        def make_llm(model, temp=0.0, max_tokens=None):
            kwargs = {
                "model": model,
                "temperature": temp,
                "api_key": api_key,
                "max_retries": 3,
            }
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            model_name = (model or "").lower()
            if any(
                tag in model_name
                for tag in ("qwen3", "gpt-oss", "deepseek", "-r1")
            ):
                kwargs["reasoning_format"] = "hidden"
            return ChatGroq(**kwargs)

        # Đọc temperature từ config thay vì cố định 0.05 — backtest phải tái lập
        # được và dùng đúng cấu hình như đường chạy web.
        agent_llm = make_llm(
            self.config.get("agent_llm_model", "openai/gpt-oss-20b"),
            self.config.get("agent_llm_temperature", 0.0),
            self.config.get("agent_llm_max_tokens", 2048),
        )
        graph_llm = make_llm(
            self.config.get("graph_llm_model", "qwen/qwen3.8-27b"),
            self.config.get("graph_llm_temperature", 0.0),
            self.config.get("graph_llm_max_tokens", 1024),
        )
        toolkit = TechnicalTools()

        graph_builder = SetGraph(agent_llm, graph_llm, toolkit)
        print("[BacktestEngine] Khởi tạo shared upstream graph...")
        self._graph_upstream = graph_builder.compile_upstream()
        self._graph_decision_variants = {
            name: graph_builder.compile_decision(ablation_config=config)
            for name, config in ABLATION_CONFIGS.items()
        }
        # Alias giữ tương thích với giao thức Full vs No-Alpha hiện tại.
        self._graph_decision_full = self._graph_decision_variants["full"]
        self._graph_decision_no_alpha = self._graph_decision_variants["baseline"]

        print("[BacktestEngine] [OK] Bốn decision variants đã sẵn sàng.")

    # ── Data helpers ───────────────────────────────────────────────────────────

    def _prepare_window(
        self, df: pd.DataFrame, end_idx: int, window_size: int
    ) -> Tuple[dict, str, str]:
        """Cắt cửa sổ OHLCV và trả về dict + date strings."""
        start_idx  = max(0, end_idx - window_size)
        window_df  = df.iloc[start_idx:end_idx].reset_index(drop=True)
        ohlcv_dict = {}
        for col in ["Datetime", "Open", "High", "Low", "Close", "Volume"]:
            if col not in window_df.columns:
                continue
            if col == "Datetime":
                ohlcv_dict[col] = window_df[col].dt.strftime("%Y-%m-%d %H:%M:%S").tolist()
            else:
                ohlcv_dict[col] = [float(v) for v in window_df[col]]
        ws = window_df["Datetime"].iloc[0].strftime("%Y-%m-%d")
        we = window_df["Datetime"].iloc[-1].strftime("%Y-%m-%d")
        return ohlcv_dict, ws, we

    def _get_actual_direction(
        self, df: pd.DataFrame, end_idx: int, lookahead: int = 1
    ) -> Tuple[str, float, float, float, float]:
        """
        Lấy nhãn kinh tế sau cửa sổ phân tích.

        Args:
            end_idx   : index cuối cửa sổ (nến cuối cùng agent nhìn thấy)
            lookahead : số nến phía trước để đánh giá.
                        - 1 = entry Open[end_idx], exit Close[end_idx]
                        - 3 = entry Open[end_idx], exit Close[end_idx+2]

        Quy ước: prev_close = close cuối cửa sổ (end_idx - 1)
                 entry_open = open đầu kỳ thực thi (end_idx)
                 next_close = close của nến end_idx + lookahead - 1
        """
        target_idx = end_idx + lookahead - 1
        if target_idx >= len(df):
            return "UNKNOWN", 0.0, 0.0, 0.0, 0.0
        prev_close = float(df["Close"].iloc[end_idx - 1])
        entry_open = float(df["Open"].iloc[end_idx])
        next_close = float(df["Close"].iloc[target_idx])
        if (
            not np.isfinite(entry_open)
            or not np.isfinite(next_close)
            or entry_open <= 0.0
            or next_close <= 0.0
        ):
            raise ValueError("Giá entry/exit phải là số dương hữu hạn")
        fee, slippage, _ = _validate_account_costs(
            self.config.get("tx_cost", 0.0025),
            self.config.get("slippage", 0.001),
        )
        net_return = compute_round_trip_net_return(
            entry_open,
            next_close,
            fee=fee,
            slippage=slippage,
        )
        pct_chg = round(net_return * 100.0, 4)
        # Nhãn accuracy dùng cùng return sau phí với tài khoản. Nhờ đó LONG
        # chỉ đúng khi vị thế mua thực thi tạo lợi nhuận ròng dương.
        direction = "UP" if net_return > 0.0 else "DOWN"
        return direction, prev_close, next_close, pct_chg, entry_open

    # ── Prediction parser ──────────────────────────────────────────────────────

    def _parse_prediction(self, state: dict) -> Tuple[str, str, str, str, str]:
        """
        Trích xuất decision, confidence, R:R từ final_state.

        Dùng bộ trích xuất chung (`utils.decision_parser`) thay cho lát cắt
        `find("{")`/`rfind("}")` cũ: khi model chèn suy luận có dấu ngoặc nhọn
        trước khối JSON thì lát cắt hỏng, dự đoán rơi về UNKNOWN và bị tính là
        sai trong thống kê accuracy dù model đã trả lời đúng.
        """
        from utils.decision_parser import parse_decision

        raw = state.get("final_trade_decision", "")
        data = parse_decision(raw, lang=self.config.get("language", "vi"))
        if data.get("decision") not in ("LONG", "SHORT"):
            reason = data.get("fallback_reason", "NO_BINARY_DECISION")
            raise ValueError(f"Decision Agent không trả LONG/SHORT ({reason})")
        return (
            data["decision"],
            data.get("confidence", "N/A"),
            data.get("risk_reward_ratio", "N/A"),
            data.get("decision_source", "invalid_output"),
            data.get("fallback_reason", ""),
        )

    # ── Single run ─────────────────────────────────────────────────────────────

    def _run_single(
        self, graph, ohlcv_dict: dict, symbol: str, timeframe: str,
        window_end_date: str = None,
        point_in_time_df: Optional[pd.DataFrame] = None,
    ):
        """Chạy một lần phân tích với sentiment lịch sử."""
        import time
        from utils import static_util
    
        t0 = time.time()
    
        p_img = t_img = ""
        try:
            p_img = static_util.generate_kline_image(ohlcv_dict).get("pattern_image", "")
            t_img = static_util.generate_trend_image(ohlcv_dict).get("trend_image", "")
        except Exception as e:
            print(f"    [!] Lỗi tạo ảnh: {e}")
    
        initial_state = {
            "kline_data":    ohlcv_dict,
            "analysis_results": None,
            "messages":      [],
            "time_frame":    timeframe,
            "stock_name":    symbol,
            "pattern_image": p_img,
            "trend_image":   t_img,
            "is_backtest":   True,
    
            # ── MỚI: truyền sentiment store và ngày cutoff ──────────────────
            "sentiment_store":  (
                self._sentiment_store
                if self._use_historical_sentiment
                else None
            ),
            "window_end_date":  window_end_date,   # "YYYY-MM-DD"
            "point_in_time_df": point_in_time_df,
            "as_of_date": (
                point_in_time_df["Datetime"].iloc[-1]
                if point_in_time_df is not None and not point_in_time_df.empty
                else window_end_date
            ),
            
            # ── MỚI: truyền normalisation và weights ───────────────────────────
            "alpha_norm_method": self.config.get("alpha_norm_method", "zscore_tanh"),
            "alpha_weights": self.config.get("alpha_weights", None),

            # ── Ngôn ngữ đầu ra cho toàn bộ agent trong pipeline backtest ──────
            "language": self.config.get("language", "vi"),
        }
    
        final_state = graph.invoke(initial_state)
        return final_state, time.time() - t0

    def _run_ablation_variants(
        self,
        ohlcv_dict: dict,
        symbol: str,
        timeframe: str,
        window_end_date: str = None,
        point_in_time_df: Optional[pd.DataFrame] = None,
        variants: Tuple[str, ...] = tuple(ABLATION_CONFIGS),
    ) -> Dict[str, Tuple[dict, float]]:
        """Chạy một snapshot upstream qua các biến thể ablation được yêu cầu."""
        from utils import static_util

        decision_graphs = dict(self._graph_decision_variants)
        if "full" not in decision_graphs and self._graph_decision_full is not None:
            decision_graphs["full"] = self._graph_decision_full
        if "baseline" not in decision_graphs and self._graph_decision_no_alpha is not None:
            decision_graphs["baseline"] = self._graph_decision_no_alpha

        unknown = set(variants).difference(ABLATION_CONFIGS)
        if unknown:
            raise ValueError(f"Biến thể ablation không hợp lệ: {sorted(unknown)}")
        missing_graphs = set(variants).difference(decision_graphs)
        if missing_graphs:
            raise RuntimeError(f"Chưa khởi tạo graph cho: {sorted(missing_graphs)}")

        t0 = time.time()
        p_img = t_img = ""
        try:
            p_img = static_util.generate_kline_image(ohlcv_dict).get("pattern_image", "")
            t_img = static_util.generate_trend_image(ohlcv_dict).get("trend_image", "")
        except Exception as e:
            print(f"    [!] Lỗi tạo ảnh: {e}")

        initial_state = {
            "kline_data": ohlcv_dict,
            "analysis_results": None,
            "messages": [],
            "time_frame": timeframe,
            "stock_name": symbol,
            "pattern_image": p_img,
            "trend_image": t_img,
            "is_backtest": True,
            "sentiment_store": (
                self._sentiment_store if self._use_historical_sentiment else None
            ),
            "window_end_date": window_end_date,
            "point_in_time_df": point_in_time_df,
            "as_of_date": (
                point_in_time_df["Datetime"].iloc[-1]
                if point_in_time_df is not None and not point_in_time_df.empty
                else window_end_date
            ),
            "language": self.config.get("language", "vi"),
        }

        upstream_state = self._graph_upstream.invoke(initial_state)
        upstream_sec = time.time() - t0
        results: Dict[str, Tuple[dict, float]] = {}

        for index, variant in enumerate(variants):
            variant_input = deepcopy(upstream_state)
            variant_config = dict(ABLATION_CONFIGS[variant])
            variant_input["ablation_config"] = variant_config
            if variant_config["enable_alpha_factors"]:
                variant_input["alpha_norm_method"] = self.config.get(
                    "alpha_norm_method", "zscore_tanh"
                )
                variant_input["alpha_weights"] = self.config.get("alpha_weights")

            variant_started = time.time()
            try:
                state = decision_graphs[variant].invoke(variant_input)
            except Exception as exc:
                error = str(exc)[:500]
                raise RuntimeError(
                    f"Decision variant {variant} thất bại; không lưu fallback: {error}"
                ) from exc
            results[variant] = (
                state,
                upstream_sec + (time.time() - variant_started),
            )
            if (
                index < len(variants) - 1
                and not self._stop_event.is_set()
            ):
                time.sleep(self.DELAY_BETWEEN_VARIANTS)

        return results

    def _run_paired_point(
        self,
        ohlcv_dict: dict,
        symbol: str,
        timeframe: str,
        window_end_date: str = None,
        point_in_time_df: Optional[pd.DataFrame] = None,
    ):
        """Chạy cặp Full/Baseline qua cùng một snapshot upstream."""
        results = self._run_ablation_variants(
            ohlcv_dict,
            symbol,
            timeframe,
            window_end_date=window_end_date,
            point_in_time_df=point_in_time_df,
            variants=("full", "baseline"),
        )
        full_state, full_sec = results["full"]
        no_alpha_state, no_alpha_sec = results["baseline"]

        return full_state, full_sec, no_alpha_state, no_alpha_sec

    # ── Metrics helpers ────────────────────────────────────────────────────────

    def _compute_partial(self, tps: List[TestPoint]) -> PartialSummary:
        vf = [tp for tp in tps if tp.pred_full     not in ("UNKNOWN", "")]
        vn = [tp for tp in tps if tp.pred_no_alpha not in ("UNKNOWN", "")]
        cf = sum(1 for tp in vf if tp.correct_full)
        cn = sum(1 for tp in vn if tp.correct_no_alpha)
        af = round(cf / len(vf) * 100, 1) if vf else 0.0
        an = round(cn / len(vn) * 100, 1) if vn else 0.0

        account = compute_account_metrics(
            tps,
            allow_shorting=self.config.get("allow_shorting", False),
            fee=self.config.get("tx_cost", 0.0025),
            slippage=self.config.get("slippage", 0.001),
            initial_capital_vnd=self.config.get("initial_capital_vnd", 50_000_000.0),
            price_multiplier=self.config.get("price_multiplier", 1_000.0),
        )
        full_account = account["full"]
        no_alpha_account = account["no_alpha"]

        return PartialSummary(
            n_completed=len(tps), n_valid_full=len(vf), n_valid_no=len(vn),
            acc_full=af, acc_no_alpha=an,
            alpha_lift=round(af - an, 1),
            n_correct_full=cf, n_correct_no=cn,
            pnl_full=round(full_account.total_return_pct, 2),
            pnl_no_alpha=round(no_alpha_account.total_return_pct, 2),
            pnl_full_vnd=round(full_account.total_pnl_vnd, 0),
            pnl_no_alpha_vnd=round(no_alpha_account.total_pnl_vnd, 0),
            equity_full_vnd=round(full_account.final_equity_vnd, 0),
            equity_no_alpha_vnd=round(no_alpha_account.final_equity_vnd, 0),
            initial_capital_vnd=full_account.initial_capital_vnd,
            sharpe_full=round(full_account.sharpe_ratio, 2),
            sharpe_no_alpha=round(no_alpha_account.sharpe_ratio, 2),
            mdd_full=round(full_account.max_drawdown_pct, 2),
            mdd_no_alpha=round(no_alpha_account.max_drawdown_pct, 2),
            equity_curve_full=full_account.equity_curve,
            equity_curve_no_alpha=no_alpha_account.equity_curve,
        )

    def _build_summary(
        self, symbol, timeframe, n_tests, window_size, step,
        tps: List[TestPoint], data_start: str, data_end: str
    ) -> BacktestSummary:
        def metrics(valid_tps, use_full: bool):
            if not valid_tps:
                return 0.0, 0.0, 0.0, 0, 0
            preds   = [tp.pred_full     if use_full else tp.pred_no_alpha  for tp in valid_tps]
            correct = [tp.correct_full  if use_full else tp.correct_no_alpha for tp in valid_tps]
            actuals = [tp.actual_direction for tp in valid_tps]
            acc     = sum(correct) / len(correct) * 100

            longs  = [(p, a) for p, a in zip(preds, actuals) if p == "LONG"]
            shorts = [(p, a) for p, a in zip(preds, actuals) if p == "SHORT"]
            lw     = sum(1 for _, a in longs  if a == "UP")   / len(longs)  * 100 if longs  else 0.0
            sw     = sum(1 for _, a in shorts if a == "DOWN") / len(shorts) * 100 if shorts else 0.0
            return round(acc, 1), round(lw, 1), round(sw, 1), len(longs), len(shorts)

        vf  = [tp for tp in tps if tp.pred_full     not in ("UNKNOWN", "")]
        vn  = [tp for tp in tps if tp.pred_no_alpha not in ("UNKNOWN", "")]
        af, lf, sf, nlf, nsf = metrics(vf, True)
        an, ln, sn, nln, nsn = metrics(vn, False)
        significance = calculate_metrics_with_significance(
            [tp.actual_direction for tp in tps],
            [tp.pred_full for tp in tps],
            [tp.pred_no_alpha for tp in tps],
        )
        account = compute_account_metrics(
            tps,
            allow_shorting=self.config.get("allow_shorting", False),
            fee=self.config.get("tx_cost", 0.0025),
            slippage=self.config.get("slippage", 0.001),
            initial_capital_vnd=self.config.get("initial_capital_vnd", 50_000_000.0),
            price_multiplier=self.config.get("price_multiplier", 1_000.0),
        )
        full_account = account["full"]
        no_alpha_account = account["no_alpha"]

        return BacktestSummary(
            symbol=symbol, timeframe=timeframe, n_tests=len(tps),
            window_size=window_size, step=step,
            started_at=self._started_at,
            ended_at=datetime.now().isoformat(),
            data_start=data_start, data_end=data_end,
            acc_full=af, long_win_full=lf, short_win_full=sf,
            n_long_full=nlf, n_short_full=nsf,
            acc_no_alpha=an, long_win_no_alpha=ln, short_win_no_alpha=sn,
            n_long_no_alpha=nln, n_short_no_alpha=nsn,
            alpha_lift=round(af - an, 1),
            alpha_helps=(af > an),
            mcnemar_p_value=float(significance["mcnemar_p_value"]),
            is_significant_05=bool(significance["is_significant_05"]),
            alpha_lift_ci_95=[
                round(float(value), 4)
                for value in significance["alpha_lift_ci_95"]
            ],
            newey_west_statistic=float(significance["newey_west_statistic"]),
            newey_west_p_value=float(significance["newey_west_p_value"]),
            pnl_full=round(full_account.total_return_pct, 2),
            sharpe_full=round(full_account.sharpe_ratio, 2),
            sortino_full=round(full_account.sortino_ratio, 2),
            mdd_full=round(full_account.max_drawdown_pct, 2),
            hit_rate_full=round(full_account.hit_rate_pct, 2),
            avg_trade_full=round(full_account.avg_trade_pct, 2),
            pnl_no_alpha=round(no_alpha_account.total_return_pct, 2),
            sharpe_no_alpha=round(no_alpha_account.sharpe_ratio, 2),
            sortino_no_alpha=round(no_alpha_account.sortino_ratio, 2),
            mdd_no_alpha=round(no_alpha_account.max_drawdown_pct, 2),
            hit_rate_no_alpha=round(no_alpha_account.hit_rate_pct, 2),
            avg_trade_no_alpha=round(no_alpha_account.avg_trade_pct, 2),
            equity_curve_full=full_account.equity_curve,
            equity_curve_no_alpha=no_alpha_account.equity_curve,
            initial_capital_vnd=full_account.initial_capital_vnd,
            equity_full_vnd=round(full_account.final_equity_vnd, 0),
            equity_no_alpha_vnd=round(no_alpha_account.final_equity_vnd, 0),
            pnl_full_vnd=round(full_account.total_pnl_vnd, 0),
            pnl_no_alpha_vnd=round(no_alpha_account.total_pnl_vnd, 0),
            cash_full_vnd=round(full_account.final_cash_vnd, 0),
            cash_no_alpha_vnd=round(no_alpha_account.final_cash_vnd, 0),
            shares_full=round(full_account.final_shares, 8),
            shares_no_alpha=round(no_alpha_account.final_shares, 8),
            equity_curve_full_vnd=full_account.equity_curve_vnd,
            equity_curve_no_alpha_vnd=no_alpha_account.equity_curve_vnd,
            test_points=[asdict(tp) for tp in tps],
        )

    # ── Save helper ────────────────────────────────────────────────────────────

    def _save(self, path: str, payload: dict):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[BacktestEngine] Lỗi lưu {path}: {e}")

    # ── Main entry ─────────────────────────────────────────────────────────────

    def run(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str = "1 day",
        n_tests: int = 15,
        window_size: int = 45,
        step: int = 3,
        callback: Optional[Callable[[dict], None]] = None,
        result_path: str = "backtest_result.json",
    ) -> BacktestSummary:
        """
        Walk-forward backtest.

        Args:
            df           : DataFrame OHLCV với cột Datetime, Open, High, Low, Close, Volume
            symbol       : Mã cổ phiếu
            timeframe    : Chuỗi khung thời gian hiển thị
            n_tests      : Số test point tối đa
            window_size  : Số nến trong mỗi cửa sổ phân tích
            step         : Bước nhảy giữa các test point
            callback     : Hàm nhận dict cập nhật tiến trình sau mỗi test
            result_path  : Đường dẫn lưu kết quả JSON tạm
        Returns:
            BacktestSummary
        """
        self._stop_event.clear()
        self._started_at = datetime.now().isoformat()

        # ── Xác định lookahead theo quy định T+2.5 ────────────────────────
        from utils.static_util import get_forecast_horizon
        horizon   = get_forecast_horizon(timeframe)
        lookahead = horizon["lookahead_candles"]   # 1 (intraday) hoặc 3 (daily)
        h_val     = horizon["horizon_val"]
        if step < lookahead:
            raise ValueError(
                f"step={step} nhỏ hơn horizon={lookahead}; các chu kỳ BUY→SELL "
                "không cho phép các kỳ định giá chồng lấn"
            )

        if self._graph_upstream is None:
            self._init_graphs()

        # Mọi mốc quyết định phải có đủ 600 nến tiền kiểm tra
        # cho cả tuyển chọn và thực thi Alpha. Thiếu dữ liệu thì
        # fail-fast thay vì âm thầm giảm N hoặc fallback sang 5 alpha cũ.
        total = len(df)
        all_ends = build_walk_forward_end_indices(
            total=total,
            n_tests=n_tests,
            window_size=window_size,
            step=step,
            lookahead=lookahead,
        )

        data_start = df["Datetime"].iloc[0].strftime("%Y-%m-%d")
        data_end   = df["Datetime"].iloc[-1].strftime("%Y-%m-%d")
        actual_n   = len(all_ends)

        print(f"\n{'='*62}")
        print(f"  [BacktestEngine] {symbol} | {actual_n} tests | window={window_size} | step={step}")
        print(f"  Horizon: {h_val} (lookahead={lookahead} nến)")
        print(f"  Dữ liệu: {data_start} → {data_end}")
        print(f"{'='*62}\n")

        if self._use_historical_sentiment:  
            self._init_sentiment_store(symbol, force_recrawl=False)
            
        test_points: List[TestPoint] = []

        for i, end_idx in enumerate(all_ends):
            if self._stop_event.is_set():
                print("[BacktestEngine] ⛔ Đã dừng theo yêu cầu.")
                break

            print(f"\n── Test {i+1}/{actual_n} (end_idx={end_idx}) {'─'*30}")

            ohlcv, ws, we         = self._prepare_window(df, end_idx, window_size)
            point_in_time_df      = df.iloc[:end_idx].copy()
            actual_dir, pc, nc, pct, entry_open = self._get_actual_direction(
                df, end_idx, lookahead
            )

            print(f"  Cửa sổ : {ws} → {we}")
            execution_pct = (nc / entry_open - 1.0) * 100.0
            print(
                f"  Nhãn net O→C: {actual_dir}  {entry_open:.2f} → {nc:.2f}  "
                f"({pct:+.2f}% sau phí)"
            )
            print(
                f"  Thực thi O→C: {entry_open:.2f} → {nc:.2f}  "
                f"({execution_pct:+.2f}% trước phí; decision close={pc:.2f})"
            )

            # ── Paired shared-reports protocol ─────────────────────────
            pred_f = pred_n = "SHORT"
            conf_f = conf_n = "Thấp"
            rr_f = rr_n = "1.5"
            source_f = source_n = "invalid_output"
            fallback_reason_f = fallback_reason_n = ""
            tf = tn = 0.0
            err_f = err_n = ""
            ok = ok_n = False
            try:
                print("  ▶ Shared upstream + paired decisions đang chạy...")
                state_f, tf, state_n, tn = self._run_paired_point(
                    ohlcv,
                    symbol,
                    timeframe,
                    window_end_date=we,
                    point_in_time_df=point_in_time_df,
                )
                pred_f, conf_f, rr_f, source_f, fallback_reason_f = (
                    self._parse_prediction(state_f)
                )
                pred_n, conf_n, rr_n, source_n, fallback_reason_n = (
                    self._parse_prediction(state_n)
                )
                if pred_f not in ("LONG", "SHORT") or pred_n not in ("LONG", "SHORT"):
                    raise AssertionError("Decision parser vi phạm hợp đồng LONG/SHORT")
                err_f = str(state_f.get("decision_error", ""))[:200]
                err_n = str(state_n.get("decision_error", ""))[:200]
                ok = (pred_f == "LONG" and actual_dir == "UP") or \
                     (pred_f == "SHORT" and actual_dir == "DOWN")
                ok_n = (pred_n == "LONG" and actual_dir == "UP") or \
                       (pred_n == "SHORT" and actual_dir == "DOWN")
                print(f"  ✔ Full: {pred_f}  →  {'✅ Đúng' if ok else '❌ Sai'}  ({tf:.0f}s)")
                print(f"  ✔ No-Alpha: {pred_n}  →  {'✅ Đúng' if ok_n else '❌ Sai'}  ({tn:.0f}s)")
            except Exception as e:
                err_f = err_n = str(e)[:200]
                print(f"  ✘ Paired run lỗi: {err_f}")
                raise RuntimeError(str(e)) from e

            tp = TestPoint(
                test_id=i + 1,
                window_start=ws, window_end=we,
                actual_prev_close=pc, actual_next_close=nc,
                actual_direction=actual_dir, actual_pct_change=pct,
                pred_full=pred_f, correct_full=ok,
                confidence_full=conf_f, rr_full=rr_f,
                pred_no_alpha=pred_n, correct_no_alpha=ok_n,
                confidence_no_alpha=conf_n, rr_no_alpha=rr_n,
                time_full_sec=round(tf, 1), time_no_alpha_sec=round(tn, 1),
                entry_open=entry_open, exit_close=nc,
                entry_time=pd.Timestamp(df["Datetime"].iloc[end_idx]).isoformat(),
                exit_time=pd.Timestamp(
                    df["Datetime"].iloc[end_idx + lookahead - 1]
                ).isoformat(),
                error_full=err_f, error_no_alpha=err_n,
                decision_source_full=source_f,
                decision_source_no_alpha=source_n,
                decision_fallback_reason_full=fallback_reason_f,
                decision_fallback_reason_no_alpha=fallback_reason_n,
            )
            test_points.append(tp)

            # Tính P&L lũy kế tại điểm này và lưu vào TestPoint
            partial = self._compute_partial(test_points)

            # Callback tiến trình
            if callback:
                callback({
                    "completed": i + 1,
                    "total": actual_n,
                    "latest": asdict(tp),
                    "partial": asdict(partial),
                })

            # Lưu tạm
            self._save(result_path, {
                "symbol": symbol, "timeframe": timeframe,
                "window_size": window_size, "step": step,
                "updated_at": datetime.now().isoformat(),
                "partial": asdict(partial),
                "test_points": [asdict(t) for t in test_points],
            })

            # Delay trước test tiếp theo
            if i < len(all_ends) - 1 and not self._stop_event.is_set():
                print(f"  ⏳ Nghỉ {self.DELAY_BETWEEN_TESTS}s...")
                time.sleep(self.DELAY_BETWEEN_TESTS)

        summary = self._build_summary(
            symbol, timeframe, n_tests, window_size, step,
            test_points, data_start, data_end
        )

        # Lưu kết quả cuối
        self._save(result_path, asdict(summary))
        
        # Vẽ biểu đồ
        try:
            self._draw_backtest_result(summary, result_path)
        except Exception as e:
            print(f"  ✘ Lỗi vẽ biểu đồ: {e}")
            
        print(f"\n{'='*62}")
        print(f"  [BacktestEngine] ✅ HOÀN THÀNH")
        print(f"  Độ chính xác Full : {summary.acc_full}%")
        print(f"  Độ chính xác No-α : {summary.acc_no_alpha}%")
        print(f"  Alpha Lift        : {summary.alpha_lift:+.1f}%")
        print(
            f"  Tài khoản Full    : {summary.equity_full_vnd:,.0f} VND "
            f"({summary.pnl_full:+.2f}%)"
        )
        print(
            f"  Tài khoản No-Alpha: {summary.equity_no_alpha_vnd:,.0f} VND "
            f"({summary.pnl_no_alpha:+.2f}%)"
        )
        print(f"  McNemar p-value   : {summary.mcnemar_p_value:.6f}")
        print(
            "  Alpha Lift CI 95% : "
            f"[{summary.alpha_lift_ci_95[0]:+.2f}, "
            f"{summary.alpha_lift_ci_95[1]:+.2f}]"
        )
        print(f"{'='*62}\n")
        return summary

    def _draw_backtest_result(self, summary: BacktestSummary, result_path: str):
        symbol = summary.symbol
        n_tests = summary.n_tests
        points = summary.test_points

        if not points:
            return

        test_ids = [p['test_id'] for p in points]
        equity_full = summary.equity_curve_full_vnd
        equity_no_alpha = summary.equity_curve_no_alpha_vnd

        correct_full = [1 if p['correct_full'] else 0 for p in points]
        correct_no_alpha = [1 if p['correct_no_alpha'] else 0 for p in points]

        cum_correct_full = np.cumsum(correct_full)
        cum_correct_no_alpha = np.cumsum(correct_no_alpha)

        bg_color = '#f4f6fb'
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.5))
        fig.patch.set_facecolor(bg_color)

        for ax in (ax1, ax2):
            ax.set_facecolor('white')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.grid(True, color='#e5e7eb', linestyle='-', linewidth=1)

        c_full = '#2962FF'
        c_no_alpha = '#00B050'

        # Left: compounded account equity
        ax1.set_title(f"Fixed-Horizon BUY→SELL Account Equity — {symbol}", fontsize=13, fontweight='bold', pad=15)
        ax1.set_xlabel("Test #", fontsize=11, color='#4b5563')
        ax1.set_ylabel("Account Equity (VND)", fontsize=11, color='#4b5563')

        label_full = f"Full ($\\alpha$) [{summary.equity_full_vnd:,.0f} VND; {summary.pnl_full:+.2f}%]"
        label_no = f"No-$\\alpha$ [{summary.equity_no_alpha_vnd:,.0f} VND; {summary.pnl_no_alpha:+.2f}%]"
        equity_test_ids = [0] + test_ids
        initial_capital = summary.initial_capital_vnd

        ax1.plot(equity_test_ids, equity_full, color=c_full, label=label_full, marker='o', markersize=5, linewidth=2.5)
        ax1.plot(equity_test_ids, equity_no_alpha, color=c_no_alpha, label=label_no, marker='s', markersize=5, linestyle='--', linewidth=2.5)

        ax1.axhline(initial_capital, color='gray', linestyle='dotted', linewidth=1, alpha=0.7)

        equity_full_arr = np.array(equity_full)
        ax1.fill_between(equity_test_ids, equity_full_arr, initial_capital, where=(equity_full_arr >= initial_capital), color=c_full, alpha=0.1)
        ax1.fill_between(equity_test_ids, equity_full_arr, initial_capital, where=(equity_full_arr < initial_capital), color='#ef4444', alpha=0.1)

        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x / 1_000_000:.1f}M'))
        ax1.tick_params(axis='both', colors='#374151', labelsize=14)
        ax1.set_xticks(equity_test_ids)
        ax1.legend(loc='upper left', framealpha=1, edgecolor='#d1d5db')

        # Right: Accuracy
        ax2.set_title("Cumulative Correct Predictions", fontsize=13, fontweight='bold', pad=15)
        ax2.set_xlabel("Test #", fontsize=11, color='#4b5563')
        ax2.set_ylabel("Cumulative Correct", fontsize=11, color='#4b5563')

        label_full_acc = f"Full ($\\alpha$) [{cum_correct_full[-1]}/{n_tests}]"
        label_no_acc = f"No-$\\alpha$ [{cum_correct_no_alpha[-1]}/{n_tests}]"

        ax2.step(test_ids, cum_correct_full, where='post', color=c_full, label=label_full_acc, linewidth=2.5)
        ax2.step(test_ids, cum_correct_no_alpha, where='post', color=c_no_alpha, label=label_no_acc, linestyle='--', linewidth=2.5)

        ax2.fill_between(test_ids, cum_correct_full, step='post', color=c_full, alpha=0.08)
        ax2.fill_between(test_ids, cum_correct_no_alpha, step='post', color=c_no_alpha, alpha=0.15)

        ax2.set_yticks(range(0, max(cum_correct_full) + 2))
        ax2.tick_params(axis='both', colors='#374151', labelsize=14)
        ax2.set_xticks(test_ids)
        ax2.legend(loc='upper left', framealpha=1, edgecolor='#d1d5db')

        fig.suptitle(f"QuantAgent Backtest — {symbol} | {n_tests} tests", fontsize=14, fontweight='bold', y=1.02, color='#1f2937')
        plt.tight_layout()

        # Đổi .json thành .png
        img_path = result_path.replace('.json', '.png')
        if img_path == result_path:
            img_path = result_path + ".png"
        
        plt.savefig(img_path, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor())
        plt.close(fig)
        print(f"  [BacktestEngine] 🖼 Đã lưu biểu đồ tại: {img_path}")

    def stop(self):
        """Dừng backtest ngay sau test point hiện tại."""
        self._stop_event.set()
        print("[BacktestEngine] Đang dừng...")
