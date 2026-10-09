"""Kiểm lịch OOS và nguồn PIT offline; không sinh tín hiệu hoặc nhãn lợi nhuận."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

import numpy as np
import pandas as pd

from core.execution_prices import (
    STOCK_SYMBOLS, build_verified_cycle_schedule, corporate_action_barriers,
    execution_prices_for_cycle, validate_raw_frame,
)
from core.historical_signals import digest, native_json
from core.prior_context import PriorContextAdapter
from core.regime_detector import WARMUP_ROWS

VERSION = "oos_coverage_v1"
ROOT = Path(__file__).resolve().parents[1]


def build_oos_calendar(frame: pd.DataFrame, events: list[dict[str, Any]],
                       vnindex: pd.DataFrame, *, start: str, end: str) -> list[dict[str, Any]]:
    """Xét mọi phiên VNINDEX; reason đầu tiên là nhóm loại trừ không trùng nhau.

    Giá tương lai chỉ dùng xác nhận khả năng thực thi. Lịch ứng viên hằng ngày
    có thể chồng lấn; đây chưa phải lịch benchmark cách ít nhất ba phiên.
    """
    validate_raw_frame(frame)
    validate_raw_frame(vnindex)
    if pd.Timestamp(start) > pd.Timestamp(end):
        raise ValueError("Phạm vi coverage đảo ngày")
    reference = pd.DatetimeIndex(vnindex.Datetime)
    dates = pd.DatetimeIndex(frame.Datetime)
    positions = np.flatnonzero((reference >= pd.Timestamp(start)) & (reference <= pd.Timestamp(end)))
    if not len(positions):
        raise ValueError("Không có phiên VNINDEX trong phạm vi coverage")
    cutoffs = reference[positions]
    padded = np.concatenate([reference.to_numpy(), np.full(3, np.datetime64("NaT"), dtype="datetime64[ns]")])
    holding = padded[positions[:, None] + np.arange(1, 4)]
    entries, exits = pd.DatetimeIndex(holding[:, 0]), pd.DatetimeIndex(holding[:, 2])
    stock_positions = dates.get_indexer(cutoffs)
    execution_positions = dates.get_indexer(holding.ravel()).reshape(-1, 3)
    present = (execution_positions >= 0).all(axis=1)
    aligned = present & (execution_positions == stock_positions[:, None] + np.arange(1, 4)).all(axis=1)
    volumes = frame.Volume.to_numpy()
    no_volume = (volumes[np.maximum(execution_positions, 0)] <= 0).any(axis=1) & present
    barriers = corporate_action_barriers(frame, events).to_numpy()
    rights = (np.searchsorted(barriers, exits.to_numpy(), side="right")
              - np.searchsorted(barriers, entries.to_numpy(), side="right")) > 0
    warmup = dates.searchsorted(cutoffs, side="right")
    checks = {
        "CUTOFF_NOT_IN_STOCK": stock_positions < 0,
        "WARMUP_600": warmup < 600,
        "VNINDEX_WARMUP": positions + 1 < WARMUP_ROWS,
        "EXIT_OUTSIDE_CALENDAR": exits.isna(),
        "CROSS_YEAR_EXECUTION": ~exits.isna() & (cutoffs.year != exits.year),
        "EXECUTION_CALENDAR_MISMATCH": ~aligned,
        "NO_MATCHED_VOLUME_AT_EXECUTION": no_volume,
        "CORPORATE_ACTION_DURING_HOLDING": rights & present,
    }
    legacy = build_verified_cycle_schedule(frame, events)
    legacy_dates = set(legacy.as_of_date.dt.strftime("%Y-%m-%d"))
    rows = []
    # Lặp các điểm kiểm định đã vector hóa, không lặp từng dòng DataFrame.
    for index, cutoff in enumerate(cutoffs.strftime("%Y-%m-%d")):
        reasons = [reason for reason, mask in checks.items() if bool(mask[index])]
        rows.append({"as_of_date": cutoff,
            "entry_date": None if pd.isna(entries[index]) else entries[index].strftime("%Y-%m-%d"),
            "exit_date": None if pd.isna(exits[index]) else exits[index].strftime("%Y-%m-%d"),
            "year": int(cutoffs[index].year), "quarter": f"{cutoffs[index].year}Q{cutoffs[index].quarter}",
            "stock_warmup_rows": int(warmup[index]), "vnindex_warmup_rows": int(positions[index] + 1),
            "eligible": not reasons, "reason": reasons[0] if reasons else None,
            "reasons": reasons, "legacy_step3": cutoff in legacy_dates,
            "pit_ready": not any(bool(checks[key][index]) for key in
                ("CUTOFF_NOT_IN_STOCK", "WARMUP_600", "VNINDEX_WARMUP"))})
    return rows


def _counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Đối soát mẫu số; số reason phụ có thể chồng lấn và không cộng thành tổng."""
    eligible = [row for row in rows if row["eligible"]]
    return {"candidates": len(rows), "eligible": len(eligible), "excluded": len(rows) - len(eligible),
        "excluded_by_primary_reason": dict(sorted(Counter(row["reason"] for row in rows if not row["eligible"]).items())),
        "legacy_step3_candidates": sum(row["legacy_step3"] for row in rows),
        "legacy_step3_eligible": sum(row["legacy_step3"] for row in eligible),
        "pit_verified": sum(row["proof_sha256"] is not None for row in rows),
        "eligible_news_reliable": sum(row["news"]["is_reliable"] for row in eligible),
        "eligible_news_neutral": sum(not row["news"]["is_reliable"] for row in eligible)}


