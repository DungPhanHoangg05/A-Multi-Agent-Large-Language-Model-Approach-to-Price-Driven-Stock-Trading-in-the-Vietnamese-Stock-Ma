"""Cấp batch train/preflight tái lập, không đọc synthetic test hoặc chạy optimizer."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from core.bayesian_memory import read_json
from core.mt_bicl_bank import SYMBOLS, content_hash
from core.mt_bicl_context import pack_episode
from core.mt_bicl_simulator import FiniteSimulator, pack_input
from core.mt_bicl_tasks import validate_episode

CONTEXT_PATH = "outputs/bayesian_benchmark/mt_bicl_v1/inputs/task_context_v1.json"
CONTEXT_SHA256 = "4fca2146fbc03f4f74762a5a6b4d44c184b4b4244c3cb28d5dfda68d93fa0c57"


def load_context(root: Path) -> dict[str, Any]:
    """Chỉ nhận byte artifact đã nghiệm thu và mã dựng artifact vẫn nguyên vẹn."""
    path = root/CONTEXT_PATH
    if hashlib.sha256(path.read_bytes()).hexdigest() != CONTEXT_SHA256:
        raise ValueError("Task/context khác artifact đã nghiệm thu")
    envelope = read_json(path)
    payload = envelope["payload"]
    if envelope["sha256"] != content_hash(payload):
        raise ValueError("Payload task/context sai checksum")
    for name, expected in payload["identity"]["code_sha256"].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest() != expected:
            raise ValueError("Mã nguồn task/context đã thay đổi: "+name)
    return payload


class TrainingBatchSource:
    """Sampler chỉ train, uniform mã rồi query; mỗi step là một địa chỉ RNG độc lập."""

    def __init__(self, simulator: FiniteSimulator, context: dict[str, Any]) -> None:
        """Caller nạp context qua load_context; giữ bản sao để không sửa evidence gốc."""
        self.simulator = simulator
        self.context = deepcopy(context)
        self.groups = {symbol: [row for row in self.context["episodes"]
                               if row["split"] == "train" and row["status"] == "AVAILABLE"
                               and row["query"]["symbol"] == symbol] for symbol in SYMBOLS}
        if any(not rows for rows in self.groups.values()):
            raise ValueError("Mỗi mã phải có query train hợp lệ")
        for rows in self.groups.values():
            for row in rows:
                if row["query"]["exit_date"] > "2020-12-31":
                    raise ValueError("Query sau train không được tham gia optimizer/preflight")

    def _permutation(self, tasks: list[Any], seed: int, index: int, domain: int) -> list[Any]:
        """Stream riêng; domain 0 synthetic/1 market để không dùng lại permutation RNG."""
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([
            self.simulator.streams["prior_permutation"], seed, index, domain])))
        return [tasks[int(i)] for i in rng.permutation(len(tasks))]

    def batch(self, step: int, *, model_seed: int, preflight: bool = False) -> list[dict[str, Any]]:
        """Interleave 64+64; preflight model_seed=0, train 17/42/73, không giữ weights."""
        if (type(step) is not int or type(model_seed) is not int or step < 0
                or type(preflight) is not bool
                or (preflight and (model_seed != 0 or step >= 100))
                or (not preflight and (model_seed not in (17, 42, 73) or step >= 10000))):
            raise ValueError("Step/seed không thuộc recipe train/preflight đã khóa")
        result = []
        for offset in range(64):
            index = 64*step+offset
            synthetic = self.simulator.episode("runtime_preflight" if preflight else "synthetic_train",
                                               index, model_seed=model_seed)
            data = synthetic["input"]
            data["prior"] = self._permutation(data["prior"], model_seed, index, 0)
            result.append({"domain": "synthetic", "source_id": synthetic["episode_id"],
                           "stream": synthetic["stream"], "model_seed": model_seed,
                           "packed": pack_input(data, query_y=synthetic["supervised_query_y"])})
            rng = self.simulator._rng("market_sampling", model_seed, index)
            symbol = SYMBOLS[int(rng.integers(0, len(SYMBOLS)))]
            rows = self.groups[symbol]
            source = rows[int(rng.integers(0, len(rows)))]
            episode = deepcopy(source)
            episode["scaler"] = self.context["scalers"][episode.pop("scaler_sha256")]
            label = episode.pop("supervised_target")["y"]
            for key in ("packed", "projection_fixture", "split", "membership_sha256"):
                episode.pop(key, None)
            k, m = int(rng.integers(0, episode["K"]+1)), int(rng.integers(0, episode["m"]+1))
            episode["prior"] = self._permutation(episode["prior"][:k], model_seed, index, 1)
            episode["target"] = episode["target"][-m:] if m else []
            episode.update(K=k, m=m)
            validate_episode(episode)
            result.append({"domain": "market", "source_id": source["query"]["episode_id"],
                           "stream": "market_sampling", "model_seed": model_seed,
                           "symbol": symbol, "split": "train", "K": k, "m": m,
                           "packed": pack_episode(episode, training_query_y=label)})
        return result
