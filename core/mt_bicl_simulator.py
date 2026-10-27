"""Simulator logistic hữu hạn theo bảng đã khóa; latent/nhãn query ở ngoài input."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from core.mt_bicl_bank import canonical_bytes, read_protocol

SIMULATOR_VERSION = "mt_bicl_finite_logistic_v1"


def validate_input(data: dict[str, Any]) -> None:
    """Kiểm ranh giới task/ID và che nhãn query, không dedupe theo giá trị x/y."""
    if type(data) is not dict or set(data) != {"prior", "target", "query"}:
        raise ValueError("Oracle/learner chỉ nhận input prior/target/query, không latent hoặc nhãn ngoài")
    if type(data["prior"]) is not list or not 0 <= len(data["prior"]) <= 3:
        raise ValueError("K ngoài miền 0..3")
    query = data["query"]
    if type(query) is not dict or set(query) != {"observation_id", "x"}:
        raise ValueError("Query không được có y, outcome hoặc latent")
    ids: set[str] = set()
    tasks: set[str] = set()

    def vector(value: Any) -> None:
        """Chỉ nhận bốn số Python gốc hữu hạn trong miền clip của simulator."""
        if (type(value) is not list or len(value) != 4 or any(type(v) not in (int, float) for v in value)
                or not np.isfinite(value).all() or (np.abs(value) > 4).any()):
            raise ValueError("x phải có bốn số hữu hạn trong [-4,4]")

    def identifier(value: Any, seen: set[str]) -> None:
        """Không cho cùng ID xuất hiện hai lần dù observation có thể cùng x/y."""
        if type(value) is not str or not value or value in seen:
            raise ValueError("ID thiếu hoặc trùng trong episode")
        seen.add(value)

    identifier(query["observation_id"], ids)
    vector(query["x"])
    for index, task in enumerate([*data["prior"], data["target"]]):
        if type(task) is not dict or set(task) != {"task_id", "observations"}:
            raise ValueError("Task phải giữ đúng ranh giới và observations")
        identifier(task["task_id"], tasks)
        rows = task["observations"]
        target = index == len(data["prior"])
        if type(rows) is not list or not (0 if target else 2) <= len(rows) <= 8:
            raise ValueError("Số observation không thuộc miền prior 2..8/target 0..8")
        for row in rows:
            if type(row) is not dict or set(row) != {"observation_id", "x", "y"}:
                raise ValueError("Observation không đúng schema x/y/ID")
            identifier(row["observation_id"], ids)
            vector(row["x"])
            if type(row["y"]) is not int or row["y"] not in (0, 1):
                raise ValueError("Nhãn phải là int 0/1 gốc")
    canonical_bytes(data)


def pack_input(data: dict[str, Any], *, query_y: int | None = None) -> dict[str, Any]:
    """Packing hai miền dùng cùng hợp đồng 69 token; y query chỉ là loss label ngoài."""
    validate_input(data)
    if query_y is not None and (type(query_y) is not int or query_y not in (0, 1)):
        raise ValueError("Nhãn query ngoài input phải là 0/1")
    values, roles, positions, labels = [], [], [], []
    for role, task in [*((0, task) for task in data["prior"]), (1, data["target"])]:
        values.append([0., 0., 0., 0., -1., 1.])
        roles.append(role)
        for row in task["observations"]:
            if role == 1:
                positions.append(len(values))
                labels.append(row["y"])
            values.extend([[*row["x"], 0., 1.], [0., 0., 0., 0., float(row["y"]), 0.]])
            roles.extend([role, role])
    positions.append(len(values))
    labels.append(query_y)
    values.append([*data["query"]["x"], 0., 1.])
    roles.append(2)
    if len(values) > 69:
        raise ValueError("Input vượt 69 token")
    return {"values": values, "roles": roles, "prediction_positions": positions,
            "external_loss_labels": labels, "query_position": len(values)-1,
            "causal_mask": "LOWER_TRIANGULAR_INCLUDING_SELF", "padding": "RIGHT_KEY_MASK_REQUIRED"}


class FiniteSimulator:
    """Một bảng coefficients cố định, RNG riêng theo stream/model seed/episode ID."""

    def __init__(self, config: dict[str, Any], streams: dict[str, Any]) -> None:
        """Factory nguồn khóa phải kiểm byte config; không fit bảng bằng dữ liệu thị trường."""
        self.config = deepcopy(config)
        self.streams = {key: value for key, value in streams.items() if type(value) is int}
        self.support = np.asarray(config["w_support"], dtype=np.float64)
        self.centers = np.asarray(config["lambda_centers"], dtype=np.float64)
        self.p_lambda = np.asarray(config["p_lambda"], dtype=np.float64)
        if (config["version"] != SIMULATOR_VERSION or self.support.shape != (64, 5) or self.centers.shape != (16, 5)
                or self.p_lambda.shape != (16,) or not all(np.isfinite(v).all() for v in (self.support, self.centers, self.p_lambda))
                or (self.p_lambda <= 0).any() or not np.isclose(self.p_lambda.sum(), 1, rtol=0, atol=1e-15)):
            raise ValueError("Bảng latent simulator không hợp lệ")
        logits = -np.sum((self.support[None]-self.centers[:, None])**2, axis=2)/(2*config["p_w_given_lambda"]["tau"]**2)
        self.log_conditional = logits-np.logaddexp.reduce(logits, axis=1)[:, None]
        self.conditional = np.exp(self.log_conditional)
        for array in (self.support, self.centers, self.p_lambda, self.log_conditional, self.conditional):
            array.setflags(write=False)

    @classmethod
    def from_locked(cls, root: Path) -> FiniteSimulator:
        """Nạp đúng simulator và seed đã đăng ký, không cho tự cập nhật checksum."""
        protocol = read_protocol(root)
        data = (root/"docs/plan/week10/simulator_v1.json").read_bytes()
        if hashlib.sha256(data).hexdigest() != protocol["artifacts"]["simulator_v1.json"]:
            raise ValueError("Simulator khác bảng đã khóa")
        return cls(json.loads(data), protocol["rng_streams"])

    def _rng(self, stream: str, model_seed: int, episode_id: int) -> np.random.Generator:
        """Không dùng global RNG hoặc chia sẻ stream test với train."""
        if (stream not in self.streams or type(model_seed) is not int or type(episode_id) is not int
                or model_seed < 0 or episode_id < 0):
            raise ValueError("Stream/model seed/episode ID không hợp lệ")
        return np.random.Generator(np.random.PCG64(np.random.SeedSequence([self.streams[stream], model_seed, episode_id])))

    def _task(self, rng: np.random.Generator, task_id: str, count: int, weight: int) -> dict[str, Any]:
        """Sinh cả matrix x trước vector uniform y, đúng thứ tự RNG đã khóa."""
        x = np.clip(rng.normal(0, 1, size=(count, 4)), -4, 4)
        logits = np.column_stack((np.ones(count), x))@self.support[weight]
        probability = np.exp(-np.logaddexp(0, -logits))
        labels = (rng.random(count) < probability).astype(int)
        return {"task_id": task_id, "observations": [
            {"observation_id": f"{task_id}:{index}", "x": vector, "y": label}
            for index, (vector, label) in enumerate(zip(x.tolist(), labels.tolist()))]}

    def episode(self, stream: str, episode_id: int, *, model_seed: int = 0) -> dict[str, Any]:
        """Sinh một episode có K=0..3,m=0..8; metadata latent không nằm trong input."""
        if stream not in ("synthetic_train", "synthetic_diagnostic", "synthetic_test", "runtime_preflight"):
            raise ValueError("Stream này không dành cho episode synthetic")
        if ((stream == "synthetic_train" and model_seed not in (17, 42, 73))
                or (stream != "synthetic_train" and model_seed != 0)):
            raise ValueError("Train dùng seed 17/42/73; các stream khóa độc lập dùng model_seed=0")
        rng = self._rng(stream, model_seed, episode_id)
        k, m = int(rng.integers(0, 4)), int(rng.integers(0, 9))
        counts = [int(rng.integers(2, 9)) for _ in range(k)]
        hyper = int(rng.choice(16, p=self.p_lambda))
        weights = [int(rng.choice(64, p=self.conditional[hyper])) for _ in range(k+1)]
        identity = f"syn:{self.streams[stream]}:{model_seed}:{episode_id}"
        prior = [self._task(rng, f"{identity}:P{index}", count, weights[index]) for index, count in enumerate(counts)]
        target = self._task(rng, identity+":T", m+1, weights[-1])
        query = target["observations"].pop()
        data = {"prior": prior, "target": target,
                "query": {"observation_id": query["observation_id"], "x": query["x"]}}
        validate_input(data)
        return {"episode_id": identity, "stream": stream, "model_seed": model_seed, "episode_index": episode_id,
                "input": data, "supervised_query_y": query["y"],
                "latent_provenance": {"lambda_index": hyper, "w_indices": weights}}

    def prior_swap_pair(self, pair_id: int) -> dict[str, Any]:
        """Hai prior từ hyper-state riêng, cùng C/x và query label ở ngoài input."""
        rng = self._rng("prior_swap_pairs", 0, pair_id)
        k, m = int(rng.integers(1, 4)), int(rng.integers(0, 9))
        counts = [int(rng.integers(2, 9)) for _ in range(k)]
        hyper_a, hyper_b = (int(rng.choice(16, p=self.p_lambda)) for _ in range(2))
        identity = f"swap:{self.streams['prior_swap_pairs']}:{pair_id}"
        prior_a, prior_b, weights_a, weights_b = [], [], [], []
        for side, hyper, destination, weights in (("A", hyper_a, prior_a, weights_a), ("B", hyper_b, prior_b, weights_b)):
            for index, count in enumerate(counts):
                weight = int(rng.choice(64, p=self.conditional[hyper]))
                weights.append(weight)
                destination.append(self._task(rng, f"{identity}:{side}:P{index}", count, weight))
        target_weight = int(rng.choice(64, p=self.conditional[hyper_a]))
        target = self._task(rng, identity+":T", m+1, target_weight)
        query = target["observations"].pop()
        result = {"pair_id": identity, "pair_index": pair_id, "prior_a": prior_a, "prior_b": prior_b,
                  "target": target, "query": {"observation_id": query["observation_id"], "x": query["x"]},
                  "supervised_query_y": query["y"], "latent_provenance": {
                      "lambda_a": hyper_a, "lambda_b": hyper_b, "w_prior_a": weights_a, "w_prior_b": weights_b,
                      "w_target": target_weight}}
        for data in pair_inputs(result):
            validate_input(data)
        return result


def pair_inputs(pair: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Tách hai input mà không đưa latent hoặc nhãn query vào đường dự báo."""
    return tuple(deepcopy({"prior": pair[key], "target": pair["target"], "query": pair["query"]})
                 for key in ("prior_a", "prior_b"))
