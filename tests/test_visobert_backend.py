import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agents.sentiment_agent as sentiment_agent


class ViSoBERTBackendTests(unittest.TestCase):
    def setUp(self):
        sentiment_agent._hf_ok = False
        sentiment_agent._hf_backend_used = ""
        sentiment_agent._hf_last_error = ""
        sentiment_agent._hf_warned = False
        sentiment_agent._local_pipeline = None
        sentiment_agent._local_pipeline_error = ""

    def test_auto_uses_local_model_when_endpoint_is_not_configured(self):
        environment = {
            "VISOBERT_BACKEND": "auto",
            "HF_INFERENCE_ENDPOINT_URL": "",
        }
        expected = [{"label": "POS", "score": 0.9}]
        with patch.dict(os.environ, environment, clear=False):
            with patch.object(
                sentiment_agent, "_predict_local", return_value=expected
            ) as local_predict:
                with patch.object(sentiment_agent, "_predict_endpoint") as endpoint_predict:
                    actual = sentiment_agent._predict("Doanh nghiệp tăng trưởng tốt")

        self.assertEqual(actual, expected)
        local_predict.assert_called_once()
        endpoint_predict.assert_not_called()

    def test_endpoint_posts_to_configured_dedicated_url(self):
        endpoint_url = "https://example.endpoints.huggingface.cloud"
        response = Mock(status_code=200)
        response.json.return_value = [[
            {"label": "NEG", "score": 0.1},
            {"label": "POS", "score": 0.8},
            {"label": "NEU", "score": 0.1},
        ]]
        environment = {
            "VISOBERT_BACKEND": "endpoint",
            "HF_INFERENCE_ENDPOINT_URL": endpoint_url,
            "HF_TOKEN": "test-token",
        }

        with patch.dict(os.environ, environment, clear=False):
            with patch.object(
                sentiment_agent.requests, "post", return_value=response
            ) as post:
                result = sentiment_agent._predict("Kết quả kinh doanh tích cực")

        self.assertEqual(result, [{"label": "POS", "score": 0.8}])
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args[0], endpoint_url)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-token")
        self.assertNotIn("router.huggingface.co", args[0])
        self.assertIn("inputs", kwargs["json"])

    def test_official_label_mapping_is_used(self):
        cases = {
            "NEG": "negative",
            "LABEL_0": "negative",
            "POS": "positive",
            "LABEL_1": "positive",
            "NEU": "neutral",
            "LABEL_2": "neutral",
        }
        sentiment_agent._hf_backend_used = "test-backend"
        for raw_label, expected_label in cases.items():
            with self.subTest(raw_label=raw_label):
                with patch.object(
                    sentiment_agent,
                    "_predict",
                    return_value=[{"label": raw_label, "score": 0.9}],
                ):
                    result = sentiment_agent._score_text("Nội dung kiểm thử")
                self.assertEqual(result["label"], expected_label)
                self.assertEqual(result["scorer"], sentiment_agent._HF_MODEL)
                self.assertFalse(result["is_fallback"])

    def test_lexicon_fallback_has_explicit_provenance(self):
        with patch.dict(
            os.environ, {"VISOBERT_BACKEND": "lexicon"}, clear=False
        ):
            result = sentiment_agent._score_text("Lợi nhuận tăng mạnh và tích cực")

        self.assertEqual(result["label"], "positive")
        self.assertEqual(result["scorer"], "viquant-lexicon-v1")
        self.assertEqual(result["scorer_backend"], "lexicon")
        self.assertTrue(result["is_fallback"])


if __name__ == "__main__":
    unittest.main()
