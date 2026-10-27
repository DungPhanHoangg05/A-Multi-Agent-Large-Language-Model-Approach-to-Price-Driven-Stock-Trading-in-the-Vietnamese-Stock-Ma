"""Kiểm bản khóa protocol MT-BICL và nguồn; không train hoặc gọi Decision."""

from __future__ import annotations

import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
from typing import Any, Mapping
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = Path("docs/plan/week10")
PROTOCOL_SHA256 = "da5cb873aa86d15ba5c0d4d50f3d65ea9da810b62b5a32b3ba819534858432fd"


def digest(data: bytes) -> str:
    """Băm byte đã khóa, không sửa newline hoặc tự cập nhật binding."""
    return hashlib.sha256(data).hexdigest()


def _json(data: bytes) -> dict[str, Any]:
    """Từ chối NaN/Infinity và payload không phải object JSON."""
    def invalid(value: str) -> None:
        """Không nhận hằng số nằm ngoài chuẩn JSON."""
        raise ValueError("JSON có hằng số không hữu hạn: " + value)
    result = json.loads(data, parse_constant=invalid)
    if type(result) is not dict:
        raise ValueError("Artifact phải là object JSON")
    return result


def validate_bundle(protocol_bytes: bytes, artifacts: Mapping[str, bytes]) -> dict[str, Any]:
    """Kiểm byte khóa và tính nhất quán số học của đặc tả, không nhận self-seal.

    Hàm thuần cho phép kiểm dữ liệu hỏng mà không sửa bằng chứng trên đĩa.
    Đây không phải oracle, tokenizer hay gate cơ chế đã triển khai.
    """
    if digest(protocol_bytes) != PROTOCOL_SHA256:
        raise ValueError("Protocol khác SHA-256 đã khóa; không được tự rehash để vượt kiểm tra")
    protocol = _json(protocol_bytes)
    if set(artifacts) != set(protocol["artifacts"]):
        raise ValueError("Danh mục artifact không khớp protocol")
    for name, expected in protocol["artifacts"].items():
        if digest(artifacts[name]) != expected:
            raise ValueError("Artifact khác binding: " + name)
        _json(artifacts[name])
    simulator = _json(artifacts["simulator_v1.json"])
    fixtures = _json(artifacts["protocol_fixtures_v1.json"])
    centers = np.asarray(simulator["lambda_centers"], dtype=np.float64)
    support = np.asarray(simulator["w_support"], dtype=np.float64)
    mass = np.asarray(simulator["p_lambda"], dtype=np.float64)
    if (centers.shape != (16, 5) or support.shape != (64, 5) or mass.shape != (16,)
            or not all(np.isfinite(x).all() for x in (centers, support, mass))
            or (mass <= 0).any() or not np.isclose(mass.sum(), 1.0, rtol=0, atol=1e-15)):
        raise ValueError("Bảng simulator thiếu latent hoặc có khối lượng không hợp lệ")
    logits = -np.sum((support[None, :, :] - centers[:, None, :]) ** 2, axis=2) / (
        2 * simulator["p_w_given_lambda"]["tau"] ** 2)
    weights = np.exp(logits - logits.max(axis=1, keepdims=True))
    weights /= weights.sum(axis=1, keepdims=True)
    if (not np.isfinite(weights).all() or (weights <= 0).any()
            or not np.allclose(weights.sum(axis=1), 1, rtol=0, atol=1e-14)):
        raise ValueError("p(w|lambda) không chuẩn hóa theo từng hyper-state")
    if protocol["training_allowed"] or protocol["decision_calls_allowed"] or protocol["is_execution_plan"]:
        raise ValueError("Khóa đặc tả không phải release train hoặc API")
    training = protocol["training"]
    if (training["model_seeds"] != [17, 42, 73] or training["optimizer_steps_per_seed"] != 10_000
            or any(a * b != training["effective_batch"] for a, b in zip(
                training["physical_batches_before_training"], training["gradient_accumulation"]))):
        raise ValueError("Ngân sách train/batch khác đặc tả")
    model = protocol["model"]
    h, ff = model["hidden"], model["ff"]
    count = 6*h + h + 3*h + 69*h + model["layers"]*(4*h*h + 2*h*ff + 9*h + ff) + h + 1
    if count != model["parameters"]:
        raise ValueError("Số tham số backbone không khớp các kích thước đã khóa")
    if 3*(1+2*8)+1+2*8+1 != protocol["tokenizer"]["max_tokens"]:
        raise ValueError("Context tối đa không khớp packing")
    example = fixtures["token_example"]
    target_positions = example["loss_positions"]
    if (len(example["tokens"]) != 9 or target_positions != [6, 8]
            or example["tokens"][-1] != {"role": "QUERY", "values": [0, 0, 1, 1, 0, 1]}
            or example["query_label_in_input"]):
        raise ValueError("Fixture token/mask có nhãn query hoặc sai vị trí loss")
    cases = fixtures["contract_cases"]
    if len({row["id"] for row in cases}) != len(cases) or len(cases) != 24:
        raise ValueError("Fixture hợp đồng thiếu hoặc trùng ID")
    probes = fixtures["semantic_probe_ids"]
    if len(probes) != 24 or len(set(probes)) != 24:
        raise ValueError("Danh mục semantic probe thiếu hoặc trùng ID")
    development = protocol["development"]
    counts = {key: len(value) for key, value in development["symbol_cutoffs"].items()}
    if counts != {"FPT": 12, "MWG": 16, "VCB": 16, "VNM": 16}:
        raise ValueError("Lịch development không giữ 60 điểm W5/W9")
    if (development["primary_slots"] != 60*6 or development["repeat_slots_including_duplicate"] != 12*3*7
            or protocol["confirmation"]["primary_slots"] != 128*6):
        raise ValueError("Mẫu số ma trận hoặc repeat sai")
    return protocol


