"""Baseline cùng 102 units, phân tích paired/blocks và verifier không gọi API."""

from __future__ import annotations

from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from core.revision_audit import sha256_file
from core.revision_baselines import daily_ledger, factor_vote, load_prices, logistic_predictions, numerical_features
from core.revision_common_study import read_json, write_json
from core.revision72_run import checked, freeze
from core.revision72_provider import scientific_context
from scripts.evaluate_revision_baselines import csv_rows
from utils.statistical_tests import binary_classification_metrics


def target(frame: pd.DataFrame, indices: list[int], protocol: dict) -> tuple[np.ndarray, np.ndarray]:
    """Giữ net/gross riêng, không chuyển target sau khi đọc prediction."""
    indices = np.asarray(indices)
    ratio = frame["Close"].to_numpy(float)[indices + 3] / frame["Open"].to_numpy(float)[indices + 1]
    net = ratio * (1-protocol["fee_each_side"]) * (1-protocol["slippage_each_side"]) / (
        (1+protocol["fee_each_side"]) * (1+protocol["slippage_each_side"])) - 1
    return (net > 0).astype(int), (ratio > 1).astype(int)


def release_manifest(root: Path, output: Path, sources: list[Path]) -> None:
    """Khóa nguồn và mọi đầu ra đã ghi, không tự viết lại release."""
    write_json(output / "manifest.json", {
        "sources": [{"path": p.relative_to(root).as_posix(), "sha256": sha256_file(p)} for p in sources],
        "outputs": [{"path": p.relative_to(output).as_posix(), "sha256": sha256_file(p)} for p in sorted(output.rglob("*")) if p.is_file()]}, True)


