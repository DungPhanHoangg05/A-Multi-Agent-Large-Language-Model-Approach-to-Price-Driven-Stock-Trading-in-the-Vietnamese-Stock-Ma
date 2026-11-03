"""Hợp đồng risk ratio cho return có tần suất tường minh, không suy từ calendar gap."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np


def cycle_frequency(points: Sequence[Any], timeframe: str, step: int | None) -> dict[str, Any]:
    """Chỉ annualise chu kỳ ngày đều, liền nhau theo bar index có provenance.

    Không lấy số ngày lịch thay số phiên. Lịch có gap, thiếu index, khung nội
    phiên hoặc chỉ một point cần daily ledger/tần suất được xác thực riêng.
    """
    result: dict[str, Any] = {"return_basis": "cycle_end", "periods_per_year": None,
                              "cycle_bars": int(step) if type(step) is int else None,
                              "frequency_status": "unsupported_timeframe"}
    if timeframe.strip().lower() not in ("1d", "1 day", "1 ngày", "daily"):
        return result
    if len(points) < 2:
        return {**result, "frequency_status": "insufficient_schedule"}
    pairs = [(getattr(p, "entry_bar_index", None), getattr(p, "exit_bar_index", None)) for p in points]
    if any(type(v) is not int or v < 0 for pair in pairs for v in pair):
        return {**result, "frequency_status": "missing_bar_indices"}
    entries = np.asarray([pair[0] for pair in pairs])
    spans = np.asarray([pair[1] - pair[0] + 1 for pair in pairs])
    if type(step) is not int or step < 1 or np.any(np.diff(entries) != step) or np.any(spans != step):
        return {**result, "frequency_status": "irregular_or_gapped_cycles"}
    return {**result, "periods_per_year": float(252 / step), "frequency_status": "regular_observed_daily_cycles"}


def risk_ratios(returns: Sequence[float], periods_per_year: float | None) -> dict[str, Any]:
    """Giữ SD population và downside-SD legacy; sửa hệ số annualisation của cả hai.

    Risk-free/MAR bằng zero. Sortino ở đây dùng population SD của các return
    âm, không phải lower-partial-moment RMS. Mẫu số suy biến hoặc tần suất
    chưa biết cho null, không dùng epsilon, zero hoặc Infinity thay thế.
    """
    values = np.asarray(returns, dtype=float)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("Return phải một chiều và hữu hạn")
    if periods_per_year is not None and (isinstance(periods_per_year, bool) or
                                        not np.isfinite(periods_per_year) or periods_per_year <= 0):
        raise ValueError("Tần suất annualisation phải dương hữu hạn hoặc None")
    mean = float(values.mean()) if len(values) else None
    std = float(values.std(ddof=0)) if len(values) else None
    negative = values[values < 0]
    downside = float(negative.std(ddof=0)) if len(negative) else None
    sharpe_unit = float(mean / std) if std is not None and std > 1e-12 else None
    sortino_unit = float(mean / downside) if downside is not None and downside > 1e-12 else None
    scale = float(np.sqrt(periods_per_year)) if periods_per_year is not None else None
    return {"sharpe_ratio": float(sharpe_unit * scale) if sharpe_unit is not None and scale is not None else None,
            "sortino_ratio": float(sortino_unit * scale) if sortino_unit is not None and scale is not None else None,
            "sharpe_unannualised": sharpe_unit, "sortino_unannualised": sortino_unit,
            "periods_per_year": float(periods_per_year) if periods_per_year is not None else None,
            "annualisation_scale": scale, "n_returns": len(values), "n_negative_returns": len(negative),
            "mean_return": mean, "population_sd": std, "negative_population_sd": downside,
            "risk_free_per_period": 0.0, "minimum_acceptable_return": 0.0,
            "sd_ddof": 0, "downside_convention": "population_sd_negative_subset_legacy_not_rms",
            "undefined_policy": "null if frequency unknown, n insufficient or denominator <= 1e-12"}


def round_ratio(value: float | None, digits: int = 2) -> float | None:
    """Làm tròn ratio hữu hạn hoặc giữ null cho JSON/NA của bảng."""
    return round(value, digits) if value is not None else None
