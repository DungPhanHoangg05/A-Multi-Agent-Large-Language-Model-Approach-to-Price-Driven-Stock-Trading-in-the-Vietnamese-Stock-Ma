"""Runner T13 offline có freeze/checkpoints; mọi controls dùng cùng design T12."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

from core.revision_alpha_contract import safe
from core.revision_audit import sha256_file
from core.revision_baselines import daily_ledger, load_prices
from core.revision_call_archive import StudyLock
from core.revision_common_study import digest, read_json, write_json
from core.revision_numeric_design import causal_factors, fit_on_scope, predict_vote, strategy_sets, validate_protocol, validate_scope
from core.revision_numeric_statistics import classification, describe, paired_inference
from core.revision_sentiment_inventory import BANK, RUN, require, verify_release

DESIGN = Path("outputs/revision/numeric_controls_design_v1")
OUTPUT = Path("outputs/revision/numeric_controls_v1")
NEW_SOURCES = ("core/revision_numeric_controls.py", "core/revision_numeric_statistics.py", "scripts/run_numeric_controls.py",
               "tests/test_revision_numeric_controls.py", "tests/test_revision_numeric_statistics.py", "tests/test_revision_numeric_controls_leakage.py")


def sealed(value: dict) -> dict:
    """Content identity không phụ thuộc thứ tự keys hoặc dtype NumPy."""
    return {**safe(value), "sha256": digest(value)}


def checked(path: Path) -> dict:
    """Từ chối checkpoint/receipt bị sửa, không thay prediction để khớp diễn giải."""
    value = read_json(path)
    require(value.get("sha256") == digest({k: v for k, v in value.items() if k != "sha256"}), "Content hash sai: " + path.name)
    return value


def save_once(path: Path, value: Any) -> None:
    """Ghi atomic mới hoặc xác nhận nội dung y hệt sau interruption; không ghi đè evidence."""
    value = safe(value)
    if path.exists():
        require(read_json(path) == value, "Artifact đã có nhưng khác nội dung: " + path.name)
    else: write_json(path, value)


def runtime() -> dict:
    """Chỉ ghi phiên bản numeric đã khóa, không đọc credentials hoặc khởi tạo SDK."""
    return {"python": sys.version.split()[0], **{name: version(name) for name in ("numpy", "pandas", "scipy", "TA-Lib")}}


def verify_sources(root: Path, run: dict) -> None:
    """Guard source/runtime và toàn bộ queue frozen trước mỗi lần run/resume."""
    require(runtime() == run["runtime"], "Runtime khác freeze T13")
    for row in run["sources"]: require(sha256_file(root / row["path"]) == row["sha256"], "Source guard: " + row["path"])
    queue = read_json(root / RUN / "manifest.json")
    require(queue["sha256"] == run["queue_run_signature"], "Queue signature khác")
    for row in queue["sources"]: require(sha256_file(root / row["path"]) == row["sha256"], "Nguồn queue đổi: " + row["path"])


def prepare(root: Path, output: Path) -> dict:
    """Khóa code/test/runtime trước fit thật; không gọi feature/fit/predict trong prepare."""
    root, output = root.resolve(), output.resolve()
    require(output.is_relative_to(root / "outputs/revision") and output != root / "outputs/revision", "Output phải là release riêng")
    require(not output.exists(), "Release đã có; dùng run/check, không chuẩn bị lại")
    verify_release(root, root / DESIGN)
    design = read_json(root / DESIGN / "design.json"); validate_protocol(design["protocol"])
    sources = {root / DESIGN / name for name in ("manifest.json", "design.json", "summary.json")}
    sources.update(root / row["path"] for row in read_json(root / DESIGN / "manifest.json")["sources"])
    sources.update(root / name for name in (*NEW_SOURCES, "utils/statistical_tests.py", "core/revision_call_archive.py"))
    queue = read_json(root / RUN / "manifest.json")
    value = {"schema_version": "numeric_controls_run_v1", "created_utc": datetime.now(timezone.utc).isoformat(),
             "protocol_digest": design["protocol_digest"], "design_file_sha256": sha256_file(root / DESIGN / "design.json"),
             "runtime": runtime(), "queue_run_signature": queue["sha256"], "api_calls": 0,
             "scope_ids": [s["scope_id"] for s in design["scopes"]], "strategy_ids": design["strategy_ids"],
             "sources": [{"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)} for path in sorted(sources)]}
    run = sealed(value); verify_sources(root, run)
    output.mkdir(parents=True); save_once(output / "run.json", run)
    return run


def matrix_digest(values: np.ndarray, columns: list[str], dates: list[str]) -> str:
    """Hash content matrix tách khỏi ZIP container metadata và giữ undefined theo IEEE."""
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes() + digest({"columns": columns, "dates": dates}).encode()).hexdigest()


def feature_cache(root: Path, output: Path, run: dict, design: dict, symbol: str, frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Tái dùng feature snapshot đã hash; khôi phục cache gián đoạn bằng content oracle."""
    scopes = [s for s in design["scopes"] if s["symbol"] == symbol]
    endpoint = max(max(s["test_indices"]) for s in scopes)
    path = output / "features" / f"{symbol}.npz"; receipt_path = path.with_suffix(".json")
    context = {"run_signature": run["sha256"], "symbol": symbol, "last_decision": endpoint, "protocol_digest": design["protocol_digest"]}
    if receipt_path.exists():
        receipt = checked(receipt_path)
        require(receipt["context"] == context and sha256_file(path) == receipt["npz_sha256"], "Feature cache context/hash khác")
    else:
        features = causal_factors(frame, endpoint, design["protocol"])
        values = features.to_numpy(float); columns = list(features.columns); dates = frame["date"].iloc[:endpoint + 1].astype(str).tolist()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            with np.load(path, allow_pickle=False) as old:
                require(matrix_digest(old["values"], old["columns"].tolist(), old["dates"].tolist()) == matrix_digest(values, columns, dates), "Partial feature cache khác nguồn")
        else:
            temporary = path.with_suffix(".npz.tmp")
            with temporary.open("wb") as stream: np.savez_compressed(stream, values=values, columns=np.asarray(columns), dates=np.asarray(dates))
            temporary.replace(path)
        receipt = sealed({"context": context, "npz_sha256": sha256_file(path), "matrix_digest": matrix_digest(values, columns, dates)})
        save_once(receipt_path, receipt)
    with np.load(path, allow_pickle=False) as packed:
        values, columns, dates = packed["values"], packed["columns"].tolist(), packed["dates"].tolist()
    require(columns == design["candidate_ids"] and values.shape == (endpoint + 1, 85) and dates == frame["date"].iloc[:endpoint + 1].astype(str).tolist(), "Feature cache sai shape/dates/universe")
    require(matrix_digest(values, columns, dates) == receipt["matrix_digest"], "Feature content hash khác")
    return pd.DataFrame(values, columns=columns), receipt


