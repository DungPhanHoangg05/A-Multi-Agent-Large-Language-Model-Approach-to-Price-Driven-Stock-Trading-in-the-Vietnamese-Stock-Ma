"""Enumeration scalar độc lập để đối chiếu oracle; không dùng kernel NumPy của oracle."""

from __future__ import annotations

import math
from typing import Any

from core.mt_bicl_simulator import validate_input


def _sum_exp(values: list[float]) -> float:
    """Log-sum-exp bằng math.fsum, độc lập với np.logaddexp.reduce."""
    maximum = max(values)
    return maximum+math.log(math.fsum(math.exp(value-maximum) for value in values))


def _log_sigmoid(value: float) -> float:
    """Không tạo sigmoid=1 rồi log(1-p), tránh mất precision ở cực trị."""
    return min(0., value)-math.log1p(math.exp(-abs(value)))


class EnumerationOracle:
    """Duyệt lambda/w* và marginal wk từng task bằng vòng lặp scalar riêng."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Nhận bảng nguồn đã kiểm, tự tính lại p(w|lambda), không nhận matrix oracle."""
        self.weights = [list(row) for row in config["w_support"]]
        self.log_hyper = [math.log(value) for value in config["p_lambda"]]
        tau = config["p_w_given_lambda"]["tau"]
        self.conditional = []
        for center in config["lambda_centers"]:
            scores = [-math.fsum((w-c)**2 for w, c in zip(weight, center))/(2*tau*tau) for weight in self.weights]
            total = _sum_exp(scores)
            self.conditional.append([score-total for score in scores])

    def _likelihood(self, rows: list[dict[str, Any]]) -> list[float]:
        """Mỗi w duyệt observations; không chia sẻ phép nhân matrix hoặc likelihood code."""
        result = []
        for weight in self.weights:
            values = []
            for row in rows:
                score = math.fsum(a*b for a, b in zip(weight, [1., *row["x"]]))
                values.append(_log_sigmoid(score if row["y"] == 1 else -score))
            result.append(math.fsum(values))
        return result

    def predict(self, data: dict[str, Any], *, pooled: bool = False,
                posterior: bool = False) -> dict[str, Any]:
        """Đối chiếu độc lập p và posterior, kể cả K=0/m=0 và dữ liệu cực trị."""
        validate_input(data)
        likelihoods = [self._likelihood(task["observations"]) for task in data["prior"]]
        target = self._likelihood(data["target"]["observations"])
        scores = [math.fsum(a*b for a, b in zip(weight, [1., *data["query"]["x"]])) for weight in self.weights]
        if pooled:
            joint = [_sum_exp([self.log_hyper[l]+self.conditional[l][w] for l in range(16)])
                     +target[w]+math.fsum(values[w] for values in likelihoods) for w in range(64)]
        else:
            joint = []
            for latent in range(16):
                evidence = math.fsum(_sum_exp([self.conditional[latent][w]+values[w] for w in range(64)])
                                     for values in likelihoods)
                for weight in range(64):
                    joint.append(self.log_hyper[latent]+evidence+self.conditional[latent][weight]+target[weight])
        total = _sum_exp(joint)
        log_one = _sum_exp([value+_log_sigmoid(scores[index % 64]) for index, value in enumerate(joint)])-total
        log_zero = _sum_exp([value+_log_sigmoid(-scores[index % 64]) for index, value in enumerate(joint)])-total
        result = {"probability": math.exp(log_one), "log_probability_one": log_one,
                  "log_probability_zero": log_zero}
        if posterior:
            normalized = [math.exp(value-total) for value in joint]
            result["lambda_posterior"] = None if pooled else [math.fsum(normalized[l*64:(l+1)*64]) for l in range(16)]
            result["target_weight_posterior"] = normalized if pooled else [math.fsum(normalized[l*64+w] for l in range(16)) for w in range(64)]
        return result
