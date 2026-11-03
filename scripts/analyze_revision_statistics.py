"""Xuất D2-05 từ predictions đã khóa, không gọi API hay sửa annualisation engine."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import scipy

from core.revision_dependent_statistics import (METRICS, circular_weights, discordance,
    hac_summary, null_coverage, percentile_summary, score_samples, simulate_null_counts)
from core.revision_r3_repeats import array_metrics
from scripts.finalize_revision_r1 import table

ANALYSIS = ROOT / "outputs/revision/r1_72h_run_v2/analysis"
OUTPUT = ROOT / "outputs/revision/dependent_statistics_v1"
POLICY = ROOT / "revision/r5_statistics_policy.json"
VARIANTS = ("AS", "B", "constant_down_cash", "constant_up_cycles", "train_majority",
            "momentum_20", "factor_only_vote", "logistic_price", "logistic_matched_market_inputs")


def sha(path: Path) -> str:
    """Hash byte nguồn, không đổi line ending hoặc dữ liệu lịch sử."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Any:
    """Đọc JSON UTF-8 không đổi artifact."""
    return json.loads(path.read_bytes())


def json_text(value: Any) -> str:
    """Từ chối NaN/Infinity hoặc numpy scalar lọt vào JSON."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def csv_text(rows: list[dict]) -> str:
    """Xuất NA cho undefined; giữ nguyên denominator và đơn vị tỷ lệ 0--1."""
    buffer = io.StringIO(newline="")
    fields = list(dict.fromkeys(k for row in rows for k in row))
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows({k: "NA" if v is None else json.dumps(v) if isinstance(v, list) else v
                     for k, v in row.items()} for row in rows)
    return buffer.getvalue()


def load_panel() -> tuple[list[dict], list[Path]]:
    """Khóa pairing/schema của 102 units và chín classifiers từ manifest R1."""
    manifest = read(ANALYSIS / "manifest.json")
    required = ("predictions.csv", "block_intervals.json")
    for name in required:
        expected = next(r["sha256"] for r in manifest["outputs"] if r["path"] == name)
        if sha(ANALYSIS / name) != expected:
            raise ValueError("Input R1 đã đổi: " + name)
    with (ANALYSIS / "predictions.csv").open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    validate_panel(rows)
    return rows, [ANALYSIS / "manifest.json", *[ANALYSIS / n for n in required]]


def validate_panel(rows: list[dict]) -> None:
    """Từ chối duplicate, missing variant, ghép sai label hoặc input hash."""
    indexed = {(r["unit_id"], r["variant"]): r for r in rows}
    if len(indexed) != len(rows):
        raise ValueError("Prediction identity trùng")
    units = sorted({r["unit_id"] for r in rows})
    if len(units) != 102 or len(rows) != 918 or {r["variant"] for r in rows} != set(VARIANTS):
        raise ValueError("Panel không đủ 102 units/chín classifiers")
    for unit in units:
        matched = [indexed.get((unit, v)) for v in VARIANTS]
        if any(r is None for r in matched):
            raise ValueError("Thiếu paired variant")
        if any(r["prediction"] not in ("LONG", "SHORT") or r["label_net"] not in ("UP", "DOWN") for r in matched):
            raise ValueError("Prediction/label không hợp lệ")
        for field in ("symbol", "fold", "date", "label_net", "market_input_hash"):
            if len({r[field] for r in matched}) != 1:
                raise ValueError("Variants khác support/truth/input: " + field)
    if len({(r["date"], r["symbol"]) for r in rows}) != 102:
        raise ValueError("Ngày/mã bị nhân đôi dưới unit khác")


def cohort(rows: list[dict], name: str) -> dict:
    """Gom confusion theo block, giữ universe/mask và ngày thật trên đúng cohort."""
    selected = [r for r in rows if name == "all_102" or
                (name == "common_eight_96" and r["symbol"] != "BHN") or
                (name == "recent_nine_54" and r["fold"].startswith("f"))]
    units = sorted([r for r in selected if r["variant"] == "AS"], key=lambda r: (r["date"], r["symbol"]))
    expected = {"all_102": 102, "common_eight_96": 96, "recent_nine_54": 54}[name]
    if len(units) != expected:
        raise ValueError("Cohort sai support")
    blocks = sorted({r["fold"] for r in units}, key=lambda b: min(r["date"] for r in units if r["fold"] == b))
    indexed = {(r["unit_id"], r["variant"]): r for r in selected}
    y = np.asarray([r["label_net"] == "UP" for r in units])
    b = np.asarray([blocks.index(r["fold"]) for r in units])
    counts, predictions = [], []
    for variant in VARIANTS:
        p = np.asarray([indexed[(r["unit_id"], variant)]["prediction"] == "LONG" for r in units])
        cells = np.where(y, np.where(p, 0, 1), np.where(p, 3, 2))
        counts.append(np.bincount(b * 4 + cells, minlength=len(blocks) * 4).reshape(len(blocks), 4))
        predictions.append(p)
    return {"name": name, "units": units, "blocks": blocks, "truth": y,
            "predictions": np.asarray(predictions), "counts": np.asarray(counts)}


def legacy_diagnostics() -> tuple[list[dict], dict, list[Path]]:
    """Đối soát chín p-value lưu, báo 53 ngày riêng và không dựng pooled HAC."""
    frozen = ROOT / "outputs/revision/legacy_lineage_v1/manifest.json"
    records = [r for r in read(frozen)["sources"] if r["path"].startswith("outputs/backtest_result/") and r["path"].endswith(".json")]
    if len(records) != 9:
        raise ValueError("Legacy phải có đúng chín point artifacts")
    result, dates, all_y, all_f, all_b, paths = [], [], [], [], [], [frozen]
    for record in records:
        path = ROOT / record["path"]
        if sha(path) != record["sha256"]:
            raise ValueError("Artifact legacy đã đổi")
        paths.append(path)
        value = read(path)
        points = value["test_points"]
        if len(points) != 20 or [p["window_end"] for p in points] != sorted({p["window_end"] for p in points}):
            raise ValueError("Legacy thiếu hoặc trùng cutoff")
        y = np.asarray([p["actual_direction"] == "UP" for p in points])
        f = np.asarray([p["pred_full"] == "LONG" for p in points])
        b = np.asarray([p["pred_no_alpha"] == "LONG" for p in points])
        diagnostic = discordance(y, f, b)
        hac = hac_summary((f == y).astype(float) - (b == y), None)
        stored = value["newey_west_p_value"]
        if hac["p_value"] is not None and not np.isclose(hac["p_value"], stored, atol=1e-12, rtol=0):
            raise ValueError("NW legacy không tái lập: " + value["symbol"])
        result.append({"symbol": value["symbol"], **diagnostic, **{f"hac_{k}": v for k, v in hac.items()},
                       "full_accuracy": float((f == y).mean()), "base_accuracy": float((b == y).mean()),
                       "stored_nw_p_value": stored, "source_sha256": record["sha256"],
                       "first_cutoff": points[0]["window_end"], "last_cutoff": points[-1]["window_end"]})
        dates.append({p["window_end"] for p in points})
        all_y.extend(y.tolist()); all_f.extend(f.tolist()); all_b.extend(b.tolist())
    summary = {**discordance(np.asarray(all_y), np.asarray(all_f), np.asarray(all_b)),
               "n_symbols": 9, "n_per_symbol": 20, "n_distinct_dates": len(set.union(*dates)),
               "n_common_dates_all_symbols": len(set.intersection(*dates)),
               "full_pooled_accuracy": float(np.mean(np.asarray(all_f) == np.asarray(all_y))),
               "base_pooled_accuracy": float(np.mean(np.asarray(all_b) == np.asarray(all_y))),
               "full_equal_symbol_macro_accuracy": float(np.mean([r["full_accuracy"] for r in result])),
               "base_equal_symbol_macro_accuracy": float(np.mean([r["base_accuracy"] for r in result])),
               "pooled_hac": None, "pooled_hac_reason": "no fixed-nine-symbol common-date rectangle; rows are not a chronological pooled series"}
    return result, summary, paths


def generate(policy: dict) -> tuple[dict[str, str], list[Path]]:
    """Sinh mọi sensitivity đã khóa, không chọn length/cohort/p-value sau outcome."""
    rows, sources = load_panel()
    legacy, legacy_support, legacy_paths = legacy_diagnostics()
    sources += legacy_paths
    intervals, hac_rows, daily, supports = [], [], [], []
    for name in policy["cohorts"]:
        data = cohort(rows, name)
        units, blocks, counts = data["units"], data["blocks"], data["counts"]
        dates, symbols = sorted({u["date"] for u in units}), sorted({u["symbol"] for u in units})
        supports.append({"cohort": name, "n_units": len(units), "n_symbols": len(symbols), "n_dates": len(dates),
                         "n_blocks": len(blocks), "blocks_in_time_order": blocks,
                         "up": int(data["truth"].sum()), "down": int((~data["truth"]).sum())})
        point = array_metrics(counts.sum(axis=1))
        for length in policy["block_lengths"]:
            weights = circular_weights(len(blocks), length, policy["bootstrap_draws"], policy["seed"])
            samples = score_samples(counts, weights)
            for control_index, control in enumerate(VARIANTS[1:], 1):
                for metric in METRICS:
                    effect = point[metric][0] - point[metric][control_index]
                    intervals.append({"cohort": name, "contrast": f"AS-{control}", "metric": metric,
                        "n_units": len(units), "n_blocks": len(blocks), "block_length": length,
                        "chunks_per_draw": int(np.ceil(len(blocks) / length)),
                        "resampling_status": "degenerate_full_cohort" if length == len(blocks) else "descriptive_sensitivity",
                        "point_difference": float(effect) if np.isfinite(effect) else None,
                        **percentile_summary(samples[metric][0] - samples[metric][control_index])})
        if name == "all_102":
            continue
        # Hai cohort chữ nhật có trọng số cố định 1/S trên mọi ngày thật.
        matrix = ((data["predictions"][0] == data["truth"]).astype(float) -
                  (data["predictions"][1] == data["truth"]))
        if len(units) != len(dates) * len(symbols):
            raise ValueError("HAC fixed universe thiếu ngày/mã")
        series = matrix.reshape(len(dates), len(symbols)).mean(axis=1)
        for date, difference in zip(dates, series):
            daily.append({"cohort": name, "date": date, "n_symbols": len(symbols),
                          "weight_per_symbol": 1 / len(symbols), "accuracy_difference": float(difference)})
        for lag in policy["hac"]["lags"]:
            hac_rows.append({"cohort": name, "contrast": "AS-B", "metric": "accuracy",
                             "n_units": len(units), "n_symbols": len(symbols), **hac_summary(series, lag)})
    simulation = []
    config = policy["null_simulation"]
    if (config["dates"], config["symbols"], config["blocks"]) != (12, 9, 6):
        raise ValueError("Mô phỏng này chỉ hỗ trợ geometry 12 ngày/chín mã/sáu blocks đã khóa")
    for index, scenario in enumerate(config["scenarios"]):
        counts = simulate_null_counts(config["panels"], scenario["ar_phi"], scenario["common_variance_share"],
                                      policy["seed"] + index, config["up_probability"])
        for length in policy["block_lengths"]:
            weights = circular_weights(config["blocks"], length, config["bootstrap_draws"], policy["seed"] + 100)
            for result in null_coverage(counts, weights):
                simulation.append({**scenario, "block_length": length, **result})
        print(f"Đã mô phỏng null {scenario['name']}: {config['panels']} panels; giữ đủ lengths/metrics.", flush=True)
    report = {"scope": "D2-05 descriptive dependent statistics; annualisation and full R5 closure remain separate",
              "analysis_is_post_inference": True, "n_new_predictions": 0, "n_api_calls": 0,
              "legacy_support": legacy_support, "cohorts": supports,
              "primary_r1_intervals_unchanged": read(ANALYSIS / "block_intervals.json"),
              "bootstrap_row_count": len(intervals), "hac_row_count": len(hac_rows),
              "null_simulation_row_count": len(simulation),
              "monte_carlo_reference": "Wilson intervals condition on the fixed common bootstrap-weight bank; finite-bootstrap uncertainty is not additionally estimated",
              "repeat_evidence": "R3/R4 joint block x paired-execution intervals retained; simulations here do not certify their coverage",
              "limits": policy["claims"]}
    outputs = {"policy.json": json_text(policy), "report.json": json_text(report),
               "legacy_diagnostics.csv": csv_text(legacy), "panel_hac.csv": csv_text(hac_rows),
               "date_scores.csv": csv_text(daily), "block_sensitivity.json": json_text(intervals),
               "block_sensitivity.csv": csv_text(intervals), "null_coverage.csv": csv_text(simulation),
               "null_coverage.json": json_text(simulation)}
    outputs.update(tables(legacy, intervals, hac_rows, simulation))
    return outputs, sources


def number(value: float | None, scale: float = 1) -> str:
    """Định dạng bảng, giữ undefined là NA."""
    return "NA" if value is None else f"{value * scale:.3f}"


def tables(legacy: list[dict], intervals: list[dict], hac: list[dict], simulation: list[dict]) -> dict[str, str]:
    """Bảng mới độc lập cho D2-05, chưa chèn vào PDF release R4 đã khóa."""
    legacy_body = [" & ".join([r["symbol"], str(r["n"]), str(r["full_only_correct"]), str(r["base_only_correct"]),
        number(r["exact_p_value"]), number(r["hac_standard_error"], 100), str(r["hac_lag"]), number(r["hac_statistic"]), number(r["hac_p_value"])]) + r" \\" for r in legacy]
    sensitivity = []
    for r in intervals:
        if r["contrast"] != "AS-B":
            continue
        ci = r["percentile_95"]
        sensitivity.append(" & ".join([r["cohort"].replace("_", r"\_"), "BA" if r["metric"] == "balanced_accuracy" else "Acc.",
            str(r["block_length"]), number(r["point_difference"], 100),
            "NA" if ci is None else f"[{number(ci[0],100)}, {number(ci[1],100)}]",
            f"{r['n_defined']}/{r['n_draws']}"]) + r" \\")
    hac_body = [" & ".join([r["cohort"].replace("_", r"\_"), str(r["n_dates_or_cutoffs"]), str(r["lag"]),
        number(r["mean"], 100), number(r["standard_error"],100), number(r["statistic"]), number(r["p_value"])]) + r" \\" for r in hac]
    null_body = [" & ".join([r["name"].replace("_", r"\_"), "BA" if r["metric"] == "balanced_accuracy" else "Acc.",
        str(r["block_length"]), str(r["n_defined_panels"]), number(r["coverage_given_defined"],100),
        "NA" if r["monte_carlo_wilson_95"] is None else "[" + ", ".join(number(v,100) for v in r["monte_carlo_wilson_95"]) + "]"]) + r" \\" for r in simulation]
    note = "All additions are post-inference descriptive sensitivities; no superiority or calibrated-significance claim. Undefined values are NA."
    return {"legacy_discordance.tex": table("Legacy discordance and per-symbol HAC diagnostics.", "tab:d205_legacy", "lrrrrrrrr",
                r"Symbol & N & Full only & Base only & Exact $p$ & SE (pp) & Lag & $t$ & HAC $p$", legacy_body,
                "Exact McNemar assumes independent discordances. Nine symbols share market shocks and do not supply independent replications. Total N=180; 20 per symbol; 53 distinct cutoff dates and no date common to all nine. Zero variance has undefined HAC, not evidence for the null. " + note),
            "block_sensitivity.tex": table("Full--Base circular study-block sensitivity (percentage points).", "tab:d205_blocks", "llrrrr",
                "Cohort & Metric & Length & Difference & Interval & Finite draws", sensitivity,
                "Lengths count registered study blocks, not trading days. Dates, symbols, eligibility masks and variants remain paired. The length-three recent-cohort resample contains the complete three-block set and is degenerate. Frozen R1/R2 intervals remain primary; all eight contrasts are in the data release. " + note),
            "panel_hac.tex": table("Fixed-universe date-level Full--Base accuracy HAC sensitivity.", "tab:d205_hac", "lrrrrrr",
                r"Cohort & Dates & Lag & Difference (pp) & SE (pp) & $t$ & $p$", hac_body,
                "Each date averages symbols at fixed weights 1/8 or 1/9. HAC lags index selected dates with irregular gaps, not adjacent trading days; t references use dates minus one degrees of freedom. " + note),
            "null_coverage.tex": table("Stylized-null zero-coverage sensitivity (percent).", "tab:d205_null", "llrrrr",
                "Scenario & Metric & Length & Defined panels & Coverage & MC interval", null_body,
                "1,000 independent simulated panels per scenario and 1,000 paired bootstrap draws per panel/length. Intervals are Wilson Monte Carlo intervals, conditional on defined panels; machine-readable artifacts report every undefined draw. This is not validation of the market DGP or repeat-panel coverage. " + note)}


def main() -> None:
    """Khóa release riêng hoặc đối chiếu hash và tái lập nguyên byte ở process mới."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if OUTPUT.exists() and not args.check:
        raise FileExistsError("Release đã tồn tại; dùng --check")
    checked = 0
    if args.check:
        expected_runtime = read(OUTPUT / "manifest.json")["runtime"]
        if expected_runtime != {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__}:
            raise ValueError("Runtime khác release; không xác nhận tái lập trên phiên bản chưa kiểm")
        for group, base in (("sources", ROOT), ("outputs", OUTPUT)):
            for record in read(OUTPUT / "manifest.json")[group]:
                if sha(base / record["path"]) != record["sha256"]:
                    raise ValueError("Hash đã đổi: " + record["path"])
                checked += 1
    policy = read(POLICY)
    outputs, sources = generate(policy)
    for name, content in outputs.items():
        if args.check:
            if (OUTPUT / name).read_bytes() != content.encode("utf-8"):
                raise ValueError("Không tái lập: " + name)
        else:
            OUTPUT.mkdir(exist_ok=True)
            (OUTPUT / name).write_text(content, encoding="utf-8", newline="\n")
    if not args.check:
        sources += [POLICY, ROOT / "core/revision_dependent_statistics.py", Path(__file__).resolve(),
                    ROOT / "tests/test_revision_dependent_statistics.py", ROOT / "core/revision_r3_repeats.py",
                    ROOT / "utils/statistical_tests.py", ROOT / "scripts/finalize_revision_r1.py"]
        manifest = {"schema_version": "dependent_statistics_release_v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                    "runtime": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
                    "sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)} for p in sources],
                    "outputs": [{"path": name, "sha256": sha(OUTPUT / name)} for name in outputs]}
        (OUTPUT / "manifest.json").write_text(json_text(manifest), encoding="utf-8", newline="\n")
    print(f"PASS D2-05: {len(outputs)} artifacts; {checked} hashes khi kiểm lại; không gọi API.")


if __name__ == "__main__":
    main()
