"""Memory/index U-BICL riêng: nhập upstream đã kiểm, đóng PIT và scaler train-only."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date
import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from core.bayesian_memory import (
    HistoricalMemory, REGIMES, exact_object, iso_date, validate_signals,
)
from core.bayesian_retriever import normalize_signals
from core.historical_outcomes import HistoricalOutcomeGenerator
from core.historical_signals import digest
from core.pit_price_features import extract_pit_price_features
from core.price_feature_index import (
    PriceFeatureIndex, SYMBOLS, TRAIN_END, _FOLDS, _VERIFIED, _json_bytes,
    build_price_feature_index, _runtime,
)

MEMORY_VERSION = "unified_bayes_memory_v1"
INDEX_VERSION = "unified_episode_price_index_v1"
MAX_EXIT = "2024-12-31"
MAX_AGE_DAYS = 730
OUTPUT = "outputs/bayesian_benchmark/unified_bic_v1/inputs/memory_index_v1.json"
IMPORT_KEYS = {"episode_id", "symbol", "as_of_date", "regime", "agent_signals", "source"}
SOURCE_KEYS = {"cohort", "point_id", "run_signature", "shared_sha256", "signal_config", "client_options"}
FORBIDDEN = {"decision", "action", "confidence", "justification", "evidence_for", "evidence_against"}
FOLDS = {name: deepcopy(fold) for name, fold in _FOLDS.items() if name.startswith("train_")}
FOLDS["oos_2023_2025"] = {**deepcopy(_FOLDS["oos_2023_2024"]), "query_end": "2025-12-31"}


def reject_decision(value: Any) -> None:
    """Chặn trường Decision ở mọi mức trước khi chiếu upstream thành feature."""
    if type(value) is dict:
        if FORBIDDEN.intersection(value):
            raise ValueError("Upstream chứa trường Decision bị cấm")
        for child in value.values():
            reject_decision(child)
    elif type(value) is list:
        for child in value:
            reject_decision(child)


def runtime_identity() -> dict[str, Any]:
    """Ghim code LF/runtime mới; không thay identity hay dependency W9."""
    result = _runtime()
    root = Path(__file__).resolve().parents[1]
    for name in ("core/unified_bayes_memory.py", "scripts/prepare_unified_bayes_memory.py",
                 "core/bayesian_memory.py", "core/historical_outcomes.py", "core/backtest_engine.py"):
        result["code_sha256"][name] = hashlib.sha256((root / name).read_text("utf-8").encode()).hexdigest()
    return result


class UnifiedPriceFeatureIndex(PriceFeatureIndex):
    """Mở scope tới 2025; tái dùng extractor/transform và đúng scaler train cũ."""

    def scaler(self, symbol: str, as_of_date: str, *, fold_id: str | None = None) -> dict[str, Any]:
        """Chọn fold mới theo cutoff thật; không refit hoặc mượn scaler mã khác."""
        cutoff = iso_date(as_of_date)
        if type(symbol) is not str or symbol not in SYMBOLS:
            raise ValueError("Mã scaler U-BICL không hợp lệ")
        matches = [key for key, fold in FOLDS.items() if fold["query_start"] <= cutoff <= fold["query_end"]]
        if len(matches) != 1 or fold_id is not None and fold_id != matches[0]:
            raise ValueError("Fold scaler U-BICL sai cutoff")
        name = matches[0]
        return {"fold_id": name, "index_sha256": self.identity,
                "scaler_version": self._payload["scaler_version"],
                "scaler_sha256": self._scaler_hashes[(name, symbol)],
                **deepcopy(self._payload["scalers"][name][symbol])}


def _index(records: list[dict[str, Any]], *, prices: dict[str, Any], calendar: pd.DatetimeIndex,
           source: dict[str, str], provenance: dict[str, Any]) -> UnifiedPriceFeatureIndex:
    """Fit đúng train gốc, rồi chỉ trích feature tại cutoff của các cycle nhập."""
    fields = ("episode_id", "symbol", "as_of_date", "exit_date")
    train = [{key: row[key] for key in fields} for row in records if row["exit_date"] <= TRAIN_END]
    base = build_price_feature_index(records=train, prices=prices, calendar=calendar,
                                    source=source, provenance=provenance)
    payload = base.payload
    payload.update(index_version=INDEX_VERSION, folds=deepcopy(FOLDS), runtime=runtime_identity())
    payload["scalers"]["oos_2023_2025"] = payload["scalers"].pop("oos_2023_2024")
    for row in records:
        if row["exit_date"] > TRAIN_END:
            frame, events = prices[row["symbol"]]
            payload["records"].append({**{key: row[key] for key in fields},
                "features": extract_pit_price_features(frame, events, calendar, row["as_of_date"], source=source)})
    payload["records"].sort(key=lambda row: row["episode_id"])
    # Hash bank mới chỉ định danh union; các vector/scaler không nhận outcome.
    payload["provenance"]["bank"] = {"bank_sha256": digest(records),
                                      "original_bank_sha256": provenance["bank"]["bank_sha256"]}
    _json_bytes(payload)
    return UnifiedPriceFeatureIndex(payload, _verified=_VERIFIED)


def build_memory(*, original: list[dict[str, Any]], imported: list[dict[str, Any]],
                 prices: dict[str, Any], calendar: pd.DatetimeIndex, source: dict[str, str],
                 provenance: dict[str, Any], compatibility: dict[str, Any],
                 source_files: dict[str, str], protocol_sha256: str) -> UnifiedMemory:
    """Biên thuần sau kiểm nguồn: tái sinh nhãn bằng engine, dedup và giữ lý do loại.

    Giá/nguồn ở đây do adapter production xác minh trước; loader phải tái dựng
    bằng chính đầu vào đó. Không đọc Decision, nhãn 2025 hoặc chọn bằng outcome.
    """
    _json_bytes({"original": original, "imported": imported, "compatibility": compatibility,
                 "source_files": source_files, "protocol_sha256": protocol_sha256})
    if (type(prices) is not dict or set(prices) != set(SYMBOLS)
            or not isinstance(calendar, pd.DatetimeIndex) or calendar.empty
            or calendar.hasnans or calendar.tz is not None or not calendar.is_unique
            or not calendar.is_monotonic_increasing or not calendar.equals(calendar.normalize())
            or calendar[0] != pd.Timestamp("2018-01-02")):
        raise ValueError("Memory cần lịch VNINDEX neo 02/01/2018 và giá đủ bốn mã")
    exact_object(compatibility, {"signal_config", "client_options"})
    if (type(original) is not list or not original or len(original) > 852
            or type(imported) is not list or len(imported) > 124
            or type(source_files) is not dict or not source_files or any(type(k) is not str or type(v) is not str
                or len(v) != 64 or set(v) - set("0123456789abcdef") for k, v in source_files.items())
            or type(protocol_sha256) is not str or len(protocol_sha256) != 64
            or set(protocol_sha256) - set("0123456789abcdef")):
        raise ValueError("Memory thiếu nguồn/hash hoặc vượt trần protocol")
    validator = HistoricalMemory(execution_loader=prices.__getitem__)
    validator._validate_all(original)
    if any(row["exit_date"] > TRAIN_END for row in original):
        raise ValueError("Bank gốc chứa cycle ngoài train")
    records = deepcopy(original)
    origins = {row["episode_id"]: {"kind": "original_bank", "bank_sha256": provenance["bank"]["bank_sha256"]}
               for row in records}
    by_id = {row["episode_id"]: row for row in records}
    by_cycle = {(row["symbol"], row["as_of_date"]): row for row in records}
    excluded = []
    generator = HistoricalOutcomeGenerator(prices.__getitem__)
    for item in imported:
        reject_decision(item)
        exact_object(item, IMPORT_KEYS)
        if type(item["episode_id"]) is not str or not item["episode_id"].strip():
            raise ValueError("Upstream thiếu episode ID chuẩn")
    for item in sorted(imported, key=lambda row: (row.get("episode_id", ""), digest(row))):
        proof = item["source"]
        exact_object(proof, SOURCE_KEYS)
        symbol, cutoff = item["symbol"], iso_date(item["as_of_date"])
        if (type(symbol) is not str or symbol not in SYMBOLS or type(item["episode_id"]) is not str
                or not item["episode_id"].strip() or type(item["regime"]) is not str or item["regime"] not in REGIMES
                or not "2023-01-01" <= cutoff <= MAX_EXIT):
            raise ValueError("Upstream sai identity/regime hoặc vượt snapshot lịch sử 2024")
        for key in ("run_signature", "shared_sha256"):
            if type(proof[key]) is not str or len(proof[key]) != 64 or set(proof[key]) - set("0123456789abcdef"):
                raise ValueError("Upstream thiếu hash nguồn đã kiểm")
        if proof["cohort"] not in ("development_2023", "holdout_2024") or proof["point_id"] != f"{symbol}-{cutoff}" or (
                cutoff[:4] != ("2023" if proof["cohort"] == "development_2023" else "2024")):
            raise ValueError("Upstream khác cohort hoặc point nguồn")
        frame, _ = prices[symbol]
        days = pd.DatetimeIndex(frame.Datetime)
        pos = days.get_indexer([pd.Timestamp(cutoff)])[0]
        if pos < 0 or pos + 3 >= len(days):
            raise ValueError("Upstream thiếu cutoff/ba phiên tất toán")
        entry, exit_date = (days[pos + offset].strftime("%Y-%m-%d") for offset in (1, 3))
        if exit_date > MAX_EXIT:
            raise ValueError("Không được nhập nhãn có exit sau 2024")
        validate_signals(item["agent_signals"])
        # Kiểm kinh tế trước compatibility: quyền/giá sai luôn phải ném lỗi.
        outcome = generator.generate(symbol, cutoff, entry, exit_date, item["agent_signals"], settled_as_of=MAX_EXIT)
        reason = None
        if proof["signal_config"] != compatibility["signal_config"]:
            reason = "INCOMPATIBLE_SIGNAL_CONFIG"
        elif proof["client_options"] != compatibility["client_options"]:
            reason = "INCOMPATIBLE_CLIENT_OPTIONS"
        else:
            try:
                normalized = normalize_signals(item["agent_signals"])
            except ValueError:
                reason = "INCOMPATIBLE_SIGNAL_SEMANTICS"
            else:
                if normalized != item["agent_signals"]:
                    reason = "NONCANONICAL_SIGNAL_SEMANTICS"
        if reason:
            excluded.append({"episode_id": item["episode_id"], "source": deepcopy(proof), "reason": reason})
            continue
        record = {key: deepcopy(item[key]) for key in IMPORT_KEYS - {"source"}}
        record.update(entry_date=entry, exit_date=exit_date, outcome=outcome)
        cycle = (symbol, cutoff)
        duplicates = [row for row in (by_id.get(record["episode_id"]), by_cycle.get(cycle)) if row is not None]
        if duplicates:
            comparable = lambda row: {key: value for key, value in row.items() if key != "episode_id"}
            if any(comparable(row) != comparable(record) for row in duplicates):
                raise ValueError("ID/cycle trùng nhưng nội dung lịch sử mâu thuẫn")
            excluded.append({"episode_id": record["episode_id"], "source": deepcopy(proof),
                             "reason": "DUPLICATE_EPISODE_ID" if record["episode_id"] in by_id else "DUPLICATE_CYCLE"})
            continue
        records.append(record)
        by_id[record["episode_id"]] = by_cycle[cycle] = record
        origins[record["episode_id"]] = {"kind": "verified_upstream", **deepcopy(proof)}
    records.sort(key=lambda row: row["episode_id"])
    validator._validate_all(records)
    positions = {day: pos for pos, day in enumerate(calendar.strftime("%Y-%m-%d"))}
    if any(row["as_of_date"] not in positions for row in records):
        raise ValueError("Memory có cutoff ngoài lịch VNINDEX")
    index = _index(records, prices=prices, calendar=calendar, source=source, provenance=provenance)
    metadata = [{key: deepcopy(row[key]) for key in (
        "episode_id", "symbol", "as_of_date", "entry_date", "exit_date", "regime", "agent_signals")} |
        {"cutoff_session_index": int(positions[row["as_of_date"]])} for row in records]
    payload = {"memory_version": MEMORY_VERSION, "protocol_sha256": protocol_sha256,
        "maximum_exit_date": MAX_EXIT, "is_execution_plan": False, "confirmation_allowed": False,
        "runtime": runtime_identity(), "source_files": deepcopy(source_files),
        "compatibility": deepcopy(compatibility), "records": records, "metadata": metadata,
        "origins": origins, "excluded": excluded, "index": index.payload,
        "counts": {"original": len(original), "imported": len(records) - len(original),
            "total": len(records), "excluded": len(excluded),
            "by_symbol": dict(sorted(Counter(row["symbol"] for row in records).items())),
            "by_year": dict(sorted(Counter(row["as_of_date"][:4] for row in records).items()))}}
    _json_bytes(payload)
    return UnifiedMemory(payload, _verified=_VERIFIED)


class UnifiedMemory:
    """Snapshot đã kiểm; lọc metadata PIT trước khi đọc outcome, không I/O ở query."""

    def __init__(self, payload: dict[str, Any], *, _verified: object) -> None:
        if _verified is not _VERIFIED:
            raise ValueError("Chỉ producer/loader được cấp snapshot U-BICL")
        self._payload = deepcopy(payload)
        self._records = {row["episode_id"]: row for row in self._payload["records"]}
        self._metadata = {row["episode_id"]: row for row in self._payload["metadata"]}
        self.index = UnifiedPriceFeatureIndex(self._payload["index"], _verified=_VERIFIED)

    @property
    def identity(self) -> str:
        """Identity toàn nguồn/memory/index, không phải cờ cho phép chạy xác nhận."""
        return digest(self._payload)

    @property
    def payload(self) -> dict[str, Any]:
        """Trả bản sao sâu, giữ cache đã kiểm độc lập với caller."""
        return deepcopy(self._payload)

    def assert_evidence(self, rows: list[dict[str, Any]], symbol: str, as_of_date: str) -> None:
        """Evidence khai PIT có future/self/ID lạ hoặc sửa nhãn phải ném lỗi."""
        cutoff = iso_date(as_of_date)
        if type(rows) is not list or type(symbol) is not str or symbol not in SYMBOLS:
            raise ValueError("Evidence/query U-BICL sai schema hoặc mã")
        _json_bytes(rows)
        ids = set()
        for row in rows:
            if type(row) is not dict:
                raise ValueError("Record evidence phải là object JSON")
            if (row.get("symbol") != symbol or iso_date(row.get("exit_date")) >= cutoff
                    or iso_date(row.get("as_of_date")) >= cutoff or type(row.get("episode_id")) is not str
                    or row["episode_id"] in ids):
                raise ValueError("Evidence chứa future/self/cycle chưa đóng hoặc ID trùng")
            key = row.get("episode_id")
            if key not in self._records or row != self._records[key]:
                raise ValueError("Evidence khác record đã xác minh")
            ids.add(key)

    def eligible(self, symbol: str, as_of_date: str, *, regime: str | None = None) -> list[dict[str, Any]]:
        """Stats giữ mọi cycle đã đóng, kể cả quá tuổi hoặc thiếu feature giá."""
        cutoff = iso_date(as_of_date)
        self.index.scaler(symbol, cutoff)
        if regime is not None and (type(regime) is not str or regime not in REGIMES):
            raise ValueError("Regime query không hợp lệ")
        keys = [key for key, row in self._metadata.items() if row["symbol"] == symbol
                and row["exit_date"] < cutoff and row["as_of_date"] < cutoff
                and (regime is None or row["regime"] == regime)]
        rows = [deepcopy(self._records[key]) for key in keys]
        self.assert_evidence(rows, symbol, cutoff)
        return rows

    def example_pool(self, symbol: str, as_of_date: str, regime: str) -> dict[str, Any]:
        """Chỉ lọc tuổi examples theo cutoff; similarity/gate/task thuộc bước sau."""
        population = self.eligible(symbol, as_of_date, regime=regime)
        records, excluded = [], []
        for row in population:
            age = (date.fromisoformat(as_of_date) - date.fromisoformat(row["as_of_date"])).days
            if age > MAX_AGE_DAYS:
                excluded.append({"episode_id": row["episode_id"], "reason": "MAX_AGE_EXCEEDED", "age_days": age})
            else:
                records.append(row)
        return {"records": records, "excluded": excluded, "max_age_days": MAX_AGE_DAYS}


def save_memory(memory: UnifiedMemory, path: Path) -> None:
    """Tạo artifact riêng một lần, không ghi vào bank/namespace legacy."""
    from core.research_input_lock import _write_once
    if not isinstance(memory, UnifiedMemory):
        raise ValueError("Cần memory đã kiểm")
    root = Path(__file__).resolve().parents[1]
    target = Path(path).resolve()
    if not target.is_relative_to((root / "outputs/bayesian_benchmark/unified_bic_v1").resolve()):
        raise ValueError("Artifact memory phải thuộc namespace U-BICL riêng")
    _write_once(target, memory.payload)


def load_memory(path: Path, **verified_inputs: Any) -> UnifiedMemory:
    """Tái dựng semantic từ nguồn thật; tự reseal checksum không hợp thức hóa dữ liệu."""
    from core.research_cohort import read_envelope
    saved = read_envelope(Path(path))
    expected = build_memory(**verified_inputs)
    if digest(saved) != expected.identity:
        raise ValueError("Memory/index/scaler khác nguồn và hợp đồng đã tái kiểm")
    return expected
