"""Schema đánh giá net/gross tường minh, không dùng alias legacy để suy giá cutoff."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

VERSION = "net_cycle_v1"


def target_fields(frame: pd.DataFrame, entry_index: int, horizon: int,
                  fee: float = .0025, slippage: float = .001) -> dict[str, Any]:
    """Tạo outcome sau inference từ đúng frame, không đưa record này vào graph state.

    entry_index=e là boundary exclusive, decision=e-1, exit=e+L-1. Return
    là tỷ lệ thập phân (1 = 100%); zero net/gross đều DOWN. Không rút ngắn horizon thiếu giá.
    """
    if any(not isinstance(v, (int, np.integer)) or isinstance(v, (bool, np.bool_)) or v < 1
           for v in (entry_index, horizon)):
        raise ValueError("Boundary/horizon phải là integer dương")
    entry_index, horizon = int(entry_index), int(horizon)
    target = entry_index + horizon - 1
    if target >= len(frame):
        raise ValueError("Thiếu toàn bộ target horizon")
    decision, entry, exit_price = (float(frame["Close"].iloc[entry_index - 1]),
                                  float(frame["Open"].iloc[entry_index]), float(frame["Close"].iloc[target]))
    if any(not np.isfinite(v) or v <= 0 for v in (decision, entry, exit_price)):
        raise ValueError("Giá decision/entry/exit phải dương hữu hạn")
    fee, slippage = float(fee), float(slippage)
    if any(not np.isfinite(v) or v < 0 for v in (fee, slippage)) or fee + slippage >= 1:
        raise ValueError("Chi phí không hợp lệ")
    gross = exit_price / entry - 1
    net = exit_price / entry * ((1 - slippage) * (1 - fee)) / ((1 + slippage) * (1 + fee)) - 1
    return {"decision_close": decision, "entry_open": entry, "exit_close": exit_price,
            "gross_return": float(gross), "net_return": float(net),
            "label_net": "UP" if net > 0 else "DOWN", "label_gross": "UP" if gross > 0 else "DOWN",
            "decision_bar_index": entry_index - 1, "target_horizon_bars": horizon,
            "label_fee_each_side": fee, "label_slippage_each_side": slippage,
            "label_contract_version": VERSION}


def require_prompt_costs(config: dict[str, Any]) -> None:
    """Chặn gọi LLM khi phí label khác hợp đồng 0,25%/0,10% cố định trong prompt.

    Cost sensitivities offline vẫn được phép qua compute_account_metrics.
    Không sửa prompt đã khóa hoặc gọi lại API để cập nhật kết quả lịch sử.
    """
    if float(config.get("tx_cost", .0025)) != .0025 or float(config.get("slippage", .001)) != .001:
        raise ValueError("Phí label khác prompt cố định; dùng sensitivity offline hoặc version prompt/protocol riêng")


def validate_target_record(record: dict[str, Any]) -> None:
    """Từ chối canonical metadata tự mâu thuẫn, không nâng cấp record legacy.

    Kiểm tra số học/schema không xác nhận snapshot/request provenance. Chi phí
    thực thi sensitivity không được dùng để thay label_fee đã khóa ở record.
    """
    if record.get("label_contract_version", "legacy_unverified") == "legacy_unverified":
        return
    if record.get("label_contract_version") != VERSION:
        raise ValueError("Phiên bản label contract không được hỗ trợ")
    required = ("decision_close", "entry_open", "exit_close", "gross_return", "net_return", "label_net", "label_gross",
                "decision_bar_index", "target_horizon_bars", "label_fee_each_side", "label_slippage_each_side")
    if any(record.get(k) is None for k in required):
        raise ValueError("Canonical label record thiếu field bắt buộc")
    d, horizon = record["decision_bar_index"], record["target_horizon_bars"]
    if type(d) is not int or type(horizon) is not int or d < 0 or horizon < 1:
        raise ValueError("Canonical indices không hợp lệ")
    values = [float(record[k]) for k in ("decision_close", "entry_open", "exit_close")]
    if any(not np.isfinite(v) or v <= 0 for v in values):
        raise ValueError("Canonical prices không hợp lệ")
    fee, slip = float(record["label_fee_each_side"]), float(record["label_slippage_each_side"])
    if any(not np.isfinite(v) or v < 0 for v in (fee, slip)) or fee + slip >= 1:
        raise ValueError("Canonical label costs không hợp lệ")
    gross = values[2] / values[1] - 1
    net = values[2] / values[1] * ((1 - slip) * (1 - fee)) / ((1 + slip) * (1 + fee)) - 1
    if not np.isclose(float(record["gross_return"]), gross, atol=1e-12, rtol=0) or not np.isclose(float(record["net_return"]), net, atol=1e-12, rtol=0):
        raise ValueError("Canonical returns không khớp giá/phí đã khóa")
    if record["label_net"] != ("UP" if net > 0 else "DOWN") or record["label_gross"] != ("UP" if gross > 0 else "DOWN"):
        raise ValueError("Canonical label không khớp return")
    if "actual_direction" in record and record["actual_direction"] != record["label_net"]:
        raise ValueError("Alias actual_direction không khớp label_net")
