"""Optimizer, RNG checkpoint và chọn checkpoint bằng 2021, không đọc synthetic test."""

from __future__ import annotations

import os
import random
from typing import Any

import numpy as np
import torch

from core.mt_bicl_bank import SYMBOLS
from core.mt_bicl_model import MTBiCLLearner, collate_packets, episode_losses


def configure(seed: int, *, cuda: bool) -> torch.device:
    """Ghim deterministic/FP32 và seed mọi RNG; CPU chỉ dùng unit test."""
    if os.environ.get("CUBLAS_WORKSPACE_CONFIG") != ":4096:8":
        raise ValueError("Cần đặt CUBLAS_WORKSPACE_CONFIG=:4096:8 trước khởi tạo CUDA")
    if cuda and not torch.cuda.is_available():
        raise ValueError("Preflight/train production yêu cầu CUDA khả dụng")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if cuda:
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_float32_matmul_precision("highest")
    torch.set_default_dtype(torch.float32)
    torch.set_num_threads(1)
    return torch.device("cuda:0" if cuda else "cpu")


def make_optimizer(model: MTBiCLLearner) -> torch.optim.AdamW:
    """Giữ lr/betas/eps/weight decay đã khóa; không scheduler hoặc early stopping."""
    return torch.optim.AdamW(model.parameters(), lr=3e-4, betas=(.9, .999), eps=1e-8,
                             weight_decay=.01, foreach=False, fused=False)


def optimizer_step(model: MTBiCLLearner, optimizer: torch.optim.Optimizer,
                   packets: list[dict[str, Any]], physical_batch: int, device: torch.device) -> float:
    """Accumulation chia liên tiếp, mean theo episode; clip một lần trước optimizer.step."""
    count = len(packets)
    if count == 0 or physical_batch < 1 or count % physical_batch:
        raise ValueError("Physical batch phải chia hết effective batch")
    model.train()
    optimizer.zero_grad(set_to_none=True)
    total = 0.
    for start in range(0, count, physical_batch):
        batch = collate_packets(packets[start:start+physical_batch], device)
        losses = episode_losses(model(batch["values"], batch["roles"], batch["padding"]), batch)
        if not bool(torch.isfinite(losses).all()):
            raise ValueError("Loss train không hữu hạn")
        loss = losses.sum()/count
        loss.backward()
        total += float(loss.detach().cpu())
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1., error_if_nonfinite=True)
    optimizer.step()
    if not all(bool(torch.isfinite(p).all()) for p in model.parameters()):
        raise ValueError("Weights train không hữu hạn")
    return total


def rng_state() -> dict[str, Any]:
    """Dùng tensor/primitive để torch.load(weights_only=True), không pickle NumPy object."""
    state = np.random.get_state()
    return {"python": random.getstate(), "numpy": {"name": state[0],
            "keys": torch.tensor(state[1].astype(np.int64)), "position": state[2],
            "has_gauss": state[3], "cached_gaussian": state[4]}, "torch": torch.get_rng_state(),
            "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_initialized() else []}


def restore_rng(state: dict[str, Any]) -> None:
    """Phục hồi ngay trước step tiếp theo, sau khi dựng model/optimizer và load state."""
    random.setstate(state["python"])
    value = state["numpy"]
    np.random.set_state((value["name"], value["keys"].numpy().astype(np.uint32), value["position"],
                         value["has_gauss"], value["cached_gaussian"]))
    torch.set_rng_state(state["torch"])
    if state["cuda"]:
        torch.cuda.set_rng_state_all(state["cuda"])


def selection_rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Chỉ 2021 để selection, giữ mọi query có x/nhãn hợp lệ cùng tập mọi seed."""
    rows = [r for r in context["episodes"] if r["split"] == "checkpoint_selection" and r["status"] == "AVAILABLE"]
    if any(sum(r["query"]["symbol"] == symbol for r in rows) < 40 for symbol in SYMBOLS):
        raise ValueError("Selection thiếu tối thiểu 40 query mỗi mã")
    if any(not "2021-01-01" <= r["query"]["as_of_date"] < r["query"]["exit_date"] <= "2021-12-31" for r in rows):
        raise ValueError("Selection chứa query ngoài 2021 hoặc vắt split")
    return sorted(rows, key=lambda r: (r["query"]["as_of_date"], SYMBOLS.index(r["query"]["symbol"])))


def selection_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Macro đều mã, clip chỉ log loss thị trường; không dùng P&L hoặc synthetic oracle."""
    if not records or len({r["episode_id"] for r in records}) != len(records):
        raise ValueError("Dự báo selection rỗng hoặc trùng ID")
    metrics = {}
    for symbol in SYMBOLS:
        group = [r for r in records if r["symbol"] == symbol]
        if not group:
            raise ValueError("Selection thiếu mã")
        p, y = np.asarray([r["p"] for r in group]), np.asarray([r["y"] for r in group])
        if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any() or not np.isin(y, [0, 1]).all():
            raise ValueError("Xác suất/nhãn selection không hợp lệ")
        clipped = np.clip(p, 1e-6, 1-1e-6)
        metrics[symbol] = {"count": len(group), "log_loss": float(-(y*np.log(clipped)+(1-y)*np.log1p(-clipped)).mean()),
                           "brier": float(((p-y)**2).mean())}
    return {"symbols": metrics, "macro_log_loss": float(np.mean([m["log_loss"] for m in metrics.values()])),
            "macro_brier": float(np.mean([m["brier"] for m in metrics.values()]))}


def evaluate_selection(model: MTBiCLLearner, rows: list[dict[str, Any]], physical_batch: int,
                       device: torch.device) -> dict[str, Any]:
    """Eval/inference mode: lấy logit query, không loss/gradient/update scaler hoặc optimizer."""
    model.eval()
    records = []
    with torch.inference_mode():
        for start in range(0, len(rows), physical_batch):
            group = rows[start:start+physical_batch]
            batch = collate_packets([r["packed"] for r in group], device)
            logits = model(batch["values"], batch["roles"], batch["padding"])
            query_logits = logits[torch.arange(len(group), device=device), batch["queries"]].cpu().tolist()
            if not np.isfinite(query_logits).all():
                raise ValueError("Logit selection không hữu hạn")
            for row, logit in zip(group, query_logits):
                records.append({"episode_id": row["query"]["episode_id"], "symbol": row["query"]["symbol"],
                                "y": row["supervised_target"]["y"], "logit": float(logit),
                                "p": float(np.exp(-np.logaddexp(0, -logit)))})
    return {"dataset": "checkpoint_selection_2021", "records": records, "metrics": selection_metrics(records)}


def selection_key(record: dict[str, Any]) -> tuple[float, float, int, int]:
    """Tie-break khóa trước: macro log loss, Brier, step tăng dần, seed 17/42/73."""
    metrics = record["metrics"]
    return (round(metrics["macro_log_loss"], 12), round(metrics["macro_brier"], 12),
            record["step"], (17, 42, 73).index(record["seed"]))
