"""Identity nguồn, lưu checkpoint atomic và ngân sách dùng chung cho ba seed."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import math
import os
from pathlib import Path
import tempfile
from time import perf_counter
from typing import Any

import torch

from core.bayesian_memory import _retry_windows_file_operation, atomic_write_json, read_json
from core.mt_bicl_bank import content_hash, read_protocol
from core.mt_bicl_batches import CONTEXT_PATH, CONTEXT_SHA256
from core.mt_bicl_training import rng_state
from core.prior_run_lock import safe_path
from scripts.verify_mt_bicl_protocol import validate_bundle, verify_sources

TRAINING_PATH = "outputs/bayesian_benchmark/mt_bicl_v1/training_v1"
CODE = ("core/mt_bicl_model.py", "core/mt_bicl_training.py", "core/mt_bicl_training_io.py",
        "core/mt_bicl_trainer.py", "scripts/train_mt_bicl.py", "core/prior_run_lock.py",
        "core/mt_bicl_bank.py", "core/mt_bicl_scaler.py", "core/bayesian_memory.py")
ORACLE_CODE = {
    "core/mt_bicl_simulator.py": "442c174a30e473cd2619e411578b41d39133b1aa1ff6c05cb6f8e25d696323e9",
    "core/mt_bicl_oracle.py": "213ad4c389a51a55e3962a3795054a3c79bf7c4c2830fcfc2cf67fe19334cbd5",
    "core/mt_bicl_oracle_reference.py": "782147c2cc9e654c700697b6a62304692dc5212851851b153f65b8261723a0d9",
    "core/mt_bicl_batches.py": "345f648b3ea3cb2bd8fdd04ed9587a6263035ccbcb9ad42c8e6617a98d46b3dc",
    "scripts/prepare_mt_bicl_oracle.py": "dc27373bf258497e6cf962436633370aa9b0cf97abe1360a296a25c8f7fb7b33",
}


def file_hash(path: Path) -> str:
    """Băm streaming để không nạp corpus test/nhãn oracle vào trainer."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_identity(root: Path) -> dict[str, Any]:
    """Đối soát nguồn khóa và runtime; không reseal đầu vào bị đổi."""
    protocol = read_protocol(root)
    directory = root/"docs/plan/week10"
    validate_bundle((directory/"protocol_v1.json").read_bytes(),
                    {name: (directory/name).read_bytes() for name in protocol["artifacts"]})
    verify_sources(root, protocol)
    inputs = {CONTEXT_PATH: CONTEXT_SHA256,
        "outputs/bayesian_benchmark/mt_bicl_v1/inputs/dense_bank_v1.json": "0c2abb43dd338ce12f63213260bad241ef0c6a9e315299ed631274d06da334dc",
        "outputs/bayesian_benchmark/mt_bicl_v1/inputs/synthetic_oracle_v1.json": "9f82873fc054788ba6bcc97c79edec4388bcda2c66c097ac763d8000ed2c1f66"}
    for name, expected in {**inputs, **ORACLE_CODE}.items():
        if file_hash(root/name) != expected:
            raise ValueError("Nguồn bank/context/oracle khác bản đã nghiệm thu: "+name)
    return {"version": "mt_bicl_training_identity_v1", "protocol_sha256": file_hash(directory/"protocol_v1.json"),
            "inputs_sha256": inputs, "oracle_code_sha256": ORACLE_CODE,
            "code_sha256": {name: file_hash(root/name) for name in CODE}, "runtime": protocol["runtime"],
            "precision": "FP32_NO_AMP_NO_TF32", "cpu_threads": 1,
            "optimizer_implementation": "AdamW_foreach_false_fused_false",
            "budget_seconds": 43200, "data_stop": protocol["time"]["data_stop"]}


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    """Envelope hash bắt lỗi hỏng/ghi dở; seal còn phải replay dự báo từ weights."""
    atomic_write_json(path, {"payload": payload, "sha256": content_hash(payload)})


def read_manifest(path: Path) -> dict[str, Any]:
    """Không nhận JSON sai envelope/hash hoặc NumPy/NaN trong payload."""
    envelope = read_json(path)
    if set(envelope) != {"payload", "sha256"} or content_hash(envelope["payload"]) != envelope["sha256"]:
        raise ValueError("Manifest sai checksum: "+str(path))
    return envelope["payload"]


def checkpoint_payload(model: torch.nn.Module, optimizer: torch.optim.Optimizer,
                       *, identity: str, seed: int, step: int, physical_batch: int) -> dict[str, Any]:
    """Step là số optimizer step đã hoàn thành; RNG thuộc trước episode 64*step tiếp theo."""
    return {"version": "mt_bicl_checkpoint_v1", "identity_sha256": identity, "seed": seed, "step": step,
            "physical_batch": physical_batch, "model": model.state_dict(), "optimizer": optimizer.state_dict(),
            "rng": rng_state()}


