"""Dựng và cold audit dataset v4; readiness dữ liệu tách khỏi PASS kỹ thuật."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import timedelta, date
import json
from pathlib import Path
from typing import Any

import numpy as np

from core.execution_prices import load_verified_execution_data
from core.mt_bicl_v4_data import NUMERIC, bounded_index, fit_scaler, membership, symbol_data
from core.mt_bicl_v4_data_regimes import DataRegimes
from core.mt_bicl_v4_lineage import CATEGORIES, agent_row, envelope, inventory
from core.mt_bicl_v4_protocol import (canonical, checksum, fit_eligible, git, read,
                                    safe_path, validate_protocol, verify as verify_protocol, PROTOCOL)

OUTPUT = Path("outputs/bayesian_benchmark/mt_bicl_v4/data")
MANIFEST = Path("docs/plan/week11/dataset_manifest_v4.json")
COVERAGE = Path("docs/plan/week11/coverage_v4.json")
SOURCES = ("core/mt_bicl_v4_data.py", "core/mt_bicl_v4_lineage.py",
    "core/mt_bicl_v4_data_regimes.py", "core/mt_bicl_v4_dataset.py",
    "scripts/prepare_mt_bicl_v4_data.py", "tests/mt_bicl_v4_data_support.py",
    "tests/test_mt_bicl_v4_data.py", "tests/test_mt_bicl_v4_data_leakage.py")


def encoded(value: Any) -> bytes:
    """JSON UTF-8 xác định và không cho NumPy/NaN lọt ra artifact."""
    canonical(value)
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def immutable(path: Path, value: Any, *, verify_only: bool = False) -> None:
    """Không sửa snapshot cũ hoặc tự reseal khi input khác; write mới theo file nguyên tử."""
    data = encoded(value)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("Artifact khác cold rebuild, cần revision: " + path.name)
    elif verify_only:
        raise ValueError("Thiếu artifact đã khóa: " + path.name)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            import os
            os.fsync(stream.fileno())
        temporary.replace(path)


def data_source(root: Path, commit: str | None = None) -> tuple[str, dict[str, str]]:
    """Source dataset độc lập source spec; phải đã commit và trùng byte Git."""
    actual = git(root, "log", "-1", "--format=%H", "--", *SOURCES).decode().strip()
    if commit is not None and actual != commit:
        raise ValueError("Source dataset đã đổi sau snapshot")
    files = {}
    for name in SOURCES:
        data = (root / name).read_bytes()
        if data != git(root, "show", actual + ":" + name):
            raise ValueError("Source dataset chưa commit: " + name)
        files[name] = checksum(data)
    return actual, files


def fold_views(rows: list[dict[str, Any]], spec: dict[str, Any], regimes: DataRegimes) -> dict[str, Any]:
    """Purge fit labels, scaler/regime đúng từng fold; query/context giữ label riêng."""
    definitions = {}
    for outer in spec["folds"]:
        definitions["outer_" + outer["id"]] = {k: outer[k] for k in ("fit_end", "evaluation_start", "evaluation_end")}
        for inner in outer["inner"]:
            definitions["inner_" + inner["id"]] = {k: inner[k] for k in ("fit_end", "evaluation_start", "evaluation_end")}
    by_cap = {}
    views = {}
    for identifier, definition in sorted(definitions.items()):
        cap = definition["fit_end"]
        if cap not in by_cap:
            by_cap[cap] = regimes.view(rows, cap)
        scaler = fit_scaler(rows, cap)
        fit = [r for r in rows if r["label_eligible"] and fit_eligible(r["entry_date"], r["exit_date"], cap,
                            definition["evaluation_start"], definition["evaluation_end"])]
        queries = [r for r in rows if definition["evaluation_start"] <= r["as_of_date"] <= definition["evaluation_end"]]
        members = [membership(row, rows, scaler, by_cap[cap]) for row in queries]
        views[identifier] = {**definition, "fit_ids": [r["episode_id"] for r in fit],
            "evaluation_ids": [r["episode_id"] for r in queries], "scaler": scaler,
            "memberships": members, "regimes": {r["episode_id"]: by_cap[cap][r["episode_id"]]
                for r in rows if r["as_of_date"] <= definition["evaluation_end"]}}
        print(f"Đã dựng fold {identifier}: fit{len(fit)}, query{len(queries)}; chưa fit predictor/API.", flush=True)
    return views


def train_views(rows: list[dict[str, Any]], regimes: DataRegimes) -> dict[str, Any]:
    """Scalers train prefix theo ngày; không dùng scaler cuối2020 cho query2018/2019."""
    train = [r for r in rows if r["as_of_date"] <= "2020-12-31"]
    states = regimes.view(rows, "2020-12-31")
    scalers, contexts = {}, []
    for row in train:
        query = row["as_of_date"]
        if query not in scalers:
            cap = (date.fromisoformat(query) - timedelta(days=1)).isoformat()
            scalers[query] = fit_scaler(rows, cap, query=query)
        contexts.append(membership(row, rows, scalers[query], states))
    return {"scalers_by_query_date": scalers, "memberships": contexts,
            "regimes": {r["episode_id"]: states[r["episode_id"]] for r in train}}


def coverage(rows: list[dict[str, Any]], folds: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Readiness chỉ theo support/lineage; không tính payoff/accuracy để sửa thiết kế."""
    by_id = {r["episode_id"]: r for r in rows}
    failures, groups = [], {}
    minimum = spec["data"]["minimum_support"]

    def counts(group: list[dict[str, Any]]) -> dict[str, Any]:
        labeled = [r for r in group if r["label_eligible"]]
        valid = [r for r in labeled if r["features"]["status"] == "AVAILABLE"]
        agent = [r for r in valid if r["agent"]["status"] == "AVAILABLE"]
        tasks = Counter(r["task_id"] for r in labeled)
        return {"grid_queries": len(group), "labeled": len(labeled), "numeric_valid": len(valid),
                "agent_valid": len(agent), "agent_valid_fraction": len(agent) / len(labeled) if labeled else 0.,
                "tasks_with_two_cycles": sum(n >= 2 for n in tasks.values()),
                "real_legacy_reports": sum(r["agent"]["source"] is not None for r in group),
                "alpha_warmup_lt600": sum(r["alpha_history_rows"] < 600 for r in group),
                "feature_reasons": dict(sorted(Counter(reason for r in group for reason in r["features"]["reasons"]).items())),
                "agent_reasons": dict(sorted(Counter(reason for r in group for reason in r["agent"]["reasons"]).items())),
                "label_reasons": dict(sorted(Counter(reason for r in group for reason in r["label_reasons"]).items()))}

    for identifier, fold in folds.items():
        groups[identifier] = {}
        for symbol in spec["data"]["symbols"]:
            fit = [by_id[i] for i in fold["fit_ids"] if by_id[i]["symbol"] == symbol]
            queries = [by_id[i] for i in fold["evaluation_ids"] if by_id[i]["symbol"] == symbol]
            f, q = counts(fit), counts(queries)
            inner = identifier.startswith("inner_")
            required = {"fit_labeled": minimum["inner_train_labeled_cycles_per_symbol"] if inner else minimum["train_labeled_cycles_per_symbol"],
                        "fit_tasks": minimum["inner_train_tasks_per_symbol"] if inner else minimum["train_tasks_with_two_cycles_per_symbol"],
                        "fit_agent": minimum["inner_agent_valid_train_cycles_per_symbol"] if inner else minimum["agent_valid_train_cycles_per_symbol"]}
            checks = {"fit_labeled": f["labeled"] >= required["fit_labeled"],
                      "fit_tasks": f["tasks_with_two_cycles"] >= required["fit_tasks"],
                      "fit_agent": f["agent_valid"] >= required["fit_agent"]}
            if not inner:
                checks.update(eval_labeled=q["labeled"] >= minimum["outer_labeled_cycles_per_symbol"],
                    eval_agent_fraction=q["agent_valid_fraction"] >= minimum["agent_valid_fraction_each_outer_symbol"])
            for check, passed in checks.items():
                if not passed:
                    failures.append({"fold": identifier, "symbol": symbol, "check": check})
            numeric = [by_id[i]["features"]["raw"] for i in fold["evaluation_ids"]
                       if by_id[i]["symbol"] == symbol and by_id[i]["features"]["status"] == "AVAILABLE"]
            scaler = fold["scaler"]
            shift = ((np.asarray(numeric) - np.asarray(scaler["mean"])) / np.asarray(scaler["scale"])) if numeric and scaler["status"] == "AVAILABLE" else None
            memberships = [m for m in fold["memberships"] if by_id[m["query_id"]]["symbol"] == symbol]
            groups[identifier][symbol] = {"fit": f, "evaluation": q, "requirements": required, "checks": checks,
                "drift": {"numeric_queries": len(numeric), "mean_standardized_shift": shift.mean(axis=0).tolist() if shift is not None else None,
                          "ood_query_count": sum(m["ood"] for m in memberships)},
                "K_histogram": dict(sorted(Counter(str(m["K"]) for m in memberships).items())),
                "m_histogram": dict(sorted(Counter(str(m["m"]) for m in memberships).items())),
                "regime_histogram": dict(sorted(Counter(fold["regimes"][i]["query_name"] for i in fold["evaluation_ids"] if by_id[i]["symbol"] == symbol).items()))}
    return {"version": "conditional_mt_bicl_data_coverage_v4", "status": "INSUFFICIENT_DATA" if failures else "DATA_READY_PASS",
        "ready_for_W11_19": not failures, "technical_audit": "PASS", "unique_queries": len(rows),
        "unique_labeled_cycles": sum(r["label_eligible"] for r in rows), "unique_tasks": len({r["task_id"] for r in rows}),
        "full_summary": counts(rows), "folds": groups, "failed_checks": failures,
        "observation_overlap": "NO_REPEATED_ID_OR_ENTRY_EXIT_WITHIN_SELECTED_D_C;FOLDS_AND_PREFIXES_REUSE_ROWS_NOT_INDEPENDENT_N",
        "training_allowed": False, "decision_calls_allowed": False, "confirmation_allowed": False}


