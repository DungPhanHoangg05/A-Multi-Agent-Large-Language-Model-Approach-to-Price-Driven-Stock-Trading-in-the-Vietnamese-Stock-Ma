"""Kiểm replay độc lập: undefined, ledger, bootstrap và runtime image fail-closed."""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from core.revision_clean_metrics import (Comparator, bootstraps, classification, ledger,
    raw_prediction, sha, target)
from core.revision_clean_replay import build_release, clean_environment, install_numpy_image, make_numpy_image


class CleanMetricsTests(unittest.TestCase):
    """Oracles nhỏ có kết quả tính tay, không gọi runner hoặc API."""

    def test_class_support_and_undefined_are_not_zero(self) -> None:
        metrics=classification(['UP','UP','DOWN','DOWN'],['LONG','SHORT','LONG','SHORT'])
        self.assertEqual(metrics['confusion'],{'tp':1,'fn':1,'tn':1,'fp':1})
        self.assertEqual(metrics['balanced_accuracy'],.5); self.assertEqual(metrics['mcc'],0.)
        only=classification(['DOWN'],['SHORT']); self.assertIsNone(only['balanced_accuracy']); self.assertIsNone(only['mcc'])
        with self.assertRaises(ValueError): classification(['UP'],['UNKNOWN'])

    def test_anchor_cash_gap_and_continuous_hold_differ(self) -> None:
        frame={'Open':np.asarray([100.,100.,120.,80.,100.]),'Close':np.asarray([100.,110.,120.,80.,100.]),'date':['d0','d1','d2','d3','d4']}
        protocol={'initial_capital_vnd':100.,'fee_each_side':0.,'slippage_each_side':0.}
        cycle=ledger(frame,[(0,1,1),(4,4,0)],protocol); hold=ledger(frame,[(0,4,1)],protocol)
        self.assertAlmostEqual(cycle['net_return_pct'],10.); self.assertAlmostEqual(hold['net_return_pct'],0.)
        self.assertEqual([r['equity_vnd'] for r in cycle['daily']],[100.,110.,110.,110.,110.])
        self.assertEqual(cycle['order_count'],2); self.assertAlmostEqual(hold['daily_close_drawdown_pct'],100/3)
        with self.assertRaises(ValueError): ledger(frame,[(0,2,1),(2,4,1)],protocol)

    def test_net_target_does_not_switch_to_gross(self) -> None:
        frame={'Open':np.ones(4)*100,'Close':np.asarray([100.,100.,100.,100.1])}
        self.assertEqual(target(frame,0,{'fee_each_side':.0025,'slippage_each_side':.001}),('DOWN','UP'))

    def test_raw_content_tool_calls_and_invalid_prediction(self) -> None:
        for message in ({'content':'{"decision":"LONG"}'},{'tool_calls':[{'args':{'decision':'LONG'}}]},
                        {'content':'','additional_kwargs':{'tool_calls':[{'function':{'arguments':'{"decision":"LONG"}'}}]}}):
            self.assertEqual(raw_prediction({'response':{'generations':[[{'message':message}]]}}),'LONG')
        with self.assertRaises(ValueError): raw_prediction({'response':{'generations':[[{'message':{'content':'{"decision":"HOLD"}'}}]]}})

    def test_comparator_rejects_missing_null_mismatch_and_changed_metric(self) -> None:
        for expected,actual in [({'x':None},{'x':0.}),({'x':1.},{'x':1.01}),({'x':1},{})]:
            with self.subTest(expected=expected),self.assertRaises(ValueError): Comparator().check(expected,actual)
        compare=Comparator(); compare.check({'x':1.},{'x':1.+1e-12}); self.assertEqual(compare.floats,1)

    def test_bootstrap_zero_weight_undefined_run_is_ignored_only_when_unselected(self) -> None:
        counts=np.asarray([[[0,1,1,0]],[[1,0,1,0]],[[1,0,1,0]]]); returns=np.asarray([[[0.,1]],[[0.,1]],[[0.,1]]])
        result=bootstraps({'AS':counts,'B':counts},{'AS':returns,'B':returns},np.ones((2,1),dtype=int),np.asarray([[0,1,2],[3,0,0]]),False)
        mcc=result['variants']['AS']['mcc']; self.assertEqual(mcc['n_defined'],1); self.assertEqual(mcc['n_undefined'],1)
        self.assertEqual(mcc['percentile_95'],[1.,1.])


class CleanEnvironmentTests(unittest.TestCase):
    """Không cho fallback package/network khi source image thiếu hoặc sai."""

    def test_child_environment_does_not_inherit_secrets_or_pythonpath(self) -> None:
        with tempfile.TemporaryDirectory() as td,patch.dict('os.environ',{'GROQ_API_KEY':'SYNTHETIC','PYTHONPATH':'outside','HTTPS_PROXY':'outside'}):
            root=Path(td); env=clean_environment(root)
            for key in ('GROQ_API_KEY','PYTHONPATH','HTTPS_PROXY'): self.assertNotIn(key,env)
            self.assertTrue(Path(env['HF_HOME']).is_relative_to(root))

    def test_numpy_record_tamper_is_detected_before_archive_creation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/'__init__.py'; source.write_bytes(b'changed')
            class Entry:
                hash=SimpleNamespace(mode='sha256',value=base64.urlsafe_b64encode(bytes.fromhex(sha(b'original'))).decode().rstrip('='))
                def __str__(self) -> str: return 'numpy/__init__.py'
            dist=SimpleNamespace(version='2.1.2',files=[Entry()],locate_file=lambda _:source)
            with patch('core.revision_clean_replay.metadata.distribution',return_value=dist),self.assertRaises(ValueError): make_numpy_image(root/'image.zip')
            self.assertFalse((root/'image.zip').exists())

    def test_missing_runtime_image_does_not_resolve_or_install_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError): install_numpy_image(Path(td)/'missing.zip',{},Path(td)/'venv')

    def test_release_overwrite_and_outside_path_rejected_before_extract(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); old=root/'outputs/revision/old'; old.mkdir(parents=True)
            for target_path in (old,root/'paper/new'):
                with patch('core.revision_clean_replay.extract_release') as extract,self.assertRaises(ValueError):
                    build_release(root,target_path,root/'package')
                extract.assert_not_called()


if __name__=='__main__':
    unittest.main()
