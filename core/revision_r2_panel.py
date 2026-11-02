"""Audit thời gian, regime và phụ thuộc trên prediction R1 đã khóa; không gọi API."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from core.revision72_analysis import block_interval, target
from core.revision_common_study import read_json
from utils.statistical_tests import binary_classification_metrics


POLICY = {
    "schema_version": "revision_r2_panel_v1",
    "scope": "retrospective descriptive audit of the complete frozen R1 study; no new model selection or LLM calls",
    "trend": "decision Close / trailing SMA60 - 1; bull >0.02, bear <-0.02, otherwise sideways; original R1 rule",
    "volatility": "sample SD of 20 past close-to-close simple returns, ddof=1; high if >= the symbol/fold train-only median, otherwise low",
    "liquidity_proxy": "trailing 20-session mean of Close*Volume in vendor quote/volume units; high if >= the symbol/fold train-only median, otherwise low",
    "degenerate_threshold": "nonpositive/nonfinite train median or unavailable history => unknown, never inferred from test",
    "new_strata_status": "volatility/liquidity definitions are post-inference descriptive additions; no confirmatory or regime-strategy claim",
    "join": "calendar decision date x symbol x variant; missing eligibility retained as NA, never CASH",
    "bootstrap": {"seed": 20261102, "repeats": 10000, "unit": "whole historical block with every eligible symbol/date/variant together"},
    "independence": "distinct dates/sessions are counted, not asserted statistically independent; symbol or repeat counts do not increase independent market replications",
}


def context_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Tính mọi đặc trưng regime bằng cửa sổ quá khứ gồm phiên cutoff."""
    close = frame["Close"].astype(float)
    return pd.DataFrame({
        "trend_gap": close / close.rolling(60, min_periods=60).mean() - 1,
        "volatility_20": close.pct_change(fill_method=None).rolling(20, min_periods=20).std(ddof=1),
        "turnover_proxy_20": (close * frame["Volume"].astype(float)).rolling(20, min_periods=20).mean(),
    }).replace([np.inf, -np.inf], np.nan)


def classify_context(features: pd.DataFrame, train: list[int], decision: int) -> dict[str, Any]:
    """Fit hai ngưỡng chỉ trên train; không đọc nhãn hoặc phân phối test."""
    if not train or max(train) >= decision or decision >= len(features):
        raise ValueError("Train/cutoff không hợp lệ cho regime")
    current = features.iloc[decision]
    gap = float(current["trend_gap"])
    result: dict[str, Any] = {"trend_gap": gap,
        "trend": "unknown" if not np.isfinite(gap) else "bull" if gap > .02 else "bear" if gap < -.02 else "sideways"}
    for field, name in (("volatility_20", "volatility"), ("turnover_proxy_20", "liquidity_proxy")):
        available = features[field].iloc[train].dropna()
        threshold = float(available.median()) if len(available) else float("nan")
        value = float(current[field])
        result.update({field: value, name + "_train_median": threshold,
            name: "unknown" if not np.isfinite(value) or not np.isfinite(threshold) or threshold <= 0 else "high" if value >= threshold else "low"})
    return result


