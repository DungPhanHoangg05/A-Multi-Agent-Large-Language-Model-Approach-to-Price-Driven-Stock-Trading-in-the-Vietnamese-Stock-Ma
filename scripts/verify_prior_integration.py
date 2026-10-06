"""Smoke tích hợp offline; chỉ giả lập inference, giữ toàn bộ kiểm chứng nguồn.

Chạy từ Git bằng Python 3.13; archive W2 chỉ bổ sung replay quan sát riêng.
Không đọc key, tải dữ liệu, fit model hoặc ghi lại kho/receipt đã đóng băng.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
import gzip
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from time import perf_counter
from typing import Any, Iterator
from unittest.mock import patch

os.environ.setdefault("MPLBACKEND", "Agg")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import numpy as np
import pandas as pd
from langchain_core.messages import AIMessage

from agents.decision_agent import TradeDecisionOutput, create_final_trade_decider
from core.backtest_engine import BacktestEngine, PRIOR_BRANCH_MODES, compute_round_trip_net_return
from core.bayesian_memory import atomic_write_json
from core.bayesian_retriever import format_compact_prior_prefix
from core.prior_backtest import ResearchSchema, canonical_hash
from core.prior_checkpoint import CheckpointSession, read_document
from core.prior_context import PriorContextAdapter, REPORT_FIELDS
from core.regime_detector import MarketRegimeDetector, _payload_hash, _regime_calibration
from prior_context_test_support import ContextFixture, model_file, write_json
from scripts.run_end_to_end_test import DeterministicVisionLLM, OfflineBacktestEngine, _working_directory
from scripts.verify_prior_prompt_budget import prefix_fixture, report_fixture
from utils.graph_setup import ABLATION_CONFIGS, SetGraph
from utils.graph_util import TechnicalTools

REGIMES = ("BULL", "BEAR", "CHOPPY", "CONSOLIDATION")


def require(condition: bool, message: str) -> None:
    """Dừng smoke ngay khi hợp đồng không đạt, kể cả với Python tối ưu."""
    if not condition:
        raise AssertionError(message)


def sha(path: Path) -> str:
    """Băm byte thật của nguồn hoặc bằng chứng."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TextLLM:
    """Indicator và Decision xác định; response raw khớp action có schema."""

    def __init__(self, action: str = "LONG") -> None:
        self.action = action
        self.indicator_calls = 0
        self.decision_calls = 0

    def invoke(self, messages: Any) -> AIMessage:
        self.indicator_calls += 1
        return AIMessage(content="**Dominant consensus:** Bullish\nDiễn giải chỉ báo tổng hợp xác định.")

    def with_structured_output(self, schema: type, method: str | None = None,
                               include_raw: bool = False) -> StructuredBinding:
        require(schema is TradeDecisionOutput and method == "json_schema" and include_raw,
                "Decision không giữ hợp đồng structured/raw")
        return StructuredBinding(self)

    def _decision(self, prompt: str) -> dict[str, Any]:
        self.decision_calls += 1
        parsed = TradeDecisionOutput(decision=self.action, forecast_horizon="T+2.5", confidence="High",
            risk_reward_ratio=1.8, evidence_for="Tín hiệu fixture đồng thuận.",
            evidence_against="Giới hạn dữ liệu tổng hợp.", justification="Kiểm chứng kỹ thuật offline.")
        return {"parsed": parsed, "raw": AIMessage(content=parsed.model_dump_json()), "parsing_error": None}


class StructuredBinding:
    """Binding riêng để không nhầm lời gọi Indicator với Decision."""

    def __init__(self, owner: TextLLM) -> None:
        self.owner = owner

    def invoke(self, prompt: str) -> dict[str, Any]:
        return self.owner._decision(prompt)


