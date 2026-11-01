"""Ngân hàng đầu vào chung và runner Full có archive, không sửa runtime legacy."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.revision_audit import DEFAULT_SYMBOLS, sha256_file
from core.revision_baselines import load_prices, samples, sentiment_features


def native(value: Any) -> Any:
    """Chuyển state sang JSON thuần; không âm thầm chấp nhận object chưa biết."""
    if isinstance(value, dict):
        return {str(k): native(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [native(v) for v in value]
    if isinstance(value, np.generic):
        return native(value.item())
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Kiểu state không được phép lưu: {type(value).__name__}")


def digest(value: Any) -> str:
    """Content hash có thứ tự khóa ổn định cho cache và parent IDs."""
    return hashlib.sha256(json.dumps(native(value), sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def write_json(path: Path, value: Any, exclusive: bool = False) -> None:
    """Ghi nguyên bản mới hoặc checkpoint atomic trong đúng thư mục đã chọn."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(native(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if exclusive:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    else:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8", newline="\n")
        temporary.replace(path)


def read_json(path: Path) -> Any:
    """Đọc UTF-8, không sửa file nguồn."""
    return json.loads(path.read_bytes())


def make_schedule(frames: dict[str, pd.DataFrame], protocol: dict) -> list[dict]:
    """Chọn folds/điểm theo ngày đã khóa, purge label overlap trước mọi fit."""
    result = []
    for symbol in DEFAULT_SYMBOLS:
        frame = frames[symbol]
        candidate = samples(frame, {**protocol, "warmup_sessions": protocol["alpha_history"] - 1})
        for fold in protocol["folds"]:
            positions = np.flatnonzero(frame["date"].to_numpy() >= fold["test_start"])
            if not len(positions):
                raise ValueError(f"{symbol}/{fold['id']}: không có test")
            test_idx = int(positions[0]) + np.arange(protocol["n_test_per_symbol_fold"]) * protocol["training_step"]
            if test_idx[0] + 1 < protocol["alpha_history"] or test_idx[-1] + protocol["horizon_observed_sessions"] >= len(frame):
                raise ValueError(f"{symbol}/{fold['id']}: thiếu lịch sử hoặc target")
            first_test = str(frame["date"].iloc[test_idx[0]])
            validation = candidate.loc[(candidate["date"] >= fold["validation_start"]) & (candidate["exit_date"] < first_test)]
            if validation.empty:
                raise ValueError("Không có validation đã trưởng thành")
            train = candidate.loc[(candidate["date"] <= fold["train_end"]) &
                                  (candidate["exit_date"] < validation["date"].iloc[0])]
            if len(train) < max(protocol["minimum_train"], protocol["full_calibration_points"]) or len(validation) < protocol["minimum_validation"]:
                raise ValueError(f"{symbol}/{fold['id']}: support train/validation không đủ")
            if train["label"].nunique() < 2 or validation["label"].nunique() < 2:
                raise ValueError(f"{symbol}/{fold['id']}: train/validation thiếu lớp")
            result.append({"symbol": symbol, "fold": fold["id"],
                "train": train["decision"].astype(int).tolist(),
                "validation": validation["decision"].astype(int).tolist(),
                "calibration": train["decision"].tail(protocol["full_calibration_points"]).astype(int).tolist(),
                "test": test_idx.astype(int).tolist(), "first_test_date": first_test,
                "last_train_label_date": str(train["exit_date"].iloc[-1]),
                "first_validation_date": str(validation["date"].iloc[0]),
                "last_validation_label_date": str(validation["exit_date"].iloc[-1])})
    return result


class FrozenSentiment:
    """Chỉ dùng score có provenance; không truy cập crawler hoặc LLM."""

    def __init__(self, articles: dict[str, list[dict]]):
        self.articles = articles

    def get_sentiment_at(self, symbol: str, cutoff_date: str, llm: Any = None,
                         window_days: int = 90) -> tuple[dict, str]:
        """Giữ missingness rõ ràng, peer list rỗng như protocol."""
        if window_days != 90:
            raise ValueError("Cửa sổ tin không khớp protocol")
        row = sentiment_features(pd.Series([cutoff_date]), self.articles.get(symbol, []))
        count = int(row["verified_article_count"].iloc[0])
        missing = bool(row["sentiment_missing"].iloc[0])
        score = None if missing else float(row["sentiment_score"].iloc[0])
        data = {"main_sentiment": {"article_count": 0 if missing else count, "avg_score": score},
                "scored_articles": [], "related_sentiment": {}, "related_companies": [],
                "is_unavailable": missing, "verified_article_count": count}
        report = ("Sentiment KHÔNG KHẢ DỤNG do thiếu tối thiểu 3 score đã xác minh; không coi là trung tính."
                  if missing else f"Sentiment đã xác minh: score={score:.6f}; số bài={count}; peers không khả dụng.")
        return data, report


