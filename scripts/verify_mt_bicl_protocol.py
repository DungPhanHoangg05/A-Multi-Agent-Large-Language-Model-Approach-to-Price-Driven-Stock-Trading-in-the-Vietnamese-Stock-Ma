"""Kiểm cấu hình và schema MT-BICL hiện hành, giữ quyền inference ở release riêng."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mt_bicl_bank import PROTOCOL_SHA256, read_protocol
from core.mt_bicl_contracts import wire_schema


def verify(root: Path) -> dict[str, Any]:
    """Đối soát byte cấu hình và schema trước khi đọc model hoặc phát request."""
    protocol = read_protocol(root)
    wire_schema()
    if protocol["candidate"] != "MT_BICL" or any(protocol[key] for key in (
        "training_allowed", "teacher_fit_allowed", "decision_calls_allowed", "confirmation_allowed"
    )):
        raise ValueError("Cấu hình MT-BICL vượt phạm vi đặc tả")
    return {"status": "SPEC_VERIFIED", "candidate": "MT_BICL", "inference_released": False}


if __name__ == "__main__":
    print(json.dumps(verify(ROOT), ensure_ascii=False))
