"""Đo ngân sách BRPP/prompt offline bằng builder thật; xuất cấu hình bàn giao W4."""

from __future__ import annotations

import argparse
import copy
import hashlib
from pathlib import Path
import sys
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents import decision_agent
from core.bayesian_memory import atomic_write_json
from core.bayesian_retriever import REGIMES, SYMBOLS, format_compact_prior_prefix
from utils.i18n import get_horizon

HANDOFF_REPORT_CHAR_LIMITS = {"trend": 800, "pattern": 800, "indicator": 800, "alpha": 1100, "sentiment": 500}
PROMPT_CHAR_LIMIT_EXCLUSIVE = 6500


def prefix_fixture(regime: str = "CONSOLIDATION", k: int = 3,
                   population: int = 852) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Tạo fixture render có labels/counts nhất quán, không phải bằng chứng giá/PIT."""
    if k == 0:
        return [], None
    wins = population // 2
    stats = {"regime": regime, "population_count": population, "metrics": {
        name: {"numerator": wins, "denominator": population, "rate": float(wins / population) if population else None}
        for name in ("win_rate_long", "bull_trap_rate", "trend_false_bullish_rate", "pattern_false_bullish_rate")
    }}
    tasks = [{"episode_id": f"fixture-{i}", "symbol": "FPT", "as_of_date": "2021-01-04",
              "entry_date": "2021-01-05", "exit_date": "2021-01-07", "regime": regime,
              "agent_signals": {"trend": "BULLISH", "pattern": "BULLISH", "alpha_consensus": "BEARISH",
                                "indicator_consensus": "NEUTRAL", "sentiment": "NEUTRAL"},
              "outcome": {"actual_direction": "UP", "net_return_pct": 1e308,
                          "result": "WIN_IF_LONG", "was_bull_trap": False}} for i in range(k)]
    return tasks, stats


def report_fixture(lang: str, style: str = "saturated") -> dict[str, str]:
    """Báo cáo dài có đầu/kết luận; thử cả payload chạm cap và nhánh distill theo heading."""
    text = "Diễn giải kỹ thuật và cảnh báo biến động. " if lang == "vi" else "Technical observations and volatility risks. "
    body = text * 500 if style == "structured" else ("Đ" if lang == "vi" else "A") * 20000
    reports = {name: f"{name.upper()}_BEGIN\n{body}\n{name.upper()}_END" for name in HANDOFF_REPORT_CHAR_LIMITS}
    if style == "structured":
        convergence = "Tổng hợp hội tụ tín hiệu" if lang == "vi" else "Signal convergence summary"
        articles = "### 15 BÀI GẦN NHẤT" if lang == "vi" else "### 15 MOST RECENT ARTICLES"
        summary = "TỔNG HỢP:" if lang == "vi" else "SUMMARY:"
        reports["indicator"] = f"CHI_TIET_BO\n---\n{convergence}\n" + reports["indicator"]
        reports["alpha"] += f"\n---\nBINH_LUAN_BO\n{summary} ALPHA_END"
        reports["sentiment"] += f"\n{articles}\nBAI_BAO_BO"
    return reports


def build_fixture_prompt(raw_reports: dict[str, str], prefix: str, *, lang: str,
                         symbol: str = "FPT", time_frame: str = "1d",
                         has_alpha: bool = True, has_sentiment: bool = True,
                         report_limits: dict[str, int] | None = None) -> tuple[str, dict[str, str]]:
    """Ghép thử ngoài pipeline; patch cap tạm thời khi đo cấu hình bàn giao W4."""
    if lang not in {"vi", "en"} or symbol not in SYMBOLS or time_frame not in {"1d", "1 ngày"}:
        raise ValueError("Fixture prompt chỉ nhận VI/EN, bốn mã và timeframe daily T+2.5")
    limits = decision_agent._REPORT_CHAR_LIMITS if report_limits is None else report_limits
    with patch.dict(decision_agent._REPORT_CHAR_LIMITS, limits):
        reports = {name: decision_agent._distill_report(name, text, lang) for name, text in raw_reports.items()}
    horizon = get_horizon(time_frame, lang)
    if horizon["lookahead_candles"] != 3 or horizon["horizon_val"] != "T+2.5":
        raise ValueError("Horizon fixture không giữ hợp đồng T+2.5")
    build = decision_agent._build_compact_prompt_vi if lang == "vi" else decision_agent._build_compact_prompt_en
    prompt = build(symbol, time_frame, 3 + int(has_alpha) + int(has_sentiment), has_alpha, has_sentiment,
                   horizon["horizon_desc"], horizon["horizon_val"], horizon["note"],
                   *[reports[name] for name in ("trend", "pattern", "indicator", "alpha", "sentiment")])
    if prefix:
        head, marker, tail = prompt.partition("### [1]")
        if not marker:
            raise ValueError("Builder không có điểm ghép trước báo cáo đầu tiên")
        prompt = head + prefix + "\n" + marker + tail
    return prompt, reports


def verify_budget() -> dict[str, Any]:
    """Đối chiếu cap hiện tại với phương án W4; không gọi LLM/HMM hoặc đọc kho giá."""
    legacy_limits = copy.deepcopy(decision_agent._REPORT_CHAR_LIMITS)
    tasks, stats = prefix_fixture()
    prefix = format_compact_prior_prefix(tasks, stats)
    legacy = []
    for lang in ("vi", "en"):
        prompt, reports = build_fixture_prompt(report_fixture(lang), prefix, lang=lang)
        legacy.append({"language": lang, "prefix_length": len(prefix), "prompt_length": len(prompt),
                       "report_lengths": {name: len(text) for name, text in reports.items()},
                       "within_limit": len(prompt) < PROMPT_CHAR_LIMIT_EXCLUSIVE})
    matrix = []
    for lang in ("vi", "en"):
        for time_frame in ("1d", "1 ngày"):
            for symbol in sorted(SYMBOLS):
                for has_alpha, has_sentiment in ((False, False), (True, False), (False, True), (True, True)):
                    for regime in sorted(REGIMES):
                        for k in (0, 1, 2, 3):
                            tasks, stats = prefix_fixture(regime, k)
                            prefix = format_compact_prior_prefix(tasks, stats)
                            raw = report_fixture(lang)
                            before = copy.deepcopy((tasks, stats, raw))
                            prompt, _ = build_fixture_prompt(raw, prefix, lang=lang, symbol=symbol,
                                time_frame=time_frame, has_alpha=has_alpha, has_sentiment=has_sentiment,
                                report_limits=HANDOFF_REPORT_CHAR_LIMITS)
                            if len(prefix) > 600 or len(prompt) >= PROMPT_CHAR_LIMIT_EXCLUSIVE:
                                raise ValueError("Cấu hình bàn giao vượt ngân sách")
                            if (tasks, stats, raw) != before:
                                raise ValueError("Đo ngân sách làm thay đổi input")
                            matrix.append({"language": lang, "time_frame": time_frame, "symbol": symbol,
                                           "has_alpha": has_alpha, "has_sentiment": has_sentiment,
                                           "regime": regime, "k": k, "prefix_length": len(prefix), "prompt_length": len(prompt)})
    tasks, stats = prefix_fixture(population=10**25)
    boundary = format_compact_prior_prefix(tasks, stats)
    if len(boundary) != 600:
        raise ValueError("Fixture biên không đúng 600 ký tự")
    reserve = []
    for lang in ("vi", "en"):
        for time_frame in ("1d", "1 ngày"):
            prompt, _ = build_fixture_prompt(report_fixture(lang), boundary, lang=lang,
                time_frame=time_frame, report_limits=HANDOFF_REPORT_CHAR_LIMITS)
            if len(prompt) >= PROMPT_CHAR_LIMIT_EXCLUSIVE:
                raise ValueError("Phương án W4 không dự phòng đủ BRPP 600 ký tự")
            reserve.append({"language": lang, "time_frame": time_frame, "prefix_length": len(boundary),
                            "prompt_length": len(prompt), "headroom_to_6500": 6500 - len(prompt)})
    if decision_agent._REPORT_CHAR_LIMITS != legacy_limits:
        raise ValueError("Cấu hình cap runtime bị sửa sau phép đo offline")
    maximum_prompt = max(r["prompt_length"] for r in matrix)
    return {"format_version": 1, "status": "PASS_WITH_REQUIRED_W4_HANDOFF", "date": "2026-10-05",
            "prefix_char_limit": 600, "decision_prompt_char_limit_exclusive": 6500,
            "input_context": "synthetic_budget_fixtures_not_price_or_point_in_time_evidence",
            "legacy_report_limits": legacy_limits, "legacy_saturated_findings": legacy,
            "handoff_report_limits": HANDOFF_REPORT_CHAR_LIMITS,
            "handoff_total_report_budget": sum(HANDOFF_REPORT_CHAR_LIMITS.values()),
            "matrix_case_count": len(matrix), "matrix_max_prefix_length": max(r["prefix_length"] for r in matrix),
            "matrix_max_prompt_length": maximum_prompt,
            "matrix_max_cases": [r for r in matrix if r["prompt_length"] == maximum_prompt],
            "full_600_character_reserve": reserve,
            "source_text_sha256": {p: hashlib.sha256((ROOT / p).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
                for p in ("agents/decision_agent.py", "core/bayesian_retriever.py", "utils/i18n.py",
                          "scripts/verify_prior_prompt_budget.py", "tests/test_bayesian_prompt_budget.py")},
            "runtime_decision_changed": False, "runtime_budget_gate_passed": False,
            "required_w4_actions": ["apply_verified_report_caps", "guard_final_prompt_len_below_6500_after_all_instructions"],
            "real_bank_smoke_completed": False, "oos_trading_backtest": False}


def main() -> None:
    """Xuất receipt fixture; không đọc .env hoặc gọi API."""
    parser = argparse.ArgumentParser(description="Kiểm ngân sách BRPP/prompt offline và bàn giao W4")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/plan/week3/prompt_budget_review.json")
    args = parser.parse_args()
    receipt = verify_budget()
    atomic_write_json(args.output, receipt)
    print(f"Đã kiểm {receipt['matrix_case_count']} ca; prompt bàn giao tối đa "
          f"{receipt['matrix_max_prompt_length']} ký tự. Cap runtime cũ còn cần xử lý ở W4. Receipt: {args.output}")


if __name__ == "__main__":
    main()
