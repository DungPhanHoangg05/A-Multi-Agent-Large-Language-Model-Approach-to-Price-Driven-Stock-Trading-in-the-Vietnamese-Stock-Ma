"""Fixture task với lịch neo 2018, index/scaler thật và nhãn engine thật."""

from copy import deepcopy
from typing import Any

import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core.bayesian_memory import HistoricalMemory
from core.bic_icl_memory import RevisionMemory, RevisionRetriever, _BUILT
from core.bic_icl_tasks import TaskSelector
from core.price_feature_index import build_price_feature_index


class TaskFixture:
    """Bốn mã giá phẳng, 20 background và 24 cycle BULL, gồm ba cặp gần query."""

    def __init__(self) -> None:
        self.calendar = pd.bdate_range('2018-01-02', '2022-12-30')
        self.prices = {symbol: (pd.DataFrame({'Datetime': self.calendar, 'Open': 100., 'High': 101.,
            'Low': 99., 'Close': 100., 'Volume': 1000, 'Reference': 100.}), [])
            for symbol in ('FPT', 'MWG', 'VCB', 'VNM')}
        self.source = {'source_library': 'vnstock', 'primary_source': 'VCI',
                       'price_basis': 'UNADJUSTED_EXECUTION', 'price_unit': 'thousand_VND'}
        self.records = ([self.record(p, 'BEAR') for p in range(300, 420, 6)]+
                        [self.record(p, 'BULL') for p in range(600, 708, 6)]+
                        [self.record(p, 'BULL') for p in (961, 967, 981, 987, 1001, 1007)])
        self.publish()

    def day(self, position: int) -> str:
        """Lấy ngày theo lịch fixture, không dùng phép cộng ngày lịch."""
        return self.calendar[position].strftime('%Y-%m-%d')

    def record(self, position: int, regime: str = 'BULL') -> dict[str, Any]:
        """Tính đúng nhãn T+3, hai chiều phí/slippage qua engine chung."""
        net = float(compute_round_trip_net_return(100., 100.)*100)
        return {'episode_id': f'FPT:{self.day(position)}', 'symbol': 'FPT', 'regime': regime,
            'as_of_date': self.day(position), 'entry_date': self.day(position+1), 'exit_date': self.day(position+3),
            'agent_signals': {'trend': 'BULLISH', 'pattern': 'NEUTRAL', 'alpha_consensus': 'NEUTRAL',
                'indicator_consensus': 'NEUTRAL', 'sentiment': 'NEUTRAL'},
            'outcome': {'actual_direction': 'DOWN', 'net_return_pct': net, 'was_bull_trap': True, 'result': 'LOSS_IF_LONG'}}

    def publish(self) -> None:
        """Xác minh schema/kinh tế trước cấp token fixture và tạo index bằng producer thật."""
        HistoricalMemory(execution_loader=lambda s: self.prices[s])._validate_all(self.records)
        self.memory = RevisionMemory({'status': 'AVAILABLE', 'records': deepcopy(self.records)}, verified=_BUILT)
        self.retriever = RevisionRetriever(self.memory)
        self.inputs = {'records': [{k: r[k] for k in ('episode_id', 'symbol', 'as_of_date', 'exit_date')} for r in self.records],
            'prices': self.prices, 'calendar': self.calendar, 'source': self.source,
            'provenance': {'bank': {'bank_sha256': self.memory.identity},
                'calendar': {'source_csv_sha256': 'c'*64},
                'prices': {s: {'csv_sha256': 'b'*64} for s in self.prices}}}
        self.index = build_price_feature_index(**self.inputs)
        self.selector = TaskSelector(self.index, self.calendar)

    def query(self, **changes: Any) -> dict[str, Any]:
        """Query đúng fold train 2022, không chứa payoff của target."""
        from core.pit_price_features import extract_pit_price_features
        cutoff = '2022-01-06'
        return {'selector': self.selector, 'query_features': extract_pit_price_features(
            *self.prices['FPT'], self.calendar, cutoff, source=self.source), 'symbol': 'FPT', 'as_of_date': cutoff,
            'current_regime': 'BULL', 'current_signals': deepcopy(self.records[0]['agent_signals']), **changes}

    def row(self, position: int, rank: int, vector: list[float] | None = None) -> dict[str, Any]:
        """Projection label-free cho oracle grouping và điều kiện biên chính xác."""
        r = self.record(position)
        return {**{k: r[k] for k in ('episode_id', 'symbol', 'regime', 'as_of_date', 'entry_date', 'exit_date')},
            'session_index': position, 'entry_session': position+1, 'exit_session': position+3,
            'rank_position': rank, 'rank_score': 1.-rank/1000, 'scaled_vector': vector or [0., 0., 0., 0.]}
