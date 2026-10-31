"""Thu thập agent/a0 ghép cặp trên snapshot PIT, không sinh quyết định từ nhãn."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import httpx

from core.historical_signals import FrozenSentimentSnapshot, digest, native_json, report_signal, snapshot_payload
from core.improvement_transport import SLOT, body_contract, validate_client
from core.mt_bicl_v2_api_preflight import client as agent_client, wire_body
from core.mt_bicl_v2_decision import canonical_request, invoke_decision
from core.mt_bicl_v4_collect_transport import OfflinePending, ReplayTransport, raw_body
from core.mt_bicl_v4_completion import BASE, DIRECTORY, NEW, DataCompletionError, corrected_coverage
from core.mt_bicl_v4_dataset import immutable
from core.mt_bicl_v4_protocol import canonical, checksum, read, safe_path
from core.prior_stage_journal import StageJournal, decode_output
from core.research_invocation import CURRENT, ENABLED, RECOVERY
from core.bayesian_memory import atomic_write_json


def clients(config: dict[str, Any], http: httpx.Client, key: str) -> tuple[Any, Any]:
    """Hai client đúng source/options release; offline caller dùng credential fixture."""
    from langchain_groq import ChatGroq
    agent = agent_client(config, http, key)
    models = config["signal_config"]["models"]
    graph = ChatGroq(model=models["graph_llm_model"], temperature=models["graph_llm_temperature"],
        max_tokens=models["graph_llm_max_tokens"], max_retries=0, api_key=key, http_client=http,
        service_tier=config["service_tier"], **config["client_options"]["graph"])
    graph.temperature = models["graph_llm_temperature"]
    validate_client(graph, "graph", models)
    return agent, graph


def input_state(row: dict[str, Any], frame: Any, articles: list[dict[str, Any]], config: dict[str, Any], *, render_images: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    """Cắt trước mọi feature/agent; chỉ đưa giá≤query và tin đã lọc vào state."""
    from core.execution_prices import raw_point_in_time_snapshot
    from utils import static_util
    cutoff = row["as_of_date"]
    if not "2018-01-02" <= cutoff <= "2022-12-31":
        raise DataCompletionError("Collection chỉ miền2018–2022")
    prefix = raw_point_in_time_snapshot(frame, cutoff)
    if len(prefix) < 600:
        raise DataCompletionError("Không đủ600 nến PIT, không gửi API")
    sentiment = FrozenSentimentSnapshot(row["symbol"], cutoff, articles)
    raw = snapshot_payload(prefix)
    kline = snapshot_payload(prefix.tail(config["signal_config"]["window_size"]))
    state = {"stock_name": row["symbol"], "as_of_date": cutoff, "window_end_date": cutoff,
        "time_frame": "1d", "is_backtest": True, "language": "vi", "messages": [],
        "point_in_time_df": prefix.copy(deep=True), "kline_data": kline,
        "alpha_norm_method": config["signal_config"]["norm_method"],
        "alpha_weights": deepcopy(config["signal_config"]["alpha_weights"]), "sentiment_store": sentiment}
    if render_images:
        state["pattern_image"] = static_util.generate_kline_image(deepcopy(kline), write_artifacts=False)["pattern_image"]
        state["trend_image"] = static_util.generate_trend_image(deepcopy(kline), write_artifacts=False)["trend_image"]
    proof = {"point_id": row["episode_id"], "as_of_date": cutoff, "price_end_date": str(prefix["Datetime"].iloc[-1].date()),
        "price_rows": len(prefix), "price_prefix_sha256": digest(raw), "kline_sha256": digest(kline),
        "news_sha256": digest(sentiment.articles), "news_dates": [x["date_parsed"] for x in sentiment.articles]}
    return state, proof


def _rows_for(ledger: dict[str, Any], signature: str, point_id: str) -> list[dict[str, Any]]:
    return [r for r in ledger["requests"] if r.get("run_signature") == signature and r.get("point_id") == point_id]


def audit_http(ledger: dict[str, Any], cache: Path, signature: str, point_id: str,
               attempts: set[str]) -> dict[str, Any]:
    """Nối mọi HTTP với UUID stage; không biến unknown/429 thành dữ liệu agent."""
    rows = _rows_for(ledger, signature, point_id)
    proofs, unsealed = {}, []
    for row in rows:
        if row.get("checkpoint_attempt_id") not in attempts or row.get("recovery_policy") != "resilient_invocation_v1":
            raise DataCompletionError("HTTP collection khác UUID/policy đã khóa")
        audit = row.get("improvement_audit")
        if row["status"] == "unknown" and row.get("dispatch_phase") == "reserved" and audit is None:
            continue
        if not isinstance(audit, dict) or not isinstance(audit.get("request"), dict):
            raise DataCompletionError("HTTP thiếu audit request")
        if row["status"] == 200:
            saved = raw_body(cache, row)
            if saved is None:
                unsealed.append(row["id"])
                continue
            proofs[row["id"]] = checksum((cache / (row["id"] + ".json")).read_bytes())
    return {"raw_sha256": proofs, "unsealed_response_missing_ids": unsealed,
            "http_rows_sha256": {r["id"]: checksum(canonical(r)) for r in rows}}


def _agent_features(reports: dict[str, str], factors: list[dict[str, Any]], original: dict[str, Any]) -> dict[str, Any]:
    """Category lấy từ report thật/factor thật; thiếu parser giữ UNKNOWN cùng reason."""
    cats, reasons = {}, []
    for key, labels in (("trend", ("Hướng xu hướng", "Trend direction")),
        ("pattern", ("Thiên lệch dự báo", "Directional bias")),
        ("indicator_consensus", ("Đồng thuận chủ đạo", "Dominant consensus"))):
        report = reports[("indicator" if key == "indicator_consensus" else key) + "_report"]
        try:
            if "lỗi toàn tập không thể chạy model" in report.lower() or "all analysis models failed" in report.lower():
                raise DataCompletionError("Agent trả khung lỗi")
            cats[key] = report_signal(report, labels)
        except ValueError:
            cats[key] = "UNKNOWN"
            reasons.append("UNPARSEABLE_" + key.upper())
    if len(factors) != 5 or len({x["id"] for x in factors}) != 5 or any(x["signal"] not in ("TĂNG", "GIẢM", "TRUNG TÍNH") for x in factors):
        raise DataCompletionError("Alpha phải có5 factor thật duy nhất")
    pos = sum(x["signal"] == "TĂNG" for x in factors)
    neg = sum(x["signal"] == "GIẢM" for x in factors)
    cats["alpha_consensus"] = "BULLISH" if pos > neg else ("BEARISH" if neg > pos else "NEUTRAL")
    if original["decision"] not in ("LONG", "SHORT"):
        raise DataCompletionError("Original không đúng schema")
    cats["original_action"] = "LONG" if original["decision"] == "LONG" else "CASH"
    return {"categories": cats, "conflicts": [None if "UNKNOWN" in (cats[a], cats[b]) else int(cats[a] != cats[b])
            for a, b in (("trend", "pattern"), ("indicator_consensus", "alpha_consensus"))],
            "status": "UNAVAILABLE" if reasons else "AVAILABLE", "reasons": reasons}


def original_from_raw(rows: list[dict[str, Any]], cache: Path, attempt: str, contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Giữ response sai schema làm bằng chứng; chỉ response hợp lệ được dùng cho a0."""
    from core.mt_bicl_v2_development import normalized_decision
    values = []
    for row in rows:
        if row.get("checkpoint_attempt_id") != attempt or row["status"] != 200 or (row.get("improvement_audit") or {}).get("request") != contract:
            continue
        cached = raw_body(cache, row)
        if cached is None:
            continue
        try:
            values.append(normalized_decision(json.loads(cached[0])["choices"][0]["message"]))
        except (ValueError, KeyError, TypeError, IndexError):
            continue
    return values


