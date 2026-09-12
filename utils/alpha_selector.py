import os
import time
import pandas as pd
from typing import List, Tuple, Dict, Any, Callable, Optional
from core.alpha_compare import ALPHA_REGISTRY, load_data, run_backtest, rank_alphas

def select_top_alphas(
    symbol: str,
    interval: str = "1d",
    top_n: int = 5,
    norm_method: str = "zscore_tanh",
    weights: dict = None,
    as_of_date: Optional[str] = None,
    historical_df: Optional[pd.DataFrame] = None,
    is_backtest: bool = False,
) -> List[Dict[str, Any]]:
    """
    Tự động hóa quy trình 'Đấu trường Alpha':
    1. Lấy tối đa 600 nến dữ liệu lịch sử tại đúng thời điểm quyết định.
    2. Chạy backtest cho toàn bộ candidates trong ALPHA_REGISTRY.
    3. Xếp hạng và chọn top_n alpha mạnh nhất.

    Trong backtest, ``historical_df`` là bắt buộc để hàm không bao giờ rơi về
    loader realtime. ``as_of_date`` được dùng làm chốt thời gian bổ sung trước
    khi lấy 600 nến gần nhất.
    """
    print(f"[AlphaSelector] Starting alpha selection for {symbol} ({interval})...")
    
    # 1. Dùng snapshot point-in-time trong backtest; chỉ live trading mới tải
    # dữ liệu realtime. Luôn copy để không làm thay đổi DataFrame của engine.
    if historical_df is not None:
        df = historical_df.copy()
        if as_of_date is not None:
            cutoff = pd.Timestamp(as_of_date)
            if "Datetime" in df.columns:
                datetimes = pd.to_datetime(df["Datetime"], errors="coerce")
                if datetimes.dt.tz is not None and cutoff.tzinfo is None:
                    cutoff = cutoff.tz_localize(datetimes.dt.tz)
                elif datetimes.dt.tz is None and cutoff.tzinfo is not None:
                    cutoff = cutoff.tz_localize(None)
                df = df.loc[datetimes.notna() & (datetimes <= cutoff)]
            elif isinstance(df.index, pd.DatetimeIndex):
                cutoff_for_index = cutoff
                if df.index.tz is not None and cutoff.tzinfo is None:
                    cutoff_for_index = cutoff.tz_localize(df.index.tz)
                elif df.index.tz is None and cutoff.tzinfo is not None:
                    cutoff_for_index = cutoff.tz_localize(None)
                df = df.loc[df.index <= cutoff_for_index]
            else:
                raise ValueError(
                    "historical_df phải có cột Datetime hoặc DatetimeIndex khi truyền as_of_date"
                )
        df = df.tail(600).copy()
    elif is_backtest:
        raise ValueError("Backtest bắt buộc truyền historical_df để tránh dữ liệu realtime")
    else:
        df = load_data(symbol, interval, lookback_days=600)

    if df.empty:
        print(f"[AlphaSelector] ! No data found for {symbol}")
        return []

    # 2. Determine lookahead
    # (Reusing logic from alpha_compare.py main)
    lookahead = 3 if interval in ("1d", "1w", "1mo") else 1
    
    # 3. Run backtest on all candidates
    try:
        results = run_backtest(df, lookahead=lookahead, norm_method=norm_method)
        if results.empty:
            return []
            
        # 4. Rank alphas
        ranked = rank_alphas(results, weights=weights)
        
        # 5. Extract top_n
        top_list = []
        for i in range(min(top_n, len(ranked))):
            row = ranked.iloc[i]
            aid = row["alpha_id"]
            if aid in ALPHA_REGISTRY:
                fn, desc = ALPHA_REGISTRY[aid]
                top_list.append({
                    "alpha_id": aid,
                    "handler": fn,
                    "description": desc,
                    "composite_score": row["composite"],
                    "metrics": {
                        "ic": row["ic"],
                        "accuracy": row["accuracy"],
                        "long_acc": row["long_acc"],
                        "sharpe": row["sharpe"]
                    }
                })
        
        print(f"[AlphaSelector] [OK] Selected Top {len(top_list)} alphas for {symbol}: {[a['alpha_id'] for a in top_list]}")
        return top_list
        
    except Exception as e:
        print(f"[AlphaSelector] Error during alpha selection: {e}")
        return []