def numeric(root: Path, bank: Path, run: Path) -> None:
    """Tái dùng predictions/fits cũ khi contract giữ nguyên; chỉ fit fold/input thay đổi."""
    output = bank / "numeric"
    if output.exists():
        raise FileExistsError("Numeric release đã tồn tại")
    manifest = read_json(bank / "manifest.json")
    protocol = manifest["protocol"]
    receipt = read_json(bank / "assets_complete.json")
    for artifact in receipt["files"]:
        if sha256_file(bank / artifact["path"]) != artifact["sha256"]:
            raise ValueError("Asset hash đã đổi")
    frames, _ = load_prices(root / protocol["price_snapshot"], protocol["price_quality_policy"])
    old = root / "outputs/revision/r1_common_numeric_v3"
    prior = pd.read_csv(old / "predictions.csv")
    prior_models = {(r["symbol"], r["fold"]): r for r in read_json(old / "models.json")}
    output.mkdir()
    (output / "daily").mkdir()
    predictions, summary, models, classes = [], [], [], []
    pooled = defaultdict(lambda: [[], []])
    numerical = {}
    for scope in manifest["schedule"]:
        symbol, fold = scope["symbol"], scope["fold"]
        frame = frames[symbol]
        if symbol not in numerical:
            numerical[symbol] = numerical_features(frame, [])
        causal, _, columns = numerical[symbol]
        xs = {role: pd.DataFrame([checked(bank / f"features/{symbol}_{i}.json")["features"] for i in scope[role]])
              for role in ("train", "validation", "test")}
        ty, _ = target(frame, scope["train"], protocol)
        vy, _ = target(frame, scope["validation"], protocol)
        sy, gross = target(frame, scope["test"], protocol)
        variants = {"constant_down_cash": np.zeros(2, int), "constant_up_cycles": np.ones(2, int),
            "train_majority": np.full(2, int(ty.mean() > .5)),
            "momentum_20": (causal["return_20"].iloc[scope["test"]].to_numpy() > 0).astype(int)}
        fitted = {}
        reused = (symbol, fold) in prior_models
        if reused:
            selected = prior.loc[(prior["symbol"] == symbol) & (prior["fold"] == fold) & (prior["variant"] == "logistic_price")].set_index("date")
            variants["logistic_price"] = np.array([int(selected.loc[str(frame["date"].iloc[i]), "prediction"] == "LONG") for i in scope["test"]])
            fitted["logistic_price"] = prior_models[(symbol, fold)]["models"]["logistic_price"]
            # Cùng OHLCV và train/validation; xác nhận các cột giá trước reuse.
            for role in ("train", "validation", "test"):
                for i in scope[role]:
                    previous = read_json(root / f"outputs/revision/r1_common_bank_v3/features/{symbol}_{i}.json")["features"]
                    current = checked(bank / f"features/{symbol}_{i}.json")["features"]
                    if {k: v for k, v in previous.items() if k.startswith("price_")} != {k: v for k, v in current.items() if k.startswith("price_")}:
                        raise ValueError("Không reuse price model khi input đổi")
        else:
            price = [c for c in xs["train"] if c.startswith("price_")]
            variants["logistic_price"], fitted["logistic_price"] = logistic_predictions(xs["train"][price], ty, xs["validation"][price], vy, xs["test"][price], protocol)
        variants["logistic_matched_market_inputs"], fitted["logistic_matched_market_inputs"] = logistic_predictions(
            xs["train"], ty, xs["validation"], vy, xs["test"], protocol)
        if reused:
            selected = prior.loc[(prior["symbol"] == symbol) & (prior["fold"] == fold) & (prior["variant"] == "factor_only_vote")].set_index("date")
            variants["factor_only_vote"] = np.array([int(selected.loc[str(frame["date"].iloc[i]), "prediction"] == "LONG") for i in scope["test"]])
            fitted["factor_only_vote"] = prior_models[(symbol, fold)]["models"]["factor_only_vote"]
        else:
            variants["factor_only_vote"], fitted["factor_only_vote"] = factor_vote(causal[columns].iloc[scope["train"]], ty, causal[columns].iloc[scope["test"]])
        models.append({"symbol": symbol, "fold": fold, "n_train": len(ty), "n_validation": len(vy),
            "reused_price_factor": reused, "matched_refit_reason": "new verified local sentiment/missingness inputs", "models": fitted})
        truth = np.where(sy, "UP", "DOWN")
        for name, values in variants.items():
            pred = np.where(values, "LONG", "SHORT")
            metrics = binary_classification_metrics(truth, pred)
            classes.append({"symbol": symbol, "fold": fold, "variant": name, "metrics": metrics})
            pooled[name][0].extend(truth.tolist()); pooled[name][1].extend(pred.tolist())
            ledger = daily_ledger(frame, [(i+1, i+3, int(a)) for i, a in zip(scope["test"], values)], protocol)
            csv_rows(output / f"daily/{symbol}_{fold}_{name}.csv", ledger.pop("daily"))
            summary.append({"symbol": symbol, "fold": fold, "variant": name, "n_test": 2, **ledger})
            for i, p, y, g in zip(scope["test"], pred, truth, gross):
                unit = next(u for u in manifest["units"] if u["symbol"] == symbol and u["fold"] == fold and u["decision"] == i)
                predictions.append({"unit_id": unit["id"], "symbol": symbol, "fold": fold, "date": unit["date"],
                    "variant": name, "prediction": str(p), "label_net": str(y), "label_gross": "UP" if g else "DOWN",
                    "market_input_hash": checked(bank / f"features/{symbol}_{i}.json")["market_input_hash"]})
        hold = daily_ledger(frame, [(scope["test"][0]+1, scope["test"][-1]+3, 1)], protocol)
        csv_rows(output / f"daily/{symbol}_{fold}_continuous_hold.csv", hold.pop("daily"))
        summary.append({"symbol": symbol, "fold": fold, "variant": "continuous_hold_price_only", "n_test": None, **hold})
    csv_rows(output / "predictions.csv", predictions)
    csv_rows(output / "summary.csv", summary)
    write_json(output / "classification.json", classes, True)
    gross = []
    for name in sorted({r["variant"] for r in predictions}):
        part = [r for r in predictions if r["variant"] == name]
        gross.append({"variant": name, "metrics": binary_classification_metrics([r["label_gross"] for r in part], [r["prediction"] for r in part]),
            "scope": "separate gross-return diagnostic; decisions were elicited for the fixed net target"})
    write_json(output / "gross_diagnostic.json", gross, True)
    write_json(output / "models.json", models, True)
    write_json(output / "report.json", {"profile": "revision_72h", "n_test": len(manifest["units"]), "n_blocks": len({u["fold"] for u in manifest["units"]}),
        "n_distinct_decision_dates": len({u["date"] for u in manifest["units"]}), "n_prediction_records": len(predictions),
        "n_daily_ledgers": len(summary), "pooled": {k: binary_classification_metrics(*v) for k, v in pooled.items()},
        "missing_variants": ["B", "AS"], "scope": "historical exploratory; source/news PIT and execution unverified; no alpha/profitability inference"}, True)
    release_manifest(root, output, [bank / "manifest.json", bank / "assets_complete.json", old / "manifest.json", old / "predictions.csv", old / "models.json", Path(__file__).resolve()])
    print(f"Numeric: {len(predictions)} predictions, {len(summary)} daily ledgers; không gọi API.")


