"""Optimizer/scheduler, inference đóng băng và metric distillation MT-BICL dùng lại cho pilot."""

from __future__ import annotations

import hashlib
import math
from typing import Any

import numpy as np
import torch

from core.mt_bicl_student import DistilledStudent, collate_packets, query_losses


def make_optimizer(model: DistilledStudent) -> torch.optim.AdamW:
    """AdamW đúng protocol; pilot giữ lr cố định, train chính dùng lịch riêng đã khóa."""
    return torch.optim.AdamW(model.parameters(), lr=3e-4, betas=(.9, .999), eps=1e-8,
                             weight_decay=.01, foreach=False, fused=False)


def scheduled_lr(step: int) -> float:
    """Warmup250 rồi cosine tới step5000; không dùng scheduler này cho pilot."""
    if type(step) is not int or not 1 <= step <= 5000:
        raise ValueError("Step scheduler ngoài miền1…5000")
    return float(step/250*3e-4 if step <= 250 else
                 3e-5+.5*(3e-4-3e-5)*(1+math.cos(math.pi*(step-250)/4750)))


def optimizer_step(model: DistilledStudent, optimizer: torch.optim.Optimizer,
                   packets: list[dict[str, Any]], physical_batch: int,
                   device: torch.device) -> dict[str, float]:
    """Mean theo episode trên effective batch; accumulation và clip đúng một lần."""
    count = len(packets)
    if not count or physical_batch < 1 or count % physical_batch:
        raise ValueError("Physical batch phải chia hết effective batch")
    model.train()
    optimizer.zero_grad(set_to_none=True)
    total = 0.
    for start in range(0, count, physical_batch):
        batch = collate_packets(packets[start:start+physical_batch], device)
        losses = query_losses(model(batch["values"], batch["roles"], batch["slots"], batch["padding"]), batch)
        if not bool(torch.isfinite(losses).all()):
            raise ValueError("Loss distillation không hữu hạn")
        loss = losses.sum()/count
        loss.backward()
        total += float(loss.detach().cpu())
    norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1., error_if_nonfinite=True)
    optimizer.step()
    if not all(bool(torch.isfinite(p).all()) for p in model.parameters()):
        raise ValueError("Weights student không hữu hạn")
    return {"soft_cross_entropy": total, "gradient_norm_before_clip": float(norm.detach().cpu())}


def tensor_hash(model: DistilledStudent) -> str:
    """Băm cả tên/dtype/shape/byte state_dict để kiểm inference không update weights."""
    value = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        cpu = tensor.detach().cpu().contiguous()
        value.update(f"{name}:{cpu.dtype}:{tuple(cpu.shape)}:".encode())
        value.update(cpu.numpy().tobytes())
    return value.hexdigest()


def metric_report(logits: list[float], qs: list[float]) -> dict[str, Any]:
    """KL oracle||student float64 từ log probabilities ổn định, không clipping."""
    z, q = np.asarray(logits, dtype=np.float64), np.asarray(qs, dtype=np.float64)
    if (z.ndim != 1 or not len(z) or z.shape != q.shape or not np.isfinite(z).all()
            or not np.isfinite(q).all() or ((q < 0) | (q > 1)).any()):
        raise ValueError("Logit/q cho metric không hợp lệ")
    one, zero = -np.logaddexp(0, -z), -np.logaddexp(0, z)
    entropy = np.zeros_like(q)
    positive = q > 0
    entropy[positive] += q[positive]*np.log(q[positive])
    positive = q < 1
    entropy[positive] += (1-q[positive])*np.log1p(-q[positive])
    cross_entropy = -q*one-(1-q)*zero
    kl = entropy+cross_entropy
    if float(kl.min()) < -1e-12:
        raise ValueError("KL âm ngoài sai số số học")
    error = np.abs(np.exp(one)-q)
    return {"count": len(z), "mean_kl_nat": float(kl.mean()),
            "soft_cross_entropy": float(cross_entropy.mean()),
            "p95_absolute_error": float(np.quantile(error, .95, method="linear")),
            "mean_absolute_error": float(error.mean()), "raw_logits": z.tolist(), "teacher_q": q.tolist()}


def evaluate(model: DistilledStudent, packets: list[dict[str, Any]], physical_batch: int,
             device: torch.device) -> dict[str, Any]:
    """Eval/inference mode, fingerprint trước/sau; chỉ dùng corpus diagnostic/tiny đã cho phép."""
    before = tensor_hash(model)
    model.eval()
    logits = []
    with torch.inference_mode():
        for start in range(0, len(packets), physical_batch):
            batch = collate_packets(packets[start:start+physical_batch], device)
            values = model(batch["values"], batch["roles"], batch["slots"], batch["padding"])
            logits.extend(values[torch.arange(len(batch["queries"]), device=device), batch["queries"]].cpu().tolist())
    if before != tensor_hash(model):
        raise ValueError("Inference đã làm đổi weights student")
    result = metric_report(logits, [packet["teacher_q"] for packet in packets])
    result["model_tensor_sha256"] = before
    return result


def gradient_audit(model: DistilledStudent, packets: list[dict[str, Any]],
                   device: torch.device) -> dict[str, Any]:
    """Đo gradient logit thật: chỉ query có loss, không marker/prior/target/PAD."""
    batch = collate_packets(packets, device)
    model.train()
    values = model(batch["values"], batch["roles"], batch["slots"], batch["padding"])
    losses = query_losses(values, batch)
    gradient, = torch.autograd.grad(losses.mean(), values)
    mask = torch.zeros_like(gradient, dtype=torch.bool)
    mask[torch.arange(len(packets), device=device), batch["queries"]] = True
    outside = int(torch.count_nonzero(gradient[~mask]).cpu())
    finite = bool(torch.isfinite(gradient).all())
    if outside or not finite or not bool((gradient[mask] != 0).any()):
        raise ValueError("Gradient query-only không đúng hoặc không hữu hạn")
    return {"status": "PASS", "query_positions": len(packets),
            "nonzero_outside_query": outside, "finite": finite}
