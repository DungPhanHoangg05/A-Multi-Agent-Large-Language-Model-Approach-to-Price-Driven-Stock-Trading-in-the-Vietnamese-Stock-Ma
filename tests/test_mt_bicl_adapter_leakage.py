"""Kiểm loader model hiện hành và ranh giới query khi gọi entrypoint MT-BICL."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import torch

from core.mt_bicl_adapter import StudentAdapter
from core.mt_bicl_bank import content_hash
from core.mt_bicl_distillation import tensor_hash
from core.mt_bicl_oracle import numeric_input
from core.mt_bicl_student import DistilledStudent
from mt_bicl_support import episode


class AdapterTests(unittest.TestCase):
    """Weights fixture ngẫu nhiên chỉ dùng kiểm hợp đồng, không là model thị trường."""

    def test_pinned_forward_and_query_poison(self) -> None:
        """Forward giữ weights, query y bị từ chối và sai hash phải dừng."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = DistilledStudent().eval()
            folder = root / "model"
            folder.mkdir()
            torch.save({"model": model.state_dict(), "model_tensor_sha256": tensor_hash(model)}, folder / "candidate.pt")
            (folder / "teacher.json").write_text(json.dumps({"pi": [1/16]*16}), encoding="utf-8")
            entries = {}
            for path in folder.iterdir():
                raw = path.read_bytes()
                entries[path.name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            payload = {"artifact_trees": {"model": entries}}
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"payload": payload, "sha256": content_hash(payload)}), encoding="utf-8")
            adapter = StudentAdapter(root, manifest)
            original = episode()
            before = adapter.fingerprint
            self.assertGreaterEqual(adapter.probability(original), 0.)
            self.assertEqual(tensor_hash(adapter.model), before)
            poisoned = numeric_input(original)
            poisoned["query"]["y"] = 1
            with self.assertRaises(ValueError):
                adapter.predict_input(poisoned)
            poisoned = deepcopy(original)
            poisoned["query"]["query_y"] = 1
            with self.assertRaises(ValueError):
                adapter.probability(poisoned)
            (folder / "candidate.pt").write_bytes(b"wrong")
            with self.assertRaises(ValueError):
                StudentAdapter(root, manifest)

    def test_missing_assets_stop_without_prediction(self) -> None:
        """Không có asset không tạo xác suất thay thế hoặc tự train."""
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileNotFoundError):
                StudentAdapter(Path(temporary))


if __name__ == "__main__":
    unittest.main()
