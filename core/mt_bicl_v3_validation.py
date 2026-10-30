"""Validation v3 có checkpoint và cold replay; giữ failed gate, không cấp release API."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_memory import read_json
from core.execution_prices import execution_prices_for_cycle
from core.mt_bicl_bank import SOURCE, SYMBOLS, content_hash
from core.mt_bicl_stream import MarketStream
from core.mt_bicl_training import configure
from core.mt_bicl_v2_adapter import StudentAdapter
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v2_teacher import BetaBernoulliTeacher
from core.mt_bicl_v21_preparation import file_hash
from core.mt_bicl_v3_budget import RuntimeBudget
from core.mt_bicl_v3_context import prepare_variants
from core.mt_bicl_v3_contracts import membership_hash, validate_context, without_target
from core.mt_bicl_v3_features import BucketTaskBuilder, make_fact_packet
from core.mt_bicl_v3_oracle import check_posterior
from core.mt_bicl_v3_validation_inputs import OUTPUT, load_inputs
from core.mt_bicl_v3_utility import posterior_utility
from core.pit_price_features import extract_pit_price_features
from core.prior_run_lock import PriorRunLock, safe_path
from utils.graph_util import TechnicalTools

POINT_VERSION = "utility_icl_validation_point_v3"
REPORT_VERSION = "utility_icl_validation_report_v3"
INDEX_VERSION = "utility_icl_validation_index_v3"
PROOF_VERSION = "utility_icl_validation_replay_v3"


def approximation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Một denominator union Full/No_target; phân nhóm chỉ mô tả, không thêm gate sau run."""
    active = [row for row in rows if row["p"] is not None]
    errors, divergences, infinite = [], [], 0
    for row in active:
        p, q = row["p"], row["q"]
        if type(p) not in (float, int) or type(q) not in (float, int) or not math.isfinite(p) or not math.isfinite(q) or not 0 <= p <= 1 or not 0 < q < 1:
            raise ValueError("Xác suất approximation ngoài hợp đồng")
        errors.append(abs(p-q))
        if p in (0., 1.):
            infinite += 1
        else:
            divergences.append(q*math.log(q/p)+(1-q)*math.log((1-q)/(1-p)))
    mean = math.fsum(divergences)/len(active) if active and not infinite else None
    p95 = float(np.quantile(errors, .95, method="linear")) if active else None
    return {"available_contexts": len(active), "unavailable_contexts": len(rows)-len(active),
            "infinite_KL_contexts": infinite, "mean_KL_nats": mean, "p95_absolute_error": p95,
            "mean_absolute_error": math.fsum(errors)/len(active) if active else None,
            "status": "PASS" if active and mean is not None and mean <= .02 and p95 <= .1 else "FAIL_APPROXIMATION_NO_TEACHER_FALLBACK"}


def check_projection(prepared: dict[str, Any]) -> None:
    """Đối soát toàn counts/mean/exemplar, không chỉ kiểm prefix tự khai."""
    branches = prepared["branches"]
    full = branches["Full_utility_ICL"]
    for name, branch in branches.items():
        if name in ("Plain_revision", "No_utility") and (branch["eligible"] != full["eligible"] or branch["utility"] is not None):
            raise ValueError("Ablation utility dùng sai mask hoặc vẫn nhận U")
        if name == "Plain_revision" and branch["probability"] is not None:
            raise ValueError("Plain nhận p")
        if name == "Stats_only":
            if {**branch["utility"], "branch_id": "Full_utility_ICL"} != full["utility"]:
                raise ValueError("Stats không giữ cùng Full U")
            if branch["projection"] is not None and "exemplars" in branch["projection"]:
                raise ValueError("Stats vẫn chứa exemplar IDs")
        projection = branch["projection"]
        if projection is None:
            continue
        episode = prepared["contexts"]["No_target" if name == "No_target" else "Full"]
        groups = [(f"P{i}", task["observations"]) for i, task in enumerate(episode["prior"], 1)]
        if name != "No_target": groups.append(("T", episode["target"]))
        if len(projection["summary"]) != len(groups) or len(projection["prefix"]) > 600:
            raise ValueError("Projection thiếu nhóm hoặc vượt budget")
        expected_ids = []
        for summary, (label, rows) in zip(projection["summary"], groups):
            wins = sum(row["y"] for row in rows)
            mean = math.fsum(row["r_net"] for row in rows)/len(rows) if rows else None
            if (summary["task"], summary["n"], summary["wins"], summary["losses"], summary["mean_r_net_fraction"]) != (label, len(rows), wins, len(rows)-wins, mean):
                raise ValueError("Summary projection khác toàn membership")
            if rows:
                expected_ids.append(min(rows, key=lambda row: (row["distance"], -date.fromisoformat(row["as_of_date"]).toordinal(), row["episode_id"]))["episode_id"])
        if name != "Stats_only" and [row["episode_id"] for row in projection["exemplars"]] != expected_ids:
            raise ValueError("Exemplar không đúng rank label-blind")
    a, b = prepared["contexts"]["Full"], prepared["contexts"]["No_target"]
    if a["prior"] != b["prior"] or a["query"] != b["query"] or b["target"] or b["m"]:
        raise ValueError("No_target đổi D/query hoặc chưa bỏ C")


