"""Chuẩn bị các ablation MT-BICL và BRPP đầy đủ counts, không gọi LLM hoặc đọc outcome query."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import math
from typing import Any, Callable

import numpy as np

from core.mt_bicl_bank import content_hash
from core.mt_bicl_teacher import BetaBernoulliTeacher
from core.mt_bicl_contracts import REVISION_BRANCHES, validate_branch, validate_context, validate_wire, without_target
from core.mt_bicl_utility import posterior_utility

LEGEND = "q=(mom5,mom20,vol20,ma20)≈2z;y=1:net>0;r,U=net fraction;a=tuổi ngày;n/w/l/r=toàn tập;e=projection;p=P(y=1)≠ER"


class NoActionableContext(RuntimeError):
    """Không có interval nào đủ evidence sửa action: dừng trước API, không hạ threshold."""


def require_actionable_context(points: list[dict[str, Any]]) -> dict[str, int]:
    """Gate toàn bộ context đã đăng ký, không lọc theo outcome hoặc action LLM."""
    ids: set[str] = set()
    supported = positive = negative = 0
    for point in points:
        full = point["branches"]["MT_BICL"]
        validate_branch(full)
        if full["point_id"] in ids:
            raise ValueError("Gate actionable nhận point trùng")
        ids.add(full["point_id"])
        wire = full["utility"]
        validate_wire(wire, "utility")
        if wire["point_id"] != full["point_id"] or wire["branch_id"] != "MT_BICL":
            raise ValueError("Gate actionable dùng sai candidate/point")
        if wire["status"] == "SUPPORTED":
            supported += 1
            positive += wire["q10_U_net_fraction"] > 0
            negative += wire["q90_U_net_fraction"] < 0
    counts = {"points": len(ids), "supported": supported, "positive_interval": positive, "negative_interval": negative}
    if not positive and not negative:
        raise NoActionableContext("NO_ACTIONABLE_CONTEXT: không gọi API hoặc hạ threshold")
    return counts


def _code(vector: list[float]) -> str:
    """Giữ lượng tử ties-to-even của bốn feature MT-BICL, không thêm bucket vào tensor."""
    return "("+",".join(str(value) for value in np.clip(np.rint(np.asarray(vector)*2), -8, 8).astype(int).tolist())+")"


def project_context(episode: dict[str, Any], *, branch_id: str, probability: float | None,
                    utility: dict[str, Any] | None) -> dict[str, Any]:
    """Tối đa một exemplar/P/T; summary dùng toàn membership kể cả phần không hiển thị."""
    validate_context(episode)
    if branch_id not in REVISION_BRANCHES:
        raise ValueError("Nhánh projection không thuộc revision MT-BICL")
    if probability is not None and (type(probability) not in (int, float) or not math.isfinite(probability) or not 0 <= probability <= 1):
        raise ValueError("p projection không hữu hạn hoặc ngoài [0,1]")
    if branch_id == "Plain_revision" and probability is not None:
        raise ValueError("Plain_revision không nhận p")
    if branch_id in ("Plain_revision", "No_utility") and utility is not None:
        raise ValueError("Ablation bỏ utility không được nhận U")
    if utility is not None:
        validate_wire(utility, "utility")
        if utility["membership_sha256"] != episode["membership_sha256"] or utility["status"] != "SUPPORTED":
            raise ValueError("U projection không thuộc membership có support")
    header = f"MT3 K{episode['K']} m{episode['m']}"+(" nhỏ" if episode["m"] <= 3 else "")
    if probability is not None:
        header += f" p={probability:.3f}"
    parts, summaries, examples = [header], [], []
    groups = [(f"P{i}", task["observations"]) for i, task in enumerate(episode["prior"], 1)]
    if branch_id != "No_target":
        groups.append(("T", episode["target"]))
    for name, rows in groups:
        wins = sum(row["y"] for row in rows)
        mean = math.fsum(row["r_net"] for row in rows)/len(rows) if rows else None
        ages = [row["age_days"] for row in rows]
        summary = {"task": name, "n": len(rows), "wins": wins, "losses": len(rows)-wins,
                   "mean_r_net_fraction": mean, "age_days_min": min(ages) if ages else None,
                   "age_days_max": max(ages) if ages else None}
        summaries.append(summary)
        line = f"{name} n{len(rows)} w{wins} l{len(rows)-wins} r"+(f"{mean:+.3g}" if mean is not None else "NA")
        line += " a"+(f"{min(ages)}..{max(ages)}" if ages else "NA")
        if rows and branch_id != "Stats_only":
            row = min(rows, key=lambda r: (r["distance"], -date.fromisoformat(r["as_of_date"]).toordinal(), r["episode_id"]))
            exemplar = {"task": name, "episode_id": row["episode_id"], "model_vector": list(row["model_vector"]),
                        "y": row["y"], "r_net_fraction": row["r_net"], "age_days": row["age_days"]}
            examples.append(exemplar)
            line += f" e{_code(row['model_vector'])}>{row['y']},r{row['r_net']:+.3g},a{row['age_days']}"
        parts.append(line)
    if utility is not None:
        parts.append("U(mean,MC,Q10,Q90)="+"/".join(f"{utility[key]:+.3g}" for key in (
            "mean_U_net_fraction", "MC_mean_U_net_fraction", "q10_U_net_fraction", "q90_U_net_fraction"))
                     +f" n+{utility['gain_count']} n-{utility['loss_count']}")
    parts.extend(("Q"+_code(episode["query"]["model_vector"]), LEGEND if probability is not None else LEGEND.split(";p=")[0]))
    prefix = "\n".join(parts)
    if len(prefix) > 600:
        raise ValueError("FAIL_PROMPT_BUDGET: BRPP MT-BICL vượt600, không cắt counts/legend")
    result = {"prefix": prefix, "prefix_chars": len(prefix), "summary": summaries,
              "small_target": episode["m"] <= 3, "membership_sha256": episode["membership_sha256"]}
    if branch_id != "Stats_only":
        result["exemplars"] = examples
    content_hash(result)
    return result


def prepare_variants(episode: dict[str, Any], teacher: BetaBernoulliTeacher,
                     probability: Callable[[dict[str, Any]], float]) -> dict[str, Any]:
    """Hai forward frozen cho Full/No_target; không dùng p MT-BICL hoặc U Full thay No_target."""
    validate_context(episode)
    no_target = without_target(episode)
    facts = episode["advisor"]["query_facts"]
    available = episode["status"] == "AVAILABLE" and facts["prefix_rows"] == 45 and facts["frame_end_date"] == facts["as_of_date"] and facts["bucket"] != "UNKNOWN"

    def calculate(selected: dict[str, Any], name: str) -> dict[str, Any]:
        """Callback nhận deep-copy, phát hiện mutate và không che lỗi model bằng abstention."""
        before = content_hash(selected)
        working = deepcopy(selected)
        p = probability(working) if available else None
        if content_hash(working) != before:
            raise ValueError("Student callback đã mutate context")
        return posterior_utility(selected, teacher, p, branch_id=name)

    full = calculate(episode, "MT_BICL")
    removed = calculate(no_target, "No_target")
    result: dict[str, Any] = {"contexts": {"Full": deepcopy(episode), "No_target": no_target},
                              "posterior_audits": {"Full": full["audit"], "No_target": removed["audit"]}, "branches": {}}
    for name in (*REVISION_BRANCHES, "Utility_only"):
        source = removed["wire"] if name == "No_target" else full["wire"]
        selected = no_target if name == "No_target" else episode
        enabled = source["status"] == "SUPPORTED"
        carries_U = name not in ("Plain_revision", "No_utility")
        wire = {**deepcopy(source), "branch_id": name} if carries_U else None
        p = None if name == "Plain_revision" else source["probability_student"]
        projection = project_context(selected, branch_id=name, probability=p, utility=wire) if enabled and name != "Utility_only" else None
        result["branches"][name] = {"branch_id": name, "point_id": episode["query"]["episode_id"],
            "eligible": enabled, "reason": source["reason"], "probability": p, "utility": wire,
            "membership_sha256": selected["membership_sha256"], "projection": projection,
            "eligibility_source_membership_sha256": source["membership_sha256"]}
        validate_branch(result["branches"][name])
    content_hash(result)
    return result