def verify_sources(root: Path, protocol: dict[str, Any]) -> None:
    """Kiểm nguồn byte còn nguyên và runtime phù hợp, không đọc payoff mới."""
    sources = {**protocol["source_sha256"],
               **{directory + "/manifest.json": value for directory, value in
                  protocol["price_manifest_sha256"].items()},
               "data/historical/manifest.json": protocol["historical_manifest_sha256"]}
    inventory = _json((root / DIRECTORY / "resource_inventory.json").read_bytes())
    sources.update(inventory["w9_locked_sha256"])
    sources["docs/plan/implementation_evidence.zip"] = inventory["retired_archive_sha256"]
    for name, expected in sources.items():
        if digest((root / name).read_bytes()) != expected:
            raise ValueError("Nguồn đã đổi so với khóa W10-02: " + name)
    for directory in (*protocol["price_manifest_sha256"], "data/historical"):
        manifest = _json((root / directory / "manifest.json").read_bytes())
        for item in manifest["files"].values():
            files = [item[key] for key in ("csv", "events", "evidence")] if "csv" in item else [item]
            for proof in files:
                path = root / directory / proof["file"]
                if digest(path.read_bytes()) != proof["sha256"]:
                    raise ValueError("Giá/evidence/quyền khác manifest đã khóa: " + str(path))
    ledger_name = "outputs/oos_pilot/api_usage.json"
    ledger = _json((root / ledger_name).read_bytes())
    with zipfile.ZipFile(root / "outputs/bayesian_benchmark/improvement_v1/holdout/frozen_results_v1.zip") as frozen:
        old = _json(frozen.read(ledger_name))
    requests = {row["id"]: row for row in ledger["requests"]}
    if (len(requests) != len(ledger["requests"])
            or any(requests.get(row["id"]) != row for row in old["requests"])):
        raise ValueError("Ledger có ID trùng hoặc request W9 bị sửa/mất; không reset để vượt kiểm tra")
    if platform.python_version() != protocol["runtime"]["python"]:
        raise ValueError("Python khác runtime đã khóa")
    for name in ("torch", "numpy", "pandas", "scikit-learn", "hmmlearn"):
        if version(name) != protocol["runtime"][name]:
            raise ValueError("Dependency khác runtime đã khóa: " + name)


def main() -> None:
    """Đọc khóa cố định và kiểm nguồn offline, không có cờ train/run/reseal."""
    if len(sys.argv) != 1:
        raise ValueError("Verifier đặc tả không nhận cờ train, run hoặc cập nhật hash")
    data = (ROOT / DIRECTORY / "protocol_v1.json").read_bytes()
    protocol = _json(data)
    if digest(data) != PROTOCOL_SHA256:
        raise ValueError("Protocol khác bản đã khóa")
    artifacts = {name: (ROOT / DIRECTORY / name).read_bytes() for name in protocol["artifacts"]}
    verified = validate_bundle(data, artifacts)
    verify_sources(ROOT, verified)
    print("Khóa đặc tả PASS: 16 hyper-state/64 w, 24 fixture/24 probe; nguồn/runtime còn nguyên. "
          "Chưa release train, Decision hoặc xác nhận.")


if __name__ == "__main__":
    main()
