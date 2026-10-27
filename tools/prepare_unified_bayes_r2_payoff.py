"""Khóa/kiểm gate payoff R2 trên 647 query train đã purge, hoàn toàn offline."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from core.execution_prices import load_verified_execution_data
from core.historical_outcomes import HistoricalOutcomeGenerator
from core.historical_signals import digest
from core.prior_backtest import canonical_hash
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once, runtime_identity
from tools.unified_bayes_r2_payoff import (
    PROTOCOL, PROTOCOL_SHA, VERSION, PayoffEvidence, aggregate, estimate_payoff,
    evaluate_gate, load_protocol, point_metrics,
)

OUTPUT = ROOT / "outputs/bayesian_benchmark/unified_bic_r2/offline/payoff_gate_v1.json"
CODE = ("tools/unified_bayes_r2_payoff.py", "tools/prepare_unified_bayes_r2_payoff.py",
        "tools/test_unified_bayes_r2_payoff.py", "tools/test_unified_bayes_r2_payoff_leakage.py")
SYMBOLS = ("FPT", "MWG", "VCB", "VNM")


def sha(path: Path) -> str:
    """Hash byte nguồn ignored, khác hash text LF của code tracked."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_identity() -> dict[str, str]:
    """Gắn nghiệm thu riêng của R2, không sửa map code/runtime đã khóa của v1."""
    return {name: hashlib.sha256((ROOT / name).read_text("utf-8").encode()).hexdigest() for name in CODE}


def source_guard(sources: dict[str, str]) -> None:
    """Nguồn phải ở workspace và nguyên byte; không chấp nhận đường credential/2025."""
    for name, checksum in sources.items():
        path = (ROOT / name).resolve()
        if (not path.is_relative_to(ROOT) or path.name.startswith(".env")
                or "execution_prices_2025" in path.parts or sha(path) != checksum):
            raise ValueError(f"Nguồn payoff thay đổi hoặc không được phép: {name}")


def query_schedule(metadata: list[dict[str, Any]], calendar: pd.DatetimeIndex,
                   spec: dict[str, Any]) -> dict[str, str]:
    """Tái dựng 647 IDs/purge từ metadata; mọi cycle dùng đúng phiên t+1/t+3."""
    if calendar.empty or not calendar.is_unique or not calendar.is_monotonic_increasing or calendar.hasnans:
        raise ValueError("Lịch payoff thiếu phiên hoặc trùng/đảo thứ tự")
    positions = np.column_stack([calendar.get_indexer(pd.to_datetime([row[key] for row in metadata]))
                                 for key in ("as_of_date", "entry_date", "exit_date")])
    if ((positions < 0).any() or (positions[:, 1] != positions[:, 0]+1).any()
            or (positions[:, 2] != positions[:, 0]+3).any()):
        raise ValueError("Metadata payoff sai hợp đồng t+1/t+3")
    result = {}
    for fold in spec["offline_gate"]["folds"]:
        queries = sorted((r for r in metadata if fold["query_start"] <= r["as_of_date"] <= fold["query_end"]),
                         key=lambda r:r["episode_id"])
        kept = [r for r in queries if r["exit_date"] <= fold["query_end"]]
        purged = [r["episode_id"] for r in queries if r["exit_date"] > fold["query_end"]]
        ids = [r["episode_id"] for r in kept]
        if (len(queries) != fold["query_count_before_end_purge"] or len(ids) != fold["query_count"]
                or canonical_hash(ids) != fold["query_ids_sha256"] or purged != fold["purged_query_ids"]):
            raise ValueError("Lịch train payoff khác mẫu/purge đã đăng ký")
        if set(ids).intersection(result):
            raise ValueError("Query payoff trùng fold")
        result.update({identifier:fold["fold_id"] for identifier in ids})
    if len(result) != spec["offline_gate"]["query_count"]:
        raise ValueError("Thiếu/thừa query train payoff")
    return result


