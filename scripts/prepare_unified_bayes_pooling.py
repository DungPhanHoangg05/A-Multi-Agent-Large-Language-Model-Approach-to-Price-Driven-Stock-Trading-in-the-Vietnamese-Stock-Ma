"""Khóa backbone U-BICL bằng 647 query train PIT, hoàn toàn offline trước Decision."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from core.bayesian_memory import read_json
from core.historical_outcomes import HistoricalOutcomeGenerator
from core.historical_signals import digest
from core.price_feature_index import _hash
from core.prior_context import PriorContextAdapter
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once, runtime_identity
from core.train_pit_validation import verify_regime_fit
from core.unified_bayes_diagnostics import VERSION, SCORE_KEYS, fold_schedule, score_rows, select_backbone
from core.unified_bayes_memory import OUTPUT as MEMORY_PATH, load_memory
from core.unified_bayes_statistics import MODELS, UnifiedBayesStatistics
from scripts.prepare_unified_bayes_memory import PROTOCOL, PROTOCOL_SHA, verified_inputs

NAMESPACE = ROOT / "outputs/bayesian_benchmark/unified_bic_v1/inputs"
DIAGNOSTICS = NAMESPACE / "pooling_diagnostics_v1.json"
CHOICE = NAMESPACE / "backbone_choice_v1.json"
MEMORY_SHA = "adbe4051575665e28688b1ed3213bb54bd6272bd29715dc2b2d887c46e8df5b9"
FIXTURE = "docs/plan/week10/fixtures/unified_bic_contract_v1.json"
FIXTURE_SHA = "f4a0a49d3be7af76c8acfcf7dbeed8ed47b112c7781d7317c91ba0ea11ee1e30"
CODE = ("core/unified_bayes_statistics.py", "core/unified_bayes_diagnostics.py",
        "scripts/prepare_unified_bayes_pooling.py", "core/train_pit_validation.py",
        "core/prior_conditional_statistics.py")


def sha(path: Path) -> str:
    """Băm byte artifact/source, tách với hash LF của code."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_identity() -> dict[str, str]:
    """Ghim module mới và primitive HMM/statistics đang dùng theo text LF."""
    return {name: hashlib.sha256((ROOT / name).read_text("utf-8").encode()).hexdigest() for name in CODE}


def load_protocol() -> dict[str, Any]:
    """Không cho sửa hằng số/lịch/fixture sau khi thấy diagnostics."""
    protocol, fixture = read_json(ROOT / PROTOCOL), read_json(ROOT / FIXTURE)
    if (_hash(protocol) != PROTOCOL_SHA or _hash(fixture) != FIXTURE_SHA
            or fixture["protocol_sha256"] != PROTOCOL_SHA):
        raise ValueError("Protocol/fixture pooling khác bản đã khóa")
    return protocol


