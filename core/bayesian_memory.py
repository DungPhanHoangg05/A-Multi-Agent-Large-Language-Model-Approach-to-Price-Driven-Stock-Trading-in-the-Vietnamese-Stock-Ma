"""Kho chu kỳ lịch sử với xác thực schema, lịch phiên và kết quả kinh tế."""

from __future__ import annotations

import copy
import json
import math
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core.execution_prices import execution_prices_for_cycle, load_verified_execution_data

SIGNAL_KEYS = {"trend", "pattern", "alpha_consensus", "indicator_consensus", "sentiment"}
RECORD_KEYS = {"episode_id", "symbol", "as_of_date", "entry_date", "exit_date", "regime", "agent_signals", "outcome"}
OUTCOME_KEYS = {"actual_direction", "net_return_pct", "was_bull_trap", "result"}
REGIMES = {"BULL", "BEAR", "CHOPPY", "CONSOLIDATION"}
SYMBOLS = {"FPT", "VNM", "VCB", "MWG"}
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "execution_prices"
ExecutionLoader = Callable[[str], tuple[pd.DataFrame, list[dict[str, Any]]]]


def copy_historical_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sao chép sâu schema phẳng; dữ liệu sai/mở rộng dùng deepcopy, không ép kiểu.

    Record hợp lệ chỉ có hai dict con với lá bất biến. Sao chép cả ba dict giữ
    mọi mức dữ liệu khả biến độc lập, tránh dispatch/memo cho từng scalar.
    Hàm không thay validator; nhánh dự phòng giữ nguyên lỗi để caller từ chối.
    """
    scalar_types = (str, int, float, bool, type(None))
    result: list[dict[str, Any]] = []
    for record in records:
        if (type(record) is dict and record.keys() == RECORD_KEYS
                and type(record['agent_signals']) is dict and record['agent_signals'].keys() == SIGNAL_KEYS
                and type(record['outcome']) is dict and record['outcome'].keys() == OUTCOME_KEYS
                and all(type(value) in scalar_types for key, value in record.items()
                        if key not in ('agent_signals', 'outcome'))
                and all(type(value) in scalar_types for value in record['agent_signals'].values())
                and all(type(value) in scalar_types for value in record['outcome'].values())):
            result.append({**record, 'agent_signals': dict(record['agent_signals']), 'outcome': dict(record['outcome'])})
        else:
            result.append(copy.deepcopy(record))
    return result


def iso_date(value: Any) -> str:
    """Chấp nhận đúng ngày ISO bằng chuỗi Python gốc."""
    if type(value) is not str:
        raise ValueError("Ngày phải là chuỗi ISO Python gốc")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Ngày ISO không hợp lệ") from exc
    if parsed.isoformat() != value:
        raise ValueError("Ngày phải có định dạng YYYY-MM-DD")
    return value


def exact_object(value: Any, keys: set[str]) -> None:
    """Từ chối trường thiếu/thừa và kiểu không phải dictionary gốc."""
    if type(value) is not dict or set(value) != keys:
        raise ValueError("Các trường không khớp schema")


def validate_signals(signals: Any) -> None:
    """Yêu cầu đủ năm tín hiệu có nội dung, không tự điền tín hiệu thiếu."""
    exact_object(signals, SIGNAL_KEYS)
    if any(type(value) is not str or not value.strip() for value in signals.values()):
        raise ValueError("Tín hiệu agent phải là chuỗi không rỗng")


def is_bullish(signal: str) -> bool:
    """Nhận diện nhãn tăng chuẩn; không suy đoán từ từ khóa trong diễn giải."""
    return signal.strip().upper() in {"BULLISH", "BULL", "UP", "TĂNG", "TĂNG GIÁ"}


def validate_historical_task_record(
    record: dict[str, Any], frame: pd.DataFrame, events: list[dict[str, Any]]
) -> None:
    """Kiểm schema W1 và đối chiếu nhãn với Open(t+1)/Close(t+3) thực thi."""
    exact_object(record, RECORD_KEYS)
    if type(record["episode_id"]) is not str or not record["episode_id"].strip():
        raise ValueError("episode_id phải có nội dung")
    for key, allowed in (("symbol", SYMBOLS), ("regime", REGIMES)):
        if type(record[key]) is not str or record[key] not in allowed:
            raise ValueError(f"{key} không hợp lệ")
    dates = [iso_date(record[key]) for key in ("as_of_date", "entry_date", "exit_date")]
    if not dates[0] < dates[1] < dates[2]:
        raise ValueError("Ngày quyết định, vào và thoát phải tăng nghiêm ngặt")
    validate_signals(record["agent_signals"])
    outcome = record["outcome"]
    exact_object(outcome, OUTCOME_KEYS)
    net = outcome["net_return_pct"]
    if type(net) not in (float, int) or not math.isfinite(net):
        raise ValueError("Lợi nhuận phải là số Python gốc hữu hạn")
    if type(outcome["was_bull_trap"]) is not bool:
        raise ValueError("was_bull_trap phải là bool Python gốc")
    if any(type(outcome[key]) is not str for key in ("actual_direction", "result")):
        raise ValueError("Hướng và kết quả phải là chuỗi Python gốc")
    entry, exit_close = execution_prices_for_cycle(frame, events, *dates)
    expected = float(compute_round_trip_net_return(entry, exit_close) * 100.0)
    if not math.isclose(net, expected, rel_tol=0.0, abs_tol=1e-8):
        raise ValueError("Nhãn không khớp lợi nhuận ròng của engine")
    positive = expected > 0.0
    if outcome["actual_direction"] != ("UP" if positive else "DOWN") or outcome["result"] != (
        "WIN_IF_LONG" if positive else "LOSS_IF_LONG"
    ):
        raise ValueError("Hướng và kết quả không khớp dấu lợi nhuận ròng")
    bullish = any(is_bullish(record["agent_signals"][key]) for key in ("trend", "pattern"))
    if outcome["was_bull_trap"] != (bullish and not positive):
        raise ValueError("Nhãn bull trap không khớp tín hiệu và lợi nhuận")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Không cho JSON chứa hai giá trị cho cùng một trường."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON có khóa trùng")
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    """Đọc JSON nghiêm ngặt, từ chối khóa trùng và NaN/Infinity."""
    def reject_constant(value: str) -> None:
        raise ValueError(f"JSON chứa số không hữu hạn: {value}")

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object,
                      parse_constant=reject_constant)


def atomic_write_json(path: Path, payload: Any) -> None:
    """Ghi cùng thư mục và thay thế nguyên tử sau khi flush/fsync thành công."""
    content = json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


class HistoricalMemory:
    """Nạp/lưu danh sách bản ghi; chỉ trả chu kỳ đã thoát trước ngày truy vấn."""

    def __init__(self, execution_loader: ExecutionLoader | None = None) -> None:
        self._execution_loader = execution_loader or (
            lambda symbol: load_verified_execution_data(DEFAULT_DATA_DIR, symbol)
        )
        self._records: list[dict[str, Any]] = []

    @property
    def records(self) -> list[dict[str, Any]]:
        """Trả bản sao để người gọi không sửa được kho đã xác thực."""
        return copy.deepcopy(self._records)

    def _validate_all(self, records: Any) -> None:
        if type(records) is not list:
            raise ValueError("Kho lịch sử phải là danh sách JSON")
        ids: set[str] = set()
        cycles: set[tuple[str, str]] = set()
        data: dict[str, tuple[pd.DataFrame, list[dict[str, Any]]]] = {}
        for record in records:
            exact_object(record, RECORD_KEYS)
            symbol = record["symbol"]
            if type(symbol) is not str or symbol not in SYMBOLS:
                raise ValueError("Mã cổ phiếu không hợp lệ")
            if symbol not in data:
                data[symbol] = self._execution_loader(symbol)
            validate_historical_task_record(record, *data[symbol])
            cycle = (symbol, record["as_of_date"])
            if record["episode_id"] in ids or cycle in cycles:
                raise ValueError("ID hoặc điểm quyết định bị trùng")
            ids.add(record["episode_id"])
            cycles.add(cycle)
        for symbol in data:
            ordered = sorted((r for r in records if r["symbol"] == symbol), key=lambda r: r["entry_date"])
            if any(left["exit_date"] >= right["entry_date"] for left, right in zip(ordered, ordered[1:])):
                raise ValueError("Các khoảng nắm giữ cùng mã bị chồng lấn")

    def add(self, record: dict[str, Any]) -> None:
        """Thêm bản ghi sau xác thực; lỗi không thay đổi kho đang dùng."""
        candidate = self.records + [copy.deepcopy(record)]
        self._validate_all(candidate)
        self._records = candidate

    def load(self, path: str | Path) -> None:
        """Nạp toàn bộ hoặc từ chối toàn bộ, không bỏ qua record lỗi."""
        candidate = read_json(Path(path))
        self._validate_all(candidate)
        self._records = copy.deepcopy(candidate)

    def save(self, path: str | Path) -> None:
        """Xác minh lại giá và bản ghi trước khi thay thế file nguyên tử."""
        self._validate_all(self._records)
        atomic_write_json(Path(path), self._records)

    def eligible(self, as_of_date: str, symbol: str | None = None) -> list[dict[str, Any]]:
        """Lọc exit_date < cutoff; không trả chu kỳ đang nắm giữ hoặc tương lai."""
        cutoff = iso_date(as_of_date)
        if symbol is not None and symbol not in SYMBOLS:
            raise ValueError("Mã truy vấn không hợp lệ")
        result = [r for r in self._records if r["exit_date"] < cutoff
                  and (symbol is None or r["symbol"] == symbol)]
        if any(r["exit_date"] >= cutoff for r in result):
            raise ValueError("Kho trả chu kỳ chưa tất toán trước cutoff")
        return copy_historical_records(result)
