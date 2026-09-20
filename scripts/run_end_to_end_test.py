"""Kiểm thử hồi quy đầu-cuối xác định cho pipeline nghiên cứu.

Script chạy một test point hoàn chỉnh mà không cần API key hay
mạng. Dữ liệu OHLCV và CafeF được tạo cố định; phần tính toán,
tạo ảnh, Alpha Selector, LangGraph, P&L và thống kê vẫn dùng mã sản
phẩm thật. Chỉ phần suy luận LLM được thay bằng bộ phản hồi có
cấu trúc để kết quả không phụ thuộc quota hoặc biến động mô hình.

Cách chạy chuẩn:
    py -3.13 scripts/run_end_to_end_test.py
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import random
import sys
import tempfile
import time
import tracemalloc
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

os.environ.setdefault("MPLBACKEND", "Agg")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# PowerShell/cmd có thể kế thừa code page không biểu diễn được log
# tiếng Việt của pipeline. Chuẩn hóa ngay từ runner để lệnh tái lập
# hoạt động giống nhau trong terminal và CI.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from langchain_core.messages import AIMessage

from agents.decision_agent import TradeDecisionOutput
from agents.sentiment_agent import _parse_listing_page
from core.backtest_engine import BacktestEngine
from data_manager.sentiment_cache import BacktestSentimentStore
from utils.graph_setup import ABLATION_CONFIGS, SetGraph
from utils.graph_util import TechnicalTools


RANDOM_SEED = 42
SYMBOL = "FPT"
N_ROWS = 603  # 600 nến tiền kiểm tra + horizon 3 nến.
WINDOW_SIZE = 45
EXPECTED_VARIANTS = ("full", "baseline")


class PipelineCheckError(AssertionError):
    """Lỗi hợp đồng của bộ kiểm thử E2E."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PipelineCheckError(message)


def _flatten_message_content(messages: Any) -> str:
    """Rút chuỗi từ payload LangChain để bộ LLM giả lập nhận diện node."""
    if isinstance(messages, str):
        return messages
    if isinstance(messages, dict):
        return " ".join(_flatten_message_content(value) for value in messages.values())
    if isinstance(messages, (list, tuple)):
        return " ".join(_flatten_message_content(value) for value in messages)
    content = getattr(messages, "content", None)
    return _flatten_message_content(content) if content is not None else str(messages)


class _StructuredDecisionLLM:
    def __init__(self, owner: "DeterministicTextLLM", schema: type) -> None:
        self.owner = owner
        self.schema = schema

    def invoke(self, prompt: Any) -> dict[str, Any]:
        self.owner.structured_calls += 1
        self.owner.last_decision_prompt = _flatten_message_content(prompt)
        payload = {
            "decision": "LONG",
            "forecast_horizon": "T+2.5",
            "confidence": "High",
            "risk_reward_ratio": 1.8,
            "evidence_for": "Price, momentum, and selected alpha factors are constructive.",
            "evidence_against": "Transaction costs remain a material execution risk.",
            "justification": "The deterministic fixture supports a net-positive LONG cycle.",
        }
        parsed = self.schema(**payload)
        return {
            "parsed": parsed,
            "raw": AIMessage(content=json.dumps(payload)),
            "parsing_error": None,
        }


class DeterministicTextLLM:
    """LLM thay thế cục bộ, tuân thủ API mà các agent đang dùng."""

    def __init__(self) -> None:
        self.direct_calls = 0
        self.structured_calls = 0
        self.last_decision_prompt = ""

    def invoke(self, prompt: Any) -> AIMessage:
        self.direct_calls += 1
        return AIMessage(content="Deterministic quantitative interpretation.")

    def with_structured_output(
        self,
        schema: type,
        method: str | None = None,
        include_raw: bool = False,
    ) -> _StructuredDecisionLLM:
        _require(schema is TradeDecisionOutput, "Decision Agent dùng sai schema")
        _require(method == "json_schema", "Decision Agent không dùng JSON schema")
        _require(include_raw is True, "Decision Agent không giữ raw response")
        return _StructuredDecisionLLM(self, schema)


