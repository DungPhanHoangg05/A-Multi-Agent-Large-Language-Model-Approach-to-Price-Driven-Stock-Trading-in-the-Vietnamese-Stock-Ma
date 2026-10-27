"""Metric cơ chế, baseline train-only và calibration; không chọn lại candidate."""

from __future__ import annotations

from copy import deepcopy
from collections import Counter
import math
from typing import Any
import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
import torch

from core.mt_bicl_bank import SYMBOLS, content_hash
from core.mt_bicl_model import MTBiCLLearner, collate_packets
from core.mt_bicl_scaler import fit_scaler
from core.mt_bicl_tasks import validate_episode
from core.mt_bicl_training import selection_metrics


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


def mechanism_metrics(logits: list[float], episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """KL Bernoulli oracle||model ổn định; giữ sai số làm tròn nhỏ, không clipping."""
    if not episodes or len(logits) != len(episodes):
        raise ValueError("Sai mẫu số synthetic")
    p, one, zero = probabilities(logits)
    q1 = np.asarray([e["oracle"]["log_probability_one"] for e in episodes], dtype=np.float64)
    q0 = np.asarray([e["oracle"]["log_probability_zero"] for e in episodes], dtype=np.float64)
    q = np.exp(q1)
    if (not np.isfinite([q1, q0]).all() or not np.allclose(q+np.exp(q0), 1, atol=1e-12, rtol=0)
            or not np.allclose(q, [e["oracle"]["probability"] for e in episodes], atol=1e-12, rtol=0)):
        raise ValueError("Oracle log probability không chuẩn hóa")
    kl = q*(q1-one)+np.exp(q0)*(q0-zero)
    error = np.abs(p-q)
    if not np.isfinite(kl).all() or (kl < -1e-12).any():
        raise ValueError("KL không hữu hạn hoặc âm quá sai số làm tròn")
    def summary(slots: np.ndarray) -> dict[str, Any]:
        """Báo support K/m cả cold-start, không bỏ nhóm lỗi lớn."""
        return {"count": int(slots.sum()), "mean_kl_nats": float(kl[slots].mean()),
                "p95_absolute_error": float(np.quantile(error[slots], .95, method="linear"))}
    result = summary(np.ones(len(episodes), dtype=bool))
    for key in ("K", "m"):
        values = np.asarray([e["oracle"][key] for e in episodes])
        result["by_"+key] = {str(int(v)): summary(values == v) for v in np.unique(values)}
    result["gate"] = "PASS" if result["mean_kl_nats"] <= .02 and result["p95_absolute_error"] <= .1 else "FAIL"
    return result


def prior_swap_metrics(a: list[float], b: list[float], pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Đánh giá đúng toàn bộ tập cặp, mẫu số eligible cố định theo oracle."""
    if len(a) != len(b) or len(a) != len(pairs) or not pairs:
        raise ValueError("Sai mẫu số prior swap")
    delta = probabilities(b)[0]-probabilities(a)[0]
    oracle = np.asarray([r["oracle_b"]["probability"]-r["oracle_a"]["probability"] for r in pairs])
    eligible = np.abs(oracle) >= .05
    if eligible.tolist() != [r["eligible"] for r in pairs]:
        raise ValueError("Không được thay denominator eligible của corpus khóa")
    count = int(eligible.sum())
    agree = int((np.sign(delta[eligible]) == np.sign(oracle[eligible])).sum())
    fraction = agree/count if count else None
    return {"attempt_pairs": len(pairs), "eligible_pairs": count, "agree_pairs": agree,
            "sign_agreement": fraction, "zero_model_delta_eligible": int((delta[eligible] == 0).sum()),
            "gate": "INCONCLUSIVE_BLOCK_DEVELOPMENT" if count < 200 else "PASS" if fraction >= .9 else "FAIL"}


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


def fit_baselines(bank: dict[str, Any]) -> dict[str, Any]:
    """Fit một lần bằng cycle train và scaler cuối 2020, không nhận tập validation."""
    scaler = fit_scaler(bank, "2021-01-01")
    if scaler != bank["frozen_scaler"]:
        raise ValueError("Scaler baseline khác scaler cuối train đã nghiệm thu")
    rows = [r for r in bank["records"] if r["split"] == "train" and r["status"] == "AVAILABLE"]
    rows.sort(key=lambda r: (r["exit_date"], SYMBOLS.index(r["symbol"]), r["episode_id"]))
    if ([r["episode_id"] for r in rows] != scaler["fit_episode_ids"] or not rows
            or any(not r["as_of_date"] < r["entry_date"] < r["exit_date"] <= "2020-12-31" for r in rows)):
        raise ValueError("Tập baseline train khác membership scaler hoặc vắt split")
    x = np.clip((np.asarray([r["features"]["vector"] for r in rows])-scaler["mean"])/scaler["scale"], -4, 4)
    y = np.asarray([r["outcome"]["y"] for r in rows])
    if not np.isfinite(x).all() or not np.isin(y, [0, 1]).all():
        raise ValueError("Baseline train không hữu hạn hoặc nhãn không nhị phân")
    rate = float((1+int(y.sum()))/(2+len(y)))
    result = {"fit_ids": scaler["fit_episode_ids"], "fit_count": len(rows),
              "scaler_sha256": content_hash(scaler), "base_rate": rate}
    if len(np.unique(y)) == 1:
        result["logistic"] = {"status": "SINGLE_CLASS_TRAIN", "constant": rate}
    else:
        model = LogisticRegression(C=1., penalty="l2", solver="lbfgs", max_iter=1000, tol=1e-8,
                                   random_state=42, class_weight=None)
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            try:
                model.fit(x, y)
            except ConvergenceWarning as error:
                raise ValueError("Logistic không hội tụ; giữ lỗi, không thay tham số hoặc fallback") from error
        result["logistic"] = {"status": "FITTED_TRAIN_ONLY", "coef": model.coef_[0].tolist(),
                              "intercept": float(model.intercept_[0]), "iterations": int(model.n_iter_[0])}
    return result


def baseline_logits(fit: dict[str, Any], vectors: list[list[float]]) -> dict[str, list[float]]:
    """Predict không nhận nhãn validation; giữ coef/rate đóng băng."""
    x = np.asarray(vectors, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != 4 or not np.isfinite(x).all() or (np.abs(x) > 4).any():
        raise ValueError("Vector baseline không thuộc miền train-scaled/clip")
    def logit(p: float) -> float:
        return math.log(p)-math.log1p(-p)
    model = fit["logistic"]
    logistic = ([logit(model["constant"])]*len(x) if model["status"] == "SINGLE_CLASS_TRAIN"
                else (x@np.asarray(model["coef"])+model["intercept"]).tolist())
    return {"base_rate": [logit(fit["base_rate"])]*len(x), "logistic": logistic}


def predict_packets(model: MTBiCLLearner, packets: list[dict[str, Any]], physical: int,
                    device: torch.device) -> list[float]:
    """Inference thuần; không optimizer hoặc loss, kiểm weights/grads trước và sau."""
    before = model_fingerprint(model)
    model.eval()
    result = []
    with torch.inference_mode():
        for start in range(0, len(packets), physical):
            batch = collate_packets(packets[start:start+physical], device)
            logits = model(batch["values"], batch["roles"], batch["padding"])
            result.extend(logits[torch.arange(len(batch["queries"]), device=device), batch["queries"]].cpu().tolist())
    probabilities(result)
    if model_fingerprint(model) != before or any(p.grad is not None for p in model.parameters()):
        raise ValueError("Weights hoặc gradient thay đổi trong evaluation")
    return result


def model_fingerprint(model: MTBiCLLearner) -> str:
    """Băm nội dung tensor, không phụ thuộc metadata archive của torch.save."""
    import hashlib
    digest = hashlib.sha256()
    for name, tensor in model.state_dict().items():
        digest.update(name.encode())
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def market_report(logits: list[float], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Calibration/r_net đầy đủ, giữ bin rỗng, không suy ER hoặc thắng hệ thống từ p."""
    if not rows or len(logits) != len(rows):
        raise ValueError("Sai mẫu số validation")
    p = probabilities(logits)[0]
    records = [{"episode_id": r["query"]["episode_id"], "symbol": r["query"]["symbol"],
                "as_of_date": r["query"]["as_of_date"], "y": r["supervised_target"]["y"],
                "r_net": r["supervised_target"]["r_net"], "p": float(v), "logit": float(z),
                "K": r["K"], "m": r["m"]} for r, v, z in zip(rows, p, logits)]
    y, net = np.asarray([r["y"] for r in records]), np.asarray([r["r_net"] for r in records])
    if not np.isfinite(net).all() or not np.array_equal(y, (net > 0).astype(int)):
        raise ValueError("Validation nhãn không khớp r_net")
    bins = np.minimum(np.searchsorted(np.asarray([i/10 for i in range(11)]), p, side="right")-1, 9)
    def describe(mask: np.ndarray) -> dict[str, Any]:
        n = int(mask.sum())
        positive, nonpositive = mask & (net > 0), mask & (net <= 0)
        return {"count": n, "mean_p": float(p[mask].mean()) if n else None,
                "observed_rate": float(y[mask].mean()) if n else None,
                "mean_r_net": float(net[mask].mean()) if n else None,
                "mean_positive_gain": float(net[positive].mean()) if positive.any() else None,
                "mean_nonpositive_loss": float(net[nonpositive].mean()) if nonpositive.any() else None}
    strata = {}
    clipped = np.clip(p, 1e-6, 1-1e-6)
    losses = -(y*np.log(clipped)+(1-y)*np.log1p(-clipped))
    for key in ("K", "m"):
        values = np.asarray([r[key] for r in records])
        strata[key] = {str(int(v)): {**describe(values == v), "log_loss": float(losses[values == v].mean()),
                                    "brier": float(((p[values == v]-y[values == v])**2).mean())}
                       for v in np.unique(values)}
    calibration = [{"left": i/10, "right": (i+1)/10, "right_inclusive": i == 9,
                    **describe(bins == i)} for i in range(10)]
    return {"metrics": selection_metrics(records), "calibration": calibration,
            "calibration_by_symbol": {s: [{"left": i/10, "right": (i+1)/10, "right_inclusive": i == 9,
                **describe((bins == i) & (np.asarray([r["symbol"] for r in records]) == s))} for i in range(10)] for s in SYMBOLS},
            "K_m_strata": strata,
            "K_m_joint_support": dict(sorted(Counter(f"K={r['K']},m={r['m']}" for r in records).items())),
            "return_diagnostics": describe(np.ones(len(rows), dtype=bool)),
            "positive_cycles_smallest_gain_first": [r for r in sorted(records, key=lambda r: (r["r_net"], r["episode_id"])) if r["y"] == 1],
            "nonpositive_cycles_largest_loss_first": [r for r in sorted(records, key=lambda r: (r["r_net"], r["episode_id"])) if r["y"] == 0],
            "records": records}
