"""Chạy baselines số trên mọi fold của bank chung trong lúc chờ inference Full."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.revision_audit import sha256_file
from core.revision_baselines import daily_ledger, factor_vote, load_prices, logistic_predictions, numerical_features
from core.revision_common_study import read_json, verify_bank, verify_features, write_json
from scripts.evaluate_revision_baselines import csv_rows
from utils.statistical_tests import binary_classification_metrics


def evaluate(bank: Path, output: Path) -> None:
    """Không dựng Full hoặc exposure control giả khi chưa có calibration thực."""
    if output.exists():
        raise FileExistsError("Không ghi đè release số chung snapshot")
    manifest = verify_bank(ROOT, bank)
    verify_features(bank, manifest)
    protocol = manifest["protocol"]
    frames, _ = load_prices(ROOT / protocol["price_snapshot"], protocol["price_quality_policy"])
    output.mkdir(parents=True)
    (output / "daily").mkdir()
    summary, predictions, classes, models = [], [], [], []
    pooled: dict[str, list[list[str]]] = defaultdict(lambda: [[], []])
    numerical_cache = {}
    for schedule in manifest["schedule"]:
        symbol, fold = schedule["symbol"], schedule["fold"]
        frame = frames[symbol]
        if symbol not in numerical_cache:
            numerical_cache[symbol] = numerical_features(frame, [])
        numerical, _, factor_columns = numerical_cache[symbol]
        feature_sets = {}
        for role in ("train", "validation", "test"):
            feature_sets[role] = pd.DataFrame([read_json(bank / "features" / f"{symbol}_{i}.json")["features"]
                                               for i in schedule[role]])
        tx, vx, sx = (feature_sets[role] for role in ("train", "validation", "test"))
        if list(tx.columns) != list(vx.columns) or list(tx.columns) != list(sx.columns):
            raise ValueError("Schema feature khác giữa các split")

        def target(indices: list[int]) -> tuple[np.ndarray, np.ndarray]:
            indices = np.asarray(indices)
            gross = frame["Close"].to_numpy(float)[indices + protocol["horizon_observed_sessions"]] / frame["Open"].to_numpy(float)[indices + 1] - 1
            net = (gross + 1) * (1 - protocol["fee_each_side"]) * (1 - protocol["slippage_each_side"]) / ((1 + protocol["fee_each_side"]) * (1 + protocol["slippage_each_side"])) - 1
            return (net > 0).astype(int), (gross > 0).astype(int)

        ty, _ = target(schedule["train"])
        vy, _ = target(schedule["validation"])
        sy, gross = target(schedule["test"])
        variants = {"constant_down_cash": np.zeros(len(sx), dtype=int),
                    "constant_up_cycles": np.ones(len(sx), dtype=int),
                    "train_majority": np.full(len(sx), int(np.mean(ty) > .5)),
                    "momentum_20": (numerical["return_20"].iloc[schedule["test"]].to_numpy() > 0).astype(int)}
        fitted = {}
        for name, columns in (("logistic_price", [c for c in tx if c.startswith("price_")]),
                              ("logistic_matched_market_inputs", list(tx.columns))):
            variants[name], fitted[name] = logistic_predictions(tx[columns], ty, vx[columns], vy, sx[columns], protocol)
        variants["factor_only_vote"], fitted["factor_only_vote"] = factor_vote(
            numerical[factor_columns].iloc[schedule["train"]], ty,
            numerical[factor_columns].iloc[schedule["test"]])
        models.append({"symbol": symbol, "fold": fold, "n_train": len(tx), "n_validation": len(vx),
                       "n_price_columns": sum(c.startswith("price_") for c in tx),
                       "n_matched_market_columns": len(tx.columns), "models": fitted})
        regimes = np.where(numerical["sma60_gap"].iloc[schedule["test"]].to_numpy() > .02, "bull",
                    np.where(numerical["sma60_gap"].iloc[schedule["test"]].to_numpy() < -.02, "bear", "sideways"))
        truth = np.where(sy, "UP", "DOWN")
        for name, values in variants.items():
            pred = np.where(values, "LONG", "SHORT")
            metrics = binary_classification_metrics(truth, pred)
            pooled[name][0].extend(truth.tolist())
            pooled[name][1].extend(pred.tolist())
            classes.append({"symbol": symbol, "fold": fold, "variant": name, "regime": "ALL", "metrics": metrics})
            for regime in sorted(set(regimes)):
                mask = regimes == regime
                classes.append({"symbol": symbol, "fold": fold, "variant": name, "regime": str(regime),
                                "metrics": binary_classification_metrics(truth[mask], pred[mask])})
            ledger = daily_ledger(frame, [(i + 1, i + protocol["horizon_observed_sessions"], int(v))
                                         for i, v in zip(schedule["test"], values)], protocol)
            csv_rows(output / "daily" / f"{symbol}_{fold}_{name}.csv", ledger.pop("daily"))
            summary.append({"symbol": symbol, "fold": fold, "variant": name, "n_test": len(sx),
                "accuracy": metrics["accuracy"], "balanced_accuracy": metrics["balanced_accuracy"],
                "mcc": metrics["mcc"], "macro_f1": metrics["macro_f1"], "long_rate": metrics["long_rate"], **ledger})
            for i, a, g, p in zip(schedule["test"], truth, gross, pred):
                feature = read_json(bank / "features" / f"{symbol}_{i}.json")
                predictions.append({"symbol": symbol, "fold": fold, "date": str(frame["date"].iloc[i]),
                    "variant": name, "prediction": str(p), "label_net": str(a), "label_gross": "UP" if g else "DOWN",
                    "market_input_hash": feature["market_input_hash"]})
        hold = daily_ledger(frame, [(schedule["test"][0] + 1, schedule["test"][-1] + protocol["horizon_observed_sessions"], 1)], protocol)
        csv_rows(output / "daily" / f"{symbol}_{fold}_continuous_hold.csv", hold.pop("daily"))
        summary.append({"symbol": symbol, "fold": fold, "variant": "continuous_hold_price_only", "n_test": None,
            "accuracy": None, "balanced_accuracy": None, "mcc": None, "macro_f1": None, "long_rate": None, **hold})
        print(f"Baselines {symbol}/{fold}: train={len(tx)}, validation={len(vx)}, test={len(sx)}.", flush=True)
    csv_rows(output / "summary.csv", summary)
    csv_rows(output / "predictions.csv", predictions)
    write_json(output / "classification.json", classes, exclusive=True)
    write_json(output / "models.json", models, exclusive=True)
    write_json(output / "report.json", {"schema_version": "r1_common_numeric_v1", "bank_id": manifest["bank_id"],
        "status": "numeric_complete_waiting_for_real_full_inference", "n_scheduled_test": manifest["n_test"],
        "n_folds": len(protocol["folds"]), "n_prediction_records": len(predictions), "n_daily_ledgers": len(summary),
        "n_distinct_decision_dates": len({r["date"] for r in predictions}),
        "pooled_metrics": {v: binary_classification_metrics(*pairs) for v, pairs in pooled.items()},
        "missing_variants": ["full", "full_train_exposure_control"],
        "scope": "deterministic numeric baselines only; no synthetic LLM repeats; symbol/fold means are not a joint portfolio; prospective validity and certified execution remain outside scope"}, exclusive=True)
    sources = [bank / "manifest.json", bank / "features_complete.json", Path(__file__).resolve()]
    write_json(output / "manifest.json", {
        "sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p)} for p in sources],
        "outputs": [{"path": p.relative_to(output).as_posix(), "sha256": sha256_file(p)} for p in sorted(output.rglob("*")) if p.is_file()]}, exclusive=True)


def main() -> None:
    """Chỉ chạy offline; không nhận key và không tạo client provider."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, default=ROOT / "outputs/revision/r1_common_bank_v3")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/revision/r1_common_numeric_v3")
    args = parser.parse_args()
    evaluate(args.bank.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
