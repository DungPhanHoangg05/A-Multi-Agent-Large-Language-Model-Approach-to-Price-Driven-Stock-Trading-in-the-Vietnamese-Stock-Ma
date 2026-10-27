"""Packing numeric và projection task examples MT-BICL; không gọi learner/LLM."""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

import numpy as np

from core.mt_bicl_bank import canonical_bytes
from core.mt_bicl_tasks import validate_episode

LEGEND = "q=(mom5,mom20,vol20,ma20); z≈q/2; y=1:net>0; p=P(y=1), không phải ER"


def without_target(episode: dict[str, Any]) -> dict[str, Any]:
    """Bỏ đúng C, giữ D/query; caller phải recompute p, không lấy p Full."""
    result = deepcopy(episode)
    result.update(target=[], m=0)
    result.pop("membership_sha256", None)
    result["reasons"] = [*result["reasons"], "TARGET_DISABLED"]
    validate_episode(result)
    return result


def pack_episode(episode: dict[str, Any], *, training_query_y: int | None = None) -> dict[str, Any]:
    """Che nhãn query trong input; chỉ đặt nhãn ngoài tensor ở vị trí loss target."""
    validate_episode(episode)
    if episode["status"] != "AVAILABLE":
        raise ValueError("Không pack episode thiếu feature/scaler")
    if training_query_y is not None and (type(training_query_y) is not int or training_query_y not in (0, 1)):
        raise ValueError("Nhãn query train phải là 0/1 gốc")
    values, roles, positions, labels = [], [], [], []
    for role, observations in [*( (0, t["observations"]) for t in episode["prior"]), (1, episode["target"])]:
        values.append([0., 0., 0., 0., -1., 1.])
        roles.append(role)
        for row in observations:
            if role == 1:
                positions.append(len(values))
                labels.append(row["y"])
            values.extend([[*row["model_vector"], 0., 1.], [0., 0., 0., 0., float(row["y"]), 0.]])
            roles.extend([role, role])
    positions.append(len(values))
    labels.append(training_query_y)
    values.append([*episode["query"]["model_vector"], 0., 1.])
    roles.append(2)
    if len(values) > 69:
        raise ValueError("Numeric context vượt 69 token")
    result = {"values": values, "roles": roles, "prediction_positions": positions,
              "external_loss_labels": labels, "query_position": len(values)-1,
              "causal_mask": "LOWER_TRIANGULAR_INCLUDING_SELF", "padding": "RIGHT_KEY_MASK_REQUIRED"}
    canonical_bytes(result)
    return result


def _code(vector: list[float]) -> str:
    """Lượng tử hóa z clip thành bốn mã integer, ties-to-even như protocol."""
    return "("+",".join(str(v) for v in np.clip(np.rint(np.asarray(vector)*2), -8, 8).astype(int).tolist())+")"


def project_episode(episode: dict[str, Any], *, probability: float | None = None,
                    mode: str = "full") -> dict[str, Any]:
    """Chiếu tối đa 2/prior +2 target; None chỉ là fixture chưa có learner p."""
    validate_episode(episode)
    if episode["status"] != "AVAILABLE" or mode not in ("full", "examples", "stats"):
        raise ValueError("Projection cần episode AVAILABLE và mode hợp lệ")
    if probability is not None and (type(probability) not in (float, int) or not math.isfinite(probability) or not 0 <= probability <= 1):
        raise ValueError("Xác suất phải hữu hạn trong [0,1]")
    if mode == "examples" and probability is not None:
        raise ValueError("Plain examples không được nhận learned p")
    counts = "/".join(str(len(t["observations"])) for t in episode["prior"]) or "0"
    head = f"MT K={episode['K']} m={episode['m']} n={counts}"
    if mode != "examples":
        head += " p="+("NA" if probability is None else f"{probability:.3f}")
    pieces, visible = [head], {"prior": [], "target": []}
    if mode != "stats":
        for index, task in enumerate(episode["prior"], 1):
            ids = set(task["selected_by_distance_ids"][:2])
            examples = [r for r in task["observations"] if r["episode_id"] in ids]
            pieces.append(f"P{index}:"+";".join(_code(r["model_vector"])+">"+str(r["y"]) for r in examples))
            visible["prior"].append([r["episode_id"] for r in examples])
        examples = episode["target"][-2:]
        pieces.append("T:"+";".join(_code(r["model_vector"])+">"+str(r["y"]) for r in examples))
        visible["target"] = [r["episode_id"] for r in examples]
    pieces.append("Q:"+_code(episode["query"]["model_vector"]))
    pieces.append(LEGEND if mode != "examples" else LEGEND.split("; p=")[0])
    prefix = "\n".join(pieces)
    if len(prefix) > 600:
        raise ValueError("FAIL_BUDGET: toàn BRPP vượt 600 ký tự")
    return {"prefix": prefix, "prefix_chars": len(prefix), "visible_ids": visible,
            "learner_prior_count": sum(len(t["observations"]) for t in episode["prior"]),
            "learner_target_count": episode["m"], "projection_is_full_context": False,
            "probability_status": "NOT_SUPPLIED" if probability is None else "SUPPLIED_BY_CALLER"}


def check_prompt_length(prompt: str) -> None:
    """Kiểm prompt đã render toàn bộ, không cắt distill/cap hoặc đếm thiếu separator."""
    if type(prompt) is not str or len(prompt) >= 6500:
        raise ValueError("FAIL_BUDGET: prompt Decision phải dưới 6500 ký tự")
