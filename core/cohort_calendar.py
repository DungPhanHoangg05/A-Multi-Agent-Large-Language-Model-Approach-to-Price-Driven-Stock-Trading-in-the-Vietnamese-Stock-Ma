"""Thiết kế lịch development/holdout/smoke theo ngày và eligibility, không outcome."""

from __future__ import annotations

from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.bayesian_memory import REGIMES, iso_date, read_json
from core.execution_prices import STOCK_SYMBOLS, execution_prices_for_cycle
from core.historical_signals import digest, native_json
from core.oos_coverage import VERSION as COVERAGE_VERSION, build_oos_calendar, save_coverage
from core.prior_config import copy_prior_json
from core.prior_run_lock import safe_path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "cohort_calendar_v1"
SPLITS = {2023: "development_2023", 2024: "holdout_2024"}
ROW_KEYS = {"as_of_date", "entry_date", "exit_date", "year", "quarter", "stock_warmup_rows",
    "vnindex_warmup_rows", "eligible", "reason", "reasons", "legacy_step3", "regime",
    "regime_state_sha256", "proof_sha256", "news"}


def _envelope(path: Path) -> dict[str, Any]:
    """Đọc JSON strict và checksum; không đọc kết quả Decision hoặc nhãn kinh tế."""
    envelope = copy_prior_json(read_json(path))
    if (type(envelope) is not dict or set(envelope) != {"payload", "sha256"}
            or digest(envelope["payload"]) != envelope["sha256"]):
        raise ValueError("Envelope lịch/coverage không hợp lệ")
    return envelope["payload"]


def _sha(path: Path) -> str:
    """Băm byte nguồn để phát hiện thay đổi mà không diễn giải nội dung outcome."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_files(files: dict[str, str], root: Path) -> None:
    """Kiểm containment/checksum và chặn credential trước lần đọc đầu tiên."""
    for relative, expected in files.items():
        path = safe_path(root, relative)
        if path.name.startswith(".env") or _sha(path) != expected:
            raise ValueError(f"Nguồn lịch thay đổi hoặc không được phép: {relative}")


def _read_locked_coverage(relative: str, root: Path) -> tuple[dict[str, Any], str]:
    """Ghim byte trước khi parse; đổi nguồn giữa đọc/băm phải dừng ngay."""
    path = safe_path(root, relative)
    if path.name.startswith(".env"):
        raise ValueError("Không dùng credential làm coverage")
    checksum = _sha(path)
    coverage = _envelope(path)
    _verify_files({**coverage["sources"], **coverage["code_sha256"], relative: checksum}, root)
    return coverage, checksum


def _rows(coverage: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Kiểm schema ngày/eligibility; regime và tin chỉ phục vụ thống kê sau chọn."""
    if (coverage.get("version") != COVERAGE_VERSION or coverage.get("status") != "PASS"
            or coverage["scope"]["start"] != "2023-01-01" or coverage["scope"]["end"] != "2024-12-31"
            or coverage["scope"]["is_execution_plan"] is not False
            or set(coverage["stocks"]) != set(STOCK_SYMBOLS)):
        raise ValueError("Lịch cần coverage bốn mã 2023–2024 đã PASS")
    result = {}
    reference = None
    for symbol in STOCK_SYMBOLS:
        rows = coverage["stocks"][symbol]["calendar"]
        if type(rows) is not list or not rows:
            raise ValueError("Coverage thiếu phiên ứng viên")
        for row in rows:
            if type(row) is not dict or set(row) != ROW_KEYS:
                raise ValueError("Schema phiên coverage sai hoặc có outcome query")
            cutoff = iso_date(row["as_of_date"])
            stamp = pd.Timestamp(cutoff)
            if (stamp.year not in SPLITS or type(row["eligible"]) is not bool
                    or row["year"] != stamp.year or row["quarter"] != f"{stamp.year}Q{stamp.quarter}"):
                raise ValueError("Phiên coverage khác năm/quý đã khóa")
            if row["eligible"] and (row["reason"] is not None or row["reasons"]
                    or row["regime"] not in REGIMES or not row["proof_sha256"] or not row["regime_state_sha256"]
                    or row["stock_warmup_rows"] < 600 or row["vnindex_warmup_rows"] < 200):
                raise ValueError("Ngày đủ điều kiện thiếu proof/warm-up hoặc còn reason loại")
        dates = [row["as_of_date"] for row in rows]
        if dates != sorted(set(dates)) or reference is not None and dates != reference:
            raise ValueError("Lịch coverage trùng/đảo ngày hoặc khác lịch VNINDEX")
        reference = dates
        result[symbol] = rows
    positions = {day: index for index, day in enumerate(reference)}
    for rows in result.values():
        for row in rows:
            if row["eligible"]:
                position = positions[row["as_of_date"]]
                if (position + 3 >= len(reference) or row["entry_date"] != reference[position + 1]
                        or row["exit_date"] != reference[position + 3]
                        or row["exit_date"][:4] != row["as_of_date"][:4]):
                    raise ValueError("Chu kỳ vượt split hoặc sai entry t+1/exit t+3")
    return result


