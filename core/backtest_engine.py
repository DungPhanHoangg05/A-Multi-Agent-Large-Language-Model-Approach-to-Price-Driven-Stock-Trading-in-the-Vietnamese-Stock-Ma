import json
import os
import time
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from utils import static_util
from default_config import DEFAULT_CONFIG
from data_manager.sentiment_cache import BacktestSentimentStore


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class TestPoint:
    test_id: int
    window_start: str
    window_end: str
    actual_prev_close: float
    actual_next_close: float
    actual_direction: str           # "UP" | "DOWN"
    actual_pct_change: float        # % thay đổi thực tế

    # Full system (có Alpha Agent)
    pred_full: str                  # "LONG" | "SHORT" | "UNKNOWN"
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

    # P&L mô phỏng lũy kế tại thời điểm này
    pnl_full: float = 0.0           # % lợi nhuận lũy kế Full system
    pnl_no_alpha: float = 0.0       # % lợi nhuận lũy kế No-Alpha system

    # Lỗi
    error_full: str = ""
    error_no_alpha: str = ""


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
    sharpe_full: float = 0.0
    sharpe_no_alpha: float = 0.0
    mdd_full: float = 0.0
    mdd_no_alpha: float = 0.0

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

    test_points: List[dict] = field(default_factory=list)


# ── Engine ─────────────────────────────────────────────────────────────────────

