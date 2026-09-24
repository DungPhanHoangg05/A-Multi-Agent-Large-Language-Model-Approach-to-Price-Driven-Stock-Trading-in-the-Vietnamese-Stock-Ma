import importlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.alpha_agent import _extract_tech_vars
from utils.json_util import to_json_compatible


class WebJsonSerializationTests(unittest.TestCase):
    def test_alpha_volume_flag_is_native_bool(self):
        kline_data = {
            "Open": np.linspace(90.0, 119.0, 30),
            "High": np.linspace(91.0, 120.0, 30),
            "Low": np.linspace(89.0, 118.0, 30),
            "Close": np.linspace(90.5, 119.5, 30),
            "Volume": np.arange(1, 31, dtype=np.int64) * 1_000,
        }

        tech_vars = _extract_tech_vars(kline_data)

        self.assertIs(type(tech_vars["has_volume"]), bool)
        json.dumps({"sentiment_data": {"tech_vars": tech_vars}}, allow_nan=False)

    def test_nested_numpy_and_pandas_values_become_strict_json(self):
        payload = {
            "flag": np.bool_(True),
            "count": np.int64(7),
            "score": np.float64(1.25),
            "missing": np.float64(np.nan),
            "timestamp": pd.Timestamp("2026-09-21 09:30:36"),
            "values": np.array([np.int64(1), np.int64(2)]),
        }

        converted = to_json_compatible(payload)

        self.assertIs(type(converted["flag"]), bool)
        self.assertIs(type(converted["count"]), int)
        self.assertIs(type(converted["score"]), float)
        self.assertIsNone(converted["missing"])
        self.assertEqual(converted["timestamp"], "2026-09-21T09:30:36")
        self.assertEqual(converted["values"], [1, 2])
        json.dumps(converted, allow_nan=False)

    def test_analysis_status_returns_numpy_payload_without_500(self):
        with patch("core.realtime_loader.get_all_symbols_realtime", return_value=[]):
            web_interface = importlib.import_module("web_interface")

        job_id = "json-regression"
        with web_interface._jobs_lock:
            web_interface._jobs[job_id] = {
                "status": "done",
                "step": np.int64(6),
                "result": {
                    "success": np.bool_(True),
                    "sentiment_data": {
                        "tech_vars": {"has_volume": np.bool_(True)}
                    },
                },
                "ts": 0.0,
            }

        try:
            response = web_interface.app.test_client().get(
                f"/api/analyze/status/{job_id}"
            )
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertIs(data["result"]["success"], True)
            self.assertIs(
                data["result"]["sentiment_data"]["tech_vars"]["has_volume"],
                True,
            )
        finally:
            with web_interface._jobs_lock:
                web_interface._jobs.pop(job_id, None)


if __name__ == "__main__":
    unittest.main()