@contextmanager
def offline_guard() -> Iterator[Counter[str]]:
    """Chặn cả transport, client thật, fit và crawl; đếm mọi lần chạm guard."""
    hits: Counter[str] = Counter()
    def forbidden(name: str) -> Any:
        def stop(*args: Any, **kwargs: Any) -> None:
            hits[name] += 1
            raise AssertionError(f"Smoke offline cấm {name}")
        return stop
    with ExitStack() as stack:
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.getaddrinfo",
                       "requests.sessions.Session.request", "httpx.Client.send", "httpx.AsyncClient.send",
                       "langchain_groq.ChatGroq.invoke", "langchain_groq.ChatGroq._generate",
                       "core.regime_detector.MarketRegimeDetector.fit",
                       "data_manager.sentiment_cache.SentimentCache.preload"):
            stack.enter_context(patch(target, side_effect=forbidden(target)))
        yield hits
        require(not hits, f"Có đường gọi ngoại vi bị bắt rồi bỏ qua: {dict(hits)}")


def synthetic_fixture(regime: str, language: str, eligible_count: int) -> ContextFixture:
    """Dựng giá/model bốn chế độ; detector/loader thật tự phân loại, không patch state."""
    fx = ContextFixture(lang=language)
    try:
        # Timestamp gzip không được làm provenance fixture thay đổi giữa hai lượt.
        price_manifest_path = fx.root / "data/execution_prices/manifest.json"
        price_manifest = json.loads(price_manifest_path.read_text("utf-8"))
        for symbol, item in price_manifest["files"].items():
            evidence = price_manifest_path.parent / item["evidence"]["file"]
            evidence.write_bytes(gzip.compress(gzip.decompress(evidence.read_bytes()), mtime=0))
            item["evidence"]["sha256"] = sha(evidence)
        write_json(price_manifest_path, price_manifest)
        index = np.arange(700, dtype=float)
        curves = {"BULL": 1000 * np.exp(.002 * index), "BEAR": 1000 * np.exp(-.002 * index),
                  "CHOPPY": 1000 * np.exp(.04 * np.sin(index * 2)),
                  "CONSOLIDATION": 1000 + .01 * np.sin(index / 10)}
        close = curves[regime]
        fx.vnindex = pd.DataFrame({"Datetime": fx.dates, "Open": close, "High": close + 1,
                                  "Low": close - 1, "Close": close, "Volume": 1000})
        path = fx.root / "data/historical/VNINDEX.csv"
        fx.vnindex.to_csv(path, index=False, date_format="%Y-%m-%d", float_format="%.17g")
        fx.vnindex = pd.read_csv(path, parse_dates=["Datetime"])
        manifest_path = path.parent / "manifest.json"
        manifest = json.loads(manifest_path.read_text("utf-8"))
        manifest["files"]["VNINDEX"]["sha256"] = sha(path)
        write_json(manifest_path, manifest)
        artifact = fx.root / f"run/regimes/VNINDEX-{fx.cutoff}.json"
        model_file(artifact, fx.vnindex.iloc[:645])
        document = json.loads(artifact.read_text("utf-8"))
        meta = document["payload"]["metadata"]
        # Artifact tổng hợp dùng fallback đã chốt; không giả định đã fit/hội tụ.
        meta.update(em_converged=False, last_gain=.02)
        meta.update(_regime_calibration(meta))
        document["sha256"] = _payload_hash(document["payload"])
        write_json(artifact, document)
        state = MarketRegimeDetector.load(artifact).classify_regime(fx.vnindex.iloc[:645], fx.cutoff)
        require(state["regime_name"] == regime, "Detector thật không phân loại đúng fixture")
        fx.records = [fx.record(p, regime) for p in (600, 603, 606)[:eligible_count]]
        fx.records.append(fx.record(644, regime))  # Chu kỳ chưa đóng giữ kho khác rỗng.
        fx.publish_bank("a" * 64)
        return fx
    except BaseException:
        fx.close()
        raise


def engine(config: dict[str, Any]) -> BacktestEngine:
    """Engine public với cấu hình ma trận đã khóa và không delay fixture."""
    result = BacktestEngine({**config["models"], "language": config["language"],
        "alpha_norm_method": config["norm_method"], "alpha_weights": config["alpha_weights"],
        "use_historical_sentiment": False})
    result.DELAY_BETWEEN_VARIANTS = result.DELAY_BETWEEN_TESTS = 0.
    return result


