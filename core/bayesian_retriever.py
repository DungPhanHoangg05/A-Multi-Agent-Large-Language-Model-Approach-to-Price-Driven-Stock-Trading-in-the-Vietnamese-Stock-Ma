"""Nền truy xuất prior: xác minh kho, lọc PIT và bảo vệ bản sao dữ liệu."""

from __future__ import annotations

import copy
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random
import re
from typing import Any
import unicodedata

from core.bayesian_memory import (
    HistoricalMemory, OUTCOME_KEYS, RECORD_KEYS, REGIMES, SYMBOLS, exact_object,
    is_bullish, iso_date, read_json, validate_signals,
)

ROOT = Path(__file__).resolve().parents[1]
MODES = {"bayesian_regime", "random", "recent", "similarity"}
SCOPES = {"same_symbol", "pooled"}
VERSIONS = {"api_contract_version": 1, "sampling_version": "prior_sampling_v1",
            "metric_version": "signal_match_v1", "statistics_version": "regime_empirical_stats_v1",
            "prefix_version": "compact_brpp_v1"}
TECHNICAL_ALIASES = {
    "BULLISH": ("BULLISH", "BULL", "UP", "TĂNG", "TĂNG GIÁ"),
    "BEARISH": ("BEARISH", "BEAR", "DOWN", "GIẢM", "GIẢM GIÁ"),
    "NEUTRAL": ("NEUTRAL", "TRUNG TÍNH", "TRUNG_TÍNH"),
}
SENTIMENT_ALIASES = {"POSITIVE": ("POSITIVE", "TÍCH CỰC"),
                     "NEGATIVE": ("NEGATIVE", "TIÊU CỰC"),
                     "NEUTRAL": ("NEUTRAL", "TRUNG TÍNH", "TRUNG_TÍNH")}


def normalize_signals(signals: dict[str, str]) -> dict[str, str]:
    """Kiểm đủ năm trường và nhận đúng alias; không suy hướng từ báo cáo."""
    validate_signals(signals)
    result: dict[str, str] = {}
    for field, value in signals.items():
        label = unicodedata.normalize("NFC", value).strip().upper()
        aliases = SENTIMENT_ALIASES if field == "sentiment" else TECHNICAL_ALIASES
        matches = [name for name, allowed in aliases.items() if label in allowed]
        if len(matches) != 1:
            raise ValueError(f"Tín hiệu {field} không thuộc bảng alias đã khóa")
        result[field] = matches[0]
    return result


def _matches_snapshot(actual: Any, expected: Any) -> bool:
    """So cả kiểu Python gốc lẫn giá trị để NumPy scalar không lọt qua phép bằng."""
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(
            type(key) is str and _matches_snapshot(actual[key], value) for key, value in expected.items()
        )
    return bool(actual == expected)


PREFIX_METRICS = ("win_rate_long", "bull_trap_rate", "trend_false_bullish_rate", "pattern_false_bullish_rate")
PREFIX_CHAR_LIMIT = 600


def _validate_prefix_statistics(stats: dict[str, Any]) -> None:
    """Kiểm schema/tỷ lệ/mẫu số và các quan hệ counts đã khóa; không sửa input."""
    exact_object(stats, {"regime", "population_count", "metrics"})
    if type(stats["regime"]) is not str or stats["regime"] not in REGIMES:
        raise ValueError("Regime của thống kê không hợp lệ")
    count = stats["population_count"]
    if type(count) is not int or count < 0:
        raise ValueError("Population count phải là int Python gốc không âm")
    metrics = stats["metrics"]
    exact_object(metrics, set(PREFIX_METRICS))
    for item in metrics.values():
        exact_object(item, {"numerator", "denominator", "rate"})
        numerator, denominator, rate = item["numerator"], item["denominator"], item["rate"]
        if (type(numerator) is not int or type(denominator) is not int
                or not 0 <= numerator <= denominator <= count):
            raise ValueError("Counts metric không hợp lệ")
        if denominator == 0:
            if rate is not None:
                raise ValueError("Mẫu số 0 phải có rate None")
        elif (type(rate) is not float or not math.isfinite(rate) or not 0 <= rate <= 1
              or not math.isclose(rate, numerator / denominator, rel_tol=0.0, abs_tol=1e-12)):
            raise ValueError("Rate khác tỷ lệ counts hoặc không là float Python gốc hữu hạn")
    win, trap, trend, pattern = (metrics[name] for name in PREFIX_METRICS)
    if (win["denominator"] != count
            or trap["numerator"] > count - win["numerator"]
            or not max(trend["numerator"], pattern["numerator"]) <= trap["numerator"]
            <= trend["numerator"] + pattern["numerator"]
            or not max(trend["denominator"], pattern["denominator"]) <= trap["denominator"]
            <= min(count, trend["denominator"] + pattern["denominator"])):
        raise ValueError("Quan hệ counts win/trap/bullish không hợp lệ")


