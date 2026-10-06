"""Nguồn PIT đã kiểm và tín hiệu Full; không fit, crawl hoặc gọi LLM."""

from __future__ import annotations

from copy import deepcopy
from collections import Counter
from datetime import date
import hashlib
from importlib.metadata import version
from pathlib import Path
import platform
import re
from typing import Any

import pandas as pd

from core.bayesian_memory import SYMBOLS, exact_object, iso_date, read_json
from core.bayesian_retriever import BayesianPriorRetriever, VERSIONS, normalize_signals
from core.execution_prices import PRICE_COLUMNS, load_verified_execution_data, raw_point_in_time_snapshot, validate_raw_frame
from core.historical_runner import HistoricalMemoryRunner, PrefixRegimeProvider
from core.historical_signals import CODE_FILES, MODEL_CONFIG_KEYS, FrozenSentimentSnapshot, digest, native_json, report_signal, snapshot_payload
from core.prior_config import PriorConfig, _relative_path, copy_prior_json, normalize_prior_config, validate_prior_execution
from core.regime_detector import FEATURE_COLUMNS, MarketRegimeDetector, build_regime_features, training_data_hash

ROOT = Path(__file__).resolve().parents[1]
REPORT_FIELDS = ("indicator_report", "pattern_report", "trend_report", "alpha_report", "sentiment_report")
_LABELS = {"trend": ("Hướng xu hướng", "Trend direction"),
           "pattern": ("Thiên lệch dự báo", "Directional bias"),
           "indicator_consensus": ("Đồng thuận chủ đạo", "Dominant consensus")}
_FORBIDDEN = {"outcome", "actual_direction", "actual_pct_change", "entry_date", "exit_date",
              "entry_open", "exit_close", "net_return", "net_return_pct", "current_regime", "regime_name"}


