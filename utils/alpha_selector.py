import os
import time
import pandas as pd
from typing import List, Tuple, Dict, Any, Callable
from core.alpha_compare import ALPHA_REGISTRY, load_data, run_backtest, rank_alphas

def select_top_alphas(symbol: str, interval: str = "1d", top_n: int = 5, 
                      norm_method: str = "zscore_tanh", weights: dict = None) -> List[Dict[str, Any]]:
    """
    Tự động hóa quy trình 'Đấu trường Alpha':
    1. Tải 600 nến dữ liệu lịch sử.
    2. Chạy backtest cho toàn bộ candidates trong ALPHA_REGISTRY.
    3. Xếp hạng và chọn top_n alpha mạnh nhất.
    """
    print(f"[AlphaSelector] Starting alpha selection for {symbol} ({interval})...")
    
    # 1. Load data (600 candles as required by alpha_compare)
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
        
        print(f"[AlphaSelector] ✓ Selected Top {len(top_list)} alphas for {symbol}: {[a['alpha_id'] for a in top_list]}")
        return top_list
        
    except Exception as e:
        print(f"[AlphaSelector] Error during alpha selection: {e}")
        return []