class DeterministicVisionLLM:
    """Phản hồi định dạng chuẩn cho Pattern và Trend Agent."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, messages: Any) -> AIMessage:
        self.calls += 1
        prompt = _flatten_message_content(messages).lower()
        if "trend direction" in prompt or "trend analyst" in prompt:
            content = (
                "**Trend direction:** Up\n"
                "**Support level:** 84.0\n"
                "**Resistance level:** 89.0\n"
                "**Trendline slope:** Rising\n"
                "**Price vs support:** Holding above support\n"
                "**Detailed analysis:** Higher lows confirm a constructive structure.\n"
                "**Trend forecast:** Continued upside while support holds.\n"
                "**Confidence:** Medium"
            )
        else:
            content = (
                "**Pattern:** Rising channel\n"
                "**Confidence:** Medium\n"
                "**Directional bias:** Bullish\n"
                "**Evidence:** Higher lows and firm closes\n"
                "**Key candles:** Recent bullish continuation candle\n"
                "**Trading implication:** Maintain bullish bias above support"
            )
        return AIMessage(content=content)


class OfflineBacktestEngine(BacktestEngine):
    """BacktestEngine thật với I/O ngoại vi được tiêm fixture cục bộ."""

    DELAY_BETWEEN_VARIANTS = 0.0
    DELAY_BETWEEN_TESTS = 0.0

    def __init__(self, cache_dir: Path) -> None:
        super().__init__({
            "language": "en",
            "use_historical_sentiment": True,
            "agent_llm_temperature": 0.0,
            "graph_llm_temperature": 0.0,
            "tx_cost": 0.0025,
            "slippage": 0.001,
            "initial_capital_vnd": 50_000_000.0,
            "price_multiplier": 1_000.0,
        })
        self.cache_dir = cache_dir
        self.text_llm = DeterministicTextLLM()
        self.vision_llm = DeterministicVisionLLM()
        self.last_variant_states: dict[str, dict[str, Any]] = {}
        self.point_in_time_max: pd.Timestamp | None = None
        self.indicator_window_rows = 0
        self.indicator_window_max: pd.Timestamp | None = None

    def _init_sentiment_store(self, symbol: str, force_recrawl: bool = False):
        self._sentiment_store = BacktestSentimentStore(cache_dir=str(self.cache_dir))
        cache = self._sentiment_store.preload_symbol(
            symbol,
            force_recrawl=force_recrawl,
        )
        _require(cache._loaded, "Sentiment cache fixture không nạp được")

    def _init_graphs(self):
        graph_builder = SetGraph(
            self.text_llm,
            self.vision_llm,
            TechnicalTools(),
        )
        self._graph_upstream = graph_builder.compile_upstream()
        self._graph_decision_variants = {
            name: graph_builder.compile_decision(ablation_config=config)
            for name, config in ABLATION_CONFIGS.items()
        }
        self._graph_decision_full = self._graph_decision_variants["full"]
        self._graph_decision_no_alpha = self._graph_decision_variants["baseline"]

    def _run_ablation_variants(self, *args, **kwargs):
        ohlcv_dict = args[0]
        window_datetimes = pd.to_datetime(ohlcv_dict["Datetime"])
        self.indicator_window_rows = len(window_datetimes)
        self.indicator_window_max = pd.Timestamp(window_datetimes.max())
        point_in_time_df = kwargs.get("point_in_time_df")
        if point_in_time_df is not None:
            self.point_in_time_max = pd.Timestamp(point_in_time_df["Datetime"].max())
        results = super()._run_ablation_variants(*args, **kwargs)
        self.last_variant_states = {
            name: state for name, (state, _elapsed) in results.items()
        }
        return results


def _synthetic_ohlcv() -> pd.DataFrame:
    """Tạo chuỗi giá có xu hướng, dao động và thanh khoản không hằng."""
    index = np.arange(N_ROWS, dtype=float)
    close = 62.0 + 0.042 * index + 1.30 * np.sin(index / 11.0)
    close += 0.45 * np.cos(index / 5.0)
    open_price = close * (1.0 + 0.0018 * np.sin(index / 3.0))
    high = np.maximum(open_price, close) + 0.55 + 0.08 * np.cos(index / 7.0)
    low = np.minimum(open_price, close) - 0.52 - 0.07 * np.sin(index / 8.0)
    volume = 1_100_000 + 220_000 * np.sin(index / 13.0)
    volume += 75_000 * np.cos(index / 4.0) + index * 450
    return pd.DataFrame({
        "Datetime": pd.bdate_range("2023-01-02", periods=N_ROWS),
        "Open": open_price,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume.astype(float),
    })


def _write_sentiment_fixture(cache_dir: Path, df: pd.DataFrame) -> None:
    decision_cutoff = pd.Timestamp(df["Datetime"].iloc[599])
    labels = ["positive", "positive", "neutral", "positive",
              "negative", "positive", "neutral", "positive"]
    scores = [0.72, 0.61, 0.0, 0.55, -0.36, 0.66, 0.0, 0.58]
    articles = []
    for index, (label, score) in enumerate(zip(labels, scores), start=1):
        article_date = decision_cutoff - pd.Timedelta(days=index * 3)
        articles.append({
            "title": f"FPT deterministic research news item {index}",
            "url": f"https://cafef.vn/fpt-fixture-{20260000 + index}.chn",
            "snippet": "Deterministic local article used by the regression test.",
            "content": "FPT reports a deterministic operating update for testing.",
            "date": article_date.strftime("%d/%m/%Y"),
            "date_parsed": article_date.strftime("%Y-%m-%d"),
            "label": label,
            "confidence": abs(score) if score else 0.5,
            "numeric_score": score,
            "scorer": "e2e-deterministic-fixture",
            "is_fallback": False,
        })
    payload = {
        "symbol": SYMBOL,
        "saved_at": "2026-09-20T00:00:00",
        "scored_articles": articles,
    }
    path = cache_dir / f"sentiment_cache_{SYMBOL}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _check_environment() -> None:
    _require(sys.version_info[:2] == (3, 13), "Bắt buộc chạy bằng Python 3.13")
    modules = (
        "pandas", "numpy", "scipy", "talib", "matplotlib", "mplfinance",
        "langchain", "langgraph", "bs4", "PIL", "requests", "vnstock",
    )
    missing = [name for name in modules if importlib.util.find_spec(name) is None]
    _require(not missing, f"Thiếu dependency trong requirements.txt: {missing}")
    _require((REPO_ROOT / "requirements.txt").is_file(), "Thiếu requirements.txt")
    print(f"[PASS] Environment: Python {sys.version.split()[0]} and required packages")


def _check_data_contract(df: pd.DataFrame) -> None:
    expected = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
    _require(list(df.columns) == expected, "Sai schema OHLCV")
    _require(len(df) == N_ROWS, "Sai số nến fixture")
    _require(df["Datetime"].is_monotonic_increasing, "Datetime không tăng dần")
    _require(not df.isna().any().any(), "OHLCV chứa NaN")
    _require((df[["Open", "High", "Low", "Close", "Volume"]] > 0).all().all(),
             "OHLCV chứa giá trị không dương")
    print(f"[PASS] Data load contract: {len(df)} ordered OHLCV rows")


def _check_cafef_parser() -> None:
    html = """
    <html><body><div class="news-item">
      <h3><a href="/fpt-tang-truong-on-dinh-20260901123456.chn"
             title="FPT duy tri tang truong on dinh trong quy moi">
             FPT duy tri tang truong on dinh trong quy moi</a></h3>
      <span>01/09/2026</span>
      <p>Noi dung tom tat dai hon ba muoi ky tu cho bo kiem thu parser CafeF.</p>
    </div></body></html>
    """
    articles = _parse_listing_page(html)
    _require(len(articles) == 1, "CafeF parser không trích xuất đúng 1 bài")
    article = articles[0]
    _require(article["url"].startswith("https://cafef.vn/"), "URL CafeF chưa chuẩn hóa")
    _require(article["date"] == "01/09/2026", "Ngày CafeF sai định dạng")
    _require(len(article["snippet"]) > 30, "CafeF snippet bị thiếu")
    print("[PASS] CafeF crawling/parser contract")


def _check_agent_states(engine: OfflineBacktestEngine, cutoff: pd.Timestamp) -> None:
    _require(set(engine.last_variant_states) == set(EXPECTED_VARIANTS),
             "Không thu được đủ state Full/Baseline")
    full = engine.last_variant_states["full"]
    for key in ("indicator_report", "pattern_report", "trend_report",
                "alpha_report", "sentiment_report", "final_trade_decision"):
        _require(isinstance(full.get(key), str) and full[key].strip(),
                 f"Full state thiếu output {key}")

    sentiment = full.get("sentiment_data")
    _require(isinstance(sentiment, dict), "Sentiment Cache output không phải dict")
    for key in ("target_stock", "main_sentiment", "scored_articles",
                "model_used", "cutoff_date", "n_articles_used", "alpha_results"):
        _require(key in sentiment, f"Sentiment Cache output thiếu {key}")
    _require(sentiment["target_stock"] == SYMBOL, "Sentiment sai ticker")
    _require(sentiment["n_articles_used"] == 8, "Sentiment không dùng đủ fixture")
    for article in sentiment["scored_articles"]:
        _require(pd.Timestamp(article["date_parsed"]) <= cutoff,
                 "Sentiment Cache lọt bài sau cutoff")
        for key in ("label", "numeric_score", "scorer", "is_fallback"):
            _require(key in article, f"Bài sentiment thiếu {key}")

    alphas = sentiment["alpha_results"]
    _require(isinstance(alphas, list) and len(alphas) == 5,
             "Alpha Selector không trả đúng top-5")
    for alpha in alphas:
        for key in ("id", "name", "type", "formula", "horizon", "value",
                    "signal", "components", "interpretation"):
            _require(key in alpha, f"Alpha output thiếu {key}")
        _require(alpha["signal"] in {"TĂNG", "GIẢM", "TRUNG TÍNH"},
                 "Alpha signal ngoài hợp đồng")
        _require(math.isfinite(float(alpha["value"])), "Alpha value không hữu hạn")

    for variant in EXPECTED_VARIANTS:
        decision = json.loads(engine.last_variant_states[variant]["final_trade_decision"])
        for key in ("decision", "forecast_horizon", "confidence",
                    "risk_reward_ratio", "evidence_for", "evidence_against",
                    "justification", "decision_source", "fallback_reason"):
            _require(key in decision, f"Decision output thiếu {key}")
        _require(decision["decision"] in {"LONG", "SHORT"}, "Decision không nhị phân")
        _require(decision["decision_source"] == "llm_structured",
                 "Decision không đi qua Structured Output")

    _require(engine.vision_llm.calls == 2,
             "Pattern/Trend không chạy đúng một lần trong shared upstream")
    _require(engine.text_llm.structured_calls == 2,
             "Decision Agent không chạy đúng Full/Baseline")
    _require(engine.point_in_time_max == cutoff,
             "Alpha Selector nhìn thấy dữ liệu sau nến quyết định")
    _require(engine.indicator_window_rows == WINDOW_SIZE,
             "Indicator Agent không nhận đúng cửa sổ W")
    _require(engine.indicator_window_max == cutoff,
             "Indicator Agent nhìn thấy nến tương lai")
    print("[PASS] Five-agent graph and Decision/Alpha/Sentiment formats")


def _walk_numbers(value: Any) -> Iterable[float]:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        yield float(value)
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _walk_numbers(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_numbers(nested)


def _check_result_json(result_path: Path) -> dict[str, Any]:
    _require(result_path.is_file(), "Backtest không tạo JSON")
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    required = {
        "symbol", "timeframe", "n_tests", "acc_full", "acc_no_alpha",
        "mcnemar_p_value", "alpha_lift_ci_95", "newey_west_p_value",
        "pnl_full", "pnl_no_alpha", "equity_curve_full_vnd",
        "equity_curve_no_alpha_vnd", "test_points",
    }
    _require(required.issubset(payload), f"JSON thiếu trường: {sorted(required - payload.keys())}")
    _require(payload["symbol"] == SYMBOL and payload["n_tests"] == 1,
             "JSON sai ticker hoặc số test point")
    _require(len(payload["test_points"]) == 1, "JSON không có đúng 1 test point")
    _require(all(math.isfinite(number) for number in _walk_numbers(payload)),
             "JSON chứa NaN/Infinity")

    point = payload["test_points"][0]
    _require(not point["error_full"] and not point["error_no_alpha"],
             "Test point ghi nhận lỗi agent")
    _require(point["executed_action_full"] == "BUY_SELL",
             "LONG không được thực thi BUY→SELL")
    _require(point["transaction_fee_full_vnd"] > 0.0,
             "P&L chưa trừ phí giao dịch")
    _require(point["slippage_cost_full_vnd"] > 0.0,
             "P&L chưa trừ trượt giá")
    expected_equity = payload["initial_capital_vnd"] * (
        1.0 + point["account_return_full"] / 100.0
    )
    _require(math.isclose(point["equity_full_vnd"], expected_equity,
                          rel_tol=0.0, abs_tol=0.05),
             "Equity chi tiết không khớp phép ghép lãi")
    _require(payload["equity_full_vnd"] == round(point["equity_full_vnd"], 0),
             "Equity tóm tắt không khớp test point")
    _require(len(payload["equity_curve_full_vnd"]) == 2,
             "Equity curve sai độ dài")
    print("[PASS] Compounded P&L, costs, statistics, and JSON integrity")
    return payload


@contextmanager
def _working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def run_pipeline() -> tuple[float, float]:
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    _check_environment()
    _check_cafef_parser()
    df = _synthetic_ohlcv()
    _check_data_contract(df)

    started = time.perf_counter()
    tracemalloc.start()
    with tempfile.TemporaryDirectory(prefix="quantagent_e2e_") as temp_name:
        temp_dir = Path(temp_name)
        _write_sentiment_fixture(temp_dir, df)
        engine = OfflineBacktestEngine(temp_dir)
        result_path = temp_dir / "end_to_end_result.json"
        with _working_directory(temp_dir):
            engine.run(
                df=df,
                symbol=SYMBOL,
                timeframe="1d",
                n_tests=1,
                window_size=WINDOW_SIZE,
                step=3,
                result_path=str(result_path),
            )

        cutoff = pd.Timestamp(df["Datetime"].iloc[599])
        _check_agent_states(engine, cutoff)
        _check_result_json(result_path)
        _require((temp_dir / "kline_chart.png").stat().st_size > 0,
                 "Không tạo được ảnh K-line")
        _require((temp_dir / "trend_graph.png").stat().st_size > 0,
                 "Không tạo được ảnh trend")
        _require(result_path.with_suffix(".png").stat().st_size > 0,
                 "Không tạo được ảnh kết quả backtest")
        print("[PASS] Chart generation artifacts")

    _current, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    elapsed = time.perf_counter() - started
    peak_mb = peak_bytes / (1024 * 1024)
    _require(math.isfinite(elapsed) and elapsed > 0.0, "Runtime không hợp lệ")
    _require(math.isfinite(peak_mb) and peak_mb > 0.0, "Memory metric không hợp lệ")
    print(f"[PASS] Runtime and memory: {elapsed:.1f}s, {peak_mb:.1f} MiB peak traced")
    return elapsed, peak_mb


def main() -> int:
    try:
        elapsed, _peak_mb = run_pipeline()
    except Exception as exc:
        print(f"[FAIL] END-TO-END PIPELINE: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"[PASS] ALL PIPELINE CHECKS SUCCESSFUL IN {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
