"""Runner ghép regime prefix, tín hiệu và nhãn; journal nguyên tử sau mỗi điểm."""

from __future__ import annotations

import copy
import hashlib
from importlib.metadata import version
import os
from pathlib import Path
import platform
from typing import Any

import pandas as pd

from core.bayesian_memory import (
    DEFAULT_DATA_DIR, SYMBOLS, ExecutionLoader, HistoricalMemory, atomic_write_json,
    exact_object, iso_date, read_json, validate_historical_task_record,
)
from core.execution_prices import build_verified_cycle_schedule, load_verified_execution_data, raw_point_in_time_snapshot
from core.historical_outcomes import HistoricalOutcomeGenerator
from core.historical_signals import CODE_FILES, MODEL_CONFIG_KEYS, ROOT, digest, disk_articles, snapshot_payload
from core.regime_detector import (
    HMM_PARAMETERS, MarketRegimeDetector, training_data_hash, validate_regime_state,
)
from default_config import DEFAULT_CONFIG

RUNNER_CODE_FILES = (*CODE_FILES, "core/historical_outcomes.py", "core/historical_runner.py",
                     "core/regime_detector.py", "utils/historical_api.py", "scripts/run_historical_memory.py")


def load_vnindex_archive() -> pd.DataFrame:
    """Đọc VN-Index W1 khi checksum và hai provider VCI/KBS còn khớp manifest."""
    directory = ROOT / "data/historical"
    manifest = read_json(directory / "manifest.json")
    item = manifest["files"]["VNINDEX"]
    path = directory / item["file"]
    if (path.resolve().parent != directory.resolve() or manifest["source_library"] != "vnstock"
            or manifest["sources"] != ["VCI", "KBS"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]):
        raise ValueError("Nguồn hoặc checksum VNINDEX không hợp lệ")
    return pd.read_csv(path, parse_dates=["Datetime"])


