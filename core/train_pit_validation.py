"""Chẩn đoán train theo fold PIT đã đăng ký; replay bằng chứng, không gọi Decision."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from core.bayesian_memory import REGIMES
from core.candidate_cohort import CODE_FILES, registry
from core.historical_signals import digest
from core.price_feature_index import PriceFeatureIndex, SYMBOLS
from core.prior_config import copy_prior_json
from core.prior_context import PriorContextAdapter
from core.prior_evidence_v2 import normalize_evidence_config
from core.prior_prompt import CANDIDATE_PROFILES
from core.prior_quality_gate import COUPLED_GATE, SPLIT_GATE
from core.regime_detector import FEATURE_COLUMNS, HMM_PARAMETERS, build_regime_features
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once, runtime_identity

VERSION = "train_pit_diagnostics_v1"
DEFAULT_REPORT = "outputs/bayesian_benchmark/train_validation_v1.json"
DEFAULT_INDEX = "outputs/bayesian_benchmark/price_features/train_validation_index_v1.json"


def fold_schedule(records: list[dict[str, Any]], index: PriceFeatureIndex,
                  calendar: pd.DatetimeIndex) -> dict[str, Any]:
    """Purge bằng entry/exit thực; scaler chỉ fit episode đóng trước query đầu fold."""
    ids = [r["episode_id"] for r in records]
    if len(set(ids)) != len(ids) or set(ids) != {r["episode_id"] for r in index.payload["records"]}:
        raise ValueError("Lịch train khác ID bank/index hoặc có ID trùng")
    for record in records:
        positions = calendar.get_indexer(pd.to_datetime([record[k] for k in ("as_of_date", "entry_date", "exit_date")]))
        if ((positions < 0).any() or positions[1] != positions[0] + 1 or positions[2] != positions[0] + 3):
            raise ValueError("Lịch fold vi phạm entry t+1/exit t+3")
    indexed = {r["episode_id"]: r for r in index.payload["records"]}
    if any(any(record[key] != indexed[record["episode_id"]][key]
               for key in ("symbol", "as_of_date", "exit_date")) for record in records):
        raise ValueError("Ngày/mã bank khác index")
    folds = {}
    for name, settings in index.payload["folds"].items():
        if not name.startswith("train_"):
            continue
        start, end = settings["query_start"], settings["query_end"]
        symbols = {}
        for symbol in SYMBOLS:
            rows = [r for r in records if r["symbol"] == symbol]
            fit = sorted(r["episode_id"] for r in rows if r["exit_date"] < start)
            purged = sorted(r["episode_id"] for r in rows if r["as_of_date"] < start <= r["exit_date"])
            queries = sorted(r["episode_id"] for r in rows if start <= r["as_of_date"] <= end)
            feature_fit = [key for key in fit if indexed[key]["features"]["status"] == "AVAILABLE"]
            scaler = index.scaler(symbol, start, fold_id=name)
            if (scaler["fit_episode_ids"] != feature_fit or scaler["fit_inclusive"]
                    or scaler["freeze_date"] != start or scaler["fit_cutoff"] != start):
                raise ValueError("Scaler fold không khớp prefix fit đã purge")
            symbols[symbol] = {"fit_ids": fit, "purged_ids": purged, "query_ids": queries,
                "feature_fit_ids": feature_fit, "scaler": scaler}
        folds[name] = {**settings, "embargo_rule": "EXIT_STRICTLY_BEFORE_QUERY",
            "extra_embargo_sessions": 0, "symbols": symbols}
    if set(folds) != {"train_2021", "train_2022"}:
        raise ValueError("Thiếu hai fold train đã đăng ký")
    return folds


def verify_regime_fit(adapter: PriorContextAdapter, point: Any) -> dict[str, Any]:
    """Tái fit scaler/calibration số học trên prefix; HMM đã fit được nạp đúng cutoff."""
    proof = point.source_provenance["regime"]
    cutoff = point.source_provenance["context"]["as_of_date"]
    meta = proof["metadata"]
    if (meta["train_end_date"] != cutoff or meta["parameters"] != HMM_PARAMETERS
            or any(day != cutoff for day in proof["component_train_end_dates"].values())
            or proof["frozen_model"] is not None):
        raise ValueError("Model/scaler/calibration dùng sai prefix train")
    prefix = adapter._vnindex.loc[adapter._vnindex.Datetime.between("2018-01-01", cutoff)]
    raw = build_regime_features(prefix, cutoff).loc[:, FEATURE_COLUMNS].to_numpy(dtype=float)
    fitted = StandardScaler().fit(raw)
    artifact = json.loads(adapter._files.path(proof["artifact_path"]).read_text(encoding="utf-8"))["payload"]
    for name, expected in (("mean", fitted.mean_), ("var", fitted.var_), ("scale", fitted.scale_)):
        if not np.allclose(artifact["scaler"][name], expected, rtol=1e-12, atol=1e-12):
            raise ValueError("Scaler HMM không được fit trên feature prefix đúng ngày")
    for name, expected in (("volatility_quantiles", np.quantile(raw[:, 1], [1/3, 2/3])),
                           ("trend_threshold", np.median(np.abs(raw[:, 4]))),
                           ("ma200_train_std", raw[:, 4].std(ddof=1))):
        if not np.allclose(meta[name], expected, rtol=1e-12, atol=1e-12):
            raise ValueError("Calibration regime khác thống kê prefix")
    return {"artifact_path": proof["artifact_path"], "artifact_sha256": proof["artifact_sha256"],
        "train_end_date": cutoff, "training_data_sha256": meta["training_data_sha256"],
        "classification_method": meta["classification_method"], "scaler_calibration_recomputed": True}


def _distribution(values: list[float | None]) -> dict[str, Any]:
    """Công bố mẫu số hữu hạn; không đổi null thành 0 hoặc loại outlier."""
    observed = [float(v) for v in values if v is not None]
    if not np.isfinite(observed).all():
        raise ValueError("Chẩn đoán chứa số không hữu hạn")
    return {"count": len(observed), "missing": len(values)-len(observed),
        "min": min(observed) if observed else None,
        "mean": float(np.mean(observed)) if observed else None,
        "max": max(observed) if observed else None}


def _candidate(evidence: dict[str, Any], name: str) -> dict[str, Any]:
    """Chiếu evidence sang chẩn đoán; không sinh action hoặc return của LLM."""
    if name == "C0":
        ready = evidence["status"] == "READY"
        return {"selected_ids": evidence["selected_ids"], "visible_ids": evidence["selected_ids"],
            "stats_ready": ready, "examples_ready": ready, "fallback": not ready,
            "reason_codes": evidence["reason_codes"], "metrics": evidence["metrics"],
            "population_count": evidence["population_count"], "conditional_count": None,
            "eligible_count": evidence["eligible_count"], "selection_exclusions": {},
            "scores": evidence["selected_scores"],
            "ages": [a["age_days"] for a in evidence["selected_ages"]], "price_distances": [],
            "evidence_sha256": evidence["evidence_sha256"]}
    view = evidence["content_views"][CANDIDATE_PROFILES[name][1]]
    selection = evidence["selection"]
    selected = [r for r in selection["trace"] if r["selection_status"] == "SELECTED"]
    return {"selected_ids": selection["metadata"]["selected_ids"], "visible_ids": view["visible_example_ids"],
        "stats_ready": bool(view["visible_metric_ids"]), "examples_ready": bool(view["visible_example_ids"]),
        "fallback": view["fallback_to_original"], "reason_codes": evidence["gate"]["reason_codes"],
        "metrics": evidence["statistics"]["metrics"],
        "population_count": evidence["statistics"]["population_count"],
        "eligible_count": evidence["statistics"]["eligible_count"],
        "selection_exclusions": selection["metadata"]["exclusion_counts"],
        "conditional_count": evidence["statistics"].get("conditional_count"),
        "scores": [r["rank_score"] for r in selected], "ages": [r["age_days"] for r in selected],
        "price_distances": [r["price_distance"] for r in selected],
        "evidence_sha256": evidence["base_evidence_sha256"]}


def diagnostic_summary(rows: list[dict[str, Any]], candidates: list[str]) -> list[dict[str, Any]]:
    """Giữ mọi nhóm mã/fold/regime, kể cả NO_EXPOSURE; Jaccard chỉ các query liên tiếp cùng nhóm."""
    result = []
    for fold in ("train_2021", "train_2022"):
        for symbol in SYMBOLS:
            for regime in sorted(REGIMES):
                group = [r for r in rows if (r["fold_id"], r["symbol"], r["regime"]) == (fold, symbol, regime)]
                for name in candidates:
                    items = [r["candidates"][name] for r in group]
                    overlaps = []
                    for left, right in zip(items, items[1:]):
                        a, b = set(left["selected_ids"]), set(right["selected_ids"])
                        overlaps.append(float(len(a & b)/len(a | b)) if a | b else None)
                    metric_summary = {}
                    for key in (items[0]["metrics"] if items else ("win_rate_long", "bull_trap_rate",
                            "trend_false_bullish_rate", "pattern_false_bullish_rate")):
                        metrics = [item["metrics"][key] for item in items]
                        metric_summary[key] = {
                            "support": _distribution([m.get("support_count", m.get("raw_counts", {}).get("conditional", {}).get("support_count")) for m in metrics]),
                            "interval_width": _distribution([None if m["credible_interval"] is None else
                                float(m["credible_interval"]["upper"]-m["credible_interval"]["lower"]) for m in metrics])}
                    result.append({"fold_id": fold, "symbol": symbol, "regime": regime, "candidate_id": name,
                        "status": "OBSERVED" if items else "NO_EXPOSURE", "query_count": len(items),
                        "feature_available": sum(r["feature_status"] == "AVAILABLE" for r in group),
                        "stats_ready": sum(i["stats_ready"] for i in items),
                        "examples_ready": sum(i["examples_ready"] for i in items),
                        "fallback_count": sum(i["fallback"] for i in items),
                        "population": _distribution([i["population_count"] for i in items]),
                        "eligible": _distribution([i["eligible_count"] for i in items]),
                        "conditional": _distribution([i["conditional_count"] for i in items]),
                        "k_eff_counts": dict(sorted(Counter(str(len(i["selected_ids"])) for i in items).items())),
                        "reason_counts": dict(sorted(Counter(code for i in items for code in i["reason_codes"]).items())),
                        "selected_score": _distribution([v for i in items for v in i["scores"]]),
                        "selected_age_days": _distribution([v for i in items for v in i["ages"]]),
                        "selected_price_distance": _distribution([v for i in items for v in i["price_distances"]]),
                        "selection_gap_sessions": _distribution([v for i in items for v in i["selection_gap_sessions"]]),
                        "selection_exclusion_counts": dict(sorted(sum((Counter(i["selection_exclusions"]) for i in items), Counter()).items())),
                        "selection_jaccard_consecutive_same_group": _distribution(overlaps), "metrics": metric_summary})
    return result


def build_train_diagnostics(adapter: PriorContextAdapter, index: PriceFeatureIndex, *,
                            run_dir: str = "outputs/historical_memory_run") -> dict[str, Any]:
    """Replay toàn bộ bank để kiểm prior provenance, chấm kỹ thuật hai fold đã khóa."""
    if adapter._mode != "historical_prefix" or adapter.prior_config != {
            **adapter.prior_config, "enable_bayesian_prior": True,
            "mode": "bayesian_regime", "k": 3, "seed": 42, "scope": "same_symbol"}:
        raise ValueError("Validation train cần HMM prefix và cấu hình prior đã đăng ký")
    adapter._bind_price_feature_index(index)
    records = sorted(adapter._retriever._memory.records, key=lambda r:(r["as_of_date"], r["symbol"]))
    calendar = pd.DatetimeIndex(adapter._vnindex.Datetime)
    folds = fold_schedule(records, index, calendar)
    query_folds = {key: name for name, fold in folds.items()
                  for item in fold["symbols"].values() for key in item["query_ids"]}
    if not query_folds:
        raise ValueError("BLOCKED: không có query train hợp lệ theo fold đã đăng ký")
    rows, regime_fits, replayed = [], {}, 0
    historical_identity = None
    candidates_registry = registry()
    for record in records:
        point = adapter.prepare(record["symbol"], record["as_of_date"])
        shared = point.load_shared_checkpoint(run_dir)
        signals_proof = shared["prior_provenance"]["signals"]
        identity = {key: signals_proof[key] for key in ("config_sha256", "code_sha256", "runtime")}
        if historical_identity is None:
            historical_identity = identity
        elif historical_identity != identity:
            raise ValueError("Checkpoint train trộn cấu hình/code/runtime lịch sử")
        cutoff = record["as_of_date"]
        if cutoff not in regime_fits:
            regime_fits[cutoff] = verify_regime_fit(adapter, point)
        replayed += 1
        if record["episode_id"] not in query_folds:
            continue
        fold_id = query_folds[record["episode_id"]]
        scaler = index.scaler(record["symbol"], cutoff, fold_id=fold_id)
        features = point.price_features()
        shared_hash = digest(shared)
        legacy = point.evidence_v2(shared, normalize_evidence_config())
        coupled = point.quality_evidence(shared, index, gate_version=COUPLED_GATE)
        split = point.quality_evidence(shared, index, gate_version=SPLIT_GATE)
        repeated = point.select_price_examples(shared, index)
        if digest(repeated) != digest(split["selection"]):
            raise ValueError("Lựa chọn ví dụ không tái lập trên cùng query")
        candidates = {name: _candidate(legacy if name == "C0" else coupled if name == "C1" else split, name)
                      for name in candidates_registry["order"]}
        for candidate in candidates.values():
            positions = sorted(calendar.get_loc(pd.Timestamp(adapter._retriever._verified_by_id[key]["as_of_date"]))
                               for key in candidate["selected_ids"])
            candidate["selection_gap_sessions"] = [int(b-a) for a, b in zip(positions, positions[1:])]
        if digest(shared) != shared_hash:
            raise ValueError("Chẩn đoán ứng viên làm đổi Full dùng chung")
        rows.append({"episode_id": record["episode_id"], "symbol": record["symbol"], "as_of_date": cutoff,
            "fold_id": fold_id, "regime": record["regime"], "shared_sha256": shared_hash,
            "scaler_sha256": scaler["scaler_sha256"], "feature_status": features["status"],
            "feature_reasons": features["reasons"],
            "news_reliable": point.source_provenance["news"]["is_reliable"],
            "scored_price_distance": _distribution([r["price_distance"] for r in split["selection"]["trace"]]),
            "candidates": candidates})
    adapter.verify_sources()
    root = Path(__file__).resolve().parents[1]
    code = {name: hashlib.sha256((root/name).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            for name in (*CODE_FILES, "core/train_pit_validation.py")}
    return copy_prior_json({"report_version": VERSION, "status": "COMPLETE", "scope": "TRAIN_PIT_DIAGNOSTICS",
        "decision_calls": 0, "llm_performance": None, "candidate_selection": None,
        "registry": candidates_registry, "code_sha256": code, "runtime": runtime_identity(),
        "sources": adapter.source_hashes, "index_identity": index.identity,
        "historical_run_signature": adapter._bank_manifest["run_signature"],
        "historical_signal_identity": historical_identity, "historical_run_dir": run_dir, "replayed_count": replayed,
        "query_count": len(rows), "bootstrap_or_outside_fold_count": len(records)-len(rows),
        "excluded_missing_provenance_count": 0, "missing_provenance_policy": "BLOCK_BEFORE_REPORT",
        "regime_fits": regime_fits, "folds": folds, "points": rows,
        "summary": diagnostic_summary(rows, candidates_registry["order"]),
        "limitations": ["PIT hồi cứu trên dữ liệu cấp thuật toán; không chứng nhận vintage provider hoặc kiến thức LLM.",
            "HMM expanding prefix; scaler giá freeze theo fold, thống kê expanding exit<query; không sweep hyperparameter.",
            "Jaccard đo các query liên tiếp trong cùng mã/fold/regime, không phải độ ổn định lợi nhuận.",
            "Không gọi Decision/mock; không xếp hạng ứng viên hoặc kết luận hiệu quả LLM; risk policy OFF."]})


def run_train_validation(report_path: Path, *, index_path: str = DEFAULT_INDEX,
                         verify_only: bool = False) -> dict[str, Any]:
    """CLI offline tạo report bất biến hoặc dựng lại toàn bộ semantic trước đối chiếu."""
    adapter = PriorContextAdapter({"enable_bayesian_prior": True})
    root = adapter._files.root
    if (report_path.name.startswith(".env") or not report_path.resolve().is_relative_to(root.resolve())
            or not report_path.resolve().is_relative_to((root/"outputs/bayesian_benchmark").resolve())):
        raise ValueError("Report train cần đường riêng trong outputs/bayesian_benchmark")
    existing = read_envelope(report_path) if report_path.exists() else None
    if verify_only and existing is None:
        raise ValueError("Thiếu report train cần verify")
    target = adapter._files.path(index_path)
    if (not target.resolve().is_relative_to((root/"outputs/bayesian_benchmark/price_features").resolve())
            or target.resolve() == report_path.resolve() or target.name.startswith(".env")):
        raise ValueError("Index train cần đường riêng trong outputs/bayesian_benchmark/price_features")
    if verify_only and not target.exists():
        raise ValueError("Thiếu index đã khóa; verify không tạo artifact")
    index = adapter.load_price_feature_index(index_path) if target.exists() else adapter.build_price_feature_index(index_path)
    adapter._files.pin(index_path)
    report = build_train_diagnostics(adapter, index)
    if existing is not None and existing != report:
        raise ValueError("Report train khác nguồn/code/registry hoặc chẩn đoán tái lập; cần đường run mới")
    if not verify_only:
        _write_once(report_path, report)
    return report