def _format_net_return(net: float | int) -> str:
    """Giữ đơn vị phần trăm và dấu; dùng scientific ở sát 0 hoặc số rất lớn."""
    try:
        finite = type(net) in (float, int) and math.isfinite(net)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError("Lợi nhuận phải là số Python gốc hữu hạn")
    if net == 0:
        return "0.00%"
    return f"{net:+.2f}%" if 0.005 <= abs(net) < 10000 else f"{net:+.2e}%"


def _prefix_task_line(task: dict[str, Any]) -> str:
    """Kiểm task theo schema nội bộ; không đọc giá hoặc tự xác nhận cutoff/provenance."""
    exact_object(task, RECORD_KEYS)
    if type(task["episode_id"]) is not str or not task["episode_id"].strip():
        raise ValueError("Task prefix thiếu ID hợp lệ")
    for field, allowed in (("symbol", SYMBOLS), ("regime", REGIMES)):
        if type(task[field]) is not str or task[field] not in allowed:
            raise ValueError(f"{field} của task prefix không hợp lệ")
    dates = [iso_date(task[field]) for field in ("as_of_date", "entry_date", "exit_date")]
    if not dates[0] < dates[1] < dates[2]:
        raise ValueError("Ngày quyết định/vào/thoát của task prefix không tăng")
    signals = normalize_signals(task["agent_signals"])
    if signals["sentiment"] != "NEUTRAL":
        raise ValueError("BRPP v1 dành cho kho thiếu tin; tín hiệu tin khác cần phiên bản prefix mới")
    outcome = task["outcome"]
    exact_object(outcome, OUTCOME_KEYS)
    net_text = _format_net_return(outcome["net_return_pct"])
    positive = outcome["net_return_pct"] > 0
    if (type(outcome["result"]) is not str or type(outcome["actual_direction"]) is not str
            or outcome["result"] != ("WIN_IF_LONG" if positive else "LOSS_IF_LONG")
            or outcome["actual_direction"] != ("UP" if positive else "DOWN")):
        raise ValueError("Nhãn LONG/hướng không khớp dấu lợi nhuận ròng")
    bullish = is_bullish(signals["trend"]) or is_bullish(signals["pattern"])
    if type(outcome["was_bull_trap"]) is not bool or outcome["was_bull_trap"] != (bullish and not positive):
        raise ValueError("Nhãn bull trap của task prefix không hợp lệ")
    codes = {"BULLISH": "+", "BEARISH": "-", "NEUTRAL": "0"}
    directions = "".join(codes[signals[field]] for field in (
        "trend", "pattern", "alpha_consensus", "indicator_consensus"
    ))
    return (f"{task['symbol']}@{task['as_of_date']} R={task['regime']} T/P/A/I={directions} "
            f"{'W' if positive else 'L'} {net_text}")