def project(document: dict[str, Any]) -> dict[str, Any]:
    """So nội dung khoa học, bỏ ID/thời gian attempt và latency vận hành."""
    return {"shared": document["shared"], "evaluation": document["evaluation"],
            "branches": {name: {"input": branch["input"], "decision": {
                key: value for key, value in branch["decision"].items() if key != "latency_seconds"}}
                for name, branch in document["branches"].items()}}


class SmokeCrash(BaseException):
    """Ngắt sau commit durable để thử resume không gọi lại upstream/Full."""


def synthetic_case(regime: str, language: str, eligible_count: int) -> dict[str, Any]:
    """Chạy public runner, đảo nhánh, crash rồi resume với file/graph thật."""
    fx = synthetic_fixture(regime, language, eligible_count)
    try:
        adapter = fx.adapter()
        text, vision = TextLLM("SHORT" if eligible_count % 2 else "LONG"), DeterministicVisionLLM()
        builder = SetGraph(text, vision, TechnicalTools())
        schema = ResearchSchema()
        from agents.alpha_agent import _compute_all_alphas
        from agents.indicator_agent import _compute_all_indicators
        with (patch("agents.alpha_agent._compute_all_alphas", wraps=_compute_all_alphas) as alpha,
              patch("agents.indicator_agent._compute_all_indicators", wraps=_compute_all_indicators) as indicator):
            def run(directory: str, resume: bool = False) -> dict[str, Any]:
                return engine(fx.config).run_prior_backtest("FPT", adapter=adapter, graph_builder=builder,
                    output_dir=fx.root / directory, cutoffs=(fx.cutoff,),
                    execution_mode="offline_fixture", resume=resume)
            continuous = run("continuous")
            require(continuous["status"] == "complete", "Runner chưa đóng điểm")
            path = f"points/FPT-{fx.cutoff}.json"
            completed = read_document(fx.root / "continuous" / path, schema, "point")
            require((indicator.call_count, text.indicator_calls, vision.calls, text.decision_calls, alpha.call_count)
                    == (1, 0, 2, 5, 1),
                    "Upstream/Full/Decision không chạy đúng một lần/năm nhánh")
            pair = engine(fx.config).run_prior_point(adapter.prepare("FPT", fx.cutoff), graph_builder=builder,
                branch_order=tuple(reversed(PRIOR_BRANCH_MODES)))
            for name, branch in pair["branches"].items():
                state, saved = branch["state"], completed["branches"][name]["input"]
                require(pair["full_bundle"] == completed["shared"]["full_bundle"], "Đảo nhánh đổi reports/Full")
                for field in ("prior_tasks", "prior_stats", "prior_metadata", "bayesian_prior_context"):
                    require(state[field] == saved[field], f"Đảo nhánh đổi {field}")
                require(state["decision_prompt"] == saved["prompt"]["text"], "Đảo nhánh đổi prompt")
            def crash(session: CheckpointSession, event: str) -> None:
                if event == "branch_complete:random":
                    raise SmokeCrash(event)
            with patch.object(CheckpointSession, "_after_commit", crash):
                try:
                    run("resumed")
                except SmokeCrash:
                    pass
                else:
                    raise AssertionError("Không chạm ranh giới crash")
            stopped = read_document(fx.root / "resumed" / path, schema, "point")
            saved = deepcopy({name: stopped["branches"][name] for name in ("original", "random")})
            before = (indicator.call_count, vision.calls, alpha.call_count, text.decision_calls)
            resumed = run("resumed", resume=True)
            after = read_document(fx.root / "resumed" / path, schema, "point")
            require((indicator.call_count, vision.calls, alpha.call_count) == before[:3], "Resume gọi lại upstream/Full")
            require(text.decision_calls - before[3] == 3, "Resume không gọi đúng ba Decision còn thiếu")
            require(all(after["branches"][name] == value for name, value in saved.items()), "Resume sửa nhánh complete")
            require(project(after) == project(completed), "Resume đổi reports/IDs/stats/prefix/kinh tế")
            require(resumed["summary"] == continuous["summary"], "Resume đổi thống kê tài khoản")
            stable = (fx.root / "resumed" / path).read_bytes()
            calls = text.decision_calls
            run("resumed", resume=True)
            require(text.decision_calls == calls and (fx.root / "resumed" / path).read_bytes() == stable,
                    "Resume complete không idempotent")
            calls = {"indicator": indicator.call_count, "vision": vision.calls,
                     "full_alpha": alpha.call_count, "decision": text.decision_calls}
            require(calls == {"indicator": 3, "vision": 6, "full_alpha": 3, "decision": 15},
                    "Sai tổng call-count continuous/đảo nhánh/resume")
        evaluation = completed["evaluation"]
        expected_net = float(compute_round_trip_net_return(float(fx.frame["FPT"].Open.iloc[645]),
                                                           float(fx.frame["FPT"].Close.iloc[647])))
        require(evaluation["entry_date"] == fx.day(645) and evaluation["exit_date"] == fx.day(647)
                and evaluation["net_return_long"] == expected_net, "Kinh tế không giữ Open(t+1)/Close(t+3)")
        require(all(value["cycle_net_return"] == (expected_net if text.action == "LONG" else 0.)
                    and value["executed_action"] == ("BUY_SELL" if text.action == "LONG" else "CASH")
                    for value in evaluation["branches"].values()), "LONG/SHORT hoặc phí hai chiều sai")
        # K=1/2 bổ sung trên chính Full đã seal; ma trận public vẫn K=0/3.
        point = adapter.prepare("FPT", fx.cutoff)
        shared = point.restore_full_bundle(completed["shared"]["full_bundle"])
        extra = []
        for k in (1, 2):
            for mode in ("random", "recent", "similarity", "bayesian_regime"):
                state = deepcopy(shared)
                state["prior_config"].update(mode=mode, k=k)
                result = builder.compile_report_decision(prior_config=state["prior_config"],
                    prior_retriever=point.retrieve, prior_source_validator=point.verify_source).invoke(state)
                require(result["prior_metadata"]["selected_count"] == min(k, eligible_count), "K bổ sung chọn sai số task")
                extra.append({"k": k, "mode": mode, "selected": result["prior_metadata"]["selected_count"],
                              "prompt_length": len(result["decision_prompt"]),
                              "prefix_length": len(result["bayesian_prior_context"])})
        branches = []
        for name, branch in completed["branches"].items():
            inputs = branch["input"]
            require(inputs["prior_metadata"]["selected_count"] == (0 if name == "original" else eligible_count),
                    "Public matrix chọn sai số task")
            branches.append({"branch": name, "requested_k": inputs["prior_config"]["k"],
                "selected_ids": inputs["prior_metadata"]["selected_ids"], "status": inputs["prior_metadata"]["status"],
                "stats": inputs["prior_stats"], "prefix_length": len(inputs["bayesian_prior_context"]),
                "prompt_length": inputs["prompt"]["char_count"], "prompt_sha256": inputs["prompt"]["sha256"]})
        adapter.verify_sources()
        json.dumps((completed, after, extra), allow_nan=False)
        return {"source_kind": "synthetic", "language": language, "regime": regime, "eligible_count": eligible_count,
            "action": text.action, "calls_before_extra_k": calls, "extra_k_decisions": len(extra),
            "shared_sha256": completed["shared"]["shared_sha256"], "evaluation": evaluation,
            "branches": branches, "extra_k": extra, "continuous_reverse_resume_equal": True,
            "complete_resume_unchanged": True, "completed_branch_fields_preserved": True}
    finally:
        fx.close()


