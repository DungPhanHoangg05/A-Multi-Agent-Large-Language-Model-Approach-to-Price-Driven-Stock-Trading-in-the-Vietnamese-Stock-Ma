"""Kiểm bộ đọc Trend viết tắt và tiếp tục checkpoint mà không gọi lại upstream."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.bayesian_memory import DEFAULT_DATA_DIR, read_json
from core.execution_prices import load_verified_execution_data
from core.historical_signals import HistoricalSignalExtractor, digest
from default_config import DEFAULT_CONFIG
from scripts.run_paced_historical_memory import REPORT_PARSE_FILE, make_compatible_report_parser

LABELS = ("Hướng xu hướng", "Trend direction")
TREND = "**Phân tích xu hướng:**\n\nHướng xu: Tăng Mức h: 87.0 Mức k: 94.5 Độ dốc đường xu: Đang tăng Giá so với h."


class HistoricalReportCompatTests(unittest.TestCase):
    def test_exact_saved_format_and_receipt_are_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            parse = make_compatible_report_parser(output)
            self.assertEqual(parse(TREND, LABELS), "BULLISH")
            before = (output / REPORT_PARSE_FILE).read_bytes()
            self.assertEqual(parse(TREND, LABELS), "BULLISH")
            self.assertEqual((output / REPORT_PARSE_FILE).read_bytes(), before)
            envelope = read_json(output / REPORT_PARSE_FILE)
            self.assertEqual(envelope["sha256"], digest(envelope["payload"]))
            entry = envelope["payload"]["entries"][0]
            self.assertEqual(entry["report_sha256"], digest(TREND))
            self.assertEqual(len(entry["parser_sha256"]), 64)

    def test_canonical_parser_behavior_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            parse = make_compatible_report_parser(Path(directory))
            self.assertEqual(parse("**Hướng xu hướng:** Giảm", LABELS), "BEARISH")
            self.assertFalse((Path(directory) / REPORT_PARSE_FILE).exists())
            for report in ("Hướng xu hướng: Tăng | Giảm\nHướng xu: Tăng",
                           "Hướng xu hướng: Tăng\nHướng xu hướng: Giảm"):
                with self.subTest(report=report), self.assertRaises(ValueError):
                    parse(report, LABELS)

    def test_ambiguous_missing_and_other_agent_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            parse = make_compatible_report_parser(Path(directory))
            for report in ("Hướng xu: Tăng | Giảm", "Hướng xu: Tăng Giảm",
                           "Hướng xu: Tăng Mức h: 87 Hướng xu: Giảm",
                           "Hướng xu: Tăng\nHướng xu: Giảm", "Hướng xu: Không rõ",
                           "Diễn giải: Hướng xu: Tăng", "Hướng xu: Tăng có thể giảm"):
                with self.subTest(report=report), self.assertRaises(ValueError):
                    parse(report, LABELS)
            with self.assertRaises(ValueError):
                parse(TREND, ("Thiên lệch dự báo", "Directional bias"))

    def test_corrupt_receipt_stops_instead_of_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            parse = make_compatible_report_parser(output)
            parse(TREND, LABELS)
            with patch("scripts.run_paced_historical_memory.read_json", return_value={
                    "payload": {"format_version": 1, "entries": []}, "sha256": "invalid"}):
                with self.assertRaisesRegex(ValueError, "checksum"):
                    parse(TREND, LABELS)

    def test_resume_uses_saved_reports_without_second_upstream(self):
        frame, events = load_verified_execution_data(DEFAULT_DATA_DIR, "FPT")
        cutoff = frame["Datetime"].iloc[599].strftime("%Y-%m-%d")
        reports = {"trend_report": TREND, "pattern_report": "Thiên lệch dự báo: Tăng",
                   "indicator_report": "Đồng thuận chủ đạo: Hỗn hợp"}
        upstream = Mock()
        upstream.invoke.return_value = reports

        def alpha(state):
            """Dùng snapshot tin thật, chỉ giả lập năm factor và báo cáo Alpha."""
            data, text = state["sentiment_store"].get_sentiment_at("FPT", cutoff, None)
            data["alpha_results"] = [{"id": index, "signal": "TĂNG"} for index in range(1, 6)]
            return {"sentiment_data": data, "sentiment_report": text, "alpha_report": "Alpha thử nghiệm"}

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            extractor = HistoricalSignalExtractor(upstream, alpha, output, DEFAULT_CONFIG,
                execution_loader=lambda symbol: (frame, events), article_loader=lambda symbol: [])
            with patch("utils.static_util.generate_kline_image", return_value={}), \
                    patch("utils.static_util.generate_trend_image", return_value={}):
                with self.assertRaises(ValueError):
                    extractor.extract("FPT", cutoff)
            checkpoint = output / f"FPT-{cutoff}.json"
            self.assertEqual(read_json(checkpoint)["payload"]["stage"], "UPSTREAM_COMPLETE")
            signature = read_json(checkpoint)["payload"]["signature"]
            with patch("core.historical_signals.report_signal", make_compatible_report_parser(output)):
                result = extractor.extract("FPT", cutoff)
            self.assertEqual(upstream.invoke.call_count, 1)
            self.assertEqual(result["reports"]["trend_report"], TREND)
            self.assertEqual(result["agent_signals"]["trend"], "BULLISH")
            self.assertEqual(read_json(checkpoint)["payload"]["signature"], signature)


if __name__ == "__main__":
    unittest.main()
