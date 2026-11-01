"""Phân tích Full thực và baselines trên cùng lịch/input bank đã khóa."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from core.revision_audit import sha256_file
from core.revision_baselines import daily_ledger, factor_vote, load_prices, logistic_predictions, numerical_features
from core.revision_common_study import (digest, read_json, unit_key, verify_bank, verify_features, write_json)
from scripts.evaluate_revision_baselines import csv_rows
from utils.statistical_tests import binary_classification_metrics


def checked_unit(run: Path, key: str, signature: str, bank: Path) -> dict:
    """Chỉ nhận quyết định có hash/ready parent/call archive thật khớp cùng run."""
    unit = read_json(run / "units" / f"{key}.json")
    if unit["parent"]["run_signature"] != signature or digest({k: v for k, v in unit.items() if k != "sha256"}) != unit["sha256"]:
        raise ValueError("Unit không khớp run hoặc content hash")
    context = unit["context"]
    parent_repeat = context["repeat_id"] if context["kind"] == "e2e" else 0
    ready_key = unit_key(context["symbol"], context["fold"], context["decision"], context["role"], "e2e", parent_repeat)
    ready = read_json(run / "ready" / f"{ready_key}.json")
    if ready["sha256"] != unit["parent"]["ready_hash"] or digest({k: v for k, v in ready.items() if k != "sha256"}) != ready["sha256"]:
        raise ValueError("Shared reports không khớp Decision parent")
    feature = read_json(bank / "features" / f"{context['symbol']}_{context['decision']}.json")
    if ready["parent"]["feature_hash"] != feature["sha256"]:
        raise ValueError("Full dùng feature/input khác baseline")
    if unit["prediction"] not in ("LONG", "SHORT") or not unit["request_ids"]:
        raise ValueError("Thiếu binary prediction/request lineage")
    successful = 0
    upstream_nodes = set()
    current_decision = False
    last_decision_raw = None
    for attempt in unit["request_ids"]:
        request = read_json(run / "calls" / f"{attempt}.request.json")
        if digest({k: v for k, v in request.items() if k != "sha256"}) != request["sha256"]:
            raise ValueError("Raw request bị sửa")
        response_path = run / "calls" / f"{attempt}.response.json"
        if response_path.exists():
            response = read_json(response_path)
            if response["parent_request_hash"] != request["sha256"]:
                raise ValueError("Response không khớp request")
            successful += 1
            if request["context"].get("stage") == "upstream":
                upstream_nodes.add(request.get("model_metadata", {}).get("langgraph_node"))
            if request["context"] == context:
                current_decision = True
                message = response["response"]["generations"][0][0]["message"]
                last_decision_raw = message.get("content", "")
                if not last_decision_raw:
                    calls = message.get("additional_kwargs", {}).get("tool_calls", [])
                    last_decision_raw = calls[0].get("function", {}).get("arguments", "") if calls else ""
        elif not (run / "calls" / f"{attempt}.error.json").exists():
            raise ValueError("Request chưa có response/error archive")
    if successful < 3 or not current_decision or not ready["state"].get("indicator_report") or not {"Pattern Agent", "Trend Agent"}.issubset(upstream_nodes):
        raise ValueError("Full không có đủ upstream/Decision responses")
    from utils.decision_parser import parse_decision
    from_raw = parse_decision(str(last_decision_raw), lang="vi").get("decision")
    from_state = parse_decision(unit["decision_state"]["final_trade_decision"], lang="vi").get("decision")
    if from_raw != unit["prediction"] or from_state != unit["prediction"]:
        raise ValueError("Prediction không tái lập được từ raw response/parsed state")
    return unit


def analyze(root: Path, bank: Path, run: Path, output: Path) -> None:
    """Không lấy prediction legacy hoặc ghép repeats thành quan sát thị trường độc lập."""
    if output.exists():
        raise FileExistsError("Không ghi đè analysis đã chốt")
    manifest = verify_bank(root, bank)
    verify_features(bank, manifest)
    protocol = manifest["protocol"]
    identity = read_json(run / "run_manifest.json")
    complete = read_json(run / "inference_complete.json")
    if identity["bank_id"] != manifest["bank_id"] or complete["run_signature"] != identity["run_signature"]:
        raise ValueError("Inference receipt khác bank/run")
    for artifact in complete["artifacts"]:
        path = (run / artifact["path"]).resolve()
        if not path.is_relative_to(run.resolve()) or sha256_file(path) != artifact["sha256"]:
            raise ValueError("Inference artifact không khớp receipt")
    frames, _ = load_prices(root / protocol["price_snapshot"], protocol["price_quality_policy"])
    output.mkdir(parents=True)
    summary, classes, predictions, model_records = [], [], [], []
    pooled: dict[tuple, list[list[str]]] = defaultdict(lambda: [[], []])
    total_full = 0
    for slot, schedule in enumerate(manifest["schedule"]):
        symbol, fold = schedule["symbol"], schedule["fold"]
        frame = frames[symbol]

        def matrix(role: str) -> pd.DataFrame:
            return pd.DataFrame([read_json(bank / "features" / f"{symbol}_{i}.json")["features"] for i in schedule[role]])

        def labels(indices: list[int]) -> tuple[np.ndarray, np.ndarray]:
            entries = frame["Open"].to_numpy(float)[np.asarray(indices) + 1]
            exits = frame["Close"].to_numpy(float)[np.asarray(indices) + protocol["horizon_observed_sessions"]]
            gross = exits / entries - 1
            net = (gross + 1) * (1 - protocol["fee_each_side"]) * (1 - protocol["slippage_each_side"]) / ((1 + protocol["fee_each_side"]) * (1 + protocol["slippage_each_side"])) - 1
            return (net > 0).astype(int), (gross > 0).astype(int)

        tx, vx, sx = matrix("train"), matrix("validation"), matrix("test")
        if list(tx.columns) != list(vx.columns) or list(tx.columns) != list(sx.columns):
            raise ValueError("Schema matched features khác giữa train/validation/test")
        ty, _ = labels(schedule["train"])
        vy, _ = labels(schedule["validation"])
        truth, gross_truth = labels(schedule["test"])
        variants = {"constant_down_cash": np.zeros(len(sx), dtype=int),
                    "constant_up_cycles": np.ones(len(sx), dtype=int),
                    "train_majority": np.full(len(sx), int(np.mean(ty) > .5))}
        numerical, _, alpha_columns = numerical_features(frame, [])
        variants["momentum_20"] = (numerical["return_20"].iloc[schedule["test"]].to_numpy() > 0).astype(int)
        models = {}
        for name, columns in (("logistic_price", [c for c in tx if c.startswith("price_")]),
                              ("logistic_matched_market_inputs", list(tx.columns))):
            variants[name], models[name] = logistic_predictions(tx[columns], ty, vx[columns], vy, sx[columns], protocol)
        variants["factor_only_vote"], models["factor_only_vote"] = factor_vote(
            numerical[alpha_columns].iloc[schedule["train"]], ty,
            numerical[alpha_columns].iloc[schedule["test"]])
        calibration = [checked_unit(run, unit_key(symbol, fold, i, "calibration", "e2e", 0), identity["run_signature"], bank)
                       for i in schedule["calibration"]]
        total_full += len(calibration)
        long_count = sum(u["prediction"] == "LONG" for u in calibration)
        probability = long_count / len(calibration)
        ci = binomtest(long_count, len(calibration)).proportion_ci(method="exact")
        seed = protocol["exposure_seed"] + slot
        variants["full_train_exposure_control"] = (np.random.default_rng(seed).random(len(sx)) < probability).astype(int)
        models["exposure_control"] = {"p_full_train": probability, "n_calibration": len(calibration),
            "n_long_train": long_count, "p_exact_ci_95": [float(ci.low), float(ci.high)], "seed": seed,
            "test_outcomes_used": False, "exact_test_exposure_match_claimed": False}
        model_records.append({"symbol": symbol, "fold": fold, "n_train": len(tx), "n_validation": len(vx),
            "source_market_information": "identical cached OHLCV and alpha/sentiment numeric inputs, not LLM prose embeddings",
            "models": models})
        regimes = np.where(numerical["sma60_gap"].iloc[schedule["test"]].to_numpy() > .02, "bull",
                    np.where(numerical["sma60_gap"].iloc[schedule["test"]].to_numpy() < -.02, "bear", "sideways"))

        def record(variant: str, predicted: np.ndarray, kind: str, repeat: int) -> None:
            actual = np.where(truth, "UP", "DOWN")
            pred = np.where(predicted, "LONG", "SHORT")
            metrics = binary_classification_metrics(actual, pred)
            ledger = daily_ledger(frame, [(i + 1, i + protocol["horizon_observed_sessions"], int(p))
                                         for i, p in zip(schedule["test"], predicted)], protocol)
            daily = ledger.pop("daily")
            filename = f"{symbol}_{fold}_{variant}_{kind}_{repeat}"
            csv_rows(output / "daily" / f"{filename}.csv", daily)
            summary.append({"symbol": symbol, "fold": fold, "variant": variant, "kind": kind, "repeat_id": repeat,
                "n_test": len(pred), "accuracy": metrics["accuracy"], "balanced_accuracy": metrics["balanced_accuracy"],
                "mcc": metrics["mcc"], "macro_f1": metrics["macro_f1"], "long_rate": metrics["long_rate"], **ledger})
            classes.append({"symbol": symbol, "fold": fold, "variant": variant, "kind": kind, "repeat_id": repeat,
                            "regime": "ALL", "metrics": metrics})
            for regime in sorted(set(regimes)):
                mask = regimes == regime
                classes.append({"symbol": symbol, "fold": fold, "variant": variant, "kind": kind,
                    "repeat_id": repeat, "regime": str(regime), "metrics": binary_classification_metrics(actual[mask], pred[mask])})
            pair = pooled[(variant, kind, repeat)]
            pair[0].extend(actual.tolist())
            pair[1].extend(pred.tolist())
            for i, a, g, p in zip(schedule["test"], actual, gross_truth, pred):
                feature = read_json(bank / "features" / f"{symbol}_{i}.json")
                predictions.append({"symbol": symbol, "fold": fold, "date": str(frame["date"].iloc[i]),
                    "variant": variant, "kind": kind, "repeat_id": repeat, "label_net": str(a),
                    "label_gross": "UP" if g else "DOWN", "prediction": str(p),
                    "market_input_hash": feature["market_input_hash"]})

        (output / "daily").mkdir(exist_ok=True)
        for name, predicted in variants.items():
            record(name, predicted, "deterministic", 0)
        for kind, repeats in (("e2e", range(protocol["end_to_end_repeats"])),
                              ("decision", range(1, protocol["decision_only_repeats"]))):
            for repeat in repeats:
                units = [checked_unit(run, unit_key(symbol, fold, i, "test", kind, repeat), identity["run_signature"], bank)
                         for i in schedule["test"]]
                total_full += len(units)
                record("full", np.asarray([u["prediction"] == "LONG" for u in units], dtype=int), kind, repeat)
        hold = daily_ledger(frame, [(schedule["test"][0] + 1, schedule["test"][-1] + protocol["horizon_observed_sessions"], 1)], protocol)
        csv_rows(output / "daily" / f"{symbol}_{fold}_continuous_hold.csv", hold.pop("daily"))
        summary.append({"symbol": symbol, "fold": fold, "variant": "continuous_hold_price_only", "kind": "deterministic",
            "repeat_id": 0, "n_test": None, "accuracy": None, "balanced_accuracy": None, "mcc": None,
            "macro_f1": None, "long_rate": None, **hold})
    expected = manifest["n_calibration"] + manifest["n_test"] * (protocol["end_to_end_repeats"] + protocol["decision_only_repeats"] - 1)
    if total_full != expected or complete["n_decisions"] != expected:
        raise ValueError("Inference receipt chưa đủ mọi calibration/fold/repeat")
    csv_rows(output / "summary.csv", summary)
    csv_rows(output / "predictions.csv", predictions)
    write_json(output / "classification.json", classes, exclusive=True)
    write_json(output / "models.json", model_records, exclusive=True)
    pooled_records = [{"variant": v, "kind": k, "repeat_id": r, "metrics": binary_classification_metrics(*pairs)}
                      for (v, k, r), pairs in sorted(pooled.items())]
    distributions = {}
    for family, keys in (("end_to_end", [("e2e", r) for r in range(protocol["end_to_end_repeats"])]),
                         ("decision_only", [("e2e", 0)] + [("decision", r) for r in range(1, protocol["decision_only_repeats"])])):
        values = [next(row["metrics"] for row in pooled_records if row["variant"] == "full" and (row["kind"], row["repeat_id"]) == key) for key in keys]
        distributions[family] = {}
        for metric in ("accuracy", "balanced_accuracy", "mcc", "macro_f1"):
            scores = [m[metric] for m in values]
            distributions[family][metric] = None if any(v is None for v in scores) else {
                "n_repeats": len(scores), "mean": float(np.mean(scores)), "sd": float(np.std(scores, ddof=1)),
                "min": float(np.min(scores)), "max": float(np.max(scores))}
    write_json(output / "report.json", {"schema_version": "r1_common_analysis_v1", "bank_id": manifest["bank_id"],
        "run_signature": identity["run_signature"], "n_unique_scheduled_test": manifest["n_test"],
        "n_full_decisions_including_calibration": total_full,
        "pooled_by_repeat": pooled_records, "repeat_distributions": distributions,
        "decision_repeat_zero_parent": {"kind": "e2e", "repeat_id": 0},
        "scope": protocol["inference_scope"], "acceptance_limitations": protocol["acceptance_scope"],
        "no_legacy_predictions_used": True}, exclusive=True)
    write_json(output / "manifest.json", {"bank_id": manifest["bank_id"],
        "sources": [{"path": p.relative_to(root).as_posix(), "sha256": sha256_file(p)} for p in
                    (bank / "manifest.json", bank / "features_complete.json", run / "run_manifest.json", run / "inference_complete.json")],
        "outputs": [{"path": p.relative_to(output).as_posix(), "sha256": sha256_file(p)} for p in sorted(output.rglob("*")) if p.is_file()]}, exclusive=True)
    print("Đã phân tích cùng snapshot; không tự đóng các gate khoa học ngoài phạm vi R1.")