class BacktestEngine:
    """
    Walk-forward backtest engine.
    Mỗi test point:
      1. Cắt window [end_idx - window_size : end_idx]
      2. Chạy Full System → prediction_full
      3. Chạy No-Alpha System → prediction_no_alpha
      4. Kiểm tra nến [end_idx] để xác định đúng/sai
    """

    # Rate-limit safety delays (giây)
    DELAY_BETWEEN_VARIANTS = 10.0   # Giữa Full và No-Alpha trong cùng test
    DELAY_BETWEEN_TESTS    = 8.0    # Giữa 2 test points

    def __init__(self, config: dict = None):
        self.config          = {**DEFAULT_CONFIG, **(config or {})}
        self._graph_full     = None
        self._graph_no_alpha = None
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

        def make_llm(model, temp=0.05):
            return ChatGroq(model=model, temperature=temp, api_key=api_key, max_retries=3)

        agent_llm = make_llm(self.config.get("agent_llm_model", "openai/gpt-oss-20b"))
        graph_llm = make_llm(self.config.get("graph_llm_model", "qwen/qwen3.6-27b"))
        toolkit = TechnicalTools()

        print("[BacktestEngine] Khởi tạo Full graph...")
        self._graph_full = SetGraph(agent_llm, graph_llm, toolkit).set_graph(include_alpha=True)

        print("[BacktestEngine] Khởi tạo No-Alpha graph...")
        self._graph_no_alpha = SetGraph(agent_llm, graph_llm, toolkit).set_graph(include_alpha=False)

        print("[BacktestEngine] ✓ Cả 2 graph đã sẵn sàng.")

    # ── Data helpers ───────────────────────────────────────────────────────────

    def _prepare_window(
        self, df: pd.DataFrame, end_idx: int, window_size: int
    ) -> Tuple[dict, str, str]:
        """Cắt cửa sổ OHLCV và trả về dict + date strings."""
        start_idx  = max(0, end_idx - window_size)
        window_df  = df.iloc[start_idx:end_idx].reset_index(drop=True)
        ohlcv_dict = {}
        for col in ["Datetime", "Open", "High", "Low", "Close"]:
            if col == "Datetime":
                ohlcv_dict[col] = window_df[col].dt.strftime("%Y-%m-%d %H:%M:%S").tolist()
            else:
                ohlcv_dict[col] = [float(v) for v in window_df[col]]
        ws = window_df["Datetime"].iloc[0].strftime("%Y-%m-%d")
        we = window_df["Datetime"].iloc[-1].strftime("%Y-%m-%d")
        return ohlcv_dict, ws, we

    def _get_actual_direction(
        self, df: pd.DataFrame, end_idx: int, lookahead: int = 1
    ) -> Tuple[str, float, float, float]:
        """
        Lấy hướng thực tế sau cửa sổ phân tích.

        Args:
            end_idx   : index cuối cửa sổ (nến cuối cùng agent nhìn thấy)
            lookahead : số nến phía trước để đánh giá.
                        - 1 = so sánh close[end_idx-1] vs close[end_idx]     (T+1)
                        - 3 = so sánh close[end_idx-1] vs close[end_idx+2]   (T+2.5)

        Quy ước: prev_close = close cuối cửa sổ (end_idx - 1)
                 next_close = close của nến end_idx + lookahead - 1
        """
        target_idx = end_idx + lookahead - 1
        if target_idx >= len(df):
            return "UNKNOWN", 0.0, 0.0, 0.0
        prev_close = float(df["Close"].iloc[end_idx - 1])
        next_close = float(df["Close"].iloc[target_idx])
        pct_chg    = round((next_close - prev_close) / prev_close * 100, 4) if prev_close else 0.0
        direction  = "UP" if next_close >= prev_close else "DOWN"
        return direction, prev_close, next_close, pct_chg

    # ── Prediction parser ──────────────────────────────────────────────────────

    def _parse_prediction(self, state: dict) -> Tuple[str, str, str]:
        """Trích xuất decision, confidence, R:R từ final_state."""
        raw = state.get("final_trade_decision", "")
        if not raw:
            return "UNKNOWN", "N/A", "N/A"
        try:
            s = raw.find("{"); e = raw.rfind("}") + 1
            if s != -1 and e > s:
                data       = json.loads(raw[s:e])
                decision   = data.get("decision", "UNKNOWN").upper().strip()
                confidence = data.get("confidence", "N/A")
                rr         = str(data.get("risk_reward_ratio", "N/A"))
                if decision in ("LONG", "SHORT"):
                    return decision, confidence, rr
        except Exception:
            pass
        if "LONG" in raw.upper():
            return "LONG", "N/A", "N/A"
        if "SHORT" in raw.upper():
            return "SHORT", "N/A", "N/A"
        return "UNKNOWN", "N/A", "N/A"

    # ── Single run ─────────────────────────────────────────────────────────────

    def _run_single(
        self, graph, ohlcv_dict: dict, symbol: str, timeframe: str,
        window_end_date: str = None   # ← tham số mới
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
            
            # ── MỚI: truyền normalisation và weights ───────────────────────────
            "alpha_norm_method": self.config.get("alpha_norm_method", "zscore_tanh"),
            "alpha_weights": self.config.get("alpha_weights", None),
        }
    
        final_state = graph.invoke(initial_state)
        return final_state, time.time() - t0

    # ── Metrics helpers ────────────────────────────────────────────────────────

    def _compute_partial(self, tps: List[TestPoint]) -> PartialSummary:
        vf = [tp for tp in tps if tp.pred_full     not in ("UNKNOWN", "")]
        vn = [tp for tp in tps if tp.pred_no_alpha not in ("UNKNOWN", "")]
        cf = sum(1 for tp in vf if tp.correct_full)
        cn = sum(1 for tp in vn if tp.correct_no_alpha)
        af = round(cf / len(vf) * 100, 1) if vf else 0.0
        an = round(cn / len(vn) * 100, 1) if vn else 0.0

        # Constants for realistic simulation
        allow_shorting = self.config.get("allow_shorting", False)
        tx_cost = self.config.get("tx_cost", 0.0025)  # 0.25% round trip (commission + tax)
        slippage = self.config.get("slippage", 0.001) # 0.1% slippage

        def compute_trade_pnl(pred: str, actual_dir: str, actual_pct: float, correct: bool) -> float:
            if pred in ("UNKNOWN", ""):
                return 0.0
            
            # Gross return
            raw_pct = abs(actual_pct) if correct else -abs(actual_pct)
            
            if pred == "SHORT" and not allow_shorting:
                return 0.0  # Cannot short
            
            # Apply costs
            net_pct = raw_pct - (tx_cost * 100) - (slippage * 100)
            return net_pct

        pnl_f = 0.0
        pnl_n = 0.0
        rets_f = []
        rets_n = []
        
        for tp in tps:
            r_f = compute_trade_pnl(tp.pred_full, tp.actual_direction, tp.actual_pct_change, tp.correct_full)
            if tp.pred_full not in ("UNKNOWN", ""):
                rets_f.append(r_f)
                pnl_f += r_f
            tp.pnl_full = round(pnl_f, 2)
                
            r_n = compute_trade_pnl(tp.pred_no_alpha, tp.actual_direction, tp.actual_pct_change, tp.correct_no_alpha)
            if tp.pred_no_alpha not in ("UNKNOWN", ""):
                rets_n.append(r_n)
                pnl_n += r_n
            tp.pnl_no_alpha = round(pnl_n, 2)
                
        def calc_sharpe_mdd(rets: List[float]):
            if not rets: return 0.0, 0.0
            arr = np.array(rets) / 100.0
            mean = np.mean(arr)
            std = np.std(arr)
            sharpe = (mean / std) * np.sqrt(252) if std > 1e-9 else 0.0
            
            cum = np.cumsum(arr)
            max_so_far = np.maximum.accumulate(cum)
            dd = max_so_far - cum
            mdd = np.max(dd) if len(dd) > 0 else 0.0
            return float(sharpe), float(mdd * 100)

        sf, mddf = calc_sharpe_mdd(rets_f)
        sn, mddn = calc_sharpe_mdd(rets_n)

        return PartialSummary(
            n_completed=len(tps), n_valid_full=len(vf), n_valid_no=len(vn),
            acc_full=af, acc_no_alpha=an,
            alpha_lift=round(af - an, 1),
            n_correct_full=cf, n_correct_no=cn,
            pnl_full=round(pnl_f, 2),
            pnl_no_alpha=round(pnl_n, 2),
            sharpe_full=round(sf, 2),
            sharpe_no_alpha=round(sn, 2),
            mdd_full=round(mddf, 2),
            mdd_no_alpha=round(mddn, 2),
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

        allow_shorting = self.config.get("allow_shorting", False)
        tx_cost = self.config.get("tx_cost", 0.0025)
        slippage = self.config.get("slippage", 0.001)

        def compute_advanced_metrics(valid_tps, use_full: bool):
            if not valid_tps:
                return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
                
            rets = []
            for tp in valid_tps:
                pred = tp.pred_full if use_full else tp.pred_no_alpha
                correct = tp.correct_full if use_full else tp.correct_no_alpha
                
                if pred == "SHORT" and not allow_shorting:
                    rets.append(0.0)
                else:
                    raw_pct = abs(tp.actual_pct_change) if correct else -abs(tp.actual_pct_change)
                    net_pct = raw_pct - (tx_cost * 100) - (slippage * 100)
                    rets.append(net_pct)
                    
            arr = np.array(rets) / 100.0
            mean = np.mean(arr)
            std = np.std(arr)
            sharpe = (mean / std) * np.sqrt(252) if std > 1e-9 else 0.0
            
            # Sortino
            downside = arr[arr < 0]
            std_down = np.std(downside) if len(downside) > 0 else 0.0
            sortino = (mean / std_down) * np.sqrt(252) if std_down > 1e-9 else 0.0
            
            cum = np.cumsum(arr)
            max_so_far = np.maximum.accumulate(cum)
            dd = max_so_far - cum
            mdd = np.max(dd) if len(dd) > 0 else 0.0
            
            pnl = sum(rets)
            hit_rate = sum(1 for r in rets if r > 0) / len(rets) * 100 if rets else 0.0
            avg_trade = np.mean(rets) if rets else 0.0
            
            return pnl, sharpe, sortino, mdd * 100, hit_rate, avg_trade

        vf  = [tp for tp in tps if tp.pred_full     not in ("UNKNOWN", "")]
        vn  = [tp for tp in tps if tp.pred_no_alpha not in ("UNKNOWN", "")]
        af, lf, sf, nlf, nsf = metrics(vf, True)
        an, ln, sn, nln, nsn = metrics(vn, False)
        
        pnl_f, sharpe_f, sortino_f, mdd_f, hr_f, avg_f = compute_advanced_metrics(vf, True)
        pnl_n, sharpe_n, sortino_n, mdd_n, hr_n, avg_n = compute_advanced_metrics(vn, False)

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
            pnl_full=round(pnl_f, 2), sharpe_full=round(sharpe_f, 2),
            sortino_full=round(sortino_f, 2), mdd_full=round(mdd_f, 2),
            hit_rate_full=round(hr_f, 2), avg_trade_full=round(avg_f, 2),
            pnl_no_alpha=round(pnl_n, 2), sharpe_no_alpha=round(sharpe_n, 2),
            sortino_no_alpha=round(sortino_n, 2), mdd_no_alpha=round(mdd_n, 2),
            hit_rate_no_alpha=round(hr_n, 2), avg_trade_no_alpha=round(avg_n, 2),
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
            df           : DataFrame OHLCV với cột Datetime, Open, High, Low, Close
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

        if self._graph_full is None:
            self._init_graphs()

        # ── Xác định lookahead theo quy định T+2.5 ────────────────────────
        from utils.static_util import get_forecast_horizon
        horizon   = get_forecast_horizon(timeframe)
        lookahead = horizon["lookahead_candles"]   # 1 (intraday) hoặc 3 (daily)
        h_val     = horizon["horizon_val"]

        # Xác định test point indices (chronological)
        total = len(df)
        # Cần ít nhất `lookahead` nến SAU end_idx để xác minh hướng thực tế
        max_end = total - lookahead
        min_end = window_size    # cần ít nhất window_size nến trước đó

        all_ends = list(range(max_end, min_end, -step))[:n_tests]
        all_ends = list(reversed(all_ends))

        if not all_ends:
            raise ValueError(
                f"Không đủ dữ liệu để backtest. "
                f"Cần ≥ {window_size + step + lookahead} nến, hiện có {total}."
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
            actual_dir, pc, nc, pct = self._get_actual_direction(df, end_idx, lookahead)

            print(f"  Cửa sổ : {ws} → {we}")
            print(f"  Thực tế : {actual_dir}  {pc:.2f} → {nc:.2f}  ({pct:+.2f}%)")

            # ── Full System ────────────────────────────────────────────
            pred_f = conf_f = rr_f = "UNKNOWN"
            tf = 0.0; err_f = ""
            try:
                print("  ▶ Full system đang chạy...")
                state_f, tf = self._run_single(self._graph_full, ohlcv, symbol, timeframe,
                                               window_end_date=we)
                pred_f, conf_f, rr_f = self._parse_prediction(state_f)
                ok = (pred_f == "LONG" and actual_dir == "UP") or \
                     (pred_f == "SHORT" and actual_dir == "DOWN")
                print(f"  ✔ Full: {pred_f}  →  {'✅ Đúng' if ok else '❌ Sai'}  ({tf:.0f}s)")
            except Exception as e:
                err_f = str(e)[:200]
                print(f"  ✘ Full lỗi: {err_f}")
                ok = False

            # Delay giữa 2 variant
            if not self._stop_event.is_set():
                time.sleep(self.DELAY_BETWEEN_VARIANTS)

            # ── No-Alpha System ────────────────────────────────────────
            pred_n = conf_n = rr_n = "UNKNOWN"
            tn = 0.0; err_n = ""; ok_n = False
            try:
                print("  ▶ No-Alpha system đang chạy...")
                state_n, tn = self._run_single(self._graph_no_alpha, ohlcv, symbol, timeframe,
                                               window_end_date=we)
                pred_n, conf_n, rr_n = self._parse_prediction(state_n)
                ok_n = (pred_n == "LONG" and actual_dir == "UP") or \
                       (pred_n == "SHORT" and actual_dir == "DOWN")
                print(f"  ✔ No-Alpha: {pred_n}  →  {'✅ Đúng' if ok_n else '❌ Sai'}  ({tn:.0f}s)")
            except Exception as e:
                err_n = str(e)[:200]
                print(f"  ✘ No-Alpha lỗi: {err_n}")

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
                error_full=err_f, error_no_alpha=err_n,
            )
            test_points.append(tp)

            # Tính P&L lũy kế tại điểm này và lưu vào TestPoint
            partial = self._compute_partial(test_points)
            tp.pnl_full     = partial.pnl_full
            tp.pnl_no_alpha = partial.pnl_no_alpha

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
        print(f"{'='*62}\n")
        return summary

    def _draw_backtest_result(self, summary: BacktestSummary, result_path: str):
        symbol = summary.symbol
        n_tests = summary.n_tests
        points = summary.test_points

        if not points:
            return

        test_ids = [p['test_id'] for p in points]
        pnl_full = [p.get('pnl_full', 0.0) for p in points]
        pnl_no_alpha = [p.get('pnl_no_alpha', 0.0) for p in points]

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

        # Left: P&L
        ax1.set_title(f"Cumulative P&L Simulation — {symbol}", fontsize=13, fontweight='bold', pad=15)
        ax1.set_xlabel("Test #", fontsize=11, color='#4b5563')
        ax1.set_ylabel("Cumulative P&L (%)", fontsize=11, color='#4b5563')

        label_full = f"Full ($\\alpha$) [{pnl_full[-1]:+.2f}%]"
        label_no = f"No-$\\alpha$ [{pnl_no_alpha[-1]:+.2f}%]"

        ax1.plot(test_ids, pnl_full, color=c_full, label=label_full, marker='o', markersize=5, linewidth=2.5)
        ax1.plot(test_ids, pnl_no_alpha, color=c_no_alpha, label=label_no, marker='s', markersize=5, linestyle='--', linewidth=2.5)

        ax1.axhline(0, color='gray', linestyle='dotted', linewidth=1, alpha=0.7)

        pnl_full_arr = np.array(pnl_full)
        ax1.fill_between(test_ids, pnl_full_arr, 0, where=(pnl_full_arr >= 0), color=c_full, alpha=0.1)
        ax1.fill_between(test_ids, pnl_full_arr, 0, where=(pnl_full_arr < 0), color='#ef4444', alpha=0.1)

        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:+.1f}%'))
        ax1.tick_params(axis='both', colors='#374151', labelsize=14)
        ax1.set_xticks(test_ids)
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