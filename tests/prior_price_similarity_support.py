"""Kho nhỏ có nhãn engine thật và index/scaler thật cho similarity giá."""

from collections import Counter
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
from typing import Any
from unittest.mock import patch

import numpy as np

from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_retriever import BayesianPriorRetriever, ROOT
from core.pit_price_features import extract_pit_price_features
from core.price_feature_index import build_price_feature_index
from price_feature_index_support import index_inputs
from prior_context_test_support import write_json

SIGNALS = {"trend": "BULLISH", "pattern": "NEUTRAL", "alpha_consensus": "NEUTRAL",
           "indicator_consensus": "BEARISH", "sentiment": "NEUTRAL"}


class PriceSimilarityFixture:
    """Tạo bank/QA tạm; giá và outcome được kiểm bằng loader/engine production."""

    def __init__(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.inputs = index_inputs()
        # Một chu kỳ WIN thật để phép hoán vị nhãn kiểm cả WIN/LOSS, không chỉ net-return.
        frame = self.inputs["prices"]["FPT"][0]
        close = frame.Close.to_numpy(copy=True)
        close[self.inputs["calendar"].get_loc("2020-06-04")] *= 1.1
        for column, values in (("Open", close), ("Close", close), ("High", close + 1),
                               ("Low", close - 1), ("Reference", np.r_[close[0], close[:-1]])):
            frame[column] = values
        self.records = []
        for projected in self.inputs["records"]:
            frame, _ = self.inputs["prices"][projected["symbol"]]
            position = self.inputs["calendar"].get_loc(projected["as_of_date"])
            net = float(100 * compute_round_trip_net_return(float(frame.Open.iloc[position + 1]),
                                                            float(frame.Close.iloc[position + 3])))
            signals = deepcopy(SIGNALS)
            if projected["as_of_date"] == "2020-06-04":
                signals["pattern"] = "BULLISH"
            self.records.append({**projected, "entry_date": self.inputs["calendar"][position + 1].strftime("%Y-%m-%d"),
                "regime": "BEAR" if projected["as_of_date"] == "2020-06-09" else "BULL",
                "agent_signals": signals, "outcome": {"actual_direction": "UP" if net > 0 else "DOWN",
                    "net_return_pct": net, "result": "WIN_IF_LONG" if net > 0 else "LOSS_IF_LONG",
                    "was_bull_trap": bool(net <= 0)}})
        self.publish()

    def close(self) -> None:
        """Dọn repo fixture thuộc đúng tiến trình kiểm thử."""
        self.directory.cleanup()

    def publish(self) -> None:
        """Phát hành bank fixture rồi khởi tạo retriever/index được kiểm thật."""
        bank, manifest, audit = [self.root / name for name in ("bank.json", "manifest.json", "audit.json")]
        write_json(bank, self.records)
        evidence = {"format_version": 1, "bank_sha256": hashlib.sha256(bank.read_bytes()).hexdigest(),
            "run_signature": "a" * 64, "completed": len(self.records),
            **{key: dict(Counter(row[field] if field != "as_of_date" else row[field][:4] for row in self.records))
               for key, field in (("by_symbol", "symbol"), ("by_regime", "regime"), ("by_year", "as_of_date"))}}
        write_json(manifest, {**evidence, "remaining": 0})
        write_json(audit, {**evidence, "status": "PASS", "schema_sha256": hashlib.sha256(
            (ROOT / "docs/plan/week1/historical_task_record.schema.json").read_bytes()).hexdigest()})
        with patch("core.bayesian_memory.load_verified_execution_data",
                   side_effect=lambda _path, symbol: self.inputs["prices"][symbol]):
            self.retriever = BayesianPriorRetriever(bank_path=bank, manifest_path=manifest, audit_path=audit)
        self.inputs["records"] = [{key: row[key] for key in ("episode_id", "symbol", "as_of_date", "exit_date")}
                                  for row in self.records]
        self.inputs["provenance"]["bank"] = {"bank_sha256": evidence["bank_sha256"]}
        self.index = build_price_feature_index(**self.inputs)

    def query(self, *, symbol: str = "FPT", cutoff: str = "2022-01-06", regime: str = "BULL") -> dict[str, Any]:
        """Nguồn query cùng extractor, không nhận nhãn hoặc giá thoát query."""
        frame, events = self.inputs["prices"][symbol]
        return {"index": self.index, "symbol": symbol, "as_of_date": cutoff, "current_regime": regime,
            "current_signals": deepcopy(SIGNALS), "query_features": extract_pit_price_features(
                frame, events, self.inputs["calendar"], cutoff, source=self.inputs["source"])}
