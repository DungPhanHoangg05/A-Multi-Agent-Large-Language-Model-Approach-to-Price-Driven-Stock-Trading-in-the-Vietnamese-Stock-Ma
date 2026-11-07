"""Teacher Beta–Bernoulli phân cấp, MAP-EM train-only và audit prior-predictive."""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from core.backtest_engine import compute_round_trip_net_return
from core.mt_bicl_inputs import validate_input
from core.mt_bicl_inputs import training_membership

MAX_ITERATIONS = 1000
TOLERANCE = 1e-10
GRID = tuple((mu, kappa) for mu in (.2, .4, .6, .8) for kappa in (2, 8, 32, 128))
ALPHA = np.asarray([mu*k for mu, k in GRID], dtype=np.float64)
BETA = np.asarray([(1-mu)*k for mu, k in GRID], dtype=np.float64)
for _array in (ALPHA, BETA):
    _array.setflags(write=False)


def grid_records() -> list[dict[str, float | int]]:
    """Giữ thứ tự μ-major/κ-minor đã đăng ký, không fit hoặc đổi grid."""
    return [{"mu": mu, "kappa": k, "alpha": float(a), "beta": float(b)}
            for (mu, k), a, b in zip(GRID, ALPHA, BETA)]


def log_likelihood(counts: Sequence[Sequence[int]]) -> np.ndarray:
    """Tính log B(a+s,b+f)/B(a,b), không hệ số tổ hợp hoặc latent thật."""
    if any(len(pair) != 2 or any(type(n) is not int or n < 0 for n in pair) for pair in counts):
        raise ValueError("Count thắng/thua phải là hai int không âm")
    result = np.empty((len(counts), 16), dtype=np.float64)
    base = [math.lgamma(a)+math.lgamma(b)-math.lgamma(a+b) for a, b in zip(ALPHA, BETA)]
    for i, (s, f) in enumerate(counts):
        result[i] = [math.lgamma(a+s)+math.lgamma(b+f)-math.lgamma(a+b+s+f)-v
                     for a, b, v in zip(ALPHA, BETA, base)]
    if not np.isfinite(result).all():
        raise ValueError("Likelihood teacher không hữu hạn")
    return result


def train_task_counts(bank: dict[str, Any], membership: dict[str, Any]) -> list[dict[str, Any]]:
    """Lọc train trước đọc outcome; kiểm nhãn kinh tế và mỗi block chỉ xuất hiện một lần."""
    actual = training_membership(bank)
    if any(actual[key] != membership[key] for key in actual):
        raise ValueError("Membership train khác bản đăng ký")
    rows = {row["episode_id"]: row for row in bank["records"]
            if row["status"] == "AVAILABLE" and row["split"] == "train"}
    result = []
    for task_id, ids in membership["task_cycle_ids"].items():
        wins = 0
        for episode_id in ids:
            row = rows[episode_id]
            if row["task_id"] != task_id or row["label_status"] != "AVAILABLE":
                raise ValueError("Nhãn/task train không hợp lệ")
            outcome = row["outcome"]
            net = float(compute_round_trip_net_return(outcome["entry_open"], outcome["exit_close"]))
            if (type(outcome["y"]) is not int or outcome["y"] != int(net > 0)
                    or not math.isfinite(outcome["r_net"]) or abs(net-outcome["r_net"]) > 1e-12):
                raise ValueError("Nhãn train không khớp helper kinh tế T+2.5")
            wins += outcome["y"]
        result.append({"task_id": task_id, "episode_ids": list(ids),
                       "successes": wins, "failures": len(ids)-wins, "count": len(ids)})
    return result


