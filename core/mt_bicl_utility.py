"""Posterior utility teacher + Bayesian bootstrap magnitude, không fit hoặc đổi phí."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.stats import beta as beta_distribution

from core.mt_bicl_bank import content_hash
from core.mt_bicl_teacher import ALPHA, BETA, BetaBernoulliTeacher
from core.mt_bicl_contracts import UTILITY_BRANCHES, validate_context, validate_wire
from core.mt_bicl_protocol import PROTOCOL_SHA256, component_seed

DRAWS = 4096
SOURCE = "TEACHER_SIGN_BAYESIAN_BOOTSTRAP_MAGNITUDE"


def common_uniforms(point_id: str, component: str) -> np.ndarray:
    """Stream mở (0,1), seed không chứa branch/repeat để giữ CRN trên subset."""
    seed = int(component_seed(PROTOCOL_SHA256, point_id, component))
    return np.random.Generator(np.random.PCG64(seed)).integers(1, 2**53, size=DRAWS, dtype=np.uint64).astype(np.float64)/(2**53)


def observations(episode: dict[str, Any]) -> list[dict[str, Any]]:
    """Mỗi observation duy nhất xuất hiện một lần; không gộp/khử trùng lỗi im lặng."""
    validate_context(episode)
    rows = [row for task in episode["prior"] for row in task["observations"]]+episode["target"]
    return sorted(rows, key=lambda row: row["episode_id"])


def support_reason(episode: dict[str, Any]) -> str:
    """Giữ nguyên mọi cold-start; không cân bằng dấu hoặc mở rộng bucket."""
    rows = observations(episode)
    facts = episode["advisor"]["query_facts"]
    if episode["status"] != "AVAILABLE" or facts["prefix_rows"] != 45 or facts["frame_end_date"] != facts["as_of_date"]:
        return "QUERY_FEATURE_UNAVAILABLE"
    if facts["bucket"] == "UNKNOWN":
        return "UNKNOWN_BUCKET"
    if episode["K"] < 2:
        return "PRIOR_TASKS_BELOW_TWO"
    gains = sum(row["r_net"] > 0 for row in rows)
    if gains < 5 or len(rows)-gains < 5:
        return "MAGNITUDE_SUPPORT_BELOW_FIVE_PER_SIGN"
    return "SUPPORTED"


def posterior_utility(episode: dict[str, Any], teacher: BetaBernoulliTeacher,
                      probability_student: float | None, *, branch_id: str = "MT_BICL") -> dict[str, Any]:
    """U dùng net fraction đã trừ phí; mean giải tích và Monte Carlo được lưu riêng."""
    rows = observations(episode)
    if branch_id not in UTILITY_BRANCHES:
        raise ValueError("Nhánh không có utility trong protocol MT-BICL")
    if probability_student is not None and (type(probability_student) not in (int, float)
            or not math.isfinite(probability_student) or not 0 <= probability_student <= 1):
        raise ValueError("p student phải hữu hạn trong [0,1], không fallback teacher")
    point_id = episode["query"]["episode_id"]
    reason = support_reason(episode)
    gains = [row for row in rows if row["r_net"] > 0]
    losses = [row for row in rows if row["r_net"] <= 0]
    wire = {"version": "utility_icl_posterior_v3", "point_id": point_id, "branch_id": branch_id,
            "status": "SUPPORTED" if reason == "SUPPORTED" else "UTILITY_UNSUPPORTED", "reason": reason,
            "source": SOURCE, "probability_student": probability_student, "posterior_mean_theta": None,
            "mean_U_net_fraction": None, "MC_mean_U_net_fraction": None,
            "q10_U_net_fraction": None, "q90_U_net_fraction": None,
            "gain_count": len(gains), "loss_count": len(losses), "K": episode["K"], "m": episode["m"],
            "draws": 0, "seed_uint128_decimal": component_seed(PROTOCOL_SHA256, point_id, "theta"),
            "membership_sha256": episode["membership_sha256"], "draws_sha256": None}
    audit: dict[str, Any] = {"protocol_sha256": PROTOCOL_SHA256, "membership_sha256": episode["membership_sha256"],
                             "unique_observation_ids": [row["episode_id"] for row in rows], "draws": None}
    if reason != "SUPPORTED":
        validate_wire(wire, "utility")
        return {"wire": wire, "audit": audit}
    if probability_student is None:
        raise ValueError("Context có support nhưng chưa có p student của membership mới")

    def counts(selected: list[dict[str, Any]]) -> list[int]:
        """Count theo task riêng, tuyệt đối không pooled count prior vào θ target."""
        s = sum(row["y"] for row in selected)
        return [s, len(selected)-s]

    prior_counts = [counts(task["observations"]) for task in episode["prior"]]
    target_counts = counts(episode["target"])
    posterior = teacher.predict_counts(prior_counts, target_counts, posterior=True)
    weights = np.asarray(posterior["lambda_posterior"], dtype=np.float64)
    cumulative = np.cumsum(weights)
    cumulative[-1] = 1.
    latent = np.searchsorted(cumulative, common_uniforms(point_id, "lambda"), side="right")
    s, f = target_counts
    theta = beta_distribution.ppf(common_uniforms(point_id, "theta"), ALPHA[latent]+s, BETA[latent]+f)

    def magnitude(selected: list[dict[str, Any]]) -> np.ndarray:
        """Exponential trọng số theo từng ID; subset giữ uniform rồi chuẩn hóa lại."""
        exponential = np.stack([-np.log(common_uniforms(point_id, "magnitude|"+row["episode_id"])) for row in selected])
        magnitudes = np.asarray([abs(row["r_net"]) for row in selected], dtype=np.float64)
        return (exponential*magnitudes[:, None]).sum(axis=0)/exponential.sum(axis=0)

    gain, loss = magnitude(gains), magnitude(losses)
    utility = theta*gain-(1-theta)*loss
    theta_mean = float(np.dot(weights, (ALPHA+s)/(ALPHA+BETA+s+f)))
    if abs(theta_mean-posterior["probability"]) > 1e-12 or not np.isfinite([theta, gain, loss, utility]).all():
        raise ValueError("Posterior teacher/utility không hữu hạn hoặc sai mean θ")
    mean_gain = math.fsum(row["r_net"] for row in gains)/len(gains)
    mean_loss = math.fsum(-row["r_net"] for row in losses)/len(losses)
    mean_U = theta_mean*mean_gain-(1-theta_mean)*mean_loss
    draws = {"lambda": latent.tolist(), "theta": theta.tolist(), "gain": gain.tolist(), "loss": loss.tolist(), "U": utility.tolist()}
    quantiles = np.quantile(utility, [.1, .9], method="linear")
    wire.update(posterior_mean_theta=theta_mean, mean_U_net_fraction=float(mean_U),
                MC_mean_U_net_fraction=float(utility.mean()), q10_U_net_fraction=float(quantiles[0]),
                q90_U_net_fraction=float(quantiles[1]), draws=DRAWS, draws_sha256=content_hash(draws))
    audit.update(prior_counts=prior_counts, target_counts=target_counts, teacher_pi=teacher.pi.tolist(),
                 lambda_posterior=weights.tolist(), gain_mean_net_fraction=float(mean_gain), loss_mean_net_fraction=float(mean_loss),
                 MC_standard_error_net_fraction=float(utility.std(ddof=1)/math.sqrt(DRAWS)),
                 MC_mean_minus_analytic_net_fraction=float(utility.mean()-mean_U), draws=draws,
                 component_seeds={component: component_seed(PROTOCOL_SHA256, point_id, component)
                                  for component in ["lambda", "theta", *("magnitude|"+row["episode_id"] for row in rows)]})
    validate_wire(wire, "utility")
    content_hash(audit)
    return {"wire": wire, "audit": audit}