def legacy_smoke() -> dict[str, Any]:
    """Kiểm entry point cũ/bốn ablation khi prior tắt, cấm nạp kho và regime."""
    fx = ContextFixture(lang="en")
    try:
        with tempfile.TemporaryDirectory(prefix="prior_legacy_") as temporary, ExitStack() as stack:
            for target in ("core.prior_context.PriorContextAdapter.__init__",
                           "core.bayesian_retriever.BayesianPriorRetriever.__init__",
                           "core.bayesian_memory.HistoricalMemory.load",
                           "core.regime_detector.MarketRegimeDetector.load"):
                stack.enter_context(patch(target, side_effect=AssertionError("Flag off nạp bank/model")))
            old = OfflineBacktestEngine(Path(temporary))
            old._use_historical_sentiment = False
            old._init_graphs()
            snapshot = fx.frame["FPT"].iloc[:645].copy()
            kline = {key: snapshot.tail(45)[key].tolist() for key in snapshot.columns}
            with _working_directory(Path(temporary)):
                variants = old._run_ablation_variants(kline, "FPT", "1d", fx.cutoff, snapshot)
                full, _, baseline, _ = old._run_paired_point(kline, "FPT", "1d", fx.cutoff, snapshot)
                builder = SetGraph(old.text_llm, old.vision_llm, TechnicalTools())
                state = {"stock_name": "FPT", "time_frame": "1d", "language": "en", "is_backtest": True,
                    "kline_data": kline, "point_in_time_df": snapshot, "window_end_date": fx.cutoff,
                    "pattern_image": "fixture", "trend_image": "fixture"}
                outputs = []
                # Ảnh thật đã tạo ở engine phía trên; dùng lại base64 của file PNG.
                import base64
                state["pattern_image"] = base64.b64encode((Path(temporary) / "kline_chart.png").read_bytes()).decode()
                state["trend_image"] = base64.b64encode((Path(temporary) / "trend_graph.png").read_bytes()).decode()
                for name, config in ABLATION_CONFIGS.items():
                    output = builder.set_graph(ablation_config=config).invoke({**state, "ablation_config": config})
                    outputs.append(name)
                    require(output["final_trade_decision"], "set_graph không trả Decision")
                for include in (False, True):
                    output = builder.compile_decision(include_alpha=include).invoke(deepcopy(full))
                    require(output["final_trade_decision"], "Alias include_alpha không trả Decision")
                output = builder.compile_report_decision(prior_config={"enable_bayesian_prior": False}).invoke(deepcopy(full))
                require(output["final_trade_decision"], "Graph report flag off thiếu Decision")
            require(set(variants) == set(ABLATION_CONFIGS) and full["alpha_report"] and not baseline.get("alpha_report"),
                    "Legacy paired/ablation đổi output")
            return {"status": "PASS", "ablations": outputs, "prior_bank_model_loads": 0,
                    "entrypoints": ["_run_ablation_variants", "_run_paired_point", "set_graph",
                                    "compile_decision(include_alpha)", "compile_report_decision(prior_off)"],
                    "legacy_run_e2e": "Kiểm riêng bằng scripts/run_end_to_end_test.py trong bốn gate"}
    finally:
        fx.close()