class _SourceFiles:
    """Ghim byte nguồn một lần; phát hiện thay đổi và symlink thoát repo."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        self.hashes: dict[str, str] = {}

    def path(self, relative: str) -> Path:
        """Kiểm cú pháp/containment trước mọi lần đọc, kể cả sau đổi symlink."""
        _relative_path(relative, "source_path")
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Đường dẫn nguồn resolve ra ngoài repo")
        return path

    def pin(self, relative: str, expected: str | None = None) -> str:
        """Đối chiếu hash khai trong manifest với byte thật, không cập nhật hash cũ."""
        checksum = hashlib.sha256(self.path(relative).read_bytes()).hexdigest()
        if (expected is not None and (type(expected) is not str or expected != checksum)
                or relative in self.hashes and self.hashes[relative] != checksum):
            raise ValueError(f"Nguồn thay đổi hoặc sai checksum: {relative}")
        self.hashes[relative] = checksum
        return checksum

    def verify(self, paths: set[str]) -> None:
        """Kiểm byte các nguồn đã ghim; không parse JSON hoặc tự thay nguồn."""
        for relative in sorted(paths):
            self.pin(relative, self.hashes[relative])


def _checked_snapshot(frame: pd.DataFrame, cutoff: str) -> pd.DataFrame:
    """Snapshot được khai PIT phải sạch sẵn; không cắt nến tương lai để che lỗi."""
    if not isinstance(frame, pd.DataFrame) or list(frame.columns) != list(PRICE_COLUMNS):
        raise ValueError("Snapshot phải có đúng sáu cột OHLCV")
    result = frame.copy(deep=True)
    result["Datetime"] = pd.to_datetime(result["Datetime"], errors="raise")
    validate_raw_frame(result)
    if result.Datetime.iloc[-1] != pd.Timestamp(cutoff) or (result.Datetime > pd.Timestamp(cutoff)).any():
        raise ValueError("Snapshot/feature có nến tương lai hoặc thiếu phiên cutoff")
    return result.reset_index(drop=True)


def _signal_config(value: dict[str, Any], window_size: int) -> dict[str, Any]:
    """Khóa cấu hình bên tạo Full, không đưa credentials hoặc map tùy ý vào proof."""
    result = copy_prior_json(value)
    exact_object(result, {"models", "window_size", "norm_method", "alpha_weights", "language", "time_frame"})
    exact_object(result["models"], MODEL_CONFIG_KEYS)
    if (type(result["window_size"]) is not int or result["window_size"] != window_size
            or result["language"] not in ("vi", "en") or result["time_frame"] != "1d"
            or result["norm_method"] not in ("zscore_tanh", "minmax", "rank")):
        raise ValueError("Cấu hình Full khác window/daily/ngôn ngữ đã khóa")
    for key, value in result["models"].items():
        if key.endswith("_model") and (type(value) is not str or not value.strip()):
            raise ValueError("Tên model Full không hợp lệ")
        if key.endswith("_max_tokens") and (type(value) is not int or value <= 0):
            raise ValueError("Token model Full phải là int dương")
        if key.endswith("_temperature") and (type(value) not in (int, float) or not 0 <= value <= 2):
            raise ValueError("Temperature model Full không hợp lệ")
    if result["alpha_weights"] is not None and type(result["alpha_weights"]) is not dict:
        raise ValueError("Alpha weights phải là object hoặc None")
    weights = result["alpha_weights"]
    if weights is not None and (set(weights) - {"ic", "acc", "sharpe"}
            or any(type(value) not in (int, float) or value < 0 for value in weights.values())
            or sum(weights.values()) <= 0):
        raise ValueError("Alpha weights phải có trọng số hợp lệ cho ic/acc/sharpe")
    return result


def _runtime_identity() -> dict[str, str]:
    """Ghi runtime thực của bên tạo Full mới, không mượn identity lịch sử."""
    return {"python": platform.python_version(), **{name: version(name) for name in
            ("numpy", "pandas", "scipy", "TA-Lib", "langgraph", "langchain-core", "langchain-groq")}}


def _signals(reports: dict[str, str], factors: list[dict[str, Any]],
             sentiment: FrozenSentimentSnapshot, compat: dict[str, str] | None = None) -> dict[str, str]:
    """Đọc hướng duy nhất, đối chiếu bảng năm Alpha và sentiment nguồn PIT."""
    exact_object(reports, set(REPORT_FIELDS))
    if any(type(value) is not str or not value.strip()
           or value.strip() in ("No data.", "Không có dữ liệu.") for value in reports.values()):
        raise ValueError("Shared Full thiếu báo cáo")
    signals = {}
    for name, labels in _LABELS.items():
        field = "indicator_report" if name == "indicator_consensus" else f"{name}_report"
        try:
            signals[name] = report_signal(reports[field], labels)
        except ValueError:
            # Chỉ replay có biên bản parser đã đóng băng mới nhận trường viết tắt.
            if name != "trend" or not compat or digest(reports[field]) not in compat:
                raise
            cleaned = reports[field].replace("**", "")
            if re.search(r"^\s*(?:[-*]\s*)?(?:Hướng xu hướng|Trend direction)\s*:", cleaned, re.I | re.M):
                raise
            fields = re.findall(r"^\s*(?:[-*]\s*)?Hướng xu\s*:\s*([^\n]+)", cleaned, re.I | re.M)
            if len(fields) != 1 or len(re.findall(r"\bHướng xu\s*:", cleaned, re.I)) != 1:
                raise
            direction = re.split(r"\s+(?=(?:Mức h|Mức k|Độ dốc đường xu)\s*:|Giá so với h(?:\s|[.:]|$))",
                                 fields[0], maxsplit=1, flags=re.I)[0].strip()
            if not re.fullmatch(r"(?:Tăng|Giảm|Đi ngang|Trung tính|Hỗn hợp)[.!]?", direction, re.I):
                raise
            parsed = report_signal(f"Hướng xu hướng: {direction}", labels)
            if parsed != compat[digest(reports[field])]:
                raise ValueError("Hướng viết tắt khác biên bản parser")
            signals[name] = parsed
    if (type(factors) is not list or len(factors) != 5
            or any(type(item) is not dict or type(item.get("id")) is not int
                   or item["id"] <= 0 or item.get("signal") not in {"TĂNG", "GIẢM", "TRUNG TÍNH"} for item in factors)
            or len({item["id"] for item in factors}) != 5):
        raise ValueError("Shared Full cần năm Alpha ID/tín hiệu khác nhau")
    rows = []
    labels = {"TĂNG": "BULLISH", "GIẢM": "BEARISH", "TRUNG TÍNH": "NEUTRAL",
              "UP": "BULLISH", "DOWN": "BEARISH", "NEUTRAL": "NEUTRAL",
              "BULLISH": "BULLISH", "BEARISH": "BEARISH"}
    for line in reports["alpha_report"].splitlines():
        cells = [part.strip() for part in line.strip().split("|")[1:-1]]
        if cells and cells[0].isdigit():
            if len(cells) != 6:
                raise ValueError("Bảng Alpha sai sáu cột")
            label = re.sub(r"[^\w\s]", "", cells[4]).strip().upper()
            if label not in labels:
                raise ValueError("Bảng Alpha thiếu hướng chuẩn")
            rows.append((int(cells[0]), labels[label]))
    if rows != [(item["id"], labels[item["signal"]]) for item in factors]:
        raise ValueError("Báo cáo Alpha khác năm factor thực chạy")
    directions = [item["signal"] for item in factors]
    up, down = directions.count("TĂNG"), directions.count("GIẢM")
    consensus = "BULLISH" if up > down else "BEARISH" if down > up else "NEUTRAL"
    if report_signal(reports["alpha_report"], ("TỔNG HỢP", "SUMMARY")) != consensus:
        raise ValueError("Tổng hợp Alpha khác đồng thuận năm factor")
    if reports["sentiment_report"] != sentiment.report:
        raise ValueError("Báo cáo sentiment khác snapshot tin PIT")
    signals["alpha_consensus"] = consensus
    signals["sentiment"] = {"positive": "POSITIVE", "negative": "NEGATIVE", "neutral": "NEUTRAL"}[
        sentiment.data["main_sentiment"]["label"]]
    return normalize_signals(signals)


class PriorContextAdapter:
    """Nạp nguồn đã xác minh một lần; chuẩn bị từng điểm trước upstream.

    Provider/model độc lập với prior_config. root chỉ định vùng dữ liệu của repo;
    code identity của Full mới lấy từ package đang thực chạy. Không tạo artifact.
    """

    def __init__(self, prior_config: PriorConfig | dict[str, Any], *, root: Path = ROOT,
                 execution_dir: str = "data/execution_prices",
                 news_dir: str = "outputs/historical_memory_run/inputs/news",
                 vnindex_manifest_path: str = "data/historical/manifest.json",
                 provider_mode: str = "historical_prefix", prefix_artifact_dir: str | None = None,
                 frozen_artifact_path: str | None = None, freeze_as_of_date: str | None = None,
                 window_size: int = 45, signal_config: dict[str, Any] | None = None,
                 retriever: BayesianPriorRetriever | None = None) -> None:
        self._config = normalize_prior_config(prior_config)
        if not self._config["enable_bayesian_prior"]:
            raise ValueError("Adapter PIT chỉ khởi tạo khi prior enabled; disabled dùng đường legacy")
        if type(window_size) is not int or not 1 <= window_size <= 600:
            raise ValueError("Window phải là int trong 1..600")
        if provider_mode not in ("historical_prefix", "fixed_train_oos"):
            raise ValueError("Provider regime chưa được đặc tả")
        if provider_mode == "historical_prefix" and (frozen_artifact_path is not None or freeze_as_of_date is not None):
            raise ValueError("Replay không nhận model đóng băng OOS")
        if provider_mode == "fixed_train_oos" and (prefix_artifact_dir is not None
                or frozen_artifact_path is None or freeze_as_of_date is None):
            raise ValueError("OOS cần artifact/freeze riêng, không nhận prefix provider")
        self._files = _SourceFiles(root)
        self._window_size, self._mode = window_size, provider_mode
        self._signal_config = None if signal_config is None else _signal_config(signal_config, window_size)
        self._fresh_identity = None if self._signal_config is None else {
            "models": self._signal_config["models"], "runtime": _runtime_identity(),
            "code_sha256": {name: hashlib.sha256((ROOT / name).read_text("utf-8").encode("utf-8")).hexdigest()
                            for name in (*CODE_FILES, "core/prior_context.py")}}
        bank = {field: self._config[field] for field in ("bank_path", "manifest_path", "audit_path")}
        self._bank = {**bank, **{field.replace("_path", "_sha256"): self._files.pin(path)
                                for field, path in bank.items()}, "versions": dict(VERSIONS)}
        self._bank_manifest = read_json(self._files.path(bank["manifest_path"]))
        audit = read_json(self._files.path(bank["audit_path"]))
        if type(self._bank_manifest) is not dict or type(audit) is not dict:
            raise ValueError("Manifest/QA kho phải là object")
        self._retriever = retriever or BayesianPriorRetriever(**{field: self._files.path(path) for field, path in bank.items()})
        if (not isinstance(self._retriever, BayesianPriorRetriever)
                or self._retriever._bank_sha256 != self._bank["bank_sha256"]
                or self._bank_manifest.get("bank_sha256") != self._bank["bank_sha256"]
                or audit.get("bank_sha256") != self._bank["bank_sha256"] or audit.get("status") != "PASS"
                or audit.get("run_signature") != self._bank_manifest.get("run_signature")):
            raise ValueError("Retriever/QA khác kho đã ghim")
        records = self._retriever._memory.records
        if (audit.get("schema_sha256") != hashlib.sha256((ROOT / "docs/plan/week1/historical_task_record.schema.json").read_bytes()).hexdigest()
                or type(self._bank_manifest.get("run_signature")) is not str
                or re.fullmatch(r"[0-9a-f]{64}", self._bank_manifest["run_signature"]) is None
                or type(self._bank_manifest.get("remaining")) is not int or self._bank_manifest["remaining"] != 0
                or digest(read_json(self._files.path(bank["bank_path"]))) != digest(records)):
            raise ValueError("Schema/signature/nội dung kho khác retriever đã xác minh")
        for evidence in (self._bank_manifest, audit):
            if (type(evidence.get("format_version")) is not int or evidence["format_version"] != 1
                    or type(evidence.get("completed")) is not int or evidence["completed"] != len(records)):
                raise ValueError("Version/count kho sai kiểu hoặc giá trị")
            for field, counts in (("by_symbol", Counter(item["symbol"] for item in records)),
                                  ("by_regime", Counter(item["regime"] for item in records)),
                                  ("by_year", Counter(item["as_of_date"][:4] for item in records))):
                supplied = evidence.get(field)
                if (type(supplied) is not dict or any(type(value) is not int or value < 0 for value in supplied.values())
                        or {key: value for key, value in supplied.items() if value} != dict(counts)):
                    raise ValueError("Độ phủ kho/QA khác retriever đã xác minh")
        manifest_path = f"{execution_dir}/manifest.json"
        self._files.pin(manifest_path)
        self._price_manifest = read_json(self._files.path(manifest_path))
        if (type(self._price_manifest) is not dict or self._price_manifest.get("source_library") != "vnstock"
                or type(self._price_manifest.get("source_library_version")) is not str
                or not self._price_manifest["source_library_version"]
                or self._price_manifest.get("crosscheck_sources") != ["VCI", "KBS"]):
            raise ValueError("Nguồn/version giá phải là vnstock với crosscheck VCI/KBS")
        if type(self._price_manifest.get("files")) is not dict or set(self._price_manifest["files"]) != SYMBOLS:
            raise ValueError("Manifest giá thiếu bốn mã nghiên cứu")
        if not {"price_gate", "price_basis", "price_unit", "primary_source", "raw_field_map",
                "requested_start", "requested_end"}.issubset(self._price_manifest):
            raise ValueError("Manifest giá thiếu gate/schema/phạm vi thực thi")
        self._prices: dict[str, tuple[pd.DataFrame, list[dict[str, Any]]]] = {}
        self._price_sources, self._news_sources, self._articles = {}, {}, {}
        for symbol in sorted(SYMBOLS):
            item = self._price_manifest["files"][symbol]
            if type(item) is not dict or not {"csv", "evidence", "events", "rows"}.issubset(item):
                raise ValueError("Manifest giá thiếu CSV/evidence/events/rows")
            sources = {"manifest_path": manifest_path, "manifest_sha256": self._files.hashes[manifest_path]}
            for name in ("csv", "evidence", "events"):
                if type(item[name]) is not dict or not {"file", "sha256"}.issubset(item[name]):
                    raise ValueError("Manifest giá thiếu path/hash nguồn")
                relative = f"{execution_dir}/{item[name]['file']}"
                sources[f"{name}_path"] = relative
                sources[f"{name}_sha256"] = self._files.pin(relative, item[name]["sha256"])
            self._prices[symbol] = load_verified_execution_data(self._files.path(execution_dir), symbol)
            self._price_sources[symbol] = sources
            relative = f"{news_dir}/{symbol}.json"
            self._news_sources[symbol] = {"snapshot_path": relative, "snapshot_sha256": self._files.pin(relative)}
            news = read_json(self._files.path(relative))
            exact_object(news, {"symbol", "scored_articles"})
            if news["symbol"] != symbol or type(news["scored_articles"]) is not list:
                raise ValueError("Snapshot tin sai symbol/schema")
            self._articles[symbol] = copy_prior_json(news["scored_articles"])
            # Kiểm mọi ngày nguồn ngay lúc init, kể cả bài sẽ bị lọc ngoài cửa sổ.
            for article in self._articles[symbol]:
                if type(article) is not dict:
                    raise ValueError("Nguồn tin chứa bài sai schema")
                if article.get("date_parsed") not in (None, ""):
                    iso_date(article["date_parsed"])
        self._files.pin(vnindex_manifest_path)
        manifest = read_json(self._files.path(vnindex_manifest_path))
        if (type(manifest) is not dict or manifest.get("source_library") != "vnstock" or manifest.get("sources") != ["VCI", "KBS"]
                or manifest.get("primary_source") != "VCI" or manifest.get("interval") not in ("1d", "1D")):
            raise ValueError("Nguồn VNINDEX không phải vnstock/VCI/KBS daily")
        if (type(manifest.get("files")) is not dict or type(manifest["files"].get("VNINDEX")) is not dict
                or not {"file", "sha256"}.issubset(manifest["files"]["VNINDEX"])):
            raise ValueError("Manifest VNINDEX thiếu path/hash")
        item = manifest["files"]["VNINDEX"]
        csv_path = (Path(vnindex_manifest_path).parent / item["file"]).as_posix()
        self._vnindex_source = {"source_manifest_path": vnindex_manifest_path,
            "source_manifest_sha256": self._files.hashes[vnindex_manifest_path], "source_csv_path": csv_path,
            "source_csv_sha256": self._files.pin(csv_path, item["sha256"])}
        self._vnindex = pd.read_csv(self._files.path(csv_path), parse_dates=["Datetime"])
        validate_raw_frame(self._vnindex)
        self._fixed = None
        self._freeze = None
        self._artifact_dir = "outputs/historical_memory_run/regimes" if prefix_artifact_dir is None else prefix_artifact_dir
        if provider_mode == "historical_prefix":
            self._provider = PrefixRegimeProvider(self._files.path(self._artifact_dir), self._vnindex)
        else:
            self._freeze = iso_date(freeze_as_of_date)
            self._fixed_path = frozen_artifact_path
            self._files.pin(frozen_artifact_path)
            self._fixed = MarketRegimeDetector.load(self._files.path(frozen_artifact_path))
            if self._fixed.metadata["train_end_date"] > self._freeze:
                raise ValueError("Model được khai đóng băng trước khi train kết thúc")
        self._base_paths = set(self._files.hashes)
        self._files.verify(self._base_paths)
        self._regime_checks: dict[tuple[str, str, str], dict[str, Any]] = {}

    @property
    def prior_config(self) -> dict[str, Any]:
        """Cấu hình kho đã khóa; không cho caller sửa adapter."""
        return deepcopy(self._config)

    @property
    def signal_config(self) -> dict[str, Any]:
        """Cấu hình tạo Full mới; journal replay không thay cho cấu hình này."""
        if self._signal_config is None:
            raise ValueError("Backtest mới cần cấu hình Full đã khóa")
        return deepcopy(self._signal_config)

    def verify_sources(self) -> None:
        """Kiểm byte toàn bộ nguồn/artifact đã ghim, không nạp lại JSON/kho."""
        self._files.verify(set(self._files.hashes))

    def execution_data(self, symbol: str) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        """Bản sao giá thực thi và sự kiện trên RAM chỉ cấp cho lớp đánh giá."""
        self.verify_sources()
        if type(symbol) is not str or symbol not in SYMBOLS:
            raise ValueError("Symbol thực thi chưa hỗ trợ")
        frame, events = self._prices[symbol]
        return frame.copy(deep=True), deepcopy(events)

    def prepare(self, symbol: str, as_of_date: str, *, time_frame: str = "1d",
                point_in_time_df: pd.DataFrame | None = None,
                vnindex_prefix: pd.DataFrame | None = None) -> PriorPointContext:
        """Cắt archive đúng ngày hoặc kiểm snapshot caller khai PIT trước upstream."""
        _, _, timeframe = validate_prior_execution(self._config, is_backtest=True, time_frame=time_frame)
        cutoff = iso_date(as_of_date)
        if type(symbol) is not str or symbol not in SYMBOLS:
            raise ValueError("Symbol query chưa được hỗ trợ")
        self._files.verify(self._base_paths)
        if not iso_date(self._price_manifest["requested_start"]) <= cutoff <= iso_date(self._price_manifest["requested_end"]):
            raise ValueError("Cutoff ngoài phạm vi gate giá thực thi, chưa mở gate OOS")
        expected = raw_point_in_time_snapshot(self._prices[symbol][0], cutoff)
        snapshot = expected if point_in_time_df is None else _checked_snapshot(point_in_time_df, cutoff)
        if (snapshot.attrs.get("symbol", symbol) != symbol
                or digest(snapshot_payload(snapshot)) != digest(snapshot_payload(expected))):
            raise ValueError("Snapshot không khớp symbol/giá thực thi đã xác minh")
        if len(snapshot) < 600:
            raise ValueError("Thiếu 600 nến Alpha PIT")
        window, alpha = snapshot.tail(self._window_size), snapshot.tail(600)
        source = self._price_sources[symbol]
        prices = {key: self._price_manifest[key] for key in
                  ("source_library", "source_library_version", "primary_source", "crosscheck_sources", "price_basis", "price_unit")}
        prices.update(source, schema=list(PRICE_COLUMNS), snapshot_start_date=snapshot.Datetime.iloc[0].strftime("%Y-%m-%d"),
            snapshot_end_date=cutoff, snapshot_rows=int(len(snapshot)), snapshot_sha256=digest(snapshot_payload(snapshot)),
            window_size=self._window_size, window_rows=int(len(window)), window_end_date=cutoff,
            window_sha256=digest(snapshot_payload(window)), alpha_start_date=alpha.Datetime.iloc[0].strftime("%Y-%m-%d"),
            alpha_end_date=cutoff, alpha_rows=600, alpha_sha256=digest(snapshot_payload(alpha)))
        articles = self._articles[symbol]
        sentiment = FrozenSentimentSnapshot(symbol, cutoff, articles)
        excluded = {"undated": 0, "future": 0, "outside_window": 0}
        endpoint = date.fromisoformat(cutoff)
        for article in articles:
            published = article.get("date_parsed")
            if published in (None, ""):
                excluded["undated"] += 1
            elif published > cutoff:
                excluded["future"] += 1
            elif (endpoint - date.fromisoformat(published)).days > 90:
                excluded["outside_window"] += 1
        visible_dates = [item["date_parsed"] for item in sentiment.articles]
        news = {**self._news_sources[symbol], "source_articles_sha256": digest(articles),
            "visible_articles_sha256": digest(sentiment.articles), "input_count": len(articles),
            "visible_count": len(visible_dates), "excluded_counts": excluded,
            "coverage_start_date": min(visible_dates) if visible_dates else None,
            "coverage_end_date": max(visible_dates) if visible_dates else None, "window_days": 90, "min_articles": 3,
            "is_reliable": bool(sentiment.data["is_reliable"]), "model_used": sentiment.data["model_used"],
            "neutral_reason": None if sentiment.data["is_reliable"] else "INSUFFICIENT_DATED_HISTORY"}
        archive_prefix = self._vnindex.loc[self._vnindex.Datetime.between("2018-01-01", cutoff), PRICE_COLUMNS].copy()
        prefix = _checked_snapshot(archive_prefix if vnindex_prefix is None else vnindex_prefix, cutoff)
        if training_data_hash(prefix) != training_data_hash(archive_prefix):
            raise ValueError("VNINDEX prefix khác nguồn manifest đã xác minh")
        if self._mode == "historical_prefix":
            artifact = f"{self._artifact_dir}/VNINDEX-{cutoff}.json"
            artifact_hash = self._files.pin(artifact)
            verified = self._provider.get(cutoff, verify_only=True)
            HistoricalMemoryRunner._validate_regime(verified, cutoff)
            if verified["artifact_sha256"] != artifact_hash:
                raise ValueError("Artifact thay đổi trong lúc provider nạp")
            # Provider không được tự khai metadata/state khác artifact đã ghim.
            # Cache gắn đủ artifact/cutoff/prefix; không dùng endpoint ngày sau cho ngày trước.
            check_key = (artifact_hash, cutoff, training_data_hash(prefix))
            if check_key not in self._regime_checks:
                detector = MarketRegimeDetector.load(self._files.path(artifact), expected_training_hash=check_key[2])
                self._regime_checks[check_key] = copy_prior_json({"metadata": detector.metadata,
                    "state": detector.classify_regime(prefix, cutoff), "artifact_sha256": artifact_hash})
            if digest(copy_prior_json(verified)) != digest(self._regime_checks[check_key]):
                raise ValueError("Provider trả regime/metadata khác artifact và prefix PIT đã xác minh")
            state, metadata = verified["state"], verified["metadata"]
            frozen = None
        else:
            metadata = self._fixed.metadata
            if not metadata["train_end_date"] <= self._freeze < cutoff or metadata["train_end_date"] >= cutoff:
                raise ValueError("OOS yêu cầu train_end <= freeze < cutoff và train_end < cutoff")
            artifact, artifact_hash = self._fixed_path, self._files.hashes[self._fixed_path]
            state = self._fixed.classify_regime(prefix, cutoff)
            frozen = {"freeze_as_of_date": self._freeze, "artifact_sha256": artifact_hash,
                      "training_data_sha256": metadata["training_data_sha256"]}
        if state["feature_end_date"] != cutoff or state["as_of_date"] != cutoff:
            raise ValueError("Regime/feature không kết thúc tại cutoff daily")
        features = build_regime_features(prefix, cutoff)
        feature_payload = {"Datetime": features.Datetime.dt.strftime("%Y-%m-%d").tolist(),
                           **{key: features[key].astype(float).tolist() for key in FEATURE_COLUMNS}}
        regime = {**self._vnindex_source, "source_symbol": "VNINDEX", "inference_prefix_sha256": training_data_hash(prefix),
            "feature_sha256": digest(feature_payload), "artifact_path": artifact, "artifact_sha256": artifact_hash,
            "metadata": metadata, "state_sha256": digest(state),
            "component_train_end_dates": {name: metadata["train_end_date"] for name in ("hmm", "scaler", "calibration")},
            "frozen_model": frozen}
        proof = {"contract_version": "prior_provenance_v1",
            "context": {"symbol": symbol, "as_of_date": cutoff, "time_frame": timeframe, "provider_mode": self._mode},
            "prices": prices, "news": news, "regime": regime, "bank": self._bank}
        paths = self._base_paths | {artifact}
        self._files.verify(paths)
        return PriorPointContext(self, snapshot, sentiment, state, copy_prior_json(proof), paths)


class PriorPointContext:
    """Một điểm đã kiểm nguồn; seal Full rồi cung cấp cặp callback cho graph W4-08."""

    def __init__(self, adapter: PriorContextAdapter, snapshot: pd.DataFrame,
                 sentiment: FrozenSentimentSnapshot, regime: dict[str, Any],
                 proof: dict[str, Any], paths: set[str]) -> None:
        self._adapter, self._snapshot = adapter, snapshot.copy(deep=True)
        self._sentiment, self._regime = deepcopy(sentiment), deepcopy(regime)
        self._proof, self._paths = deepcopy(proof), set(paths)
        self._shared: dict[str, Any] | None = None
        self._results: dict[str, dict[str, Any]] = {}

    @property
    def prior_config(self) -> dict[str, Any]:
        """Trả cấu hình kho/query đã khóa để caller kiểm ma trận trước upstream."""
        return deepcopy(self._adapter._config)

    @property
    def source_provenance(self) -> dict[str, Any]:
        """Proof trước LLM chưa có nhóm signals; không nhập trực tiếp vào Decision."""
        return deepcopy(self._proof)

    def agent_state(self) -> dict[str, Any]:
        """Input upstream/Full PIT; prior chưa bật, không có outcome query."""
        self._adapter._files.verify(self._paths)
        if self._adapter._signal_config is None:
            raise ValueError("Full fresh cần cấu hình bên tạo reports đã khóa trước run")
        config = self._adapter._signal_config
        context = self._proof["context"]
        return {"stock_name": context["symbol"], "as_of_date": context["as_of_date"], "time_frame": "1d",
            "is_backtest": True, "language": config["language"], "messages": [],
            "point_in_time_df": self._snapshot.copy(deep=True),
            "kline_data": snapshot_payload(self._snapshot.tail(self._adapter._window_size)),
            "window_end_date": context["as_of_date"], "sentiment_store": deepcopy(self._sentiment),
            "alpha_norm_method": config["norm_method"], "alpha_weights": deepcopy(config["alpha_weights"])}

    def _seal(self, reports: dict[str, str], factors: list[dict[str, Any]], config: dict[str, Any],
              identity: dict[str, Any], origin: str, checkpoint_path: str | None = None,
              compat: dict[str, str] | None = None) -> dict[str, Any]:
        """Gắn reports/tín hiệu với nguồn đã kiểm, không đổi identity lịch sử."""
        self._adapter._files.verify(self._paths)
        config = _signal_config(config, self._adapter._window_size)
        reports, factors = native_json(reports), native_json(factors)
        signals = _signals(reports, factors, self._sentiment, compat)
        proof = deepcopy(self._proof)
        proof["signals"] = {"origin": origin, "checkpoint_path": checkpoint_path,
            "checkpoint_sha256": None if checkpoint_path is None else self._adapter._files.hashes[checkpoint_path],
            "reports_sha256": digest(reports), "signals_sha256": digest(signals), "config_sha256": digest(config),
            **copy_prior_json(identity)}
        context = proof["context"]
        shared = {"stock_name": context["symbol"], "as_of_date": context["as_of_date"], "time_frame": "1d",
            "is_backtest": True, "language": config["language"],
            "ablation_config": {"enable_alpha_factors": True, "enable_sentiment": True}, **reports,
            "prior_config": deepcopy(self._adapter._config), "market_regime": deepcopy(self._regime),
            "current_signals": signals, "prior_provenance": proof, "prior_tasks": [], "prior_stats": None,
            "prior_metadata": None, "bayesian_prior_context": ""}
        shared = copy_prior_json(shared)
        if self._shared is not None and digest(shared) != digest(self._shared):
            raise ValueError("Điểm đã seal Full không được thay reports/config/signals")
        self._shared = shared
        return deepcopy(shared)

    def bind_full(self, full_state: dict[str, Any]) -> dict[str, Any]:
        """Đối chiếu Full mới với input/cấu hình/tin PIT rồi seal JSON cho các nhánh."""
        expected = self.agent_state()
        if type(full_state) is not dict or _FORBIDDEN.intersection(full_state):
            raise ValueError("Full state chứa outcome query")
        for field in ("stock_name", "as_of_date", "time_frame", "is_backtest", "language", "window_end_date",
                      "alpha_norm_method", "alpha_weights", "kline_data"):
            if digest(full_state.get(field)) != digest(expected[field]):
                raise ValueError(f"Full state khác input đã khóa: {field}")
        snapshot = _checked_snapshot(full_state.get("point_in_time_df"), expected["as_of_date"])
        if digest(snapshot_payload(snapshot)) != self._proof["prices"]["snapshot_sha256"]:
            raise ValueError("Full state dùng giá khác snapshot đã kiểm")
        data = native_json(full_state.get("sentiment_data"))
        if type(data) is not dict or any(digest(data.get(key)) != digest(value) for key, value in self._sentiment.data.items()):
            raise ValueError("Full sentiment_data khác tin PIT/coverage đã kiểm")
        self._sentiment._validate(data)
        return self._seal({field: full_state.get(field) for field in REPORT_FIELDS}, data.get("alpha_results"),
                          self._adapter._signal_config, self._adapter._fresh_identity, "shared_full")

    def restore_full_bundle(self, bundle: dict[str, Any]) -> dict[str, Any]:
        """Tái dựng Full từ snapshot PIT rồi so seal, không gọi lại Alpha/vision."""
        bundle = copy_prior_json(bundle)
        if set(bundle) != {"reports", "current_signals", "market_regime", "prior_provenance", "alpha_factors", "sentiment_data"}:
            raise ValueError("Full bundle phục hồi thiếu field hoặc chứa outcome query")
        data = bundle["sentiment_data"]
        if type(data) is not dict or set(data).difference({*self._sentiment.data, "alpha_results", "sentiment_norm", "related_norm", "tech_vars"}):
            raise ValueError("Sentiment bundle chứa field ngoài projection Full")
        def reject_outcome(value: Any) -> None:
            if type(value) is dict:
                if {"outcome", "evaluation", "actual_direction", "entry_open", "exit_close", "net_return_long"}.intersection(value):
                    raise ValueError("Full bundle chứa outcome query")
                for child in value.values():
                    reject_outcome(child)
            elif type(value) is list:
                for child in value:
                    reject_outcome(child)
        reject_outcome(bundle)
        if digest(data.get("alpha_results")) != digest(bundle["alpha_factors"]):
            raise ValueError("Alpha factors khác bundle phục hồi")
        state = self.agent_state()
        state.update(bundle["reports"], sentiment_data=data)
        shared = self.bind_full(state)
        expected = {"reports": {field: shared[field] for field in REPORT_FIELDS},
            **{field: shared[field] for field in ("current_signals", "market_regime", "prior_provenance")},
            "alpha_factors": bundle["alpha_factors"], "sentiment_data": data}
        if digest(bundle) != digest(expected):
            raise ValueError("Full bundle/hash/tín hiệu/provenance khác nguồn PIT hiện tại")
        return shared

    def load_shared_checkpoint(self, run_dir: str) -> dict[str, Any]:
        """Đọc journal COMPLETE và episode/run đã ràng buộc, không invoke extractor."""
        if self._proof["context"]["provider_mode"] != "historical_prefix":
            raise ValueError("Journal replay chỉ dùng với provider prefix đúng ngày")
        files, context = self._adapter._files, self._proof["context"]
        symbol, cutoff = context["symbol"], context["as_of_date"]
        paths = [f"{run_dir}/run_manifest.json", f"{run_dir}/episodes/{symbol}-{cutoff}.json",
                 f"{run_dir}/signals/{symbol}-{cutoff}.json"]
        for path in paths:
            files.pin(path)
        self._paths.update(paths)
        run, episode, checkpoint = [HistoricalMemoryRunner._read_envelope(files.path(path)) for path in paths]
        if any(type(value) is not dict for value in (run, episode, checkpoint)):
            raise ValueError("Payload journal/run/episode phải là object")
        signature = digest(run)
        if signature != self._adapter._bank_manifest["run_signature"] or episode.get("signature") != signature:
            raise ValueError("Journal không thuộc run/signature của kho đã xác minh")
        if checkpoint.get("stage") != "COMPLETE" or type(checkpoint.get("result")) is not dict:
            raise ValueError("Checkpoint tín hiệu chưa COMPLETE")
        bundle = checkpoint["result"]
        reports = bundle.get("reports")
        if (type(reports) is not dict or digest(checkpoint.get("reports")) != digest({
                field: reports.get(field) for field in ("indicator_report", "pattern_report", "trend_report")})):
            raise ValueError("Reports upstream checkpoint khác Full đã hoàn thành")
        provenance = bundle.get("provenance")
        # Chữ ký W2 khóa input trước upstream, chưa có hash reports/five Alpha.
        signed_input = None if type(provenance) is not dict else {
            key: value for key, value in provenance.items() if key not in ("reports_sha256", "alpha_factors")}
        if type(provenance) is not dict or checkpoint.get("signature") != digest(signed_input):
            raise ValueError("Signature tín hiệu khác provenance bên tạo")
        config = _signal_config(provenance.get("config"), self._adapter._window_size)
        record, episode_proof = episode.get("record", {}), episode.get("provenance", {})
        if type(record) is not dict or type(episode_proof) is not dict:
            raise ValueError("Record/provenance episode phải là object")
        verified_regime = {"state": self._regime, "metadata": self._proof["regime"]["metadata"],
                           "artifact_sha256": self._proof["regime"]["artifact_sha256"]}
        expected_record = self._adapter._retriever._verified_by_id.get(f"{symbol}:{cutoff}")
        if (expected_record is None or any(digest(record.get(key)) != digest(expected_record[key]) for key in
                                          ("episode_id", "symbol", "as_of_date", "regime", "agent_signals"))
                or episode_proof.get("signal_checkpoint_sha256") != files.hashes[paths[2]]
                or digest(episode_proof.get("regime")) != digest(verified_regime)
                or bundle.get("symbol") != symbol or bundle.get("as_of_date") != cutoff
                or digest(config) != digest(run.get("signal_config")) or config["models"] != run.get("models")
                or provenance.get("reports_sha256") != digest(bundle.get("reports"))):
            raise ValueError("Episode/reports/config khác nguồn checkpoint đã kiểm")
        price, news = self._proof["prices"], self._proof["news"]
        expected = {"symbol": symbol, "as_of_date": cutoff, "price_basis": price["price_basis"],
            "price_source": price["primary_source"], "price_unit": price["price_unit"],
            "price_sha256": price["snapshot_sha256"], "price_start_date": price["snapshot_start_date"],
            "price_end_date": cutoff, "price_rows": price["snapshot_rows"],
            "alpha_start_date": price["alpha_start_date"], "alpha_end_date": cutoff,
            "news_sha256": news["visible_articles_sha256"], "news_count": news["visible_count"],
            "news_dates": [item["date_parsed"] for item in self._sentiment.articles],
            "news_is_reliable": news["is_reliable"], "sentiment_model": news["model_used"]}
        if any(digest(provenance.get(key)) != digest(value) for key, value in expected.items()):
            raise ValueError("Provenance checkpoint khác snapshot giá/tin/Alpha PIT")
        identity = {key: provenance.get(key) for key in ("runtime", "code_sha256")}
        identity["models"] = config["models"]
        if (type(identity["runtime"]) is not dict or set(identity["runtime"]) != set(_runtime_identity())
                or any(type(value) is not str or not value for value in identity["runtime"].values())
                or type(identity["code_sha256"]) is not dict or set(identity["code_sha256"]) != set(CODE_FILES)
                or any(type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
                       for value in identity["code_sha256"].values())
                or any(value != run.get("code_sha256", {}).get(key) for key, value in identity["code_sha256"].items())
                or any(value != run.get("runtime", {}).get(key) for key, value in identity["runtime"].items()
                       if key in run.get("runtime", {}))):
            raise ValueError("Identity code/runtime checkpoint khác run gốc")
        compat = self._compat(run_dir)
        signals = _signals(bundle.get("reports"), provenance.get("alpha_factors"), self._sentiment, compat)
        if digest(signals) != digest(bundle.get("agent_signals")) or signals != record["agent_signals"]:
            raise ValueError("Tín hiệu replay khác báo cáo hoặc episode")
        return self._seal(bundle.get("reports"), provenance.get("alpha_factors"), config, identity,
                          "historical_signal_checkpoint", paths[2], compat)

    def _compat(self, run_dir: str) -> dict[str, str]:
        """Đọc biên bản/parser đóng băng có hash; không thực thi mã parser lịch sử."""
        item = self._adapter._bank_manifest.get("report_parse_compat")
        if item is None:
            return {}
        files = self._adapter._files
        path = (Path(self._adapter._config["manifest_path"]).parent / item["file"]).as_posix()
        files.pin(path, item["sha256"])
        self._paths.add(path)
        payload = HistoricalMemoryRunner._read_envelope(files.path(path))
        exact_object(payload, {"format_version", "entries"})
        if type(payload["format_version"]) is not int or payload["format_version"] != 1 or type(payload["entries"]) is not list:
            raise ValueError("Biên bản parser sai schema/version")
        result = {}
        for entry in payload["entries"]:
            exact_object(entry, {"report_sha256", "signal", "parser_sha256", "rule"})
            if entry["rule"] != "abbreviated_trend_direction_v1" or entry["signal"] not in ("BULLISH", "BEARISH", "NEUTRAL"):
                raise ValueError("Biên bản parser chứa rule/hướng chưa đặc tả")
            parser = f"{run_dir}/{item['parser_sources'][entry['parser_sha256']]}"
            files.pin(parser, entry["parser_sha256"])
            self._paths.add(parser)
            if entry["report_sha256"] in result and result[entry["report_sha256"]] != entry["signal"]:
                raise ValueError("Biên bản parser chứa hướng mâu thuẫn")
            result[entry["report_sha256"]] = entry["signal"]
        return result

    def _query(self, projection: dict[str, Any]) -> dict[str, Any]:
        """Whitelist query W3 từ shared đã seal; không nối proof/outcome vào retriever."""
        if self._shared is None:
            raise ValueError("Chưa seal Full signals; không truy xuất prior")
        config, _, timeframe = validate_prior_execution(projection.get("prior_config"),
            is_backtest=projection.get("is_backtest"), time_frame=projection.get("time_frame"),
            ablation_config=projection.get("ablation_config"))
        if not config["enable_bayesian_prior"] or timeframe != "1d":
            raise ValueError("Callback nguồn chỉ nhận prior enabled/daily")
        if _FORBIDDEN.intersection(projection):
            raise ValueError("Projection chứa alias hoặc outcome query")
        for field in ("bank_path", "manifest_path", "audit_path"):
            if config[field] != self._adapter._config[field]:
                raise ValueError("Nhánh dùng kho khác nguồn đã kiểm")
        for field in ("stock_name", "as_of_date", "market_regime", "current_signals", "prior_provenance", *REPORT_FIELDS):
            if digest(copy_prior_json(projection.get(field))) != digest(self._shared[field]):
                raise ValueError(f"Projection khác shared/source đã seal: {field}")
        return {"symbol": self._shared["stock_name"], "as_of_date": self._shared["as_of_date"],
            "current_regime": self._regime["regime_name"], "current_signals": deepcopy(self._shared["current_signals"]),
            **{field: config[field] for field in ("mode", "k", "seed", "scope")}}

    def verify_source(self, projection: dict[str, Any]) -> None:
        """Hook graph: đối chiếu source/shared và result từ retriever đã nạp, không format."""
        query = self._query(projection)
        self._adapter._files.verify(self._paths)
        if projection.get("prior_metadata") is None:
            if projection.get("prior_tasks") != [] or projection.get("prior_stats") is not None or projection.get("bayesian_prior_context") != "":
                raise ValueError("Context trước retrieve có result/prefix còn sót")
        else:
            result = self._results.get(digest(query))
            actual = {key: copy_prior_json(projection.get(f"prior_{key}")) for key in ("tasks", "stats", "metadata")}
            if result is None or digest(actual) != digest(result):
                raise ValueError("Result khác retriever/eligible population đã xác minh")

    def retrieve(self, projection: dict[str, Any]) -> dict[str, Any]:
        """Callback graph gọi retrieve thật một lần, giữ bản sao result để hậu kiểm."""
        query = self._query(projection)
        self._adapter._files.verify(self._paths)
        result = self._adapter._retriever.retrieve(**query)
        self._results[digest(query)] = copy_prior_json(result)
        return copy_prior_json(result)
