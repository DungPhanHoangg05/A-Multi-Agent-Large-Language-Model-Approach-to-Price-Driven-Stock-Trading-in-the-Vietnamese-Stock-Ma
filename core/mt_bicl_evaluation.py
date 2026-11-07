"""Xác suất số ổn định và chiếu episode PIT sang input model."""

from __future__ import annotations
from copy import deepcopy
from typing import Any
import numpy as np
from core.mt_bicl_bank import content_hash
from core.mt_bicl_tasks import validate_episode

def probabilities(logits: list[float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Logsigmoid float64 gốc, không clip logits/probability để giảm KL."""
    z = np.asarray(logits, dtype=np.float64)
    if z.ndim != 1 or not np.isfinite(z).all():
        raise ValueError("Logit phải là vector hữu hạn")
    one, zero = -np.logaddexp(0, -z), -np.logaddexp(0, z)
    p = np.exp(one)
    if ((p < 0) | (p > 1)).any():
        raise ValueError("Xác suất gốc ngoài [0,1]")
    return p, one, zero


def market_input(row: dict[str, Any], context: dict[str, Any], mode: str = "full") -> dict[str, Any]:
    """Kiểm PIT trước bỏ metadata; query y/r_net không đi vào input oracle hoặc learner."""
    if mode not in ("full", "no_prior", "no_target"):
        raise ValueError("Ablation không thuộc protocol")
    episode = deepcopy(row)
    episode["scaler"] = context["scalers"][episode.pop("scaler_sha256")]
    for key in ("supervised_target", "packed", "projection_fixture", "split"):
        episode.pop(key, None)
    validate_episode(episode)
    def observation(r: dict[str, Any]) -> dict[str, Any]:
        """Chỉ x/y của cycle đã đóng; không r_net, date hoặc regime trong tensor."""
        return {"observation_id": r["episode_id"], "x": list(r["model_vector"]), "y": r["y"]}
    return {"prior": [] if mode == "no_prior" else [
                {"task_id": t["task_id"], "observations": [observation(r) for r in t["observations"]]}
                for t in episode["prior"]],
            "target": {"task_id": episode["query"]["task_id"], "observations": [] if mode == "no_target"
                       else [observation(r) for r in episode["target"]]},
            "query": {"observation_id": episode["query"]["episode_id"], "x": list(episode["query"]["model_vector"])}}
