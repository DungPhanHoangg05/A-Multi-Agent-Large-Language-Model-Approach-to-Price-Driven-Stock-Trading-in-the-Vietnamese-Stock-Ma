"""Walk-forward nghiên cứu, checkpoint từng nhánh và kết quả kinh tế."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from agents.decision_agent import TradeDecisionOutput
from core.backtest_engine import (BacktestEngine, PRIOR_BRANCH_MODES, TestPoint,
    build_walk_forward_end_indices, compute_account_metrics, compute_round_trip_net_return)
from core.bayesian_memory import atomic_write_json, iso_date, read_json
from core.bayesian_retriever import VERSIONS, format_compact_prior_prefix
from core.execution_prices import execution_prices_for_cycle
from core.historical_signals import CODE_FILES, digest
from core.prior_config import copy_prior_json, normalize_prior_config, validate_prior_execution
from core.prior_context import PriorContextAdapter, REPORT_FIELDS, _runtime_identity
from utils import graph_setup, decision_parser

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "prior_research_checkpoint_v1"


def canonical_hash(value: Any) -> str:
    """Hash checkpoint mới; không đổi digest snapshot/journal W2."""
    content = json.dumps(copy_prior_json(value), sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ResearchSchema:
    """Resolve schema đã khóa từ repo, không tải tham chiếu trên mạng."""

    def __init__(self) -> None:
        schemas = [read_json(ROOT / path) for path in (
            "docs/plan/week4/research_checkpoint.schema.json",
            "docs/plan/week1/historical_task_record.schema.json",
            "docs/plan/week1/market_regime_state.schema.json")]
        def reject_network(uri: str) -> Resource:
            raise ValueError("Schema nghiên cứu không được resolve nguồn ngoài repo")
        registry = Registry(retrieve=reject_network)
        for schema in schemas:
            registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
        self.schema, self.registry = schemas[0], registry

    def validate(self, value: dict[str, Any], definition: str | None = None) -> None:
        """Kiểm native/finite rồi kiểm schema; lỗi shape phải dừng trước ghi file."""
        value = copy_prior_json(value)
        schema = self.schema if definition is None else {"$ref": f"{self.schema['$id']}#/$defs/{definition}"}
        errors = list(Draft202012Validator(schema, registry=self.registry).iter_errors(value))
        if errors:
            raise ValueError(f"Kết quả nghiên cứu sai schema tại {list(errors[0].absolute_path)}")


def write_document(path: Path, payload: dict[str, Any], schema: ResearchSchema,
                   definition: str | None = None) -> str:
    """Ghi envelope strict/atomic; trả SHA byte file thật, không nuốt lỗi đĩa."""
    schema.validate(payload, definition)
    atomic_write_json(path, {"payload": payload, "sha256": canonical_hash(payload)})
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_point(frame: pd.DataFrame, events: list[dict[str, Any]], cutoff: str,
                   branches: dict[str, Any]) -> dict[str, Any]:
    """Chấm sau Decision bằng Open(t+1)/Close(t+3) và hàm kinh tế duy nhất."""
    iso_date(cutoff)
    dates = pd.DatetimeIndex(frame.Datetime)
    index = int(dates.get_indexer([pd.Timestamp(cutoff)])[0])
    if index < 0 or index + 3 >= len(frame):
        raise ValueError("Thiếu phiên quyết định/entry/exit cho chu kỳ T+2.5")
    entry, exit_date = dates[index + 1].strftime("%Y-%m-%d"), dates[index + 3].strftime("%Y-%m-%d")
    entry_open, exit_close = execution_prices_for_cycle(frame, events, cutoff, entry, exit_date)
    net = float(compute_round_trip_net_return(entry_open, exit_close))
    actual = "UP" if net > 0 else "DOWN"
    if type(branches) is not dict or set(branches) != set(PRIOR_BRANCH_MODES):
        raise ValueError("Chỉ chấm điểm đủ năm Decision hợp lệ")
    evaluated = {}
    for name, branch in branches.items():
        action = branch["decision"]["action"]
        if branch["status"] != "complete" or action not in ("LONG", "SHORT"):
            raise ValueError("Nhánh chưa hoàn tất không được chấm thành CASH")
        evaluated[name] = {"correct": bool((action == "LONG") == (actual == "UP")),
            "executed_action": "BUY_SELL" if action == "LONG" else "CASH",
            "cycle_net_return": net if action == "LONG" else 0.0}
    return {"entry_date": entry, "exit_date": exit_date, "entry_open": entry_open,
            "exit_close": exit_close, "net_return_long": net, "actual_direction": actual,
            "branches": evaluated}


def summarize_points(points: list[dict[str, Any]]) -> dict[str, Any]:
    """Common support năm nhánh; metric tài khoản tái sử dụng engine hiện tại."""
    summary = {}
    for name in PRIOR_BRANCH_MODES:
        if not points:
            summary[name] = {"sample_count": 0, "correct_count": 0, "long_count": 0,
                             "short_count": 0, "accuracy": None, "account_metrics": None}
            continue
        test_points = []
        for index, point in enumerate(points):
            if point["status"] != "complete" or set(point["branches"]) != set(PRIOR_BRANCH_MODES):
                raise ValueError("Summary chỉ nhận điểm hoàn tất trên common support")
            evaluation, decision = point["evaluation"], point["branches"][name]["decision"]
            action = decision["action"]
            if any(branch["status"] != "complete" for branch in point["branches"].values()):
                raise ValueError("Không chấm riêng nhánh thành công của điểm còn dở")
            # Hai field prediction chỉ phục vụ API tính tài khoản cũ bên trong;
            # output nghiên cứu vẫn giữ năm branch ID, không ánh xạ thành ablation.
            test_points.append(TestPoint(test_id=index + 1,
                window_start=point["source_proof"]["prices"]["snapshot_start_date"],
                window_end=point["context"]["as_of_date"], actual_prev_close=0.,
                actual_next_close=evaluation["exit_close"], actual_direction=evaluation["actual_direction"],
                actual_pct_change=evaluation["net_return_long"] * 100.,
                pred_full=action, pred_no_alpha=action,
                correct_full=evaluation["branches"][name]["correct"], correct_no_alpha=evaluation["branches"][name]["correct"],
                confidence_full=decision["confidence"], confidence_no_alpha=decision["confidence"],
                rr_full=decision["risk_reward_ratio"], rr_no_alpha=decision["risk_reward_ratio"],
                time_full_sec=point["branches"][name]["decision"]["latency_seconds"], time_no_alpha_sec=0.,
                entry_open=evaluation["entry_open"], exit_close=evaluation["exit_close"],
                entry_time=evaluation["entry_date"], exit_time=evaluation["exit_date"]))
        metrics = compute_account_metrics(test_points)["full"]
        count = len(points)
        correct = sum(int(point["evaluation"]["branches"][name]["correct"]) for point in points)
        longs = sum(point["branches"][name]["decision"]["action"] == "LONG" for point in points)
        summary[name] = {"sample_count": count, "correct_count": correct, "long_count": int(longs),
                         "short_count": count - int(longs), "accuracy": float(correct / count),
                         "account_metrics": copy_prior_json(asdict(metrics))}
    return summary


class PriorBacktestRunner:
    """Điều phối nhiều cutoff; adapter/retriever được caller nạp một lần trước run."""

    def __init__(self, engine: BacktestEngine, adapter: PriorContextAdapter,
                 builder: graph_setup.SetGraph, *, execution_mode: str = "research") -> None:
        if not isinstance(adapter, PriorContextAdapter) or not isinstance(builder, graph_setup.SetGraph):
            raise ValueError("Backtest cần adapter đã xác minh và builder đúng loại")
        if execution_mode not in ("research", "offline_fixture"):
            raise ValueError("execution_mode nghiên cứu không hợp lệ")
        self.engine, self.adapter, self.builder = engine, adapter, builder
        self.config = adapter.signal_config
        self.mode, self.schema = execution_mode, ResearchSchema()
        if adapter.prior_config["seed"] != 42 or adapter.prior_config["scope"] != "same_symbol":
            raise ValueError("Ma trận nghiên cứu khóa seed=42 và scope=same_symbol")
        for key, expected in {**self.config["models"], "language": self.config["language"],
                              "alpha_norm_method": self.config["norm_method"], "alpha_weights": self.config["alpha_weights"]}.items():
            actual = engine.config.get(key, "zscore_tanh" if key == "alpha_norm_method" else None)
            if digest(actual) != digest(expected):
                raise ValueError(f"Cấu hình engine khác Full đã khóa: {key}")
        for key, expected in (("tx_cost", .0025), ("slippage", .001),
                              ("initial_capital_vnd", 50_000_000.), ("price_multiplier", 1000.)):
            if type(engine.config[key]) not in (int, float) or engine.config[key] != expected:
                raise ValueError("Nghiên cứu giữ nguyên phí/vốn/đơn vị kinh tế đã khóa")
        if engine.config.get("allow_shorting") is not False:
            raise ValueError("Nghiên cứu chỉ cho SHORT giữ CASH")
        if execution_mode == "research":
            from langchain_groq import ChatGroq
            for role, llm in (("agent", builder.agent_llm), ("graph", builder.graph_llm)):
                if (not isinstance(llm, ChatGroq) or llm.model_name != self.config["models"][f"{role}_llm_model"]
                        or llm.temperature != self.config["models"][f"{role}_llm_temperature"]
                        or llm.max_tokens != self.config["models"][f"{role}_llm_max_tokens"]):
                    raise ValueError("Client nghiên cứu không khớp model/config; fixture phải khai offline_fixture")

    def _identity(self, symbol: str, step: int, contexts: list[Any]) -> dict[str, Any]:
        """Khóa cấu hình/nguồn/model/code; không đọc hoặc ghi credentials."""
        from agents import decision_agent
        sources = {}
        for point in contexts:
            proof = point.source_provenance
            for group in ("prices", "news", "regime", "bank"):
                for key, path in proof[group].items():
                    sha_key = key.replace("_path", "_sha256")
                    if key.endswith("_path") and sha_key in proof[group]:
                        if path in sources and sources[path] != proof[group][sha_key]:
                            raise ValueError("Cùng path nguồn có hai checksum")
                        sources[path] = proof[group][sha_key]
        matrix = [{"branch_id": name, "prior_config": normalize_prior_config({
            **self.adapter.prior_config, "mode": mode, "k": k}),
            "ablation": dict(graph_setup.ABLATION_CONFIGS["full"])} for name, (mode, k) in PRIOR_BRANCH_MODES.items()]
        config = self.config
        code_files = (*CODE_FILES, "core/backtest_engine.py", "core/prior_context.py", "core/prior_backtest.py",
                      "core/prior_config.py", "core/decision_prior.py", "core/bayesian_retriever.py", "agents/decision_agent.py",
                      "core/prior_checkpoint.py", "core/prior_run_lock.py",
                      "docs/plan/week4/research_checkpoint.schema.json", "docs/plan/week4/checkpoint_policy.json",
                      "docs/plan/week1/historical_task_record.schema.json", "docs/plan/week1/market_regime_state.schema.json")
        identity = {"identity_version": "prior_run_identity_v1", "protocol": "five_way_full_shared_pit",
            "versions": {"state_contract": "prior_runtime_contract_v1", "provenance": "prior_provenance_v1",
                "checkpoint": SCHEMA_VERSION, "hash_algorithm": "prior_checkpoint_canonical_json_v1",
                "retriever": dict(VERSIONS), "state_projection": "prior_state_projection_v1", "prompt_pipeline": "prior_decision_prompt_v1"},
            "matrix": matrix, "run_config": {"symbols": [symbol], "time_frame": "1d", "language": config["language"],
                "window_size": config["window_size"], "step": step, "lookahead_candles": 3,
                "alpha_norm_method": config["norm_method"], "alpha_weights": config["alpha_weights"],
                "fee": .0025, "slippage": .001, "initial_capital_vnd": 50_000_000., "price_multiplier": 1000., "execution_mode": self.mode},
            "bank": contexts[0].source_provenance["bank"],
            "sources": {"provider_mode": contexts[0].source_provenance["context"]["provider_mode"],
                "files": [{"path": path, "sha256": sha} for path, sha in sorted(sources.items())],
                "frozen_model": contexts[0].source_provenance["regime"]["frozen_model"]},
            "models": {"provider": "groq" if self.mode == "research" else "offline_fixture", **config["models"],
                "backend": "auto-structured-or-text/include_raw", "structured_output_schema_sha256": canonical_hash(TradeDecisionOutput.model_json_schema())},
            "templates": {"decision_template_sha256": canonical_hash({
                "vi": inspect.getsource(decision_agent._build_compact_prompt_vi),
                "en": inspect.getsource(decision_agent._build_compact_prompt_en), "reasoning": decision_agent._PRIOR_REASONING}),
                "brpp_template_sha256": hashlib.sha256(inspect.getsource(format_compact_prior_prefix).encode()).hexdigest()},
            "code_sha256": {path: hashlib.sha256((ROOT / path).read_text("utf-8").encode()).hexdigest() for path in code_files},
            "runtime": _runtime_identity(),
            "point_plan": [{"point_id": f"{symbol}-{point.source_provenance['context']['as_of_date']}",
                "context": {"symbol": symbol, "as_of_date": point.source_provenance["context"]["as_of_date"], "time_frame": "1d"},
                "source_sha256": canonical_hash({key: point.source_provenance[key] for key in ("context", "prices", "news", "regime", "bank")})}
                for point in contexts]}
        self.schema.validate(identity, "identity")
        return identity

    def branch_input(self, point: Any, shared: dict[str, Any], bundle_sha: str,
                     name: str, state: dict[str, Any], prompt: str) -> dict[str, Any]:
        """Projection input đúng ma trận/hash; dùng cả trước API và khi phục hồi."""
        mode, k = PRIOR_BRANCH_MODES[name]
        expected = normalize_prior_config({**self.adapter.prior_config, "mode": mode, "k": k})
        if state.get("prior_config") != expected:
            raise ValueError("Nhánh trả cấu hình khác ma trận nghiên cứu")
        point.verify_source(state)
        if type(prompt) is not str or not 0 < len(prompt) < 6500:
            raise ValueError("Prompt nghiên cứu vượt hợp đồng ngân sách")
        query = {"symbol": shared["stock_name"], "as_of_date": shared["as_of_date"],
            "current_regime": shared["market_regime"]["regime_name"], "current_signals": shared["current_signals"],
            **{key: state["prior_config"][key] for key in ("mode", "k", "seed", "scope")}}
        return {"prior_config": state["prior_config"], "shared_sha256": bundle_sha, "query_sha256": canonical_hash(query),
            **{key: state[key] for key in ("prior_tasks", "prior_stats", "prior_metadata", "bayesian_prior_context")},
            "prompt": {"text": prompt, "char_count": len(prompt), "sha256": hashlib.sha256(prompt.encode()).hexdigest()}}

    def branch_record(self, point: Any, shared: dict[str, Any], bundle_sha: str,
                      name: str, branch: dict[str, Any]) -> dict[str, Any]:
        """Kiểm response thật rồi serialize một nhánh, chưa chấm outcome query."""
        state = branch["state"]
        inputs = self.branch_input(point, shared, bundle_sha, name, state, state["decision_prompt"])
        decision = decision_parser.parse_decision(state["final_trade_decision"], lang=self.config["language"])
        if decision["decision"] not in ("LONG", "SHORT") or decision["decision_source"] not in (
                "llm_json", "llm_structured", "llm_text_recovery"):
            raise ValueError("Decision lỗi/fallback không được nhập vào kết quả nghiên cứu")
        raw = branch.get("raw_response")
        if type(raw) is list:
            raw = json.dumps(copy_prior_json(raw), ensure_ascii=False, allow_nan=False)
        if type(raw) is not str or not raw.strip():
            raise ValueError("Thiếu response raw của Decision; không thay bằng response tự dựng")
        candidates = [raw]
        try:
            response = json.loads(raw)
        except (ValueError, TypeError):
            response = None
        if type(response) is dict and type(response.get("tool_calls")) is list:
            candidates = [json.dumps(call["args"], ensure_ascii=False) for call in response["tool_calls"]
                          if type(call) is dict and type(call.get("args")) is dict]
        parsed_raw = [decision_parser.parse_decision(text, lang=self.config["language"])["decision"] for text in candidates]
        actions = {action for action in parsed_raw if action in ("LONG", "SHORT")}
        if actions and actions != {decision["decision"]}:
            raise ValueError("Decision chuẩn hóa khác action trong response raw")
        if not actions and self.mode == "research":
            raise ValueError("Response raw chưa chứng minh được action LLM nghiên cứu")
        return {"status": "complete", "input": inputs,
            "attempts": [{"attempt_id": branch["attempt_id"], "started_at": branch["started_at"],
                "finished_at": branch["finished_at"], "status": "complete", "error": None}],
            "decision": {"action": decision["decision"], "confidence": decision["confidence"],
                "risk_reward_ratio": decision["risk_reward_ratio"], "raw_response": raw,
                "normalized_response": state["final_trade_decision"], "decision_source": decision["decision_source"],
                "fallback_reason": decision["fallback_reason"], "provider_request_id": None,
                "latency_seconds": branch["elapsed_seconds"]}, "error": None}

    def _completed_point(self, point: Any, paired: dict[str, Any], signature: str,
                         frame: pd.DataFrame, events: list[dict[str, Any]]) -> dict[str, Any]:
        """Đóng điểm sau đủ năm Decision, không biến lỗi thành nhánh complete."""
        shared, bundle = paired["shared"], paired["full_bundle"]
        source = {key: point.source_provenance[key] for key in ("context", "prices", "news", "regime", "bank")}
        bundle_sha, branches = canonical_hash(bundle), {}
        for name in PRIOR_BRANCH_MODES:
            branches[name] = self.branch_record(point, shared, bundle_sha, name, paired["branches"][name])
        cutoff, symbol = shared["as_of_date"], shared["stock_name"]
        prices = source["prices"]
        document = {"schema_version": SCHEMA_VERSION, "run_signature": signature,
            "document_type": "point_checkpoint", "point_id": f"{symbol}-{cutoff}", "revision": 1, "status": "complete",
            "context": {"symbol": symbol, "as_of_date": cutoff, "time_frame": "1d"}, "source_proof": source,
            "source_sha256": canonical_hash(source), "agent_projection": {
                "stock_name": symbol, "as_of_date": cutoff, "window_end_date": cutoff,
                "time_frame": "1d", "language": self.config["language"], "is_backtest": True,
                "snapshot_ref": {"path": prices["csv_path"], "csv_sha256": prices["csv_sha256"],
                    "snapshot_sha256": prices["snapshot_sha256"], "rows": prices["snapshot_rows"],
                    "start_date": prices["snapshot_start_date"], "end_date": cutoff, "schema": prices["schema"]}},
            "shared": {"stage": "shared_complete", "upstream_reports": {key: shared[key] for key in REPORT_FIELDS[:3]},
                "full_bundle": bundle, "shared_sha256": bundle_sha}, "branches": branches,
            "evaluation": evaluate_point(frame, events, cutoff, branches), "error": None}
        document = copy_prior_json(document)
        self.schema.validate(document, "point")
        return document

    def run(self, symbol: str, *, output_dir: Path, time_frame: str = "1d", n_tests: int = 15,
            step: int = 3, cutoffs: tuple[str, ...] | None = None,
            callback: Callable[[dict[str, Any]], None] | None = None, resume: bool = False) -> dict[str, Any]:
        """Kiểm toàn plan trước API, ghi từng điểm complete và summary common support."""
        if type(resume) is not bool:
            raise ValueError("resume phải bool Python gốc")
        validate_prior_execution(self.adapter.prior_config, is_backtest=True, time_frame=time_frame)
        if type(n_tests) is not int or n_tests < 1 or type(step) is not int or step < 3:
            raise ValueError("n_tests phải int dương; step ít nhất ba phiên")
        if not 20 <= self.config["window_size"] <= 600:
            raise ValueError("Window nghiên cứu phải trong 20..600")
        frame, events = self.adapter.execution_data(symbol)
        if cutoffs is None:
            ends = build_walk_forward_end_indices(len(frame), n_tests, self.config["window_size"], step, 3)
            cutoffs = tuple(frame.Datetime.iloc[end - 1].strftime("%Y-%m-%d") for end in ends)
        if type(cutoffs) is not tuple or not cutoffs or any(type(value) is not str for value in cutoffs):
            raise ValueError("Cutoffs phải là tuple ngày ISO không rỗng")
        dates = pd.DatetimeIndex(frame.Datetime)
        positions = dates.get_indexer([pd.Timestamp(iso_date(value)) for value in cutoffs])
        if (positions < 599).any() or (positions + 3 >= len(frame)).any() or (positions[1:] - positions[:-1] < step).any():
            raise ValueError("Plan thiếu 600 nến/phiên thoát, ngày sai thứ tự hoặc chu kỳ chồng lấn")
        # Kiểm quyền/thanh khoản/lịch trước API, chưa tính outcome vào state.
        for position, cutoff in zip(positions.tolist(), cutoffs):
            execution_prices_for_cycle(frame, events, cutoff,
                dates[position + 1].strftime("%Y-%m-%d"), dates[position + 3].strftime("%Y-%m-%d"))
        contexts = [self.adapter.prepare(symbol, cutoff, time_frame=time_frame) for cutoff in cutoffs]
        identity = self._identity(symbol, step, contexts)
        output_dir = Path(output_dir).resolve()
        if not resume and output_dir.exists() and any(output_dir.iterdir()):
            raise ValueError("Thư mục đã có dữ liệu; dùng resume=True cho run đã khởi tạo")
        if resume and not (output_dir / "run_manifest.json").is_file():
            raise ValueError("Không có manifest nghiên cứu; không migrate output legacy/W4-11")
        from core.prior_checkpoint import PriorCheckpointStore
        store = PriorCheckpointStore(self, output_dir, identity, contexts, frame, events)
        return store.execute(resume=resume, callback=callback)
