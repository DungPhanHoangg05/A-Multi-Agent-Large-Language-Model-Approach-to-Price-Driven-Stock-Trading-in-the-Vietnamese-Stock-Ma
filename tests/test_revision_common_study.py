"""Kiểm thử bank chung, trace API, ngân sách và chống resume sai repeat."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import sys
import tempfile
import time
import unittest
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.revision_call_archive import CallArchive, GuardedLLM, StudyLock, StudyStop, retry_after_seconds
from core.revision_common_study import (FrozenSentiment, digest, make_schedule, market_features,
    pack_state, point_state, read_json, restore_state, unit_key, verify_features, write_json)
from core.revision_common_study import run_full
from core.revision_audit import sha256_file
from core.revision_baselines import load_prices
from core.revision_common_analysis import checked_unit

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = read_json(ROOT / "revision/r1_common_protocol.json")


class CommonBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames, _ = load_prices(ROOT / PROTOCOL["price_snapshot"], PROTOCOL["price_quality_policy"])

    def test_three_folds_all_nine_symbols_purge_and_calibration_before_test(self):
        schedule = make_schedule(self.frames, PROTOCOL)
        self.assertEqual(len(schedule), 27)
        self.assertEqual(sum(len(s["test"]) for s in schedule), 540)
        self.assertEqual(sum(len(s["calibration"]) for s in schedule), 540)
        for item in schedule:
            self.assertLess(item["last_train_label_date"], item["first_validation_date"])
            self.assertLess(item["last_validation_label_date"], item["first_test_date"])
            self.assertTrue(set(item["calibration"]).issubset(item["train"]))
            self.assertTrue(all(i + 1 >= 600 for i in item["train"] + item["validation"] + item["test"]))

    def test_future_test_prices_do_not_select_schedule_or_calibration(self):
        original = make_schedule(self.frames, PROTOCOL)
        changed = {k: v.copy() for k, v in self.frames.items()}
        # Sau test_start của fold cuối, không được ảnh hưởng việc chọn lịch.
        for frame in changed.values():
            frame.loc[frame["date"] >= "2026-07-01", ["Open", "High", "Low", "Close"]] *= 15
        self.assertEqual(original, make_schedule(changed, PROTOCOL))

    def test_incomplete_test_horizon_or_insufficient_train_fail(self):
        changed = dict(self.frames)
        changed["BHN"] = changed["BHN"].iloc[-610:].reset_index(drop=True)
        with self.assertRaises(ValueError):
            make_schedule(changed, PROTOCOL)

    def test_feature_alpha_phase_never_calls_llm_and_matches_raw_window(self):
        from agents.alpha_agent import create_alpha_agent
        state = point_state(self.frames["BHN"], "BHN", 650, PROTOCOL, FrozenSentiment({}))
        self.assertEqual(len(state["point_in_time_df"]), 600)
        self.assertEqual(len(state["kline_data"]["Close"]), 45)
        self.assertNotIn("entry_open", state)
        self.assertNotIn("label", state)
        with redirect_stdout(io.StringIO()):
            alpha = create_alpha_agent(None, True, True)(state)
        features = market_features(state, alpha)
        self.assertEqual(features["price_Close_44"], state["kline_data"]["Close"][-1])
        self.assertEqual(sum(v for k, v in features.items() if k.endswith("_selected")), 5)
        self.assertEqual(features["sentiment_missing"], 1)
        packed = pack_state({**state, **alpha})
        restored = restore_state(packed, state)
        self.assertEqual(pack_state(restored), packed)

    def test_unknown_sentiment_is_not_used_as_verified_neutral(self):
        store = FrozenSentiment({"AAA": [{"date_parsed": "2026-01-01", "numeric_score": .5}] * 5})
        data, report = store.get_sentiment_at("AAA", "2026-01-20")
        self.assertTrue(data["is_unavailable"])
        self.assertIsNone(data["main_sentiment"]["avg_score"])
        self.assertIn("không coi là trung tính", report)

    def test_backtest_indicator_has_report_without_llm(self):
        from agents.indicator_agent import create_indicator_agent
        from utils.graph_util import TechnicalTools
        state = point_state(self.frames["FPT"], "FPT", 650, PROTOCOL, FrozenSentiment({}))
        with redirect_stdout(io.StringIO()):
            result = create_indicator_agent(None, TechnicalTools())(state)
        self.assertTrue(result["indicator_report"])
        self.assertEqual(result["messages"], [])

    def test_repeat_kind_and_fold_get_different_checkpoint_ids(self):
        values = {unit_key("AAA", "f1", 600, "test", "e2e", 0), unit_key("AAA", "f1", 600, "test", "e2e", 1),
                  unit_key("AAA", "f1", 600, "test", "decision", 1), unit_key("AAA", "f2", 600, "test", "e2e", 0)}
        self.assertEqual(len(values), 4)

    def test_feature_receipt_cannot_claim_a_partial_bank_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            bank = Path(temp)
            manifest = {"bank_id": "bank", "schedule": [{"symbol": "AAA", "train": [600], "validation": [610], "test": [620]}]}
            write_json(bank / "features_complete.json", {"bank_id": "bank", "n_points": 2, "files": []})
            with self.assertRaises(ValueError): verify_features(bank, manifest)


class CallArchiveTests(unittest.TestCase):
    def test_compound_retry_after_and_daily_quota_stop_before_fallback(self):
        for message, expected in (("Please try again in 18m10.368s.", 1090.368),
                ("retry after 1h2m3s", 3723), ("try again in 2 minutes 5 seconds.", 125),
                ("retry after 250ms", .25), ("retry after 120 seconds", 120)):
            self.assertAlmostEqual(retry_after_seconds(message), expected)
        self.assertIsNone(retry_after_seconds("không có thời gian retry"))
        with tempfile.TemporaryDirectory() as temp:
            handler = CallArchive(Path(temp), "bank", 2, "secret")
            handler.context = {"stage": "upstream"}
            key = uuid4()
            handler.on_chat_model_start({}, [[HumanMessage(content="fixture")]], run_id=key)
            error = RuntimeError("429 tokens per day (TPD): Limit 200000. Please try again in 18m10.368s.")
            before = time.monotonic()
            with self.assertRaisesRegex(StudyStop, "quota"):
                handler.on_llm_error(error, run_id=key)
            self.assertGreaterEqual(handler.not_before, before + 1090.368)
            self.assertEqual(handler.count, 1)
            self.assertFalse(handler.pending)
            self.assertTrue((Path(temp) / "calls" / f"{key}.error.json").exists())
            # Kiểm tra BaseException đi xuyên callback manager và retry proxy thật.
            handler.not_before = 0
            model = FakeListChatModel(responses=["không được dùng"], callbacks=[handler])
            with patch.object(FakeListChatModel, "_generate", side_effect=error):
                with self.assertRaises(StudyStop):
                    GuardedLLM(model).invoke("fixture")
            self.assertEqual(handler.count, 2)

    def test_real_callback_archives_raw_messages_and_response_without_secret(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            handler = CallArchive(path, "bank", 1, "gsk_secret")
            handler.context = {"stage": "decision"}
            model = FakeListChatModel(responses=['{"decision":"LONG","note":"gsk_secret"}'], callbacks=[handler])
            GuardedLLM(model).invoke([HumanMessage(content="gsk_secret")])
            self.assertEqual(handler.count, 1)
            self.assertEqual(len(list((path / "calls").glob("*.request.json"))), 1)
            self.assertEqual(len(list((path / "calls").glob("*.response.json"))), 1)
            self.assertFalse(any("gsk_secret" in p.read_text(encoding="utf8") for p in path.rglob("*.json")))

    def test_budget_stops_before_the_next_call_and_resume_counts_attempts(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            h = CallArchive(path, "bank", 1, "")
            h.context = {"stage": "decision"}
            model = FakeListChatModel(responses=["x"], callbacks=[h])
            model.invoke("first")
            with self.assertRaises(StudyStop): model.invoke("second")
            self.assertEqual(h.count, 1)
            resumed = CallArchive(path, "bank", 2, "")
            self.assertEqual(resumed.count, 1)
            resumed.context = {"stage": "decision"}
            FakeListChatModel(responses=["x"], callbacks=[resumed]).invoke("third")
            self.assertEqual(resumed.count, 2)
            with self.assertRaises(ValueError): CallArchive(path, "other_bank", 3, "")

    def test_6500_char_prompt_and_missing_context_are_stopped_before_network(self):
        with tempfile.TemporaryDirectory() as temp:
            h = CallArchive(Path(temp), "bank", 3, "")
            model = FakeListChatModel(responses=["x"], callbacks=[h])
            with self.assertRaises(StudyStop): model.invoke("not_contextualized")
            h.context = {"stage": "decision"}
            with self.assertRaises(StudyStop): model.invoke("x" * 6500)
            self.assertEqual(h.count, 0)

    def test_retry_after_120_seconds_is_not_capped_at_60(self):
        with tempfile.TemporaryDirectory() as temp:
            h = CallArchive(Path(temp), "bank", 3, "secret")
            h.context = {"stage": "upstream"}
            run_id = uuid4()
            h.on_chat_model_start({}, [[HumanMessage(content="ok")]], run_id=run_id)
            before = time.monotonic()
            h.on_llm_error(Exception("retry after 120 seconds secret"), run_id=run_id)
            self.assertGreaterEqual(h.not_before, before + 120)

    def test_langgraph_node_metadata_reaches_the_actual_model_callback(self):
        class State(TypedDict):
            content: str
        with tempfile.TemporaryDirectory() as temp:
            h = CallArchive(Path(temp), "bank", 2, "")
            h.context = {"stage": "upstream"}
            model = FakeListChatModel(responses=["x"], callbacks=[h])
            graph = StateGraph(State)
            graph.add_node("Pattern Agent", lambda s: {"content": model.invoke(s["content"]).content})
            graph.add_edge(START, "Pattern Agent")
            graph.add_edge("Pattern Agent", END)
            graph.compile().invoke({"content": "test"})
            request = read_json(next((Path(temp) / "calls").glob("*.request.json")))
            self.assertEqual(request["model_metadata"]["langgraph_node"], "Pattern Agent")

    def test_second_process_style_lock_is_exclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            with StudyLock(Path(temp) / "run.lock"):
                with self.assertRaises(RuntimeError):
                    with StudyLock(Path(temp) / "run.lock"):
                        pass

    def test_exclusive_artifact_write_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "unit.json"
            write_json(path, {"x": 1}, exclusive=True)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError): write_json(path, {"x": 2}, exclusive=True)
            self.assertEqual(path.read_bytes(), before)


class FullRunnerIntegrationTests(unittest.TestCase):
    def test_budget_stop_resume_shared_reports_and_raw_prediction_replay(self):
        """LLM giả chỉ ở temp fixture; không xuất hoặc gọi đây là kết quả thực nghiệm."""
        frames, _ = load_prices(ROOT / PROTOCOL["price_snapshot"], PROTOCOL["price_quality_policy"])
        protocol = {**PROTOCOL, "end_to_end_repeats": 2, "decision_only_repeats": 2}
        schedule = {"symbol": "FPT", "fold": "fixture", "train": [600], "validation": [603],
                    "calibration": [600], "test": [610]}
        manifest = {"bank_id": "fixture_bank", "protocol": protocol, "schedule": [schedule], "n_calibration": 1, "n_test": 1}

        class FakeUpstream:
            def __init__(self, text, vision):
                self.text, self.vision = text, vision

            def invoke(self, state):
                result = dict(state)
                result["indicator_report"] = "Báo cáo Python xác định của fixture"
                for name, key, model in (("Pattern Agent", "pattern_report", self.vision), ("Trend Agent", "trend_report", self.vision)):
                    response = model.invoke("fixture", config={"metadata": {"langgraph_node": name}})
                    result[key] = "Báo cáo fixture kiểm thử"
                    result["messages"] = result.get("messages", []) + [response]
                return result

        def chat_factory(**kwargs):
            return FakeListChatModel(responses=['{"decision":"LONG","confidence":"Cao","risk_reward_ratio":1.5}'],
                                     callbacks=kwargs["callbacks"])

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bank, run = root / "bank", root / "run"
            write_json(bank / "news.json", {})
            files = []
            for index in (600, 603, 610):
                state = point_state(frames["FPT"], "FPT", index, protocol, FrozenSentiment({}))
                feature = {"bank_id": "fixture_bank", "features": {}, "market_input_hash": digest(state["kline_data"]),
                    "alpha_state": {"alpha_report": "Alpha fixture", "messages": []}}
                feature["sha256"] = digest(feature)
                path = bank / "features" / f"FPT_{index}.json"
                write_json(path, feature)
                files.append({"path": path.relative_to(bank).as_posix(), "sha256": sha256_file(path)})
            write_json(bank / "features_complete.json", {"bank_id": "fixture_bank", "n_points": 3, "files": files})
            catalog = SimpleNamespace(models=SimpleNamespace(list=lambda: SimpleNamespace(data=[
                SimpleNamespace(id=protocol["agent_llm_model"]), SimpleNamespace(id=protocol["graph_llm_model"])])))
            with (patch("core.revision_common_study.verify_bank", return_value=manifest),
                  patch("core.revision_common_study.load_prices", return_value=(frames, {})),
                  patch("groq.Groq", return_value=catalog),
                  patch("langchain_groq.ChatGroq", side_effect=chat_factory) as model_factory,
                  patch("utils.graph_setup.SetGraph", side_effect=lambda t, v, k: SimpleNamespace(compile_upstream=lambda: FakeUpstream(t, v))),
                  patch("utils.static_util.generate_kline_image", return_value={"pattern_image": "fixture_image"}),
                  patch("utils.static_util.generate_trend_image", return_value={"trend_image": "fixture_image"}),
                  patch.dict("os.environ", {"GROQ_API_KEY": "gsk_fixture"}), redirect_stdout(io.StringIO())):
                with self.assertRaises(StudyStop): run_full(root, bank, run, 5)
                calibration_key = unit_key("FPT", "fixture", 600, "calibration", "e2e", 0)
                self.assertTrue((run / "units" / f"{calibration_key}.json").exists())
                run_full(root, bank, run, 20)
                complete = read_json(run / "inference_complete.json")
                self.assertEqual(complete["n_decisions"], 4)
                self.assertEqual(complete["attempted_requests"], 10)
                count = model_factory.call_count
                run_full(root, bank, run, 20)
                self.assertEqual(model_factory.call_count, count)
            key = unit_key("FPT", "fixture", 610, "test", "decision", 1)
            unit = checked_unit(run, key, complete["run_signature"], bank)
            self.assertEqual(unit["prediction"], "LONG")
            # Tự đổi prediction và tính lại self-hash vẫn phải bị replay raw bác bỏ.
            forged = deepcopy(unit)
            forged["prediction"] = "SHORT"
            forged["sha256"] = digest({k: v for k, v in forged.items() if k != "sha256"})
            write_json(run / "units" / f"{key}.json", forged)
            with self.assertRaisesRegex(ValueError, "raw response"):
                checked_unit(run, key, complete["run_signature"], bank)


if __name__ == "__main__":
    unittest.main()
