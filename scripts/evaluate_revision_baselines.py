"""Đánh giá baselines số trên snapshot mới và báo riêng tính so sánh với legacy."""

from __future__ import annotations

import argparse
import csv
from importlib.metadata import version
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.revision_audit import DEFAULT_SYMBOLS, build_legacy_report, sha256_file
from core.revision_baselines import (daily_ledger, factor_vote, load_prices, logistic_predictions,
                                     numerical_features, samples, temporal_split)
from utils.statistical_tests import binary_classification_metrics


def dump(path: Path, payload: object) -> None:
    """JSON không có NaN/Infinity và giữ nguyên byte khi commit bundle."""
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def csv_rows(path: Path, rows: list[dict]) -> None:
    """Xuất bảng với NA rõ ràng cho trường không xác định."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: "NA" if v is None else v for k, v in row.items()} for row in rows)


def matched_schedule(frame: pd.DataFrame, legacy: dict, protocol: dict) -> tuple[pd.DataFrame, list[dict]]:
    """Không sửa label cũ; ghi cả mọi sai lệch giá/label và horizon ở snapshot mới."""
    date_index = {day: index for index, day in enumerate(frame["date"])}
    rows, differences = [], []
    for point in legacy["test_points"]:
        d = date_index[point["window_end"][:10]]
        e, h = d + 1, d + protocol["horizon_observed_sessions"]
        if h >= len(frame):
            raise ValueError("Snapshot chưa có label trưởng thành của test")
        entry, exit_price = float(frame["Open"].iloc[e]), float(frame["Close"].iloc[h])
        fee, slip = protocol["fee_each_side"], protocol["slippage_each_side"]
        gross = exit_price / entry - 1
        net = (gross + 1) * (1 - fee) * (1 - slip) / ((1 + fee) * (1 + slip)) - 1
        row = {"test_id": point["test_id"], "decision": d, "entry": e, "exit": h,
               "date": frame["date"].iloc[d], "entry_date": frame["date"].iloc[e],
               "exit_date": frame["date"].iloc[h], "entry_open": entry, "exit_close": exit_price,
               "label": int(net > 0), "label_gross": int(gross > 0)}
        fields = []
        if row["entry_date"] != point["entry_time"][:10] or row["exit_date"] != point["exit_time"][:10]:
            fields.append("calendar_horizon")
        for key in ("entry_open", "exit_close"):
            if abs(row[key] - float(point[key])) > protocol["price_match_atol"]:
                fields.append(key)
        if ("UP" if net > 0 else "DOWN") != point["actual_direction"]:
            fields.append("net_label")
        if fields:
            differences.append({"test_id": point["test_id"], "date": row["date"], "fields": fields,
                                "legacy_entry": point["entry_open"], "new_entry": entry,
                                "legacy_exit": point["exit_close"], "new_exit": exit_price,
                                "legacy_label": point["actual_direction"], "new_label": "UP" if net > 0 else "DOWN"})
        rows.append(row)
    return pd.DataFrame(rows), differences


def evaluate(price_dir: Path, output: Path, protocol_path: Path) -> None:
    """Chạy offline, không chọn release/cutoff/seed theo outcome và không trộn Full vào bảng khác giá."""
    if output.exists():
        raise FileExistsError("Không ghi đè release kết quả đã tồn tại")
    protocol = json.loads(protocol_path.read_bytes())
    frames, price_manifest = load_prices(price_dir, protocol.get("price_quality_policy", "reject"))
    if set(frames) != set(DEFAULT_SYMBOLS):
        raise ValueError("Cần đủ chín mã của protocol")
    output.mkdir(parents=True)
    pooled, grouped, summary, model_records, prediction_rows, differences = {}, {}, [], {}, [], []
    classification_records = []
    source_paths = [protocol_path, price_dir / "manifest.json", ROOT / "core/revision_baselines.py",
                    Path(__file__), ROOT / "core/alpha_compare.py", ROOT / "utils/statistical_tests.py",
                    ROOT / "scripts/freeze_revision_prices.py", ROOT / "tests/test_revision_baseline_leakage.py",
                    ROOT / "revision/requirements-r1.txt", ROOT / "core/revision_audit.py",
                    ROOT / "outputs/revision/r1_source_inventory.json",
                    ROOT / "scripts/inventory_revision_sources.py"]
    fold = "train_to_2025_validation_2026_legacy_schedule"
    for symbol_index, symbol in enumerate(DEFAULT_SYMBOLS):
        frame = frames[symbol]
        legacy_paths = sorted((ROOT / "outputs/backtest_result").glob(f"backtest_{symbol}_*.json"))
        if len(legacy_paths) != 1:
            raise ValueError(f"{symbol}: chưa chọn được artifact legacy duy nhất")
        legacy = json.loads(legacy_paths[0].read_bytes())
        news_path = ROOT / f"sentiment_cache_{symbol}.json"
        articles = json.loads(news_path.read_bytes())["scored_articles"] if news_path.exists() else []
        source_paths += [legacy_paths[0], price_dir / f"{symbol}.csv"]
        if news_path.exists():
            source_paths.append(news_path)
        test, mismatch = matched_schedule(frame, legacy, protocol)
        differences += [{"symbol": symbol, **m} for m in mismatch]
        features, price_columns, alpha_columns = numerical_features(frame, articles)
        train_sample = samples(frame, protocol)
        train_idx, val_idx = temporal_split(train_sample, test["date"].iloc[0], protocol)
        train, val = train_sample.loc[train_idx], train_sample.loc[val_idx]
        y_train, y_val = train["label"].to_numpy(int), val["label"].to_numpy(int)
        train_x = features.iloc[train["decision"]].reset_index(drop=True)
        val_x = features.iloc[val["decision"]].reset_index(drop=True)
        test_x = features.iloc[test["decision"]].reset_index(drop=True)
        predictions = {"constant_down_cash": np.zeros(len(test), dtype=int),
                       "constant_up_cycles": np.ones(len(test), dtype=int),
                       "train_majority": np.full(len(test), int(np.mean(y_train) > .5)),
                       "momentum_20": (test_x["return_20"].to_numpy() > 0).astype(int)}
        models = {}
        for name, columns in (("logistic_price", price_columns),
                              ("logistic_price_alpha_sentiment", list(features.columns))):
            predictions[name], models[name] = logistic_predictions(
                train_x[columns], y_train, val_x[columns], y_val, test_x[columns], protocol)
        predictions["factor_only_vote"], models["factor_only_vote"] = factor_vote(
            train_x[alpha_columns], y_train, test_x[alpha_columns])
        probability = float(np.mean(train_x["return_20"].to_numpy() > 0))
        rng = np.random.default_rng(protocol["exposure_seed"] + symbol_index)
        predictions["train_momentum_exposure_control"] = (rng.random(len(test)) < probability).astype(int)
        models["exposure_control"] = {"p_train": probability, "seed": protocol["exposure_seed"] + symbol_index,
                                      "reference": "train momentum, not Full", "full_matched": False}
        model_records[symbol] = {"fold": fold, "n_train": len(train), "n_validation": len(val),
                                 "last_train_label_date": train["exit_date"].iloc[-1],
                                 "first_validation_date": val["date"].iloc[0],
                                 "last_validation_label_date": val["exit_date"].iloc[-1],
                                 "first_test_date": test["date"].iloc[0], "models": models,
                                 "n_test_verified_sentiment_available": int((test_x["sentiment_missing"] == 0).sum()),
                                 "feature_information_equivalence_to_full": "unverified; 85-factor superset, reports/peers absent"}
        regime = np.where(test_x["sma60_gap"] > .02, "bull", np.where(test_x["sma60_gap"] < -.02, "bear", "sideways"))
        for variant, predicted in predictions.items():
            truth = np.where(test["label"].to_numpy(), "UP", "DOWN")
            pred = np.where(predicted, "LONG", "SHORT")
            metrics = binary_classification_metrics(truth, pred)
            classification_records.append({"symbol": symbol, "variant": variant, "fold": fold,
                "repeat_id": 0, "target": "net", "regime": "ALL", "metrics": metrics})
            classification_records.append({"symbol": symbol, "variant": variant, "fold": fold,
                "repeat_id": 0, "target": "gross_secondary_same_predictions", "regime": "ALL",
                "metrics": binary_classification_metrics(np.where(test["label_gross"], "UP", "DOWN"), pred)})
            pooled.setdefault(variant, [[], []])
            pooled[variant][0].extend(truth.tolist())
            pooled[variant][1].extend(pred.tolist())
            for group in sorted(set(regime)):
                mask = regime == group
                grouped.setdefault((variant, str(group)), [[], []])
                grouped[(variant, str(group))][0].extend(truth[mask].tolist())
                grouped[(variant, str(group))][1].extend(pred[mask].tolist())
                classification_records.append({"symbol": symbol, "variant": variant, "fold": fold,
                    "repeat_id": 0, "target": "net", "regime": str(group),
                    "metrics": binary_classification_metrics(truth[mask], pred[mask])})
            cycles = list(zip(test["entry"].astype(int), test["exit"].astype(int), predicted.tolist()))
            ledger = daily_ledger(frame, cycles, protocol)
            daily = ledger.pop("daily")
            csv_rows(output / f"daily_{symbol}_{variant}.csv", daily)
            summary.append({"symbol": symbol, "variant": variant, "fold": fold, "repeat_id": 0,
                            "n_test": len(test), "accuracy": metrics["accuracy"], "balanced_accuracy": metrics["balanced_accuracy"],
                            "mcc": metrics["mcc"], "macro_f1": metrics["macro_f1"], "long_rate": metrics["long_rate"], **ledger})
            for index in range(len(test)):
                prediction_rows.append({"symbol": symbol, "variant": variant, "fold": fold, "repeat_id": 0,
                    "date": test["date"].iloc[index], "regime": str(regime[index]),
                    "label_net": str(truth[index]), "label_gross": "UP" if test["label_gross"].iloc[index] else "DOWN",
                    "prediction": str(pred[index]), "entry_open": float(test["entry_open"].iloc[index]),
                    "exit_close": float(test["exit_close"].iloc[index])})
        hold = daily_ledger(frame, [(int(test["entry"].iloc[0]), int(test["exit"].iloc[-1]), 1)], protocol)
        csv_rows(output / f"daily_{symbol}_continuous_hold.csv", hold.pop("daily"))
        summary.append({"symbol": symbol, "variant": "continuous_hold_price_only", "fold": fold, "repeat_id": 0,
                        "n_test": None, "accuracy": None, "balanced_accuracy": None, "mcc": None,
                        "macro_f1": None, "long_rate": None, **hold})
        print(f"Đã đánh giá {symbol}: train={len(train)}, validation={len(val)}, test={len(test)}, sai lệch legacy={len(mismatch)}")
    pooled_metrics = {v: binary_classification_metrics(*pairs) for v, pairs in pooled.items()}
    macro = {v: {key: float(np.mean([r[key] for r in summary if r["variant"] == v]))
                 if all(r[key] is not None for r in summary if r["variant"] == v) else None
                 for key in ("accuracy", "balanced_accuracy", "mcc", "macro_f1", "long_rate", "net_return_pct")}
             for v in sorted({r["variant"] for r in summary})}
    report = {"schema_version": "r1_numeric_evaluation_v1", "protocol_sha256": sha256_file(protocol_path),
              "status": "exploratory_reconstructed_snapshot", "n_test": 180, "n_symbols": 9,
              "legacy_comparison_status": "blocked_snapshot_mismatch" if differences else "canonical_prices_match_inputs_still_unverified",
              "legacy_full_used_in_numeric_table": False,
              "legacy_discrepancies": differences, "n_legacy_price_or_label_mismatches": len(differences),
              "n_legacy_label_mismatches": sum("net_label" in d["fields"] for d in differences),
              "pooled_metrics": pooled_metrics, "macro_over_symbols": macro,
              "regime_metrics": [{"variant": v, "regime": g, "metrics": binary_classification_metrics(*pairs)}
                                 for (v, g), pairs in sorted(grouped.items())],
              "runtime": {name: version(name) for name in ("numpy", "pandas", "scipy", "scikit-learn", "TA-Lib")},
              "price_manifest": price_manifest,
              "open_requirements": protocol["open_dependencies"]}
    csv_rows(output / "summary.csv", summary)
    csv_rows(output / "predictions.csv", prediction_rows)
    dump(output / "report.json", report)
    dump(output / "models.json", model_records)
    dump(output / "classification.json", classification_records)
    legacy_report = build_legacy_report(sorted((ROOT / "outputs/backtest_result").glob("*.json")), ROOT)
    dump(output / "legacy_recomputed.json", legacy_report)
    dump(output / "manifest.json", {"schema_version": "r1_numeric_release_v1",
        "sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p)} for p in sorted(set(source_paths))],
        "outputs": [{"path": p.name, "sha256": sha256_file(p)} for p in sorted(output.iterdir()) if p.is_file()]})


def main() -> None:
    """CLI offline chỉ dùng đường dẫn snapshot được cung cấp rõ ràng."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prices", type=Path, default=ROOT / "outputs/revision/r1_prices_v1")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/revision/r1_numeric_v1")
    parser.add_argument("--protocol", type=Path, default=ROOT / "revision/r1_protocol.json")
    args = parser.parse_args()
    evaluate(args.prices.resolve(), args.output.resolve(), args.protocol.resolve())


if __name__ == "__main__":
    main()
