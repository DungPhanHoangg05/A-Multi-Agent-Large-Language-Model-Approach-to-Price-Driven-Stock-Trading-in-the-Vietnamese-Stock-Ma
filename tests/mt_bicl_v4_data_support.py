"""Fixture tổng hợp chỉ cho kiểm dữ liệu v4, không dùng làm cache thị trường."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

from core.historical_signals import digest, snapshot_payload
from core.mt_bicl_v4_lineage import EPISODE_DIR, PROMPT_SOURCES, SIGNAL_DIR
from mt_bicl_bank_support import prices


def lineage(root: Path) -> tuple[dict[str, Any], Any, dict[str, Any], dict[str, Any]]:
    """Cache giả có checksum/cross-binding thật để kiểm lỗi provenance/parser."""
    frame, calendar = prices(620)
    cutoff = str(calendar[599].date())
    config = {"models": {"agent_llm_model": "fixture"}}
    identifier = "FPT-" + cutoff
    row = {"episode_id": identifier, "symbol": "FPT", "as_of_date": cutoff, "alpha_history_rows": 600}
    reports = {"trend_report": "Hướng xu hướng: Tăng", "pattern_report": "Thiên lệch dự báo: Giảm",
               "indicator_report": "Đồng thuận chủ đạo: Trung tính"}
    codes = {}
    for name in PROMPT_SOURCES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
        codes[name] = hashlib.sha256(b"fixture").hexdigest()
    proof = {"symbol": "FPT", "as_of_date": cutoff, "price_end_date": cutoff,
        "alpha_end_date": cutoff, "price_rows": 600, "news_dates": [],
        "reports_sha256": digest(reports), "price_sha256": digest(snapshot_payload(frame.iloc[:600])),
        "config": deepcopy(config), "price_basis": "UNADJUSTED_EXECUTION", "price_source": "VCI",
        "price_unit": "thousand_VND", "code_sha256": codes,
        "alpha_factors": [{"id": i + 1, "signal": "TĂNG" if i < 3 else "GIẢM"} for i in range(5)]}
    payload = {"stage": "COMPLETE", "result": {"symbol": "FPT", "as_of_date": cutoff,
        "provenance": proof, "reports": reports, "agent_signals": {"trend": "BULLISH", "pattern": "BEARISH",
            "indicator_consensus": "NEUTRAL", "alpha_consensus": "BULLISH"}}}
    save_lineage(root, identifier, payload)
    return row, frame, config, payload


def save_lineage(root: Path, identifier: str, payload: dict[str, Any]) -> None:
    """Ghi lại checksum hai file để test không dừng chỉ vì envelope bên ngoài."""
    path = root / SIGNAL_DIR / (identifier + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"payload": payload, "sha256": digest(payload)}), encoding="utf-8")
    episode = {"provenance": {"signal_checkpoint_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}
    ep = root / EPISODE_DIR / (identifier + ".json")
    ep.parent.mkdir(parents=True, exist_ok=True)
    ep.write_text(json.dumps({"payload": episode, "sha256": digest(episode)}), encoding="utf-8")


def members() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Ba prior task, target và một query; khoảng entry–exit disjoint."""
    rows = []
    import pandas as pd
    days = pd.bdate_range("2019-01-02", periods=100).strftime("%Y-%m-%d").tolist()
    for n in range(20):
        i = 4 * n
        task = n // 5
        rows.append({"episode_id": f"FPT-{days[i]}", "symbol": "FPT", "as_of_date": days[i],
            "entry_date": days[i + 1], "exit_date": days[i + 3], "task_id": f"FPT:block{task:04d}",
            "block_complete": True, "block_end_date": days[min((task + 1) * 20 - 1, 99)],
            "label_eligible": True, "features": {"status": "AVAILABLE", "raw": [float(n) / 20] * 9,
                "feature_end_date": days[i]}, "agent": {"status": "UNAVAILABLE"}})
    query = deepcopy(rows[-1])
    scaler = {"status": "AVAILABLE", "fit_end": "2018-12-31", "mean": [0.] * 9, "scale": [1.] * 9}
    regimes = {r["episode_id"]: {"query_name": "BULL", "task_name": "BULL"} for r in rows}
    return rows, query, scaler, regimes