def build_diagnostics() -> dict[str, Any]:
    """Kiểm memory thật rồi replay đúng query train; producer prior chạy trước đọc target."""
    protocol = load_protocol()
    if sha(ROOT / MEMORY_PATH) != MEMORY_SHA:
        raise ValueError("Memory U10-03 khác snapshot đã nghiệm thu; không chọn lại nguồn")
    inputs = verified_inputs()
    memory = load_memory(ROOT / MEMORY_PATH, **inputs)
    adapter = PriorContextAdapter({"enable_bayesian_prior": True})
    calendar = pd.DatetimeIndex(adapter._vnindex.Datetime)
    folds = fold_schedule(memory, calendar, protocol)
    query_folds = {key: fold for fold, item in folds.items() for key in item["query_ids"]}
    queries = sorted((deepcopy(memory._metadata[key]) for key in query_folds),
                     key=lambda row: (row["as_of_date"], row["symbol"]))
    statistics = UnifiedBayesStatistics(memory)
    outcomes = HistoricalOutcomeGenerator(adapter._prices.__getitem__)
    rows, fits = [], {}
    historical_identity = None
    for position, row in enumerate(queries, 1):
        symbol, cutoff = row["symbol"], row["as_of_date"]
        point = adapter.prepare(symbol, cutoff)
        shared = point.load_shared_checkpoint("outputs/historical_memory_run")
        signal_proof = shared["prior_provenance"]["signals"]
        identity = {key: signal_proof[key] for key in ("config_sha256", "code_sha256", "runtime")}
        if historical_identity is None:
            historical_identity = identity
        elif historical_identity != identity:
            raise ValueError("Queries pooling trộn model/schema/runtime tín hiệu lịch sử")
        if (shared["current_signals"] != row["agent_signals"]
                or shared["market_regime"]["regime_name"] != row["regime"]):
            raise ValueError("Query pooling khác signals/regime của memory đã kiểm")
        if cutoff not in fits:
            fits[cutoff] = verify_regime_fit(adapter, point)
        fold_id = query_folds[row["episode_id"]]
        scaler = memory.index.scaler(symbol, cutoff, fold_id=fold_id)
        if scaler != folds[fold_id]["symbols"][symbol]["scaler"]:
            raise ValueError("Scaler bị refit hoặc đổi trong fold diagnostics")
        evidence = statistics.evidence(symbol=symbol, as_of_date=cutoff,
            current_regime=shared["market_regime"]["regime_name"], current_signals=shared["current_signals"])
        # Nhãn query chỉ được truy cập sau khi cả bốn posterior đã tạo xong.
        outcome = outcomes.generate(symbol, cutoff, row["entry_date"], row["exit_date"],
            row["agent_signals"], settled_as_of=folds[fold_id]["query_end"])
        if outcome != memory._records[row["episode_id"]]["outcome"]:
            raise ValueError("Target diagnostics khác nhãn engine trong memory")
        net = float(outcome["net_return_pct"] / 100.)
        rows.append({"episode_id": row["episode_id"], "symbol": symbol, "as_of_date": cutoff,
            "exit_date": row["exit_date"], "fold_id": fold_id, "label": int(net > 0), "net_long_return": net,
            "probability": {name: evidence["posteriors"][name]["posterior_mean"] for name in MODELS},
            "ready": {name: evidence["posteriors"][name]["gate"]["ready"] for name in MODELS},
            "evidence_sha256": evidence["evidence_sha256"], "counts": evidence["counts"],
            "groups": evidence["groups"], "shared_sha256": digest(shared),
            "source_proof_sha256": digest(point.source_provenance), "regime_fit_sha256": digest(fits[cutoff]),
            "scaler_sha256": scaler["scaler_sha256"]})
        if position % 50 == 0 or position == len(queries):
            print(f"Đã kiểm {position}/{len(queries)} query train; chưa đọc target ngoài train hoặc gọi Decision", flush=True)
    adapter.verify_sources()
    sources = {**inputs["source_files"], **adapter.source_hashes,
        MEMORY_PATH: MEMORY_SHA, FIXTURE: sha(ROOT / FIXTURE)}
    for name, expected in sources.items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"Nguồn đổi khi dựng diagnostics: {name}")
    score = score_rows([{key: row[key] for key in SCORE_KEYS} for row in rows])
    return {"report_version": VERSION, "protocol_sha256": PROTOCOL_SHA,
        "memory_sha256": memory.identity, "memory_file_sha256": MEMORY_SHA, "index_sha256": memory.index.identity,
        "code_sha256": code_identity(), "runtime": runtime_identity(), "sources": dict(sorted(sources.items())),
        "query_count": len(rows), "decision_calls": 0, "is_execution_plan": False, "confirmation_allowed": False,
        "historical_identity": historical_identity, "folds": folds, "regime_fits": fits,
        "points": rows, "summary": score,
        "limitations": ["Chọn hyperparameter trên train 2021/2022, không phải kiểm định xác nhận hoặc hiệu quả LLM.",
            "CrI Beta plug-in; raw n không là ESS hoặc xác suất query được hiệu chuẩn.",
            "Nguồn 2023/2024 chỉ được tái kiểm trong snapshot chung; không tham gia scoring/chọn lambda.",
            "HMM dùng historical_prefix đúng query, scaler giữ nguyên đầu fold; không thêm embargo hoặc sweep."]}


def choice_for_report(report: dict[str, Any], diagnostics_sha256: str) -> dict[str, Any]:
    """Bind kết quả choice vào diagnostics thật, nguồn, code và runtime trước LLM."""
    if (report.get("report_version") != VERSION or report.get("protocol_sha256") != PROTOCOL_SHA
            or type(diagnostics_sha256) is not str or len(diagnostics_sha256) != 64
            or set(diagnostics_sha256) - set("0123456789abcdef")):
        raise ValueError("Choice thiếu diagnostics/protocol đã kiểm")
    return {**select_backbone(report["summary"]), "status": "LOCKED", "metric": "win_rate_long",
        "protocol_sha256": PROTOCOL_SHA, "diagnostics_sha256": diagnostics_sha256,
        "diagnostics_payload_sha256": digest(report), "source_sha256": _hash(report["sources"]),
        "memory_sha256": report["memory_sha256"], "index_sha256": report["index_sha256"],
        "code_sha256": report["code_sha256"], "runtime": report["runtime"],
        "is_execution_plan": False, "confirmation_allowed": False}


def main() -> None:
    """Mặc định verify-only; prepare ghi một lần, resume đúng report/choice hiện hữu."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare", action="store_true", help="Tạo diagnostics và khóa choice offline")
    modes.add_argument("--verify-only", action="store_true", help="Tái dựng toàn bộ nguồn/posterior/loss/gate")
    args = parser.parse_args()
    if not args.prepare and (not DIAGNOSTICS.exists() or not CHOICE.exists()):
        raise ValueError("Chưa có diagnostics/choice; verifier không tạo artifact")
    expected = build_diagnostics()
    if args.prepare:
        _write_once(DIAGNOSTICS, expected)
    elif read_envelope(DIAGNOSTICS) != expected:
        raise ValueError("Diagnostics khác nguồn/PIT/posterior/loss đã tái dựng, kể cả tự reseal")
    choice = choice_for_report(expected, sha(DIAGNOSTICS))
    if args.prepare:
        _write_once(CHOICE, choice)
    elif read_envelope(CHOICE) != choice:
        raise ValueError("Choice khác winner/gate/diagnostics/source/code/runtime đã tái dựng")
    print(f"Đã khóa backbone {choice['choice']}, lambda={choice['lambda']}, gate pooling={choice['gate_status']}; "
          f"647 query train, reasons={choice['reasons']}; chưa gọi LLM hoặc phát hành xác nhận")


if __name__ == "__main__":
    main()