def verify(root: Path, bank: Path, run: Path) -> list[dict]:
    """Kiểm hashes, lineage, raw decision replay và same-parent; không nhận checkpoint cũ."""
    from utils.decision_parser import parse_decision
    identity = freeze(root, bank, run)
    manifest = read_json(bank / "manifest.json")
    valid = []
    amendment_path=run/"execution_amendment.json"
    epoch=checked(amendment_path)["sha256"] if amendment_path.exists() else identity["sha256"]
    expected = {(j["unit_id"], j["realization"], d["variant"], d["repeat"]): j["org"]
                for j in identity["jobs"] for d in j["decisions"]}
    expected.update({(u["id"], 0, v, 0): u["org"] for u in manifest["smoke"] for v in ("B", "AS")})
    seen = set()
    for org in range(1, 6):
        shard = run / f"shards/org{org}"
        node_hashes = set()
        for path in (shard / "nodes").glob("*.json"):
            record = checked(path)
            if record["parent"]["run_signature"] != identity["sha256"]:
                raise ValueError("Node thuộc run khác")
            for artifact in record["call_hashes"]:
                if sha256_file(shard / artifact["path"]) != artifact["sha256"]:
                    raise ValueError("Raw node bị sửa")
            node_hashes.add(record["sha256"])
        for path in (shard / "decisions").glob("*.json"):
            record = checked(path)
            context = record["context"]
            key = (context["unit_id"], context["realization"], context["variant"], context["repeat"])
            if key in seen or expected.get(key) != org or record["prediction"] not in ("LONG", "SHORT"):
                raise ValueError("Decision trùng/khác shard/job hoặc prediction không hợp lệ")
            seen.add(key)
            unit = next(u for u in manifest["units"] + manifest["smoke"] if u["id"] == context["unit_id"])
            if record["parent"]["asset_hash"] != checked(bank / f"features/{unit['symbol']}_{unit['decision']}.json")["sha256"]:
                raise ValueError("Decision dùng input khác bank")
            if record["parent"]["run_signature"] != identity["sha256"] or not set(record["parent"]["node_hashes"]).issubset(node_hashes):
                raise ValueError("Decision lineage không hợp lệ")
            for artifact in record["call_hashes"]:
                if sha256_file(shard / artifact["path"]) != artifact["sha256"]:
                    raise ValueError("Raw decision bị sửa")
            if not record["request_ids"]:
                raise ValueError("Decision thiếu API response")
            raw = None
            for attempt in record["request_ids"]:
                req = checked(shard / f"calls/{attempt}.request.json")
                resp = read_json(shard / f"calls/{attempt}.response.json")
                if scientific_context(req["context"]) != scientific_context(record["context"]) or resp["parent_request_hash"] != req["sha256"]:
                    raise ValueError("Request/variant/response không khớp")
                if "provider_org" in req["context"] and (req["context"]["provider_org"] not in range(1,6) or req["context"].get("execution_epoch") != epoch):
                    raise ValueError("Routing metadata không khớp operational epoch đã khóa")
                raw = resp["response"]["generations"][0][0]["message"]
            text = raw.get("content", "")
            if not text:
                text = raw.get("additional_kwargs", {}).get("tool_calls", [{}])[0].get("function", {}).get("arguments", "")
            if parse_decision(text, lang="vi").get("decision") != record["prediction"]:
                raise ValueError("Prediction không replay được từ raw")
            valid.append(record)
    groups = defaultdict(dict)
    for record in valid:
        c = record["context"]
        groups[(c["unit_id"], c["realization"])][record["parent"]["upstream_hash"]] = True
    if any(len(v) != 1 for v in groups.values()):
        raise ValueError("Variants/repeats dùng upstream khác trong cùng realization")
    print(f"Integrity PASS: {len(valid)} decisions thật; chưa phải đóng R1.")
    return valid


