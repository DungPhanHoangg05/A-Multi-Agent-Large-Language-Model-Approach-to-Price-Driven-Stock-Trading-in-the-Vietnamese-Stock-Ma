"""Oracle hierarchical logistic log-space và baseline shared-w naive pooling."""

from __future__ import annotations

from typing import Any

import numpy as np

from core.mt_bicl_simulator import FiniteSimulator, validate_input


class FiniteBayesOracle:
    """Tích phân wk riêng từng prior task, normalize joint lambda,w* đúng một lần."""

    def __init__(self, simulator: FiniteSimulator) -> None:
        """Chỉ dùng bảng cố định của simulator; không fit bằng thị trường."""
        self.support = simulator.support
        self.log_conditional = simulator.log_conditional
        self.log_hyper = np.log(simulator.p_lambda)
        self.log_marginal_weight = np.logaddexp.reduce(self.log_hyper[:, None]+self.log_conditional, axis=0)

    def _likelihood(self, rows: list[dict[str, Any]]) -> np.ndarray:
        """Bernoulli log likelihood ổn định cho mọi w; m=0 có log L=0."""
        if not rows:
            return np.zeros(64, dtype=np.float64)
        x = np.asarray([row["x"] for row in rows], dtype=np.float64)
        y = np.asarray([row["y"] for row in rows], dtype=int)[:, None]
        logits = np.column_stack((np.ones(len(rows)), x))@self.support.T
        return np.where(y == 1, -np.logaddexp(0, -logits), -np.logaddexp(0, logits)).sum(axis=0)

    def predict(self, data: dict[str, Any], *, pooled: bool = False,
                posterior: bool = False) -> dict[str, Any]:
        """Trả p/log p Python gốc; C cập nhật cả lambda, không clip để che KL lớn."""
        validate_input(data)
        prior_likelihood = [self._likelihood(task["observations"]) for task in data["prior"]]
        target_likelihood = self._likelihood(data["target"]["observations"])
        logits = np.asarray([1., *data["query"]["x"]])@self.support.T
        log_one, log_zero = -np.logaddexp(0, -logits), -np.logaddexp(0, logits)
        if pooled:
            joint = self.log_marginal_weight+target_likelihood+sum(prior_likelihood, np.zeros(64))
        else:
            evidence = sum((np.logaddexp.reduce(self.log_conditional+values[None], axis=1)
                            for values in prior_likelihood), np.zeros(16))
            joint = self.log_hyper[:, None]+evidence[:, None]+self.log_conditional+target_likelihood[None]
        joint = joint-np.logaddexp.reduce(joint.ravel())
        p1 = float(np.logaddexp.reduce((joint+log_one).ravel()))
        p0 = float(np.logaddexp.reduce((joint+log_zero).ravel()))
        if not np.isfinite([p1, p0]).all():
            raise ValueError("Oracle có log probability không hữu hạn")
        result = {"probability": float(np.exp(p1)), "log_probability_one": p1,
                  "log_probability_zero": p0, "K": len(data["prior"]),
                  "m": len(data["target"]["observations"]), "pooled": pooled,
                  "normalization_error": float(abs(np.exp(joint).sum()-1))}
        if posterior:
            result["target_weight_posterior"] = (np.exp(joint) if pooled else np.exp(joint).sum(axis=0)).tolist()
            result["lambda_posterior"] = None if pooled else np.exp(joint).sum(axis=1).tolist()
        return result
