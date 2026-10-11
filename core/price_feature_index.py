"""Index giá phụ và scaler đóng băng theo mã/fold; không đọc nhãn kinh tế."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile
from typing import Any

import numpy as np
import pandas as pd

from core.pit_price_features import (
    FEATURE_COLUMNS, FEATURE_VERSION, PRICE_POLICY_VERSION, SOURCE_FIELDS,
    extract_pit_price_features,
)

INDEX_VERSION = "episode_price_index_v1"
SCALER_VERSION = "symbol_fold_standard_v1"
SYMBOLS = ("FPT", "MWG", "VCB", "VNM")
TRAIN_END = "2022-12-30"
DEFAULT_INDEX_PATH = "outputs/bayesian_benchmark/price_features/index.json"
_VERIFIED = object()
_FOLDS = {
    "train_2021": {"query_start": "2021-01-04", "query_end": "2021-12-31",
                   "fit_cutoff": "2021-01-04", "fit_inclusive": False, "freeze_date": "2021-01-04"},
    "train_2022": {"query_start": "2022-01-06", "query_end": TRAIN_END,
                   "fit_cutoff": "2022-01-06", "fit_inclusive": False, "freeze_date": "2022-01-06"},
    "oos_2023_2024": {"query_start": "2023-01-01", "query_end": "2024-12-31",
                      "fit_cutoff": TRAIN_END, "fit_inclusive": True, "freeze_date": "2022-12-31"},
}


def _day(value: Any) -> str:
    """Chỉ nhận ngày ISO gốc, không tự sửa ngày khai sai."""
    if type(value) is not str:
        raise ValueError("Ngày index/scaler phải là chuỗi ISO")
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("Ngày không chuẩn")
    except ValueError as exc:
        raise ValueError("Ngày index/scaler phải có định dạng YYYY-MM-DD") from exc
    return value


def _json_bytes(value: Any) -> bytes:
    """JSON chuẩn hóa chỉ chứa kiểu Python gốc và số hữu hạn."""
    def check(item: Any) -> None:
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("Khóa JSON phải là chuỗi gốc")
            for child in item.values():
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        elif item is not None and type(item) not in (str, bool, int, float):
            raise ValueError("Index chứa kiểu JSON không nguyên bản")
    check(value)
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Index chứa số không hữu hạn hoặc JSON không hợp lệ") from exc


def _hash(value: Any) -> str:
    """Băm nội dung JSON xác định, không phụ thuộc thứ tự khóa."""
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _runtime() -> dict[str, Any]:
    """Ghim mã thực thi bằng text LF và runtime thực, tách khỏi lock W5."""
    root = Path(__file__).resolve().parents[1]
    return {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
            "code_sha256": {name: hashlib.sha256((root / name).read_text("utf-8").encode("utf-8")).hexdigest()
                            for name in ("core/pit_price_features.py", "core/price_feature_index.py",
                                         "core/prior_context.py")}}


def _source(value: Any) -> dict[str, str]:
    """Giữ hợp đồng nguồn giá thô; không đổi đơn vị trong index."""
    if (type(value) is not dict or set(value) != set(SOURCE_FIELDS)
            or any(type(item) is not str for item in value.values())
            or value["source_library"] != "vnstock" or value["primary_source"] not in ("VCI", "KBS")
            or value["price_basis"] != "UNADJUSTED_EXECUTION" or value["price_unit"] != "thousand_VND"):
        raise ValueError("Nguồn index phải là giá thô vnstock/VCI/KBS, nghìn VND")
    return deepcopy(value)


def _material(prices: dict[str, tuple[pd.DataFrame, list[dict[str, Any]]]],
              calendar: pd.DatetimeIndex) -> dict[str, Any]:
    """Băm prefix train để kiểm cùng dữ liệu khi nối archive OOS đã xác minh."""
    result: dict[str, Any] = {}
    for symbol in SYMBOLS:
        frame, events = prices[symbol]
        prefix = frame.loc[pd.to_datetime(frame["Datetime"]) <= pd.Timestamp(TRAIN_END),
                           ["Datetime", "Open", "High", "Low", "Close", "Volume", "Reference"]].copy()
        prefix["Datetime"] = pd.to_datetime(prefix["Datetime"]).dt.strftime("%Y-%m-%d")
        # Evidence VCI dùng cả YYYY-MM-DD và ISO tại 00:00:00; cùng quy tắc extractor.
        try:
            event_days = pd.DatetimeIndex(pd.to_datetime(
                [event["exrightDate"] for event in events if event.get("exrightDate") not in (None, "")],
                format="mixed", errors="raise"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Ngày quyền trong nguồn index không hợp lệ") from exc
        if event_days.hasnans or event_days.tz is not None or not event_days.equals(event_days.normalize()):
            raise ValueError("Ngày quyền trong nguồn index không phải ngày giao dịch gốc")
        result[symbol] = {
            "prices_sha256": _hash({"columns": list(prefix.columns), "rows": prefix.to_numpy().tolist()}),
            "events_sha256": _hash(sorted(event_days[event_days <= pd.Timestamp(TRAIN_END)].strftime("%Y-%m-%d").tolist())),
        }
    result["calendar_sha256"] = _hash(calendar[calendar <= pd.Timestamp(TRAIN_END)].strftime("%Y-%m-%d").tolist())
    return result


def _fit(records: list[dict[str, Any]], symbol: str, fold: dict[str, Any]) -> dict[str, Any]:
    """Fit population variance trên đúng episode đã đóng trước biên fold."""
    rows = [row for row in records if row["symbol"] == symbol and row["features"]["status"] == "AVAILABLE"
            and (row["exit_date"] <= fold["fit_cutoff"] if fold["fit_inclusive"]
                 else row["exit_date"] < fold["fit_cutoff"])]
    result = {"symbol": symbol, "fit_cutoff": fold["fit_cutoff"],
              "fit_inclusive": fold["fit_inclusive"], "freeze_date": fold["freeze_date"],
              "fit_episode_ids": [row["episode_id"] for row in rows], "fit_count": len(rows),
              "fit_min_exit_date": min((row["exit_date"] for row in rows), default=None),
              "fit_max_exit_date": max((row["exit_date"] for row in rows), default=None),
              "status": "AVAILABLE" if len(rows) >= 2 else "SCALER_UNAVAILABLE",
              "reason": None if len(rows) >= 2 else "FIT_COUNT_BELOW_TWO",
              "mean": None, "variance": None, "scale": None, "zero_variance": None}
    if len(rows) >= 2:
        matrix = np.asarray([row["features"]["vector"] for row in rows], dtype=float)
        with np.errstate(over="ignore", invalid="ignore"):
            mean = matrix.mean(axis=0)
            variance = ((matrix - mean) ** 2).mean(axis=0)
            scale = np.where(variance > 0, np.sqrt(variance), 1.)
        if not all(np.isfinite(item).all() for item in (mean, variance, scale)):
            raise ValueError("Tham số scaler không hữu hạn")
        result.update(mean=mean.tolist(), variance=variance.tolist(), scale=scale.tolist(),
                      zero_variance=(variance == 0).tolist())
    return result


def build_price_feature_index(*, records: list[dict[str, Any]],
                              prices: dict[str, tuple[pd.DataFrame, list[dict[str, Any]]]],
                              calendar: pd.DatetimeIndex, source: dict[str, str],
                              provenance: dict[str, Any]) -> PriceFeatureIndex:
    """Producer từ nguồn đã xác minh; adapter là biên kiểm byte/evidence production.

    records chỉ là phép chiếu ID/mã/cutoff/exit, tuyệt đối không nhận outcome.
    Không nạp archive đánh giá, fit HMM hoặc thay đổi bank đầu vào.
    """
    source = _source(source)
    if type(prices) is not dict or set(prices) != set(SYMBOLS) or not isinstance(calendar, pd.DatetimeIndex):
        raise ValueError("Index cần đủ nguồn bốn mã và lịch VNINDEX")
    if (type(provenance) is not dict or set(provenance) != {"bank", "prices", "calendar"}
            or type(provenance["prices"]) is not dict or set(provenance["prices"]) != set(SYMBOLS)):
        raise ValueError("Index thiếu provenance bank/giá/lịch đã kiểm")
    # Hash nguồn thật do adapter cấp; không nhận lời khai thiếu/sai checksum.
    for group in (provenance["bank"], provenance["calendar"], *provenance["prices"].values()):
        if type(group) is not dict or not group:
            raise ValueError("Provenance index không hợp lệ")
        hashes = [value for key, value in group.items() if key.endswith("sha256")]
        if not hashes or any(type(value) is not str or len(value) != 64
                             or any(char not in "0123456789abcdef" for char in value) for value in hashes):
            raise ValueError("Provenance index thiếu checksum SHA256")
    if set(provenance["prices"]) != set(SYMBOLS) or type(records) is not list or not records:
        raise ValueError("Index thiếu nguồn/mã hoặc episode")
    indexed, ids, cycles = [], set(), set()
    for row in records:
        if type(row) is not dict or set(row) != {"episode_id", "symbol", "as_of_date", "exit_date"}:
            raise ValueError("Index chỉ nhận ID/mã/cutoff/exit, không nhận nhãn")
        symbol, episode_id = row["symbol"], row["episode_id"]
        cutoff, exit_date = _day(row["as_of_date"]), _day(row["exit_date"])
        if (type(symbol) is not str or symbol not in SYMBOLS or type(episode_id) is not str
                or not episode_id.strip() or episode_id in ids or (symbol, cutoff) in cycles
                or not cutoff < exit_date <= TRAIN_END or pd.Timestamp(exit_date) not in calendar):
            raise ValueError("Episode index trùng/thiếu ID, sai mã hoặc ngày train")
        ids.add(episode_id)
        cycles.add((symbol, cutoff))
        frame, events = prices[symbol]
        indexed.append({**deepcopy(row), "features": extract_pit_price_features(
            frame, events, calendar, cutoff, source=source)})
    indexed.sort(key=lambda row: row["episode_id"])
    payload = {"index_version": INDEX_VERSION, "scaler_version": SCALER_VERSION,
               "feature_version": FEATURE_VERSION, "price_policy_version": PRICE_POLICY_VERSION,
               "feature_columns": list(FEATURE_COLUMNS), "folds": deepcopy(_FOLDS), "source": source,
               "runtime": _runtime(), "provenance": deepcopy(provenance),
               "train_material": _material(prices, calendar), "records": indexed,
               "scalers": {fold_id: {symbol: _fit(indexed, symbol, fold) for symbol in SYMBOLS}
                           for fold_id, fold in _FOLDS.items()}}
    _json_bytes(payload)
    return PriceFeatureIndex(payload, _verified=_VERIFIED)


def save_price_feature_index(index: PriceFeatureIndex, path: Path) -> str:
    """Ghi nguyên tử một lần; không ghi đè artifact khác dù cùng tên."""
    if not isinstance(index, PriceFeatureIndex):
        raise ValueError("Cần index đã xác minh")
    content = _json_bytes({"payload": index.payload, "sha256": index.identity}) + b"\n"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise ValueError("Index đã tồn tại với identity khác; cần đường dẫn mới") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return hashlib.sha256(content).hexdigest()


def load_price_feature_index(path: Path, *, expected_sha256: str | None = None,
                            **verified_inputs: Any) -> PriceFeatureIndex:
    """Kiểm byte/envelope rồi tái tạo semantic đúng nguồn một lần trước hot query."""
    content = Path(path).read_bytes()
    if expected_sha256 is not None and hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError("Checksum byte index không khớp")
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Index JSON trùng khóa")
            result[key] = value
        return result
    try:
        envelope = json.loads(content, object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Không đọc được JSON index") from exc
    if (type(envelope) is not dict or set(envelope) != {"payload", "sha256"}
            or envelope["sha256"] != _hash(envelope["payload"])):
        raise ValueError("Envelope index sai hash/schema")
    expected = build_price_feature_index(**verified_inputs)
    if _json_bytes(envelope["payload"]) != _json_bytes(expected.payload):
        raise ValueError("Index/scaler khác nguồn, phiên bản, vector hoặc fit provenance đã xác minh")
    return expected


class PriceFeatureIndex:
    """Cache đã kiểm; chỉ transform trên RAM, không I/O hoặc refit trong query."""

    def __init__(self, payload: dict[str, Any], *, _verified: object) -> None:
        if _verified is not _VERIFIED:
            raise ValueError("Chỉ producer/loader được tạo cache index")
        self._payload = deepcopy(payload)
        self._identity = _hash(payload)
        self._records = {row["episode_id"]: row for row in self._payload["records"]}
        self._scaler_hashes = {
            (fold_id, symbol): _hash({"scaler_version": SCALER_VERSION, "feature_version": FEATURE_VERSION,
                                    "fold_id": fold_id, **scaler})
            for fold_id, scalers in self._payload["scalers"].items() for symbol, scaler in scalers.items()}

    @property
    def identity(self) -> str:
        """Hash nội dung index/scaler/source đã khóa."""
        return self._identity

    @property
    def payload(self) -> dict[str, Any]:
        """Bản sao sở hữu; caller không sửa cache bằng kết quả trả về."""
        return deepcopy(self._payload)

    def verify_query_sources(self, *, prices: dict[str, tuple[pd.DataFrame, list[dict[str, Any]]]],
                             calendar: pd.DatetimeIndex, source: dict[str, str],
                             bank: dict[str, Any]) -> None:
        """Kiểm prefix train khi nối nguồn query/OOS; gọi một lần ngoài hot query."""
        if (type(prices) is not dict or set(prices) != set(SYMBOLS)
                or not isinstance(calendar, pd.DatetimeIndex)):
            raise ValueError("Nguồn query/OOS thiếu bốn mã hoặc lịch VNINDEX")
        if (_source(source) != self._payload["source"] or bank != self._payload["provenance"]["bank"]
                or _material(prices, calendar) != self._payload["train_material"]):
            raise ValueError("Nguồn query/OOS không bảo toàn bank và prefix train của index")

    def scaler(self, symbol: str, as_of_date: str, *, fold_id: str | None = None) -> dict[str, Any]:
        """Chọn fold theo ngày; caller khai fold khác bị từ chối, không fallback."""
        cutoff = _day(as_of_date)
        if type(symbol) is not str or symbol not in SYMBOLS:
            raise ValueError("Mã scaler không hợp lệ")
        matches = [name for name, fold in _FOLDS.items() if fold["query_start"] <= cutoff <= fold["query_end"]]
        if len(matches) != 1 or fold_id is not None and fold_id != matches[0]:
            raise ValueError("Fold scaler sai cutoff hoặc ngoài giao thức validation/OOS")
        name = matches[0]
        return {"fold_id": name, "index_sha256": self.identity, "scaler_version": SCALER_VERSION,
                "scaler_sha256": self._scaler_hashes[(name, symbol)],
                **deepcopy(self._payload["scalers"][name][symbol])}

    def closed_episode_ids(self, symbol: str, as_of_date: str) -> list[str]:
        """Population PIT giữ cả episode thiếu feature; không dùng outcome để lọc."""
        cutoff = _day(as_of_date)
        if type(symbol) is not str or symbol not in SYMBOLS:
            raise ValueError("Mã population không hợp lệ")
        return [key for key, row in self._records.items() if row["symbol"] == symbol and row["exit_date"] < cutoff]

    def _scaled(self, features: dict[str, Any], scaler: dict[str, Any]) -> dict[str, Any]:
        """Biến đổi vector hoặc giữ reason coverage đã xác minh; không cắt outlier."""
        status = features["status"] if scaler["status"] == "AVAILABLE" else "SCALER_UNAVAILABLE"
        scaled = None
        if status == "AVAILABLE":
            with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                vector = (np.asarray(features["vector"]) - scaler["mean"]) / scaler["scale"]
            if not np.isfinite(vector).all():
                raise ValueError("Vector đã scale không hữu hạn")
            scaled = vector.tolist()
        return {"status": status, "raw_vector": deepcopy(features["vector"]), "scaled_vector": scaled,
                "feature_status": features["status"], "feature_reasons": list(features["reasons"]),
                "fold_id": scaler["fold_id"], "index_sha256": self.identity,
                "scaler_sha256": scaler["scaler_sha256"],
                "scaler_version": SCALER_VERSION, "scaler_status": scaler["status"]}

    def transform_query(self, symbol: str, as_of_date: str, features: dict[str, Any], *,
                        fold_id: str | None = None) -> dict[str, Any]:
        """Nhận kết quả extractor tin cậy; adapter kiểm nguồn trước biên thuần này."""
        scaler = self.scaler(symbol, as_of_date, fold_id=fold_id)
        _json_bytes(features)
        required = {"feature_version", "price_policy_version", "feature_columns", "as_of_date",
                    "feature_end_date", "status", "reasons", "vector", "source", "coverage"}
        if (type(features) is not dict or not required.issubset(features)
                or set(features) - required - {"symbol", "source_provenance"}
                or features.get("feature_version") != FEATURE_VERSION
                or features.get("price_policy_version") != PRICE_POLICY_VERSION
                or features.get("feature_columns") != list(FEATURE_COLUMNS)
                or features.get("as_of_date") != as_of_date or features.get("source") != self._payload["source"]
                or features.get("symbol", symbol) != symbol):
            raise ValueError("Feature query sai nguồn, phiên bản, mã hoặc cutoff")
        status, vector, reasons = features.get("status"), features.get("vector"), features.get("reasons")
        coverage = features.get("coverage")
        if (type(coverage) is not dict or set(coverage) != {
                "required_bars", "expected_bars", "available_bars", "start_date", "end_date",
                "missing_sessions", "barrier_dates", "zero_volume_count"}
                or type(reasons) is not list or any(type(reason) is not str for reason in reasons)
                or len(set(reasons)) != len(reasons)
                or any(type(coverage[key]) is not int or coverage[key] < 0
                       for key in ("required_bars", "expected_bars", "available_bars", "zero_volume_count"))
                or coverage["required_bars"] != 21
                or not coverage["available_bars"] <= coverage["expected_bars"] <= 21
                or coverage["zero_volume_count"] > coverage["available_bars"]
                or coverage["end_date"] != features["feature_end_date"]):
            raise ValueError("Feature query thiếu coverage/reason")
        for key in ("start_date", "end_date"):
            if coverage[key] is not None and _day(coverage[key]) > as_of_date:
                raise ValueError("Coverage query chứa ngày tương lai")
        for key in ("missing_sessions", "barrier_dates"):
            days = coverage[key]
            if (type(days) is not list or any(_day(day) > as_of_date for day in days)
                    or days != sorted(days)
                    or key == "missing_sessions" and len(days) != len(set(days))):
                raise ValueError("Coverage query có phiên thiếu trùng, sai thứ tự hoặc tương lai")
        if bool(coverage["barrier_dates"]) != ("CORPORATE_ACTION_WINDOW" in reasons):
            raise ValueError("Reason quyền không khớp coverage query")
        if status == "AVAILABLE":
            if (reasons or features.get("feature_end_date") != as_of_date or type(vector) is not list
                    or len(vector) != 4 or any(type(value) not in (int, float) for value in vector)
                    or coverage.get("required_bars") != 21 or coverage.get("available_bars") != 21
                    or coverage.get("expected_bars") != 21 or coverage.get("missing_sessions") != []
                    or coverage.get("barrier_dates") != [] or coverage.get("end_date") != as_of_date):
                raise ValueError("Feature query AVAILABLE không đủ bốn chiều/21 phiên PIT")
        elif status != "UNAVAILABLE" or vector is not None or not reasons or any(
                reason not in ("INSUFFICIENT_HISTORY", "MISSING_CUTOFF", "MISSING_SESSION", "CORPORATE_ACTION_WINDOW")
                for reason in reasons):
            raise ValueError("Feature query UNAVAILABLE thiếu reason đã xác minh")
        return self._scaled(features, scaler)

    def prior_features(self, symbol: str, as_of_date: str, episode_ids: list[str], *,
                       fold_id: str | None = None) -> list[dict[str, Any]]:
        """Scale prior theo fold query, chặn ID lạ/trùng và exit≥query trước sử dụng."""
        scaler = self.scaler(symbol, as_of_date, fold_id=fold_id)
        if (type(episode_ids) is not list or any(type(key) is not str for key in episode_ids)
                or len(set(episode_ids)) != len(episode_ids)):
            raise ValueError("Danh sách ID prior thiếu hoặc trùng")
        rows = []
        for key in episode_ids:
            row = self._records.get(key)
            if row is None or row["symbol"] != symbol or row["exit_date"] >= as_of_date:
                raise ValueError("ID prior không có trong index, sai mã hoặc rò rỉ ngày thoát")
            rows.append({"episode_id": key, "as_of_date": row["as_of_date"], "exit_date": row["exit_date"],
                         **self._scaled(row["features"], scaler)})
        return rows
