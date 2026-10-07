"""Khóa nguồn OOS, chứng minh model train-only và chọn pilot theo lịch giá."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.bayesian_memory import atomic_write_json, read_json
from core.execution_prices import STOCK_SYMBOLS, build_verified_cycle_schedule, load_verified_execution_data
from core.groq_pacing import MODEL_LIMITS
from core.historical_signals import MODEL_CONFIG_KEYS, disk_articles
from core.prior_backtest import canonical_hash
from core.prior_config import normalize_prior_config
from core.prior_context import PriorContextAdapter
from core.regime_detector import MarketRegimeDetector, training_data_hash
from default_config import DEFAULT_CONFIG

ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = "outputs/oos_pilot/inputs"
EXECUTION_DIR = "data/execution_prices_oos"


def sha_file(path: Path) -> str:
    """Checksum byte nguồn; không dùng hàm này cho key hoặc credential."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_cutoffs(frame: pd.DataFrame, events: list[dict[str, Any]], count: int = 20) -> tuple[str, ...]:
    """Chọn 20 ngày hợp lệ đầu OOS, không xem return, regime hoặc dự báo."""
    if type(count) is not int or count < 1:
        raise ValueError("Số điểm pilot phải là số nguyên dương")
    schedule = build_verified_cycle_schedule(frame, events)
    eligible = schedule.loc[schedule.eligible & schedule.as_of_date.between("2023-01-01", "2024-12-31")]
    dates = tuple(eligible.as_of_date.head(count).dt.strftime("%Y-%m-%d"))
    if len(dates) != count:
        raise ValueError("Nguồn chưa đủ điểm pilot OOS hợp lệ")
    return dates


def verify_frozen_model(root: Path = ROOT) -> dict[str, Any]:
    """Tái fit cùng prefix chỉ để đối chiếu HMM/scaler/calibration, không ghi model.

    Nhãn UNVERIFIED/RESEARCH_ONLY của artifact vẫn giữ nguyên. Proof riêng chỉ
    chứng minh thành phần đã fit trên prefix 2018–2022 đã có checksum W1.
    """
    csv_path = root / "data/historical/VNINDEX.csv"
    manifest = read_json(csv_path.parent / "manifest.json")
    if sha_file(csv_path) != manifest["files"]["VNINDEX"]["sha256"]:
        raise ValueError("VNINDEX không khớp manifest đóng băng")
    archive = pd.read_csv(csv_path, parse_dates=["Datetime"])
    train = archive.loc[archive.Datetime.between("2018-01-01", "2022-12-31")].copy()
    artifact = root / "data_manager/regime_model.json"
    original_hash = sha_file(artifact)
    frozen = MarketRegimeDetector.load(artifact, expected_training_hash=training_data_hash(train))
    replay = MarketRegimeDetector().fit(train)
    for original, reproduced in ((frozen._scaler.mean_, replay._scaler.mean_),
            (frozen._scaler.var_, replay._scaler.var_), (frozen._scaler.scale_, replay._scaler.scale_),
            (frozen._model.startprob_, replay._model.startprob_), (frozen._model.transmat_, replay._model.transmat_),
            (frozen._model.means_, replay._model.means_), (frozen._model.covars_, replay._model.covars_)):
        if not np.allclose(original, reproduced, rtol=1e-9, atol=1e-10):
            raise ValueError("Model/scaler không tái lập từ prefix train đã đóng băng")
    if canonical_hash(frozen.metadata) != canonical_hash(replay.metadata) or sha_file(artifact) != original_hash:
        raise ValueError("Calibration/model metadata không tái lập hoặc artifact bị thay đổi")
    return {"status": "PASS", "artifact_path": "data_manager/regime_model.json", "artifact_sha256": original_hash,
            "training_data_sha256": training_data_hash(train), "train_start": frozen.metadata["train_start_date"],
            "train_end": frozen.metadata["train_end_date"], "freeze_as_of_date": "2022-12-31",
            "components": {name: "PREFIX_REPLAY_MATCH" for name in ("hmm", "scaler", "calibration")},
            "source_path": "data/historical/VNINDEX.csv", "source_sha256": sha_file(csv_path),
            "source_manifest_sha256": sha_file(csv_path.parent / "manifest.json"),
            "scope": "RETROSPECTIVE_TRAIN_ONLY_RESEARCH_NOT_LIVE_ARCHIVE_CERTIFICATION"}


def build_adapter(plan: dict[str, Any], root: Path = ROOT) -> PriorContextAdapter:
    """Nối nguồn riêng vào API W4; không ghi đè train hoặc Memory Bank."""
    config = normalize_prior_config({"enable_bayesian_prior": True})
    return PriorContextAdapter(config, root=root, execution_dir=plan["execution_dir"],
        news_dir=plan["news_dir"], vnindex_manifest_path="data/historical/manifest.json",
        provider_mode="fixed_train_oos", frozen_artifact_path=plan["model"]["artifact_path"],
        freeze_as_of_date=plan["model"]["freeze_as_of_date"], window_size=45, signal_config=plan["signal_config"])