def collect_point(root: Path, row: dict[str, Any], frame: Any, articles: list[dict[str, Any]],
                  release: dict[str, Any], signature: str, llms: tuple[Any, Any], ledger: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Mỗi node một UUID durable, complete chỉ đọc; replay trước key chạy cùng hàm này."""
    from utils.graph_setup import SetGraph
    from utils.graph_util import TechnicalTools
    from core.research_cohort import save_envelope, read_envelope
    pid = row["episode_id"]
    directory = root / DIRECTORY / "points" / pid
    path = directory / "complete.json"
    state, source = input_state(row, frame, articles, release["config"], render_images=not path.exists())
    binding = {"run_signature": signature, "point_id": pid, "source_sha256": checksum(canonical(source))}
    cache = root / DIRECTORY / "http_cache"
    if path.exists():
        saved = read(path.read_bytes())
        if saved["binding"] != binding or saved["source"] != source:
            raise DataCompletionError("Point complete khác nguồn PIT")
        for name, expected in saved["files_sha256"].items():
            if checksum(safe_path(root, name).read_bytes()) != expected:
                raise DataCompletionError("Bằng chứng point complete bị sửa/mất")
        by_id = {r["id"]: r for r in ledger()["requests"]}
        for rid, expected in saved["http"]["http_rows_sha256"].items():
            if rid not in by_id or checksum(canonical(by_id[rid])) != expected:
                raise DataCompletionError("Ledger point complete bị sửa")
        from core.research_cohort import read_envelope
        journal = StageJournal(directory / "stages.json", binding)
        if list(journal.document["nodes"]) != ["indicator", "pattern", "trend", "full"]:
            raise DataCompletionError("Point complete thiếu4 node")
        expected_reports = {}
        for name, node in journal.document["nodes"].items():
            last = node["attempts"][-1]
            if last["status"] != "complete":
                raise DataCompletionError("Point complete còn stage unknown")
            fields = ("alpha_report", "sentiment_report") if name == "full" else (name + "_report",)
            expected_reports.update({k: last["output"][k] for k in fields})
        original = read_envelope(directory / "original.json")
        full = journal.document["nodes"]["full"]["attempts"][-1]["output"]
        attempts = {n["attempts"][-1]["attempt_id"] for n in journal.document["nodes"].values()} | {original["attempt_id"]}
        shared = {"stock_name": row["symbol"], "as_of_date": row["as_of_date"], "language": "vi", "is_backtest": True,
                  "time_frame": "1d", **expected_reports}
        if original["binding"] != binding or original["request"] != canonical_request(shared, "", {"decision": release["config"]}):
            raise DataCompletionError("Original complete khác canonical request từ reports PIT")
        if (saved["reports"] != expected_reports or original["status"] != "complete"
                or saved["original"] != original["decision"]
                or saved["agent"] != _agent_features(expected_reports, full["sentiment_data"]["alpha_results"], original["decision"])
                or saved["http"] != audit_http(ledger(), cache, signature, pid, attempts)):
            raise DataCompletionError("Point complete khác journal/Original/raw")
        parsed = original_from_raw(_rows_for(ledger(), signature, pid), cache, original["attempt_id"], original["contract"])
        if not parsed or original["decision"] != parsed[-1]:
            raise DataCompletionError("Original complete khác raw durable")
        return saved
    journal = StageJournal(directory / "stages.json", binding, create=True)
    def stage(name: str, function: Callable, current: dict[str, Any]) -> dict[str, Any]:
        def invoke(actual: dict[str, Any]) -> dict[str, Any]:
            budget = CURRENT.get()
            if budget is None:
                raise DataCompletionError("Node thiếu invocation")
            budget.branch_id = name
            token = SLOT.set({**binding, "branch_id": name, "checkpoint_attempt_id": budget.checkpoint_attempt_id})
            try:
                return function(actual)
            finally:
                SLOT.reset(token)
        return journal.invoke(name, invoke, current)
    enable, recovery = ENABLED.set(True), RECOVERY.set(True)
    try:
        builder = SetGraph(*llms, TechnicalTools())
        upstream = builder.compile_upstream(stage_checkpoint=stage).invoke(deepcopy(state))
        if (digest(upstream["kline_data"]) != digest(state["kline_data"])
                or not upstream["point_in_time_df"].equals(state["point_in_time_df"])):
            raise DataCompletionError("Upstream thay nguồn PIT")
        upstream["sentiment_store"] = state["sentiment_store"]
        full = builder.compile_full_preparation(strict_research_mode=True, stage_checkpoint=stage).invoke(deepcopy(upstream))
        sentiment = full["sentiment_data"]
        if any(sentiment.get(k) != v for k, v in state["sentiment_store"].data.items()):
            raise DataCompletionError("Alpha thay dữ liệu sentiment PIT")
        reports = {k: full[k] for k in ("indicator_report", "pattern_report", "trend_report", "alpha_report", "sentiment_report")}
        shared = {"stock_name": row["symbol"], "as_of_date": row["as_of_date"], "language": "vi", "is_backtest": True, "time_frame": "1d", **reports}
        request = canonical_request(shared, "", {"decision": release["config"]})
        contract = body_contract(wire_body(llms[0], request))
        original_path = directory / "original.json"
        if original_path.exists():
            original = read_envelope(original_path)
            if original["binding"] != binding or original["request"] != request or original["contract"] != contract:
                raise DataCompletionError("Original intent khác reports/request")
        else:
            original = {"binding": binding, "request": request, "contract": contract,
                        "attempt_id": str(uuid4()), "status": "unknown", "decision": None}
            save_envelope(original_path, original)
        if original["status"] != "complete":
            token = SLOT.set({**binding, "branch_id": "original", "checkpoint_attempt_id": original["attempt_id"]})
            try:
                decision = invoke_decision(llms[0], request, attempt_id=original["attempt_id"], run_signature=signature, branch_id="original")
            finally:
                SLOT.reset(token)
            original.update(status="complete", decision=decision)
            save_envelope(original_path, original)
        attempts = {node["attempts"][-1]["attempt_id"] for node in journal.document["nodes"].values()} | {original["attempt_id"]}
        http = audit_http(ledger(), cache, signature, pid, attempts)
        # Indicator/Alpha backtest là tính toán Python thật đã khóa, không gọi LLM.
        # Pattern/Trend/Original bắt buộc có response HTTP200 durable.
        rows = _rows_for(ledger(), signature, pid)
        required = {journal.document["nodes"][name]["attempts"][-1]["attempt_id"] for name in ("pattern", "trend")} | {original["attempt_id"]}
        deterministic = {journal.document["nodes"][name]["attempts"][-1]["attempt_id"] for name in ("indicator", "full")}
        if any(r.get("checkpoint_attempt_id") in deterministic for r in rows):
            raise DataCompletionError("Indicator/Alpha backtest không được tự thêm API")
        if any(not any(r.get("checkpoint_attempt_id") == attempt and r["status"] == 200 and r["id"] in http["raw_sha256"] for r in rows) for attempt in required):
            raise DataCompletionError("Stage collection thiếu raw HTTP200 durable")
        actual = original_from_raw(rows, cache, original["attempt_id"], contract)
        if not actual or actual[-1] != original["decision"]:
            raise DataCompletionError("Original parsed khác raw HTTP đã audit")
        features = _agent_features(reports, native_json(sentiment["alpha_results"]), original["decision"])
        files = {(directory / name).relative_to(root).as_posix(): checksum((directory / name).read_bytes()) for name in ("stages.json", "original.json")}
        files.update({(DIRECTORY / "http_cache" / (rid + ".json")).as_posix(): sha for rid, sha in http["raw_sha256"].items()})
        result = {"version": "conditional_v4_collected_point", "binding": binding, "source": source,
            "reports": reports, "agent": features, "original": original["decision"], "http": http, "files_sha256": files}
        immutable(path, result)
        return result
    finally:
        ENABLED.reset(enable)
        RECOVERY.reset(recovery)


def assemble(root: Path, release: dict[str, Any], signature: str, completed: list[dict[str, Any]], warmup: dict[str, Any]) -> dict[str, Any]:
    """Dựng revision mới, giữ byte nhãn/scaler/context cũ; readiness từ coverage đã sửa."""
    rows = read((root / BASE / "observations.json").read_bytes())["rows"]
    by_id = {p["binding"]["point_id"]: p for p in completed}
    if len(completed) != len(rows) or len(by_id) != len(completed) or set(by_id) != set(release["point_ids"]):
        raise DataCompletionError("Chưa đủ toàn cohort để nghiệm thu data")
    for row in rows:
        point = by_id[row["episode_id"]]
        row["agent"] = {**deepcopy(point["agent"]), "source": {"path": (DIRECTORY / "points" / row["episode_id"] / "complete.json").as_posix(),
            "sha256": checksum((root / DIRECTORY / "points" / row["episode_id"] / "complete.json").read_bytes())}, "original": deepcopy(point["original"])}
        row["alpha_history_rows"] = point["source"]["price_rows"]
    folds = read((root / BASE / "folds.json").read_bytes())
    spec = read((root / "docs/plan/week11/protocol_v4.json").read_bytes())
    report = corrected_coverage(rows, folds, spec)
    immutable(root / NEW / "observations.json", {"feature_columns": [x[0] for x in spec["features"]["numeric"]], "rows": rows})
    immutable(root / NEW / "coverage.json", report)
    parent = read((root / "docs/plan/week11/dataset_manifest_v4.json").read_bytes())
    result = {"version": "conditional_v4_completed_dataset", "run_signature": signature,
        "status": report["status"], "ready_for_W11_19": report["ready_for_W11_19"], "acceptance": "AWAITING_AGENT_COLD_ACCEPTANCE",
        "points": len(completed), "collection_release_sha256": checksum((root / "docs/plan/week11/data_completion_release_v4.json").read_bytes()),
        "warmup": warmup, "inherited_artifact_sha256": parent["artifact_sha256"],
        "artifact_sha256": {(NEW / name).as_posix(): checksum((root / NEW / name).read_bytes()) for name in ("observations.json", "coverage.json")},
        "collection_point_sha256": {p["binding"]["point_id"]: checksum((root / DIRECTORY / "points" / p["binding"]["point_id"] / "complete.json").read_bytes()) for p in completed},
        "labels_unchanged": True, "training_allowed": False, "development_allowed": False, "confirmation_allowed": False}
    immutable(root / NEW / "manifest.json", result)
    return result
