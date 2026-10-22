"""Cohort tổng hợp 12 point, selector/renderer/SDK thật, không credential hoặc mạng thật."""

from copy import deepcopy
from types import SimpleNamespace
from typing import Any

from bic_icl_fixture import DecisionFixture
from bic_icl_tasks_support import TaskFixture
from core.bic_icl_protocol import CohortSources, schedule
from core.historical_signals import digest


class CohortFixture:
    """Nguồn tổng hợp chỉ cho fixture ngoài workspace; production dùng adapter PIT thật."""

    def __init__(self, language: str = 'vi') -> None:
        self.fx, self.sdk = TaskFixture(), DecisionFixture()
        self.root = self.sdk.root/'cohort'
        self.plan = {'split': 'fixture', 'schedule': schedule({s: ['2022-01-06', '2022-01-13', '2022-01-20']
            for s in ('FPT', 'MWG', 'VCB', 'VNM')}), 'language': language, 'upstream_policy': 'VERIFIED_CACHE',
            'code_sha256': {'fixture': 'a'*64}, 'runtime': {'python': 'fixture'}}
        self.signature = digest(self.plan)
        self.sources = SimpleNamespace(frozen=SimpleNamespace(index=self.fx.index, retriever=self.fx.retriever),
            selector=self.fx.selector, adapter=SimpleNamespace(execution_data=lambda symbol: self.fx.prices[symbol]),
            verify=lambda: None, validate=self.validate, cached=self.cached)
        self.sources.packet = lambda *args: CohortSources.packet(self.sources, *args)

    def validate(self, plan: dict[str, Any]) -> None:
        """Fixture thay plan/lịch phải dừng trước SDK."""
        if digest(plan) != self.signature:
            raise ValueError('Plan fixture khác binding')
        self.sources.verify()

    def cached(self, row: dict[str, str]) -> tuple[Any, dict[str, Any], dict[str, Any]]:
        """Mô phỏng source seal; không lấy response Decision cũ."""
        proof = {'context': {'symbol': row['symbol'], 'as_of_date': row['as_of_date']},
            'prices': {'snapshot_start_date': '2018-01-02'}}
        reports = {name+'_report': 'Báo cáo fixture.' for name in ('indicator', 'pattern', 'trend', 'alpha', 'sentiment')}
        shared = {'stock_name': row['symbol'], 'as_of_date': row['as_of_date'], 'is_backtest': True,
            'language': self.plan['language'], 'time_frame': '1d', **reports,
            'current_signals': deepcopy(self.fx.records[0]['agent_signals']),
            'market_regime': {'as_of_date': row['as_of_date'], 'feature_end_date': row['as_of_date'], 'regime_name': 'BULL'},
            'prior_provenance': proof}
        bundle = {'reports': reports, **{k: shared[k] for k in ('current_signals', 'market_regime', 'prior_provenance')}}
        def verify(actual: dict[str, Any]) -> None:
            if actual != shared:
                raise ValueError('Nguồn fixture bị thay đổi')
        from core.pit_price_features import extract_pit_price_features
        features = extract_pit_price_features(*self.fx.prices[row['symbol']], self.fx.calendar,
            row['as_of_date'], source=self.fx.source)
        point = SimpleNamespace(verify_source=verify, price_features=lambda: features, source_provenance=proof)
        return point, deepcopy(shared), deepcopy(bundle)

    def close(self) -> None:
        """Đóng SDK trước dọn fixture Windows."""
        self.sdk.close()
