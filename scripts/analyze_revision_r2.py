"""Xuất/kiểm audit R2 từ snapshot và inference R1 đã chốt, hoàn toàn offline."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import csv
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from core.revision_baselines import load_prices
from core.revision_common_study import native, read_json
from core.revision_r2_panel import (POLICY, audit_fold, audit_preprocessing, calendar_panel,
    classify_context, cohort_dependence, context_features, group_metrics)
from scripts.finalize_revision_r1 import fmt, table, validate

BANK = ROOT / "outputs/revision/r1_72h_bank_v2"
RUN = ROOT / "outputs/revision/r1_72h_run_v2"
ANALYSIS = RUN / "analysis"
R1_RELEASE = ROOT / "outputs/revision/r1_manuscript_v2"
OUTPUT = ROOT / "outputs/revision/r2_panel_v1"


def sha(path: Path) -> str:
    """Đọc hash byte nguyên bản."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_text(value: object) -> str:
    """Không đưa NaN/Infinity hoặc numpy scalar vào artifact."""
    return json.dumps(native(value), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def csv_text(records: list[dict]) -> str:
    """Giữ ô không xác định là NA và thứ tự cột ổn định."""
    handle = io.StringIO(newline="")
    fields = list(dict.fromkeys(k for r in records for k in r))
    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows({k: "NA" if native(v) is None else native(v) for k, v in r.items()} for r in records)
    return handle.getvalue()


def verify_closed_r1() -> None:
    """Đối chiếu nguồn R1 qua ZIP khi bản thảo/kế hoạch hiện hành đã chuyển sang R2."""
    manifest = read_json(R1_RELEASE / "manifest.json")
    with zipfile.ZipFile(R1_RELEASE / "sources.zip") as archive:
        for record in manifest["sources"]:
            path = ROOT / record["path"]
            if sha(path) != record["sha256"]:
                if hashlib.sha256(archive.read(record["path"])).hexdigest() != record["sha256"]:
                    raise ValueError("Nguồn R1 không khớp bản archive")
    for record in manifest["outputs"]:
        if sha(R1_RELEASE / record["path"]) != record["sha256"]:
            raise ValueError("Đầu ra R1 đã bị sửa")


def payloads() -> dict[str, str]:
    """Tính audit bằng inputs đã hash, không fit lại classifier hoặc sửa prediction."""
    verify_closed_r1()
    rows, _, _ = validate()
    bank = read_json(BANK / "manifest.json")
    protocol = bank["protocol"]
    frames, prices = load_prices(ROOT / protocol["price_snapshot"], protocol["price_quality_policy"])
    models = {(r["symbol"], r["fold"]): r for r in read_json(BANK / "numeric/models.json")}
    scopes = {(s["symbol"], s["fold"]): s for s in bank["schedule"]}
    features = {symbol: context_features(frame) for symbol, frame in frames.items()}
    folds = []
    for number, scope in enumerate(bank["schedule"], 1):
        record = audit_fold(frames[scope["symbol"]], scope, protocol)
        audit_preprocessing(BANK, scope, models[(scope["symbol"], scope["fold"])])
        record["stored_preprocessing_matches_purged_refit"] = True
        folds.append(record)
        if number % 9 == 0 or number == len(bank["schedule"]):
            print(f"Audit folds/preprocessing {number}/{len(bank['schedule'])}", flush=True)
    contexts, target_sessions = {}, []
    for unit in bank["units"]:
        symbol, decision = unit["symbol"], unit["decision"]
        scope = scopes[(symbol, unit["fold"])]
        context = {"unit_id": unit["id"], "symbol": symbol, "fold": unit["fold"], "date": unit["date"],
            "analysis_decision_index": decision,
            **classify_context(features[symbol], scope["train"], decision)}
        contexts[unit["id"]] = context
        for offset in (1, 2, 3):
            target_sessions.append({"unit_id": unit["id"], "symbol": symbol, "fold": unit["fold"],
                "decision_date": unit["date"], "target_date": str(frames[symbol]["date"].iloc[decision + offset]),
                "observed_session_offset": offset})
    original = {r["unit_id"]: r["regime"] for r in rows}
    if any(original[k] != v["trend"] for k, v in contexts.items()):
        raise ValueError("Trend rule không khớp R1; không đổi nhãn regime cũ")
    ledger_cache, exposure = {}, {}
    unit_index = {u["id"]: u for u in bank["units"]}
    for row in rows:
        key = (row["symbol"], row["fold"], row["variant"])
        if key not in ledger_cache:
            base = ANALYSIS if row["variant"] in ("B", "AS") else BANK / "numeric"
            ledger_cache[key] = pd.read_csv(base / f"daily/{key[0]}_{key[1]}_{key[2]}.csv").set_index("date")
        unit = unit_index[row["unit_id"]]
        dates = frames[unit["symbol"]]["date"].iloc[unit["decision"] + 1:unit["decision"] + 4].tolist()
        ledger = ledger_cache[key].loc[dates]
        held = int(ledger["held_during_session"].sum())
        closed = int(ledger["close_exposure"].sum())
        if held != 3 * int(row["prediction"] == "LONG") or closed != 2 * int(row["prediction"] == "LONG"):
            raise ValueError("Target-session exposure không khớp daily ledger")
        exposure[(row["unit_id"], row["variant"])] = {"dates": dates, "target_sessions": 3,
            "held_sessions": held, "close_sessions": closed}
    panel = calendar_panel(bank["units"], rows, sorted(frames))
    regimes = group_metrics(rows, contexts, exposure)
    dependence = cohort_dependence(rows)
    if dependence["cohorts"]["all_102"]["intervals"] != read_json(ANALYSIS / "block_intervals.json"):
        raise ValueError("Main block bootstrap không tái lập từ calendar panel")
    observed = sorted(set().union(*(set(frame["date"]) for frame in frames.values())))
    universe = []
    for symbol, frame in sorted(frames.items()):
        raw = pd.read_csv(ROOT / protocol["price_snapshot"] / f"{symbol}.csv")
        eligible = [u for u in bank["units"] if u["symbol"] == symbol]
        universe.append({"symbol": symbol, "n_raw_rows": len(raw), "raw_first_date": str(raw["date"].iloc[0]),
            "raw_last_date": str(raw["date"].iloc[-1]), "n_analysis_rows": len(frame),
            "analysis_first_date": str(frame["date"].iloc[0]), "n_excluded_prefix": len(raw) - len(frame),
            "zero_volume_rows_raw": int((raw["Volume"] == 0).sum()),
            "missing_from_observed_raw_union": len(set(observed) - set(raw["date"])),
            "n_llm_test_units": len(eligible), "n_llm_blocks": len({u["fold"] for u in eligible}),
            "listing_delisting_status": "unverified; no point-in-time constituent/delisted universe recovered",
            "suspension_status": "unknown; zero volume or absent row is not independently certified suspension",
            "selection_scope": "legacy purposive/surviving nine-symbol sample, not a random or market-wide universe"})
    identity = read_json(RUN / "run_manifest.json")
    requests = [read_json(p) for p in RUN.glob("shards/org*/calls/*.request.json")]
    responses = [read_json(p) for p in RUN.glob("shards/org*/calls/*.response.json")]
    starts = sorted(r["started_at_utc"] for r in requests)
    model_names, fingerprints = Counter(), set()
    for response in responses:
        output = response["response"].get("llm_output") or {}
        model_names[str(output.get("model_name", "unreported"))] += 1
        if output.get("system_fingerprint"):
            fingerprints.add(str(output["system_fingerprint"]))
    last_exit = max(f["last_test_label_date"] for f in folds)
    contamination = {"scope": "historical exploratory, not prospective or contamination-free",
        "protocol_freeze_utc": identity["t0_utc"], "first_archived_request_utc": starts[0],
        "last_archived_request_utc": starts[-1], "last_test_label_date": last_exit,
        "n_units_after_protocol_freeze": sum(u["date"] > identity["t0_utc"][:10] for u in bank["units"]),
        "n_labels_maturing_after_protocol_freeze": sum(r["target_date"] > identity["t0_utc"][:10] for r in target_sessions if r["observed_session_offset"] == 3),
        "observed_response_model_names": dict(sorted(model_names.items())),
        "reported_system_fingerprints": sorted(fingerprints),
        "immutable_served_weight_revision": "unverified",
        "training_corpus_or_cutoff_authenticated_for_served_text_and_vision_weights": "unknown",
        "release_date_establishes_cleanliness": False,
        "interpretation": "Model release dates/temperature and request fingerprints do not certify training corpus exclusion. Multi-year historical points may be memorised by either served model; no point is claimed an untouched prospective holdout.",
        "input_provenance_limits": "retrieved OHLCV and cached news are retrospective; price adjustments, publication/content availability and universe membership remain unverified",
        "future_holdout": "requires a separately frozen protocol/model identity and genuinely later matured outcomes; no retrospective relabelling"}
    assert last_exit < identity["t0_utc"][:10]
    coverage = []
    for fold in sorted({u["fold"] for u in bank["units"]}, key=lambda f: min(u["date"] for u in bank["units"] if u["fold"] == f)):
        selected = [r for r in rows if r["fold"] == fold and r["variant"] == "AS"]
        ids = {r["unit_id"] for r in selected}
        coverage.append({"fold": fold, "n_units": len(ids), "n_symbols": len({r["symbol"] for r in selected}),
            "decision_dates": sorted({r["date"] for r in selected}),
            "n_target_calendar_dates": len({r["target_date"] for r in target_sessions if r["unit_id"] in ids}),
            "up": sum(r["label_net"] == "UP" for r in selected),
            "down": sum(r["label_net"] == "DOWN" for r in selected),
            "trend_counts": dict(Counter(contexts[u]["trend"] for u in ids)),
            "AS_LONG": sum(r["prediction"] == "LONG" for r in selected),
            "B_LONG": sum(r["prediction"] == "LONG" for r in rows if r["fold"] == fold and r["variant"] == "B")})
    summary = {"n_units": len(bank["units"]), "n_symbols": len(frames), "n_blocks": len(coverage),
        "n_decision_dates": panel["date"].nunique(), "n_target_calendar_dates": len({r["target_date"] for r in target_sessions}),
        "n_target_symbol_sessions": len(target_sessions), "full_date_symbol_slots": len(panel) // 9,
        "eligible_date_symbol_slots": int(panel["eligible"].sum()) // 9,
        "missing_date_symbol_slots": int((~panel["eligible"]).sum()) // 9,
        "n_panel_rows_all_variants": len(panel), "n_missing_panel_rows": int((~panel["eligible"]).sum()),
        "first_decision_date": min(u["date"] for u in bank["units"]),
        "last_decision_date": max(u["date"] for u in bank["units"]),
        "coverage": coverage, "independence": POLICY["independence"],
        "fold_audit": "51 purged outer symbol/fold scopes; stored preprocessing checked against train+validation only; no classifier refit",
        "selector_scope": "LLM uses frozen causal 600-session native selector at each cutoff; its diagnostics are not nested factor-discovery inference (R10 remains separate)",
        "universe_limitation": "eight-symbol/six-block and nine-symbol/three-block cohorts overlap and must not be pooled",
        "status": "R2_evidence_ready_pending_manuscript_review"}
    exposed = [{k: v for k, v in r.items() if k != "metrics"} | {"n_up": r["metrics"]["per_class"]["UP"]["support"],
        "n_down": r["metrics"]["per_class"]["DOWN"]["support"], "decision_long_rate": r["metrics"]["long_rate"]} for r in regimes]
    result = {"protocol.json": json_text(POLICY), "data_manifest.json": json_text({"snapshot": prices, "universe": universe}),
        "folds.csv": csv_text(folds), "regime_labels.csv": csv_text(list(contexts.values())),
        "prediction_panel.csv": csv_text(panel.to_dict("records")), "target_sessions.csv": csv_text(target_sessions),
        "stratified_metrics.json": json_text(regimes), "exposure_by_regime.csv": csv_text(exposed),
        "dependence.json": json_text(dependence), "contamination.json": json_text(contamination),
        "report.json": json_text(summary)}
    result.update(tex_tables(summary, folds, regimes, dependence))
    return result


def tex_tables(summary: dict, folds: list[dict], regimes: list[dict], dependence: dict) -> dict[str, str]:
    """Tạo bảng phụ lục từ đúng audit đã tính, không chọn regime theo outcome."""
    body = []
    for r in summary["coverage"]:
        dates = "/".join(x[5:] for x in r["decision_dates"])
        trends = "/".join(str(r["trend_counts"].get(t, 0)) for t in ("bull", "bear", "sideways"))
        body.append(" & ".join([r["fold"].replace("_", r"\_"), dates, str(r["n_symbols"]), str(r["n_units"]),
            f"{r['up']}/{r['down']}", trends, str(r["AS_LONG"]), str(r["B_LONG"])]) + r" \\")
    result = {"r2_coverage.tex": table("Temporal support of the fixed R1 prediction bank.", "tab:r2_coverage", "llrrrrrr",
        "Block & Dates (MM-DD) & Symbols & N & UP/DOWN & Bull/Bear/Side & LONG AS & LONG B", body,
        "Each block has two decision dates and six distinct target-session dates. The first three omit BHN for the frozen valid-suffix/warm-up rule. Totals: 102 units, 12 decision dates, 36 target-session calendar dates; none is asserted statistically independent.")}
    body = []
    for dimension, name in (("trend", "Trend"), ("volatility", "Volatility"), ("liquidity_proxy", "Turnover proxy")):
        values = sorted({r["stratum"] for r in regimes if r["dimension"] == dimension})
        for value in values:
            part = {r["variant"]: r for r in regimes if r["dimension"] == dimension and r["stratum"] == value}
            full, base, price = (part[v] for v in ("AS", "B", "logistic_price"))
            m = full["metrics"]
            body.append(" & ".join([name, value, str(full["n_units"]), str(full["n_dates"]),
                str(m["per_class"]["UP"]["support"]), fmt(m["balanced_accuracy"]), fmt(base["metrics"]["balanced_accuracy"]),
                fmt(price["metrics"]["balanced_accuracy"]), fmt(m["long_rate"])]) + r" \\")
    result["r2_regimes.tex"] = table("Causal context strata on the same predictions (percentages except counts).", "tab:r2_regimes", "llrrrrrrr",
        "Dimension & Stratum & N & Dates & UP & BA AS & BA B & BA price & LONG AS", body,
        "Trend uses the frozen close/SMA60 rule. Volatility and turnover-proxy high/low thresholds are symbol/fold train-only medians; these two dimensions are post-inference descriptive additions. Dates overlap across strata. Turnover proxy is not order-book liquidity; no regime-dependent strategy is fitted.")
    body = []
    for key, label in (("all_102", "All available"), ("eight_symbols_six_blocks", "Eight symbols"), ("nine_symbols_three_recent_blocks", "Nine recent")):
        r = dependence["cohorts"][key]
        interval = next(v for v in r["intervals"] if v["contrast"] == "AS-B")["percentile_95"]
        delta = r["metrics"]["AS"]["balanced_accuracy"] - r["metrics"]["B"]["balanced_accuracy"]
        body.append(" & ".join([label, str(r["n_units"]), str(r["n_blocks"]), str(r["n_dates"]),
            fmt(r["metrics"]["AS"]["balanced_accuracy"]), fmt(r["metrics"]["B"]["balanced_accuracy"]),
            f"{delta*100:.2f}", f"[{interval[0]*100:.2f}, {interval[1]*100:.2f}]"]) + r" \\")
    result["r2_dependence.tex"] = table("Coverage-cohort sensitivity with synchronized whole-block resampling.", "tab:r2_dependence", "lrrrrrrr",
        "Cohort & N & Blocks & Dates & BA AS & BA B & Delta (pp) & 95\\% interval (pp)", body,
        "10,000 descriptive resamples, seed 20261102. Every selected block retains its full cross-section, both dates, all variants and missing eligibility mask. Cohorts overlap; three or six blocks are too few for a precision or general-superiority claim.")
    body = []
    for c in summary["coverage"]:
        part = [r for r in folds if r["fold"] == c["fold"]]
        body.append(" & ".join([c["fold"].replace("_", r"\_"), str(len(part)),
            f"{min(r['n_train'] for r in part)}--{max(r['n_train'] for r in part)}",
            f"{min(r['n_validation'] for r in part)}--{max(r['n_validation'] for r in part)}",
            str(min(r["warmup_available_at_first_train"] for r in part)), "PASS", "PASS"]) + r" \\")
    result["r2_folds.tex"] = table("Audit of the frozen chronological outer folds and inner validation.", "tab:r2_folds", "lrrrrll",
        "Block & Symbol scopes & Train range & Validation range & Warm-up & Purge & Refit stats", body,
        "Warm-up counts available observed sessions at the first train cutoff. All 51 scopes have label exits strictly before the next split. Stored imputation/scaling statistics reproduce from train plus matured validation; classifiers are not refitted. Exact split dates/counts are in folds.csv.")
    return result


def sources() -> list[Path]:
    """Khóa code audit và các manifest/source nguyên bản; bản thảo có release riêng."""
    return [ROOT / p for p in ["core/revision_r2_panel.py", "scripts/analyze_revision_r2.py", "tests/test_revision_r2_leakage.py",
        "scripts/finalize_revision_r1.py", "core/revision_baselines.py", "core/revision72_analysis.py",
        "core/revision_common_study.py", "utils/statistical_tests.py",
        "outputs/revision/r1_prices_v1/manifest.json", "outputs/revision/r1_72h_bank_v2/manifest.json",
        "outputs/revision/r1_72h_bank_v2/numeric/manifest.json", "outputs/revision/r1_72h_bank_v2/numeric/models.json",
        "outputs/revision/r1_72h_run_v2/run_manifest.json", "outputs/revision/r1_72h_run_v2/analysis/manifest.json",
        "outputs/revision/r1_manuscript_v2/manifest.json", "outputs/revision/r1_manuscript_v2/sources.zip"]]


def main() -> None:
    """Tạo release mới hoặc đối soát nguyên bản mà không ghi đè artifact đã khóa."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if OUTPUT.exists() and not args.check:
        raise FileExistsError("R2 release đã tồn tại; dùng --check, không ghi đè")
    if args.check:
        manifest = read_json(OUTPUT / "manifest.json")
        for r in manifest["sources"]:
            if sha(ROOT / r["path"]) != r["sha256"]:
                raise ValueError("Nguồn R2 đã đổi: " + r["path"])
        for r in manifest["outputs"]:
            if sha(OUTPUT / r["path"]) != r["sha256"]:
                raise ValueError("Artifact R2 đã đổi: " + r["path"])
    generated = payloads()
    for name, text in generated.items():
        if args.check:
            if (OUTPUT / name).read_bytes() != text.encode("utf-8"):
                raise ValueError("Audit không tái lập: " + name)
        else:
            OUTPUT.mkdir(exist_ok=True)
            (OUTPUT / name).write_text(text, encoding="utf-8", newline="\n")
        if name.endswith(".tex"):
            path = ROOT / "paper/generated" / name
            if args.check:
                if path.read_bytes() != text.encode("utf-8"):
                    raise ValueError("Bảng không khớp audit: " + name)
            else:
                path.write_text(text, encoding="utf-8", newline="\n")
    if not args.check:
        manifest = {"schema_version": "revision_r2_panel_release_v1", "scope": POLICY["scope"],
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)} for p in sources()],
            "outputs": [{"path": name, "sha256": sha(OUTPUT / name)} for name in generated]}
        (OUTPUT / "manifest.json").write_text(json_text(manifest), encoding="utf-8", newline="\n")
    print(f"PASS: R2 {'tái lập' if args.check else 'đã xuất'} {len(generated)} artifacts; không gọi API.")


if __name__ == "__main__":
    main()
