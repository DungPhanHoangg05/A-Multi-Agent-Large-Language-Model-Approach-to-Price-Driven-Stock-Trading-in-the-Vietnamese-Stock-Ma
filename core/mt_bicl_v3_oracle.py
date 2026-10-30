"""Oracle utility độc lập theo tích tuần tự và từng magnitude, không gọi sampler production."""

from __future__ import annotations

import hashlib
import math
from typing import Any

import numpy as np
from scipy.stats import beta as beta_distribution

from core.mt_bicl_v2_reference import SequentialBetaOracle
from core.mt_bicl_v3_protocol import PROTOCOL_SHA256


def numeric_input(episode: dict[str, Any]) -> dict[str, Any]:
    """Chỉ chiếu x/y context và x query, không nhận nhãn query hoặc latent simulator."""
    def rows(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Đổi tên schema observation, giữ thứ tự task/cycle."""
        return [{"observation_id": row["episode_id"], "x": row["model_vector"], "y": row["y"]} for row in selected]
    return {"prior": [{"task_id": t["task_id"], "observations": rows(t["observations"])} for t in episode["prior"]],
            "target": {"task_id": episode["query"]["task_id"], "observations": rows(episode["target"])},
            "query": {"observation_id": episode["query"]["episode_id"], "x": episode["query"]["model_vector"]}}


def _uniforms(point: str, component: str) -> np.ndarray:
    """Tái hiện seed/material/range độc lập, không import component_seed/common_uniforms."""
    material = f"utility-v3|{PROTOCOL_SHA256}|{point}|{component}"
    seed = int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:16], "big")
    return np.random.Generator(np.random.PCG64(seed)).integers(1, 2**53, size=4096, dtype=np.uint64).astype(float)/(2**53)


def check_posterior(episode: dict[str, Any], result: dict[str, Any], pi: list[float]) -> dict[str, Any]:
    """So mean θ/U và mọi draw; sai số MC mean không là gate so với mean giải tích."""
    wire, audit = result["wire"], result["audit"]
    if episode["query"]["model_vector"] is None:
        if wire["status"] == "SUPPORTED" or audit["draws"] is not None:
            raise ValueError("Query missing vẫn khai sampling")
        return {"status": "PASS", "supported": False, "teacher": None, "draws_checked": 0, "max_error": 0.}
    reference = SequentialBetaOracle(pi).predict(numeric_input(episode), posterior=True)
    if wire["status"] != "SUPPORTED":
        if audit["draws"] is not None or wire["draws"] != 0:
            raise ValueError("Unsupported vẫn khai đã sampling")
        return {"status": "PASS", "supported": False, "teacher": reference, "draws_checked": 0, "max_error": 0.}
    rows = sorted([r for task in episode["prior"] for r in task["observations"]]+episode["target"], key=lambda r: r["episode_id"])
    gain_rows = [row for row in rows if row["r_net"] > 0]
    loss_rows = [row for row in rows if row["r_net"] <= 0]
    point = episode["query"]["episode_id"]
    uniforms = {row["episode_id"]: _uniforms(point, "magnitude|"+row["episode_id"]) for row in rows}
    lambda_u, theta_u = _uniforms(point, "lambda"), _uniforms(point, "theta")
    mass = reference["lambda_posterior"]
    latent = []
    gain, loss = [], []
    for i in range(4096):
        total, selected = 0., 15
        for j, weight in enumerate(mass):
            total += weight
            if lambda_u[i] < total:
                selected = j
                break
        latent.append(selected)
        for group, target in ((gain_rows, gain), (loss_rows, loss)):
            weights = [-math.log(float(uniforms[row["episode_id"]][i])) for row in group]
            target.append(math.fsum(w*abs(row["r_net"]) for w, row in zip(weights, group))/math.fsum(weights))
    grid = [(mu*kappa, (1-mu)*kappa) for mu in (.2, .4, .6, .8) for kappa in (2, 8, 32, 128)]
    s = sum(row["y"] for row in episode["target"])
    f = episode["m"]-s
    theta = beta_distribution.ppf(theta_u, [grid[j][0]+s for j in latent], [grid[j][1]+f for j in latent])
    expected = [float(t*g-(1-t)*l) for t, g, l in zip(theta, gain, loss)]
    mean_U = reference["probability"]*math.fsum(r["r_net"] for r in gain_rows)/len(gain_rows)-(1-reference["probability"])*math.fsum(-r["r_net"] for r in loss_rows)/len(loss_rows)
    errors = {"mean_theta": abs(reference["probability"]-wire["posterior_mean_theta"]), "mean_U": abs(mean_U-wire["mean_U_net_fraction"]),
              "lambda_posterior": max(abs(a-b) for a, b in zip(mass, audit["lambda_posterior"])),
              "all_U_draws": max(abs(a-b) for a, b in zip(expected, audit["draws"]["U"])),
              "theta_draws": float(np.max(np.abs(theta-np.array(audit["draws"]["theta"]))))}
    if max(errors.values()) > 1e-12 or latent != audit["draws"]["lambda"]:
        raise ValueError("Utility khác oracle độc lập quá1e−12")
    if wire["gain_count"] != len(gain_rows) or wire["loss_count"] != len(loss_rows):
        raise ValueError("Sai counts unique magnitude")
    return {"status": "PASS", "supported": True, "teacher": reference, "draws_checked": 4096,
            "absolute_errors": errors, "max_error": max(errors.values()), "MC_standard_error_net_fraction": audit["MC_standard_error_net_fraction"],
            "MC_mean_minus_analytic_net_fraction": audit["MC_mean_minus_analytic_net_fraction"]}
