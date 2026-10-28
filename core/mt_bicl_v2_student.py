"""Learner distillation v2: paired/legacy packing, causal mask và soft loss chỉ query."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from core.mt_bicl_simulator import validate_input

LEGACY = "LEGACY_X_Y_69_WITH_TASK_SLOT"
PAIRED = "PAIRED_37"
CASES = (LEGACY, PAIRED)
MARKER = [0., 0., 0., 0., -1., 1.]


def _encode(data: dict[str, Any], packing: str, teacher_q: float | None) -> dict[str, Any]:
    """Mã hóa input đã validate; hàm riêng cho phép đối chiếu fixture một observation."""
    values, roles, slots = [], [], []
    for role, slot, task in [*((0, i, task) for i, task in enumerate(data["prior"])),
                             (1, 3, data["target"])]:
        values.append(list(MARKER))
        roles.append(role)
        slots.append(slot)
        for row in task["observations"]:
            if packing == PAIRED:
                tokens = [[*row["x"], float(row["y"]), 0.]]
            else:
                tokens = [[*row["x"], 0., 1.], [0., 0., 0., 0., float(row["y"]), 0.]]
            values.extend(tokens)
            roles.extend([role]*len(tokens))
            slots.extend([slot]*len(tokens))
    values.append([*data["query"]["x"], 0., 1.])
    roles.append(2)
    slots.append(3)
    return {"version": "mt_bicl_distillation_packet_v2", "packing": packing,
            "values": values, "roles": roles, "task_slots": slots,
            "query_position": len(values)-1, "loss_positions": [len(values)-1],
            "teacher_q": teacher_q, "causal_mask": "LOWER_TRIANGULAR_INCLUDING_SELF",
            "padding": "RIGHT_KEY_MASK"}


def pack_input(data: dict[str, Any], *, teacher_q: float | None = None,
               packing: str = PAIRED) -> dict[str, Any]:
    """Nhãn query/latent không có tham số nhận; q posterior là sidecar loss tách biệt."""
    validate_input(data)
    if packing not in CASES or (teacher_q is not None and (
            type(teacher_q) not in (int, float) or not np.isfinite(teacher_q) or not 0 <= teacher_q <= 1)):
        raise ValueError("Packing hoặc soft teacher q không hợp lệ")
    return _encode(data, packing, float(teacher_q) if teacher_q is not None else None)


def validate_packet(packet: dict[str, Any]) -> None:
    """Giải mã rồi round-trip để chặn label query, role/slot/mask và loss vị trí sai."""
    expected_keys = {"version", "packing", "values", "roles", "task_slots", "query_position",
                     "loss_positions", "teacher_q", "causal_mask", "padding"}
    if type(packet) is not dict or set(packet) != expected_keys or packet["packing"] not in CASES:
        raise ValueError("Packet distillation sai schema")
    values, roles, slots = packet["values"], packet["roles"], packet["task_slots"]
    if (type(values) is not list or not 2 <= len(values) <= (37 if packet["packing"] == PAIRED else 69)
            or len(roles) != len(values) or len(slots) != len(values)
            or any(type(x) is not int for x in [*roles, *slots])
            or any(type(row) is not list or len(row) != 6 or any(type(x) not in (int, float) for x in row)
                   for row in values) or not np.isfinite(values).all()):
        raise ValueError("Packet distillation sai kích thước/kiểu hoặc không hữu hạn")
    if roles[-1] != 2 or slots[-1] != 3 or values[-1][4:] != [0., 1.]:
        raise ValueError("Query phải che nhãn và thuộc target slot3")
    tasks, index = [], 0
    while index < len(values)-1:
        role, slot = roles[index], slots[index]
        if values[index] != MARKER or role not in (0, 1):
            raise ValueError("Thiếu marker ranh giới task")
        target = role == 1
        if slot != (3 if target else len(tasks)):
            raise ValueError("Task slot không theo thứ tự trình bày")
        task = {"task_id": f"T{len(tasks)}", "observations": []}
        index += 1
        while index < len(values)-1 and values[index] != MARKER:
            if roles[index] != role or slots[index] != slot:
                raise ValueError("Observation vượt role/task slot")
            if packet["packing"] == PAIRED:
                x, y = values[index][:4], values[index][4]
                if values[index][5] != 0. or y not in (0., 1.):
                    raise ValueError("Paired observation phải có nhãn đã biết")
                index += 1
            else:
                if index+1 >= len(values)-1 or values[index][4:] != [0., 1.]:
                    raise ValueError("Legacy X thiếu Y kế tiếp")
                label = values[index+1]
                if label[:4] != [0.]*4 or label[5] != 0. or label[4] not in (0., 1.) \
                        or roles[index+1] != role or slots[index+1] != slot:
                    raise ValueError("Legacy Y sai nhãn/role/slot")
                x, y = values[index][:4], label[4]
                index += 2
            task["observations"].append({"observation_id": f"O{index}", "x": x, "y": int(y)})
        tasks.append((role, task))
        if target and index != len(values)-1:
            raise ValueError("Target phải là task cuối cùng")
    if not tasks or tasks[-1][0] != 1 or any(role != 0 for role, _ in tasks[:-1]):
        raise ValueError("Phân vai prior/target không đúng")
    data = {"prior": [task for _, task in tasks[:-1]], "target": tasks[-1][1],
            "query": {"observation_id": "Q", "x": values[-1][:4]}}
    expected = pack_input(data, packing=packet["packing"], teacher_q=packet["teacher_q"])
    if expected != packet:
        raise ValueError("Packet bị đổi mask, loss hoặc metadata đã khóa")


def collate_packets(packets: list[dict[str, Any]], device: torch.device) -> dict[str, torch.Tensor]:
    """Pad phải; q chỉ ở tensor loss, không truyền vào numeric/role/slot của forward."""
    if not packets:
        raise ValueError("Batch distillation không được rỗng")
    packing = packets[0]["packing"]
    length = 37 if packing == PAIRED else 69
    count = len(packets)
    values = np.zeros((count, length, 6), dtype=np.float32)
    roles = np.zeros((count, length), dtype=np.int64)
    slots = np.zeros((count, length), dtype=np.int64)
    padding = np.ones((count, length), dtype=bool)
    qs, labels, queries = [], [], []
    for i, packet in enumerate(packets):
        validate_packet(packet)
        if packet["packing"] != packing:
            raise ValueError("Không trộn hai packing trong một batch")
        size = len(packet["values"])
        values[i, :size], roles[i, :size], slots[i, :size] = packet["values"], packet["roles"], packet["task_slots"]
        padding[i, :size] = False
        queries.append(size-1)
        qs.append(packet["teacher_q"] if packet["teacher_q"] is not None else 0.)
        labels.append(packet["teacher_q"] is not None)
    return {"values": torch.from_numpy(values).to(device), "roles": torch.from_numpy(roles).to(device),
            "slots": torch.from_numpy(slots).to(device), "padding": torch.from_numpy(padding).to(device),
            "queries": torch.tensor(queries, dtype=torch.long, device=device),
            "teacher_q": torch.tensor(qs, dtype=torch.float32, device=device),
            "has_teacher_q": torch.tensor(labels, dtype=torch.bool, device=device)}


class DistilledStudent(nn.Module):
    """Hai lớp128/head4/FF256, pre-LN/GELU/dropout0 và final LayerNorm đã khóa."""

    def __init__(self, packing: str = PAIRED) -> None:
        """Legacy chỉ là pilot đối chứng; không có cờ thay chiều sâu/hidden/loss."""
        super().__init__()
        if packing not in CASES:
            raise ValueError("Packing student không hợp lệ")
        self.packing, self.max_tokens = packing, 37 if packing == PAIRED else 69
        self.numeric = nn.Linear(6, 128)
        self.role, self.slot = nn.Embedding(3, 128), nn.Embedding(4, 128)
        layer = nn.TransformerEncoderLayer(128, 4, dim_feedforward=256, dropout=0., activation="gelu",
                                          layer_norm_eps=1e-5, batch_first=True, norm_first=True)
        self.decoder = nn.TransformerEncoder(layer, 2, enable_nested_tensor=False)
        self.norm, self.head = nn.LayerNorm(128, eps=1e-5), nn.Linear(128, 1)
        # Đặt position cuối để hai pilot cùng seed có cùng weights ở mọi khối chung.
        self.position = nn.Embedding(self.max_tokens, 128)
        self.register_buffer("causal_mask", torch.ones(self.max_tokens, self.max_tokens, dtype=torch.bool).triu(1), persistent=False)
        if sum(p.numel() for p in self.parameters()) != (271873 if packing == PAIRED else 275969):
            raise ValueError("Số tham số student khác protocol")

    def forward(self, values: torch.Tensor, roles: torch.Tensor, slots: torch.Tensor,
                padding: torch.Tensor) -> torch.Tensor:
        """Chỉ đọc context hợp lệ; không có đối số q, query y hoặc latent."""
        if values.dtype != torch.float32 or values.shape[1:] != (self.max_tokens, 6):
            raise ValueError("Student chỉ nhận input FP32 đúng chiều đã khóa")
        hidden = self.numeric(values)+self.role(roles)+self.slot(slots)+self.position(
            torch.arange(self.max_tokens, device=values.device))
        hidden = self.decoder(hidden, mask=self.causal_mask, src_key_padding_mask=padding, is_causal=True)
        return self.head(self.norm(hidden)).squeeze(-1)


def query_losses(logits: torch.Tensor, batch: dict[str, torch.Tensor]) -> torch.Tensor:
    """Soft Bernoulli cross-entropy mỗi episode, gradient chỉ tại logit query, q detach."""
    q = batch["teacher_q"].detach()
    if (not bool(batch["has_teacher_q"].all()) or not bool(torch.isfinite(q).all())
            or bool(((q < 0) | (q > 1)).any())):
        raise ValueError("Train cần q posterior hữu hạn cho mọi episode")
    query = logits[torch.arange(len(q), device=logits.device), batch["queries"]]
    return F.binary_cross_entropy_with_logits(query, q, reduction="none")
