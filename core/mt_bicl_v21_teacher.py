"""Fitter v2.1: chỉ tăng trần EM lên1.000, giữ nguyên recipe và tolerance v2."""

from __future__ import annotations

from typing import Any
import numpy as np

from core.mt_bicl_v2_teacher import TOLERANCE, log_likelihood

MAX_ITERATIONS = 1000


def fit_hyperprior(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """MAP-EM tối đa1.000 vòng đã đăng ký; không tự kéo dài hoặc dùng fallback."""
    if (not tasks or len({task["task_id"] for task in tasks}) != len(tasks)
            or any(task["count"] < 1 or task["successes"]+task["failures"] != task["count"]
                   for task in tasks)):
        raise ValueError("Fit cần các block duy nhất có count hợp lệ")
    likelihood = log_likelihood([[task["successes"], task["failures"]] for task in tasks])
    pi = np.full(16, 1/16, dtype=np.float64)

    def objective(value: np.ndarray) -> float:
        """Log posterior MAP bỏ hằng số Dirichlet; α=2 cho hệ số log π bằng1."""
        return float(np.logaddexp.reduce(likelihood+np.log(value), axis=1).sum()+np.log(value).sum())

    trace = [{"iteration": 0, "objective": objective(pi), "max_pi_delta": None}]
    converged = False
    for iteration in range(1, MAX_ITERATIONS+1):
        joint = likelihood+np.log(pi)
        responsibilities = np.exp(joint-np.logaddexp.reduce(joint, axis=1)[:, None])
        next_pi = (responsibilities.sum(axis=0)+1)/(len(tasks)+16)
        delta = float(np.max(np.abs(next_pi-pi)))
        score = objective(next_pi)
        if (not np.isfinite(next_pi).all() or abs(float(next_pi.sum())-1) > 1e-12
                or score < trace[-1]["objective"]-1e-10):
            raise ValueError("EM có xác suất không hợp lệ hoặc objective giảm")
        trace.append({"iteration": iteration, "objective": score, "max_pi_delta": delta})
        pi = next_pi
        if delta < TOLERANCE:
            converged = True
            break
    return {"pi": pi.tolist(), "iterations": iteration, "converged": converged,
            "max_pi_delta": delta, "fit_objective_trace": trace,
            "status": "CONVERGED" if converged else "STOP_TEACHER_NONCONVERGENCE_NO_UNIFORM_FALLBACK"}