def target_rows(frame: pd.DataFrame, indices: list[int], protocol: dict) -> list[dict]:
    """Đọc outcomes chỉ cho đánh giá sau khi fit train đã đóng, đúng Open-to-Close net L3."""
    index = np.asarray(indices, dtype=int); target = protocol["target"]
    entry, exit_ = index + 1, index + target["horizon_observed_sessions"]
    opening, closing = frame["Open"].to_numpy(float)[entry], frame["Close"].to_numpy(float)[exit_]
    require(np.isfinite(opening).all() and np.isfinite(closing).all() and (opening > 0).all() and (closing > 0).all(), "Target prices thiếu/không hợp lệ")
    net = closing / opening * (1 - target["fee_each_side"]) * (1 - target["slippage_each_side"]) / ((1 + target["fee_each_side"]) * (1 + target["slippage_each_side"])) - 1
    require(np.isfinite(net).all(), "Target net return không hữu hạn")
    return [{"decision": int(i), "date": str(frame["date"].iloc[i]), "entry": int(en), "exit": int(ex),
             "entry_date": str(frame["date"].iloc[en]), "exit_date": str(frame["date"].iloc[ex]),
             "label": int(value > 0), "net_return": float(value)} for i, en, ex, value in zip(index, entry, exit_, net)]


