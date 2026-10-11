"""Request/prompt chỉ dùng query đã seal và chu kỳ đóng trước cutoff."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from core.historical_signals import digest
from core.prior_prompt import build_prior_request
from prior_price_similarity_support import PriceSimilarityFixture
from test_prior_quality_gate import gate_query
from test_prior_prompt_contract import FixtureLlm, decision_result, request_state, invoke_request


class PriorPromptLeakageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = PriceSimilarityFixture()
        self.addCleanup(self.fx.close)
        self.query = gate_query(self.fx)
        self.evidence = self.fx.retriever.quality_evidence(**self.query)

    def request(self, evidence: dict | None = None, query: dict | None = None) -> dict:
        query = query or self.query
        return build_prior_request(self.evidence if evidence is None else evidence, "C3", self.fx.retriever,
            selector=query["selector"], query_features=query["query_features"])

    def test_query_outcome_or_alias_never_reaches_llm_even_when_prior_off(self) -> None:
        request = self.request()
        for field in ("outcome", "net_return_pct", "actual_direction", "entry_date", "exit_date", "entry_open", "exit_close", "net_return"):
            llm = FixtureLlm(decision_result(request))
            state = {**request_state(request), field: "QUERY_LABEL_SECRET"}
            with self.assertRaises(ValueError):
                invoke_request(request, state, llm)
            self.assertEqual(llm.prompts, [])

    def test_changed_query_and_prefix_binding_fail_before_llm(self) -> None:
        request = self.request()
        for changed in ({"as_of_date": "2022-01-07"}, {"stock_name": "VCB"},
                        {"current_signals": {**request["query"]["current_signals"], "trend": "BEARISH"}}):
            llm = FixtureLlm(decision_result(request))
            with self.assertRaises(ValueError):
                invoke_request(request, {**request_state(request), **changed}, llm)
            self.assertEqual(llm.prompts, [])

    def test_rehashed_future_task_or_counts_are_rejected_by_source_builder(self) -> None:
        for mutate in (lambda e:e["selection"]["regime_population"].append(deepcopy(self.fx.records[-1])),
                       lambda e:e["statistics"]["metrics"]["win_rate_long"].update(posterior_mean=.99)):
            changed = deepcopy(self.evidence)
            mutate(changed)
            changed["base_evidence_sha256"] = digest({k:v for k,v in changed.items() if k != "base_evidence_sha256"})
            with self.assertRaises(ValueError):
                self.request(changed)

    def test_future_then_past_does_not_change_request_or_read_future_outcomes(self) -> None:
        query = gate_query(self.fx, cutoff="2021-01-04")
        evidence = self.fx.retriever.quality_evidence(**query)
        before = self.request(evidence, query)
        self.request()
        class ForbiddenOutcome(dict):
            """Bẫy RAM, không sửa bank/artifact đóng băng."""
            def __getitem__(self, key):
                raise AssertionError("Không đọc outcome tương lai")
        for source in (self.fx.retriever._memory._records, self.fx.retriever._verified_by_id.values()):
            for row in source:
                if row["exit_date"] >= query["as_of_date"]:
                    row["outcome"] = ForbiddenOutcome()
        with patch.object(self.fx.retriever, "retrieve", side_effect=AssertionError("Không chạy lại nhánh v1")):
            self.assertEqual(self.request(evidence, query), before)
