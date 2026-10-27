"""Future/self/target poison và purge cho đường payoff R2, không dùng benchmark thật."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd

from core.prior_backtest import canonical_hash
from tools import prepare_unified_bayes_r2_payoff as cli
from tools.unified_bayes_r2_payoff import PayoffEvidence, point_metrics

SIGNALS = {"trend":"BULLISH","pattern":"BULLISH","indicator_consensus":"NEUTRAL",
           "alpha_consensus":"BEARISH","sentiment":"NEUTRAL"}
QUERY = {"symbol":"FPT","as_of_date":"2021-01-04","current_regime":"CHOPPY","current_signals":SIGNALS}


def fixture() -> tuple[list[dict], dict[str, dict]]:
    """25 cycle lịch sử: năm C, mười B1 và mười B2; return đơn vị phần trăm trong bank."""
    metadata, records = [], {}
    for i in range(25):
        day=pd.Timestamp("2020-01-06")+pd.offsets.BDay(3*i)
        signals=deepcopy(SIGNALS)
        if 5 <= i < 15:signals["pattern"]="BEARISH"
        meta={"episode_id":f"FPT:{day:%Y-%m-%d}","symbol":"FPT","as_of_date":f"{day:%Y-%m-%d}",
              "entry_date":f"{day+pd.offsets.BDay(1):%Y-%m-%d}","exit_date":f"{day+pd.offsets.BDay(3):%Y-%m-%d}",
              "regime":"CHOPPY" if i < 15 else "BEAR","agent_signals":signals}
        metadata.append(meta);records[meta["episode_id"]]={**deepcopy(meta),"outcome":{"net_return_pct":1.}}
    return metadata,records


class PayoffLeakageTests(unittest.TestCase):
    """Giữ mô hình tách biệt query target, metadata future và nhãn không thuộc pool."""

    def setUp(self) -> None:
        self.metadata,self.records=fixture()

    def test_partition_is_disjoint_same_symbol_and_prior_return_percent_to_ratio_once(self) -> None:
        value=PayoffEvidence(self.metadata,self.records).evidence(**QUERY)
        ids=[i for group in value["groups"].values() for i in group]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(value["counts"],{"nC":5,"sC":5,"n1":10,"s1":10,"n2":10,"s2":10})
        self.assertAlmostEqual(value["prediction"]["posterior"]["mean"],.01)
        self.assertTrue(value["prediction"]["gate"]["ready"])

    def test_equal_exit_future_self_and_foreign_symbol_outcomes_are_never_opened(self) -> None:
        expected=PayoffEvidence(self.metadata,self.records).evidence(**QUERY)
        class Poison(dict):
            """Không cho đọc/copy bất kỳ trường nào của record bị loại."""
            def __getitem__(self,key: str) -> object:raise AssertionError("Đã đọc record không PIT")
            def __deepcopy__(self,memo: dict) -> object:raise AssertionError("Đã copy record không PIT")
        for symbol,cutoff,exit_day in (("FPT","2020-12-30","2021-01-04"),
                                       ("FPT","2021-01-04","2021-01-07"),
                                       ("FPT","2021-02-01","2021-02-04"),
                                       ("MWG","2020-01-06","2020-01-09")):
            meta={**deepcopy(self.metadata[0]),"episode_id":f"{symbol}:{cutoff}","symbol":symbol,
                  "as_of_date":cutoff,"exit_date":exit_day}
            self.metadata.append(meta);self.records[meta["episode_id"]]=Poison()
        self.assertEqual(PayoffEvidence(self.metadata,self.records).evidence(**QUERY),expected)

    def test_tampered_record_metadata_is_rejected_before_outcome(self) -> None:
        identifier=self.metadata[0]["episode_id"]
        self.records[identifier]["exit_date"]="2021-01-04"
        self.records[identifier]["outcome"]=None
        with self.assertRaisesRegex(ValueError,"PIT"):
            PayoffEvidence(self.metadata,self.records).evidence(**QUERY)

    def test_declared_partition_self_or_unknown_member_raises_value_error(self) -> None:
        meta={**deepcopy(self.metadata[0]),"episode_id":"FPT:2021-01-04","as_of_date":"2021-01-04","exit_date":"2021-01-07"}
        self.metadata.append(meta);self.records[meta["episode_id"]]={**meta,"outcome":None}
        engine=PayoffEvidence(self.metadata,self.records)
        for bad in (meta["episode_id"],"unknown"):
            with patch("tools.unified_bayes_r2_payoff.partition_records",return_value={"C":[bad],"B1":[],"B2":[],"excluded":[]}),self.assertRaises(ValueError):
                engine.evidence(**QUERY)

    def test_query_decision_confidence_or_outcome_features_are_rejected(self) -> None:
        engine=PayoffEvidence(self.metadata,self.records)
        for key in ("decision","confidence","justification"):
            with self.subTest(key=key),self.assertRaises(ValueError):
                engine.evidence(**(QUERY|{"current_signals":SIGNALS|{key:"forbidden"}}))

    def test_target_change_only_changes_scoring_after_prediction(self) -> None:
        engine=PayoffEvidence(self.metadata,self.records)
        value=engine.evidence(**QUERY)
        a=point_metrics(value["prediction"],.01);b=point_metrics(value["prediction"],-.1)
        self.assertNotEqual(a,b)
        self.assertEqual(engine.evidence(**QUERY),value)

    def test_no_feature_or_age_filter_is_applied_to_stats_payoff(self) -> None:
        engine=PayoffEvidence(self.metadata,self.records)
        early=engine.evidence(**QUERY)
        late=engine.evidence(**(QUERY|{"as_of_date":"2023-01-04"}))
        self.assertEqual(late["groups"],early["groups"])
        self.assertEqual(late["prediction"],early["prediction"])
        with patch("pathlib.Path.read_bytes",side_effect=AssertionError("I/O")),patch("pathlib.Path.read_text",side_effect=AssertionError("I/O")):
            engine.evidence(**QUERY)

    def test_duplicates_and_nonfinite_labels_are_integrity_errors(self) -> None:
        with self.assertRaises(ValueError):PayoffEvidence(self.metadata+[self.metadata[0]],self.records)
        self.records[self.metadata[0]["episode_id"]]["outcome"]["net_return_pct"]=float("nan")
        with self.assertRaises(ValueError):PayoffEvidence(self.metadata,self.records).evidence(**QUERY)

    def test_fold_purge_and_cycle_sessions_are_reconstructed(self) -> None:
        calendar=pd.bdate_range("2021-12-20","2022-01-10")
        metadata=[]
        for cutoff in ("2021-12-27","2021-12-30"):
            day=pd.Timestamp(cutoff)
            metadata.append({"episode_id":f"FPT:{cutoff}","as_of_date":cutoff,
                             "entry_date":f"{day+pd.offsets.BDay(1):%Y-%m-%d}","exit_date":f"{day+pd.offsets.BDay(3):%Y-%m-%d}"})
        kept=["FPT:2021-12-27"]
        spec={"offline_gate":{"query_count":1,"folds":[{"fold_id":"train_2021","query_start":"2021-12-20",
               "query_end":"2021-12-31","query_count_before_end_purge":2,"query_count":1,
               "query_ids_sha256":canonical_hash(kept),"purged_query_ids":["FPT:2021-12-30"]}]}}
        self.assertEqual(cli.query_schedule(metadata,calendar,spec),{kept[0]:"train_2021"})
        metadata[0]["exit_date"]="2021-12-31"
        with self.assertRaises(ValueError):cli.query_schedule(metadata,calendar,spec)

    def test_offline_guard_blocks_key_network_2025_and_development_actions(self) -> None:
        for event,args in (("socket.connect",()),("socket.getaddrinfo",()),
                           ("open",(str(cli.ROOT/".env"),)),
                           ("open",(str(cli.ROOT/"data/execution_prices_2025/FPT.csv"),)),
                           ("open",(str(cli.ROOT/"outputs/bayesian_benchmark/unified_bic_v1/development/run/report.json"),))):
            with self.subTest(event=event,args=args),self.assertRaises(ValueError):cli.offline_guard(event,args)
        cli.offline_guard("open",(str(cli.ROOT/"data/execution_prices_oos/FPT.csv"),))
        with self.assertRaises(ValueError):cli.source_guard({"../outside-workspace":"0"*64})


if __name__ == "__main__":
    unittest.main()