def panel_summary(index: dict, unit_ids: list[str], variants: list[str], truth: dict, upstream: bool = False) -> dict:
    """Chỉ gộp support hoàn chỉnh của panel; không suy variance cho broad one-pass."""
    common = [u for u in unit_ids if all((u, r if upstream else 0, v, 0 if upstream else r) in index for r in range(3) for v in variants)]
    results = []
    for variant in variants:
        scores, predictions = [], []
        for repeat in range(3):
            pred = [index[(u, repeat if upstream else 0, variant, 0 if upstream else repeat)]["prediction"] for u in common]
            predictions.append(pred)
            scores.append(binary_classification_metrics([truth[u] for u in common], pred))
        dispersion = {}
        for metric in ("accuracy", "balanced_accuracy", "mcc", "macro_f1", "long_rate"):
            values = [r[metric] for r in scores]
            dispersion[metric] = None if not common or any(v is None for v in values) else {
                "mean": float(np.mean(values)), "sd": float(np.std(values, ddof=1)), "min": float(min(values)), "max": float(max(values))}
        disagreement = None if not common else float(np.mean([np.mean(np.asarray(predictions[a]) != np.asarray(predictions[b])) for a, b in ((0,1), (0,2), (1,2))]))
        results.append({"variant": variant, "by_repeat": scores, "dispersion": dispersion, "pairwise_disagreement": disagreement})
    contrasts = []
    pairs = (("AS", "B"), ("A", "B"), ("AS", "S"), ("AS", "A"), ("S", "B"), ("AS", "P"))
    for a, b in pairs:
        if a not in variants or b not in variants:
            continue
        left, right = next(r for r in results if r["variant"] == a), next(r for r in results if r["variant"] == b)
        delta = [None if x["balanced_accuracy"] is None or y["balanced_accuracy"] is None else x["balanced_accuracy"]-y["balanced_accuracy"] for x, y in zip(left["by_repeat"], right["by_repeat"])]
        contrasts.append({"contrast": f"{a}-{b}", "BA_delta_by_repeat": delta})
    return {"n_planned_units": len(unit_ids), "n_complete_common_units": len(common), "unit_ids": common,
        "results": results, "contrasts": contrasts, "scope": "panel-only three realizations; descriptive dispersion, not SD/CI of all 102 units"}


def system_costs(run: Path) -> dict:
    """Chi phí API quan sát được; token thiếu không điền bằng dự đoán hoặc giá hiện hành."""
    attempted = errors = successes = missing_usage = 0
    prompt = completion = 0
    latency, models, providers = [], Counter(), Counter()
    branch_attempts, branch_errors = Counter(), Counter()
    for shard in (run / "shards").glob("org*"):
        attempted += len(list((shard / "calls").glob("*.request.json")))
        errors += len(list((shard / "calls").glob("*.error.json")))
        for path in (shard / "calls").glob("*.request.json"):
            context = read_json(path)["context"]
            providers[int(context.get("provider_org",shard.name[3:]))] += 1
            branch = context.get("variant", "shared_" + context.get("node", "unknown"))
            branch_attempts[branch] += 1
            if path.with_name(path.name.replace(".request.", ".error.")).exists():
                branch_errors[branch] += 1
        for p in (shard / "calls").glob("*.response.json"):
            response = read_json(p); successes += 1
            output = response["response"].get("llm_output") or {}
            usage = output.get("token_usage")
            if usage:
                prompt += int(usage.get("prompt_tokens", 0)); completion += int(usage.get("completion_tokens", 0))
            else:
                missing_usage += 1
            models[output.get("model_name", "unreported")] += 1
            request = read_json(p.with_name(p.name.replace(".response.", ".request.")))
            latency.append((datetime.fromisoformat(response["ended_at_utc"])-datetime.fromisoformat(request["started_at_utc"])).total_seconds())
    return {"request_files": attempted, "successful_responses": successes, "errors": errors,
        "usage_unreported_responses": missing_usage, "observed_prompt_tokens": prompt, "observed_completion_tokens": completion,
        "latency_seconds_sum": float(sum(latency)), "latency_seconds_median": float(np.median(latency)) if latency else None,
        "models": dict(models), "attempts_by_provider_org":dict(providers), "failures_by_branch": {k: {"attempts": n, "errors": branch_errors[k],
            "error_fraction": branch_errors[k]/n} for k, n in branch_attempts.items()},
        "monetary_cost": None, "scope": "SDK-observed usage; excludes unknown usage on failed requests; not inferred billing"}


