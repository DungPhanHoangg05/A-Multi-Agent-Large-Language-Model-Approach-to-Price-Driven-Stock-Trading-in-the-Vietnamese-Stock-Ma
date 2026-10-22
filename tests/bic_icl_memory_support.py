"""Fixture nhỏ cho revision, dùng engine/extractor/scaler và retriever thật."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pandas as pd

from core.bic_icl_memory import RevisionMemory, _BUILT, build_revision_index
from core.historical_signals import digest
from core.pit_price_features import extract_pit_price_features
from prior_price_similarity_support import PriceSimilarityFixture


def revision_fixture(fx: PriceSimilarityFixture) -> tuple:
    """Tạo snapshot fixture qua cùng biên union/index, không đọc output thật."""
    memory = RevisionMemory({'status': 'AVAILABLE', 'records': deepcopy(fx.records)}, verified=_BUILT)
    adapter = SimpleNamespace(_prices=fx.inputs['prices'], _vnindex=pd.DataFrame({'Datetime': fx.inputs['calendar']}),
        _price_feature_index_inputs=lambda: fx.inputs,
        price_features=lambda symbol, cutoff: extract_pit_price_features(*fx.inputs['prices'][symbol],
            fx.inputs['calendar'], cutoff, source=fx.inputs['source']))
    return memory, build_revision_index(memory, adapter, fx.index)


def diagnostic_row(key: str, label: int, probabilities: dict | None = None) -> dict:
    """Hàng chấm điểm độc lập readiness, không giả score từ return."""
    return {'episode_id': key, 'symbol': 'FPT', 'as_of_date': '2021-03-01', 'fold_id': 'train_2021',
        'regime': 'BULL', 'quarter': '2021Q1', 'label': label, 'net_long_return': .02 if label else -.03,
        'probability': probabilities or {'A': .5, 'R2': .6, 'R4': .6, 'R8': .6},
        'ready': {name: False for name in ('A', 'R2', 'R4', 'R8')}}


class CheckpointFixture:
    """Point tin cậy tối thiểu để kiểm biên adapter/journal và hợp đồng T+3."""

    def __init__(self) -> None:
        from core.prior_context import REPORT_FIELDS
        self.days = pd.bdate_range('2023-01-02', periods=12)
        self.frame = pd.DataFrame({'Datetime': self.days, 'Open': 100., 'Close': 102., 'High': 103.,
                                  'Low': 99., 'Volume': 1000, 'Reference': 102.})
        cutoff = self.days[2].strftime('%Y-%m-%d')
        self.proof = {'context': {'symbol': 'FPT', 'as_of_date': cutoff}}
        self.bundle = {'reports': {k: f'Báo cáo {k}' for k in REPORT_FIELDS}, 'sentiment_data': {},
            'current_signals': {'trend': 'BULLISH', 'pattern': 'NEUTRAL', 'alpha_consensus': 'NEUTRAL',
                'indicator_consensus': 'BEARISH', 'sentiment': 'NEUTRAL'},
            'market_regime': {'regime_name': 'BULL'}, 'prior_provenance': {}, 'alpha_factors': []}
        self.sealed = False
        def restore(bundle: dict) -> dict:
            if bundle != self.bundle:
                raise ValueError('Bundle không khớp nguồn fixture')
            self.sealed = True
            return deepcopy(bundle)
        def prices(symbol: str) -> tuple:
            if not self.sealed:
                raise AssertionError('Đọc giá nhãn trước seal upstream')
            return self.frame, []
        self.point = SimpleNamespace(source_provenance=self.proof, restore_full_bundle=restore,
                                     _adapter=SimpleNamespace(execution_data=prices))
        pid, signature = f'FPT-{cutoff}', 'a'*64
        nodes = {name: {'input_sha256': 'b'*64, 'attempts': [{'status': 'complete', 'output': {
            **{k: self.bundle['reports'][k] for k in (REPORT_FIELDS[3:] if name == 'full' else (name+'_report',))},
            **({'sentiment_data': {}} if name == 'full' else {})}}]}
            for name in ('indicator', 'pattern', 'trend', 'full')}
        self.journal = {'version': 'agent_stage_journal_v1', 'binding': {'run_signature': signature,
            'point_id': pid, 'source_sha256': digest(self.proof)}, 'nodes': nodes}
        self.document = {'point_version': 'improvement_shared_point_v1', 'run_signature': signature,
            'point_id': pid, 'context': {'symbol': 'FPT', 'as_of_date': cutoff}, 'source_proof': self.proof,
            'full_bundle': deepcopy(self.bundle), 'shared_sha256': digest(self.bundle), 'journal_sha256': 'c'*64}
        self.options = {'point': self.point, 'signature': signature, 'journal_sha256': 'c'*64}
