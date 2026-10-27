"""Đo tài nguyên decoder dự kiến bằng dữ liệu giả; không train candidate MT-BICL."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
from statistics import median
import subprocess
from time import perf_counter
from typing import Any


def benchmark(*, steps: int = 100, warmup: int = 10, batch_size: int = 128) -> dict[str, Any]:
    """Đo forward/backward/AdamW FP32 tại context dài nhất, không lưu weights.

    Packing tạm dùng một token ranh giới/task và hai token x/y mỗi observation.
    Đây là proxy tài nguyên; tokenizer, simulator và loss thật khóa ở W10-02.
    """
    if steps < 100 or warmup < 1 or batch_size < 1:
        raise ValueError("Cần ít nhất 100 step đo, warm-up và batch dương")
    import torch
    from torch import nn

    if platform.python_version() != "3.13.5" or not torch.cuda.is_available():
        raise ValueError("Benchmark yêu cầu Python 3.13.5 và CUDA khả dụng")
    torch.manual_seed(42)
    torch.cuda.manual_seed_all(42)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    device = torch.device("cuda:0")
    roles: list[int] = []
    label_visible: list[bool] = []
    target_positions: list[int] = []
    for role in range(4):
        roles.append(0 if role < 3 else 1)
        label_visible.append(False)
        for _ in range(8):
            if role == 3:
                target_positions.append(len(roles))
            roles.extend([0 if role < 3 else 1] * 2)
            label_visible.extend([False, True])
    target_positions.append(len(roles))
    roles.append(2)
    label_visible.append(False)
    length = len(roles)

    class ResourceDecoder(nn.Module):
        """Decoder causal chỉ phục vụ đo tốc độ và bộ nhớ."""

        def __init__(self) -> None:
            """Giữ đúng kích thước backbone dự kiến và head Bernoulli."""
            super().__init__()
            self.numeric = nn.Linear(6, 128)
            self.role = nn.Embedding(3, 128)
            self.position = nn.Embedding(length, 128)
            layer = nn.TransformerEncoderLayer(
                128, 4, dim_feedforward=256, dropout=0.1, batch_first=True,
            )
            self.decoder = nn.TransformerEncoder(layer, 2, enable_nested_tensor=False)
            self.head = nn.Linear(128, 1)

        def forward(self, values: torch.Tensor) -> torch.Tensor:
            """Trả logit; causal mask chặn nhìn token nhãn sau vị trí dự báo."""
            hidden = self.numeric(values) + self.role(role_ids) + self.position(position_ids)
            hidden = self.decoder(hidden, mask=causal_mask, is_causal=True)
            return self.head(hidden).squeeze(-1)

    role_ids = torch.tensor(roles, device=device)
    position_ids = torch.arange(length, device=device)
    causal_mask = nn.Transformer.generate_square_subsequent_mask(length, device=device)
    visible = torch.tensor(label_visible, device=device)
    values = torch.randn(batch_size, length, 6, device=device)
    values[:, :, 4] = torch.where(visible, torch.randint(0, 2, (batch_size, length), device=device), 0)
    values[:, :, 5] = (~visible).float()
    labels = torch.randint(0, 2, (batch_size, len(target_positions)), device=device).float()
    model = ResourceDecoder().to(device).train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4)
    durations: list[float] = []
    torch.cuda.reset_peak_memory_stats(device)
    start_all = perf_counter()
    for step in range(warmup + steps):
        torch.cuda.synchronize(device)
        start = perf_counter()
        optimizer.zero_grad(set_to_none=True)
        logits = model(values)[:, target_positions]
        loss = nn.functional.binary_cross_entropy_with_logits(logits, labels)
        loss.backward()
        optimizer.step()
        torch.cuda.synchronize(device)
        elapsed = perf_counter() - start
        if not bool(torch.isfinite(loss)):
            raise ValueError("Loss benchmark không hữu hạn")
        if step >= warmup:
            durations.append(elapsed)
    if not all(bool(torch.isfinite(p).all()) for p in model.parameters()):
        raise ValueError("Weights benchmark không hữu hạn")
    ordered = sorted(durations)
    mean = sum(durations) / len(durations)
    properties = torch.cuda.get_device_properties(device)
    driver = subprocess.run(
        ["nvidia-smi", "--query-gpu=driver_version,power.limit", "--format=csv,noheader"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return {
        "benchmark_version": "mt_bicl_gpu_proxy_v1",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python": platform.python_version(), "torch": str(torch.__version__),
        "cuda": torch.version.cuda, "gpu": properties.name,
        "compute_capability": list(torch.cuda.get_device_capability(device)),
        "device_memory_bytes": int(properties.total_memory), "driver_power": driver,
        "seed": 42, "precision": "float32", "tf32": False, "amp": False,
        "layers": 2, "hidden": 128, "attention_heads": 4, "ff": 256,
        "dropout": 0.1, "parameters": int(sum(p.numel() for p in model.parameters())),
        "optimizer": "AdamW", "lr": 3e-4, "batch_size": batch_size,
        "tokens": length, "prior_observations": 24, "target_observations": 8,
        "target_loss_positions": target_positions, "query_label_visible": False,
        "warmup_steps": warmup, "measured_steps": steps,
        "step_seconds": durations, "mean_step_seconds": mean,
        "median_step_seconds": median(durations),
        "p95_step_seconds": ordered[(95 * steps + 99) // 100 - 1],
        "timed_seconds": sum(durations), "total_seconds": perf_counter() - start_all,
        "peak_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
        "peak_reserved_bytes": int(torch.cuda.max_memory_reserved(device)),
        "three_seeds_10000_steps_compute_hours": mean * 30_000 / 3600,
        "finite_loss_and_weights": True,
        "scope": "Proxy dữ liệu giả preallocated; gồm forward/backward/optimizer/synchronize, "
                 "không gồm data loader, oracle, validation, checkpoint hoặc tích hợp LLM. "
                 "Không phải candidate, phép kiểm cơ chế hoặc cam kết thời gian train thật.",
    }


def main() -> None:
    """Chạy phép đo offline và ghi vào đường dẫn mới do người gọi chọn."""
    parser = argparse.ArgumentParser(description="Benchmark GPU dự kiến cho MT-BICL, không API")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Không ghi đè phép đo đã lưu; hãy chọn đường dẫn mới")
    result = benchmark()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"Benchmark hoàn tất: {result['mean_step_seconds']:.4f} giây/step; lưu {args.output}")


if __name__ == "__main__":
    main()