def budget_smoke() -> dict[str, Any]:
    """Biên formatter 600 và guard Decision 6499/6500, không patch cap/builder."""
    tasks, stats = prefix_fixture(population=10**25)
    prefix = format_compact_prior_prefix(tasks, stats)
    require(len(prefix) == 600, "Formatter không đạt fixture biên 600")
    rows = []
    for language in ("vi", "en"):
        reports = report_fixture(language)
        state = {"stock_name": "FPT", "time_frame": "1d", "language": language, "is_backtest": True,
                 **{name + "_report": value for name, value in reports.items()}}
        text = TextLLM()
        # Preparer tổng hợp chỉ dành cho dự phòng prefix, không là bằng chứng nguồn PIT.
        node = create_final_trade_decider(text, _prior_preparer=lambda value: (value, prefix))
        result = node(state)
        base = len(result["decision_prompt"])
        require(base < 6500 and prefix in result["decision_prompt"], "Cap runtime không dự phòng prefix 600")
        for target in (6499, 6500):
            before = text.decision_calls
            padded = {**state, "stock_name": "FPT" + "Đ" * (target - base)}
            try:
                result = node(padded)
            except ValueError as error:
                require(target == 6500 and "6500" in str(error), "Guard báo lỗi sai biên")
                require(text.decision_calls == before, "Guard 6500 vẫn gọi LLM")
            else:
                require(target == 6499 and len(result["decision_prompt"]) == target
                        and text.decision_calls == before + 1, "Guard 6499 không nhận prompt hợp lệ")
            rows.append({"language": language, "prefix_length": 600, "prompt_length": target,
                         "accepted": target == 6499, "decision_calls": text.decision_calls - before})
    return {"source_kind": "synthetic_budget_only", "boundary_cases": rows,
            "runtime_caps_unpatched": True, "prefix_char_limit": 600, "prompt_char_limit_exclusive": 6500}