def prepare_inputs(root: Path = ROOT) -> dict[str, Any]:
    """Tạo plan một lần; input đã tồn tại chỉ được xác minh, không lựa chọn lại ngày."""
    from scripts.verify_execution_price_gate import verify_bundle
    directory = root / INPUT_DIR
    plan_path = directory / "plan.json"
    if plan_path.exists():
        return verify_inputs(root)
    verify_bundle(root / EXECUTION_DIR, end="2024-12-31")
    directory.mkdir(parents=True, exist_ok=True)
    source_news = {}
    for symbol in STOCK_SYMBOLS:
        source = root / f"sentiment_cache_{symbol}.json"
        articles = disk_articles(root, symbol)
        visible = [a for a in articles if a.get("date_parsed") and a["date_parsed"] <= "2024-12-31"]
        destination = directory / "news" / f"{symbol}.json"
        snapshot = {"symbol": symbol, "scored_articles": visible}
        if destination.exists() and read_json(destination) != snapshot:
            raise ValueError("Snapshot tin đã tồn tại và khác cache; không ghi đè")
        atomic_write_json(destination, snapshot)
        source_news[symbol] = {"cache_existed": source.exists(), "cache_sha256": sha_file(source) if source.exists() else None,
            "input_count": len(articles), "dated_through_oos_count": len(visible), "snapshot_sha256": sha_file(destination)}
    frame, events = load_verified_execution_data(root / EXECUTION_DIR, "FPT")
    models = {key: DEFAULT_CONFIG[key] for key in sorted(MODEL_CONFIG_KEYS)}
    plan = {"version": 1, "symbol": "FPT", "selection": "FIRST_20_ELIGIBLE_OOS_CALENDAR_CYCLES_STEP_3",
        "cutoffs": list(select_cutoffs(frame, events)), "execution_dir": EXECUTION_DIR, "news_dir": f"{INPUT_DIR}/news",
        "execution_manifest_sha256": sha_file(root / EXECUTION_DIR / "manifest.json"), "model": verify_frozen_model(root),
        "signal_config": {"models": models, "window_size": 45, "norm_method": "zscore_tanh", "alpha_weights": None,
                          "language": "vi", "time_frame": "1d"},
        "client_options": {"agent": {"reasoning_format": "hidden", "reasoning_effort": "low"},
                           "graph": {"reasoning_format": "hidden", "reasoning_effort": "none"}},
        "limits": MODEL_LIMITS, "quota_source": "ACCOUNT_LIMITS_USER_CONFIRMED_2026_10_07",
        "news_sources": source_news}
    adapter = build_adapter(plan, root)
    contexts = [adapter.prepare("FPT", cutoff) for cutoff in plan["cutoffs"]]
    plan["news_coverage"] = [{"cutoff": p.source_provenance["context"]["as_of_date"],
        "visible_count": p.source_provenance["news"]["visible_count"],
        "neutral_reason": p.source_provenance["news"]["neutral_reason"]} for p in contexts]
    atomic_write_json(plan_path, {"payload": plan, "sha256": canonical_hash(plan)})
    return plan


def verify_inputs(root: Path = ROOT) -> dict[str, Any]:
    """Kiểm plan/hash/nguồn/model/PIT offline; không tự tải hoặc gọi LLM."""
    from scripts.verify_execution_price_gate import verify_bundle
    envelope = read_json(root / INPUT_DIR / "plan.json")
    plan = envelope["payload"]
    if envelope["sha256"] != canonical_hash(plan) or plan["limits"] != MODEL_LIMITS:
        raise ValueError("Plan hoặc quota khác bản đã khóa")
    verify_bundle(root / plan["execution_dir"], end="2024-12-31")
    if (sha_file(root / plan["execution_dir"] / "manifest.json") != plan["execution_manifest_sha256"]
            or sha_file(root / plan["model"]["artifact_path"]) != plan["model"]["artifact_sha256"]
            or sha_file(root / plan["model"]["source_path"]) != plan["model"]["source_sha256"]):
        raise ValueError("Nguồn giá hoặc model đã thay đổi")
    frame, events = load_verified_execution_data(root / plan["execution_dir"], "FPT")
    if plan["cutoffs"] != list(select_cutoffs(frame, events)):
        raise ValueError("Plan khác lựa chọn lịch OOS đã quy định")
    for symbol, source in plan["news_sources"].items():
        if sha_file(root / plan["news_dir"] / f"{symbol}.json") != source["snapshot_sha256"]:
            raise ValueError("Snapshot tin đã thay đổi")
    adapter = build_adapter(plan, root)
    for cutoff in plan["cutoffs"]:
        adapter.prepare("FPT", cutoff)
    return plan