def _overlap(rows: list[dict[str, Any]], observed: list[dict[str, Any]]) -> np.ndarray:
    """Chặn mọi giao nhau giữa các phiên giữ lệnh; không dùng giá tại các phiên đó."""
    if not observed:
        return np.zeros(len(rows), dtype=bool)
    entry = np.array([r["entry_date"] for r in rows], dtype="datetime64[D]")
    exit_dates = np.array([r["exit_date"] for r in rows], dtype="datetime64[D]")
    old_entry = np.array([r["entry_date"] for r in observed], dtype="datetime64[D]")
    old_exit = np.array([r["exit_date"] for r in observed], dtype="datetime64[D]")
    return ((entry[:, None] <= old_exit) & (exit_dates[:, None] >= old_entry)).any(axis=1)


def design_calendar(coverage: dict[str, Any], pilot_cutoffs: dict[str, list[str]], *,
                    points_per_quarter: int = 4) -> dict[str, Any]:
    """Chọn đều theo thứ hạng ngày hợp lệ trên lưới ba phiên neo đầu từng năm.

    Eligibility và loại exposure được áp dụng trước chọn. Sau khi chọn, lỗi API
    giữ nguyên điểm trong mẫu số, không chọn ngày thay thế. Regime/tin không
    tham gia xếp hạng hoặc quyết định ngày smoke/mẫu chính.
    """
    if type(points_per_quarter) is not int or not 1 <= points_per_quarter <= 20:
        raise ValueError("Mục tiêu mỗi mã/quý phải là số nguyên từ 1 đến 20")
    rows_by_symbol = _rows(coverage)
    if (set(pilot_cutoffs) != set(STOCK_SYMBOLS)
            or any(type(days) is not list or days != sorted(set(days)) for days in pilot_cutoffs.values())):
        raise ValueError("Exposure pilot cần danh sách ngày tăng dần cho đủ bốn mã")
    cohorts = {split: {"symbol_cutoffs": {}, "by_symbol": {}} for split in SPLITS.values()}
    smoke, pilot, point_metadata = {}, {}, {}
    for symbol, rows in rows_by_symbol.items():
        by_date = {row["as_of_date"]: row for row in rows}
        observed = []
        for day in pilot_cutoffs[symbol]:
            if day not in by_date or not day.startswith("2023-") or not by_date[day]["eligible"]:
                raise ValueError("Ngày pilot ngoài development hoặc không khớp coverage")
            observed.append(by_date[day])
        pilot[symbol] = list(pilot_cutoffs[symbol])
        eligible = [row for row in rows if row["eligible"]]
        pilot_overlap = _overlap(eligible, observed)
        # Neo theo toàn bộ lịch ứng viên của năm, không đánh lại phase sau loại.
        grid = {year: {row["as_of_date"] for row in [r for r in rows if r["year"] == year][::3]}
                for year in SPLITS}
        reasons = {row["as_of_date"]: "INELIGIBLE_EXECUTION" for row in rows if not row["eligible"]}
        pool = []
        for row, overlaps in zip(eligible, pilot_overlap.tolist()):
            day = row["as_of_date"]
            reason = ("OBSERVED_PILOT_CUTOFF" if day in pilot_cutoffs[symbol] else
                      "PILOT_HOLDING_OVERLAP" if overlaps else
                      "OFF_STEP3_GRID" if day not in grid[row["year"]] else None)
            if reason:
                reasons[day] = reason
            else:
                pool.append(row)
        smoke_pool = [row for row in pool if row["year"] == 2023]
        if not smoke_pool:
            raise ValueError(f"Không còn ngày smoke riêng trong development cho {symbol}")
        smoke_row = smoke_pool[0]
        smoke[symbol] = [smoke_row["as_of_date"]]
        smoke_overlap = _overlap(pool, [smoke_row])
        available = []
        for row, overlaps in zip(pool, smoke_overlap.tolist()):
            day = row["as_of_date"]
            if day == smoke_row["as_of_date"]:
                reasons[day] = "SMOKE_CUTOFF"
            elif overlaps:
                reasons[day] = "SMOKE_HOLDING_OVERLAP"
            else:
                available.append(row)
        selected_all = [smoke_row]
        for year, split in SPLITS.items():
            quarter_stats, selected = {}, []
            for number in range(1, 5):
                quarter = f"{year}Q{number}"
                candidates = [row for row in available if row["quarter"] == quarter]
                count = min(points_per_quarter, len(candidates))
                # Lấy hai đầu và các thứ hạng cách đều; n=1 dùng điểm giữa.
                ranks = (np.array([(len(candidates) - 1) // 2]) if count == 1 else
                         np.linspace(0, len(candidates) - 1, count, dtype=int))
                chosen = [candidates[int(index)] for index in ranks]
                selected.extend(chosen)
                for row in candidates:
                    reasons[row["as_of_date"]] = "NOT_SELECTED_QUARTER_TARGET"
                for row in chosen:
                    reasons[row["as_of_date"]] = "SELECTED_MAIN"
                quarter_stats[quarter] = {"target": points_per_quarter, "available_grid": len(candidates),
                    "selected": count, "shortfall": points_per_quarter - count}
            cohorts[split]["symbol_cutoffs"][symbol] = [r["as_of_date"] for r in selected]
            cohorts[split]["by_symbol"][symbol] = {"quarters": quarter_stats,
                "selected": len(selected), "target": 4 * points_per_quarter,
                "shortfall": 4 * points_per_quarter - len(selected),
                "regime": {name: sum(r["regime"] == name for r in selected) for name in sorted(REGIMES)},
                "news_reliable": sum(bool(r["news"]["is_reliable"]) for r in selected),
                "disposition": dict(sorted(Counter(reasons[r["as_of_date"]] for r in rows if r["year"] == year).items()))}
            selected_all.extend(selected)
        for row in selected_all:
            point_metadata[f"{symbol}-{row['as_of_date']}"] = {key: row[key] for key in
                ("entry_date", "exit_date", "quarter", "regime", "proof_sha256", "regime_state_sha256")}
    return native_json({"version": VERSION, "status": "DRAFT_PENDING_QUOTA_AND_INPUT_LOCK",
        "is_execution_plan": False, "selection": {"version": "uniform_eligible_step3_v1",
            "points_per_symbol_quarter": points_per_quarter, "step_sessions": 3,
            "anchor": "FIRST_VNINDEX_SESSION_OF_EACH_YEAR", "smoke": "FIRST_ELIGIBLE_DEVELOPMENT_GRID_AFTER_PILOT",
            "pilot_exclusion": "SAME_SYMBOL_CUTOFF_AND_OVERLAPPING_HOLDING_SESSIONS",
            "sample": "UNIFORM_INTEGER_RANKS_ON_ELIGIBLE_GRID_PER_QUARTER",
            "replacement_after_failure": False, "selection_uses_outcome_or_regime_or_news": False},
        "observed_pilot": pilot, "smoke": {"split": "development_2023", "matrix": "smoke_v1", "symbol_cutoffs": smoke},
        "cohorts": cohorts, "points": point_metadata,
        "summary": {"target_main": 32 * points_per_quarter,
            "planned_main": sum(len(days) for group in cohorts.values() for days in group["symbol_cutoffs"].values()),
            "planned_smoke": 4, "observed_pilot": sum(map(len, pilot.values()))}})


def build_locked_calendar(coverage_path: Path, destination: Path, *, root: Path = ROOT,
                          points_per_quarter: int = 4) -> dict[str, Any]:
    """Kiểm nguồn/eligibility/proof đã khóa, thiết kế rồi lưu một JSON runtime.

    Chỉ kiểm inventory và checksum checkpoint pilot; không parse Decision,
    evaluation, kết quả hoặc lợi nhuận của pilot/holdout để chọn mẫu.
    """
    from core.pilot_readiness import INPUT_DIR, build_adapter, verify_inputs
    if (not destination.resolve().is_relative_to((root / "outputs/bayesian_benchmark").resolve())
            or destination.suffix != ".json" or destination.resolve() == coverage_path.resolve()):
        raise ValueError("Lịch phải là JSON runtime riêng, không ghi đè coverage hoặc nguồn")
    if type(points_per_quarter) is not int or not 1 <= points_per_quarter <= 20:
        raise ValueError("Mục tiêu mỗi mã/quý phải là số nguyên từ 1 đến 20")
    relative = coverage_path.resolve().relative_to(root.resolve()).as_posix()
    coverage, coverage_checksum = _read_locked_coverage(relative, root)
    with redirect_stdout(StringIO()):
        plan = verify_inputs(root)
        adapter = build_adapter(plan, root)
    if plan["symbol"] != "FPT":
        raise ValueError("Pilot đã khóa phải là FPT")
    pilot_dates = {symbol: list(plan["cutoffs"]) if symbol == "FPT" else [] for symbol in STOCK_SYMBOLS}
    points_dir = root / "outputs/pilot_fpt_run/points"
    expected = {f"FPT-{day}.json" for day in plan["cutoffs"]}
    if {path.name for path in points_dir.glob("*.json")} != expected:
        raise ValueError("Inventory pilot khác exposure đã khóa; cần rà soát trước khi chọn mẫu")
    if f"{INPUT_DIR}/plan.json" not in coverage["sources"]:
        raise ValueError("Coverage chưa ghim plan/exposure pilot")
    sources = {**coverage["sources"], relative: coverage_checksum}
    sources.update({path.relative_to(root).as_posix(): _sha(safe_path(root, path.relative_to(root).as_posix()))
                    for path in sorted(points_dir.glob("*.json"))})
    vnindex = pd.read_csv(root / plan["model"]["source_path"], parse_dates=["Datetime"])
    rows = _rows(coverage)
    for symbol in STOCK_SYMBOLS:
        frame, events = adapter.execution_data(symbol)
        calendar = build_oos_calendar(frame, events, vnindex, start="2023-01-01", end="2024-12-31")
        if len(calendar) != len(rows[symbol]):
            raise ValueError("Coverage không còn khớp lịch nguồn")
        for expected_row, stored in zip(calendar, rows[symbol]):
            expected_row.pop("pit_ready")
            if any(stored[key] != value for key, value in expected_row.items()):
                raise ValueError("Eligibility coverage bị sửa dù đã tính lại checksum")
    design = design_calendar(coverage, pilot_dates, points_per_quarter=points_per_quarter)
    verified = 0
    for symbol in STOCK_SYMBOLS:
        frame, events = adapter.execution_data(symbol)
        days = design["smoke"]["symbol_cutoffs"][symbol] + [day for group in design["cohorts"].values()
                                                                for day in group["symbol_cutoffs"][symbol]]
        for day in days:
            row = design["points"][f"{symbol}-{day}"]
            with redirect_stdout(StringIO()):
                point = adapter.prepare(symbol, day)
            if digest(point.source_provenance) != row["proof_sha256"] or digest(point.market_regime) != row["regime_state_sha256"]:
                raise ValueError("Proof PIT của ngày chọn khác coverage đã khóa")
            execution_prices_for_cycle(frame, events, day, row["entry_date"], row["exit_date"])
            verified += 1
    design.update(sources=sources, coverage_payload_sha256=digest(coverage),
        code_sha256={name: _sha(ROOT / name) for name in ("core/cohort_calendar.py", "scripts/run_bayesian_ablation.py")},
        verification={"source_calendar": "PASS", "selected_pit_and_execution": "PASS", "verified_points": verified})
    _verify_files({**coverage["sources"], **coverage["code_sha256"], **sources}, root)
    if {path.name for path in points_dir.glob("*.json")} != expected:
        raise ValueError("Inventory pilot thay đổi trong lúc thiết kế; không lưu lịch")
    save_coverage(design, destination, root=root)
    return design
