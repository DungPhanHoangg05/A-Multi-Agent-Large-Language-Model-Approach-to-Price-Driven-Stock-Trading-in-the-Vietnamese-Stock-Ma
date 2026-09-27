"""Kiểm thử trích tín hiệu, provenance và checkpoint không gọi lại upstream."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from langchain_core.messages import AIMessage

from core.bayesian_memory import DEFAULT_DATA_DIR, read_json
from core.execution_prices import load_verified_execution_data
from core.historical_signals import FrozenSentimentSnapshot, HistoricalSignalExtractor, disk_articles, report_signal
from default_config import DEFAULT_CONFIG


REPORTS = {"indicator_report": "- Đồng thuận chủ đạo: **HỖN HỢP** — độ tin cậy thấp",
           "pattern_report": "**Thiên lệch dự báo:** Tăng",
           "trend_report": "**Hướng xu hướng:** Đi ngang"}


def fake_alpha(state):
    """Giữ nguyên snapshot tin; trả đủ năm factor có nhãn xác định."""
    data, report = state["sentiment_store"].get_sentiment_at(state["stock_name"], state["as_of_date"], None)
    data["alpha_results"] = [{"id": index, "signal": "TĂNG" if index <= 3 else "GIẢM"}
                             for index in range(1, 6)]
    return {"sentiment_data": data, "sentiment_report": report, "alpha_report": "Báo cáo alpha thử nghiệm"}


class LocalLLM:
    """Phản hồi có cấu trúc cho agent thật, không cần mạng hoặc API key."""

    def __init__(self):
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        text = " ".join(str(message.content) for message in messages)
        if "Hướng xu hướng" in text or "Trend direction" in text:
            content = ("**Hướng xu hướng:** Tăng\n**Mức hỗ trợ:** 40\n**Mức kháng cự:** 90\n"
                       "**Độ dốc đường xu hướng:** Đang tăng\n**Giá so với hỗ trợ:** Bật lên\n"
                       "**Phân tích chi tiết:** Các đáy cao dần.\n**Dự đoán xu hướng:** Tăng.\n**Độ tin cậy:** Trung bình")
        else:
            content = ("**Mô hình:** Kênh tăng\n**Độ tin cậy:** Trung bình\n**Thiên lệch dự báo:** Tăng\n"
                       "**Bằng chứng:** Các đáy cao dần\n**Nến quan trọng:** Nến tăng\n**Hàm ý giao dịch:** Theo chiều tăng")
        return AIMessage(content=content)


class HistoricalSignalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.events = load_verified_execution_data(DEFAULT_DATA_DIR, "FPT")
        cls.cutoff = cls.frame["Datetime"].iloc[599].strftime("%Y-%m-%d")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.upstream = Mock()
        self.upstream.invoke.return_value = copy.deepcopy(REPORTS)
        self.alpha = Mock(side_effect=fake_alpha)
        self.images = [patch("utils.static_util.generate_kline_image", return_value={}),
                       patch("utils.static_util.generate_trend_image", return_value={})]
        for image in self.images:
            image.start()
            self.addCleanup(image.stop)

    def extractor(self, **kwargs):
        return HistoricalSignalExtractor(self.upstream, kwargs.pop("alpha", self.alpha), self.directory.name,
                                         kwargs.pop("config", DEFAULT_CONFIG),
                                         execution_loader=kwargs.pop("loader", lambda symbol: (self.frame.copy(), self.events)),
                                         article_loader=kwargs.pop("articles", lambda symbol: []), **kwargs)

    def test_five_signals_provenance_and_disk_reuse(self):
        result = self.extractor().extract("FPT", self.cutoff)
        self.assertEqual(result["agent_signals"], {"trend": "NEUTRAL", "pattern": "BULLISH",
                         "indicator_consensus": "NEUTRAL", "alpha_consensus": "BULLISH", "sentiment": "NEUTRAL"})
        self.assertEqual(result["provenance"]["price_rows"], 600)
        self.assertEqual(result["provenance"]["price_end_date"], self.cutoff)
        self.assertFalse(result["provenance"]["news_is_reliable"])
        self.assertEqual(set(result["reports"]), {*REPORTS, "alpha_report", "sentiment_report"})
        self.assertNotIn("groq_api_key", str(result["provenance"]))
        result["reports"].clear()
        reloaded = self.extractor().extract("FPT", self.cutoff)
        self.assertEqual(len(reloaded["reports"]), 5)
        self.assertEqual(self.upstream.invoke.call_count, 1)
        self.assertEqual(self.alpha.call_count, 1)

    def test_alpha_retry_uses_saved_upstream(self):
        self.alpha.side_effect = [RuntimeError("Lỗi alpha thử nghiệm"), fake_alpha({
            "stock_name": "FPT", "as_of_date": self.cutoff,
            "sentiment_store": FrozenSentimentSnapshot("FPT", self.cutoff, [])})]
        with self.assertRaises(RuntimeError):
            self.extractor().extract("FPT", self.cutoff)
        result = self.extractor().extract("FPT", self.cutoff)
        self.assertEqual(result["agent_signals"]["alpha_consensus"], "BULLISH")
        self.assertEqual(self.upstream.invoke.call_count, 1)
        self.assertEqual(self.alpha.call_count, 2)

    def test_failed_upstream_never_automatically_repeated(self):
        self.upstream.invoke.side_effect = RuntimeError("Lỗi upstream thử nghiệm")
        with self.assertRaises(RuntimeError):
            self.extractor().extract("FPT", self.cutoff)
        with self.assertRaisesRegex(ValueError, "dở dang"):
            self.extractor().extract("FPT", self.cutoff)
        self.assertEqual(self.upstream.invoke.call_count, 1)

    def test_missing_upstream_report_rejected(self):
        self.upstream.invoke.return_value.pop("trend_report")
        with self.assertRaises(ValueError):
            self.extractor().extract("FPT", self.cutoff)
        self.alpha.assert_not_called()

    def test_changed_configuration_rejected_before_rerun(self):
        self.extractor().extract("FPT", self.cutoff)
        config = {**DEFAULT_CONFIG, "graph_llm_model": "changed-model"}
        with self.assertRaisesRegex(ValueError, "thay đổi"):
            self.extractor(config=config).extract("FPT", self.cutoff)
        self.assertEqual(self.upstream.invoke.call_count, 1)

    def test_corrupt_checkpoint_rejected(self):
        self.extractor().extract("FPT", self.cutoff)
        path = Path(self.directory.name) / f"FPT-{self.cutoff}.json"
        path.write_text(path.read_text(encoding="utf-8").replace('"BULLISH"', '"BEARISH"'), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.extractor().extract("FPT", self.cutoff)
        self.assertEqual(self.upstream.invoke.call_count, 1)

    def test_busy_point_lock_rejects_duplicate_worker(self):
        lock = Path(self.directory.name) / f"FPT-{self.cutoff}.lock"
        lock.touch()
        with self.assertRaises(RuntimeError):
            self.extractor().extract("FPT", self.cutoff)
        self.upstream.invoke.assert_not_called()

    def test_report_parser_rejects_unknown_missing_or_duplicate_field(self):
        for report in ("", "**Hướng xu hướng:** Không thể xác định", "**Hướng xu hướng:** Tăng | Giảm",
                       "**Hướng xu hướng:** Tăng\n**Hướng xu hướng:** Giảm"):
            with self.subTest(report=report), self.assertRaises(ValueError):
                report_signal(report, ("Hướng xu hướng",))
        self.assertEqual(report_signal("**Trend direction:** Downtrend", ("Trend direction",)), "BEARISH")

    def test_missing_or_duplicate_alpha_factors_rejected(self):
        for factors in ([], [{"id": 1, "signal": "TĂNG"}] * 5, [None] * 5):
            def bad_alpha(state):
                result = fake_alpha(state)
                result["sentiment_data"]["alpha_results"] = factors
                return result
            with tempfile.TemporaryDirectory() as directory:
                extractor = self.extractor(alpha=bad_alpha)
                extractor.checkpoint_dir = Path(directory)
                with self.assertRaises(ValueError):
                    extractor.extract("FPT", self.cutoff)

    def test_disk_news_missing_is_explicit_sparse_neutral(self):
        self.assertEqual(disk_articles(Path(self.directory.name), "FPT"), [])
        result = self.extractor().extract("FPT", self.cutoff)
        self.assertEqual(result["provenance"]["news_count"], 0)
        self.assertEqual(result["provenance"]["sentiment_model"], "neutral-insufficient-dated-history")

    def test_reliable_dated_news_uses_actual_aggregate(self):
        articles = [{"date_parsed": self.cutoff, "title": f"Tin {index}",
                     "url": f"https://example.test/article/{index}", "label": "positive",
                     "numeric_score": 0.8, "confidence": 0.9} for index in range(3)]
        result = self.extractor(articles=lambda symbol: articles).extract("FPT", self.cutoff)
        self.assertTrue(result["provenance"]["news_is_reliable"])
        self.assertEqual(result["provenance"]["news_count"], 3)
        self.assertEqual(result["agent_signals"]["sentiment"], "POSITIVE")

    def test_real_graph_alpha_and_raw_prices_with_local_llm(self):
        from utils.graph_setup import SetGraph
        from utils.graph_util import TechnicalTools

        self.images[0].stop()
        self.images[1].stop()
        llm = LocalLLM()
        builder = SetGraph(llm, llm, TechnicalTools())
        extractor = HistoricalSignalExtractor.from_graph_builder(builder, self.directory.name, DEFAULT_CONFIG,
                                                                  article_loader=lambda symbol: [])
        with patch("builtins.print"):
            result = extractor.extract("FPT", self.cutoff)
            restored = extractor.extract("FPT", self.cutoff)
        self.assertEqual(result, restored)
        self.assertEqual(llm.calls, 2)
        self.assertEqual(len(result["provenance"]["alpha_factors"]), 5)
        checkpoint = read_json(Path(self.directory.name) / f"FPT-{self.cutoff}.json")
        self.assertEqual(checkpoint["payload"]["stage"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
