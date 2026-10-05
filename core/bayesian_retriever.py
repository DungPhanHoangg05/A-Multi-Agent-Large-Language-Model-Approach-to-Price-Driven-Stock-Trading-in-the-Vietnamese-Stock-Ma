"""Nền truy xuất prior: xác minh kho, lọc PIT và bảo vệ bản sao dữ liệu."""

from __future__ import annotations

import copy
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
from typing import Any
import unicodedata

from core.bayesian_memory import (
    HistoricalMemory, REGIMES, SYMBOLS, iso_date, read_json, validate_signals,
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


class BayesianPriorRetriever:
    """Nạp kho một lần; lọc PIT và chọn prior ở bốn mode, chưa tính stats."""

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
        """Trả task đã chọn/population/metadata; stats và result retrieve hoàn chỉnh chờ task sau."""
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

    def retrieve(self, *, symbol: str, as_of_date: str, current_regime: str,
                 current_signals: dict[str, str] | None = None, mode: str = "bayesian_regime",
                 k: int = 3, seed: int = 42, scope: str = "same_symbol") -> dict[str, Any]:
        """Xử lý Original K=0; K>0 chờ tích hợp thống kê thì dừng tường minh."""
        prepared = self.prepare_query(symbol=symbol, as_of_date=as_of_date,
                                      current_regime=current_regime, current_signals=current_signals,
                                      mode=mode, k=k, seed=seed, scope=scope)
        if k > 0:
            raise NotImplementedError("Thống kê và result retrieve K>0 sẽ tích hợp ở W3-09")
        metadata = prepared["metadata"]
        metadata.update(effective_seed=None, selected_count=0, selected_ids=[], selected_scores=[],
                        status="disabled", reason="k_zero")
        return {"tasks": [], "stats": None, "metadata": metadata}