def point_state(frame: pd.DataFrame, symbol: str, decision: int, protocol: dict,
                sentiment: FrozenSentiment) -> dict:
    """Chỉ đưa prefix tới decision vào Full; không truyền entry/exit/labels."""
    from core.backtest_engine import BacktestEngine
    engine = BacktestEngine({"use_historical_sentiment": False})
    df = frame.rename(columns={"date": "Datetime"}).copy()
    df["Datetime"] = pd.to_datetime(df["Datetime"])
    end = decision + 1
    if end < protocol["alpha_history"]:
        raise ValueError("Thiếu lịch sử Alpha")
    window, _, cutoff = engine._prepare_window(df, end, protocol["window_size"])
    return {"stock_name": symbol, "time_frame": "1 ngày", "kline_data": window,
            "messages": [], "language": protocol["language"], "is_backtest": True,
            "point_in_time_df": df.iloc[max(0, end - protocol["alpha_history"]):end].copy(),
            "as_of_date": df["Datetime"].iloc[decision], "window_end_date": cutoff,
            "sentiment_store": sentiment, "alpha_norm_method": protocol["alpha_norm_method"], "alpha_weights": protocol["alpha_weights"]}


def pack_state(state: dict) -> dict:
    """Bỏ object runtime có thể khôi phục; lưu đầy đủ messages/reports/numeric state."""
    from langchain_core.messages import messages_to_dict
    result = {k: v for k, v in state.items() if k not in ("point_in_time_df", "sentiment_store", "messages")}
    result["messages"] = messages_to_dict(state.get("messages", []))
    return native(result)


def restore_state(packed: dict, initial: dict) -> dict:
    """Khôi phục messages và prefix đã xác minh, không fetch live."""
    from langchain_core.messages import messages_from_dict
    result = {**deepcopy(packed), "point_in_time_df": initial["point_in_time_df"],
              "sentiment_store": initial["sentiment_store"]}
    result["messages"] = messages_from_dict(packed.get("messages", []))
    return result


def market_features(initial: dict, alpha: dict) -> dict[str, float | None]:
    """Mã hóa đúng numeric đầu vào: OHLCV 45 nến và selected-alpha metrics, không dùng prose LLM."""
    from core.alpha_compare import ALPHA_REGISTRY, get_alpha_template
    features = {}
    for field in ("Open", "High", "Low", "Close", "Volume"):
        for index, value in enumerate(initial["kline_data"][field]):
            features[f"price_{field}_{index:02d}"] = float(value)
    identities = {}
    for key in ALPHA_REGISTRY:
        template = get_alpha_template(key, "vi")
        pair = (template.get("name"), template.get("formula"))
        if pair in identities:
            raise ValueError("Template alpha không có định danh duy nhất")
        identities[pair] = key
        for metric in ("selected", "value", "ic", "accuracy", "composite_score"):
            features[f"factor_{key}_{metric}"] = 0.0 if metric == "selected" else None
    data = alpha["sentiment_data"]
    for factor in data["alpha_results"]:
        key = identities[(factor["name"], factor["formula"])]
        components = factor["components"]
        features.update({f"factor_{key}_selected": 1.0, f"factor_{key}_value": float(factor["value"]),
            f"factor_{key}_ic": float(components["ic"]),
            f"factor_{key}_accuracy": float(str(components["accuracy"]).strip("%")) / 100,
            f"factor_{key}_composite_score": float(components["composite_score"])})
    for key, value in data.get("sentiment_norm", {}).items():
        if isinstance(value, (float, int, bool, np.generic)):
            features[f"sentiment_{key}"] = float(value)
    features["sentiment_missing"] = float(data.get("is_unavailable", True))
    return native(features)


