"""Biên input D/C/x và membership train của MT-BICL."""

from __future__ import annotations
from typing import Any
import numpy as np
from core.mt_bicl_bank import canonical_bytes, content_hash

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
            "frozen_scaler_sha256": content_hash(bank["frozen_scaler"])}
