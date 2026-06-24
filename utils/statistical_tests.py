import numpy as np
import pandas as pd
from typing import Tuple, Dict, List
import math
from statsmodels.stats.contingency_tables import mcnemar

def calculate_mcnemar_test(y_true: np.ndarray, y_pred_full: np.ndarray, y_pred_no_alpha: np.ndarray) -> Dict[str, float]:
    """
    Perform McNemar's test to compare the accuracy of two models (Full vs No-Alpha).
    
    Args:
        y_true: Ground truth binary outcomes (e.g. 1 for up, 0 for down)
        y_pred_full: Predictions of the full model
        y_pred_no_alpha: Predictions of the baseline (no-alpha) model
        
    Returns:
        Dict containing statistic and p_value
    """
    # Create contingency table
    # Cell a: Both correct
    # Cell b: Full correct, No-Alpha wrong
    # Cell c: Full wrong, No-Alpha correct
    # Cell d: Both wrong
    
    full_correct = (y_pred_full == y_true)
    no_alpha_correct = (y_pred_no_alpha == y_true)
    
    a = np.sum(full_correct & no_alpha_correct)
    b = np.sum(full_correct & ~no_alpha_correct)
    c = np.sum(~full_correct & no_alpha_correct)
    d = np.sum(~full_correct & ~no_alpha_correct)
    
    table = [[a, b], [c, d]]
    
    # Calculate McNemar's test
    # If b+c is too small (<25), use exact binomial test (handled by exact=True)
    # We use exact=False and correction=True for general large sample
    use_exact = (b + c) < 25
    result = mcnemar(table, exact=use_exact, correction=True)
    
    return {
        "statistic": float(result.statistic),
        "p_value": float(result.pvalue),
        "n_discordant": int(b + c)
    }

def block_bootstrap_accuracy(y_true: np.ndarray, y_pred: np.ndarray, block_size: int = 5, n_iterations: int = 1000, alpha: float = 0.05) -> Tuple[float, float, float]:
    """
    Perform block bootstrap to get confidence interval for accuracy, accounting for time-series dependence.
    
    Args:
        y_true: Ground truth outcomes
        y_pred: Predicted outcomes
        block_size: Size of contiguous blocks to sample
        n_iterations: Number of bootstrap iterations
        alpha: Significance level for CI
        
    Returns:
        Tuple of (mean_accuracy, lower_ci, upper_ci)
    """
    n = len(y_true)
    if n == 0:
        return 0.0, 0.0, 0.0
        
    if n < block_size:
        block_size = max(1, n // 2)
        
    correct = (y_true == y_pred).astype(float)
    
    n_blocks = int(np.ceil(n / block_size))
    bootstrapped_accs = np.zeros(n_iterations)
    
    for i in range(n_iterations):
        # Sample starting indices for blocks with replacement
        start_indices = np.random.randint(0, n - block_size + 1, size=n_blocks)
        
        # Build the bootstrapped sample
        boot_sample = []
        for start_idx in start_indices:
            boot_sample.extend(correct[start_idx:start_idx + block_size])
            
        # Truncate to exact original length
        boot_sample = np.array(boot_sample[:n])
        bootstrapped_accs[i] = np.mean(boot_sample)
        
    lower_bound = np.percentile(bootstrapped_accs, alpha / 2 * 100)
    upper_bound = np.percentile(bootstrapped_accs, (1 - alpha / 2) * 100)
    
    return float(np.mean(bootstrapped_accs)), float(lower_bound), float(upper_bound)

def calculate_metrics_with_significance(
    actuals: List[str], 
    preds_full: List[str], 
    preds_no_alpha: List[str],
    block_size: int = 5,
    n_bootstrap: int = 1000
) -> Dict:
    """
    Convenience function to compute all statistical significance metrics from raw categorical predictions.
    """
    # Filter out UNKNOWN predictions, ensuring alignment
    # We only compute McNemar on overlapping valid predictions
    valid_idx = [i for i, (a, p1, p2) in enumerate(zip(actuals, preds_full, preds_no_alpha))
                 if p1 != "UNKNOWN" and p2 != "UNKNOWN" and a != "UNKNOWN"]
                 
    if len(valid_idx) < 10:
        return {"error": "Not enough overlapping valid predictions for statistical testing (need >= 10)."}
        
    y_true = np.array([actuals[i] for i in valid_idx])
    y_pred_f = np.array([preds_full[i] for i in valid_idx])
    y_pred_n = np.array([preds_no_alpha[i] for i in valid_idx])
    
    # 1. McNemar's Test
    mcnemar_res = calculate_mcnemar_test(y_true, y_pred_f, y_pred_n)
    
    # 2. Block Bootstrap for Full System
    mean_f, lo_f, hi_f = block_bootstrap_accuracy(y_true, y_pred_f, block_size, n_bootstrap)
    
    # 3. Block Bootstrap for No-Alpha System
    mean_n, lo_n, hi_n = block_bootstrap_accuracy(y_true, y_pred_n, block_size, n_bootstrap)
    
    # 4. Bootstrap Delta
    n = len(y_true)
    correct_f = (y_true == y_pred_f).astype(float)
    correct_n = (y_true == y_pred_n).astype(float)
    delta = correct_f - correct_n
    
    n_blocks = int(np.ceil(n / block_size))
    boot_deltas = np.zeros(n_bootstrap)
    for i in range(n_bootstrap):
        start_indices = np.random.randint(0, n - block_size + 1, size=n_blocks)
        boot_sample = []
        for start_idx in start_indices:
            boot_sample.extend(delta[start_idx:start_idx + block_size])
        boot_sample = np.array(boot_sample[:n])
        boot_deltas[i] = np.mean(boot_sample)
        
    delta_lo = np.percentile(boot_deltas, 2.5)
    delta_hi = np.percentile(boot_deltas, 97.5)
    
    return {
        "n_samples": len(valid_idx),
        "mcnemar_statistic": mcnemar_res["statistic"],
        "mcnemar_p_value": mcnemar_res["p_value"],
        "is_significant_05": mcnemar_res["p_value"] < 0.05,
        "full_acc_ci": [float(lo_f * 100), float(hi_f * 100)],
        "no_alpha_acc_ci": [float(lo_n * 100), float(hi_n * 100)],
        "delta_acc_ci": [float(delta_lo * 100), float(delta_hi * 100)]
    }