def audit_fold(frame: pd.DataFrame, scope: dict, protocol: dict) -> dict:
    """Kiểm chỉ số, label maturity, purge và metadata bằng ngày thực trong snapshot."""
    horizon = int(protocol["horizon_observed_sessions"])
    arrays = {role: np.asarray(scope[role], dtype=int) for role in ("train", "validation", "test")}
    for role, values in arrays.items():
        if not len(values) or np.any(np.diff(values) <= 0) or values.min() < 0 or values.max() + horizon >= len(frame):
            raise ValueError(f"Lịch {role} thiếu/trùng/vượt snapshot")
    train, validation, test = (arrays[k] for k in ("train", "validation", "test"))
    if train[-1] + horizon >= validation[0] or validation[-1] + horizon >= test[0]:
        raise ValueError("Label span chạm split kế tiếp")
    if train[0] + 1 < int(protocol["alpha_history"]) or np.any(test[:-1] + horizon >= test[1:]):
        raise ValueError("Thiếu warm-up hoặc target test chồng lấn")
    dates = frame["date"].to_numpy()
    actual = {"last_train_label_date": str(dates[train[-1] + horizon]),
        "first_validation_date": str(dates[validation[0]]),
        "last_validation_label_date": str(dates[validation[-1] + horizon]),
        "first_test_date": str(dates[test[0]])}
    if any(scope[k] != v for k, v in actual.items()):
        raise ValueError("Metadata split không khớp snapshot")
    result = {"symbol": scope["symbol"], "fold": scope["fold"], **actual, "purge_pass": True,
        "first_train_date": str(dates[train[0]]), "last_test_label_date": str(dates[test[-1] + horizon]),
        "warmup_available_at_first_train": int(train[0] + 1), "warmup_available_at_first_test": int(test[0] + 1),
        "n_train": int(len(train)), "n_validation": int(len(validation)), "n_test": int(len(test)),
        "n_final_refit": int(len(train) + len(validation))}
    for role, indices in arrays.items():
        net, _ = target(frame, indices.tolist(), protocol)
        result[role + "_up"] = int(net.sum())
        result[role + "_down"] = int(len(net) - net.sum())
    return result


def audit_preprocessing(bank: Path, scope: dict, models: dict) -> None:
    """Đối chiếu stored imputer/scaler với đúng train+validation, không fit lại classifier."""
    features = [read_json(bank / f"features/{scope['symbol']}_{i}.json")["features"]
                for i in scope["train"] + scope["validation"]]
    values = pd.DataFrame(features)
    for name in ("logistic_price", "logistic_matched_market_inputs"):
        stored = models["models"][name]
        if stored["train_rows"] != len(scope["train"]) or stored["validation_rows"] != len(scope["validation"]):
            raise ValueError("Stored fit dùng sample count khác fold")
        imputer = SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)
        transformed = imputer.fit_transform(values[stored["columns"]])
        scaler = StandardScaler().fit(transformed)
        for actual, expected in ((imputer.statistics_, stored["refit_imputer_statistics"]),
                                 (scaler.mean_, stored["refit_scaler_mean"]), (scaler.scale_, stored["refit_scaler_scale"])):
            if not np.allclose(actual, np.asarray(expected, dtype=float), rtol=1e-10, atol=1e-10, equal_nan=True):
                raise ValueError("Preprocessing không tái lập từ train+validation đã purge")


def calendar_panel(units: list[dict], predictions: list[dict], symbols: list[str]) -> pd.DataFrame:
    """Join theo ngày và mã, giữ các ô không đủ eligibility thay vì fill prediction."""
    dates = sorted({u["date"] for u in units})
    variants = sorted({r["variant"] for r in predictions})
    unit_frame = pd.DataFrame(units)
    pred_frame = pd.DataFrame(predictions)
    if unit_frame["id"].duplicated().any() or unit_frame.duplicated(["symbol", "date"]).any() or pred_frame.duplicated(["symbol", "date", "variant"]).any():
        raise ValueError("Panel có duplicate calendar key")
    pairs = pred_frame.merge(unit_frame[["id", "symbol", "date"]], on=["symbol", "date"], how="left", validate="many_to_one")
    if pairs["id"].isna().any() or not (pairs["unit_id"] == pairs["id"]).all():
        raise ValueError("Unit ID/date/symbol không khớp")
    if set(pairs["unit_id"]) != set(unit_frame["id"]):
        raise ValueError("Thiếu prediction của unit đã đăng ký")
    if any(set(g["variant"]) != set(variants) for _, g in pairs.groupby("unit_id")):
        raise ValueError("Các classifier không có common support")
    grid = pd.MultiIndex.from_product([dates, symbols, variants], names=["date", "symbol", "variant"]).to_frame(index=False)
    panel = grid.merge(pred_frame, on=["date", "symbol", "variant"], how="left", validate="one_to_one")
    panel["eligible"] = panel["unit_id"].notna()
    panel["missing_reason"] = np.where(panel["eligible"], "", "BHN_excluded_from_early_blocks_by_valid_suffix_warmup" )
    # Lý do BHN chỉ áp dụng đúng exclusion đã đăng ký, không che missing ngoài dự kiến.
    if any(panel.loc[~panel["eligible"], "symbol"] != "BHN"):
        raise ValueError("Panel thiếu mã ngoài exclusion đã khóa")
    return panel


