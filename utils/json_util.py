"""Chuyển dữ liệu runtime sang các kiểu JSON chuẩn của Python."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
import math
from pathlib import Path
from typing import Any


def to_json_compatible(value: Any) -> Any:
    """
    Chuẩn hóa đệ quy payload trước khi trả qua Flask ``jsonify``.

    NumPy/Pandas thường tạo scalar như ``numpy.bool_`` hoặc ``numpy.int64``.
    Chúng trông giống kiểu Python khi log nhưng không được ``json`` hỗ trợ.
    Hàm này giữ nguyên cấu trúc payload và đổi các scalar/container phổ biến
    thành ``dict``, ``list``, ``str``, ``bool``, ``int``, ``float`` hoặc
    ``None`` thuần Python.
    """

    # Dùng so sánh kiểu chính xác: ``numpy.float64`` là subclass của ``float``
    # trên một số phiên bản NumPy nhưng vẫn không phải scalar JSON thuần.
    if value is None or type(value) in (str, bool, int):
        return value

    if type(value) is float:
        return value if math.isfinite(value) else None

    if isinstance(value, Enum):
        return to_json_compatible(value.value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    if is_dataclass(value) and not isinstance(value, type):
        return to_json_compatible(asdict(value))

    if isinstance(value, dict):
        return {
            str(to_json_compatible(key)): to_json_compatible(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json_compatible(item) for item in value]

    # NumPy scalar (np.bool_, np.integer, np.floating, ...) và một số scalar
    # Pandas cung cấp ``item()`` để trả về kiểu Python tương ứng.
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            scalar = item_method()
        except (TypeError, ValueError):
            scalar = value
        if scalar is not value:
            return to_json_compatible(scalar)

    # ndarray, Series và Index cung cấp ``tolist()``.
    tolist_method = getattr(value, "tolist", None)
    if callable(tolist_method):
        try:
            return to_json_compatible(tolist_method())
        except (TypeError, ValueError):
            pass

    # Pydantic v2/v1 models đôi khi đi qua ranh giới API trong lúc debug.
    for method_name in ("model_dump", "dict"):
        dump_method = getattr(value, method_name, None)
        if callable(dump_method):
            try:
                return to_json_compatible(dump_method())
            except (TypeError, ValueError):
                pass

    # Payload giao diện cần luôn trả được kết quả. Đối tượng không thuộc hợp
    # đồng JSON được biểu diễn bằng chuỗi thay vì làm toàn endpoint trả HTTP 500.
    return str(value)
