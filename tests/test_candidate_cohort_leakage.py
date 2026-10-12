"""Ứng viên giữ PIT/index/fold và từ chối artifact future đã tự băm lại."""

from copy import deepcopy
import hashlib
import unittest

from core.candidate_cohort import prepare_candidate_plan
from core.prior_backtest import canonical_hash
from core.research_cohort import read_envelope, save_envelope, validate_plan
from test_candidate_cohort import CandidateSetup


class CandidateCohortLeakageTests(CandidateSetup, unittest.TestCase):
    def test_holdout_parent_or_shifted_calendar_never_reaches_llm(self) -> None:
        parent = read_envelope(self.parent)
        parent["split"] = "holdout_2024"
        save_envelope(self.parent, parent)
        with self.assertRaises(ValueError):
            prepare_candidate_plan(self.parent, self.fx.root / "future_plan.json", self.adapter, index_path="index.json")
        self.assertEqual(self.llm.calls, 0)

    def test_rehashed_scaler_future_fit_is_rejected_semantically(self) -> None:
        path = self.fx.root / "index.json"
        payload = read_envelope(path)
        payload["scalers"]["train_2022"]["FPT"]["fit_episode_ids"].append("FPT:2024-01-01")
        # Index dùng canonical JSON riêng; ghi lại hash đúng để kiểm semantic, không chỉ checksum.
        from core.price_feature_index import _json_bytes, _hash
        path.write_bytes(_json_bytes({"payload": payload, "sha256": _hash(payload)}) + b"\n")
        changed = deepcopy(self.plan)
        changed["price_index"].update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), identity=_hash(payload))
        with self.assertRaises(ValueError):
            validate_plan(changed, self.adapter)
        self.assertEqual(self.llm.calls, 0)

    def test_future_task_rehashed_in_evidence_cannot_resume_any_stock(self) -> None:
        self.runner.run_cohort(self.plan, output_dir=self.output, symbols=["FPT"])
        path, doc = self.checkpoint()
        evidence = doc["evidence"]
        future = deepcopy(self.fx.records[-1])
        future.update(episode_id="FPT:2024-01-01", as_of_date="2024-01-01", exit_date="2024-01-04")
        evidence["selection"]["regime_population"].append(future)
        evidence["base_evidence_sha256"] = canonical_hash({k:v for k,v in evidence.items() if k != "base_evidence_sha256"})
        save_envelope(path, doc)
        calls = self.llm.calls
        with self.assertRaises(ValueError):
            self.runner.run_cohort(self.plan, output_dir=self.output, resume=True, symbols=["MWG"])
        self.assertEqual(self.llm.calls, calls)

    def test_rehashed_fold_and_query_cutoff_do_not_rebind_sealed_plan(self) -> None:
        for mutate in (lambda p:p["symbol_cutoffs"]["FPT"].__setitem__(0, "2024-01-01"),
                       lambda p:p["price_index"].update(fold_id="oos_2023_2024")):
            changed = deepcopy(self.plan)
            mutate(changed)
            with self.assertRaises(ValueError):
                validate_plan(changed, self.adapter)
        self.assertEqual(self.llm.calls, 0)
