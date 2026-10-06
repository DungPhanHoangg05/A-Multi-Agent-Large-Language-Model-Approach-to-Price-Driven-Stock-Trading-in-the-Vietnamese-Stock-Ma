"""Nguồn file/model nhỏ xác định cho adapter PIT; không fit hoặc dùng archive local."""

from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd

from agents.alpha_agent import _build_alpha_report
from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_retriever import BayesianPriorRetriever
from core.execution_prices import PRICE_COLUMNS, RAW_FIELD_MAP, STOCK_SYMBOLS, load_verified_execution_data, raw_point_in_time_snapshot
from core.historical_signals import CODE_FILES, FrozenSentimentSnapshot, digest, snapshot_payload
from core.prior_context import PriorContextAdapter, _runtime_identity
from core.regime_detector import FEATURE_COLUMNS, HMM_PARAMETERS, MarketRegimeDetector, _payload_hash, _regime_calibration, _runtime_versions, training_data_hash

CODE_ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    """Ghi file fixture UTF-8 có nội dung hữu hạn."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")


def envelope(path: Path, value: dict) -> None:
    """Dùng đúng envelope journal, không dùng cách băm model."""
    write_json(path, {"payload": value, "sha256": digest(value)})


def model_file(path: Path, history: pd.DataFrame) -> None:
    """Tạo tham số HMM/scaler xác định; loader thật kiểm envelope, không chạy fit."""
    means = [[-.005, .02, -.10, -.12, -.15], [.005, .01, .10, .12, .15],
             [0., .005, .001, .001, .001], [0., .04, .08, -.08, .08]]
    meta = {"source_symbol": "VNINDEX", "parameters": dict(HMM_PARAMETERS),
        "feature_columns": list(FEATURE_COLUMNS), "versions": _runtime_versions(),
        "train_start_date": history.Datetime.iloc[0].strftime("%Y-%m-%d"),
        "train_end_date": history.Datetime.iloc[-1].strftime("%Y-%m-%d"),
        "training_rows": int(len(history)), "feature_rows": int(len(history) - 199),
        "training_data_sha256": training_data_hash(history), "iterations": 10,
        "last_gain": .0005, "em_converged": True, "state_occupancy": [.25] * 4,
        "state_feature_means": means, "volatility_quantiles": [.007, .022],
        "trend_threshold": .04, "ma200_train_std": .05,
        "price_basis_status": "UNVERIFIED", "artifact_purpose": "RESEARCH_ONLY"}
    meta.update(_regime_calibration(meta))
    payload = {"format_version": 2, "metadata": meta,
        "model": {"startprob": [.25] * 4, "transmat": [[.25] * 4 for _ in range(4)],
                  "means": means, "covars": [[1.] * 5 for _ in range(4)]},
        "scaler": {"mean": [0.] * 5, "scale": [1.] * 5, "var": [1.] * 5}}
    write_json(path, {"payload": payload, "sha256": _payload_hash(payload)})


class ContextFixture:
    """Repo dữ liệu tạm gồm evidence VCI, tin, VNINDEX, model và kho QA."""

    def __init__(self, articles: list[dict] | None = None, *, lang: str = "vi") -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.dates = pd.bdate_range("2018-01-02", periods=700)
        self.cutoff = self.day(644)
        self.frame = {}
        manifest = {"source_library": "vnstock", "source_library_version": "fixture-4.0",
            "price_gate": "PASS", "price_basis": "UNADJUSTED_EXECUTION", "price_unit": "thousand_VND",
            "primary_source": "VCI", "crosscheck_sources": ["VCI", "KBS"], "raw_field_map": RAW_FIELD_MAP,
            "requested_start": self.day(0), "requested_end": self.day(699), "files": {}}
        for offset, symbol in enumerate(STOCK_SYMBOLS):
            directory = self.root / "data/execution_prices"
            directory.mkdir(parents=True, exist_ok=True)
            close = 100 + offset * 10 + .001 * np.arange(700)
            records = [{"ticker": symbol, "tradingDate": day, "openPrice": float(price * 1000),
                "highestPrice": float((price + 1) * 1000), "lowestPrice": float((price - 1) * 1000),
                "closePrice": float(price * 1000), "referencePrice": float(reference * 1000),
                "matchPrice": float(price * 1000), "totalMatchVolume": 1000}
                for day, price, reference in zip(self.dates.strftime("%Y-%m-%d"), close, np.r_[close[0], close[:-1]])]
            from core.execution_prices import normalise_vci_execution_prices
            frame = normalise_vci_execution_prices(records, symbol, self.day(0), self.day(699))
            frame.to_csv(directory / f"{symbol}.csv", index=False, date_format="%Y-%m-%d", float_format="%.17g")
            (directory / f"{symbol}.evidence.json.gz").write_bytes(gzip.compress(json.dumps({"records": records}).encode("utf-8")))
            write_json(directory / f"{symbol}.events.json", {"records": []})
            manifest["files"][symbol] = {"rows": 700, **{key: {"file": f"{symbol}{suffix}",
                "sha256": hashlib.sha256((directory / f"{symbol}{suffix}").read_bytes()).hexdigest()}
                for key, suffix in (("csv", ".csv"), ("evidence", ".evidence.json.gz"), ("events", ".events.json"))}}
        write_json(self.root / "data/execution_prices/manifest.json", manifest)
        self.frame = {symbol: load_verified_execution_data(self.root / "data/execution_prices", symbol)[0]
                      for symbol in STOCK_SYMBOLS}
        index = np.arange(700, dtype=float)
        close = 1000. * np.exp(.0002 * index + .06 * np.sin(index / 21))
        vnindex = pd.DataFrame({"Datetime": self.dates, "Open": close, "High": close + 1,
                               "Low": close - 1, "Close": close, "Volume": 1000})
        path = self.root / "data/historical/VNINDEX.csv"
        path.parent.mkdir(parents=True)
        vnindex.to_csv(path, index=False, date_format="%Y-%m-%d", float_format="%.17g")
        self.vnindex = pd.read_csv(path, parse_dates=["Datetime"])
        write_json(path.parent / "manifest.json", {"source_library": "vnstock", "sources": ["VCI", "KBS"],
            "primary_source": "VCI", "interval": "1d", "files": {"VNINDEX": {"file": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}})
        for symbol in STOCK_SYMBOLS:
            write_json(self.root / f"run/inputs/news/{symbol}.json", {"symbol": symbol, "scored_articles": articles or []})
        model_file(self.root / f"run/regimes/VNINDEX-{self.cutoff}.json", self.vnindex.iloc[:645])
        model_file(self.root / "model/fixed.json", self.vnindex.iloc[:600])
        self.config = {"models": {"agent_llm_model": "mock/decision", "graph_llm_model": "mock/vision",
            "agent_llm_temperature": 0., "graph_llm_temperature": 0.,
            "agent_llm_max_tokens": 2048, "graph_llm_max_tokens": 1024}, "window_size": 45,
            "norm_method": "zscore_tanh", "alpha_weights": None, "language": lang, "time_frame": "1d"}
        self.prior_config = {"enable_bayesian_prior": True, "bank_path": "bank/bank.json",
                             "manifest_path": "bank/manifest.json", "audit_path": "bank/audit.json"}
        self.records = [self.record(position, "BULL") for position in (600, 603, 606)]
        detector = MarketRegimeDetector.load(self.root / f"run/regimes/VNINDEX-{self.cutoff}.json")
        self.regime = detector.classify_regime(self.vnindex.iloc[:645], self.cutoff)
        self.records.append(self.record(644, self.regime["regime_name"]))
        self.publish_bank("a" * 64)

    def close(self) -> None:
        """Dọn duy nhất repo dữ liệu fixture trong thư mục tạm."""
        self.directory.cleanup()

    def day(self, position: int) -> str:
        return self.dates[position].strftime("%Y-%m-%d")

    def record(self, position: int, regime: str) -> dict:
        """Nhãn fixture dùng chính engine kinh tế và giá thực thi đã dựng."""
        net = float(100 * compute_round_trip_net_return(float(self.frame["FPT"].Open.iloc[position + 1]),
                                                       float(self.frame["FPT"].Close.iloc[position + 3])))
        return {"episode_id": f"FPT:{self.day(position)}", "symbol": "FPT", "as_of_date": self.day(position),
            "entry_date": self.day(position + 1), "exit_date": self.day(position + 3), "regime": regime,
            "agent_signals": {"trend": "BULLISH", "pattern": "NEUTRAL", "indicator_consensus": "BEARISH",
                              "alpha_consensus": "NEUTRAL", "sentiment": "NEUTRAL"},
            "outcome": {"actual_direction": "UP" if net > 0 else "DOWN", "net_return_pct": net,
                        "result": "WIN_IF_LONG" if net > 0 else "LOSS_IF_LONG", "was_bull_trap": bool(net <= 0)}}

    def publish_bank(self, signature: str) -> None:
        write_json(self.root / "bank/bank.json", self.records)
        counts = {"by_symbol": dict(Counter(row["symbol"] for row in self.records)),
                  "by_regime": dict(Counter(row["regime"] for row in self.records)),
                  "by_year": dict(Counter(row["as_of_date"][:4] for row in self.records))}
        evidence = {"format_version": 1, "bank_sha256": hashlib.sha256((self.root / "bank/bank.json").read_bytes()).hexdigest(),
                    "run_signature": signature, "completed": len(self.records), **counts}
        write_json(self.root / "bank/manifest.json", {**evidence, "remaining": 0})
        write_json(self.root / "bank/audit.json", {**evidence, "status": "PASS", "schema_sha256": hashlib.sha256(
            (CODE_ROOT / "docs/plan/week1/historical_task_record.schema.json").read_bytes()).hexdigest()})

    def retriever(self) -> BayesianPriorRetriever:
        """Chỉ chuyển loader mặc định về repo fixture, giữ validator nhãn thật."""
        with patch("core.bayesian_memory.load_verified_execution_data",
                   side_effect=lambda _directory, symbol: (self.frame[symbol], [])):
            return BayesianPriorRetriever(bank_path=self.root / "bank/bank.json",
                manifest_path=self.root / "bank/manifest.json", audit_path=self.root / "bank/audit.json")

    def adapter(self, **kwargs) -> PriorContextAdapter:
        """Khởi tạo adapter production bằng file fixture và retriever đã kiểm."""
        options = {"root": self.root, "news_dir": "run/inputs/news", "prefix_artifact_dir": "run/regimes",
                   "signal_config": self.config, **kwargs}
        if "retriever" not in options:
            options["retriever"] = self.retriever()
        if options.get("provider_mode") == "fixed_train_oos":
            options["prefix_artifact_dir"] = None
        return PriorContextAdapter(self.prior_config, **options)

    @staticmethod
    def factors() -> list[dict]:
        """Năm factor cho builder báo cáo thật, đồng thuận trung tính."""
        return [{"id": i + 1, "name": f"Factor {i + 1}", "type": "fixture", "value": "0.10",
                 "signal": signal, "horizon": "T+2.5", "formula": "fixture", "components": {},
                 "interpretation": "Dữ liệu tổng hợp xác định."}
                for i, signal in enumerate(("TĂNG", "GIẢM", "TRUNG TÍNH", "TĂNG", "GIẢM"))]

    def reports(self, sentiment: FrozenSentimentSnapshot) -> dict:
        """Tái sử dụng builder Alpha thật để kiểm cả VI/EN và bảng factor."""
        lang = self.config["language"]
        factors = self.factors()
        report = _build_alpha_report(factors, {"has_volume": True}, {}, "FPT", lang)
        report += "\n**TỔNG HỢP: TRUNG TÍNH**\n" if lang == "vi" else "\n**SUMMARY: NEUTRAL**\n"
        return {"trend_report": "Hướng xu hướng: Tăng\n" if lang == "vi" else "Trend direction: Bullish\n",
            "pattern_report": "Thiên lệch dự báo: Đi ngang\n" if lang == "vi" else "Directional bias: Neutral\n",
            "indicator_report": "Đồng thuận chủ đạo: Giảm\n" if lang == "vi" else "Dominant consensus: Bearish\n",
            "alpha_report": report, "sentiment_report": sentiment.report}

    def full(self, point) -> dict:
        """Full giả lập giữ mọi input; không gọi Indicator/vision/LLM."""
        state = point.agent_state()
        sentiment = state["sentiment_store"]
        state.update(self.reports(sentiment), sentiment_data={**deepcopy(sentiment.data), "alpha_results": self.factors()})
        return state

    def make_replay(self) -> None:
        """Journal xác định có run/episode/checkpoint liên kết; không lấy archive local."""
        symbol, cutoff = "FPT", self.cutoff
        snapshot = raw_point_in_time_snapshot(self.frame[symbol], cutoff)
        articles = json.loads((self.root / "run/inputs/news/FPT.json").read_text("utf-8"))["scored_articles"]
        sentiment = FrozenSentimentSnapshot(symbol, cutoff, articles)
        reports = self.reports(sentiment)
        signals = deepcopy(self.records[-1]["agent_signals"])
        signals["sentiment"] = {"positive": "POSITIVE", "negative": "NEGATIVE", "neutral": "NEUTRAL"}[
            sentiment.data["main_sentiment"]["label"]]
        self.records[-1]["agent_signals"] = signals
        code = {name: hashlib.sha256(("historical:" + name).encode()).hexdigest() for name in CODE_FILES}
        runtime = {name: "historical-fixture" for name in _runtime_identity()}
        provenance = {"symbol": symbol, "as_of_date": cutoff, "price_basis": "UNADJUSTED_EXECUTION",
            "price_source": "VCI", "price_unit": "thousand_VND", "price_sha256": digest(snapshot_payload(snapshot)),
            "price_start_date": self.day(0), "price_end_date": cutoff, "price_rows": int(len(snapshot)),
            "alpha_start_date": self.day(45), "alpha_end_date": cutoff, "news_sha256": digest(sentiment.articles),
            "news_dates": [item["date_parsed"] for item in sentiment.articles], "news_count": len(sentiment.articles),
            "news_is_reliable": bool(sentiment.data["is_reliable"]), "sentiment_model": sentiment.data["model_used"],
            "config": self.config, "runtime": runtime, "code_sha256": code,
            "reports_sha256": digest(reports), "alpha_factors": self.factors()}
        run = {"models": self.config["models"], "signal_config": self.config, "code_sha256": code,
               "runtime": runtime}
        self.publish_bank(digest(run))
        envelope(self.root / "run/run_manifest.json", run)
        signal_path = self.root / f"run/signals/FPT-{cutoff}.json"
        signed_input = {key: value for key, value in provenance.items() if key not in ("reports_sha256", "alpha_factors")}
        envelope(signal_path, {"stage": "COMPLETE", "signature": digest(signed_input),
            "reports": {field: reports[field] for field in ("indicator_report", "pattern_report", "trend_report")},
            "result": {"symbol": symbol, "as_of_date": cutoff, "agent_signals": signals,
                       "reports": reports, "provenance": provenance}})
        detector = MarketRegimeDetector.load(self.root / f"run/regimes/VNINDEX-{cutoff}.json")
        proof = {"state": self.regime, "metadata": detector.metadata, "artifact_sha256": hashlib.sha256(
            (self.root / f"run/regimes/VNINDEX-{cutoff}.json").read_bytes()).hexdigest()}
        envelope(self.root / f"run/episodes/FPT-{cutoff}.json", {"signature": digest(run), "record": self.records[-1],
            "provenance": {"regime": proof, "signal_checkpoint_sha256": hashlib.sha256(signal_path.read_bytes()).hexdigest()}})
