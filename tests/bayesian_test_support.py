"""Fixture chung cho kiểm hành vi/PIT; nhãn luôn sinh bằng engine T+2.5 thật."""

from __future__ import annotations

from typing import Any

import pandas as pd

from core.backtest_engine import compute_round_trip_net_return
from core import bayesian_retriever
import test_bayesian_retriever as foundations


class PriorPipelineFixture:
    """Kho tạm hai mã, có lịch sử đóng, exit bằng cutoff và query chưa đóng."""

    def __init__(self) -> None:
        self.base = foundations.BayesianRetrieverFoundationTests()
        self.base.setUp()
        self.base.frame = pd.DataFrame({'Datetime': pd.bdate_range('2020-01-01', periods=24),
            'Open': 100.0, 'High': 105.0, 'Low': 99.0, 'Close': 100.0, 'Volume': 1000, 'Reference': 100.0})
        self.base.frame.loc[[3, 12], 'Close'] = 102.0
        self.refresh_reference()
        specifications = [('FPT', 0, 'BULL', 'BULLISH', 'NEUTRAL'),
                          ('FPT', 3, 'BULL', 'BEARISH', 'BULLISH'),
                          ('FPT', 6, 'BULL', 'BULLISH', 'BULLISH'),
                          ('FPT', 9, 'BULL', 'BULLISH', 'BULLISH'),
                          ('FPT', 12, 'BEAR', 'NEUTRAL', 'NEUTRAL'),
                          ('MWG', 0, 'BULL', 'BULLISH', 'BULLISH'),
                          ('MWG', 3, 'BEAR', 'BEARISH', 'NEUTRAL'),
                          ('MWG', 6, 'BULL', 'BULLISH', 'BULLISH')]
        self.base.rows = [self.record(*specification) for specification in specifications]
        self.base.publish_fixture()

    def close(self) -> None:
        """Dọn kho tạm bằng cleanup của fixture nền."""
        self.base.doCleanups()

    def day(self, position: int) -> str:
        """Trả ngày phiên trong lịch fixture, không giả định ngày lịch là phiên."""
        return self.base.frame.Datetime.iloc[position].strftime('%Y-%m-%d')

    def refresh_reference(self) -> None:
        """Cập nhật giá tham chiếu bằng phép dịch vector khi sửa giá fixture."""
        self.base.frame['Reference'] = self.base.frame.Close.shift().fillna(100.0)

    def record(self, symbol: str, position: int, regime: str, trend: str, pattern: str) -> dict[str, Any]:
        """Dùng Open(t+1)/Close(t+3) và đúng phí/trượt giá của engine."""
        row = self.base.record(symbol, position, regime)
        row['agent_signals'].update(trend=trend, pattern=pattern)
        net = float(100 * compute_round_trip_net_return(100.0, float(self.base.frame.Close.iloc[position + 3])))
        row['outcome'] = {'actual_direction': 'UP' if net > 0 else 'DOWN', 'net_return_pct': net,
                          'result': 'WIN_IF_LONG' if net > 0 else 'LOSS_IF_LONG',
                          'was_bull_trap': (trend == 'BULLISH' or pattern == 'BULLISH') and net <= 0}
        return row

    def relabel(self) -> None:
        """Sinh lại mọi nhãn từ giá mới; không sửa outcome độc lập để lách validator."""
        dates = list(self.base.frame.Datetime.dt.strftime('%Y-%m-%d'))
        for row in self.base.rows:
            rebuilt = self.record(row['symbol'], dates.index(row['as_of_date']), row['regime'],
                                  row['agent_signals']['trend'], row['agent_signals']['pattern'])
            row['outcome'] = rebuilt['outcome']
        self.base.publish_fixture()

    def query(self, **updates: Any) -> dict[str, Any]:
        """Query tại phiên thứ 10; chỉ gửi tín hiệu, không gửi nhãn tương lai."""
        return self.base.query(**{'as_of_date': self.day(9), **updates})

    def create(self) -> bayesian_retriever.BayesianPriorRetriever:
        """Nạp kho qua schema và validator giá/nhãn thật, chỉ giả lập loader giá."""
        return self.base.create()

    @staticmethod
    def bundle(retriever: bayesian_retriever.BayesianPriorRetriever, query: dict[str, Any]) -> dict[str, Any]:
        """Đường gọi hoàn chỉnh retrieve → BRPP, không chứa outcome của query."""
        result = retriever.retrieve(**query)
        return {'result': result, 'prefix': bayesian_retriever.format_compact_prior_prefix(result['tasks'], result['stats'])}