def audit_oos_coverage(adapter: PriorContextAdapter, vnindex: pd.DataFrame, *,
                       start: str = "2023-01-01", end: str = "2024-12-31",
                       progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Kiểm mọi cutoff có đủ PIT, kể cả chu kỳ bị loại vì giá thực thi.

    Lỗi checksum/model/leakage phải dừng audit; không biến lỗi nguồn thành
    một ngày bị loại để tiếp tục bằng dữ liệu chưa được xác minh.
    """
    stocks = {}
    for symbol in STOCK_SYMBOLS:
        frame, events = adapter.execution_data(symbol)
        rows = build_oos_calendar(frame, events, vnindex, start=start, end=end)
        for index, row in enumerate(rows):
            row.update(regime="UNAVAILABLE", regime_state_sha256=None, proof_sha256=None, news=None)
            if row.pop("pit_ready"):
                point = adapter.prepare(symbol, row["as_of_date"])
                proof, state = point.source_provenance, point.market_regime
                if (state["as_of_date"] != row["as_of_date"] or state["feature_end_date"] != row["as_of_date"]
                        or proof["regime"]["state_sha256"] != digest(state)):
                    raise ValueError("Trạng thái regime không khớp cutoff/proof PIT")
                row.update(regime=state["regime_name"], regime_state_sha256=digest(state),
                    proof_sha256=digest(proof), news={key: proof["news"][key] for key in
                        ("input_count", "visible_count", "excluded_counts", "is_reliable", "neutral_reason")})
            if row["eligible"]:
                if row["proof_sha256"] is None:
                    raise ValueError("Ngày đủ điều kiện chưa được adapter xác minh")
                execution_prices_for_cycle(frame, events, row["as_of_date"], row["entry_date"], row["exit_date"])
            if progress and (index + 1) % 100 == 0:
                progress(f"{symbol}: đã kiểm PIT {index + 1}/{len(rows)} ngày")
        groups = {field: {value: _counts([row for row in rows if str(row[field]) == value])
                         for value in sorted({str(row[field]) for row in rows})}
                  for field in ("year", "quarter", "regime")}
        stocks[symbol] = {"summary": _counts(rows), "groups": groups, "calendar": rows}
        if progress:
            progress(f"{symbol}: {stocks[symbol]['summary']['eligible']}/{len(rows)} ngày đủ điều kiện")
    return native_json({"version": VERSION, "status": "PASS", "scope": {"start": start, "end": end,
        "candidate_calendar": "ALL_VNINDEX_SESSIONS", "selection": "ELIGIBILITY_ONLY_NO_OUTCOME",
        "execution": "OPEN_T_PLUS_1_CLOSE_T_PLUS_3_SAME_YEAR", "warmup_stock": 600,
        "warmup_vnindex": WARMUP_ROWS, "news_policy": "STRICT_PIT_NEUTRAL_IF_INSUFFICIENT",
        "is_execution_plan": False}, "sources": adapter.source_hashes, "stocks": stocks,
        "summary": _counts([row for stock in stocks.values() for row in stock["calendar"]])})


def audit_locked_oos(*, root: Path = ROOT, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Tái dùng gate OOS/model/tin đã khóa; không prepare/refit/tải thêm nguồn."""
    from core.pilot_readiness import INPUT_DIR, build_adapter, sha_file, verify_inputs
    plan = verify_inputs(root)
    adapter = build_adapter(plan, root)
    vnindex = pd.read_csv(root / plan["model"]["source_path"], parse_dates=["Datetime"])
    result = audit_oos_coverage(adapter, vnindex, progress=progress)
    relative = f"{INPUT_DIR}/plan.json"
    result["sources"][relative] = sha_file(root / relative)
    result["model_scope"] = plan["model"]["scope"]
    result["splits"] = {"2023": "development_exploratory", "2024": "holdout_calendar_only"}
    result["code_sha256"] = {path: sha_file(ROOT / path) for path in (
        "core/oos_coverage.py", "core/prior_context.py", "core/execution_prices.py",
        "core/regime_detector.py", "core/historical_signals.py", "core/pilot_readiness.py",
        "scripts/verify_execution_price_gate.py")}
    return result


def save_coverage(payload: dict[str, Any], destination: Path, *, root: Path = ROOT) -> None:
    """Ghi một artifact runtime nguyên tử; file khác nội dung không được ghi đè."""
    path = destination.resolve()
    directory = (root / "outputs/bayesian_benchmark").resolve()
    if not path.is_relative_to(directory) or path.suffix != ".json":
        raise ValueError("Coverage phải nằm trong outputs/bayesian_benchmark và có đuôi .json")
    for relative, expected in payload["sources"].items():
        source = (root / relative).resolve()
        if not source.is_relative_to(root.resolve()) or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Nguồn thay đổi trước khi lưu coverage: {relative}")
    envelope = {"payload": payload, "sha256": digest(payload)}
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != envelope:
            raise ValueError("Coverage đã tồn tại với identity khác; chọn đường dẫn runtime mới")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(envelope, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Hard link tạo đích độc quyền, không có khoảng ghi đè giữa exists/link.
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