def observed_replay() -> dict[str, Any]:
    """Xác minh lại journal/episode/model/kho thật; chỉ mock Decision, không tính OOS."""
    contexts = (("FPT", "2022-12-27"), ("MWG", "2022-12-27"), ("VCB", "2022-12-27"),
                ("VNM", "2022-12-27"), ("FPT", "2020-06-04"), ("FPT", "2022-03-04"))
    bank = ROOT / "data_manager/regime_memory_store.json"
    initial = {path.relative_to(ROOT).as_posix(): sha(path) for path in
        (bank, bank.with_suffix(".manifest.json"), ROOT / "docs/plan/week2/memory_bank_audit.json")}
    try:
        adapter = PriorContextAdapter({"enable_bayesian_prior": True})
        require(len(adapter._retriever._memory.records) == 852, "Replay không nhận kho 852 đã chốt")
        text = TextLLM()
        builder = SetGraph(text, object(), object())
        rows = []
        for symbol, cutoff in contexts:
            point = adapter.prepare(symbol, cutoff)
            shared = point.load_shared_checkpoint("outputs/historical_memory_run")
            outputs = {}
            for order in (tuple(PRIOR_BRANCH_MODES), tuple(reversed(PRIOR_BRANCH_MODES))):
                for name in order:
                    state = deepcopy(shared)
                    mode, k = PRIOR_BRANCH_MODES[name]
                    state["prior_config"].update(mode=mode, k=k)
                    output = builder.compile_report_decision(prior_config=state["prior_config"],
                        prior_retriever=point.retrieve, prior_source_validator=point.verify_source).invoke(state)
                    compact = {key: output[key] for key in (*REPORT_FIELDS, "prior_tasks", "prior_stats",
                        "prior_metadata", "bayesian_prior_context", "decision_prompt", "final_trade_decision")}
                    if name in outputs:
                        require(compact == outputs[name], "Replay/đảo nhánh đổi reports/IDs/stats/prefix")
                    outputs[name] = compact
            rows.append({"symbol": symbol, "cutoff": cutoff, "regime": shared["market_regime"]["regime_name"],
                "source_provenance": shared["prior_provenance"], "reports_sha256": canonical_hash({
                    key: shared[key] for key in REPORT_FIELDS}), "branches": [{"branch": name,
                    "selected_ids": output["prior_metadata"]["selected_ids"], "stats": output["prior_stats"],
                    "status": output["prior_metadata"]["status"], "prefix_length": len(output["bayesian_prior_context"]),
                    "prompt_length": len(output["decision_prompt"])} for name, output in outputs.items()]})
        adapter.verify_sources()
        require(all(sha(ROOT / path) == value for path, value in initial.items()), "Replay sửa kho/manifest/QA")
        require(text.decision_calls == 60 and text.indicator_calls == 0, "Replay gọi lại upstream")
        return {"status": "PASS", "source_kind": "observed_historical_inputs_mock_decision", "bank_records": 852,
            "bank_manifest_qa_sha256": initial, "context_count": len(rows), "distinct_branch_count": 30,
            "decision_calls_including_reversed_order": text.decision_calls,
            "coverage_by_symbol": dict(Counter(row["symbol"] for row in rows)),
            "coverage_by_regime": dict(Counter(row["regime"] for row in rows)), "contexts": rows,
            "oos_trading_result": False, "historical_shared_reports_reused": True}
    except FileNotFoundError as error:
        return {"status": "BLOCKED", "source_kind": "observed", "reason": f"Thiếu archive/proof local: {error.filename}",
                "completed_contexts": len(locals().get("rows", [])), "oos_trading_result": False}


