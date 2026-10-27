"""Chọn prior/target/query rời nhau, giữ ranh giới task và metadata PIT."""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

import numpy as np
import pandas as pd

from core.mt_bicl_bank import SYMBOLS, canonical_bytes, content_hash, day
from core.mt_bicl_regimes import RegimeTimeline
from core.mt_bicl_scaler import _vector, fit_scaler, transform_features
from core.mt_bicl_stream import MarketStream

EPISODE_VERSION = "mt_bicl_task_episode_v1"


def validate_episode(episode: dict[str, Any]) -> None:
    """Từ chối future membership, trùng ID, task khác mã hoặc giao khoảng giữ lệnh."""
    query = episode["query"]
    cutoff = day(query["as_of_date"])
    if not cutoff < day(query["entry_date"]) < day(query["exit_date"]):
        raise ValueError("Ngày query/entry/exit không tăng")
    if query["episode_id"] != f"{query['symbol']}-{cutoff}" or "y" in query or "outcome" in query:
        raise ValueError("Query có ID sai hoặc chứa nhãn")
    if query["block_index"] != query["calendar_index"]//63 or query["task_id"] != f"{query['symbol']}:block{query['block_index']:04d}":
        raise ValueError("Query không đúng task/block")
    _regime_proof(query["regime"], cutoff)
    if query["regime"]["as_of_date"] != cutoff:
        raise ValueError("Regime query dùng sai ngày")
    scaler = episode["scaler"]
    if (scaler["fit_cutoff"] > cutoff or (scaler["fit_inclusive"] and scaler["fit_cutoff"] >= cutoff)
            or (scaler["fit_max_exit_date"] is not None and scaler["fit_max_exit_date"] >= cutoff)):
        raise ValueError("Scaler membership chứa thông tin sau cutoff")
    if episode["status"] == "AVAILABLE":
        for key in ("raw", "z", "model_vector"):
            if (type(query[key]) is not list or len(query[key]) != 4
                    or not np.isfinite(np.asarray(query[key], dtype=float)).all()
                    or (key == "model_vector" and (np.abs(query[key]) > 4).any())):
                raise ValueError("Vector query không hợp lệ")
    if len(episode["prior"]) != episode["K"] or len(episode["target"]) != episode["m"]:
        raise ValueError("Mẫu số K/m không khớp membership")
    if not 0 <= episode["K"] <= 3 or not 0 <= episode["m"] <= 8:
        raise ValueError("Context vượt miền đã khóa")
    ids = {query["episode_id"]}
    intervals = [(query["entry_date"], query["exit_date"])]
    tasks = set()
    observations = []
    for task in episode["prior"]:
        if (task["task_id"] in tasks or not 2 <= len(task["observations"]) <= 8
                or task["block_index"] >= query["block_index"]
                or task["task_id"] != f"{query['symbol']}:block{task['block_index']:04d}"):
            raise ValueError("Prior task thiếu cycle, trùng hoặc không trước target")
        tasks.add(task["task_id"])
        _regime_proof(task["regime"], task["block_start_date"])
        if task["regime"]["as_of_date"] != task["block_start_date"]:
            raise ValueError("Metadata regime task không ở đầu block")
        if (len(task["selected_by_distance_ids"]) != len(task["observations"])
                or set(task["selected_by_distance_ids"]) != {row["episode_id"] for row in task["observations"]}):
            raise ValueError("Danh sách rank khác membership prior")
        observations.extend((row, task["block_index"]) for row in task["observations"])
    observations.extend((row, query["block_index"]) for row in episode["target"])
    for row, block in observations:
        if (row["episode_id"] in ids or row["episode_id"] != f"{row['symbol']}-{row['as_of_date']}"
                or row["symbol"] != query["symbol"]
                or row["block_index"] != block or row["task_id"] != f"{query['symbol']}:block{block:04d}"
                or not day(row["as_of_date"]) < day(row["entry_date"]) < day(row["exit_date"]) < cutoff):
            raise ValueError("Membership vi phạm ID, block, mã hoặc temporal cutoff")
        if (type(row["y"]) is not int or row["y"] not in (0, 1)
                or type(row["r_net"]) not in (float, int) or not math.isfinite(row["r_net"])
                or row["y"] != int(row["r_net"] > 0)):
            raise ValueError("Nhãn context không hợp lệ")
        for key in ("raw", "z", "model_vector"):
            if (len(row[key]) != 4 or not np.isfinite(np.asarray(row[key], dtype=float)).all()
                    or (key == "model_vector" and (np.abs(row[key]) > 4).any())):
                raise ValueError("Vector context không hữu hạn hoặc sai số chiều")
        ids.add(row["episode_id"])
        intervals.append((row["entry_date"], row["exit_date"]))
    ordered = sorted(intervals)
    if any(a[1] >= b[0] for a, b in zip(ordered, ordered[1:])):
        raise ValueError("Khoảng entry-exit của context/query bị chồng lấp")
    canonical_bytes(episode)