def prepare_bank(root: Path, destination: Path, protocol_path: Path) -> dict:
    """Khóa lịch và nguồn trước khi tính feature hoặc gọi bất kỳ API LLM nào."""
    if destination.exists():
        raise FileExistsError("Không ghi đè ngân hàng đã khóa")
    protocol = read_json(protocol_path)
    price_dir = root / protocol["price_snapshot"]
    frames, price_manifest = load_prices(price_dir, protocol["price_quality_policy"])
    schedule = make_schedule(frames, protocol)
    sources = [protocol_path, price_dir / "manifest.json"] + list(price_dir.glob("*.csv"))
    sources += [p for directory in ("agents", "utils") for p in (root / directory).glob("*.py")]
    sources += [root / p for p in ("core/backtest_engine.py", "core/alpha_compare.py", "core/revision_baselines.py",
        "core/revision_common_study.py", "core/revision_call_archive.py", "core/revision_common_analysis.py",
        "scripts/run_revision_common_study.py", "default_config.py")]
    news = {}
    for symbol in DEFAULT_SYMBOLS:
        path = root / f"sentiment_cache_{symbol}.json"
        news[symbol] = []
        if path.exists():
            sources.append(path)
            news[symbol] = [{k: a.get(k) for k in ("date_parsed", "available_at", "numeric_score", "scorer")}
                            for a in read_json(path).get("scored_articles", [])]
    n_test = sum(len(s["test"]) for s in schedule)
    n_calibration = sum(len(s["calibration"]) for s in schedule)
    # Backtest Indicator/Alpha là Python; Pattern + Trend + Decision gọi LLM.
    nominal = n_calibration * 3 + n_test * protocol["end_to_end_repeats"] * 3 + n_test * (protocol["decision_only_repeats"] - 1)
    from importlib.metadata import version
    import sys
    runtime = {name: version(name) for name in ("numpy", "pandas", "scipy", "scikit-learn", "TA-Lib", "groq", "langchain-groq", "langchain-core", "langgraph")}
    runtime["python"] = sys.version.split()[0]
    manifest = {"schema_version": "r1_common_bank_v1", "protocol": protocol, "runtime": runtime,
        "news_hash": digest(news),
        "schedule": schedule, "price_manifest": price_manifest,
        "n_test": n_test, "n_calibration": n_calibration, "nominal_llm_requests": nominal,
        "call_count_policy": "nominal only; verifier/format/API retries can add calls; execution requires explicit request cap",
        "sources": [{"path": p.relative_to(root).as_posix(), "sha256": sha256_file(p)} for p in sorted(set(sources))]}
    manifest["bank_id"] = digest(manifest)
    destination.mkdir(parents=True)
    write_json(destination / "manifest.json", manifest, exclusive=True)
    write_json(destination / "news.json", news, exclusive=True)
    return manifest


def verify_bank(root: Path, bank: Path) -> dict:
    """Từ chối resume khác nguồn/code/protocol hoặc sửa manifest."""
    manifest = read_json(bank / "manifest.json")
    unsigned = {k: v for k, v in manifest.items() if k != "bank_id"}
    if digest(unsigned) != manifest["bank_id"]:
        raise ValueError("Định danh bank không khớp manifest")
    for source in manifest["sources"]:
        path = (root / source["path"]).resolve()
        if not path.is_relative_to(root.resolve()) or sha256_file(path) != source["sha256"]:
            raise ValueError(f"Nguồn bank đã đổi: {source['path']}")
    if digest(read_json(bank / "news.json")) != manifest["news_hash"]:
        raise ValueError("Frozen news đã đổi")
    from importlib.metadata import version
    import sys
    for name, expected in manifest["runtime"].items():
        actual = sys.version.split()[0] if name == "python" else version(name)
        if actual != expected:
            raise ValueError(f"Runtime đã đổi: {name}")
    return manifest


_FEATURE_WORKER: dict[str, Any] = {}


def _init_feature_worker(root: str, bank: str, manifest: dict) -> None:
    """Khởi tạo một worker CPU, tuyệt đối không tạo client LLM."""
    from agents.alpha_agent import create_alpha_agent
    root_path, bank_path = Path(root), Path(bank)
    protocol = manifest["protocol"]
    frames, _ = load_prices(root_path / protocol["price_snapshot"], protocol["price_quality_policy"])
    _FEATURE_WORKER.update({"bank": bank_path, "manifest": manifest, "frames": frames,
        "sentiment": FrozenSentiment(read_json(bank_path / "news.json")),
        "node": create_alpha_agent(None, True, True)})