def build(root: Path, *, verify_only: bool = False) -> dict[str, Any]:
    """Cold rebuild dữ liệu≤2022; mọi bằng chứng v1–v3 readonly, model mới chỉ regime X."""
    verify_protocol(root)
    spec = validate_protocol((root / PROTOCOL).read_bytes())
    if list(NUMERIC) != [name for name, _ in spec["features"]["numeric"]]:
        raise ValueError("Thứ tự feature khác protocol")
    existing = read((root / MANIFEST).read_bytes()) if (root / MANIFEST).exists() else None
    if existing is not None:
        if (root / MANIFEST).read_bytes() != git(root, "show", "HEAD:" + MANIFEST.as_posix()):
            raise ValueError("Manifest dataset chưa khớp receipt đã commit; không chấp nhận tự reseal")
        verify_only = True
    commit, sources = data_source(root, existing["source_commit"] if existing else None)
    inputs = inventory(root)
    if existing and (existing["source_sha256"] != sources or existing["agent_input_sha256"] != inputs):
        raise ValueError("Source/cache đổi sau snapshot dataset; cần revision")
    if inputs:
        envelope(root / "outputs/historical_memory_run/run_manifest.json")
    history = bounded_index(root / "data/historical/VNINDEX.csv", spec["data"]["oof_end"])
    v3 = read((root / "docs/plan/week11/protocol_v3.json").read_bytes())
    config = v3["decision"]["config"]["signal_config"]
    rows, labels = [], {}
    for symbol in spec["data"]["symbols"]:
        frame, events = load_verified_execution_data(root / "data/execution_prices", symbol)
        symbol_rows, symbol_labels = symbol_data(symbol, frame, events, history)
        for row in symbol_rows:
            row["agent"] = agent_row(root, row, frame, config)
        rows.extend(symbol_rows)
        labels.update(symbol_labels)
        print(f"Đã dựng {symbol}: {len(symbol_rows)} query, {len(symbol_labels)} nhãn engine; không API.", flush=True)
    rows.sort(key=lambda r: (r["as_of_date"], spec["data"]["symbols"].index(r["symbol"])))
    if len({r["episode_id"] for r in rows}) != len(rows):
        raise ValueError("Dataset trùng ID")
    registry = read((root / OUTPUT / "regime_registry.json").read_bytes()) if verify_only else None
    regimes = DataRegimes(history, root / OUTPUT / "regime_models", frozen=registry)
    folds = fold_views(rows, spec, regimes)
    train = train_views(rows, regimes)
    report = coverage(rows, folds, spec)
    requirements = {"status": report["status"], "collection_released": False,
        "structural_problem": "LOCKED_SOURCE_STARTS_2018_BUT_ALPHA_REQUIRES600_BARS;EARLY_INNER_FIT_CANNOT_REACH_AGENT_SUPPORT",
        "required_before_API": ["SOURCE_AND_EXPOSURE_AMENDMENT_FOR_PRE2018_RAW_WARMUP_NO_TRAIN_LABEL_EXPANSION",
            "MATCHING_PINNED_AGENT_PROMPT_REPORTS_PIT_AND_DURABLE_ORIGINAL_WITH_RAW_LEDGER_PROOF",
            "SEPARATE_USER_API_COLLECTION_RELEASE_NO_FORECAST_TRAINING_RELEASE"],
        "points": [{"point_id": r["episode_id"], "alpha_history_rows": r["alpha_history_rows"],
                    "reasons": r["agent"]["reasons"]} for r in rows if r["agent"]["status"] != "AVAILABLE"]}
    artifacts = {"observations.json": {"feature_columns": list(NUMERIC), "rows": rows},
                 "labels.json": labels, "folds.json": folds, "train_prefixes.json": train,
                 "regime_registry.json": regimes.records, "agent_requirements.json": requirements}
    for name, value in artifacts.items():
        immutable(root / OUTPUT / name, value, verify_only=verify_only)
    immutable(root / COVERAGE, report, verify_only=verify_only)
    file_hashes = {(OUTPUT / name).as_posix(): checksum(encoded(value)) for name, value in artifacts.items()}
    file_hashes[COVERAGE.as_posix()] = checksum(encoded(report))
    for cutoff, record in regimes.records.items():
        file_hashes[(OUTPUT / "regime_models" / (cutoff + ".json")).as_posix()] = record["file_sha256"]
    manifest = {"version": "conditional_mt_bicl_dataset_manifest_v4", "status": report["status"],
        "ready_for_W11_19": report["ready_for_W11_19"], "technical_audit": "PASS",
        "protocol_sha256": checksum((root / PROTOCOL).read_bytes()), "source_commit": commit,
        "source_sha256": sources, "source_input_sha256": spec["input_sha256"], "agent_input_sha256": inputs,
        "artifact_sha256": file_hashes, "unique_queries": len(rows), "unique_labeled_cycles": len(labels),
        "date_range": ["2018-01-02", spec["data"]["oof_end"]], "exposure": deepcopy(spec["exposure"]),
        "learner_or_reference_fit": False, "API_calls": 0, "query_outcomes_2023_or_2025_used": False,
        "training_allowed": False, "decision_calls_allowed": False, "confirmation_allowed": False}
    immutable(root / MANIFEST, manifest, verify_only=verify_only)
    if inventory(root) != inputs:
        raise ValueError("Cache agent thay đổi trong khi dựng dataset")
    for name, expected in manifest["artifact_sha256"].items():
        if checksum(safe_path(root, name).read_bytes()) != expected:
            raise ValueError("Artifact bị thay trong khi cold verify")
    return manifest