def block_interval(rows: list[dict], variants: tuple[str, str], seed: int = 20261102) -> dict:
    """Bootstrap joint cross-section theo sáu block, 10.000 lần, BA delta mô tả."""
    matrices = []
    for name in variants:
        blocks = []
        for block in sorted({r["fold"] for r in rows}):
            selected = [r for r in rows if r["variant"] == name and r["fold"] == block]
            metrics = binary_classification_metrics([r["label_net"] for r in selected], [r["prediction"] for r in selected])
            c = metrics["confusion"]
            blocks.append([c[k] for k in ("tp", "fn", "tn", "fp")])
        matrices.append(np.array(blocks))
    rng = np.random.default_rng(seed)
    weights = rng.multinomial(len(matrices[0]), np.full(len(matrices[0]), 1/len(matrices[0])), 10000)
    deltas = []
    with np.errstate(divide="ignore", invalid="ignore"):
        for matrix in matrices:
            c = weights @ matrix
            deltas.append((c[:, 0]/(c[:, 0]+c[:, 1]) + c[:, 2]/(c[:, 2]+c[:, 3]))/2)
    diff = deltas[0] - deltas[1]
    finite = diff[np.isfinite(diff)]
    return {"contrast": f"{variants[0]}-{variants[1]}", "n_blocks": len(matrices[0]), "n_resamples": 10000,
        "n_undefined": int(len(diff)-len(finite)), "percentile_95": np.quantile(finite, [.025, .975]).tolist() if len(finite) else None,
        "scope": "descriptive block bootstrap with few historical blocks; no independence/power or superiority guarantee"}