class PrefixRegimeProvider:
    """Mỗi ngày quyết định có một HMM/scaler/calibration fit đúng prefix của ngày đó."""

    def __init__(self, artifact_dir: str | Path, archive: pd.DataFrame | None = None) -> None:
        self.artifact_dir = Path(artifact_dir)
        self.archive = load_vnindex_archive() if archive is None else archive.copy(deep=True)

    @property
    def input_hash(self) -> str:
        """Định danh dữ liệu nghiên cứu; không truyền archive tương lai vào model."""
        dates = pd.to_datetime(self.archive["Datetime"], errors="raise")
        return training_data_hash(self.archive.loc[dates.between("2018-01-01", "2022-12-31")])

    def get(self, as_of_date: str, *, verify_only: bool = False) -> dict[str, Any]:
        """Cắt trước fit/kiểm tra; nạp artifact có sẵn thay vì fit lại khi tiếp tục."""
        cutoff = iso_date(as_of_date)
        dates = pd.to_datetime(self.archive["Datetime"], errors="raise")
        prefix = self.archive.loc[dates.between("2018-01-01", cutoff)].copy()
        if prefix.empty or pd.Timestamp(prefix["Datetime"].iloc[-1]) != pd.Timestamp(cutoff):
            raise ValueError("VN-Index thiếu phiên tại ngày quyết định")
        expected_hash = training_data_hash(prefix)
        path = self.artifact_dir / f"VNINDEX-{cutoff}.json"
        if path.exists():
            detector = MarketRegimeDetector.load(path, expected_training_hash=expected_hash)
        else:
            if verify_only:
                raise ValueError("Thiếu artifact regime của episode đã hoàn thành")
            detector = MarketRegimeDetector().fit(prefix)
            detector.save(path)
        meta = detector.metadata
        if meta["train_end_date"] != cutoff:
            raise ValueError("Model/scaler/calibration không kết thúc đúng prefix quyết định")
        state = detector.classify_regime(prefix, cutoff)
        return {"state": state, "metadata": meta,
                "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


class HistoricalMemoryRunner:
    """Lưu riêng episode hoàn chỉnh và xuất kho từ journal có thứ tự đã xác minh."""

    def __init__(self, output_dir: str | Path, signal_extractor: Any = None, *,
                 symbols: tuple[str, ...] = ("FPT", "VNM", "VCB", "MWG"),
                 start: str = "2018-01-01", end: str = "2022-12-31",
                 execution_loader: ExecutionLoader | None = None,
                 regime_provider: PrefixRegimeProvider | None = None,
                 model_config: dict[str, Any] | None = None,
                 article_loader: Any = None) -> None:
        self.output_dir = Path(output_dir)
        self.start, self.end = iso_date(start), iso_date(end)
        if not "2018-01-01" <= self.start <= self.end <= "2022-12-31":
            raise ValueError("Runner chỉ nhận phạm vi nghiên cứu 2018–2022")
        if not symbols or len(set(symbols)) != len(symbols) or any(symbol not in SYMBOLS for symbol in symbols):
            raise ValueError("Danh sách mã không hợp lệ hoặc trùng")
        self.symbols = tuple(sorted(symbols))
        loader = execution_loader or (lambda symbol: load_verified_execution_data(DEFAULT_DATA_DIR, symbol))
        self.data = {symbol: loader(symbol) for symbol in self.symbols}
        self.regime_provider = regime_provider or PrefixRegimeProvider(self.output_dir / "regimes")
        self.signal_extractor = signal_extractor
        self.article_loader = article_loader or (lambda symbol: disk_articles(ROOT, symbol))
        self.model_config = {key: (model_config or DEFAULT_CONFIG)[key] for key in sorted(MODEL_CONFIG_KEYS)}
        if any(self.model_config[key] != 0.0 for key in ("agent_llm_temperature", "graph_llm_temperature")):
            raise ValueError("Runner nghiên cứu dùng nhiệt độ LLM cố định bằng 0")
        self.outcomes = HistoricalOutcomeGenerator(self.execution_data)

    def execution_data(self, symbol: str) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        """Trả bản sao bộ dữ liệu đã xác minh cho các thành phần của cùng run."""
        frame, events = self.data[symbol]
        return frame.copy(deep=True), copy.deepcopy(events)

    def plan(self) -> dict[str, Any]:
        """Tạo lịch vector hóa, không fit HMM hoặc gọi LLM; giữ lý do loại chu kỳ."""
        candidates: list[dict[str, Any]] = []
        for symbol in self.symbols:
            schedule = build_verified_cycle_schedule(*self.data[symbol], warmup=600, step=3)
            schedule = schedule.loc[(schedule["as_of_date"] >= self.start) & (schedule["exit_date"] <= self.end)].copy()
            for key in ("as_of_date", "entry_date", "exit_date"):
                schedule[key] = schedule[key].dt.strftime("%Y-%m-%d")
            schedule["symbol"] = symbol
            candidates.extend(schedule.to_dict("records"))
        candidates.sort(key=lambda point: (point["as_of_date"], point["symbol"]))
        eligible = [{key: point[key] for key in ("symbol", "as_of_date", "entry_date", "exit_date")}
                    for point in candidates if point["eligible"]]
        return {"candidate_count": len(candidates), "eligible_count": len(eligible),
                "excluded": [point for point in candidates if not point["eligible"]], "points": eligible}

    def _identity(self, plan: dict[str, Any]) -> dict[str, Any]:
        data_hashes = {}
        for symbol, (frame, events) in self.data.items():
            canonical = frame.to_csv(index=False, date_format="%Y-%m-%d", float_format="%.17g", lineterminator="\n")
            data_hashes[symbol] = {"prices": hashlib.sha256(canonical.encode("utf-8")).hexdigest(), "events": digest(events),
                                   "news": digest(self.article_loader(symbol))}
        return {"format_version": 1, "symbols": list(self.symbols), "start": self.start, "end": self.end,
                "warmup": 600, "step": 3, "seed": 42, "fee": 0.0025, "slippage": 0.001,
                "models": self.model_config, "hmm_parameters": dict(HMM_PARAMETERS),
                "signal_config": self.signal_extractor.config if self.signal_extractor is not None else None,
                "data": data_hashes, "vnindex_sha256": self.regime_provider.input_hash,
                "plan_sha256": digest(plan),
                "code_sha256": {name: hashlib.sha256((ROOT / name).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
                                for name in RUNNER_CODE_FILES},
                "runtime": {"python": platform.python_version(), **{
                    name: version(name) for name in ("numpy", "pandas", "scipy", "scikit-learn", "hmmlearn")}}}

    @staticmethod
    def _write_envelope(path: Path, payload: dict[str, Any]) -> None:
        atomic_write_json(path, {"payload": payload, "sha256": digest(payload)})

    @staticmethod
    def _read_envelope(path: Path) -> dict[str, Any]:
        envelope = read_json(path)
        exact_object(envelope, {"payload", "sha256"})
        if type(envelope["payload"]) is not dict or digest(envelope["payload"]) != envelope["sha256"]:
            raise ValueError("Checksum journal không khớp")
        return envelope["payload"]

    @staticmethod
    def _validate_regime(proof: dict[str, Any], cutoff: str) -> None:
        exact_object(proof, {"state", "metadata", "artifact_sha256"})
        state, meta = proof["state"], proof["metadata"]
        if type(meta) is not dict or not {"train_start_date", "train_end_date", "training_data_sha256"} <= set(meta):
            raise ValueError("Provenance model thiếu khoảng train hoặc checksum prefix")
        validate_regime_state(state)
        if (state["as_of_date"] != cutoff or state["feature_end_date"] > cutoff
                or iso_date(meta["train_end_date"]) != cutoff
                or iso_date(meta["train_start_date"]) > cutoff):
            raise ValueError("Regime/model/scaler/calibration vượt cutoff hoặc khác ngày quyết định")

    def _validate_episode(self, payload: dict[str, Any], point: dict[str, str], signature: str) -> None:
        exact_object(payload, {"signature", "record", "provenance"})
        record = payload["record"]
        if type(record) is not dict:
            raise ValueError("Journal thiếu record hoàn chỉnh")
        if payload["signature"] != signature or any(record.get(key) != value for key, value in point.items()):
            raise ValueError("Episode không khớp run hoặc lịch ứng viên")
        if record["episode_id"] != f"{point['symbol']}:{point['as_of_date']}":
            raise ValueError("ID episode không khớp mã và điểm quyết định")
        validate_historical_task_record(record, *self.data[point["symbol"]])
        provenance = payload["provenance"]
        exact_object(provenance, {"regime", "signal_checkpoint_sha256"})
        proof = provenance["regime"]
        self._validate_regime(proof, point["as_of_date"])
        verified = self.regime_provider.get(point["as_of_date"], verify_only=True)
        if proof != verified or record["regime"] != verified["state"]["regime_name"]:
            raise ValueError("Provenance regime không khớp artifact đã xác minh")
        signal_path = self.output_dir / "signals" / f"{point['symbol']}-{point['as_of_date']}.json"
        if hashlib.sha256(signal_path.read_bytes()).hexdigest() != payload["provenance"]["signal_checkpoint_sha256"]:
            raise ValueError("Checkpoint tín hiệu khác provenance của episode")
        signal_payload = self._read_envelope(signal_path)
        if signal_payload.get("stage") != "COMPLETE" or type(signal_payload.get("result")) is not dict:
            raise ValueError("Episode dùng checkpoint tín hiệu chưa hoàn chỉnh")
        bundle = signal_payload["result"]
        if (bundle.get("agent_signals") != record["agent_signals"] or bundle.get("symbol") != point["symbol"]
                or bundle.get("as_of_date") != point["as_of_date"]):
            raise ValueError("Episode dùng tín hiệu chưa hoàn chỉnh hoặc sai nhãn")
        signal_proof = bundle.get("provenance", {})
        cutoff = point["as_of_date"]
        prefix = raw_point_in_time_snapshot(self.data[point["symbol"]][0], cutoff)
        if (signal_proof.get("price_end_date") != cutoff or signal_proof.get("alpha_end_date") != cutoff
                or signal_proof.get("price_sha256") != digest(snapshot_payload(prefix))
                or type(signal_proof.get("news_dates")) is not list
                or any(iso_date(published) > cutoff for published in signal_proof["news_dates"])):
            raise ValueError("Provenance tín hiệu chứa dữ liệu ngoài snapshot quyết định")
        if digest(bundle.get("reports")) != signal_proof.get("reports_sha256"):
            raise ValueError("Báo cáo tín hiệu sai checksum")

    def run(self, *, max_new_points: int | None = None, verify_only: bool = False) -> dict[str, Any]:
        """Tiếp tục journal đã xác thực; lỗi dừng ngay, không thêm record nửa chừng."""
        if max_new_points is not None and (type(max_new_points) is not int or max_new_points < 1):
            raise ValueError("Giới hạn số điểm mới phải là số nguyên dương")
        if not verify_only and self.signal_extractor is None:
            raise ValueError("Chạy tạo episode cần bộ trích tín hiệu")
        if verify_only and not self.output_dir.is_dir():
            raise ValueError("Chưa có thư mục run để kiểm tra")
        plan = self.plan()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        lock = self.output_dir / "run.lock"
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError("Run đang hoạt động hoặc cần rà soát khóa sau gián đoạn") from exc
        os.close(descriptor)
        try:
            return self._run_locked(plan, max_new_points, verify_only)
        finally:
            lock.unlink()

    def _run_locked(self, plan: dict[str, Any], limit: int | None, verify_only: bool) -> dict[str, Any]:
        manifest_path = self.output_dir / "run_manifest.json"
        identity = self._identity(plan)
        if manifest_path.exists():
            existing = self._read_envelope(manifest_path)
            # Verify không cần khởi tạo LLM; vẫn so phiên bản/cấu hình đã lưu.
            if self.signal_extractor is None:
                identity["signal_config"] = existing.get("signal_config")
            if identity != existing:
                raise ValueError("Dữ liệu, phạm vi, cấu hình hoặc mã nguồn của run đã thay đổi")
        elif verify_only:
            raise ValueError("Chưa có manifest run để kiểm tra")
        else:
            if self.signal_extractor is None:
                raise ValueError("Chạy tạo episode cần bộ trích tín hiệu")
            self._write_envelope(manifest_path, identity)
        signature = digest(identity)
        episodes_dir = self.output_dir / "episodes"
        points = plan["points"]
        paths = [episodes_dir / f"{p['symbol']}-{p['as_of_date']}.json" for p in points]
        if set(episodes_dir.glob("*.json")) - set(paths):
            raise ValueError("Journal chứa episode ngoài lịch đã chốt")
        records = []
        missing_seen = False
        for point, path in zip(points, paths):
            if not path.exists():
                missing_seen = True
                continue
            if missing_seen:
                raise ValueError("Journal có khoảng trống trước episode đã hoàn thành")
            payload = self._read_envelope(path)
            self._validate_episode(payload, point, signature)
            records.append(payload["record"])
        store_path = self.output_dir / "memory.json"
        if store_path.exists():
            previous = read_json(store_path)
            if previous not in (records, records[:-1]):
                raise ValueError("Kho xuất không khớp journal; từ chối ghi đè")
        elif records and verify_only:
            raise ValueError("Thiếu kho xuất từ journal")
        if verify_only:
            if records and read_json(store_path) != records:
                raise ValueError("Kho xuất chậm một checkpoint; cần tiếp tục để phục hồi")
            return {"completed": len(records), "remaining": len(points) - len(records), "new_points": 0}
        atomic_write_json(store_path, records)
        processed = 0
        for point, path in zip(points[len(records):], paths[len(records):]):
            if limit is not None and processed >= limit:
                break
            cutoff, symbol = point["as_of_date"], point["symbol"]
            proof = self.regime_provider.get(cutoff)
            self._validate_regime(proof, cutoff)
            bundle = self.signal_extractor.extract(symbol, cutoff)
            if bundle["symbol"] != symbol or bundle["as_of_date"] != cutoff:
                raise ValueError("Tín hiệu trả sai mã hoặc cutoff")
            signals = bundle["agent_signals"]
            outcome = self.outcomes.generate(**point, agent_signals=signals, settled_as_of=self.end)
            record = {"episode_id": f"{symbol}:{cutoff}", **point, "regime": proof["state"]["regime_name"],
                      "agent_signals": signals, "outcome": outcome}
            signal_path = self.output_dir / "signals" / f"{symbol}-{cutoff}.json"
            payload = {"signature": signature, "record": record, "provenance": {
                "regime": proof, "signal_checkpoint_sha256": hashlib.sha256(signal_path.read_bytes()).hexdigest()}}
            self._validate_episode(payload, point, signature)
            self._write_envelope(path, payload)
            records.append(record)
            atomic_write_json(store_path, records)
            processed += 1
            print(f"Đã lưu {len(records)}/{len(points)} episode: {symbol} @ {cutoff}")
        memory = HistoricalMemory(self.execution_data)
        memory.load(store_path)
        return {"completed": len(records), "remaining": len(points) - len(records), "new_points": processed}
