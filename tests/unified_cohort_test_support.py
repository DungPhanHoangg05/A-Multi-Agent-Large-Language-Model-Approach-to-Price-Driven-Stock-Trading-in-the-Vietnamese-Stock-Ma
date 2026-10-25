"""Cohort bốn mã tổng hợp qua source/context/kernel/SDK thật và HTTP mock."""

from copy import deepcopy
from typing import Any
from unittest.mock import patch

from core.pit_price_features import extract_pit_price_features
from core.unified_bayes_decision import DecisionPreparer
from core.unified_bayes_source import BoundCohort
from unified_execution_test_support import ExecutionFixture, MODELS, SourcePoint, shared_state


def make_cohort(fx: ExecutionFixture) -> BoundCohort:
    """Không sửa production loader; fixture được đánh dấu rõ, nhãn qua evaluator engine."""
    prepared, sources, upstream = [], {}, {}
    fx.evaluations = []
    with patch("core.unified_bayes_decision.load_renderer_lock", return_value={}):
        producer = DecisionPreparer(fx.context, fx.llm, MODELS)
    for symbol in ("FPT", "MWG", "VCB", "VNM"):
        shared = shared_state()
        shared["stock_name"] = symbol
        frame, events = fx.inputs["prices"][symbol]
        features = extract_pit_price_features(frame, events, fx.inputs["calendar"], shared["as_of_date"], source=fx.inputs["source"])
        point = SourcePoint(features, shared)
        point.source_provenance["prices"] = {"snapshot_start_date": "2022-11-01"}
        def data(actual, source=point):
            source.check()
            fx.evaluations.append(actual)
            return deepcopy(fx.inputs["prices"][actual])
        point._adapter.execution_data = data
        value = producer.prepare(point, shared)
        prepared.append(value)
        sources[value.point_id] = point
        upstream[value.point_id] = {"files": {}, "shared_sha256": value.shared_sha256}
    def check() -> None:
        for point in sources.values():
            point.check()
    return BoundCohort(prepared, sources, upstream, check, {}, MODELS)