class SourceAudit:
    """Cache phép kiểm raw/helper theo ID; chỉ đọc nhãn khi cycle đã đóng trước query."""

    def __init__(self, prices: dict[str, Any], calendar: pd.DatetimeIndex) -> None:
        self.prices, self.calendar = prices, calendar
        self.features: dict[str, Any] = {}
        self.labels: dict[str, Any] = {}
        self.fact_hashes: dict[str, str] = {}
        self.raw_facts: dict[str, Any] = {}

    def facts(self, packet: dict[str, Any]) -> None:
        """Dùng helper Indicator thật và SMA scalar, không so hai lần cùng renderer."""
        pid = packet["point_id"]
        if pid in self.fact_hashes:
            if self.fact_hashes[pid] != content_hash(packet): raise ValueError("Facts cùng ID nhưng đổi nội dung")
            return
        if pid not in self.raw_facts:
            self.raw_facts[pid] = make_fact_packet(self.prices[pid[:3]][0], pid[:3], packet["as_of_date"])
        if self.raw_facts[pid] != packet:
            raise ValueError("Facts khác prefix raw nguồn")
        if packet["prefix_rows"] == 45 and packet["frame_end_date"] == packet["as_of_date"] and packet["numeric"]["macd"] is not None:
            frame = self.prices[pid[:3]][0]
            close = frame.loc[frame["Datetime"] <= packet["as_of_date"], "Close"].tail(45).tolist()
            legacy = TechnicalTools.compute_macd.invoke({"kline_data": {"Close": close}})
            n = packet["numeric"]
            if round(n["macd"], 4) != legacy["macd"][-1] or round(n["signal"], 4) != legacy["macd_signal"][-1] or abs(n["sma20"]-math.fsum(close[-20:])/20) > 1e-12:
                raise ValueError("Facts khác helper TA-Lib/SMA20 trên prefix45")
        self.fact_hashes[pid] = content_hash(packet)

    def feature(self, symbol: str, cutoff: str) -> dict[str, Any]:
        """Bốn feature độc lập từ primitive nguồn, không từ p/projection đã lưu."""
        pid = symbol+"-"+cutoff
        if pid not in self.features:
            self.features[pid] = extract_pit_price_features(*self.prices[symbol], self.calendar, cutoff, source=SOURCE)
        return self.features[pid]

    def context(self, episode: dict[str, Any], visible: list[dict[str, Any]], regimes: Any) -> dict[str, int]:
        """Kiểm rank/centroid/nhãn với toàn population cùng bucket trước selection."""
        validate_context(episode)
        query, meta = episode["query"], episode["v3"]
        self.facts(meta["query_facts"])
        qx = self.feature(query["symbol"], query["as_of_date"])
        if query["raw"] is not None and (qx["vector"] is None or not np.allclose(query["raw"], qx["vector"], atol=1e-12, rtol=0)):
            raise ValueError("Raw query khác primitive PIT")
        records = {row["episode_id"]: row for row in visible}
        for pid, fact in meta["historical_facts"].items():
            self.facts(fact)
            original = records[pid]
            feature = self.feature(original["symbol"], original["as_of_date"])
            if feature["status"] != "AVAILABLE" or not np.allclose(feature["vector"], original["features"]["vector"], atol=1e-12, rtol=0):
                raise ValueError("Feature centroid/context khác nguồn PIT")
        selected = [row for task in episode["prior"] for row in task["observations"]]+episode["target"]
        for row in selected:
            if row["exit_date"] >= query["as_of_date"]: raise ValueError("Membership chứa nhãn chưa đóng")
            pid = row["episode_id"]
            if pid not in self.labels:
                opening, closing = execution_prices_for_cycle(*self.prices[row["symbol"]], row["as_of_date"], row["entry_date"], row["exit_date"])
                self.labels[pid] = float(compute_round_trip_net_return(opening, closing))
            net = self.labels[pid]
            if row["y"] != int(net > 0) or abs(row["r_net"]-net) > 1e-12:
                raise ValueError("Nhãn context không khớp engine net T+2.5")
            expected_raw = self.feature(row["symbol"], row["as_of_date"])["vector"]
            z = (np.array(expected_raw)-episode["scaler"]["mean"])/episode["scaler"]["scale"]
            if (not np.allclose(row["raw"], expected_raw, atol=1e-12, rtol=0) or not np.allclose(row["z"], z, atol=1e-12, rtol=0)
                    or not np.allclose(row["model_vector"], np.clip(z, -4, 4), atol=1e-12, rtol=0)):
                raise ValueError("Raw/z/model-vector context khác scaler nguồn")
        if episode["status"] == "AVAILABLE" and meta["bucket"] != "UNKNOWN":
            # Duyệt record dictionary, không lặp row Pandas; không đọc y để rank.
            eligible = []
            for row in visible:
                if row["symbol"] != query["symbol"] or row["status"] != "AVAILABLE" or row["exit_date"] >= query["as_of_date"]: continue
                pid = row["episode_id"]
                if pid not in self.raw_facts: self.raw_facts[pid] = make_fact_packet(self.prices[row["symbol"]][0], row["symbol"], row["as_of_date"])
                if self.raw_facts[pid]["bucket"] == meta["bucket"]: eligible.append(row)
            if len(eligible) != episode["eligible_count"]: raise ValueError("Eligible population thiếu/thừa cycle cùng bucket")
            groups = {}
            for row in eligible:
                if row["block_index"] < query["block_index"]: groups.setdefault(row["block_index"], []).append(row)
            ranked = []
            for block, population in groups.items():
                if len(population) < 2: continue
                matrix = np.clip((np.array([row["features"]["vector"] for row in population])-episode["scaler"]["mean"])/episode["scaler"]["scale"], -4, 4)
                centroid = matrix.mean(axis=0)
                distances = {row["episode_id"]: float(np.linalg.norm(v-np.array(query["model_vector"]))) for row, v in zip(population, matrix)}
                nearest = sorted(population, key=lambda row: (distances[row["episode_id"]], -date.fromisoformat(row["as_of_date"]).toordinal(), row["episode_id"]))[:8]
                task_regime = regimes.task(block)
                matched = query["regime"]["name"] != "UNKNOWN" and task_regime["name"] == query["regime"]["name"]
                rank = (not matched, float(np.linalg.norm(centroid-np.array(query["model_vector"]))),
                        -date.fromisoformat(max(row["exit_date"] for row in population)).toordinal(), f"{query['symbol']}:block{block:04d}")
                ranked.append((rank, centroid, population, nearest))
            expected_tasks = sorted(ranked, key=lambda item: item[0])[:3]
            if [r[0][-1] for r in expected_tasks] != [task["task_id"] for task in episode["prior"]]: raise ValueError("Prior task rank không khớp toàn population")
            for task, (_, centroid, population, nearest) in zip(episode["prior"], expected_tasks):
                if set(task["centroid_fit_ids"]) != {row["episode_id"] for row in population} or not np.allclose(centroid, task["centroid"], atol=1e-12, rtol=0):
                    raise ValueError("Centroid không dùng toàn population cùng bucket")
                if [r["episode_id"] for r in nearest] != task["selected_by_distance_ids"]: raise ValueError("Rank cycle khác oracle label-blind")
            expected_target = sorted((row for row in eligible if row["block_index"] == query["block_index"]), key=lambda row: (row["as_of_date"], row["episode_id"]))[-8:]
            if [row["episode_id"] for row in expected_target] != [row["episode_id"] for row in episode["target"]]: raise ValueError("Target không phải tám cycle mới nhất cùng bucket")
        return {"selected_labels_checked": len(selected), "fact_packets_checked": 1+len(meta["historical_facts"])}