def save_checkpoint(path: Path, payload: dict[str, Any], *, replace: bool = False) -> dict[str, Any]:
    """Ghi/fsync/replace atomic; caller dùng tên mới và đổi pointer cho mỗi resume snapshot."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise ValueError("Không ghi đè checkpoint mốc đã lưu")
    name, failure = None, None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".checkpoint-", suffix=".tmp", delete=False) as handle:
            name = handle.name
            torch.save(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
        _retry_windows_file_operation(lambda: os.replace(name, path))
    except BaseException as error:
        failure = error
        raise
    finally:
        if name is not None and os.path.exists(name):
            try:
                _retry_windows_file_operation(lambda: os.unlink(name))
            except OSError as cleanup_error:
                if failure is None:
                    raise
                failure.add_note("Không dọn được file tạm checkpoint: "+str(cleanup_error))
    return {"file": path.name, "sha256": file_hash(path), "bytes": path.stat().st_size,
            "seed": payload["seed"], "step": payload["step"], "physical_batch": payload["physical_batch"]}


def load_checkpoint(directory: Path, record: dict[str, Any], identity: str) -> dict[str, Any]:
    """Kiểm hash/size/step/seed/physical batch trước load; weights_only không unpickle tùy ý."""
    path = safe_path(directory, record["file"])
    if path.stat().st_size != record["bytes"] or file_hash(path) != record["sha256"]:
        raise ValueError("Checkpoint khác manifest")
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if (payload["version"] != "mt_bicl_checkpoint_v1" or payload["identity_sha256"] != identity
            or type(payload["step"]) is not int or not 0 <= payload["step"] <= 10000
            or any(payload[key] != record[key] for key in ("seed", "step", "physical_batch"))):
        raise ValueError("Checkpoint sai identity/seed/step/batch")
    if not all(bool(torch.isfinite(v).all()) for v in payload["model"].values()):
        raise ValueError("Checkpoint chứa weights không hữu hạn")
    if not all(bool(torch.isfinite(v).all()) for state in payload["optimizer"]["state"].values()
               for v in state.values() if isinstance(v, torch.Tensor)):
        raise ValueError("Checkpoint chứa optimizer state không hữu hạn")
    return payload


class RunBudget:
    """Một state/12 giờ cho preflight và cả ba seed; Ctrl+C dừng đồng hồ sau khi lưu."""

    def __init__(self, directory: Path, identity: dict[str, Any]) -> None:
        self.directory, self.identity = directory, identity
        self.path = directory/"state.json"
        if self.path.exists():
            self.state = read_manifest(self.path)
            if self.state["identity"] != identity:
                raise ValueError("Source/runtime/inputs đã đổi; không resume bằng identity mới")
        else:
            self.state = {"version": "mt_bicl_training_run_v1", "identity": identity,
                          "status": "AWAITING_PREFLIGHT", "elapsed_seconds": 0., "active_since": None,
                          "preflight": None, "seeds": {str(s): {"status": "PENDING", "resume": None,
                          "checkpoints": []} for s in (17, 42, 73)}}
        self.started: float | None = None

    def __enter__(self) -> RunBudget:
        """Nếu lần trước chết cứng, tính cả khoảng không xác định tới lúc phục hồi để không lách cap."""
        elapsed = self.state["elapsed_seconds"]
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("Ngân sách elapsed không hợp lệ")
        now = datetime.now(timezone.utc)
        if self.state["active_since"] is not None:
            gap = (now-datetime.fromisoformat(self.state["active_since"])).total_seconds()
            if gap < 0:
                raise ValueError("Đồng hồ chạy lùi khi phục hồi")
            self.state["elapsed_seconds"] += gap
        self.state["active_since"] = now.isoformat()
        self.started = perf_counter()
        self.save()
        return self

    def used(self) -> float:
        """Wall time hoạt động, gồm generation/evaluation/checkpoint; không nhân cap mỗi seed."""
        return self.state["elapsed_seconds"]+(perf_counter()-self.started if self.started is not None else 0.)

    def save(self) -> None:
        """Giữ active_since tới khi session kết thúc; crash không làm reset thời gian."""
        write_manifest(self.path, self.state)

    def check(self, *, forecast_seconds: float = 0.) -> None:
        """Không cho candidate khi hết cap/lịch hoặc preflight dự báo không đủ thời gian."""
        stop = datetime.fromisoformat(self.identity["data_stop"]+"T23:59:59+07:00")
        now = datetime.now(timezone.utc)
        if (self.used()+forecast_seconds >= self.identity["budget_seconds"]
                or now+timedelta(seconds=forecast_seconds) >= stop
                or self.state["status"] == "INCOMPLETE_NO_CANDIDATE"):
            self.state["status"] = "INCOMPLETE_NO_CANDIDATE"
            self.save()
            raise RuntimeError("Hết quỹ giờ/lịch hoặc projection vượt cap: INCOMPLETE_NO_CANDIDATE")

    def __exit__(self, *args: Any) -> None:
        self.state["elapsed_seconds"] = self.used()
        self.state["active_since"] = None
        self.started = None
        self.save()
