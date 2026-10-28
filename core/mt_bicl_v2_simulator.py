"""Sampler v2 theo manifest đã khóa; feature train độc lập với latent và nhãn sinh."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Sequence

import numpy as np

from core.mt_bicl_bank import content_hash
from core.mt_bicl_scaler import _vector
from core.mt_bicl_simulator import validate_input
from core.mt_bicl_v2_teacher import ALPHA, BETA, BetaBernoulliTeacher
from scripts.verify_mt_bicl_protocol_v2 import training_membership


def train_feature_pool(bank: dict[str, Any], membership: dict[str, Any]) -> dict[str, Any]:
    """Chỉ lấy nguyên vector train, giữ tương quan và không đọc outcome của cycle nguồn."""
    actual = training_membership(bank)
    if any(actual[key] != membership[key] for key in actual):
        raise ValueError("Pool feature không đúng membership/scaler train")
    records = {row["episode_id"]: row for row in bank["records"]
               if row["status"] == "AVAILABLE" and row["split"] == "train"}
    raw = np.asarray([_vector(records[name]["features"], records[name]["as_of_date"])
                      for name in membership["feature_pool_ids"]], dtype=np.float64)
    scaler = bank["frozen_scaler"]
    mean, scale = np.asarray(scaler["mean"]), np.asarray(scaler["scale"])
    if (mean.shape != (4,) or scale.shape != (4,) or not np.isfinite(mean).all()
            or not np.isfinite(scale).all() or (scale <= 0).any()):
        raise ValueError("Scaler pool không hợp lệ")
    vectors = np.clip((raw-mean)/scale, -4, 4)
    if not np.isfinite(vectors).all():
        raise ValueError("Pool feature không hữu hạn")
    return {"episode_ids": list(membership["feature_pool_ids"]), "vectors": vectors.tolist(),
            "scaler_sha256": content_hash(scaler), "source_outcomes_used": False}


class BetaTaskSimulator:
    """Random-access theo seed/episode/domain; không phụ thuộc thứ tự batch/resume."""

    def __init__(self, pi: Sequence[float], feature_pool: dict[str, Any], manifest: dict[str, Any]) -> None:
        """Sao chép dữ liệu train đã kiểm và manifest, không fit lại teacher hoặc scaler."""
        self.pi = BetaBernoulliTeacher(pi).pi
        self.pool = np.array(feature_pool["vectors"], dtype=np.float64, copy=True)
        if (self.pool.shape != (731, 4) or not np.isfinite(self.pool).all()
                or (np.abs(self.pool) > 4).any() or feature_pool["source_outcomes_used"] is not False):
            raise ValueError("Sampler cần đúng731 vector train đã clip")
        self.pool.setflags(write=False)
        self.manifest = deepcopy(manifest)

    def _check(self, stream: str, index: int, model_seed: int) -> int:
        """Từ chối ngoài range/model seed đã đăng ký, không tự kéo dài corpus."""
        if stream not in self.manifest["streams"] or type(index) is not int or type(model_seed) is not int:
            raise ValueError("Stream/ID/seed không hợp lệ")
        spec = self.manifest["streams"][stream]
        expected_seeds = (17, 42, 73) if stream in ("train", "preflight") else (0,)
        if model_seed not in expected_seeds or not 0 <= index < spec["ids"]["stop_exclusive"]:
            raise ValueError("ID/model seed ngoài manifest")
        return spec["seed"]

    def _base(self, stream: str, index: int, model_seed: int) -> dict[str, Any]:
        """Sinh cấu trúc, latent, vector rồi nhãn với các RNG miền độc lập."""
        seed = self._check(stream, index, model_seed)

        def rng(domain: int) -> np.random.Generator:
            """Không chia sẻ trạng thái global giữa train/validation/test/pair."""
            return np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, model_seed, index, domain])))

        stress = stream in ("synthetic_validation", "synthetic_test", "validation_swap", "test_swap") and index >= 4500
        if stress:
            case = (index-4500) % 10
            k, m = (1 if case < 5 else 3), [0, 1, 2, 4, 8][case % 5]
            lengths = [8]*k
            latent, theta = None, None
        else:
            structure = rng(0)
            k, m = int(structure.integers(0, 4)), int(structure.integers(0, 9))
            lengths = structure.integers(2, 9, size=k).tolist()
            latent = int(rng(1).choice(16, p=self.pi))
            theta = rng(2).beta(ALPHA[latent], BETA[latent], size=k+1)
        indices = rng(3).integers(0, 731, size=sum(lengths)+m+1)
        x = self.pool[indices].tolist()
        if stress:
            y_prior = [0 if ((index-4500)//10) % 2 == 0 else 1]*sum(lengths)
            y_target, query_y = [j % 2 for j in range(m)], None
        else:
            thresholds = np.repeat(theta, [*lengths, m+1])
            labels = (rng(4).random(len(thresholds)) < thresholds).astype(int).tolist()
            y_prior, y_target, query_y = labels[:sum(lengths)], labels[sum(lengths):-1], labels[-1]
        prefix = f"v2:{seed}:{model_seed}:{index}"
        prior, offset = [], 0
        for task_index, size in enumerate(lengths):
            name = f"{prefix}:P{task_index}"
            prior.append({"task_id": name, "observations": [
                {"observation_id": f"{name}:{j}", "x": x[offset+j], "y": y_prior[offset+j]}
                for j in range(size)]})
            offset += size
        target = {"task_id": f"{prefix}:T", "observations": [
            {"observation_id": f"{prefix}:T:{j}", "x": x[offset+j], "y": y_target[j]} for j in range(m)]}
        permutation_seed = self.manifest["streams"]["permutation"]["seed"]
        order = np.random.Generator(np.random.PCG64(np.random.SeedSequence(
            [permutation_seed, model_seed, index, seed]))).permutation(k).tolist()
        data = {"prior": [prior[j] for j in order], "target": target,
                "query": {"observation_id": f"{prefix}:Q", "x": x[-1]}}
        validate_input(data)
        return {"episode_id": prefix, "index": index, "stream": stream, "input": data,
                "sidecar": {"query_y": query_y, "lambda_index": latent,
                            "theta": theta.tolist() if theta is not None else None,
                            "source_feature_indices": indices.tolist(), "prior_permutation": order,
                            "stress": bool(stress)}}

    def episode(self, stream: str, index: int, *, model_seed: int = 0) -> dict[str, Any]:
        """Không cho lấy swap qua API episode hoặc dùng miền audit làm train."""
        if stream not in ("train", "diagnostic", "synthetic_validation", "synthetic_test", "pilot_tiny", "preflight"):
            raise ValueError("Stream không dành cho episode")
        return self._base(stream, index, model_seed)

    def pair(self, stream: str, index: int) -> dict[str, Any]:
        """Giữ toàn bộ x/C/query/ID; chỉ thay nhãn prior bằng miền λB/θB/labelsB."""
        if stream not in ("validation_swap", "test_swap"):
            raise ValueError("Stream không dành cho swap")
        episode = self._base(stream, index, 0)
        seed = self.manifest["streams"][stream]["seed"]
        a, b = episode["input"], deepcopy(episode["input"])
        latent, theta = None, None
        if episode["sidecar"]["stress"]:
            for task in b["prior"]:
                for row in task["observations"]:
                    row["y"] = 1-row["y"]
        else:
            def rng(domain: int) -> np.random.Generator:
                """Miền B không tiêu thụ RNG của target hoặc feature A."""
                return np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, 0, index, domain])))
            latent = int(rng(5).choice(16, p=self.pi))
            k = len(b["prior"])
            theta = rng(6).beta(ALPHA[latent], BETA[latent], size=k)
            order = episode["sidecar"]["prior_permutation"]
            canonical = sorted(zip(order, b["prior"]))
            thresholds = np.repeat(theta, [len(task["observations"]) for _, task in canonical])
            labels = (rng(7).random(len(thresholds)) < thresholds).astype(int).tolist()
            offset = 0
            for _, task in canonical:
                for row in task["observations"]:
                    row["y"] = labels[offset]
                    offset += 1
        validate_input(b)
        return {"episode_id": episode["episode_id"], "index": index, "stream": stream,
                "input_a": a, "input_b": b, "sidecar": {**episode["sidecar"],
                "lambda_b_index": latent, "theta_b": theta.tolist() if theta is not None else None}}
