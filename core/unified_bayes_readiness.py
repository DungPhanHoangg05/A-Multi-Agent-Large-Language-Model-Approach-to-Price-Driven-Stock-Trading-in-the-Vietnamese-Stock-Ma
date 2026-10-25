"""Khóa dry-run, coverage/repeat và MDE giả định từ train, không chấm query OOS."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from core.bayesian_memory import iso_date, read_json
from core.historical_signals import digest
from core.price_feature_index import _json_bytes
from core.prior_run_lock import safe_path
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once, runtime_identity
from core.unified_bayes_contracts import ROOT, SYMBOLS, sha
from core.unified_bayes_source import BoundCohort, readiness, repeat_sample
from core.unified_bayes_validation import diagnostics, read_validation, validation_identity

VERSION = "unified_bic_readiness_assessment_v1"
POLICY_PATH = ROOT / "docs/plan/week10/fixtures/unified_bic_planning_v1.json"
POOLING_PATH = ROOT / "outputs/bayesian_benchmark/unified_bic_v1/inputs/pooling_diagnostics_v1.json"
POOLING_SHA = "575b650ceb88b7c69bdbe73786b1240d0a9f0bcc60b820f186b7486535993dca"


def planning_policy() -> dict[str, Any]:
    """Hằng số planning cố định trong code trước khi xem kết quả mô phỏng."""
    expected = {"planning_version": "unified_bic_planning_v1",
        "calibration": "purged_train_2021_2022_complete_four_symbol_cutoff_clusters",
        "layouts": ["development_locked_mask", "hypothetical_128_32_shared_cutoffs"],
        "calibration_panels": ["train_2021_2022", "train_2021", "train_2022"],
        "blocks": [4, 2, 8], "draws": 10000, "seed": 20261024, "rng": "PCG64",
        "disagreement_rates": [.1, .25, .5], "long_probability": .5,
        "proxy_actions": "iid_cutoff_common_across_symbols_symmetric_flip", "antithetic_branch_swap": True,
        "effect_shift": "terminal_equal_weight_account_delta_return_pp",
        "effect_grid_pp": [0, 1, 2, 3, 5, 10, 15, 20, 30], "critical_quantile": .975,
        "target_power": .8, "quantile_method": "linear",
        "inference": "planning_location_shift_not_protocol_bootstrap_or_observed_LLM_power",
        "changes_sample_or_method": False, "confirmation_release": False}
    if digest(read_json(POLICY_PATH)) != digest(expected):
        raise ValueError("Policy MDE khác các giả định đã khóa; không chọn theo power đẹp")
    return expected


def training_panels(pooling: dict[str, Any], memory: dict[str, Any]) -> dict[str, Any]:
    """Chỉ lấy 2021/2022 đã purge; kiểm nhãn với memory rồi giữ cụm đủ bốn mã."""
    if pooling["memory_sha256"] != digest(memory) or pooling["protocol_sha256"] != memory["protocol_sha256"]:
        raise ValueError("Nguồn MDE khác memory/protocol đã kiểm")
    records = {row["episode_id"]: row for row in memory["records"]}
    seen, by_date = set(), {}
    for row in pooling["points"]:
        key, symbol, cutoff, exit_date = (row[name] for name in ("episode_id", "symbol", "as_of_date", "exit_date"))
        year = cutoff[:4]
        original = records.get(key)
        if (key in seen or key != f"{symbol}:{cutoff}" or symbol not in SYMBOLS or year not in ("2021", "2022")
                or not iso_date(cutoff) < iso_date(exit_date) <= year + "-12-31"
                or row["fold_id"] != "train_" + year or original is None
                or any(row[name] != original[name] for name in ("symbol", "as_of_date", "exit_date"))
                or type(row["net_long_return"]) not in (int, float) or not np.isfinite(row["net_long_return"])
                or row["net_long_return"] <= -1
                or row["net_long_return"] != original["outcome"]["net_return_pct"] / 100.):
            raise ValueError("MDE chứa nhãn OOS/alias/cycle chưa đóng hoặc khác nhãn engine nguồn")
        seen.add(key)
        by_date.setdefault(cutoff, {})[symbol] = float(row["net_long_return"])
    expected = {key for fold in pooling["folds"].values() for key in fold["query_ids"]}
    if seen != expected or len(seen) != pooling["query_count"]:
        raise ValueError("MDE thiếu/thừa query train đã purge")
    panels = {}
    for name in planning_policy()["calibration_panels"]:
        dates = sorted(day for day, values in by_date.items() if len(values) == 4 and
                       (name == "train_2021_2022" or day.startswith(name.removeprefix("train_"))))
        if len(dates) < 8:
            raise ValueError("MDE thiếu cụm train đủ bốn mã; không điền return thiếu bằng 0")
        selected = {day for day in by_date if name == "train_2021_2022" or day.startswith(name.removeprefix("train_"))}
        panels[name] = {"dates": dates, "net_returns": [[by_date[day][s] for s in SYMBOLS] for day in dates],
            "source_rows": sum(len(by_date[day]) for day in selected),
            "excluded_incomplete_cluster_dates": sorted(selected-set(dates)),
            "included_episode_ids": [f"{s}:{day}" for day in dates for s in SYMBOLS]}
    return panels


def account_delta(returns: np.ndarray, original_long: np.ndarray, candidate_long: np.ndarray,
                  mask: np.ndarray) -> np.ndarray:
    """Bốn tài khoản fractional/full-cash, compounding net đã có phí; không cộng cycle."""
    values = np.asarray(returns, dtype=float)
    if (values.ndim != 3 or values.shape[2] != 4 or not np.isfinite(values).all() or (values <= -1).any()
            or original_long.shape != values.shape or candidate_long.shape != values.shape
            or original_long.dtype != bool or candidate_long.dtype != bool
            or mask.shape != values.shape[1:] or mask.dtype != bool or not mask.any(axis=0).all()):
        raise ValueError("Panel/action/mask MDE sai shape, thiếu mã hoặc không hữu hạn")
    a = np.prod(1. + values * (candidate_long & mask), axis=1)
    b = np.prod(1. + values * (original_long & mask), axis=1)
    result = 100. * np.mean(a-b, axis=1)
    if not np.isfinite(result).all():
        raise ValueError("Tài khoản MDE vượt miền hữu hạn")
    return result


def simulate_noise(panel: np.ndarray, mask: np.ndarray, *, block: int, disagreement: float,
                   draws: int, seed: int) -> np.ndarray:
    """Resample cụm ngày cùng bốn mã; proxy LONG=1/2, flip đối xứng, swap antithetic."""
    values = np.asarray(panel, dtype=float)
    if (values.ndim != 2 or values.shape[1] != 4 or not len(values) or not np.isfinite(values).all()
            or (values <= -1).any() or mask.ndim != 2 or mask.shape[1] != 4 or mask.dtype != bool
            or not mask.any(axis=0).all() or type(block) is not int or block < 1
            or type(draws) is not int or draws < 4 or draws % 2 or type(seed) is not int
            or type(disagreement) not in (int, float) or not 0 <= disagreement <= 1):
        raise ValueError("Tham số mô phỏng MDE không hợp lệ")
    rng = np.random.Generator(np.random.PCG64(seed))
    n, half = len(mask), draws // 2
    starts = rng.integers(0, len(values), size=(half, (n+block-1)//block))
    indices = ((starts[..., None]+np.arange(block)) % len(values)).reshape(half, -1)[:, :n]
    sampled = values[indices]
    original = np.broadcast_to((rng.random((half, n, 1)) < .5), sampled.shape)
    flip = np.broadcast_to((rng.random((half, n, 1)) < disagreement), sampled.shape)
    delta = account_delta(sampled, original, original ^ flip, mask)
    return np.concatenate((delta, -delta))


def mde_planning(panels: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """MDE location-shift chỉ là planning; không thay bootstrap xác nhận hoặc chọn N."""
    policy = planning_policy()
    dates = sorted({pid[4:] for pid in plan["requests"]})
    mask = np.array([[f"{symbol}-{day}" in plan["requests"] for symbol in SYMBOLS] for day in dates], dtype=bool)
    layouts = {"development_locked_mask": mask, "hypothetical_128_32_shared_cutoffs": np.ones((32, 4), dtype=bool)}
    results = []
    for panel_name in policy["calibration_panels"]:
        for layout, active in layouts.items():
            for block in policy["blocks"]:
                for rate in policy["disagreement_rates"]:
                    noise = simulate_noise(np.asarray(panels[panel_name]["net_returns"]), active,
                        block=block, disagreement=rate, draws=policy["draws"], seed=policy["seed"])
                    critical = float(np.quantile(noise, policy["critical_quantile"], method="linear"))
                    threshold = float(critical-np.quantile(noise, 1-policy["target_power"], method="linear"))
                    curve = []
                    for effect in policy["effect_grid_pp"]:
                        hits = (noise+effect > critical).astype(float)
                        pair_rates = (hits[:len(noise)//2] + hits[len(noise)//2:]) / 2.
                        curve.append({"effect_pp": effect, "power": float(hits.mean()),
                            "monte_carlo_se": float(pair_rates.std(ddof=1)/np.sqrt(len(pair_rates)))})
                    results.append({"calibration": panel_name, "layout": layout, "block": block,
                        "disagreement_rate": rate, "points": int(active.sum()), "cutoff_clusters": len(active),
                        "per_symbol": {s: int(active[:, j].sum()) for j, s in enumerate(SYMBOLS)},
                        "noise_sha256": hashlib.sha256(np.asarray(noise, dtype="<f8").tobytes()).hexdigest(),
                        "critical_delta_pp": critical, "location_shift_mde_80_pp": max(0., threshold),
                        "power_curve": curve})
    return {"status": "PLANNING_ONLY", "policy": policy, "policy_sha256": digest(policy),
        "draws": policy["draws"], "independent_antithetic_pairs": policy["draws"]//2,
        "source_panels": {name: {k: v for k, v in row.items() if k != "net_returns"} |
                          {"net_returns_sha256": digest(row["net_returns"])} for name, row in panels.items()},
        "scenarios": results, "confirmation_power_certified": False, "alters_sample_or_method": False,
        "limitations": ["Proxy action giả định, không phải Decision hoặc noise LLM quan sát được.",
            "Location shift ở delta tài khoản cuối kỳ, không là mô phỏng hiệu ứng policy hoặc bootstrap CI trong protocol.",
            "Train complete-case và stationarity/circular blocks là giả định; báo cả từng năm và L=2/8.",
            "128 điểm là layout giả định 32 cụm cùng ngày, chưa là lịch 2025; không chứng nhận đủ power."]}


def repeat_design(plan: dict[str, Any]) -> dict[str, Any]:
    """Giải trình strata/fill trước action và giữ toàn lịch primary/repeat đã khóa."""
    if plan["repeat_sample"] != repeat_sample(plan["requests"]):
        raise ValueError("Mẫu repeat khác rule readiness đã khóa")
    strata = ("both_ready", "one_block_ready", "off")
    selected = []
    for symbol in SYMBOLS:
        ids = sorted(pid for pid in plan["requests"] if pid.startswith(symbol + "-"))
        first = {name: next((pid for pid in ids if readiness(plan["requests"][pid]) == name), None) for name in strata}
        chosen = [pid for pid in first.values() if pid]
        missing = [name for name in strata if first[name] is None]
        fill = [pid for pid in ids if pid not in chosen][:max(0, 3-len(chosen))]
        for pid in [*chosen, *fill]:
            selected.append({"point_id": pid, "stratum": readiness(plan["requests"][pid]),
                "selection_reason": "FIRST_AVAILABLE_STRATUM" if pid in chosen else "FILL_MISSING_STRATUM",
                "missing_strata": missing, "filled_for": missing[fill.index(pid)] if pid in fill else None,
                "upstream_sha256": digest(plan["requests"][pid]["upstream"]),
                "packets_sha256": digest(plan["requests"][pid]["packets"])})
    selected.sort(key=lambda row: (row["point_id"][4:], SYMBOLS.index(row["point_id"][:3])))
    if [row["point_id"] for row in selected] != plan["repeat_sample"]:
        raise ValueError("Giải trình repeat khác mẫu đã khóa")
    return {"sample": selected, "additional_repeat_ids": [1, 2, 3], "in_primary": False,
        "schedule": deepcopy(plan["schedule"]), "schedule_sha256": digest(plan["schedule"]),
        "order_policy": "Original_first_primary_j_mod_4_repeat_(3j+r-1)_mod_5", "vote": False}


def coverage(diag: dict[str, Any]) -> dict[str, Any]:
    """Gate coverage dự kiến, không giả common support của các LLM chưa chạy."""
    overall, stocks = diag["overall"], diag["by_symbol"]
    rules = {
        "prior_visible": overall["branches"]["U_full"]["visible_count"] >= 30 and all(v["branches"]["U_full"]["visible_count"] >= 5 for v in stocks.values()),
        "examples_visible": overall["branches"]["U_examples"]["visible_count"] >= 12 and all(v["branches"]["U_examples"]["visible_count"] >= 2 for v in stocks.values()),
        "multi_task_claim": overall["at_least_two_selected_tasks"] >= 12 and all(v["at_least_two_selected_tasks"] >= 2 for v in stocks.values())}
    return {"checks": {name: "PASS" if value else "INSUFFICIENT_EVIDENCE" for name, value in rules.items()},
        "overall": deepcopy(overall), "by_symbol": deepcopy(stocks), "observed_llm_common_support": 0,
        "observed_repeat_pairs": 0, "actual_llm_outcomes": "NOT_RUN", "nomination_allowed": False}


def build_assessment(cohort: BoundCohort, plan: dict[str, Any], llm: Any, memory: dict[str, Any],
                     audit_path: Path, *, pooling_path: Path = POOLING_PATH) -> dict[str, Any]:
    """Nguồn/request/audit tái dựng trước MDE, không tạo run/UUID hoặc đọc payoff OOS."""
    diag = diagnostics(cohort, plan, llm, memory)
    audit = read_validation(audit_path, plan, diag)
    real = plan["split"] == "development_2023_exploratory"
    if real and (pooling_path.resolve() != POOLING_PATH.resolve() or sha(pooling_path) != POOLING_SHA or len(plan["requests"]) != 60):
        raise ValueError("Assessment thật khác nguồn pooling/60 điểm đã khóa")
    pooling = read_envelope(pooling_path)
    if pooling["runtime"] != plan["runtime"] or pooling["protocol_sha256"] != plan["protocol_sha256"]:
        raise ValueError("Pool MDE khác runtime/protocol")
    if real and pooling["query_count"] != 647:
        raise ValueError("MDE thật phải dùng đúng 647 query đã purge")
    panels = training_panels(pooling, memory)
    report = {"assessment_version": VERSION, "stage": "U10_09", "split": plan["split"],
        "plan_sha256": digest(plan), "request_lock_sha256": plan["request_lock_sha256"],
        "source_sha256": deepcopy(plan["sources"]), "execution_code_sha256": plan["code_sha256"]}
    for name, checksum in pooling["sources"].items():
        if sha(safe_path(ROOT, name)) != checksum:
            raise ValueError("Nguồn pooling thay đổi trong planning")
    report.update({"validation_code_sha256": validation_identity(), "runtime": runtime_identity(),
        "models": deepcopy(plan["models"]), "model_preflight": "PENDING_MANUAL_NONRESEARCH_PREFLIGHT",
        "technical_gates_sha256": audit["technical_gates_sha256"], "validation_audit_sha256": sha(audit_path),
        "pooling_sha256": sha(pooling_path), "diagnostics_payload_sha256": digest(diag),
        "coverage": coverage(diag), "repeat": repeat_design(plan), "mde": mde_planning(panels, plan),
        "logical_slots": {"primary_llm": sum(len(row["order"]) for row in plan["schedule"] if row["repeat_id"] == 0),
            "repeat_llm": sum(len(row["order"]) for row in plan["schedule"] if row["repeat_id"] != 0),
            "numeric_offline_blocks": len(plan["schedule"])},
        "http_attempts": 0, "query_evaluations": 0, "risk_policy": "OFF",
        "confirmation_allowed": False, "nomination_allowed": False, "api_executed": False,
        "handoff": "PENDING_U10_10_AND_U11_01"})
    report["execution_readiness"] = {"readiness_version": "unified_bic_execution_readiness_v1", "stage": "U10_09",
        "plan_sha256": digest(plan), "technical_gates_sha256": audit["technical_gates_sha256"],
        "request_lock_sha256": plan["request_lock_sha256"], "confirmation_allowed": False} if real else None
    _json_bytes(report)
    # Không dùng checksum của chính report làm nguồn tin; kiểm lại source/audit sau mô phỏng.
    cohort.verify(llm)
    read_validation(audit_path, plan, diag)
    if sha(pooling_path) != report["pooling_sha256"]:
        raise ValueError("Nguồn MDE đổi trong mô phỏng")
    return report


def read_assessment(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    """Tự reseal số liệu, mẫu repeat, model hoặc MDE đều không thay bản dựng lại."""
    saved = read_envelope(path)
    if digest(saved) != digest(expected):
        raise ValueError("Assessment khác source/schedule/model/MDE đã tái dựng")
    return saved


def publish(root: Path, expected: dict[str, Any], cohort: BoundCohort, plan: dict[str, Any], llm: Any,
            *, prepare: bool = False) -> None:
    """Bridge sáu field đúng consumer U10-07; không ghi authorization hoặc preflight của run."""
    if (cohort.split != "development_2023_exploratory" or expected["split"] != cohort.split
            or expected["execution_readiness"] is None or expected["plan_sha256"] != digest(plan)
            or digest(plan) != digest(cohort.plan(llm)) or expected["validation_code_sha256"] != validation_identity()):
        raise ValueError("Fixture không được phát hành readiness development")
    for name, value in (("assessment.json", expected), ("execution_readiness.json", expected["execution_readiness"])):
        path = root / name
        if prepare:
            _write_once(path, value)
        if digest(read_envelope(path)) != digest(value):
            raise ValueError("Artifact readiness khác producer nguồn hiện tại")
