"""Nối cycle giá đã đóng vào view PIT; không nhận nhãn từ báo cáo đánh giá."""

from __future__ import annotations

from copy import deepcopy
from functools import partial
from typing import Any

import numpy as np
import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core.mt_bicl_bank import (
    SOURCE, SYMBOLS, _visible_events, _visible_prices, batch_features, content_hash, day, partition,
)
from core.pit_price_features import extract_pit_price_features


def market_partition(date: str) -> str | None:
    """Giữ split cũ và mở miền đã xem 2023/2024, chưa mở nhãn xác nhận 2025."""
    if date <= "2022-12-31":
        return partition(date)
    if date <= "2023-12-31":
        return "development"
    if date <= "2024-12-31":
        return "exposed_reference"
    return None


class MarketStream:
    """Chỉ sinh nhãn từ nguồn giá đã kiểm, sau tất toán và trước query hiện tại."""

    def __init__(self, bank: dict[str, Any], prices: dict[str, tuple[pd.DataFrame, list[dict[str, Any]]]],
                 calendar: pd.DatetimeIndex) -> None:
        """Bank/nguồn phải được caller xác minh; trả view sao chép để bảo vệ cache."""
        if set(prices) != set(SYMBOLS):
            raise ValueError("Stream phải có đủ bốn mã")
        self._rows = {row["episode_id"]: deepcopy(row) for row in bank["records"]}
        if len(self._rows) != len(bank["records"]):
            raise ValueError("Bank có ID trùng")
        self._prices = {symbol: (frame.copy(), deepcopy(events)) for symbol, (frame, events) in prices.items()}
        self.calendar = pd.DatetimeIndex(calendar)
        if (not len(self.calendar) or self.calendar.hasnans or self.calendar.tz is not None or self.calendar.has_duplicates
                or not self.calendar.is_monotonic_increasing or not self.calendar.equals(self.calendar.normalize())
                or self.calendar[0] != pd.Timestamp("2018-01-02")):
            raise ValueError("Lịch stream không hợp lệ")
        self._last_query: str | None = None
        self.audit: list[dict[str, Any]] = []

    def _index(self, query: str) -> int:
        """Không dùng ngày gần nhất hoặc tự mở source 2025 chưa được release."""
        query = day(query)
        index = int(self.calendar.get_indexer([pd.Timestamp(query)])[0])
        if index < 0 or query > "2024-12-31" or index+3 >= len(self.calendar):
            raise ValueError("Query thiếu lịch t+3 hoặc ngoài nguồn stream đã mở")
        return index

    def features(self, symbol: str, query: str) -> dict[str, Any]:
        """Chỉ đọc x tại query, không tính nhãn hoặc xem giá entry/exit query."""
        self._index(query)
        if symbol not in SYMBOLS:
            raise ValueError("Mã query stream không hợp lệ")
        return extract_pit_price_features(*self._prices[symbol], self.calendar, query, source=SOURCE)

    def closed_records(self) -> list[dict[str, Any]]:
        """Xuất bản sao view đã đóng hiện tại để cold-verifier đối chiếu nguồn giá."""
        if self._last_query is None:
            return []
        result = [deepcopy(row) for row in self._rows.values() if row["exit_date"] < self._last_query]
        return sorted(result, key=lambda row: (row["as_of_date"], SYMBOLS.index(row["symbol"])))

    def advance(self, query: str) -> list[dict[str, Any]]:
        """Nối nhãn exit<query theo thứ tự; cùng query được gọi lại idempotent."""
        index = self._index(query)
        if self._last_query is not None and query < self._last_query:
            raise ValueError("Stream không được lùi thời gian; tạo instance mới để replay")
        added = []
        prefix_calendar = self.calendar[:index+1]
        days = self.calendar.strftime("%Y-%m-%d").tolist()
        for symbol in SYMBOLS:
            candidates = np.asarray([i for i in range(20, index-3, 3)
                                     if f"{symbol}-{days[i]}" not in self._rows], dtype=int)
            if not len(candidates):
                continue
            source, ledger = self._prices[symbol]
            frame = _visible_prices(source, prefix_calendar)
            events = _visible_events(ledger, prefix_calendar[-1])
            features, barriers = batch_features(frame, events, prefix_calendar, candidates)
            aligned = frame.set_index("Datetime").reindex(prefix_calendar)
            present = prefix_calendar.isin(pd.DatetimeIndex(frame["Datetime"]))
            entries, exits = candidates+1, candidates+3
            holding = np.stack((entries, entries+1, exits), axis=1)
            missing = ~present[holding].all(axis=1)
            no_volume = (aligned["Volume"].to_numpy(dtype=float)[holding] == 0).any(axis=1)
            corporate = (np.searchsorted(barriers, prefix_calendar[exits], side="right")
                         - np.searchsorted(barriers, prefix_calendar[entries], side="right")) > 0
            block_cut = candidates//63 != exits//63
            splits = [market_partition(days[i]) for i in candidates]
            split_cut = np.asarray([part != market_partition(days[i]) or part is None for part, i in zip(splits, exits)])
            allowed = ~(missing | no_volume | corporate | block_cut | split_cut)
            opens = aligned["Open"].to_numpy(dtype=float)[entries]
            closes = aligned["Close"].to_numpy(dtype=float)[exits]
            net = np.full(len(candidates), np.nan)
            helper = np.frompyfunc(partial(compute_round_trip_net_return, fee=.0025, slippage=.001), 2, 1)
            if allowed.any():
                net[allowed] = helper(opens[allowed], closes[allowed]).astype(float)
            for slot, i in enumerate(candidates.tolist()):
                reasons = [reason for condition, reason in (
                    (missing[slot], "MISSING_EXECUTION_SESSION"), (no_volume[slot], "NO_MATCHED_VOLUME_AT_EXECUTION"),
                    (corporate[slot], "CORPORATE_ACTION_DURING_HOLDING"), (block_cut[slot], "CROSS_BLOCK_HOLDING"),
                    (split_cut[slot], "PURGED_SPLIT_BOUNDARY")) if condition]
                all_reasons = [*features[slot]["reasons"], *reasons]
                block = i//63
                row = {"episode_id": f"{symbol}-{days[i]}", "symbol": symbol, "as_of_date": days[i],
                    "entry_date": days[i+1], "exit_date": days[i+3], "calendar_index": i,
                    "task_id": f"{symbol}:block{block:04d}", "block_index": block,
                    "block_start_date": days[block*63], "block_start_calendar_index": block*63,
                    "block_end_calendar_index": (block+1)*63-1, "query_split": splits[slot],
                    "split": None if split_cut[slot] else splits[slot], "status": "EXCLUDED" if all_reasons else "AVAILABLE",
                    "reasons": all_reasons, "features": features[slot], "label_status": "UNAVAILABLE" if reasons else "AVAILABLE",
                    "label_reasons": reasons, "outcome": None if reasons else {"entry_open": float(opens[slot]),
                        "exit_close": float(closes[slot]), "r_net": float(net[slot]), "y": int(net[slot] > 0)}}
                if row["exit_date"] >= query:
                    raise ValueError("Stream đưa nhãn chưa đóng vào view")
                self._rows[row["episode_id"]] = row
                added.append(row["episode_id"])
        self._last_query = query
        visible = self.closed_records()
        self.audit.append({"as_of_date": query, "appended_ids": added,
                           "visible_ids_sha256": content_hash([row["episode_id"] for row in visible])})
        return visible
