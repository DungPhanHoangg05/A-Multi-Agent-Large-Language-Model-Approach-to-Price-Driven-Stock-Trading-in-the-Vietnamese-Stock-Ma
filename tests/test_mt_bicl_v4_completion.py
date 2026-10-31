"""Kiểm amendment coverage/cache, warmup thô và giới hạn nguồn trước API."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from core.mt_bicl_v4_completion import DIRECTORY, cache_audit, corrected_coverage, normalized_agent_tree
from core.mt_bicl_v4_protocol import read
from core.mt_bicl_v4_warmup import combine_warmup, load_warmup


def warmup_fixture() -> tuple[list[dict], pd.DataFrame, dict]:
    """Giá thô synthetic có overlap thật với base; tuyệt đối không dùng cho dataset nghiên cứu."""
    pre = pd.bdate_range("2015-01-02", "2017-12-29")
    post = pd.bdate_range("2018-01-02", periods=90)
    days = pre.append(post)
    frame = pd.DataFrame({"Datetime": days, "Open": 100., "High": 101., "Low": 99.,
        "Close": 100., "Volume": 1000, "Reference": 100., "MatchPrice": 100.})
    base = frame.loc[frame["Datetime"] >= "2018-01-02"].reset_index(drop=True)
    records = []
    for row in frame.loc[frame["Datetime"] <= "2018-01-15"].to_dict("records"):
        records.append({"ticker": "FPT", "tradingDate": row["Datetime"].strftime("%Y-%m-%d"),
            "openPrice": row["Open"] * 1000, "highestPrice": row["High"] * 1000,
            "lowestPrice": row["Low"] * 1000, "closePrice": row["Close"] * 1000,
            "referencePrice": row["Reference"] * 1000, "matchPrice": row["MatchPrice"] * 1000,
            "totalMatchVolume": row["Volume"]})
    settings = {"start": "2015-01-01", "end": "2018-01-15", "append_only_before": "2018-01-02", "minimum_pre_anchor_rows": 579}
    return records, base, settings


class CompletionTests(unittest.TestCase):
    """Coverage agent không phụ thuộc numeric nhưng joint mask/fallback vẫn giữ."""

    def test_agent_coverage_independent_of_numeric_and_threshold_unchanged(self) -> None:
        root = Path('.')
        rows = read((root/'outputs/bayesian_benchmark/mt_bicl_v4/data/observations.json').read_bytes())['rows']
        folds = read((root/'outputs/bayesian_benchmark/mt_bicl_v4/data/folds.json').read_bytes())
        spec = read((root/'docs/plan/week11/protocol_v4.json').read_bytes())
        changed = deepcopy(rows)
        for row in changed:
            row['agent']['status'] = 'AVAILABLE'
        report = corrected_coverage(changed, folds, spec)
        self.assertTrue(report['ready_for_W11_19'])
        self.assertEqual(report['full_summary']['agent_valid_fraction'], 1.)
        self.assertLess(report['full_summary']['joint_full_input_fraction'], .7)
        self.assertEqual(spec['data']['minimum_support']['agent_valid_fraction_each_outer_symbol'], .7)
        self.assertEqual(corrected_coverage(rows, folds, spec)['full_summary']['agent_valid'], 0)

    def test_below_seventy_percent_agent_does_not_pass_even_with_numeric(self) -> None:
        root = Path('.')
        rows = read((root/'outputs/bayesian_benchmark/mt_bicl_v4/data/observations.json').read_bytes())['rows']
        folds = read((root/'outputs/bayesian_benchmark/mt_bicl_v4/data/folds.json').read_bytes())
        spec = read((root/'docs/plan/week11/protocol_v4.json').read_bytes())
        report = corrected_coverage(rows, folds, spec)
        self.assertFalse(report['ready_for_W11_19'])
        self.assertEqual(sum(x['check']=='eval_agent_fraction' for x in report['failed_checks']),12)

    def test_retry_only_AST_normalization_preserves_prompt_changes(self) -> None:
        old='def _invoke_with_retry(call_fn, *args):\n return call_fn(*args)\n'
        guarded='def _invoke_with_retry(call_fn, *args):\n from core.research_invocation import CURRENT, invoke_once\n if CURRENT.get() is not None:\n  return invoke_once(call_fn, *args)\n return call_fn(*args)\n'
        self.assertEqual(normalized_agent_tree(old),normalized_agent_tree(guarded))
        self.assertNotEqual(normalized_agent_tree(old+'PROMPT="a"\n'),normalized_agent_tree(guarded+'PROMPT="b"\n'))

    def test_real_legacy_prompt_audit_does_not_invent_HTTP_option_equivalence(self) -> None:
        result=cache_audit(Path('.').resolve())
        self.assertEqual(result['reports_prompt_AST_equivalent'],852)
        self.assertFalse(result['reuse_allowed'])
        self.assertIn('OPTIONS',result['reason'])

    def test_raw_warmup_appends_only_before_anchor_and_keeps_base_exact(self) -> None:
        records,base,settings=warmup_fixture()
        joined,proof=combine_warmup('FPT',records,base,settings)
        pd.testing.assert_frame_equal(joined.loc[joined['Datetime']>='2018-01-02'].reset_index(drop=True),base,check_dtype=False)
        self.assertGreaterEqual(proof['pre_anchor_rows'],579)
        self.assertFalse(proof['pre2018_labels_created'])

    def test_adjusted_or_wrong_overlap_is_rejected(self) -> None:
        records,base,settings=warmup_fixture()
        for row in records:
            for key in ('openPrice','highestPrice','lowestPrice','closePrice','referencePrice','matchPrice'):
                row[key]*=.5
        with self.assertRaises(ValueError): combine_warmup('FPT',records,base,settings)

    def test_insufficient_pre_anchor_or_absent_overlap_is_rejected(self) -> None:
        records,base,settings=warmup_fixture()
        for changed in ([r for r in records if r['tradingDate']>='2017-01-01'],[r for r in records if r['tradingDate']<'2018-01-02']):
            with self.assertRaises(ValueError): combine_warmup('FPT',changed,base,settings)

    def test_wrong_symbol_raw_warmup_cannot_enter_dataset(self) -> None:
        records,base,settings=warmup_fixture()
        with self.assertRaises(ValueError): combine_warmup('VCB',records,base,settings)

    def test_warmup_resume_does_not_fetch_completed_symbol(self) -> None:
        records,base,settings=warmup_fixture()
        release={'warmup':settings,'config':{'symbol_order':['FPT']}}
        with TemporaryDirectory() as folder, patch('core.mt_bicl_v4_warmup.load_verified_execution_data',return_value=(base,[])):
            root=Path(folder)
            fetch=Mock(return_value=(records,[]))
            first=load_warmup(root,release,fetch=fetch)
            second=load_warmup(root,release,fetch=fetch)
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(first[1],second[1])
            pd.testing.assert_frame_equal(first[0]['FPT'],second[0]['FPT'])

    def test_missing_sealed_warmup_never_refetches_to_hide_integrity_failure(self) -> None:
        records,base,settings=warmup_fixture()
        release={'warmup':settings,'config':{'symbol_order':['FPT']}}
        with TemporaryDirectory() as folder, patch('core.mt_bicl_v4_warmup.load_verified_execution_data',return_value=(base,[])):
            root=Path(folder)
            fetch=Mock(return_value=(records,[]))
            load_warmup(root,release,fetch=fetch)
            (root/DIRECTORY/'warmup/FPT.json').unlink()
            with self.assertRaises(ValueError): load_warmup(root,release,fetch=fetch)
            self.assertEqual(fetch.call_count,1)


if __name__=='__main__':
    unittest.main()