def fit_hyperprior(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """MAP-EM đúng 1.000 vòng tối đa; trả cả failure, không tự kéo dài hoặc dùng fallback."""
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


class BetaBernoulliTeacher:
    """Weights π cố định; inference chỉ conditioning theo count D/C, không refit."""

    def __init__(self, pi: Sequence[float]) -> None:
        """Kiểm mass hữu hạn, dương và đã chuẩn hóa; không tự sửa input."""
        self.pi = np.array(pi, dtype=np.float64, copy=True)
        if (self.pi.shape != (16,) or not np.isfinite(self.pi).all()
                or (self.pi <= 0).any() or abs(float(self.pi.sum())-1) > 1e-12):
            raise ValueError("π cần đúng16 mass dương, hữu hạn, tổng bằng1")
        self.pi.setflags(write=False)

    def predict_counts(self, prior: list[list[int]], target: list[int], *, pooled: bool = False,
                       posterior: bool = False) -> dict[str, Any]:
        """Normalize một lần trên λ; C cập nhật cả λ lẫn predictive của θ target."""
        likelihood = log_likelihood([*prior, target])
        s, f = target
        if pooled:
            s += sum(pair[0] for pair in prior)
            f += sum(pair[1] for pair in prior)
            joint = np.log(self.pi)+log_likelihood([[s, f]])[0]
        else:
            joint = np.log(self.pi)+likelihood.sum(axis=0)
        joint -= np.logaddexp.reduce(joint)
        probabilities = (ALPHA+s)/(ALPHA+BETA+s+f)
        log_one = float(np.logaddexp.reduce(joint+np.log(probabilities)))
        log_zero = float(np.logaddexp.reduce(joint+np.log1p(-probabilities)))
        result = {"probability": float(math.exp(log_one)), "log_probability_one": log_one,
                  "log_probability_zero": log_zero, "K": len(prior), "m": sum(target)}
        if posterior:
            result["lambda_posterior"] = np.exp(joint).tolist()
        return result

    def predict(self, data: dict[str, Any], *, pooled: bool = False,
                posterior: bool = False) -> dict[str, Any]:
        """Không nhận query y/latent; feature chỉ kiểm hợp đồng, không vào likelihood."""
        validate_input(data)
        counts = []
        for task in [*data["prior"], data["target"]]:
            rows = task["observations"]
            successes = sum(row["y"] for row in rows)
            counts.append([successes, len(rows)-successes])
        return self.predict_counts(counts[:-1], counts[-1], pooled=pooled, posterior=posterior)


def prior_predictive_audit(tasks: list[dict[str, Any]], pi: Sequence[float], seed: int) -> dict[str, Any]:
    """1.000 replicate theo size task thật; báo bất lợi, không chọn lại grid/π."""
    teacher = BetaBernoulliTeacher(pi)
    sizes = np.asarray([task["count"] for task in tasks], dtype=np.int64)
    offsets = np.r_[0, np.cumsum(sizes)[:-1]]

    def summaries(wins: np.ndarray) -> dict[str, float | list[float]]:
        """Mean theo cycle, variance theo task ddof0; quantile tuyến tính."""
        rates = wins/sizes
        return {"mean_rate": float(wins.sum()/sizes.sum()),
                "variance_task_rate": float(rates.var()),
                "all_win_fraction": float((wins == sizes).mean()),
                "all_loss_fraction": float((wins == 0).mean()),
                "task_rate_quantiles_05_50_95": np.quantile(rates, [.05, .5, .95], method="linear").tolist()}

    records = []
    for replicate in range(1000):
        def rng(domain: int) -> np.random.Generator:
            """Các miền λ/θ/nhãn độc lập, không dùng global RNG."""
            return np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, 0, replicate, domain])))
        latent = rng(1).choice(16, size=len(tasks), p=teacher.pi)
        theta = rng(2).beta(ALPHA[latent], BETA[latent])
        labels = rng(4).random(int(sizes.sum())) < np.repeat(theta, sizes)
        records.append(summaries(np.add.reduceat(labels.astype(np.int64), offsets)))
    intervals = {key: np.quantile(np.asarray([record[key] for record in records]), [.025, .975],
                                  axis=0, method="linear").tolist() for key in records[0]}
    return {"replicates": 1000, "seed": seed, "task_sizes": sizes.tolist(),
            "observed": summaries(np.asarray([task["successes"] for task in tasks])),
            "predictive_95_percent_intervals": intervals, "replicate_summaries": records,
            "market_fit_quality_is_release_gate": False}
