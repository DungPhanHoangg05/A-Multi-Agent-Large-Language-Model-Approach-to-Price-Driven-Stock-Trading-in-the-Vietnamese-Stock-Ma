"""Nạp model MT-BICL đã pin hash và suy luận thuần, tách khỏi dữ liệu đánh giá."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any

import torch

from core.mt_bicl_bank import content_hash
from core.mt_bicl_contracts import validate_context
from core.mt_bicl_distillation import tensor_hash
from core.mt_bicl_evaluation import probabilities
from core.mt_bicl_oracle import numeric_input
from core.mt_bicl_student import DistilledStudent, collate_packets, pack_input
from core.mt_bicl_teacher import BetaBernoulliTeacher


class StudentAdapter:
    """Giữ model/teacher frozen, không có optimizer hoặc fallback xác suất."""

    def __init__(self, root: Path, manifest: Path | None = None) -> None:
        """Kiểm envelope, namespace và byte từng component trước khi nạp tensor."""
        root = root.resolve()
        path = manifest or root / "docs/plan/week11/mt_bicl_model.json"
        raw_manifest = path.read_bytes()
        if manifest is None:
            anchored = subprocess.check_output(
                ["git", "show", "HEAD:docs/plan/week11/mt_bicl_model.json"], cwd=root
            )
            if raw_manifest != anchored:
                raise ValueError("Model manifest MT-BICL khác bản đã neo Git")
        record = json.loads(raw_manifest)
        payload = record["payload"]
        if content_hash(payload) != record["sha256"]:
            raise ValueError("Model manifest MT-BICL sai checksum")
        components: dict[str, Path] = {}
        for directory, entries in payload["artifact_trees"].items():
            for name, expected in entries.items():
                candidate = root / directory / name
                component = candidate.resolve()
                if not component.is_relative_to(root) or candidate.is_symlink() or name in components:
                    raise ValueError("Đường dẫn component MT-BICL không hợp lệ")
                raw = component.read_bytes()
                if len(raw) != expected["bytes"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
                    raise ValueError("Component MT-BICL khác manifest")
                components[name] = component
        if set(components) != {"candidate.pt", "teacher.json"}:
            raise ValueError("Model MT-BICL thiếu hoặc thừa component")
        teacher = json.loads(components["teacher.json"].read_bytes())
        if "payload" in teacher:
            if content_hash(teacher["payload"]) != teacher["sha256"]:
                raise ValueError("Teacher MT-BICL sai checksum")
            teacher = teacher["payload"]
        self.teacher = BetaBernoulliTeacher(teacher["pi"])
        checkpoint = torch.load(components["candidate.pt"], map_location="cpu", weights_only=True)
        self.device = torch.device("cpu")
        self.model = DistilledStudent().to(self.device)
        self.model.load_state_dict(checkpoint["model"], strict=True)
        self.model.eval().requires_grad_(False)
        self.fingerprint = tensor_hash(self.model)
        if self.fingerprint != checkpoint["model_tensor_sha256"]:
            raise ValueError("Student tensor khác manifest export")

    def probability(self, episode: dict[str, Any]) -> float:
        """Kiểm membership/PIT trước chiếu D/C/x, giữ query outcome ngoài tensor."""
        validate_context(episode)
        return self.predict_input(numeric_input(episode))

    def predict_input(self, data: dict[str, Any]) -> float:
        """Chỉ forward tại query; kiểm fingerprint để phát hiện cập nhật weights."""
        batch = collate_packets([pack_input(data)], self.device)
        with torch.inference_mode():
            logits = self.model(batch["values"], batch["roles"], batch["slots"], batch["padding"])
            value = float(logits[0, int(batch["queries"][0])].item())
        probability = float(probabilities([value])[0][0])
        if not math.isfinite(probability) or not 0 <= probability <= 1 or tensor_hash(self.model) != self.fingerprint:
            raise ValueError("Student probability hoặc weights không hợp lệ")
        return probability
