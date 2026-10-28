"""Kiểm khóa đặc tả v2 và nguồn v1; không fit teacher, sinh corpus hoặc train."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.verify_mt_bicl_protocol import (
    PROTOCOL_SHA256 as LEGACY_SHA256, ROOT, _json, digest, validate_bundle,
    verify_sources,
)

DIRECTORY = Path("docs/plan/week10")
PROTOCOL_SHA256 = "00fa160c4fd25aacaf789ba011721f3e03d1b03b9b020cb298a93ca94ddedb40"


def canonical_hash(value: Any) -> str:
    """Băm JSON hữu hạn theo cùng quy ước của bank đã khóa."""
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8"))


def training_membership(bank: dict[str, Any]) -> dict[str, Any]:
    """Lấy ID train duy nhất theo block; không đọc outcome hoặc fit tham số."""
    rows = [row for row in bank["records"] if row["status"] == "AVAILABLE"
            and row["split"] == "train"]
    if any(not "2018-01-02" <= row["as_of_date"] < row["entry_date"]
           <= row["exit_date"] <= "2020-12-31" for row in rows):
        raise ValueError("Membership train chứa cycle ngoài split hoặc sai ngày")
    rows.sort(key=lambda row: (row["symbol"], row["as_of_date"], row["episode_id"]))
    ids = [row["episode_id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Membership train có ID trùng")
    groups: dict[str, list[str]] = {}
    for row in rows:
        groups.setdefault(row["task_id"], []).append(row["episode_id"])
    return {"feature_pool_ids": ids, "task_cycle_ids": dict(sorted(groups.items())),
            "cycles": len(rows), "tasks": len(groups),
            "frozen_scaler_sha256": canonical_hash(bank["frozen_scaler"])}


def validate_spec(data: bytes, artifacts: Mapping[str, bytes]) -> dict[str, Any]:
    """Từ chối tự rehash; kiểm số học và các ranh giới thực thi của bản khóa."""
    if digest(data) != PROTOCOL_SHA256:
        raise ValueError("Protocol v2 khác SHA-256 khóa; cần amendment mới, không self-seal")
    protocol = _json(data)
    if set(artifacts) != set(protocol["artifacts"]):
        raise ValueError("Danh mục artifact v2 không khớp")
    for name, expected in protocol["artifacts"].items():
        if digest(artifacts[name]) != expected:
            raise ValueError("Artifact v2 khác binding: " + name)
        _json(artifacts[name])
    flags = ("training_allowed", "teacher_fit_allowed", "development_allowed",
             "decision_calls_allowed", "is_execution_plan")
    if any(protocol[key] is not False for key in flags):
        raise ValueError("Đặc tả không cấp quyền fit/train/API")
    manifest = _json(artifacts["corpus_manifest_v2.json"])
    streams = manifest["streams"]
    seeds = [item["seed"] for item in streams.values()]
    if len(set(seeds)) != 10 or any(20261027 <= seed <= 20261103 for seed in seeds):
        raise ValueError("Stream v2 trùng seed hoặc trùng miền v1")
    if any(item["materialized"] for item in streams.values()):
        raise ValueError("Bước khóa recipe chưa sinh corpus")
    for name in ("synthetic_validation", "synthetic_test", "validation_swap", "test_swap"):
        if streams[name]["ids"] != {"start": 0, "stop_exclusive": 5000}:
            raise ValueError("Sai số episode/cặp đã đăng ký")
    if not all(streams[name]["held_until_selection_seal"] for name in ("synthetic_test", "test_swap")):
        raise ValueError("Test phải được giữ đến sau seal selection")
    model, training = protocol["model"], protocol["training"]
    h, ff = model["hidden"], model["ff"]
    parameters = (6*h+h + 3*h + 4*h + 37*h
                  + 2*(4*h*h+2*h*ff+9*h+ff) + 2*h + h+1)
    if parameters != model["parameters"] or parameters != 271873:
        raise ValueError("Số tham số paired learner không khớp")
    if protocol["tokenizer"]["max_tokens"] != 3*(1+8)+1+8+1:
        raise ValueError("Packing không khớp tối đa 37 token")
    if (training["optimizer_steps_per_seed"] // training["checkpoint_every_steps"]
            * len(training["model_seeds"]) != 60
            or any(a*b != 128 for a, b in zip(training["physical_batches_before_training"],
                                            training["gradient_accumulation"]))):
        raise ValueError("Sai ngân sách step/checkpoint/batch")
    budget = protocol["budget"]
    known_hours = budget["known_v1_active_seconds"] / 3600
    if (budget["training_budget_granted_seconds"] != 0 or budget["fit_budget_granted_seconds"] != 0
            or budget["v2_active_training_cap_seconds"] != 4*3600
            or abs(budget["W10_v2_remaining_upper_bound_hours"]-(10-known_hours)) > 1e-12
            or any(abs(rem-(total-known_hours)) > 1e-12 for rem, total in zip(
                budget["remaining_total_upper_bound_hours"], budget["user_total_hours"]))):
        raise ValueError("Ngân sách không được reset hoặc tự coi dự toán là quyền chạy")
    return protocol


def verify_evidence(root: Path, protocol: dict[str, Any],
                    membership: dict[str, Any]) -> dict[str, int]:
    """Băm nguồn và 77 file cũ, kiểm membership; không mở weights bằng torch."""
    byte_count = 0
    for section in ("source_sha256", "frozen_evidence_sha256"):
        for name, expected in protocol[section].items():
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
                raise ValueError("Đường dẫn binding không hợp lệ")
            content = (root / name).read_bytes()
            if digest(content) != expected:
                raise ValueError("Nguồn/bằng chứng đã đổi: " + name)
            if section == "frozen_evidence_sha256":
                byte_count += len(content)
    legacy_data = (root / DIRECTORY / "protocol_v1.json").read_bytes()
    if digest(legacy_data) != LEGACY_SHA256 or protocol["legacy_protocol_sha256"] != LEGACY_SHA256:
        raise ValueError("Protocol v1 phải giữ nguyên")
    legacy = _json(legacy_data)
    validate_bundle(legacy_data, {name: (root / DIRECTORY / name).read_bytes()
                                  for name in legacy["artifacts"]})
    verify_sources(root, legacy)
    for key in ("runtime", "splits", "economic_contract", "calendar", "features",
                "scaler", "regime", "membership", "numeric_baselines", "projection",
                "development", "confirmation"):
        if protocol[key] != legacy[key]:
            raise ValueError("Hợp đồng kế thừa không khớp: " + key)
    bank_path = root / "outputs/bayesian_benchmark/mt_bicl_v1/inputs/dense_bank_v1.json"
    bank_bytes = bank_path.read_bytes()
    envelope = _json(bank_bytes)
    if (digest(bank_bytes) != membership["bank_byte_sha256"]
            or canonical_hash(envelope["payload"]) != envelope["sha256"]
            or envelope["sha256"] != membership["bank_payload_sha256"]):
        raise ValueError("Bank không khớp membership v2")
    observed = training_membership(envelope["payload"])
    if any(observed[key] != membership[key] for key in observed):
        raise ValueError("Membership hoặc scaler train không khớp bản khóa")
    if observed["cycles"] != 731 or observed["tasks"] != 48:
        raise ValueError("Support train khác bản đăng ký")
    return {"evidence_files": len(protocol["frozen_evidence_sha256"]),
            "evidence_bytes": byte_count, "train_cycles": 731, "train_tasks": 48}


def main() -> None:
    """CLI chỉ đọc, không có cờ fit, run, train, sinh dữ liệu hoặc reseal."""
    if len(sys.argv) != 1:
        raise ValueError("Verifier v2 không nhận cờ thực thi hoặc reseal")
    data = (ROOT / DIRECTORY / "protocol_v2.json").read_bytes()
    if digest(data) != PROTOCOL_SHA256:
        raise ValueError("Protocol v2 khác bản khóa")
    protocol = _json(data)
    artifacts = {name: (ROOT / DIRECTORY / name).read_bytes() for name in protocol["artifacts"]}
    validate_spec(data, artifacts)
    summary = verify_evidence(ROOT, protocol, _json(artifacts["training_membership_v2.json"]))
    print(f"Khóa đặc tả v2 PASS; {summary['evidence_files']} file v1 nguyên byte; "
          f"{summary['train_cycles']} cycle/{summary['train_tasks']} block train. "
          "Chưa fit teacher, sinh corpus hoặc train; budget cấp=0, development/Decision=false.")


if __name__ == "__main__":
    main()
