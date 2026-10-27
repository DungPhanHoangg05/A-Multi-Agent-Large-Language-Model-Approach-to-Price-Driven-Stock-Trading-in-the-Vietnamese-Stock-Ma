"""Learner causal FP32 và loss chỉ trên X target/query theo protocol MT-BICL."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

MAX_TOKENS = 69


def collate_packets(packets: list[dict[str, Any]], device: torch.device) -> dict[str, torch.Tensor]:
    """Pad phải tới 69; nhãn loss ở tensor riêng, không nối vào numeric input."""
    if not packets:
        raise ValueError("Batch không được rỗng")
    count = len(packets)
    values = np.zeros((count, MAX_TOKENS, 6), dtype=np.float32)
    roles = np.zeros((count, MAX_TOKENS), dtype=np.int64)
    padding = np.ones((count, MAX_TOKENS), dtype=bool)
    labels = np.zeros((count, MAX_TOKENS), dtype=np.float32)
    loss_mask = np.zeros((count, MAX_TOKENS), dtype=bool)
    queries = []
    for i, packet in enumerate(packets):
        x, r = np.asarray(packet["values"], dtype=np.float32), packet["roles"]
        length = len(x)
        if (not 2 <= length <= MAX_TOKENS or x.shape != (length, 6) or not np.isfinite(x).all()
                or len(r) != length or any(type(v) is not int or v not in (0, 1, 2) for v in r)
                or packet["causal_mask"] != "LOWER_TRIANGULAR_INCLUDING_SELF"
                or packet["padding"] != "RIGHT_KEY_MASK_REQUIRED"
                or packet["query_position"] != length-1 or r[-1] != 2
                or not np.array_equal(x[-1, 4:], [0., 1.])):
            raise ValueError("Packet sai kích thước/mask/query chưa che nhãn")
        positions, targets = packet["prediction_positions"], packet["external_loss_labels"]
        expected = [j for j in range(length) if r[j] in (1, 2) and x[j, 4] == 0 and x[j, 5] == 1]
        if positions != expected or len(targets) != len(positions):
            raise ValueError("Loss phải nằm đúng mọi X target/query, không prior/Y/marker/PAD")
        for position, y in zip(positions, targets):
            if y is not None:
                if type(y) is not int or y not in (0, 1):
                    raise ValueError("Nhãn loss phải là int 0/1 gốc hoặc None khi inference")
                labels[i, position], loss_mask[i, position] = y, True
        values[i, :length], roles[i, :length], padding[i, :length] = x, r, False
        queries.append(length-1)
    return {"values": torch.from_numpy(values).to(device), "roles": torch.from_numpy(roles).to(device),
            "padding": torch.from_numpy(padding).to(device), "labels": torch.from_numpy(labels).to(device),
            "loss_mask": torch.from_numpy(loss_mask).to(device),
            "queries": torch.tensor(queries, dtype=torch.long, device=device)}


class MTBiCLLearner(nn.Module):
    """Hai lớp hidden128/4 heads/FF256, không encoder hai chiều hoặc input query y."""

    def __init__(self) -> None:
        """Kiến trúc cố định 275.201 tham số, không nhận cờ đổi architecture."""
        super().__init__()
        self.numeric = nn.Linear(6, 128)
        self.role = nn.Embedding(3, 128)
        self.position = nn.Embedding(MAX_TOKENS, 128)
        layer = nn.TransformerEncoderLayer(128, 4, dim_feedforward=256, dropout=.1, activation="relu",
                                          layer_norm_eps=1e-5, batch_first=True, norm_first=False)
        self.decoder = nn.TransformerEncoder(layer, 2, enable_nested_tensor=False)
        self.head = nn.Linear(128, 1)
        self.register_buffer("causal_mask", torch.ones(MAX_TOKENS, MAX_TOKENS, dtype=torch.bool).triu(1), persistent=False)
        if sum(p.numel() for p in self.parameters()) != 275201:
            raise ValueError("Số tham số khác architecture đã khóa")

    def forward(self, values: torch.Tensor, roles: torch.Tensor, padding: torch.Tensor) -> torch.Tensor:
        """Mask tương lai và key padding tách riêng, vị trí hiện tại chỉ đọc X chưa có Y."""
        if values.dtype != torch.float32 or values.shape[1:] != (MAX_TOKENS, 6):
            raise ValueError("Learner chỉ nhận FP32 [batch,69,6]")
        hidden = self.numeric(values)+self.role(roles)+self.position(torch.arange(MAX_TOKENS, device=values.device))
        hidden = self.decoder(hidden, mask=self.causal_mask, src_key_padding_mask=padding, is_causal=True)
        return self.head(hidden).squeeze(-1)


def episode_losses(logits: torch.Tensor, batch: dict[str, torch.Tensor]) -> torch.Tensor:
    """Mean BCE tại X target/query của từng episode trước mean effective batch."""
    mask = batch["loss_mask"]
    counts = mask.sum(dim=1)
    if bool((counts == 0).any()):
        raise ValueError("Episode train không có nhãn target/query")
    return (F.binary_cross_entropy_with_logits(logits, batch["labels"], reduction="none")*mask).sum(dim=1)/counts