def analyze(root: Path, bank: Path, run: Path) -> None:
    """R1 tối thiểu cần 102 paired units; panel thiếu được báo, không giả complete."""
    records = verify(root, bank, run)
    manifest = read_json(bank / "manifest.json")
    identity = checked(run / "run_manifest.json")
    index = {(r["context"]["unit_id"], r["context"]["realization"], r["context"]["variant"], r["context"]["repeat"]): r
             for r in records if not r["context"]["smoke"]}
    if any((u["id"], 0, v, 0) not in index for u in manifest["units"] for v in ("B", "AS")):
        raise ValueError("Chưa đủ 102 cặp B/AS; không tạo bảng Full từ run thiếu")
    import time
    if len(index) < manifest["n_decisions"] and ((run / "execution_amendment.json").exists() or time.time() < identity["deadline_epoch"]):
        raise ValueError("Còn panel jobs trước T0+60h; resume inference trước khi khóa analysis release")
    output = run / "analysis"
    if output.exists():
        raise FileExistsError("Không ghi đè analysis release")
    frames, _ = load_prices(root / manifest["protocol"]["price_snapshot"], manifest["protocol"]["price_quality_policy"])
    numeric_rows = pd.read_csv(bank / "numeric/predictions.csv").to_dict("records")
    rows, summary, classes = list(numeric_rows), pd.read_csv(bank / "numeric/summary.csv").where(lambda x: x.notna(), None).to_dict("records"), []
    for row in rows:
        row.setdefault("market_input_hash", None)
    output.mkdir(); (output / "daily").mkdir()
    for scope in manifest["schedule"]:
        symbol, fold = scope["symbol"], scope["fold"]
        units = [u for u in manifest["units"] if u["symbol"] == symbol and u["fold"] == fold]
        frame = frames[symbol]
        truth, gross = target(frame, scope["test"], manifest["protocol"])
        for variant in ("B", "AS"):
            pred = [index[(u["id"], 0, variant, 0)]["prediction"] for u in units]
            for u, p, y, g in zip(units, pred, truth, gross):
                rows.append({"unit_id": u["id"], "symbol": symbol, "fold": fold, "date": u["date"], "variant": variant,
                    "prediction": p, "label_net": "UP" if y else "DOWN", "label_gross": "UP" if g else "DOWN",
                    "market_input_hash": checked(bank / f"features/{symbol}_{u['decision']}.json")["market_input_hash"]})
            ledger = daily_ledger(frame, [(i+1, i+3, int(p=="LONG")) for i, p in zip(scope["test"], pred)], manifest["protocol"])
            csv_rows(output / f"daily/{symbol}_{fold}_{variant}.csv", ledger.pop("daily"))
            summary.append({"symbol": symbol, "fold": fold, "variant": variant, "n_test": 2, **ledger})
    regimes = {}
    for unit in manifest["units"]:
        frame, i = frames[unit["symbol"]], unit["decision"]
        gap = float(frame["Close"].iloc[i] / frame["Close"].iloc[i-59:i+1].mean() - 1)
        regimes[unit["id"]] = "bull" if gap > .02 else "bear" if gap < -.02 else "sideways"
    for row in rows:
        row["regime"] = regimes[row["unit_id"]]
    for name in sorted({r["variant"] for r in rows}):
        selected = [r for r in rows if r["variant"] == name]
        for group in ("ALL", "symbol", "fold", "regime"):
            for value in (["ALL"] if group == "ALL" else sorted({r[group] for r in selected})):
                part = selected if group == "ALL" else [r for r in selected if r[group] == value]
                classes.append({"variant": name, "group": group, "value": value,
                    "metrics": binary_classification_metrics([r["label_net"] for r in part], [r["prediction"] for r in part])})
        common8 = [r for r in selected if r["symbol"] != "BHN"]
        classes.append({"variant": name, "group": "universe", "value": "eight_symbols_six_blocks",
            "metrics": binary_classification_metrics([r["label_net"] for r in common8], [r["prediction"] for r in common8])})
        newer = [r for r in selected if r["fold"].startswith("f")]
        classes.append({"variant": name, "group": "universe", "value": "nine_symbols_three_recent_folds",
            "metrics": binary_classification_metrics([r["label_net"] for r in newer], [r["prediction"] for r in newer])})
    for row in summary:
        part = [r for r in rows if (r["symbol"],r["fold"],r["variant"]) == (row["symbol"],row["fold"],row["variant"])]
        metrics = binary_classification_metrics([r["label_net"] for r in part], [r["prediction"] for r in part])
        row.update({k: metrics[k] if part else None for k in ("accuracy", "balanced_accuracy", "mcc", "macro_f1", "long_rate")})
        if not part: row["n_test"] = None
    csv_rows(output / "predictions.csv", rows)
    csv_rows(output / "economics.csv", summary)
    write_json(output / "classification.json", classes, True)
    gross_rows = [{"variant": name, "metrics": binary_classification_metrics(
        [r["label_gross"] for r in rows if r["variant"] == name], [r["prediction"] for r in rows if r["variant"] == name]),
        "scope": "separate gross diagnostic; predictions elicited for fixed net target"} for name in sorted({r["variant"] for r in rows})]
    write_json(output / "gross_diagnostic.json", gross_rows, True)
    macro = []
    for name in sorted({r["variant"] for r in rows}):
        records_by_symbol = [r["metrics"] for r in classes if r["variant"] == name and r["group"] == "symbol"]
        macro.append({"variant": name, "n_symbols": len(records_by_symbol), "metrics": {k: {
            "mean": float(np.mean([r[k] for r in records_by_symbol if r[k] is not None])) if any(r[k] is not None for r in records_by_symbol) else None,
            "n_defined": sum(r[k] is not None for r in records_by_symbol)} for k in ("accuracy", "balanced_accuracy", "mcc", "macro_f1", "long_rate")}})
    write_json(output / "macro_by_symbol.json", macro, True)
    contrasts = [block_interval(rows, ("AS", name)) for name in sorted({r["variant"] for r in rows}) if name != "AS"]
    write_json(output / "block_intervals.json", contrasts, True)
    actual = len(index)
    write_json(output / "report.json", {"n_paired_units": len(manifest["units"]), "required_research_decisions": manifest["n_decisions"],
        "actual_research_decisions": actual, "all_jobs_complete": actual == manifest["n_decisions"],
        "execution_epochs":dict(Counter(r.get("execution_epoch","original") for r in records if not r["context"]["smoke"])),
        "cross_epoch_main_pairs":sum(index[(u["id"],0,"B",0)].get("execution_epoch","original") != index[(u["id"],0,"AS",0)].get("execution_epoch","original") for u in manifest["units"]),
        "n_unique_decision_dates": len({u["date"] for u in manifest["units"]}),
        "status": "paired_R1_tables_ready_pending_manuscript_and_panel_review",
        "limitations": "historical exploratory; six blocks/roughly twelve dates, uncertain PIT news and model contamination; fractional immediate-cash ledger not certified settlement; no automatic R1 closure"}, True)
    write_json(output / "panel_records.json", [r for r in records if r["context"]["unit_id"] in manifest["panel"]], True)
    truth = {r["unit_id"]: r["label_net"] for r in rows}
    decision_panel = panel_summary(index, manifest["panel"], ["B","A","S","AS","P"] if manifest["gate"] == "factorial" else ["B","AS","P"], truth)
    upstream_panel = panel_summary(index, [u["id"] for u in manifest["units"] if u["upstream"]], ["B","AS"], truth, True)
    for name, panel in (("decision_panel.json", decision_panel), ("upstream_panel.json", upstream_panel)):
        support = [u for u in manifest["units"] if u["id"] in panel["unit_ids"]]
        panel.update({"n_dates": len({u["date"] for u in support}), "n_blocks": len({u["fold"] for u in support}),
                      "symbols": sorted({u["symbol"] for u in support})})
        write_json(output / name, panel, True)
    write_json(output / "system_costs.json", system_costs(run), True)
    # Bảng tự sinh để cập nhật manuscript sau review, không tự thay số liệu cũ.
    lines = [r"\begin{table}[htbp]", r"\centering", r"\caption{Common-snapshot paired comparison on 102 units (six historical blocks).}",
        r"\label{tab:revision-paired-baselines}", r"\begin{tabular}{lrrrrrr}", r"\hline",
        r"Variant & Accuracy & BA & MCC & Macro-F1 & LONG rate & Mean net return \\", r"\hline"]
    for record in [r for r in classes if r["group"] == "ALL"]:
        name, metrics = record["variant"], record["metrics"]
        mean_return = float(np.mean([r["net_return_pct"] for r in summary if r["variant"] == name]))
        values = ["NA" if metrics[k] is None else f"{metrics[k]*100:.2f}" for k in ("accuracy", "balanced_accuracy")]
        values += ["NA" if metrics["mcc"] is None else f"{metrics['mcc']:.3f}"]
        values += ["NA" if metrics[k] is None else f"{metrics[k]*100:.2f}" for k in ("macro_f1", "long_rate")]
        values += [f"{mean_return:.2f}"]
        lines.append(name.replace("_", r"\_") + " & " + " & ".join(values) + r" \\")
    lines += [r"\hline", r"\end{tabular}", r"\par\footnotesize Percentages except MCC. Mean return is over 51 symbol--block accounts, not a joint portfolio. Historical exploratory evidence; execution and news PIT are unverified.", r"\end{table}"]
    (output / "r1_baselines.tex").write_text("\n".join(lines)+"\n", encoding="utf8", newline="\n")
    sources = [run / "run_manifest.json", bank / "manifest.json", bank / "numeric/manifest.json"]
    if (run/"execution_amendment.json").exists():
        sources += [run/"execution_amendment.json",run/"runtime_history/original_sources.zip",run/"runtime_history/before_provider_only.json"]
    sources += [p for shard in (run / "shards").glob("org*") for folder in ("calls", "nodes", "decisions", "charts")
                for p in sorted((shard / folder).glob("*.json"))]
    release_manifest(root, output, sources)
    print("Đã xuất bảng paired R1; cần kiểm tra panels/claims và cập nhật manuscript/response.")