def format_compact_prior_prefix(tasks: list[dict[str, Any]], stats: dict[str, Any] | None) -> str:
    """Render BRPP v1 ≤600 ký tự; caller phải xác minh PIT và provenance trước khi gọi."""
    if type(tasks) is not list or len(tasks) > 3:
        raise ValueError("BRPP v1 nhận list Python gốc có tối đa ba task")
    if stats is None:
        if tasks:
            raise ValueError("Task prior không rỗng phải có thống kê")
        return ""
    _validate_prefix_statistics(stats)
    ids: set[str] = set()
    task_lines: list[str] = []
    for task in tasks:
        line = _prefix_task_line(task)
        if task["episode_id"] in ids:
            raise ValueError("Task prefix trùng ID")
        ids.add(task["episode_id"])
        task_lines.append(line)

    def rate_text(item: dict[str, Any]) -> str:
        """Giữ mẫu số hỗ trợ, dùng N/A thay cho tỷ lệ chưa xác định."""
        if item["denominator"] == 0:
            return "0/0(N/A)"
        return f"{item['numerator']}/{item['denominator']}({item['rate'] * 100:.1f}%)"

    rates = [rate_text(stats["metrics"][name]) for name in PREFIX_METRICS]
    lines = [f"[BRPP v1] R={stats['regime']}; n={stats['population_count']}; k={len(tasks)}",
             f"LONGwin={rates[0]}; Trap={rates[1]}; TrendFail={rates[2]}; PatternFail={rates[3]}",
             "T/P/A/I:+ tăng,- giảm,0 trung tính; W/L=LONG ròng sau phí; SHORT=tiền mặt; S=thiếu tin.",
             *task_lines]
    prefix = unicodedata.normalize("NFC", "\n".join(lines))
    if len(prefix) > PREFIX_CHAR_LIMIT:
        raise ValueError("BRPP vượt 600 ký tự; cần chốt phiên bản mới, không cắt chuỗi hoặc bỏ task")
    return prefix