def _feature_worker(point: tuple[str, int]) -> bool:
    """Tính một điểm riêng biệt, atomic file và reuse đúng hash."""
    symbol, index = point
    manifest = _FEATURE_WORKER["manifest"]
    bank, frames = _FEATURE_WORKER["bank"], _FEATURE_WORKER["frames"]
    path = bank / "features" / f"{symbol}_{index}.json"
    if path.exists():
        cached = read_json(path)
        if cached["bank_id"] != manifest["bank_id"] or digest({k: v for k, v in cached.items() if k != "sha256"}) != cached["sha256"]:
            raise ValueError("Feature cache sai bank hoặc hash")
        return False
    initial = point_state(frames[symbol], symbol, index, manifest["protocol"], _FEATURE_WORKER["sentiment"])
    with redirect_stdout(io.StringIO()):
        alpha = _FEATURE_WORKER["node"](initial)
    feature = market_features(initial, alpha)
    record = {"bank_id": manifest["bank_id"], "symbol": symbol, "decision": index,
        "cutoff": str(frames[symbol]["date"].iloc[index]), "features": feature,
        "market_input_hash": digest({"window": initial["kline_data"], "features": feature}),
        "alpha_state": pack_state(alpha)}
    record["sha256"] = digest(record)
    write_json(path, record, exclusive=True)
    return True


def prepare_features(root: Path, bank: Path, workers: int = 4) -> int:
    """Tính feature thật bằng Alpha node hiện tại; không dựng output LLM giả."""
    from concurrent.futures import ProcessPoolExecutor
    from core.revision_call_archive import StudyLock
    if not 1 <= workers <= 4:
        raise ValueError("Số worker CPU phải từ 1 tới 4")
    manifest = verify_bank(root, bank)
    points = sorted({(s["symbol"], int(i)) for s in manifest["schedule"]
                     for role in ("train", "validation", "test") for i in s[role]})
    with StudyLock(bank / "features.lock"):
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_feature_worker,
                                 initargs=(str(root), str(bank), manifest)) as pool:
            for number, _ in enumerate(pool.map(_feature_worker, points, chunksize=1), 1):
                if number % 25 == 0 or number == len(points):
                    print(f"Đã khóa feature {number}/{len(points)} điểm (không gọi LLM).", flush=True)
        receipt = {"bank_id": manifest["bank_id"], "n_points": len(points),
            "files": [{"path": p.relative_to(bank).as_posix(), "sha256": sha256_file(p)} for p in sorted((bank / "features").glob("*.json"))]}
        path = bank / "features_complete.json"
        if path.exists() and read_json(path) != receipt:
            raise ValueError("Receipt feature đã khóa có nội dung khác")
        if not path.exists():
            write_json(path, receipt, exclusive=True)
    return len(points)


def verify_features(bank: Path, manifest: dict) -> None:
    """Không chạy Full trên bank feature chưa hoàn tất hoặc bị sửa byte."""
    complete = read_json(bank / "features_complete.json")
    expected = {(s["symbol"], i) for s in manifest["schedule"]
                for role in ("train", "validation", "test") for i in s[role]}
    if complete["bank_id"] != manifest["bank_id"] or complete["n_points"] != len(expected):
        raise ValueError("Feature receipt không khớp lịch bank")
    if len(complete["files"]) != len(expected):
        raise ValueError("Feature receipt thiếu/thừa file")
    expected_paths = {f"features/{symbol}_{index}.json" for symbol, index in expected}
    if {record["path"] for record in complete["files"]} != expected_paths:
        raise ValueError("Feature receipt trùng/sai danh sách điểm")
    for record in complete["files"]:
        path = (bank / record["path"]).resolve()
        if not path.is_relative_to(bank.resolve()) or sha256_file(path) != record["sha256"]:
            raise ValueError("Feature file không khớp receipt")


def unit_key(symbol: str, fold: str, decision: int, role: str, kind: str, repeat: int) -> str:
    """Mỗi fold, phase và repeat có checkpoint riêng, không tái gán nhãn run khác."""
    return f"{symbol}_{fold}_{role}_{decision}_{kind}_{repeat}"


