"""Kiểm màu thân nến/legend và prompt version từ renderer thật, không gọi model."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.audit_chart_convention import POLICY, audit_prompt, fixture_frame, image_parts, render, text_parts


class ChartConventionTests(unittest.TestCase):
    """Fixture có gap và doji phân biệt màu body với biến động so giá tham chiếu."""

    @classmethod
    def setUpClass(cls) -> None:
        """Render mỗi đường một lần; các assertions dùng lại cùng artifact thực."""
        data = fixture_frame().to_dict("list")
        cls.renders = {(prototype, kind): render(data, kind, prototype)
                       for prototype in (False, True) for kind in ("pattern", "trend")}

    def test_candle_body_prices_and_colors_match_ohlcv(self) -> None:
        for (prototype, kind), (_, meta) in self.renders.items():
            with self.subTest(prototype=prototype, kind=kind):
                self.assertTrue(meta["body_geometry_and_colors_match"])
                self.assertEqual(meta["n_candles"], 40 if prototype and kind == "pattern" else 45)

    def test_gap_fixture_separates_body_direction_from_previous_close(self) -> None:
        data = fixture_frame()
        mismatched = (data.Close.diff() * (data.Close - data.Open) < 0).sum()
        self.assertGreater(int(mismatched), 30)

    def test_doji_is_explicit_without_a_bearish_forecast_claim(self) -> None:
        for kind in ("pattern", "trend"):
            meta = self.renders[(False, kind)][1]
            self.assertEqual((meta["n_up"], meta["n_down"], meta["n_doji"]), (22, 22, 1))

    def test_support_resistance_labels_and_line_colors(self) -> None:
        for prototype in (False, True):
            meta = self.renders[(prototype, "trend")][1]
            self.assertEqual(set(meta["line_colors"].values()), {"#0000ff", "#ff0000"})
            self.assertEqual(len(meta["legend"]), 2)
            self.assertEqual(meta["legend_handle_colors"], ["#0000ff", "#ff0000"])
            self.assertTrue(meta["legend_handles_match_lines"])

    def test_decoded_png_contains_both_composited_body_colors(self) -> None:
        for _, meta in self.renders.values():
            self.assertTrue(all(n > 0 for n in meta["palette_pixel_counts"].values()))
            self.assertEqual(meta["body_alpha"], .9)

    def test_prompt_version_changes_only_english_color_literals(self) -> None:
        result, _ = audit_prompt(json.loads(POLICY.read_bytes()))
        self.assertTrue(result["vi_messages_unchanged"])
        self.assertTrue(result["comparison_holds_image_fixed"])
        self.assertTrue(result["en_only_two_color_literals_changed"])
        self.assertNotEqual(result["old_en_sha256"], result["new_en_sha256"])
        self.assertEqual(result["n_new_api_calls"], 0)

    def test_request_image_extraction_preserves_actual_bytes(self) -> None:
        raw = self.renders[(False, "pattern")][0]
        value = [{"data": {"content": [{"type": "text", "text": "fixture"},
                  {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(raw).decode()}}]}}]
        self.assertEqual(image_parts(value), [raw])
        self.assertEqual(text_parts(value), ["fixture"])
        with self.assertRaises(ValueError):
            image_parts({"type": "image_url", "image_url": {"url": "https://invalid.example/chart.png"}})


if __name__ == "__main__":
    unittest.main()
