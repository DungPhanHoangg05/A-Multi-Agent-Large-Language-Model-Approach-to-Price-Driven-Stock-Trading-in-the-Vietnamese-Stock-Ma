"""Fixture tổng hợp MT-BICL, không dùng outcomes thị trường hoặc chạy frozen weights thật."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from core.mt_bicl_contracts import membership_hash, validate_context, validate_fact_packet
from mt_bicl_tasks_support import builder, setup

UUID = "00000000-0000-4000-8000-000000000001"


def packet(identifier: str, *, macd: float = 1., signal: float = 0., close: float = 2., sma: float = 1.) -> dict[str, Any]:
    """Facts kiểm hợp đồng có nguồn synthetic; không dùng như bằng chứng verifier nguồn."""
    cutoff = identifier.split("-", 1)[1]
    result = {"version": "utility_icl_facts_v3", "point_id": identifier, "as_of_date": cutoff,
        "frame_end_date": cutoff, "prefix_rows": 45,
        "numeric": {"macd": macd, "signal": signal, "macd_minus_signal": macd-signal,
                    "close": close, "sma20": sma, "close_minus_sma20": close-sma},
        "bucket": "UNKNOWN" if macd == signal or close == sma else "MACD_"+("POS" if macd > signal else "NEG")+"_PRICE_"+("POS" if close > sma else "NEG"),
        "assertions": {"MACD_SIGNAL": "ABOVE" if macd > signal else "BELOW" if macd < signal else "EQUAL",
                       "MACD_ZERO": "POSITIVE" if macd > 0 else "NEGATIVE" if macd < 0 else "ZERO",
                       "PRICE_SMA20": "ABOVE" if close > sma else "BELOW" if close < sma else "EQUAL"},
        "horizon": "T+2.5", "reported_warnings": [], "source_sha256": {"synthetic_fixture": "0"*64}}
    validate_fact_packet(result)
    return result


@lru_cache(maxsize=1)
def _template() -> dict[str, Any]:
    """Tái dùng schema/lịch hợp lệ cũ rồi can thiệp label/payoff fixture tách biệt."""
    bank, sources, history = setup()
    episode = builder(bank, sources, history).build("FPT", str(history["Datetime"].iloc[995].date()))
    rows = [r for task in episode["prior"] for r in task["observations"]]+episode["target"]
    for i, row in enumerate(rows):
        row.update(y=i % 2, r_net=.04 if i % 2 else -.02)
    ids = {identifier for task in episode["prior"] for identifier in task["centroid_fit_ids"]}
    ids.update(row["episode_id"] for row in episode["target"])
    episode["advisor"] = {"version": "utility_icl_context_v3", "bucket": "MACD_POS_PRICE_POS",
                      "query_facts": packet(episode["query"]["episode_id"]),
                      "historical_facts": {identifier: packet(identifier) for identifier in sorted(ids)}}
    episode["membership_sha256"] = membership_hash(episode)
    validate_context(episode)
    return episode


def episode() -> dict[str, Any]:
    """Mỗi test nhận bản sao độc lập, không mutate cache chung."""
    return deepcopy(_template())


def reply(facts: dict[str, Any], decision: str = "LONG", *, anchor: bool = False) -> dict[str, Any]:
    """Response giả có đủ schema MT-BICL; không phải kết quả suy luận LLM."""
    return {"version": "utility_icl_reply_v3", "decision": decision, "forecast_horizon": "T+2.5",
        "confidence": "Cao", "risk_reward_ratio": 1., "evidence_for": "Fixture thuận.",
        "evidence_against": "Fixture nghịch.", "justification": "Chỉ kiểm hợp đồng offline.",
        "fact_ids": list(facts["assertions"]), "fact_assertions": deepcopy(facts["assertions"]),
        "context_reason": "NOT_APPLICABLE" if anchor else "SUPPORTED"}


def original(decision: str = "LONG") -> dict[str, Any]:
    """Schema legacy không mang fields MT-BICL."""
    return {k: v for k, v in reply(packet("FPT-2023-01-06"), decision).items()
            if k not in ("version", "fact_ids", "fact_assertions", "context_reason")}


def shared(facts: dict[str, Any], text: str = "Báo cáo fixture, không gọi upstream.") -> dict[str, Any]:
    """Năm báo cáo chung, chỉ nhãn point/PIT không có outcome query."""
    return {"stock_name": facts["point_id"].split("-", 1)[0], "as_of_date": facts["as_of_date"],
        "time_frame": "1d", "language": "vi", "is_backtest": True,
        **{name+"_report": text for name in ("trend", "pattern", "indicator", "alpha", "sentiment")}}


def protocol() -> dict[str, Any]:
    """Đọc spec khóa, không tạo grant/counter hoặc chạy metadata verifier thực nghiệm."""
    return json.loads(Path("docs/plan/week11/mt_bicl_protocol.json").read_text(encoding="utf-8"))


def unsupported(branch: dict[str, Any], reason: str = "PRIOR_TASKS_BELOW_TWO") -> dict[str, Any]:
    """Fixture trạng thái unsupported nhất quán, không sửa mỗi cờ eligible để che U lỗi."""
    result = deepcopy(branch)
    result.update(eligible=False, reason=reason, projection=None)
    if result["utility"] is not None:
        wire = result["utility"]
        wire.update(status="UTILITY_UNSUPPORTED", reason=reason, draws=0, draws_sha256=None)
        for key in ("posterior_mean_theta", "mean_U_net_fraction", "MC_mean_U_net_fraction", "q10_U_net_fraction", "q90_U_net_fraction"):
            wire[key] = None
    return result