def run_full(root: Path, bank: Path, run: Path, max_requests: int) -> None:
    """Chạy Full thực trên bank đã khóa; không fetch dữ liệu, không sửa legacy."""
    import os
    from dotenv import load_dotenv
    from langchain_groq import ChatGroq
    from groq import Groq
    from agents.decision_agent import create_final_trade_decider
    from utils.graph_setup import SetGraph
    from utils.graph_util import TechnicalTools
    from core.backtest_engine import BacktestEngine
    from core.revision_call_archive import CallArchive, GuardedLLM, StudyLock
    from utils import static_util

    manifest = verify_bank(root, bank)
    verify_features(bank, manifest)
    protocol, bank_id = manifest["protocol"], manifest["bank_id"]
    load_dotenv(root / ".env")
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        raise RuntimeError("Chưa cấu hình GROQ_API_KEY; chưa gọi inference.")
    # /models là read-only; xác nhận cấu hình trước mọi request inference.
    available = {m.id for m in Groq(api_key=key, max_retries=0, timeout=20).models.list().data}
    wanted = {protocol["agent_llm_model"], protocol["graph_llm_model"]}
    if not wanted.issubset(available):
        raise RuntimeError(f"Model đã khóa không có trong catalogue: {sorted(wanted - available)}")
    frames, _ = load_prices(root / protocol["price_snapshot"], protocol["price_quality_policy"])
    sentiment = FrozenSentiment(read_json(bank / "news.json"))
    run.mkdir(parents=True, exist_ok=True)
    with StudyLock(run / "run.lock"):
        identity = {"schema_version": "r1_common_full_run_v1", "bank_id": bank_id, "run_id": run.name,
                    "features_receipt_hash": sha256_file(bank / "features_complete.json")}
        identity["run_signature"] = digest(identity)
        path = run / "run_manifest.json"
        if path.exists() and read_json(path) != identity:
            raise ValueError("Run identity/feature receipt khác; từ chối resume")
        if not path.exists():
            write_json(path, identity, exclusive=True)
        completion = run / "inference_complete.json"
        if completion.exists():
            receipt = read_json(completion)
            expected_count = manifest["n_calibration"] + manifest["n_test"] * (
                protocol["end_to_end_repeats"] + protocol["decision_only_repeats"] - 1)
            if receipt["run_signature"] != identity["run_signature"] or receipt["n_decisions"] != expected_count:
                raise ValueError("Completion receipt chưa đủ hoặc khác run")
            for artifact in receipt["artifacts"]:
                artifact_path = (run / artifact["path"]).resolve()
                if not artifact_path.is_relative_to(run.resolve()) or sha256_file(artifact_path) != artifact["sha256"]:
                    raise ValueError("Inference đã hoàn tất nhưng artifact bị sửa")
            print("Run đã hoàn tất và còn nguyên hash; không gọi lại inference.")
            return
        archive = CallArchive(run, bank_id, max_requests, key)

        def model(role: str) -> GuardedLLM:
            prefix = "agent" if role == "text" else "graph"
            delegate = ChatGroq(model=protocol[f"{prefix}_llm_model"], api_key=key,
                temperature=protocol[f"{prefix}_llm_temperature"], max_tokens=protocol[f"{prefix}_llm_max_tokens"],
                max_retries=0, reasoning_format="hidden", callbacks=[archive], timeout=120)
            return GuardedLLM(delegate)

        text_model, vision_model = model("text"), model("vision")
        upstream = SetGraph(text_model, vision_model, TechnicalTools()).compile_upstream()
        decide = create_final_trade_decider(text_model)
        parser = BacktestEngine({"use_historical_sentiment": False})
        completed = 0

        def ready_state(item: dict, index: int, role: str, repeat: int) -> dict:
            symbol, fold = item["symbol"], item["fold"]
            initial = point_state(frames[symbol], symbol, index, protocol, sentiment)
            feature = read_json(bank / "features" / f"{symbol}_{index}.json")
            ready_path = run / "ready" / f"{unit_key(symbol, fold, index, role, 'e2e', repeat)}.json"
            parent = {"run_signature": identity["run_signature"], "feature_hash": feature["sha256"]}
            if ready_path.exists():
                cached = read_json(ready_path)
                body = {k: v for k, v in cached.items() if k != "sha256"}
                if cached["parent"] != parent or digest(body) != cached["sha256"]:
                    raise ValueError("Ready-state cache không khớp input/repeat")
                return cached
            initial["pattern_image"] = static_util.generate_kline_image(initial["kline_data"]).get("pattern_image", "")
            initial["trend_image"] = static_util.generate_trend_image(initial["kline_data"]).get("trend_image", "")
            if not initial["pattern_image"] or not initial["trend_image"]:
                raise RuntimeError("Không tạo được đầy đủ chart; không thay bằng input thiếu")
            context = {"symbol": symbol, "fold": fold, "decision": index, "role": role,
                       "kind": "e2e", "repeat_id": repeat, "stage": "upstream", "market_input_hash": feature["market_input_hash"]}
            archive.context = context
            before = len(archive.ids)
            state = upstream.invoke(deepcopy(initial))
            if digest(state["kline_data"]) != digest(initial["kline_data"]):
                raise RuntimeError("Upstream đã làm thay đổi dữ liệu giá đầu vào")
            observed_nodes = set()
            for attempt in archive.ids[before:]:
                if (run / "calls" / f"{attempt}.response.json").exists():
                    request = read_json(run / "calls" / f"{attempt}.request.json")
                    observed_nodes.add(request.get("model_metadata", {}).get("langgraph_node"))
            if not state.get("indicator_report") or not {"Pattern Agent", "Trend Agent"}.issubset(observed_nodes):
                raise RuntimeError("Có upstream thiếu response thật; dừng thay vì lưu Full với báo cáo fallback rỗng")
            alpha = restore_state(feature["alpha_state"], initial)
            state["messages"] = state.get("messages", []) + alpha.pop("messages", [])
            for name, value in alpha.items():
                if name not in ("point_in_time_df", "sentiment_store"):
                    state[name] = value
            state["point_in_time_df"], state["sentiment_store"] = initial["point_in_time_df"], sentiment
            record = archive.clean({"parent": parent, "context": context, "state": pack_state(state),
                      "request_ids": archive.ids[before:]})
            record["sha256"] = digest(record)
            write_json(ready_path, record, exclusive=True)
            return record

        def decision(item: dict, index: int, role: str, kind: str, repeat: int, ready: dict) -> None:
            nonlocal completed
            symbol, fold = item["symbol"], item["fold"]
            output = run / "units" / f"{unit_key(symbol, fold, index, role, kind, repeat)}.json"
            parent = {"run_signature": identity["run_signature"], "ready_hash": ready["sha256"]}
            if output.exists():
                saved = read_json(output)
                if saved["parent"] != parent or digest({k: v for k, v in saved.items() if k != "sha256"}) != saved["sha256"]:
                    raise ValueError("Decision checkpoint sai parent/hash")
                completed += 1
                return
            initial = point_state(frames[symbol], symbol, index, protocol, sentiment)
            state = restore_state(ready["state"], initial)
            context = {"symbol": symbol, "fold": fold, "decision": index, "role": role,
                       "kind": kind, "repeat_id": repeat, "stage": "decision"}
            archive.context = context
            before = len(archive.ids)
            result = decide(state)
            combined = {**state, **result}
            prediction, confidence, ratio, source, reason = parser._parse_prediction(combined)
            if prediction not in ("LONG", "SHORT"):
                raise RuntimeError("Full không trả binary prediction; không tạo fallback")
            record = archive.clean({"parent": parent, "context": context, "prediction": prediction,
                      "confidence": confidence, "risk_reward_ratio": ratio, "decision_source": source,
                      "fallback_reason": reason, "decision_state": pack_state(result),
                      "request_ids": ready["request_ids"] + archive.ids[before:]})
            record["sha256"] = digest(record)
            write_json(output, record, exclusive=True)
            completed += 1
            print(f"Đã checkpoint {completed}: {symbol}/{fold}/{role}/{kind}/{repeat}.", flush=True)

        # Toàn bộ calibration trước test; không lấy LONG rate từ test.
        for item in manifest["schedule"]:
            for index in item["calibration"]:
                ready = ready_state(item, index, "calibration", 0)
                decision(item, index, "calibration", "e2e", 0, ready)
        for item in manifest["schedule"]:
            for index in item["test"]:
                first = ready_state(item, index, "test", 0)
                decision(item, index, "test", "e2e", 0, first)
                for repeat in range(1, protocol["decision_only_repeats"]):
                    decision(item, index, "test", "decision", repeat, first)
                for repeat in range(1, protocol["end_to_end_repeats"]):
                    ready = ready_state(item, index, "test", repeat)
                    decision(item, index, "test", "e2e", repeat, ready)
        artifacts = [p for directory in ("units", "ready", "calls") for p in (run / directory).glob("*.json")]
        artifacts += [run / "run_manifest.json", run / "usage.json"]
        write_json(completion, {**identity, "n_decisions": completed,
            "attempted_requests": archive.count, "status": "inference_complete_not_scientific_acceptance",
            "artifacts": [{"path": p.relative_to(run).as_posix(), "sha256": sha256_file(p)} for p in sorted(artifacts)]}, exclusive=True)
