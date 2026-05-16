import json
import os
import time
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import static_util
from default_config import DEFAULT_CONFIG
from sentiment_cache import BacktestSentimentStore


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
        from sentiment_cache import BacktestSentimentStore
 
        print(f"\n[BacktestEngine] Đang preload sentiment lịch sử cho {symbol}...")
        self._sentiment_store = BacktestSentimentStore(cache_dir=".")
        self._sentiment_store.preload_symbol(symbol, force_recrawl=force_recrawl)
        print(f"[BacktestEngine] ✓ Sentiment store sẵn sàng cho {symbol}")

    # ── Graph initialization ───────────────────────────────────────────────────

    def _init_graphs(self):
        import os
        from langchain_groq import ChatGroq
        from graph_setup import SetGraph
        from graph_util import TechnicalTools

        api_key = self.config.get("groq_api_key") or os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise ValueError("Groq API key chưa được cấu hình.")

        def make_llm(model, temp=0.05):
            return ChatGroq(model=model, temperature=temp, api_key=api_key, max_retries=3)

        agent_llm = make_llm(self.config.get("agent_llm_model", "llama-3.1-8b-instant"))
        graph_llm = make_llm(self.config.get("graph_llm_model",
                                              "meta-llama/llama-4-scout-17b-16e-instruct"))
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
        import static_util
    
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

        # P&L mô phỏng lũy kế:
        # - Đúng: cộng |pct_change|, Sai: trừ |pct_change|, UNKNOWN: bỏ qua
        pnl_f = 0.0
        for tp in tps:
            if tp.pred_full not in ("UNKNOWN", ""):
                pct = abs(tp.actual_pct_change)
                pnl_f += pct if tp.correct_full else -pct

        pnl_n = 0.0
        for tp in tps:
            if tp.pred_no_alpha not in ("UNKNOWN", ""):
                pct = abs(tp.actual_pct_change)
                pnl_n += pct if tp.correct_no_alpha else -pct

        return PartialSummary(
            n_completed=len(tps), n_valid_full=len(vf), n_valid_no=len(vn),
            acc_full=af, acc_no_alpha=an,
            alpha_lift=round(af - an, 1),
            n_correct_full=cf, n_correct_no=cn,
            pnl_full=round(pnl_f, 2),
            pnl_no_alpha=round(pnl_n, 2),
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
        from static_util import get_forecast_horizon
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
        print(f"\n{'='*62}")
        print(f"  [BacktestEngine] ✅ HOÀN THÀNH")
        print(f"  Độ chính xác Full : {summary.acc_full}%")
        print(f"  Độ chính xác No-α : {summary.acc_no_alpha}%")
        print(f"  Alpha Lift        : {summary.alpha_lift:+.1f}%")
        print(f"{'='*62}\n")
        return summary

    def stop(self):
        """Dừng backtest ngay sau test point hiện tại."""
        self._stop_event.set()
        print("[BacktestEngine] Đang dừng...")