def _drop_prior(episode: dict[str, Any], index: int) -> dict[str, Any]:
    """Diagnostic bỏ task, không rerank/bù task và không thay policy theo kết quả."""
    value = deepcopy(episode)
    value["prior"].pop(index)
    value["K"] -= 1
    keep = {pid for task in value["prior"] for pid in task["centroid_fit_ids"]}|{row["episode_id"] for row in value["target"]}
    value["v3"]["historical_facts"] = {k: v for k, v in value["v3"]["historical_facts"].items() if k in keep}
    value["membership_sha256"] = membership_hash(value)
    validate_context(value)
    return value


def derive_report(identity: dict[str, Any], points: list[dict[str, Any]]) -> dict[str, Any]:
    """Giữ mọi điểm/nhóm và fail gate; không nominate hoặc thay candidate bằng ablation."""
    if [p["point_id"] for p in points] != [p["point_id"] for p in identity["cohort"]]:
        raise ValueError("Report thiếu/đổi denominator cohort")
    records = [r for point in points for r in point["approximation"]]
    approx = approximation(records)
    scopes = sorted({p["stage"] for p in points})
    coverage = {}
    for scope in ["all", *scopes]:
        scoped = points if scope == "all" else [p for p in points if p["stage"] == scope]
        groups: dict[str, Any] = {}
        for point in scoped:
            for name in ("Full_utility_ICL", "No_target"):
                wire = point["variants"][name]["utility"]
                labels = ["all", "symbol="+point["symbol"], "regime="+point["regime"], "bucket="+point["bucket"],
                          "K="+str(wire["K"]), "m="+str(wire["m"]), "cold_start="+str(wire["m"] == 0),
                          "n_gain="+str(wire["gain_count"]), "n_loss="+str(wire["loss_count"])]
                for label in labels:
                    counts = groups.setdefault(name+"/"+label, {"N": 0, "supported": 0, "positive": 0, "negative": 0, "cross_or_touch_zero": 0, "reasons": {}})
                    counts["N"] += 1
                    if wire["status"] == "SUPPORTED":
                        counts["supported"] += 1
                        counts["positive"] += int(wire["q10_U_net_fraction"] > 0)
                        counts["negative"] += int(wire["q90_U_net_fraction"] < 0)
                        counts["cross_or_touch_zero"] += int(wire["q10_U_net_fraction"] <= 0 <= wire["q90_U_net_fraction"])
                    counts["reasons"][wire["reason"]] = counts["reasons"].get(wire["reason"], 0)+1
        coverage[scope] = groups
    actionable = coverage["development2023"]["Full_utility_ICL/all"]
    failures = []
    if approx["status"] != "PASS": failures.append("FAIL_APPROXIMATION_NO_TEACHER_FALLBACK")
    if not actionable["positive"] and not actionable["negative"]: failures.append("NO_ACTIONABLE_CONTEXT")
    maximum = max((oracle["max_error"] for point in points for oracle in point["oracles"].values()), default=0.)
    return {"identity": identity, "status": failures[0] if failures else "OFFLINE_VALIDATION_PASS", "failed_gates": failures,
            "technical_status": "PASS", "cohort_N": len(points), "point_ids": [p["point_id"] for p in points],
            "approximation": {"union_gate": approx, "by_scope_descriptive": {scope: approximation([r for r in records if r["stage"] == scope]) for scope in scopes},
                              "by_branch_descriptive": {name: approximation([r for r in records if r["branch_id"] == name]) for name in ("Full_utility_ICL", "No_target")}},
            "coverage": coverage, "oracle_max_absolute_error": maximum,
            "oracle_draws_checked": sum(v["draws_checked"] for p in points for v in p["oracles"].values()),
            "semantic_contracts": "SCOPED_TESTS_AND_PER_POINT_SOURCE_MATH_PROJECTION_ABLATION_CHECKS",
            "exposure": "2021_2022_EXPOSED_DIAGNOSTIC_2023_ADAPTIVE_NOT_INDEPENDENT_VALIDATION",
            "query_outcomes_used": False, "API_calls": 0, "weights_refit": False, "teacher_point_fallback": False,
            "development_allowed": False, "decision_calls_allowed": False, "confirmation_allowed": False,
            "next_step": "W11-10_ONLY_IF_ALL_GATES_PASS" if not failures else "STOP_NO_API_KEEP_FAILURES_NO_TUNING"}


