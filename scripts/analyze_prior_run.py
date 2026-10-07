"""Đối soát ledger và quyết định từ checkpoint; chỉ đọc, không gọi LLM."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.prior_backtest import ResearchSchema, canonical_hash, summarize_points
from core.prior_checkpoint import read_document


def _number(value: Any) -> float:
    """Chặn số không hữu hạn, bool và thời gian âm trước tổng hợp."""
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Số đo telemetry không hợp lệ")
    return float(value)


def _timestamp(value: str) -> float:
    """Chỉ nhận timestamp có múi giờ để ghép với epoch ledger."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Timestamp attempt thiếu múi giờ")
    return _number(parsed.timestamp())


def _distribution(values: list[float]) -> dict[str, Any]:
    """P95 nội suy tuyến tính; tập không có số đo trả null, không điền zero."""
    ordered = sorted(_number(v) for v in values)
    if not ordered:
        return {"count": 0, "sum": None, "median": None, "p95": None, "max": None}
    position = (len(ordered) - 1) * .95
    low, high = math.floor(position), math.ceil(position)
    return {"count": len(ordered), "sum": float(sum(ordered)),
            "median": float(statistics.median(ordered)),
            "p95": float(ordered[low] + (ordered[high] - ordered[low]) * (position - low)),
            "max": float(ordered[-1])}


def _safe_path(root: Path, relative: str) -> Path:
    """Không đọc path thoát run hoặc credential, kể cả qua symlink."""
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root.resolve()) or path.name.startswith(".env"):
        raise ValueError("Đường dẫn phân tích không hợp lệ")
    return path


def _strict_json(path: Path) -> dict[str, Any]:
    """Không nhận JSON trùng khóa hoặc NaN; không mở file credential."""
    if path.resolve().name.startswith(".env"):
        raise ValueError("Phân tích không được đọc credential")
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("JSON telemetry có khóa trùng")
            result[key] = value
        return result
    def reject(value: str) -> None:
        raise ValueError("JSON telemetry có số không hữu hạn")
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                       parse_constant=reject)
    if type(value) is not dict:
        raise ValueError("Telemetry cần JSON object")
    return value