def _regime_proof(proof: dict[str, Any], cutoff: str) -> None:
    """Không nhận regime/model được tạo bằng dữ liệu sau ngày đã công bố."""
    if (day(proof["as_of_date"]) > cutoff or day(proof["model_fit_cutoff"]) > cutoff
            or (proof["model_training_end_date"] is not None and proof["model_training_end_date"] > proof["model_fit_cutoff"])
            or (proof["feature_end_date"] is not None and proof["feature_end_date"] > proof["as_of_date"])):
        raise ValueError("Regime metadata vi phạm PIT")
    if proof["name"] == "UNKNOWN":
        if (proof["reason"] != "INSUFFICIENT_REGIME_HISTORY" or proof["prefix_rows"] >= 499
                or proof["model_sha256"] is not None or proof["model_training_end_date"] is not None):
            raise ValueError("UNKNOWN không có bằng chứng thiếu lịch sử")
    elif (proof["name"] not in ("BULL", "BEAR", "CHOPPY", "CONSOLIDATION")
          or proof["method"] not in ("HMM", "MULTI_FACTOR") or proof["model_sha256"] is None):
        raise ValueError("Regime không có model/calibration hợp lệ")


class TaskBuilder:
    """Builder lấy nhãn từ MarketStream, không nhận outcome query/report làm feature."""

    def __init__(self, bank: dict[str, Any], stream: MarketStream, regimes: RegimeTimeline) -> None:
        """Caller nạp bank bằng cold-verifier; scaler train cuối được tái tính riêng."""
        self._bank = deepcopy(bank)
        self.stream = stream
        self.regimes = regimes
        self.calendar = stream.calendar
        self._days = self.calendar.strftime("%Y-%m-%d").tolist()
        self._positions = {value: index for index, value in enumerate(self._days)}
        self._frozen: dict[str, Any] | None = None
        self._scalers: dict[str, dict[str, Any]] = {}
        self._view_date: str | None = None
        self._view: list[dict[str, Any]] = []

    def build(self, symbol: str, query_date: str) -> dict[str, Any]:
        """Tính x, lọc exit<query trước rank; chỉ đọc nhãn sau khi đã chọn bằng x."""
        cutoff = day(query_date)
        if symbol not in SYMBOLS:
            raise ValueError("Mã query không thuộc protocol")
        index = self._positions.get(cutoff, -1)
        if index < 0 or index+3 >= len(self.calendar):
            raise ValueError("Query thiếu lịch t+3")
        if self._view_date != cutoff:
            self._view = self.stream.advance(cutoff)
            self._view_date = cutoff
        records = self._view
        features = self.stream.features(symbol, cutoff)
        if cutoff not in self._scalers:
            if cutoff <= "2020-12-31":
                self._scalers[cutoff] = fit_scaler(self._bank, cutoff)
            else:
                if self._frozen is None:
                    self._frozen = fit_scaler(self._bank, "2021-01-01")
                    if self._bank.get("frozen_scaler", self._frozen) != self._frozen:
                        raise ValueError("Scaler cuối train khác tập fit đã khóa")
                self._scalers[cutoff] = self._frozen
        scaler = self._scalers[cutoff]
        transformed = transform_features(features, scaler)
        regime = self.regimes.query(cutoff)
        _regime_proof(regime, cutoff)
        block = index//63
        query = {"episode_id": f"{symbol}-{cutoff}", "symbol": symbol, "as_of_date": cutoff,
                 "entry_date": str(self.calendar[index+1].date()), "exit_date": str(self.calendar[index+3].date()),
                 "calendar_index": index, "block_index": block, "task_id": f"{symbol}:block{block:04d}",
                 "raw": transformed["raw"], "z": transformed["z"], "model_vector": transformed["model_vector"],
                 "feature_status": features["status"], "regime": regime}
        episode = {"episode_version": EPISODE_VERSION, "status": transformed["status"],
                   "reasons": list(transformed["reasons"]), "query": query, "scaler": deepcopy(scaler),
                   "K": 0, "m": 0, "prior": [], "target": [], "eligible_count": 0}
        if transformed["status"] != "AVAILABLE":
            validate_episode(episode)
            return episode
        # Toàn bộ phép tính distance/centroid chạy trên matrix, không duyệt row Pandas.
        eligible = [row for row in records if row["symbol"] == symbol and row["status"] == "AVAILABLE"
                    and row["exit_date"] < cutoff and row["episode_id"] != query["episode_id"]]
        for row in eligible:
            i = self._positions.get(row["as_of_date"], -1)
            if (i < 0 or i+3 >= len(self._days) or row["entry_date"] != self._days[i+1]
                    or row["exit_date"] != self._days[i+3] or i//63 != (i+3)//63
                    or row["block_index"] != i//63 or row["task_id"] != f"{symbol}:block{i//63:04d}"):
                raise ValueError("Cycle source sai lịch phiên hoặc block")
        raw = np.asarray([_vector(row["features"], row["as_of_date"]) for row in eligible], dtype=float).reshape(-1, 4)
        z = (raw-np.asarray(scaler["mean"]))/np.asarray(scaler["scale"])
        matrix = np.clip(z, -4, 4)
        distances = np.linalg.norm(matrix-np.asarray(query["model_vector"]), axis=1)
        episode["eligible_count"] = len(eligible)

        def observation(slot: int) -> dict[str, Any]:
            """Chỉ chiếu schema (x,y) của cycle nguồn đã đóng, giữ r_net trong sidecar."""
            row = eligible[slot]
            outcome = row["outcome"]
            return {**{key: row[key] for key in ("episode_id", "symbol", "as_of_date", "entry_date", "exit_date", "task_id", "block_index")},
                    "raw": raw[slot].tolist(), "z": z[slot].tolist(), "model_vector": matrix[slot].tolist(),
                    "y": outcome["y"], "r_net": outcome["r_net"], "distance": float(distances[slot]),
                    "age_days": int((pd.Timestamp(cutoff)-pd.Timestamp(row["exit_date"])).days)}

        groups: dict[int, list[int]] = {}
        target = []
        for slot, row in enumerate(eligible):
            candidate_block = row["block_index"]
            if candidate_block < block:
                groups.setdefault(candidate_block, []).append(slot)
            elif candidate_block == block:
                target.append(slot)
            else:
                raise ValueError("Cycle đã chọn thuộc block tương lai")
        ranked = []
        for prior_block, slots in groups.items():
            if len(slots) < 2:
                continue
            task_regime = self.regimes.task(prior_block)
            _regime_proof(task_regime, str(self.calendar[prior_block*63].date()))
            centroid = matrix[slots].mean(axis=0)
            distance = float(np.linalg.norm(centroid-np.asarray(query["model_vector"])))
            match = regime["name"] != "UNKNOWN" and regime["name"] == task_regime["name"]
            latest = max(eligible[s]["exit_date"] for s in slots)
            task_id = f"{symbol}:block{prior_block:04d}"
            rank = (not match, distance, -pd.Timestamp(latest).toordinal(), task_id)
            selected = sorted(slots, key=lambda s: (float(distances[s]), -pd.Timestamp(eligible[s]["as_of_date"]).toordinal(), eligible[s]["episode_id"]))[:8]
            chosen = sorted(selected, key=lambda s: (eligible[s]["as_of_date"], eligible[s]["episode_id"]))
            ranked.append((rank, {"task_id": task_id, "block_index": prior_block,
                "block_start_date": self._days[prior_block*63], "regime": task_regime,
                "known_regime_match": bool(match), "centroid": centroid.tolist(), "distance": distance,
                "centroid_fit_ids": [eligible[s]["episode_id"] for s in sorted(slots)],
                "population": len(slots), "selected_by_distance_ids": [eligible[s]["episode_id"] for s in selected],
                "chosen_slots": chosen}))
        episode["prior"] = [task for _, task in sorted(ranked, key=lambda pair: pair[0])[:3]]
        for task in episode["prior"]:
            task["observations"] = [observation(s) for s in task.pop("chosen_slots")]
        target = sorted(target, key=lambda s: (eligible[s]["as_of_date"], eligible[s]["episode_id"]))[-8:]
        episode["target"] = [observation(s) for s in target]
        episode["K"], episode["m"] = len(episode["prior"]), len(target)
        if episode["K"] < 3:
            episode["reasons"].append("PRIOR_TASKS_BELOW_THREE")
        if not episode["m"]:
            episode["reasons"].append("TARGET_COLD_START")
        elif episode["m"] < 8:
            episode["reasons"].append("TARGET_CONTEXT_BELOW_EIGHT")
        episode["membership_sha256"] = content_hash({"prior": [t["selected_by_distance_ids"] for t in episode["prior"]],
                                                     "target": [r["episode_id"] for r in episode["target"]]})
        validate_episode(episode)
        return episode