def group_metrics(rows: list[dict], contexts: dict[str, dict], exposure: dict[tuple[str, str], dict]) -> list[dict]:
    """Báo support/ngày và exposure trong ba target sessions cho từng stratum."""
    result = []
    for dimension in ("trend", "volatility", "liquidity_proxy"):
        groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for row in rows:
            groups[(contexts[row["unit_id"]][dimension], row["variant"])].append(row)
        for (stratum, variant), part in sorted(groups.items()):
            records = [exposure[(r["unit_id"], variant)] for r in part]
            n_sessions = sum(r["target_sessions"] for r in records)
            result.append({"dimension": dimension, "stratum": stratum, "variant": variant,
                "n_units": len(part), "n_dates": len({r["date"] for r in part}),
                "n_symbols": len({r["symbol"] for r in part}),
                "n_target_calendar_dates": len({day for r in records for day in r["dates"]}),
                "target_symbol_sessions": n_sessions,
                "held_target_sessions": sum(r["held_sessions"] for r in records),
                "target_session_exposure": sum(r["held_sessions"] for r in records) / n_sessions,
                "target_close_exposure": sum(r["close_sessions"] for r in records) / n_sessions,
                "exposure_scope": "only three target sessions per unit; excludes cash gaps between scheduled units, not calendar portfolio exposure",
                "metrics": binary_classification_metrics([r["label_net"] for r in part], [r["prediction"] for r in part])})
    return result


def cohort_dependence(rows: list[dict]) -> dict:
    """Giữ toàn panel trong block bootstrap; kiểm các cohort có support khác nhau."""
    cohorts = {
        "all_102": rows,
        "eight_symbols_six_blocks": [r for r in rows if r["symbol"] != "BHN"],
        "nine_symbols_three_recent_blocks": [r for r in rows if r["fold"].startswith("f")],
    }
    result = {}
    for name, selected in cohorts.items():
        variants = sorted({r["variant"] for r in selected})
        metrics = {v: binary_classification_metrics([r["label_net"] for r in selected if r["variant"] == v],
            [r["prediction"] for r in selected if r["variant"] == v]) for v in variants}
        result[name] = {"n_units": len({r["unit_id"] for r in selected}), "n_dates": len({r["date"] for r in selected}),
            "n_blocks": len({r["fold"] for r in selected}), "n_symbols": len({r["symbol"] for r in selected}),
            "metrics": metrics, "intervals": [block_interval(selected, ("AS", v)) for v in variants if v != "AS"]}
    main = cohorts["all_102"]
    leave_out = []
    for block in sorted({r["fold"] for r in main}):
        part = [r for r in main if r["fold"] != block]
        metrics = {v: binary_classification_metrics([r["label_net"] for r in part if r["variant"] == v],
                   [r["prediction"] for r in part if r["variant"] == v]) for v in ("AS", "B", "logistic_price")}
        leave_out.append({"omitted_block": block, "n_units": len({r["unit_id"] for r in part}),
            "AS_B_BA_delta": metrics["AS"]["balanced_accuracy"] - metrics["B"]["balanced_accuracy"],
            "AS_price_BA_delta": metrics["AS"]["balanced_accuracy"] - metrics["logistic_price"]["balanced_accuracy"],
            "metrics": metrics})
    return {"cohorts": result, "leave_one_block_out": leave_out,
        "scope": "few-block descriptive sensitivity only; no independent-symbol Wilcoxon or effective-sample-size claim; cohorts overlap and are not pooled"}
