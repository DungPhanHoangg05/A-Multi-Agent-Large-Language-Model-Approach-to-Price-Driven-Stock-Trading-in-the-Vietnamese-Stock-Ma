"""Kiểm scorer recipe thật bằng mocks và prompt missing, không inference/API thật."""

from __future__ import annotations

from copy import deepcopy
import inspect
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import torch
from tokenizers import Tokenizer, models, pre_tokenizers, processors
from core.revision_audit import sha256_file
from core.revision72_data import CARD_URL, REVISION, score_local
from core.revision72_run import checked, signed, variant_state
from core.revision_common_study import FrozenSentiment, digest, write_json
from core.revision_r4_factorial import prompt_parts
from core.revision_sentiment_contract import (
    MAPPING, audit_prompts, inspect_prompt, recipe_contract, tokenizer_contract, validate_scores, verify_snapshot,
)
from core.revision_sentiment_inventory import BANK
from scripts.prepare_chart_r4 import native_prompt

ROOT = Path(__file__).resolve().parents[1]


class ScorerRecipeTests(unittest.TestCase):
    """Chạy chính score_local với fake transport/model; tokenizer tự chứa trong fixture."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.snapshot = self.root / f".cache/huggingface/hub/models--5CD-AI--Vietnamese-Sentiment-visobert/snapshots/{REVISION}"
        self.snapshot.mkdir(parents=True)
        tokenizer = Tokenizer(models.WordLevel({"<s>": 0, "<pad>": 1, "</s>": 2, "<unk>": 3, "<mask>": 4,
                                               "tin": 5, "tốt": 6, "xấu": 7, "trung": 8, "tính": 9}, unk_token="<unk>"))
        tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
        tokenizer.post_processor = processors.TemplateProcessing(single="<s> $A </s>", special_tokens=[("<s>", 0), ("</s>", 2)])
        tokenizer.save(str(self.snapshot / "tokenizer.json"))
        write_json(self.snapshot / "config.json", {"id2label": MAPPING})
        write_json(self.snapshot / "tokenizer_config.json", {"model_max_length": 256, "truncation_side": "right"})
        (self.snapshot / "model.safetensors").write_bytes(b"mock weights; never loaded")
        (self.snapshot / "sentencepiece.bpe.model").write_bytes(b"fixture tokenizer auxiliary file")
        write_json(self.snapshot / "special_tokens_map.json", {"bos_token": "<s>", "eos_token": "</s>"})
        texts = ["tin tốt", "tin xấu", "trung tính", "tin tốt " * 600]
        self.audit = {"articles": [{"article_id": str(i), "text": text, "eligible_source": True} for i, text in enumerate(texts)]}
        self.forward_inputs = []
        self.logits = torch.tensor([[0., 3., -1.], [3., 0., -1.], [0., -1., 3.], [1., 1., 0.]])
        instance = self

        class FakeModel:
            """Không nạp weights, không truy cập network; chỉ logits cố định cho mapping."""

            def eval(self) -> FakeModel:
                """Interface giống model thật trong score_local."""
                return self

            def __call__(self, **inputs: object) -> SimpleNamespace:
                """Ghi keys/token cap thật đã đến model sau preprocessing."""
                instance.forward_inputs.append(inputs)
                return SimpleNamespace(logits=instance.logits)

        self.output = self.root / "native_output"; self.output.mkdir()
        old_threads = torch.get_num_threads(); self.addCleanup(torch.set_num_threads, old_threads)
        with patch("core.revision72_data.Path.home", return_value=self.root), \
             patch("requests.get", return_value=SimpleNamespace(text="0 -> Negative\n1 -> Positive\n2 -> Neutral", raise_for_status=lambda: None)) as request, \
             patch("transformers.AutoModelForSequenceClassification.from_pretrained", return_value=FakeModel()) as factory, \
             patch.object(socket.socket, "connect", side_effect=AssertionError("Cấm network")):
            self.scores = score_local(self.audit, self.output)
        request.assert_called_once_with(CARD_URL, timeout=30)
        self.assertTrue(factory.call_args.kwargs["local_files_only"])

    def test_actual_score_local_mapping_formula_and_first_index_tie(self) -> None:
        rows = validate_scores(self.scores, self.audit)
        self.assertEqual([r["label"] for r in rows], ["POS", "NEG", "NEU", "NEG"])
        self.assertGreater(rows[0]["numeric_score"], 0)
        self.assertLess(rows[1]["numeric_score"], 0)
        self.assertEqual(rows[3]["numeric_score"], 0)
        self.assertEqual(recipe_contract()["max_length"], 256)

    def test_actual_scorer_forward_keys_padding_and_cap(self) -> None:
        self.assertEqual(len(self.forward_inputs), 1)
        inputs = self.forward_inputs[0]
        self.assertNotIn("token_type_ids", inputs)
        self.assertEqual(tuple(inputs["input_ids"].shape), (4, 256))
        self.assertEqual(int(inputs["attention_mask"][0].sum()), 4)
        self.assertEqual(int(inputs["attention_mask"][3].sum()), 256)
        self.assertEqual(inputs["input_ids"][3][0].item(), 0)
        self.assertEqual(inputs["input_ids"][3][-1].item(), 2)

    def test_tokenizer_recipe_checks_short_and_long_inputs(self) -> None:
        contract, rows = tokenizer_contract(self.snapshot, self.audit, self.scores)
        self.assertEqual(contract["truncation_side"], "right")
        self.assertEqual(contract["long_fixture_tokens_after"], 256)
        self.assertEqual(contract["truncated_excerpts"], 1)
        self.assertEqual(rows[3]["effective_tokens"], 256)
        self.assertFalse(contract["model_forward_executed"])

    def test_probabilities_wrong_sign_labels_and_mapping_fail_closed(self) -> None:
        for change in ("score", "label", "probabilities", "mapping"):
            scores = deepcopy(self.scores)
            if change == "score": scores["scores"]["0"]["numeric_score"] *= -1
            if change == "label": scores["scores"]["0"]["label"] = "NEG"
            if change == "probabilities": scores["scores"]["0"]["probabilities"] = [0.8, 0.8, 0.8]
            if change == "mapping": scores["mapping"] = {"0": "POS", "1": "NEG", "2": "NEU"}
            with self.subTest(change=change), self.assertRaises(ValueError): validate_scores(scores, self.audit)

    def test_snapshot_hash_or_mapping_mismatch_is_rejected(self) -> None:
        self.assertEqual(len(verify_snapshot(self.snapshot, self.scores)), 6)
        (self.snapshot / "tokenizer.json").write_bytes(b"tampered tokenizer")
        with self.assertRaisesRegex(ValueError, "Snapshot sai hash"):
            verify_snapshot(self.snapshot, self.scores)

    def test_changed_recipe_truncation_or_local_only_is_rejected(self) -> None:
        source = inspect.getsource(score_local)
        for old, new in (("max_length=256", "max_length=128"), ("local_files_only=True", "local_files_only=False")):
            with self.subTest(parameter=old), patch("core.revision_sentiment_contract.inspect.getsource", return_value=source.replace(old, new)), self.assertRaises(ValueError):
                recipe_contract()


class SentimentPromptTests(unittest.TestCase):
    """Missing-news S không trở thành sentiment information effect hoặc neutral thật."""

    def setUp(self) -> None:
        self.shared = {"stock_name": "FPT", "time_frame": "1 ngày", "language": "vi", "is_backtest": True,
                       "indicator_report": "Chỉ báo fixture", "pattern_report": "Pattern fixture", "trend_report": "Trend fixture"}
        self.asset = checked(next((ROOT / BANK / "features").glob("*.json")))
        data, report = FrozenSentiment({"FPT": []}).get_sentiment_at("FPT", "2026-01-03")
        self.asset["sentiment_data"], self.asset["sentiment_report"] = data, report
        self.asset["sentiment_norm"] = {"is_reliable": False, "raw_avg_score": 0.0}

    def prompt(self, variant: str) -> str:
        """Native builder dừng trước invoke, không tạo prediction giả."""
        return native_prompt(variant_state(self.shared, self.asset, self.asset, variant))

    def test_missing_s_keeps_marker_and_is_not_sentiment_information(self) -> None:
        prompt = self.prompt("S")
        result = inspect_prompt(prompt, self.asset, "S", False)
        self.assertTrue(result["has_sentiment_section"])
        self.assertFalse(result["sentiment_information_available"])
        self.assertIn("KHÔNG KHẢ DỤNG", result["sentiment_block"])
        self.assertNotIn("score=", result["sentiment_block"])
        self.assertNotIn("alpha", prompt_parts(prompt))

    def test_missing_as_and_baseline_are_not_scorer_evidence(self) -> None:
        for variant in ("AS", "B"):
            result = inspect_prompt(self.prompt(variant), self.asset, variant, False)
            self.assertFalse(result["sentiment_information_available"])
        self.assertFalse(inspect_prompt(self.prompt("B"), self.asset, "B", False)["has_sentiment_section"])

    def test_three_articles_available_even_when_normalizer_eight_flag_false(self) -> None:
        news = [{"date_parsed": "2026-01-01", "numeric_score": 0.2, "scorer": "visobert"}] * 3
        data, report = FrozenSentiment({"FPT": news}).get_sentiment_at("FPT", "2026-01-03")
        self.asset["sentiment_data"], self.asset["sentiment_report"] = data, report
        result = inspect_prompt(self.prompt("S"), self.asset, "S", False)
        self.assertTrue(result["sentiment_information_available"])
        self.assertFalse(result["normalizer_is_reliable"])

    def test_replacing_missing_marker_with_neutral_or_score_is_rejected(self) -> None:
        prompt = self.prompt("S")
        bad = prompt.replace(self.asset["sentiment_report"], "Sentiment = neutral (0.0); score=0.0")
        with self.assertRaisesRegex(ValueError, "khác asset"):
            inspect_prompt(bad, self.asset, "S", False)

    def test_real_cap_preserves_missing_marker_and_budget(self) -> None:
        self.asset["sentiment_report"] = "Sentiment KHÔNG KHẢ DỤNG. " + "Thông tin fixture. " * 150 + "không coi là trung tính"
        result = inspect_prompt(self.prompt("S"), self.asset, "S", False)
        self.assertLessEqual(len(result["sentiment_block"]), 600)
        self.assertLess(result["prompt_chars"], 6500)
        self.assertFalse(result["sentiment_information_available"])

    def test_completed_raw_only_snapshot_ignores_partial_and_checks_actual_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unit = {"id": "FPT_fixture", "symbol": "FPT", "decision": 1, "placebo_donor": 0}
            # Tạo signed asset mới từ dữ liệu fixture, không sửa cache/bank repo.
            value = {k: v for k, v in self.asset.items() if k != "sha256"}; asset = signed(value)
            write_json(root / BANK / "features/FPT_1.json", asset)
            write_json(root / BANK / "features/FPT_0.json", signed({"fixture": True}))
            hashes = []
            for name, field in (("Indicator", "indicator_report"), ("Pattern", "pattern_report"), ("Trend", "trend_report")):
                node = signed({"parent": {"asset_hash": asset["sha256"]}, "context": {"unit_id": unit["id"]}, "state": {field: self.shared[field]}})
                hashes.append(node["sha256"])
                write_json(root / f"outputs/revision/chart_r1_run_v1/shards/org1/nodes/{unit['id']}_r0_{name}.json", node)
            prompt = self.prompt("AS")
            request_path = root / "outputs/revision/revision_minimal_v1/shards/org1/calls/fake.request.json"
            request = {"messages": [[{"type": "human", "data": {"content": prompt}}]]}
            write_json(request_path, signed(request))
            record_path = request_path.parent.parent / "decisions/fixture.json"
            write_json(record_path, signed({"request_ids": ["fake"], "call_hashes": [{"path": "calls/fake.request.json", "sha256": sha256_file(request_path)}]}))
            (request_path.parent / "inflight.response.json").write_bytes(b"partial unfinished file")
            manifest = {"jobs": [{"id": "fixture", "unit": unit, "phase": "main", "context": {"variant": "AS", "realization": 0, "repeat": 0},
                                   "prompt": prompt, "origin_org": 1, "origin_parent": {"node_hashes": hashes}}]}
            completed = [{"job_id": "fixture", "path": record_path.relative_to(root).as_posix()}]
            coverage = {"release_cutoffs": [{"id": unit["id"], "coverage": {"sentiment_missing": True}}]}
            with patch("core.revision_sentiment_contract.collect", return_value=completed):
                evidence, summary, _ = audit_prompts(root, manifest, coverage)
            self.assertEqual(summary["actual_raw_requests_checked"], 1)
            self.assertEqual(summary["missing_cutoff_native_S_diagnostics"], 1)
            self.assertFalse(evidence["derived_S_missing_news"][0]["sentiment_information_available"])
            request["messages"][0][0]["data"]["content"] += " changed"
            write_json(request_path, signed(request))
            with patch("core.revision_sentiment_contract.collect", return_value=completed), self.assertRaisesRegex(ValueError, "Raw actual message"):
                audit_prompts(root, manifest, coverage)


if __name__ == "__main__":
    unittest.main()
