import json
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import argparse
from datetime import datetime
import pandas as pd
from typing import List, Dict, Any

from core.backtest_engine import BacktestEngine
from core.alpha_compare import load_data
from utils.statistical_tests import calculate_metrics_with_significance

def save_results(results: List[Dict], out_dir: str, prefix: str, symbol: str):
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = f"{out_dir}/{prefix}_{symbol}_{timestamp}.csv"
    res_df = pd.DataFrame(results)
    res_df.to_csv(out_file, index=False)
    print(f"\n✅ Thử nghiệm hoàn tất. Kết quả lưu tại: {out_file}")

def run_experiment(symbol: str, timeframe: str, config: dict, kwargs_backtest: dict) -> dict:
    engine = BacktestEngine(config=config)
    
    # Extract df from kwargs if present, else load it
    df = kwargs_backtest.pop('df', None)
    if df is None:
        df = load_data(symbol, timeframe, lookback_days=800)
    
    try:
        summary = engine.run(
            df=df,
            symbol=symbol,
            timeframe=timeframe,
            **kwargs_backtest
        )
        
        actuals = [tp["actual_direction"] for tp in summary.test_points]
        preds_f = [tp["pred_full"] for tp in summary.test_points]
        preds_n = [tp["pred_no_alpha"] for tp in summary.test_points]
        
        sig_metrics = calculate_metrics_with_significance(actuals, preds_f, preds_n)
        
        return {
            "acc_full": summary.acc_full,
            "acc_no_alpha": summary.acc_no_alpha,
            "pnl_full": getattr(summary, "pnl_full", 0.0),
            "sharpe_full": getattr(summary, "sharpe_full", 0.0),
            "mdd_full": getattr(summary, "mdd_full", 0.0),
            "pnl_no_alpha": getattr(summary, "pnl_no_alpha", 0.0),
            "sharpe_no_alpha": getattr(summary, "sharpe_no_alpha", 0.0),
            "mcnemar_p_value": sig_metrics.get("mcnemar_p_value", 1.0),
            "is_significant": sig_metrics.get("is_significant_05", False),
            "delta_acc_ci": sig_metrics.get("delta_acc_ci", [0.0, 0.0])
        }
    except Exception as e:
        print(f"❌ Lỗi khi chạy backtest: {e}")
        return None

def main():
    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Run robustness experiments for QuantAgent.")
    parser.add_argument("--mode", type=str, required=True, 
                        choices=["hyperparams", "norm", "weights"],
                        help="Chế độ thí nghiệm cần chạy.")
    parser.add_argument("--symbol", type=str, default="FPT", help="Mã cổ phiếu (mặc định FPT).")
    parser.add_argument("--n_tests", type=int, default=21, help="Số test point mỗi vòng (giữ nhỏ để tránh lỗi Groq API).")
    args = parser.parse_args()

    symbol = args.symbol
    timeframe = "1d"
    out_dir = "outputs/robustness"
    n_tests = args.n_tests

    print("=" * 60)
    print(f"BẮT ĐẦU THÍ NGHIỆM: {args.mode.upper()} trên {symbol}")
    print("=" * 60)

    base_config = {
        "allow_shorting": False,
        "tx_cost": 0.0025,
        "slippage": 0.001,
        "alpha_norm_method": "zscore_tanh",
        "alpha_weights": {"ic": 0.35, "acc": 0.30, "long_acc": 0.20, "sharpe": 0.15}
    }

    base_kwargs = {
        "n_tests": n_tests,
        "window_size": 45,
        "step": 3,
        "result_path": f"{out_dir}/temp_result.json"
    }

    results = []

    if args.mode == "hyperparams":
        windows = [30, 45, 60]
        target_tests = max(1, n_tests // len(windows))
        for w in windows:
            print(f"\n--- Thử nghiệm W={w} ---")
            df = load_data(symbol, timeframe, lookback_days=800)
            max_possible = max(0, (len(df) - w) // base_kwargs["step"])
            current_n_tests = min(target_tests, max_possible)
            if current_n_tests < 1:
                print(f"Bỏ qua W={w} vì không đủ dữ liệu (có {len(df)} nến).")
                continue
            kw = base_kwargs.copy()
            kw["window_size"] = w
            kw["n_tests"] = current_n_tests
            kw["df"] = df
            res = run_experiment(symbol, timeframe, base_config, kw)
            if res:
                res["window_size"] = w
                results.append(res)
            
    elif args.mode == "norm":
        norms = ["zscore_tanh", "minmax", "rank"]
        target_tests = max(1, n_tests // len(norms))
        for norm in norms:
            print(f"\n--- Thử nghiệm Normalization={norm} ---")
            df = load_data(symbol, timeframe, lookback_days=800)
            max_possible = max(0, (len(df) - base_kwargs["window_size"]) // base_kwargs["step"])
            current_n_tests = min(target_tests, max_possible)
            if current_n_tests < 1:
                continue
            cfg = base_config.copy()
            cfg["alpha_norm_method"] = norm
            kw = base_kwargs.copy()
            kw["n_tests"] = current_n_tests
            kw["df"] = df
            res = run_experiment(symbol, timeframe, cfg, kw)
            if res:
                res["norm_method"] = norm
                results.append(res)

    elif args.mode == "weights":
        weights_scenarios = {
            "default": {"ic": 0.35, "acc": 0.30, "long_acc": 0.20, "sharpe": 0.15},
            "equal_weight": {"ic": 0.25, "acc": 0.25, "long_acc": 0.25, "sharpe": 0.25},
            "ic_heavy": {"ic": 0.60, "acc": 0.20, "long_acc": 0.10, "sharpe": 0.10}
        }
        target_tests = max(1, n_tests // len(weights_scenarios))
        for w_name, w_dict in weights_scenarios.items():
            print(f"\n--- Thử nghiệm Alpha Weights={w_name} ---")
            df = load_data(symbol, timeframe, lookback_days=800)
            max_possible = max(0, (len(df) - base_kwargs["window_size"]) // base_kwargs["step"])
            current_n_tests = min(target_tests, max_possible)
            if current_n_tests < 1:
                continue
            cfg = base_config.copy()
            cfg["alpha_weights"] = w_dict
            kw = base_kwargs.copy()
            kw["n_tests"] = current_n_tests
            kw["df"] = df
            res = run_experiment(symbol, timeframe, cfg, kw)
            if res:
                res["weight_scenario"] = w_name
                results.append(res)

    if results:
        save_results(results, out_dir, f"sweep_{args.mode}", symbol)
    else:
        print("Không thu được kết quả nào!")

if __name__ == "__main__":
    main()