def summarize_ledger(ledger: dict[str, Any], *, run_started_at: float,
                     attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Tổng usage toàn ledger; chỉ gán HTTP vào attempt bằng cửa sổ đã lưu.

    Ledger v1 không ghi role/point/pacing. Request ngoài cửa sổ Decision
    được giữ unattributed, không đoán preflight hoặc format retry từ token.
    Charged tái lập đúng policy v1: total_tokens dương, còn lại giữ reserve.
    """
    if type(ledger.get("version")) is not int or ledger["version"] != 1 or type(ledger.get("requests")) is not list:
        raise ValueError("Ledger chưa có phiên bản hỗ trợ")
    limits = ledger.get("limits")
    if type(limits) is not dict or not limits or not set(limits).issubset({
            "openai/gpt-oss-20b", "qwen/qwen3.8-27b"}):
        raise ValueError("Ledger thiếu model/giới hạn")
    known_preflight = set(ledger.get("preflight", {}).get("request_ids", []))
    records = ledger["requests"]
    ids = [r["id"] for r in records]
    if len(ids) != len(set(ids)) or not known_preflight.issubset(ids):
        raise ValueError("ID ledger trùng hoặc preflight mất request")
    status_counts: Counter[str] = Counter()
    model_rows: dict[str, list[dict[str, Any]]] = {model: [] for model in limits}
    phases: Counter[str] = Counter()
    linked: Counter[str] = Counter()
    first, last = [], []
    for row in records:
        if row["model"] not in model_rows:
            raise ValueError("Model request khác giới hạn ledger")
        status = row["status"]
        if not (type(status) is int and 100 <= status <= 599) and status not in (
                "unknown", "transport_error"):
            raise ValueError("Trạng thái HTTP không hợp lệ")
        start = _number(row["started_at"])
        if type(row["reserved_tokens"]) is not int or row["reserved_tokens"] < 1:
            raise ValueError("Reserve request phải int dương")
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if key in row and (type(row[key]) is not int or row[key] < 0):
                raise ValueError("Usage provider không hợp lệ")
        if all(key in row for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
            if row["total_tokens"] != row["prompt_tokens"] + row["completion_tokens"]:
                raise ValueError("Tổng usage không khớp input/output")
        latency = _number(row["latency_seconds"]) if "latency_seconds" in row else None
        finish = _number(row["completed_at"]) if "completed_at" in row else start + (latency or 0.)
        if finish < start:
            raise ValueError("HTTP kết thúc trước bắt đầu")
        first.append(start)
        last.append(finish)
        windows = [a for a in attempts if a["start"] <= start and
                   a["finish"] is not None and finish <= a["finish"]]
        if len(windows) > 1:
            raise ValueError("HTTP thuộc nhiều attempt; không thể đối soát")
        if row["id"] in known_preflight:
            if windows:
                raise ValueError("Preflight chồng lên attempt Decision")
            phase = "known_preflight"
        elif windows:
            phase = "decision"
            linked[windows[0]["attempt_id"]] += 1
        elif start < run_started_at:
            phase = "before_run_unclassified"
        else:
            phase = "run_nondecision_unattributed"
        phases[phase] += 1
        status_counts[str(status)] += 1
        model_rows[row["model"]].append(row)
    models = {}
    for model, rows in model_rows.items():
        measured = [r for r in rows if "total_tokens" in r]
        held = [r for r in rows if not r.get("total_tokens")]
        models[model] = {
            "http_attempts": len(rows), "http_200": sum(r["status"] == 200 for r in rows),
            "unknown_outcome": sum(r["status"] in ("unknown", "transport_error") for r in rows),
            "prompt_tokens": sum(r.get("prompt_tokens", 0) for r in rows),
            "prompt_usage_count": sum("prompt_tokens" in r for r in rows),
            "completion_tokens": sum(r.get("completion_tokens", 0) for r in rows),
            "completion_usage_count": sum("completion_tokens" in r for r in rows),
            "actual_total_tokens": sum(r["total_tokens"] for r in measured),
            "actual_usage_count": len(measured), "missing_usage_count": len(rows) - len(measured),
            "requested_reserve_tokens": sum(r["reserved_tokens"] for r in rows),
            "held_reserve_tokens": sum(r["reserved_tokens"] for r in held),
            "charged_tokens": sum(r.get("total_tokens") or r["reserved_tokens"] for r in rows),
            "http_latency_seconds": _distribution([r["latency_seconds"] for r in rows if "latency_seconds" in r]),
            "missing_latency_count": sum("latency_seconds" not in r for r in rows),
            "http_200_latency_seconds": _distribution([r["latency_seconds"] for r in rows
                                                       if r["status"] == 200 and "latency_seconds" in r]),
        }
    return {"scope": "whole_supplied_ledger", "http_attempts": len(records),
            "status_counts": dict(sorted(status_counts.items())), "request_phases": dict(sorted(phases.items())),
            "models": models, "ledger_wall_span_seconds": float(max(last) - min(first)) if first else None,
            "decision_http_attempts": sum(linked.values()),
            "decision_attempts_without_http": sum(linked[a["attempt_id"]] == 0 for a in attempts),
            "additional_http_in_decision_windows": sum(max(0, count - 1) for count in linked.values()),
            "format_retry_count": None, "pacing_seconds": None,
            "limitations_vi": "V1 không lưu pacing/role từng request; khoảng trống không đồng nghĩa nghỉ quota. "
                              "Preflight chỉ gán khi có ID durable; usage thiếu không là zero, charged giữ reserve v1."}


def _reason_fingerprints(decision: dict[str, Any]) -> dict[str, Any]:
    """Trỏ về lý do structured đã lưu, không xuất response/prompt tự do."""
    try:
        parsed = json.loads(decision["normalized_response"])
    except (ValueError, TypeError):
        return {"status": "unavailable", "fields": {}}
    fields = {}
    for key in ("evidence_for", "evidence_against", "justification"):
        value = parsed.get(key) if type(parsed) is dict else None
        if type(value) is str:
            fields[key] = {"char_count": len(value), "sha256": hashlib.sha256(value.encode()).hexdigest()}
    return {"status": "available" if fields else "unavailable", "fields": fields}


def audit_points(points: list[dict[str, Any]]) -> dict[str, Any]:
    """Đọc trace paired; outcome chỉ được dùng sau Decision để đối chiếu P&L."""
    rows, attempts, graph_elapsed, durations, window_spans = [], [], [], [], []
    statuses: Counter[str] = Counter()
    seen_attempts: set[str] = set()
    for point in points:
        cutoff = date.fromisoformat(point["context"]["as_of_date"])
        branches = point["branches"]
        if point["status"] != "complete" or any(b["status"] != "complete" for b in branches.values()):
            raise ValueError("Audit cần common support complete; không bỏ điểm dở")
        bundle_sha = canonical_hash(point["shared"]["full_bundle"])
        if bundle_sha != point["shared"]["shared_sha256"] or any(
                b["input"]["shared_sha256"] != bundle_sha for b in branches.values()):
            raise ValueError("Input các nhánh khác shared bundle")
        point_attempts = []
        for name, branch in branches.items():
            graph_elapsed.append(_number(branch["decision"]["latency_seconds"]))
            for attempt in branch["attempts"]:
                if attempt["attempt_id"] in seen_attempts:
                    raise ValueError("Attempt trùng giữa checkpoint")
                seen_attempts.add(attempt["attempt_id"])
                start = _timestamp(attempt["started_at"])
                finish = _timestamp(attempt["finished_at"]) if attempt["finished_at"] else None
                if finish is not None:
                    durations.append(_number(finish - start))
                statuses[attempt["status"]] += 1
                item = {"attempt_id": attempt["attempt_id"], "point_id": point["point_id"],
                        "branch": name, "start": start, "finish": finish}
                attempts.append(item)
                point_attempts.append(item)
        starts = [a["start"] for a in point_attempts]
        finishes = [a["finish"] for a in point_attempts if a["finish"] is not None]
        if starts and finishes:
            window_spans.append(float(max(finishes) - min(starts)))
        original = branches["original"]["decision"]
        bayesian = branches["bayesian"]
        inputs, decision = bayesian["input"], bayesian["decision"]
        metadata, stats = inputs["prior_metadata"], inputs["prior_stats"]
        if metadata["selected_ids"] != [r["episode_id"] for r in inputs["prior_tasks"]]:
            raise ValueError("IDs prior không khớp task đã lưu")
        scores = {r["episode_id"]: r["score"] for r in metadata["selected_scores"]}
        selected = []
        for task in inputs["prior_tasks"]:
            exit_date = date.fromisoformat(task["exit_date"])
            if not date.fromisoformat(task["as_of_date"]) < date.fromisoformat(task["entry_date"]) <= exit_date < cutoff:
                raise ValueError("Prior vi phạm exit_date < as_of_date")
            selected.append({"episode_id": task["episode_id"], "as_of_date": task["as_of_date"],
                "exit_date": task["exit_date"], "age_calendar_days": (cutoff - date.fromisoformat(task["as_of_date"])).days,
                "exit_age_calendar_days": (cutoff - exit_date).days, "score": scores.get(task["episode_id"]),
                "historical_result": task["outcome"]["result"], "historical_net_return_pct": task["outcome"]["net_return_pct"]})
        evaluation = point["evaluation"]
        # Tái dùng hàm kinh tế; không sinh nhãn Close-to-Close trong công cụ audit.
        from core.backtest_engine import compute_round_trip_net_return
        expected = float(compute_round_trip_net_return(evaluation["entry_open"], evaluation["exit_close"]))
        if not math.isclose(expected, evaluation["net_return_long"], rel_tol=0., abs_tol=1e-12):
            raise ValueError("Return checkpoint khác engine kinh tế")
        actual = "UP" if expected > 0 else "DOWN"
        if evaluation["actual_direction"] != actual:
            raise ValueError("Nhãn checkpoint khác return sau phí")
        for name, branch in branches.items():
            expected_return = expected if branch["decision"]["action"] == "LONG" else 0.
            if not math.isclose(evaluation["branches"][name]["cycle_net_return"], expected_return,
                                rel_tol=0., abs_tol=1e-12):
                raise ValueError("Return nhánh khác action đã lưu")
            if evaluation["branches"][name]["correct"] != ((branch["decision"]["action"] == "LONG") == (actual == "UP")):
                raise ValueError("Cờ đúng/sai khác action/nhãn kinh tế")
        news = point["source_proof"]["news"]
        rows.append({"point_id": point["point_id"], "symbol": point["context"]["symbol"],
            "as_of_date": cutoff.isoformat(), "regime": point["shared"]["full_bundle"]["market_regime"]["regime_name"],
            "query_signals": point["shared"]["full_bundle"]["current_signals"],
            "original_action": original["action"], "bayesian_action": decision["action"],
            "disagrees": original["action"] != decision["action"],
            "net_return_long_pct": expected * 100., "actual_direction": evaluation["actual_direction"],
            "cycle_return_delta_pct": 100. * (evaluation["branches"]["bayesian"]["cycle_net_return"] -
                                              evaluation["branches"]["original"]["cycle_net_return"]),
            "population_count": stats["population_count"] if stats else None,
            "prior_metrics": stats["metrics"] if stats else None,
            "requested_k": metadata["requested_k"], "selected_count": metadata["selected_count"],
            "selected_priors": selected,
            "news_coverage": {k: news[k] for k in ("visible_count", "window_days", "min_articles", "is_reliable", "neutral_reason")},
            "structured_reason": {"original": _reason_fingerprints(original), "bayesian": _reason_fingerprints(decision)},
            "reason_location": f"points/{point['point_id']}.json:branches.<branch>.decision.normalized_response"})
    summary = summarize_points(points)
    return {"point_count": len(points), "disagreement_count": sum(r["disagrees"] for r in rows),
            "rows": rows, "summary": summary,
            "return_delta_pct": (summary["bayesian"]["account_metrics"]["total_return_pct"] -
                                 summary["original"]["account_metrics"]["total_return_pct"]) if points else None,
            "attempts": attempts, "decision_attempt_statuses": dict(statuses),
            "timing": {"decision_graph_elapsed_seconds": _distribution(graph_elapsed),
                "decision_attempt_wall_seconds": _distribution(durations),
                "decision_window_span_seconds": _distribution(window_spans),
                "unfinished_attempt_count": sum(a["finish"] is None for a in attempts),
                "whole_point_wall_seconds": None, "retrieval_seconds": None, "pacing_seconds": None,
                "limitations_vi": "Latency Decision là thời gian graph chứa cả chuẩn bị/nghỉ/HTTP; "
                                  "span chỉ từ attempt Decision đầu đến cuối, không gồm toàn upstream. "
                                  "V1 không lưu timer toàn điểm, retrieval hoặc pacing."}}


def analyze_run(output_dir: Path, ledger_path: Path, *, reconciliation_dir: Path | None = None) -> dict[str, Any]:
    """Kiểm envelope/source pairing/kinh tế và audit replay, không đổi lock/run.

    Đây là audit số đo trên byte đã lưu, không thay verifier semantic của
    phiên bản nghiên cứu ghim: không fit model, dựng lại report hoặc gọi API.
    """
    root = output_dir.resolve(strict=True)
    schema = ResearchSchema()
    identity = read_document(_safe_path(root, "identity.json"), schema, "identity")
    manifest = read_document(_safe_path(root, "run_manifest.json"), schema, "manifest")
    result = read_document(_safe_path(root, "results.json"), schema, "result")
    signature = canonical_hash(identity)
    if manifest["run_signature"] != signature or canonical_hash(manifest["identity"]) != signature or result["run_signature"] != signature:
        raise ValueError("Identity/manifest/result khác signature")
    if result["status"] != "complete" or result["completed_point_ids"] != result["planned_point_ids"]:
        raise ValueError("Run còn dở; không thống kê bằng cách bỏ điểm")
    if [p["point_id"] for p in identity["point_plan"]] != result["planned_point_ids"]:
        raise ValueError("Lịch result khác plan trong identity")
    points = []
    for entry in result["point_files"]:
        path = _safe_path(root, entry["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Byte checkpoint khác result")
        point = read_document(path, schema, "point")
        if point["run_signature"] != signature:
            raise ValueError("Checkpoint khác signature run")
        points.append(point)
    if [p["point_id"] for p in points] != result["planned_point_ids"]:
        raise ValueError("Checkpoint không khớp toàn bộ lịch đã khóa")
    if {p.name for p in (root / "points").glob("*.json")} != {Path(e["path"]).name for e in result["point_files"]}:
        raise ValueError("Thừa hoặc thiếu checkpoint so với plan")
    audit = audit_points(points)
    if canonical_hash(audit["summary"]) != canonical_hash(result["summary"]):
        raise ValueError("Summary đã lưu khác engine dựng lại")
    ledger = _strict_json(ledger_path)
    usage = summarize_ledger(ledger, run_started_at=_timestamp(manifest["created_at"]), attempts=audit.pop("attempts"))
    replay_count = 0
    if reconciliation_dir is not None:
        folder = reconciliation_dir.resolve(strict=True)
        for path in sorted(folder.glob("*.json")):
            if path.name.endswith(".before-replay.json"):
                continue
            envelope = _strict_json(path)
            proof = envelope["payload"]
            if set(envelope) != {"payload", "sha256"} or canonical_hash(proof) != envelope["sha256"]:
                raise ValueError("Audit replay sai envelope/hash")
            if proof["run_signature"] != signature:
                raise ValueError("Audit replay khác run")
            if proof["action"] != "USER_AUTHORIZED_REPLAY_OF_UNKNOWN_UPSTREAM_ONCE" or proof["status"] != "APPLIED":
                raise ValueError("Audit replay chưa áp dụng hợp lệ")
            completion = proof.get("completion", {})
            if completion.get("status") != "VERIFIED_COMPLETE" or completion.get("result_file_sha256") != hashlib.sha256(
                    (root / "results.json").read_bytes()).hexdigest():
                raise ValueError("Audit replay chưa có completion khớp result")
            current = _safe_path(root, f"points/{proof['point_id']}.json")
            if hashlib.sha256(current.read_bytes()).hexdigest() != completion.get("point_file_sha256"):
                raise ValueError("Điểm sau replay khác completion đã ghi")
            # Audit lúc replay còn giữ hash planned của các điểm phía sau;
            # chúng được phép chuyển complete. Chỉ đóng băng các điểm đã xong trước replay.
            index = result["planned_point_ids"].index(proof["point_id"])
            for point_id in result["planned_point_ids"][:index]:
                filename = f"{point_id}.json"
                expected_sha = proof["other_point_file_sha256"].get(filename)
                if hashlib.sha256(_safe_path(root, f"points/{filename}").read_bytes()).hexdigest() != expected_sha:
                    raise ValueError("Điểm durable trước replay bị thay đổi")
            if completion.get("old_complete_points_byte_unchanged") != index:
                raise ValueError("Số điểm bảo toàn trong audit replay không khớp")
            backup = _safe_path(folder, Path(proof["previous_point_backup"]).name)
            if hashlib.sha256(backup.read_bytes()).hexdigest() != proof["previous_point_file_sha256"]:
                raise ValueError("Backup replay khác byte đã ghi")
            previous = read_document(backup, schema, "point")
            if canonical_hash(previous) != proof["previous_payload_sha256"] or previous["point_id"] != proof["point_id"]:
                raise ValueError("Backup replay khác payload/point")
            records = [r for r in ledger["requests"] if r["id"] == proof["unknown_http_request_record_id"]]
            if len(records) != 1 or records[0]["status"] not in ("unknown", "transport_error") or records[0].get("total_tokens"):
                raise ValueError("Replay làm mất record HTTP chưa rõ kết quả")
            if records[0]["reserved_tokens"] != proof["unknown_request_reserve_kept"]:
                raise ValueError("Reserve unknown bị thay đổi")
            replay_count += 1
    return {"analysis_version": "prior_run_audit_v1", "run_signature": signature,
            "telemetry": usage, "paired_audit": audit,
            "graph_evidence": {"complete_shared_points": len(points), "complete_full_bundles": len(points),
                "decision_attempt_statuses": audit["decision_attempt_statuses"],
                "authorized_upstream_replays": replay_count if reconciliation_dir is not None else None,
                "upstream_invocation_count": None, "full_invocation_count": None,
                "limitations_vi": "Stage durable chứng minh đầu ra hoàn tất, không là bộ đếm invocation. "
                                  "Replay chỉ đếm audit đã kiểm; không suy ra unknown chưa được provider xử lý."}}


def main(argv: list[str] | None = None) -> None:
    """In báo cáo gọn; không tạo JSON/receipt hoặc in prompt/response/key."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/pilot_fpt_run")
    parser.add_argument("--ledger", type=Path, default=ROOT / "outputs/oos_pilot/api_usage.json")
    parser.add_argument("--reconciliation-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    report = analyze_run(args.output_dir, args.ledger, reconciliation_dir=args.reconciliation_dir)
    usage, paired = report["telemetry"], report["paired_audit"]
    print(f"Đối soát PASS: {paired['point_count']} điểm; {usage['http_attempts']} HTTP attempt toàn ledger")
    for model, row in usage["models"].items():
        print(f"{model}: HTTP 200={row['http_200']}; unknown={row['unknown_outcome']}; "
              f"input/output={row['prompt_tokens']}/{row['completion_tokens']}; "
              f"actual={row['actual_total_tokens']}; reserve giữ={row['held_reserve_tokens']}; charged={row['charged_tokens']}")
        timing = row["http_latency_seconds"]
        print(f"  Thời gian HTTP: tổng={timing['sum']}; p95={timing['p95']}; thiếu số đo={row['missing_latency_count']}")
    print(f"Phân loại request: {usage['request_phases']}; retry định dạng chưa đo riêng")
    print(f"Attempt Decision: {paired['decision_attempt_statuses']}; HTTP trong cửa sổ={usage['decision_http_attempts']}")
    for name, timing in paired["timing"].items():
        if isinstance(timing, dict):
            print(f"Thời gian {name}: tổng={timing['sum']}; median={timing['median']}; p95={timing['p95']}")
    print("Pacing/retrieval/toàn điểm: chưa có số đo riêng trong checkpoint v1")
    print(f"Bất đồng Original/Bayesian: {paired['disagreement_count']}/{paired['point_count']}; "
          f"chênh return={paired['return_delta_pct']:.6f} điểm phần trăm")
    for row in paired["rows"]:
        if row["disagrees"]:
            print(f"{row['point_id']}: {row['original_action']} → {row['bayesian_action']}; "
                  f"LONG ròng={row['net_return_long_pct']:.6f}%; population={row['population_count']}; "
                  f"K={row['requested_k']}/{row['selected_count']}; tin={row['news_coverage']['visible_count']}")
            for prior in row["selected_priors"]:
                print(f"  {prior['episode_id']}: score={prior['score']}; tuổi={prior['age_calendar_days']} ngày; "
                      f"{prior['historical_result']}; LONG ròng={prior['historical_net_return_pct']:.6f}%")
            print(f"  Lý do structured: fingerprint tại {row['reason_location']}; không xuất nội dung tự do")
    print(f"Replay upstream có audit: {report['graph_evidence']['authorized_upstream_replays']}; "
          "giữ reserve unknown, không suy ra exactly-once")


if __name__ == "__main__":
    main()