def verify(*, replay: bool = True) -> dict[str, Any]:
    """Chạy smoke bắt buộc từ Git; replay local được báo trạng thái riêng."""
    require(sys.version_info[:2] == (3, 13), "Smoke yêu cầu Python 3.13")
    started = perf_counter()
    with offline_guard() as hits:
        cases = []
        for index, regime in enumerate(REGIMES):
            for language in ("vi", "en"):
                print(f"[Smoke] Tổng hợp {regime}/{language}, eligible={index}", flush=True)
                cases.append(synthetic_case(regime, language, index))
        legacy, budget = legacy_smoke(), budget_smoke()
        observed = observed_replay() if replay else {"status": "NOT_REQUESTED", "source_kind": "observed"}
    rows = [branch for case in cases for branch in (*case["branches"], *case["extra_k"])]
    maximum = max(row["prompt_length"] for row in rows)
    require(maximum < 6500 and max(row["prefix_length"] for row in rows) <= 600, "Smoke runtime vượt budget")
    sources = ("scripts/verify_prior_integration.py", "tests/prior_context_test_support.py",
               "scripts/run_end_to_end_test.py", "scripts/verify_prior_prompt_budget.py")
    return {"format_version": 1, "status": "PASS_OFFLINE_SYNTHETIC", "python": platform.python_version(),
        "elapsed_seconds": round(perf_counter() - started, 3), "source_text_sha256": {
            path: hashlib.sha256((ROOT / path).read_text("utf-8").encode()).hexdigest() for path in sources},
        "synthetic": {"status": "PASS", "context_count": len(cases),
            "public_branch_outputs": sum(len(case["branches"]) for case in cases),
            "decision_calls_continuous_reverse_resume": sum(case["calls_before_extra_k"]["decision"] for case in cases),
            "extra_k_decisions": sum(case["extra_k_decisions"] for case in cases),
            "max_prompt_length": maximum, "max_prefix_length": max(row["prefix_length"] for row in rows),
            "regimes": list(REGIMES), "languages": ["vi", "en"], "requested_k": [0, 1, 2, 3], "cases": cases},
        "legacy": legacy, "budget": budget, "observed_replay": observed, "external_guard_hits": dict(hits),
        "inference_mocks": ["Pattern/Trend vision", "Decision structured/raw"],
        "real_runtime": ["charts/indicators/Alpha", "execution labels and evaluation", "PIT/source/model validation",
            "retriever/ranking/statistics", "formatter/runtime prompt builder", "LangGraph", "checkpoint/OS lock/resume"],
        "real_llm_api_called": False, "oos_trading_backtest": False,
        "limitations_vi": "Fixture tổng hợp không chứng minh hiệu quả đầu tư. Replay dùng tin/báo cáo W2 và Decision giả; không mở gate OOS/pilot."}


def main() -> int:
    """CLI ghi receipt tại đường dẫn được yêu cầu; checkpoint chỉ nằm trong thư mục tạm."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Đường dẫn receipt mới; không ghi đè bằng chứng cũ")
    parser.add_argument("--skip-observed", action="store_true", help="Chỉ chạy smoke bắt buộc tái lập từ Git")
    args = parser.parse_args()
    if args.output is not None and args.output.exists():
        parser.error("Receipt đã tồn tại; chọn đường dẫn mới")
    result = verify(replay=not args.skip_observed)
    if args.output is not None:
        atomic_write_json(args.output, result)
    print(json.dumps({"status": result["status"], "synthetic": result["synthetic"]["context_count"],
                      "observed_replay": result["observed_replay"]["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
