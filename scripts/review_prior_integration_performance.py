"""Đo lại retriever theo W3 và tách overhead tích hợp W4; không gọi LLM thật."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
import sys
from time import perf_counter_ns
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents import decision_agent
from core.bayesian_memory import HistoricalMemory, atomic_write_json, read_json
from core.bayesian_retriever import BayesianPriorRetriever, VERSIONS, format_compact_prior_prefix
from core.prior_backtest import canonical_hash
from core.prior_context import PriorContextAdapter, _runtime_identity
from core.regime_detector import MarketRegimeDetector
from scripts.benchmark_bayesian_retriever import benchmark, measure, summarize
from scripts.verify_prior_integration import TextLLM, offline_guard, require, sha
from utils.graph_setup import SetGraph, _consume_graph_prior


def review_adapter() -> dict[str, Any]:
    """Đo riêng constructor, context, verifier, callback và graph với báo cáo W2."""
    receipt_path = ROOT / "docs/plan/week4/integration_smoke.json"
    receipt = read_json(receipt_path)
    require(receipt["status"] == "PASS_OFFLINE_INTEGRATION_SMOKE", "Chưa có smoke W4-14 PASS")
    observed = receipt["smoke"]["observed_replay"]
    require(observed["status"] == "PASS", "Overhead nguồn quan sát cần archive/proof replay PASS")
    counts: Counter[str] = Counter()
    memory_load, retriever_init = HistoricalMemory.load, BayesianPriorRetriever.__init__
    def load(owner: HistoricalMemory, *args: Any, **kwargs: Any) -> Any:
        counts["memory_load"] += 1
        return memory_load(owner, *args, **kwargs)
    def construct(owner: BayesianPriorRetriever, *args: Any, **kwargs: Any) -> None:
        counts["retriever_constructor"] += 1
        retriever_init(owner, *args, **kwargs)
    with (patch.object(HistoricalMemory, "load", load),
          patch.object(BayesianPriorRetriever, "__init__", construct)):
        started = perf_counter_ns()
        adapter = PriorContextAdapter({"enable_bayesian_prior": True})
        constructor_ns = perf_counter_ns() - started
    require(dict(counts) == {"retriever_constructor": 1, "memory_load": 1}, "Constructor nạp lặp kho")
    text = TextLLM()
    builder = SetGraph(text, object(), object())
    points, states, prepared, graphs, context_receipts = [], [], [], [], []
    with patch.object(MarketRegimeDetector, "load", wraps=MarketRegimeDetector.load) as models:
        for row in observed["contexts"]:
            started = perf_counter_ns()
            point = adapter.prepare(row["symbol"], row["cutoff"])
            shared = point.load_shared_checkpoint("outputs/historical_memory_run")
            context_ns = perf_counter_ns() - started
            require(canonical_hash({key: shared[key] for key in (
                "indicator_report", "pattern_report", "trend_report", "alpha_report", "sentiment_report")})
                == row["reports_sha256"], "Reports khác replay đã chốt")
            graph = builder.compile_report_decision(prior_config=shared["prior_config"],
                prior_retriever=point.retrieve, prior_source_validator=point.verify_source)
            output = graph.invoke(deepcopy(shared))
            points.append(point)
            states.append(shared)
            prepared.append(output)
            graphs.append(graph)
            context_receipts.append({"symbol": row["symbol"], "cutoff": row["cutoff"],
                "regime": shared["market_regime"]["regime_name"], "prepare_and_journal_ns": context_ns,
                "prompt_length": len(output["decision_prompt"]),
                "prefix_length": len(output["bayesian_prior_context"]),
                "source_provenance_sha256": canonical_hash(shared["prior_provenance"])})
        model_loads = models.call_count
    stages = {}
    # Verifier đọc byte để kiểm checksum; retrieval API vẫn chỉ dùng kho trong RAM.
    with ExitStack() as guards:
        for target in ("core.prior_context.read_json", "core.bayesian_memory.read_json",
                       "core.bayesian_retriever.read_json", "core.prior_context.load_verified_execution_data",
                       "core.bayesian_memory.HistoricalMemory.load", "core.regime_detector.MarketRegimeDetector.load"):
            guards.enter_context(patch(target, side_effect=AssertionError("Đường nóng nạp lại JSON/giá/model")))
        guards.enter_context(patch.object(adapter._retriever._memory, "_execution_loader",
            side_effect=AssertionError("Query nạp lại giá")))
        node = decision_agent.create_final_trade_decider(text, _prior_preparer=_consume_graph_prior)
        operations = {
            "source_validator": [lambda p=p, s=s: p.verify_source(deepcopy(s)) for p, s in zip(points, states)],
            "adapter_retrieve": [lambda p=p, s=s: p.retrieve(deepcopy(s)) for p, s in zip(points, states)],
            "formatter": [lambda s=s: format_compact_prior_prefix(s["prior_tasks"], s["prior_stats"]) for s in prepared],
            "prepared_decision_node_mock": [lambda s=s: node(deepcopy(s)) for s in prepared],
            "report_decision_graph_mock": [lambda g=g, s=s: g.invoke(deepcopy(s)) for g, s in zip(graphs, states)],
        }
        for name, calls in operations.items():
            expected = [call() for call in calls]
            timings = measure(calls, expected, warmup=6, samples=120)
            stages[name] = {"summary": summarize(timings), "samples_ns": timings,
                "by_context": [{"symbol": row["symbol"], "cutoff": row["cutoff"],
                    **summarize(timings[index::len(points)])} for index, row in enumerate(context_receipts)]}
    adapter.verify_sources()
    require(dict(counts) == {"retriever_constructor": 1, "memory_load": 1}, "Đường nóng nạp lại kho")
    return {"status": "PASS", "scope": "observed_shared_reports_mock_decision",
        "configuration": {"provider": "historical_prefix", "mode": "bayesian_regime", "k": 3,
            "scope": "same_symbol", "seed": 42, "time_frame": "1d"},
        "cold_adapter_constructor_ms": constructor_ns / 1e6, "constructor_counts": dict(counts),
        "context_model_loads": model_loads, "contexts": context_receipts, "stages": stages,
        "method": {"clock": "perf_counter_ns", "percentile": "nearest_rank_ceil_0.95_n",
            "warmup_per_stage": 6, "samples_per_stage": 120, "samples_per_context_per_stage": 20,
            "includes_deep_copy_and_validation": True, "outlier_removal": False,
            "json_price_model_reload_blocked_after_prepare": True,
            "checksum_byte_io_retained": True, "graph_includes_mock_decision": True,
            "excluded": ["upstream/vision/Alpha", "checkpoint/fsync", "real LLM latency"]}}


def review() -> dict[str, Any]:
    """Giữ nguyên phương pháp W3; kết quả và giới hạn W4 ghi ở receipt mới."""
    with offline_guard() as hits:
        retrieval = benchmark()
        adapter = review_adapter()
    smoke = read_json(ROOT / "docs/plan/week4/integration_smoke.json")
    for path, expected in smoke["source_text_sha256"].items():
        require(hashlib.sha256((ROOT / path).read_text("utf-8").encode()).hexdigest() == expected,
                f"Smoke không thuộc code hiện tại: {path}")
    status = "PASS_OFFLINE_PERFORMANCE_REVIEW" if retrieval["status"] == "PASS" else "FAIL_RETRIEVAL_P95"
    return {"format_version": 1, "task": "W4-15", "status": status,
        "measured_at_utc": datetime.now(timezone.utc).isoformat(), "runtime": _runtime_identity(),
        "retrieval": retrieval, "adapter": adapter, "external_guard_hits": dict(hits),
        "runtime_budget": {"integration_smoke_path": "docs/plan/week4/integration_smoke.json",
            "integration_smoke_sha256": sha(ROOT / "docs/plan/week4/integration_smoke.json"),
            "backtest_report_caps": decision_agent._BACKTEST_REPORT_CHAR_LIMITS,
            "total_backtest_report_budget": sum(decision_agent._BACKTEST_REPORT_CHAR_LIMITS.values()),
            "synthetic_context_max_prompt": smoke["smoke"]["synthetic"]["max_prompt_length"],
            "observed_context_max_prompt": max(b["prompt_length"] for row in
                smoke["smoke"]["observed_replay"]["contexts"] for b in row["branches"]),
            "boundary_cases": smoke["smoke"]["budget"]["boundary_cases"],
            "templates": {"decision_template_sha256": canonical_hash({
                "vi": inspect.getsource(decision_agent._build_compact_prompt_vi),
                "en": inspect.getsource(decision_agent._build_compact_prompt_en),
                "reasoning": decision_agent._PRIOR_REASONING}),
                "brpp_template_sha256": hashlib.sha256(inspect.getsource(format_compact_prior_prefix).encode()).hexdigest()},
            "versions": VERSIONS, "runtime_budget_gate_passed": True},
        "source_text_sha256": {path: hashlib.sha256((ROOT / path).read_text("utf-8").encode()).hexdigest() for path in (
            "scripts/review_prior_integration_performance.py", "scripts/benchmark_bayesian_retriever.py",
            "core/prior_context.py", "core/prior_backtest.py", "core/decision_prior.py", "utils/graph_setup.py",
            "core/bayesian_memory.py", "core/bayesian_retriever.py", "agents/decision_agent.py")},
        "limits_vi": ["Benchmark W3 trong trường retrieval giữ phương pháp và ghi chú gốc; ghi chú handoff cap W4 cũ đã được đóng bằng runtime_budget của receipt này.",
            "Overhead adapter/graph có kiểm byte checksum, không áp ngưỡng p95 retrieval <30 ms cho các bước này.",
            "Đo phụ thuộc máy/tải nền; không đặt ngưỡng thời gian trong unit test, không suy ra hiệu năng LLM hoặc đầu tư OOS."],
        "real_llm_api_called": False, "oos_trading_backtest": False}


def main() -> int:
    """Ghi receipt mới trong W4; không ghi đè hoặc sửa receipt W3/W4 đã đóng băng."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if (not output.is_relative_to((ROOT / "docs/plan/week4").resolve())
            or output.suffix != ".json" or output.exists()):
        parser.error("Receipt mới phải ở docs/plan/week4, đuôi .json và chưa tồn tại")
    result = review()
    atomic_write_json(output, result)
    print(f"Đã lưu nghiệm thu hiệu năng: {output.relative_to(ROOT)}; {result['status']}", flush=True)
    return 0 if result["status"] == "PASS_OFFLINE_PERFORMANCE_REVIEW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