def run(root: Path, *, verify_only: bool = False) -> dict[str, Any]:
    """Một lệnh tự resume; point đã durable dùng lại, verify-only tái dựng toàn bộ không ghi đè."""
    stage = "cold_verification" if verify_only else "offline_validation"
    with RuntimeBudget(root, stage) as budget, threadpool_limits(limits=1):
        with PriorRunLock(root/"outputs/oos_pilot/api_usage.json.lock", "shared-account-ledger-v2"):
            inputs = load_inputs(root)
        budget.checkpoint()
        directory = root/OUTPUT
        identity = inputs["identity"]
        index_path = directory/"index.json"
        index = read_envelope(index_path, INDEX_VERSION) if index_path.exists() else {"identity": identity, "points": {}, "status": "RUNNING"}
        if index["identity"] != identity: raise ValueError("Source/cohort đã đổi; không reset/resume bằng identity mới")
        if verify_only and (index["status"] != "COMPLETE" or not (directory/"report.json").exists()): raise ValueError("Chưa đủ point/report để cold replay")
        configure(42, cuda=True)
        student = StudentAdapter(root, inputs["inherited"])
        teacher = BetaBernoulliTeacher(inputs["pi"])
        stream = MarketStream(inputs["bank"], inputs["prices"], pd.DatetimeIndex(inputs["history"]["Datetime"]))
        builder = BucketTaskBuilder(inputs["bank"], stream, inputs["regimes"], {s: f for s, (f, _) in inputs["prices"].items()})
        audit = SourceAudit(inputs["prices"], stream.calendar)
        points = []
        for number, query in enumerate(inputs["cohort"], 1):
            budget.check()
            pid = query["point_id"]
            episode = builder.build(query["symbol"], query["as_of_date"])
            path = directory/"points"/(pid+".json")
            if pid in index["points"] and not verify_only:
                if file_hash(path) != index["points"][pid]: raise ValueError("Point durable bị đổi byte")
                point = read_envelope(path, POINT_VERSION)
                if point["identity_sha256"] != content_hash(identity) or point["context_sha256"] != content_hash(episode): raise ValueError("Cached point khác context/source")
            else:
                source_checks = audit.context(episode, stream.closed_records(), inputs["regimes"])
                prepared = prepare_variants(episode, teacher, student.probability)
                check_projection(prepared)
                oracles, approx = {}, []
                for name, key in (("Full_utility_ICL", "Full"), ("No_target", "No_target")):
                    selected = prepared["contexts"][key]
                    result = {"wire": prepared["branches"][name]["utility"], "audit": prepared["posterior_audits"][key]}
                    oracle = check_posterior(selected, result, inputs["pi"])
                    oracles[name] = oracle
                    approx.append({"point_id": pid, "stage": query["stage"], "branch_id": name, "p": result["wire"]["probability_student"],
                                   "q": oracle["teacher"]["probability"] if oracle["teacher"] is not None else None})
                sensitivity = []
                if prepared["branches"]["Full_utility_ICL"]["probability"] is not None:
                    for i, task in enumerate(episode["prior"]):
                        budget.check()
                        subset = _drop_prior(episode, i)
                        p = student.probability(subset)
                        value = posterior_utility(subset, teacher, p)
                        proof = check_posterior(subset, value, inputs["pi"])
                        oracles["leave_out/"+task["task_id"]] = proof
                        sensitivity.append({"omitted_task_id": task["task_id"], "utility": value["wire"], "policy_selection_allowed": False})
                # Sidecar giữ seeds/hash/precision; draw tái dựng từ protocol, không nhân bản mảng lớn.
                posterior_audits = {name: {k: v for k, v in value.items() if k != "draws"} for name, value in prepared["posterior_audits"].items()}
                point = {**query, "identity_sha256": content_hash(identity), "context_sha256": content_hash(episode),
                         "context": episode, "symbol": query["symbol"], "regime": episode["query"]["regime"]["name"], "bucket": episode["v3"]["bucket"],
                         "variants": prepared["branches"], "posterior_audits": posterior_audits, "oracles": oracles,
                         "approximation": approx, "source_checks": source_checks, "leave_one_prior_out": sensitivity}
                if verify_only:
                    if read_envelope(path, POINT_VERSION) != point or file_hash(path) != index["points"][pid]: raise ValueError("Cold replay point khác bản durable")
                else:
                    write_envelope(path, POINT_VERSION, point, immutable=True)
                    index["points"][pid] = file_hash(path)
                    write_envelope(index_path, INDEX_VERSION, index)
            points.append(point)
            budget.checkpoint()
            if number % 20 == 0 or number == len(inputs["cohort"]):
                print(f"Đã {'replay' if verify_only else 'kiểm'} {number}/{len(inputs['cohort'])} point; còn {budget.remaining_seconds()/3600:.2f} giờ v3; không API/P&L query.", flush=True)
        report = derive_report(identity, points)
        if verify_only:
            if report != read_envelope(directory/"report.json", REPORT_VERSION): raise ValueError("Cold replay report không khớp")
            write_envelope(directory/"replay.json", PROOF_VERSION, {"status": "REPLAY_MATCH", "identity_sha256": content_hash(identity),
                "report_sha256": file_hash(directory/"report.json"), "point_count": len(points), "point_tree_sha256": content_hash(index["points"]),
                "gate_status": report["status"], "API_calls": 0}, immutable=True)
        else:
            write_envelope(directory/"report.json", REPORT_VERSION, report, immutable=True)
            index["status"] = "COMPLETE"
            write_envelope(index_path, INDEX_VERSION, index)
        budget.checkpoint()
        return report