def scope_predictions(features: pd.DataFrame, frame: pd.DataFrame, scope: dict, fitted: dict, strategies: dict, protocol: dict) -> dict:
    """Đủ 23 variants cho validation/test, cùng fitted state; không chọn theo validation metrics."""
    before = digest(fitted); result = {}
    for role in ("validation", "test"):
        indices = scope[f"{role}_indices"]; matrix = features.iloc[indices]
        predictions = {name: predict_vote(matrix, fitted, spec["ids"], protocol, no_flip=spec["no_flip"]).tolist() for name, spec in strategies.items()}
        rows = target_rows(frame, indices, protocol)
        result[role] = [{**row, "actions": {name: values[position] for name, values in predictions.items()}} for position, row in enumerate(rows)]
    require(before == digest(fitted), "Prediction làm đổi fit state")
    return result


def validate_checkpoint(record: dict, features: pd.DataFrame, frame: pd.DataFrame, scope: dict, design: dict, run: dict, receipt: dict) -> None:
    """Resume chỉ nhận đúng scope/source/feature và prediction semantics; không refit checkpoint tốt."""
    require(record["context"] == {"run_signature": run["sha256"], "scope_digest": digest(scope), "feature_receipt_digest": receipt["sha256"]}, "Checkpoint context/parent khác")
    require(record["scope_id"] == scope["scope_id"] and record["fitted"]["train_rows"] == len(scope["train_indices"]), "Checkpoint sai scope/train support")
    expected_sets = strategy_sets(record["fitted"], scope["scope_id"], design["protocol"])
    require(expected_sets == record["strategies"] and set(expected_sets) == set(design["strategy_ids"]), "Checkpoint đổi strategy/seed/fit")
    expected = scope_predictions(features, frame, scope, record["fitted"], expected_sets, design["protocol"])
    require(expected == record["predictions"], "Checkpoint prediction/target khác recipe")


def evaluate_scope(features: pd.DataFrame, frame: pd.DataFrame, scope: dict, design: dict, run: dict, receipt: dict) -> dict:
    """Một fit train/scope, đóng state trước validation/test; không tái fit no-flip/random."""
    validate_scope(frame, scope, design["protocol"])
    fitted = fit_on_scope(features, frame, scope, design["protocol"])
    strategies = strategy_sets(fitted, scope["scope_id"], design["protocol"])
    require(set(strategies) == set(design["strategy_ids"]), "Thiếu strategy/seed")
    predictions = scope_predictions(features, frame, scope, fitted, strategies, design["protocol"])
    return sealed({"context": {"run_signature": run["sha256"], "scope_digest": digest(scope), "feature_receipt_digest": receipt["sha256"]},
                   "scope_id": scope["scope_id"], "fitted": fitted, "strategies": strategies, "predictions": predictions})


def common_test(records: list[dict], design: dict) -> tuple[list[dict], np.ndarray, np.ndarray]:
    """Common support đủ 102 units×23 strategies; thiếu/trùng không được lọc âm thầm."""
    by_scope = {r["scope_id"]: r for r in records}
    require(len(by_scope) == len(records) == len(design["scopes"]) and set(by_scope) == {s["scope_id"] for s in design["scopes"]}, "Thiếu/trùng scope")
    units = []
    for scope in design["scopes"]:
        rows = by_scope[scope["scope_id"]]["predictions"]["test"]
        require([r["decision"] for r in rows] == scope["test_indices"] and len(rows) == len(scope["test_units"]), "Test support khác design")
        for unit, row in zip(scope["test_units"], rows):
            require(unit["date"] == row["date"] and set(row["actions"]) == set(design["strategy_ids"]), "Unit/strategy mismatch")
            units.append({**unit, **row, "scope_id": scope["scope_id"]})
    units.sort(key=lambda u: (u["date"], u["symbol"], u["id"]))
    require(len({u["id"] for u in units}) == len(units) == design["protocol"]["scope"]["main_units"], "Common support thiếu/trùng unit")
    predicted = np.asarray([[u["actions"][name] for name in design["strategy_ids"]] for u in units])
    truth = np.asarray([u["label"] for u in units])
    require(predicted.shape == (len(units), 23) and np.isin(predicted, [0, 1]).all() and np.isin(truth, [0, 1]).all(), "Nonbinary/missing prediction")
    require(predicted.size == design["expected_predictions"], "Không đủ planned predictions")
    return units, truth, predicted