class BayesianPriorRetriever:
    """Nạp kho một lần; chọn prior PIT ở bốn mode và tính tỷ lệ mẫu cùng regime."""

    def __init__(self, *, bank_path: str | Path, manifest_path: str | Path,
                 audit_path: str | Path) -> None:
        """Xác minh checksum/schema/signature và nhãn kinh tế trước khi dùng kho."""
        path = Path(bank_path)
        bank_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest, audit = read_json(Path(manifest_path)), read_json(Path(audit_path))
        schema_hash = hashlib.sha256(
            (ROOT / "docs/plan/week1/historical_task_record.schema.json").read_bytes()
        ).hexdigest()
        try:
            if (type(manifest) is not dict or type(audit) is not dict
                    or audit["status"] != "PASS"
                    or manifest["bank_sha256"] != bank_hash or audit["bank_sha256"] != bank_hash
                    or audit["schema_sha256"] != schema_hash
                    or type(manifest["run_signature"]) is not str
                    or not re.fullmatch(r"[0-9a-f]{64}", manifest["run_signature"])
                    or audit["run_signature"] != manifest["run_signature"]):
                raise ValueError("Kho/manifest/QA/schema/signature không khớp")
            for evidence in (manifest, audit):
                if type(evidence["format_version"]) is not int or evidence["format_version"] != 1:
                    raise ValueError("Phiên bản bằng chứng chưa được hỗ trợ")
            if type(manifest["remaining"]) is not int or manifest["remaining"] != 0:
                raise ValueError("Kho phát hành chưa hoàn tất")
        except (KeyError, TypeError) as exc:
            raise ValueError("Bằng chứng kho thiếu trường hoặc sai kiểu") from exc
        memory = HistoricalMemory()
        memory.load(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != bank_hash:
            raise ValueError("File kho thay đổi trong lúc nạp")
        snapshot = memory.records
        coverage = {"by_symbol": Counter(r["symbol"] for r in snapshot),
                    "by_regime": Counter(r["regime"] for r in snapshot),
                    "by_year": Counter(r["as_of_date"][:4] for r in snapshot)}
        try:
            for evidence in (manifest, audit):
                if type(evidence["completed"]) is not int or evidence["completed"] != len(snapshot):
                    raise ValueError("Số record khác manifest/QA")
                for key, counts in coverage.items():
                    supplied = evidence[key]
                    if (type(supplied) is not dict
                            or any(type(v) is not int or v < 0 for v in supplied.values())
                            or {k: v for k, v in supplied.items() if v} != dict(counts)):
                        raise ValueError("Độ phủ kho khác manifest/QA")
        except (KeyError, TypeError) as exc:
            raise ValueError("Thống kê bằng chứng thiếu trường hoặc sai kiểu") from exc
        for record in snapshot:
            normalize_signals(record["agent_signals"])
        self._memory = memory
        self._verified_by_id = {r["episode_id"]: r for r in snapshot}
        self._bank_sha256 = bank_hash

    @staticmethod
    def _validate_query(*, symbol: str, as_of_date: str, current_regime: str,
                        current_signals: dict[str, str] | None, mode: str,
                        k: int, seed: int, scope: str) -> None:
        """Kiểm query trước nhánh K=0; bool không được coi là int hợp lệ."""
        for name, value, allowed in (("symbol", symbol, SYMBOLS),
                                     ("current_regime", current_regime, REGIMES),
                                     ("mode", mode, MODES), ("scope", scope, SCOPES)):
            if type(value) is not str or value not in allowed:
                raise ValueError(f"{name} không hợp lệ")
        iso_date(as_of_date)
        if type(k) is not int or not 0 <= k <= 3:
            raise ValueError("K phải là int Python gốc trong 0..3")
        if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
            raise ValueError("Seed phải là int Python gốc trong 0..2^32−1")
        if current_signals is not None:
            normalize_signals(current_signals)
        elif k > 0 and mode in {"bayesian_regime", "similarity"}:
            raise ValueError("Chế độ similarity/Bayesian cần đủ tín hiệu hiện tại")

    def _assert_pool(self, records: list[dict[str, Any]], *, symbol: str,
                     as_of_date: str, scope: str, regime: str | None = None) -> None:
        """Chặn prior sai cutoff/scope/ID hoặc khác bản đã xác minh, không bỏ qua lỗi."""
        if type(records) is not list:
            raise ValueError("Pool phải là list Python gốc")
        ids: set[str] = set()
        for record in records:
            if type(record) is not dict or type(record.get("episode_id")) is not str:
                raise ValueError("Record pool không có ID hợp lệ")
            identifier = record["episode_id"]
            if identifier in ids or not _matches_snapshot(record, self._verified_by_id.get(identifier)):
                raise ValueError("Record pool trùng ID hoặc khác kho đã xác minh")
            if (record["exit_date"] >= as_of_date
                    or (scope == "same_symbol" and record["symbol"] != symbol)
                    or (regime is not None and record["regime"] != regime)):
                raise ValueError("Record pool vi phạm cutoff/scope/regime")
            ids.add(identifier)

    def prepare_query(self, *, symbol: str, as_of_date: str, current_regime: str,
                      current_signals: dict[str, str] | None = None,
                      mode: str = "bayesian_regime", k: int = 3, seed: int = 42,
                      scope: str = "same_symbol") -> dict[str, Any]:
        """Trả pool chung/population PIT để task sau ranking/stats; không gọi I/O."""
        self._validate_query(symbol=symbol, as_of_date=as_of_date, current_regime=current_regime,
                             current_signals=current_signals, mode=mode, k=k, seed=seed, scope=scope)
        metadata = {**VERSIONS, "bank_sha256": self._bank_sha256, "symbol": symbol,
                    "as_of_date": as_of_date, "current_regime": current_regime, "mode": mode,
                    "scope": scope, "requested_k": k, "seed": seed}
        if k == 0:
            metadata.update(eligible_count=None, matched_regime_count=None, candidate_count=None)
            return {"eligible_tasks": [], "regime_population": [], "metadata": metadata}
        eligible = self._memory.eligible(as_of_date, symbol if scope == "same_symbol" else None)
        self._assert_pool(eligible, symbol=symbol, as_of_date=as_of_date, scope=scope)
        population = [r for r in eligible if r["regime"] == current_regime]
        self._assert_pool(population, symbol=symbol, as_of_date=as_of_date,
                          scope=scope, regime=current_regime)
        metadata.update(eligible_count=len(eligible), matched_regime_count=len(population),
                        candidate_count=len(population) if mode == "bayesian_regime" else len(eligible))
        return {"eligible_tasks": copy.deepcopy(eligible),
                "regime_population": copy.deepcopy(population), "metadata": metadata}

    def _validate_selection(self, selected: list[dict[str, Any]], *, symbol: str,
                            as_of_date: str, current_regime: str, scope: str,
                            mode: str, k: int) -> None:
        """Kiểm hậu điều kiện cho bộ chọn sẽ triển khai; không cho vượt K."""
        self._assert_pool(selected, symbol=symbol, as_of_date=as_of_date, scope=scope,
                          regime=current_regime if mode == "bayesian_regime" else None)
        if len(selected) > k:
            raise ValueError("Bộ chọn trả quá K prior")

    @staticmethod
    def _select_recent(candidates: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
        """Xếp exit giảm dần, phá hòa bằng ID tăng dần, không dùng thứ tự kho."""
        ordered = sorted(candidates, key=lambda record: record["episode_id"])
        return sorted(ordered, key=lambda record: record["exit_date"], reverse=True)[:k]

    @staticmethod
    def _select_random(candidates: list[dict[str, Any]], k: int,
                       metadata: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        """Lấy không hoàn lại bằng RNG cục bộ và seed query, không phụ thuộc outcome/hash kho."""
        payload = {key: metadata[key] for key in (
            "sampling_version", "seed", "symbol", "as_of_date", "scope"
        )}
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(encoded).digest()
        generator = random.Random(int.from_bytes(digest, "big"))
        ordered = sorted(candidates, key=lambda record: record["episode_id"])
        return generator.sample(ordered, min(k, len(ordered))), digest.hex()

    @staticmethod
    def _select_similarity(candidates: list[dict[str, Any]], k: int,
                           current_signals: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, float]]:
        """So khớp bốn tín hiệu; phá hòa bằng exit/ID, không đọc nhãn kinh tế."""
        query = normalize_signals(current_signals)
        fields = ("trend", "pattern", "alpha_consensus", "indicator_consensus")
        scores: dict[str, float] = {}
        for record in candidates:
            signals = normalize_signals(record["agent_signals"])
            scores[record["episode_id"]] = 0.25 * sum(signals[field] == query[field] for field in fields)
        ordered = sorted(candidates, key=lambda record: record["episode_id"])
        ordered.sort(key=lambda record: record["exit_date"], reverse=True)
        ordered.sort(key=lambda record: scores[record["episode_id"]], reverse=True)
        return ordered[:k], scores

    def select_prior_tasks(self, *, symbol: str, as_of_date: str, current_regime: str,
                           current_signals: dict[str, str] | None = None,
                           mode: str = "bayesian_regime", k: int = 3, seed: int = 42,
                           scope: str = "same_symbol") -> dict[str, Any]:
        """Trả task đã chọn/population/metadata; retrieve bổ sung thống kê từ toàn population."""
        prepared = self.prepare_query(symbol=symbol, as_of_date=as_of_date,
                                      current_regime=current_regime, current_signals=current_signals,
                                      mode=mode, k=k, seed=seed, scope=scope)
        metadata = prepared["metadata"]
        effective_seed = None
        scores: dict[str, float] = {}
        if k == 0:
            selected: list[dict[str, Any]] = []
            status, reason = "disabled", "k_zero"
        else:
            candidates = prepared["eligible_tasks"]
            if mode == "recent":
                selected = self._select_recent(candidates, k)
            elif mode == "random":
                selected, effective_seed = self._select_random(candidates, k, metadata)
            elif mode == "similarity":
                selected, scores = self._select_similarity(candidates, k, current_signals)
            else:
                selected, scores = self._select_similarity(prepared["regime_population"], k, current_signals)
            self._validate_selection(selected, symbol=symbol, as_of_date=as_of_date,
                                     current_regime=current_regime, scope=scope, mode=mode, k=k)
            if not selected:
                status = "empty"
                reason = "no_eligible_history" if metadata["eligible_count"] == 0 else "no_matching_regime"
            elif len(selected) < k:
                status, reason = "partial", "insufficient_candidates"
            else:
                status, reason = "complete", None
        metadata.update(effective_seed=effective_seed, selected_count=len(selected),
                        selected_ids=[r["episode_id"] for r in selected],
                        selected_scores=[{"episode_id": r["episode_id"], "score": scores.get(r["episode_id"])}
                                         for r in selected],
                        status=status, reason=reason)
        return {"tasks": copy.deepcopy(selected),
                "regime_population": copy.deepcopy(prepared["regime_population"]), "metadata": metadata}

    def _compute_statistics(self, population: list[dict[str, Any]], *, symbol: str,
                            as_of_date: str, current_regime: str, scope: str) -> dict[str, Any]:
        """Tính tỷ lệ mẫu trên toàn population PIT; không smoothing hoặc dùng K làm mẫu số."""
        self._assert_pool(population, symbol=symbol, as_of_date=as_of_date,
                          scope=scope, regime=current_regime)
        wins = union_count = trap_count = trend_count = trend_fail = pattern_count = pattern_fail = 0
        for record in population:
            signals = normalize_signals(record["agent_signals"])
            trend = is_bullish(signals["trend"])
            pattern = is_bullish(signals["pattern"])
            loss = record["outcome"]["result"] == "LOSS_IF_LONG"
            trap = (trend or pattern) and loss
            if record["outcome"]["was_bull_trap"] is not trap:
                raise ValueError("Nhãn bull trap khác quan hệ bullish và LOSS trong population")
            wins += int(record["outcome"]["result"] == "WIN_IF_LONG")
            union_count += int(trend or pattern)
            trap_count += int(trap)
            trend_count += int(trend)
            trend_fail += int(trend and loss)
            pattern_count += int(pattern)
            pattern_fail += int(pattern and loss)

        def metric(numerator: int, denominator: int) -> dict[str, int | float | None]:
            """Giữ counts gốc; mẫu số 0 có tỷ lệ không xác định để JSON lưu null."""
            return {"numerator": numerator, "denominator": denominator,
                    "rate": float(numerator / denominator) if denominator else None}

        return {"regime": current_regime, "population_count": len(population), "metrics": {
            "win_rate_long": metric(wins, len(population)),
            "bull_trap_rate": metric(trap_count, union_count),
            "trend_false_bullish_rate": metric(trend_fail, trend_count),
            "pattern_false_bullish_rate": metric(pattern_fail, pattern_count),
        }}

    def retrieve(self, *, symbol: str, as_of_date: str, current_regime: str,
                 current_signals: dict[str, str] | None = None, mode: str = "bayesian_regime",
                 k: int = 3, seed: int = 42, scope: str = "same_symbol") -> dict[str, Any]:
        """Trả tasks/stats/metadata; Original K=0 không tạo pool hoặc tính thống kê."""
        selection = self.select_prior_tasks(symbol=symbol, as_of_date=as_of_date,
                                            current_regime=current_regime, current_signals=current_signals,
                                            mode=mode, k=k, seed=seed, scope=scope)
        stats = None
        if k > 0:
            stats = self._compute_statistics(selection["regime_population"], symbol=symbol,
                                             as_of_date=as_of_date, current_regime=current_regime, scope=scope)
            count = selection["metadata"]["matched_regime_count"]
            if type(count) is not int or stats["population_count"] != count:
                raise ValueError("Population thống kê khác matched_regime_count")
        return {"tasks": selection["tasks"], "stats": stats, "metadata": selection["metadata"]}
