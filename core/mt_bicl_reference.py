"""Oracle scalar độc lập bằng tích predictive tuần tự; không dùng log-beta teacher."""

from __future__ import annotations

import math
from typing import Any, Sequence

from core.mt_bicl_inputs import validate_input


class SequentialBetaOracle:
    """Tích phân riêng θ từng task; chỉ chia normalization sau khi nhân D và C."""

    def __init__(self, pi: Sequence[float]) -> None:
        """Sao chép π vào tuple; không import grid/likelihood từ teacher."""
        self.pi = tuple(float(value) for value in pi)
        if (len(self.pi) != 16 or any(not math.isfinite(v) or v <= 0 for v in self.pi)
                or abs(math.fsum(self.pi)-1) > 1e-12):
            raise ValueError("π oracle không hợp lệ")

    def predict(self, data: dict[str, Any], *, pooled: bool = False,
                posterior: bool = False) -> dict[str, Any]:
        """Duyệt16 trạng thái, nhân xác suất từng nhãn với count prefix thực."""
        validate_input(data)
        prior = [task["observations"] for task in data["prior"]]
        target = data["target"]["observations"]
        groups = [[row for task in prior for row in task]+target] if pooled else [*prior, target]
        masses, predictions = [], []
        index = 0
        for mu in (.2, .4, .6, .8):
            for kappa in (2, 8, 32, 128):
                mass = self.pi[index]
                predictive = mu
                for observations in groups:
                    a, b = mu*kappa, (1-mu)*kappa
                    for row in observations:
                        y = row["y"]
                        mass *= (a if y else b)/(a+b)
                        a += y
                        b += 1-y
                    predictive = a/(a+b)
                masses.append(mass)
                predictions.append(predictive)
                index += 1
        denominator = math.fsum(masses)
        if not math.isfinite(denominator) or denominator <= 0:
            raise ValueError("Oracle scalar mất normalization")
        one = math.fsum(w*p for w, p in zip(masses, predictions))/denominator
        zero = math.fsum(w*(1-p) for w, p in zip(masses, predictions))/denominator
        result = {"probability": float(one), "log_probability_one": math.log(one),
                  "log_probability_zero": math.log(zero), "K": len(prior), "m": len(target)}
        if posterior:
            result["lambda_posterior"] = [w/denominator for w in masses]
        return result