def classification_groups(units: list[dict], truth: np.ndarray, predicted: np.ndarray, strategies: list[str]) -> list[dict]:
    """Per-symbol/block/scope và pooled có cùng support giữa mọi strategy."""
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, unit in enumerate(units):
        for key in (("pooled", "ALL"), ("symbol", unit["symbol"]), ("block", unit["fold"]), ("scope", unit["scope_id"])): groups[key].append(index)
    return [{"level": level, "group": group, "strategy": strategy, "metrics": classification(truth[indices], predicted[indices, position])}
            for (level, group), indices in sorted(groups.items()) for position, strategy in enumerate(strategies)]


def account_results(units: list[dict], frames: dict[str, pd.DataFrame], strategies: list[str], protocol: dict) -> tuple[list[dict], list[dict]]:
    """Ledger cùng cycles/cost, báo riêng accounts khác khoảng lịch và giữ daily evidence."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for unit in units:
        groups[("symbol", unit["symbol"])].append(unit); groups[("scope", unit["scope_id"])].append(unit)
    accounts, daily = [], []
    for (level, group), points in sorted(groups.items()):
        points.sort(key=lambda u: u["decision"]); symbol = points[0]["symbol"]
        for strategy in strategies:
            cycles = [(u["entry"], u["exit"], int(u["actions"][strategy])) for u in points]
            ledger = daily_ledger(frames[symbol], cycles, protocol["target"])
            series = ledger.pop("daily")
            record = {"level": level, "group": group, "symbol": symbol, "strategy": strategy, "cycles": len(cycles), **ledger}
            accounts.append(record)
            if level == "symbol": daily.append({"group": group, "strategy": strategy, "daily": series})
    return accounts, daily


def summarize_random(metrics: list[dict], accounts: list[dict]) -> dict:
    """Giữ đủ trials và dispersion; không dùng random-family mean làm ensemble."""
    pooled = {r["strategy"]: r["metrics"] for r in metrics if r["level"] == "pooled"}
    account_map: dict[str, list[dict]] = defaultdict(list)
    for row in accounts:
        if row["level"] == "symbol": account_map[row["strategy"]].append(row)
    trials = []
    for seed in range(20):
        name = f"random_seed_{seed:02d}"
        trials.append({"seed": seed, "strategy": name, **{k: pooled[name][k] for k in ("balanced_accuracy", "mcc", "macro_f1", "accuracy", "long_rate")},
                       "mean_symbol_return_pct": describe([r["net_return_pct"] for r in account_map[name]])["mean"],
                       "mean_symbol_drawdown_pct": describe([r["daily_close_drawdown_pct"] for r in account_map[name]])["mean"]})
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in metrics:
        if row["strategy"].startswith("random_seed_"): groups[(row["level"], row["group"])].append(row)
    grouped = [{"level": level, "group": group, "metrics": {key: describe([r["metrics"][key] for r in rows])
                for key in ("balanced_accuracy", "mcc", "macro_f1", "accuracy", "long_rate")}} for (level, group), rows in sorted(groups.items())]
    return {"trials": trials, "pooled_trial_dispersion": {key: describe([r[key] for r in trials]) for key in trials[0] if key not in ("seed", "strategy")},
            "grouped_classification_dispersion": grouped, "selection": "Không best seed hoặc ensemble; n_defined/undefined giữ riêng cho mọi metric."}


def save_arrays(path: Path, arrays: dict[str, np.ndarray]) -> None:
    """Giữ nguyên NPZ đã có nếu mọi content array khớp; không so ZIP timestamps."""
    if path.exists():
        with np.load(path, allow_pickle=False) as old:
            require(set(old.files) == set(arrays), "Array artifact schema khác")
            for key, value in arrays.items():
                require(np.array_equal(old[key], value, equal_nan=True) if np.issubdtype(value.dtype, np.number) else np.array_equal(old[key], value), "Array artifact khác: " + key)
    else:
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("wb") as stream: np.savez_compressed(stream, **arrays)
        temporary.replace(path)


def finalize(root: Path, output: Path, run: dict, design: dict, records: list[dict], frames: dict[str, pd.DataFrame]) -> dict:
    """Chỉ tạo analysis complete sau đủ common support; inference đúng family đã khóa."""
    units, truth, predicted = common_test(records, design); strategies = design["strategy_ids"]; protocol = design["protocol"]
    metrics = classification_groups(units, truth, predicted, strategies)
    accounts, daily = account_results(units, frames, strategies, protocol)
    inference, arrays = paired_inference(truth, predicted, [u["fold"] for u in units], strategies, design["contrast_ids"],
        draws=protocol["inference"]["bootstrap"]["draws"], seed=protocol["inference"]["bootstrap"]["seed"])
    random = summarize_random(metrics, accounts)
    validation = [{"scope_id": r["scope_id"], "strategy": name,
        "metrics": classification([p["label"] for p in r["predictions"]["validation"]], [p["actions"][name] for p in r["predictions"]["validation"]])}
        for r in records for name in strategies]
    pooled = {r["strategy"]: r["metrics"] for r in metrics if r["level"] == "pooled"}
    headline = []
    for name in ("fixed_custom5", "dynamic_train_top5", "dynamic_train_top5_no_flip"):
        symbol_metrics = [r["metrics"] for r in metrics if r["level"] == "symbol" and r["strategy"] == name]
        symbol_accounts = [r for r in accounts if r["level"] == "symbol" and r["strategy"] == name]
        headline.append({"strategy": name, "pooled": pooled[name], "macro_symbol_BA": describe([r["balanced_accuracy"] for r in symbol_metrics]),
                         "mean_symbol_return_pct": describe([r["net_return_pct"] for r in symbol_accounts])["mean"]})
    summary = {"result": "PASS_EXPLORATORY_NUMERIC_CONTROLS", "main_units": len(units), "strategies": len(strategies), "test_predictions": int(predicted.size),
        "fit_scopes": len(records), "validation_prediction_memberships": sum(len(r["predictions"]["validation"]) * len(strategies) for r in records),
        "random_draws": sum(sum(k.startswith("random_seed_") for k in r["strategies"]) for r in records),
        "class_support": inference["class_support"], "protocol_digest": design["protocol_digest"], "api_calls": 0,
        "eligible_train_range": [min(len(r["fitted"]["eligible_ids"]) for r in records), max(len(r["fitted"]["eligible_ids"]) for r in records)],
        "fixed_inactive_slots": sum(len(r["strategies"]["fixed_custom5"]["inactive_ids"]) for r in records),
        "headline": headline, "random_family": random["pooled_trial_dispersion"],
        "primary_contrasts": [r for r in inference["contrasts"] if r["contrast"] in protocol["inference"]["primary_contrasts"]],
        "holm_rejections": sum(r["reject_holm_0_05"] is True for r in inference["contrasts"]),
        "limits": ["Historical exploratory, sáu blocks/12 dates phụ thuộc; p/CI chỉ diagnostic và mọi seed giữ nguyên.",
            "Dynamic train/mã/block khác native per-cutoff selector; numeric evidence không thay LLM ablation hoặc sửa causal gate T10.",
            "Mean symbol returns là bình quân accounts khác khoảng lịch, không market portfolio; ledger chưa xác nhận execution/settlement/corporate actions.",
            "Không chọn best seed/threshold/checkpoint, không suy accuracy hoặc thua ít hơn là alpha/profitability."]}
    for name, value in (("test_predictions.json", units), ("test_metrics.json", metrics), ("accounts.json", accounts),
                        ("validation_metrics.json", validation), ("random_dispersion.json", random), ("inference.json", inference), ("summary.json", summary)):
        save_once(output / name, value)
    save_arrays(output / "resampling.npz", arrays)
    encoded = json.dumps(safe(daily), ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ledger_path = output / "daily_ledgers.json.gz"
    if ledger_path.exists(): require(gzip.decompress(ledger_path.read_bytes()) == encoded, "Daily ledger evidence khác")
    else:
        temporary = ledger_path.with_suffix(".gz.tmp")
        with temporary.open("wb") as stream:
            with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as compressor: compressor.write(encoded)
        temporary.replace(ledger_path)
    verify_sources(root, run)
    paths = sorted(p for p in output.rglob("*") if p.is_file() and p.name != "manifest.json" and not p.name.endswith(".tmp"))
    manifest = {"schema_version": "numeric_controls_results_v1", "sources": run["sources"], "run_signature": run["sha256"],
                "protocol_digest": design["protocol_digest"], "frozen_source_hashes_checked_before_after": len(read_json(root / RUN / "manifest.json")["sources"]),
                "outputs": [{"path": p.relative_to(output).as_posix(), "sha256": sha256_file(p)} for p in paths]}
    save_once(output / "manifest.json", manifest)
    return summary


def run_controls(root: Path, output: Path) -> dict:
    """Run/resume offline, một OS lock riêng; không điều khiển worker API hoặc sửa nguồn frozen."""
    root, output = root.resolve(), output.resolve()
    require(output.is_relative_to(root / "outputs/revision"), "Output ngoài revision")
    run = checked(output / "run.json"); verify_sources(root, run)
    if (output / "manifest.json").exists():
        verify_release(root, output); return read_json(output / "summary.json")
    design = read_json(root / DESIGN / "design.json")
    require(design["protocol_digest"] == run["protocol_digest"] and sha256_file(root / DESIGN / "design.json") == run["design_file_sha256"], "Design đổi sau freeze")
    bank = read_json(root / BANK / "manifest.json")
    frames, _ = load_prices(root / bank["protocol"]["price_snapshot"], bank["protocol"]["price_quality_policy"])
    lock = root / "tmp" / ("numeric_controls_" + digest(output.relative_to(root).as_posix())[:16] + ".lock")
    records, cached = [], {}
    with StudyLock(lock):
        for index, scope in enumerate(design["scopes"], 1):
            symbol = scope["symbol"]
            if symbol not in cached: cached[symbol] = feature_cache(root, output, run, design, symbol, frames[symbol])
            features, receipt = cached[symbol]
            path = output / "scopes" / f"{symbol}_{scope['fold']}.json"
            try:
                if path.exists():
                    record = checked(path); validate_checkpoint(record, features, frames[symbol], scope, design, run, receipt)
                else:
                    record = evaluate_scope(features, frames[symbol], scope, design, run, receipt); save_once(path, record)
                records.append(record)
            except Exception as error:
                failure = sealed({"run_signature": run["sha256"], "failed_scope": scope["scope_id"], "completed_scopes": [r["scope_id"] for r in records],
                                  "error": f"{type(error).__name__}: {error}", "result": "INCOMPLETE_NO_FALLBACK"})
                save_once(output / f"failure_{index:02d}.json", failure)
                raise
            if index % 9 == 0 or index == len(design["scopes"]): print(f"T13: đã có {index}/{len(design['scopes'])} scope hợp lệ, không API.", flush=True)
        return finalize(root, output, run, design, records, frames)


def check_release(root: Path, output: Path) -> int:
    """Đối soát nguồn/đầu ra complete; giữ riêng prepare/incomplete với kết quả nghiệm thu."""
    run = checked(output / "run.json"); verify_sources(root, run)
    return verify_release(root, output)