def make_panels(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Cùng giao readiness cho mọi dự báo; giữ cả ô không có support."""
    return {"overall": aggregate(rows),
            "by_fold": {f:aggregate([r for r in rows if r["fold_id"] == f]) for f in ("train_2021", "train_2022")},
            "by_symbol": {s:aggregate([r for r in rows if r["symbol"] == s]) for s in SYMBOLS},
            "by_fold_symbol": {f"{f}/{s}": aggregate([r for r in rows if r["fold_id"] == f and r["symbol"] == s])
                               for f in ("train_2021", "train_2022") for s in SYMBOLS}}


def diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Outlier/phụ thuộc/n nhỏ là mô tả, không sửa dữ liệu hoặc thay gate."""
    ready = [r for r in rows if r["metrics"] is not None]
    dependence = {}
    for f in ("train_2021", "train_2022"):
        for s in SYMBOLS:
            group = sorted([r for r in ready if r["fold_id"] == f and r["symbol"] == s], key=lambda r:r["as_of_date"])
            target = [r["target_return"] for r in group]
            error = [r["target_return"]-r["evidence"]["prediction"]["posterior"]["mean"] for r in group]
            def lag(values: list[float]) -> float | None:
                if len(values) < 3 or min(float(np.std(values[:-1])), float(np.std(values[1:]))) == 0:
                    return None
                return float(np.corrcoef(values[:-1], values[1:])[0,1])
            dependence[f"{f}/{s}"] = {"count": len(group), "lag1_target": lag(target), "lag1_error": lag(error)}
    synthetic = []
    c = [-.02,-.01,0.,.01,.02]
    for n in range(6):
        synthetic.append({"case": f"small_n_{n}", "prediction": estimate_payoff(c[:n],c*4,stats_ready=n>=5)})
    for outlier in (-.5,.5):
        synthetic.append({"case": f"outlier_{outlier}", "prediction": estimate_payoff(c[:-1]+[outlier],c*4,stats_ready=True)})
    synthetic.append({"case": "constant_dependent", "prediction": estimate_payoff([.01]*5,[.01]*20,stats_ready=True)})
    return {"worst_absolute_error": [{"episode_id":r["episode_id"], "target_return":r["target_return"],
              "metrics":r["metrics"]} for r in sorted(ready,key=lambda r:(-r["metrics"]["absolute_error_nig"],r["episode_id"]))[:10]],
            "worst_nll": [{"episode_id":r["episode_id"], "target_return":r["target_return"], "metrics":r["metrics"]}
                          for r in sorted(ready,key=lambda r:(-r["metrics"]["nll_nig"],r["episode_id"]))[:10]],
            "dependence": dependence,
            "clusters_90_sessions": {str(key):aggregate([r for r in rows if r["cluster_90_sessions"] == key])
                                     for key in sorted({r["cluster_90_sessions"] for r in rows})},
            "conditional_support_bins": {f"{lo}_{hi}":aggregate([r for r in rows if lo <= r["evidence"]["counts"]["nC"]
                                      and (hi is None or r["evidence"]["counts"]["nC"] <= hi)])
                                         for lo,hi in ((0,4),(5,9),(10,19),(20,None))},
            "synthetic_stress": synthetic,
            "exclusion_reasons": dict(Counter(reason for r in rows for reason in r["evidence"]["prediction"]["gate"]["reason_codes"])),
            "not_independent_observations_or_ESS": True}


def build_report() -> dict[str, Any]:
    """Dùng snapshot U10-04 đã kiểm, tái dựng partition/số học và nhãn engine train."""
    spec = load_protocol()
    pins = {spec["offline_gate"]["source_memory_file"]:spec["offline_gate"]["source_memory_file_sha256"],
            spec["offline_gate"]["source_diagnostics_file"]:spec["offline_gate"]["source_diagnostics_file_sha256"],
            spec["backbone_choice"]["file"]:spec["backbone_choice"]["file_sha256"]}
    source_guard(pins)
    memory, old, choice = (read_envelope(ROOT / name) for name in pins)
    if (old["runtime"] != runtime_identity() or choice["choice"] != "hierarchical_pool" or choice["lambda"] != 8
            or choice["gate_status"] != "PASS" or choice["diagnostics_sha256"] != pins[spec["offline_gate"]["source_diagnostics_file"]]):
        raise ValueError("Runtime/backbone/source U10-04 không khớp")
    sources = {**memory["source_files"], **old["sources"], **pins}
    source_guard(sources)
    old_code = {**old["code_sha256"], **memory["runtime"]["code_sha256"]}
    for name, expected in old_code.items():
        if hashlib.sha256((ROOT/name).read_text("utf-8").encode()).hexdigest() != expected:
            raise ValueError(f"Code LF v1 thay đổi: {name}")
    own_code = code_identity()
    calendar = pd.DatetimeIndex(pd.read_csv(ROOT/memory["index"]["provenance"]["calendar"]["source_csv_path"],parse_dates=["Datetime"])["Datetime"])
    metadata = memory["metadata"]
    query_folds = query_schedule(metadata, calendar, spec)
    by_id = {r["episode_id"]:r for r in metadata}
    records = {r["episode_id"]:r for r in memory["records"]}
    old_points = {r["episode_id"]:r for r in old["points"]}
    if set(old_points) != set(query_folds) or len(old["points"]) != 647:
        raise ValueError("Snapshot diagnostics thiếu/trùng query train")
    prices = {s:load_verified_execution_data(ROOT/Path(memory["index"]["provenance"]["prices"][s]["csv_path"]).parent,s) for s in SYMBOLS}
    outcomes = HistoricalOutcomeGenerator(prices.__getitem__)
    engine = PayoffEvidence(metadata, records)
    rows = []
    for identifier in sorted(query_folds,key=lambda i:(by_id[i]["as_of_date"],by_id[i]["symbol"])):
        meta, previous = by_id[identifier], old_points[identifier]
        evidence = engine.evidence(symbol=meta["symbol"],as_of_date=meta["as_of_date"],
                                   current_regime=meta["regime"],current_signals=meta["agent_signals"])
        if (evidence["groups"] != {k:g["episode_ids"] for k,g in previous["groups"].items()}
                or evidence["counts"] != previous["counts"] or evidence["v1_probability"] != previous["probability"]["pool_8"]
                or evidence["v1_stats_gate"]["ready"] != previous["ready"]["pool_8"]):
            raise ValueError("Partition/posterior/readiness tái dựng khác snapshot U10-04")
        # Target của chính query chỉ được chấm sau khi evidence PIT đã tạo xong.
        fold = next(f for f in spec["offline_gate"]["folds"] if f["fold_id"] == query_folds[identifier])
        target = outcomes.generate(meta["symbol"],meta["as_of_date"],meta["entry_date"],meta["exit_date"],
                                   meta["agent_signals"],settled_as_of=fold["query_end"])
        if target != records[identifier]["outcome"] or target["net_return_pct"]/100 != previous["net_long_return"]:
            raise ValueError("Target payoff khác nhãn engine/snapshot train")
        net = float(target["net_return_pct"]/100)
        rows.append({"episode_id":identifier,"symbol":meta["symbol"],"as_of_date":meta["as_of_date"],
                     "exit_date":meta["exit_date"],"fold_id":query_folds[identifier],
                     "cluster_90_sessions":int(meta["cutoff_session_index"]//90),"evidence":evidence,
                     "target_return":net,"metrics":point_metrics(evidence["prediction"],net)})
    # Kiểm thêm toàn nhãn train dùng làm prior bằng cùng engine, không đọc outcome OOS.
    for meta in metadata:
        if meta["exit_date"] <= "2022-12-30":
            expected = outcomes.generate(meta["symbol"],meta["as_of_date"],meta["entry_date"],meta["exit_date"],
                                         meta["agent_signals"],settled_as_of="2022-12-30")
            if records[meta["episode_id"]]["outcome"] != expected:
                raise ValueError("Nhãn prior train khác hàm kinh tế engine")
    panels = make_panels(rows)
    result = {"report_version":VERSION,"protocol_sha256":PROTOCOL_SHA,"code_sha256":own_code,
              "runtime":runtime_identity(),"sources":dict(sorted(sources.items())),"v1_code_sha256":old_code,
              "query_count":647,"points":rows,"panels":panels,"gate":evaluate_gate(panels),
              "diagnostics":diagnostics(rows),"llm_calls":0,"is_execution_plan":False,
              "confirmation_allowed":False,"risk_policy":"OFF",
              "provenance_policy":"reuse_pinned_verified_U10_04_signals_regimes_scalers_without_refit",
              "limitations":["Train 2021/2022 đã dùng chọn lambda v1; gate tiếp nối không là xác nhận độc lập.",
                             "Prior EB và conditional Gaussian là xấp xỉ; Student-t không loại phụ thuộc thời gian.",
                             "Nguồn chung 2023/2024 chỉ đối soát hash; scoring/nhãn train không dùng outcome OOS.",
                             "Mean/CrI lịch sử chưa là expected return query hiệu chuẩn; không override action."]}
    source_guard(sources)
    if code_identity() != own_code or load_protocol() != spec:
        raise ValueError("Code/protocol payoff thay trong lúc dựng report")
    return result


def read_report(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    """Tự reseal report sai model/support/metric/gate không thay bản tái dựng."""
    saved = read_envelope(path)
    if digest(saved) != digest(expected):
        raise ValueError("Payoff report khác nguồn/PIT/số học/rule đã tái dựng")
    return saved


def offline_guard(event: str, args: tuple[Any, ...]) -> None:
    """Không mở key, mạng, giá 2025 hoặc bộ Decision development v1 trong CLI."""
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise ValueError("Gate payoff không được dùng mạng")
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = str(args[0]).replace("\\","/").lower()
        if (Path(path).name.startswith(".env") or "/execution_prices_2025/" in path
                or "/unified_bic_v1/development/" in path):
            raise ValueError("Gate payoff không được đọc key/2025/development v1")


def main() -> None:
    """Prepare write-once hoặc default cold consumer; không có cờ gọi API."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare",action="store_true")
    modes.add_argument("--verify-only",action="store_true")
    args = parser.parse_args()
    sys.addaudithook(offline_guard)
    expected = build_report()
    if args.prepare:
        _write_once(OUTPUT,expected)
    result = read_report(OUTPUT,expected)
    source_guard(result["sources"])
    if code_identity() != result["code_sha256"] or canonical_hash(load_protocol()) != result["protocol_sha256"]:
        raise ValueError("Code/protocol đổi trước công bố gate payoff")
    print(f"Gate payoff R2 {result['gate']['status']}: common={result['panels']['overall']['common_count']}/647; "
          f"failed_checks={result['gate']['failed_checks']}; API=0, confirmation_allowed=false",flush=True)


if __name__ == "__main__":
    main()
