"""Receipt semantic fixtures theo commit để tái lập QA mà không ghi đè bằng chứng cũ."""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

from core.bayesian_memory import read_json
from core.mt_bicl_v2_io import write_envelope
from core.mt_bicl_v2_release import runtime_identity
from core.mt_bicl_v21_preparation import file_hash
from core.mt_bicl_v3_validation_inputs import CHECKS, CHECKS_VERSION, CHECK_SOURCES, CODE, validate_checks


class _Result(unittest.TextTestResult):
    """Thu đúng test IDs PASS, không biến suite bị skip/lỗi thành receipt đạt gate."""

    def startTestRun(self) -> None:
        self.successful: list[str] = []
        super().startTestRun()

    def addSuccess(self, test: unittest.TestCase) -> None:
        self.successful.append(test.id())
        super().addSuccess(test)


def contracts(root: Path) -> dict[str, Any]:
    """Chỉ unit fixture được grant loại trừ; không mở RuntimeBudget hoặc dữ liệu thị trường."""
    sys.path.insert(0, str(root/"tests"))
    loader = unittest.TestLoader()
    suite = loader.discover(str(root/"tests"), pattern="test_mt_bicl_v3_*.py")
    suite.addTests(loader.loadTestsFromNames([
        "test_mt_bicl_v2_decision.DecisionTests.test_original_duplicate_is_an_independent_call_not_shared_off",
        "test_paired_protocol.PairedProtocolTests.test_run_invokes_one_paired_execution_per_test_point"]))
    result = unittest.TextTestRunner(verbosity=2, resultclass=_Result).run(suite)
    if not result.wasSuccessful() or result.skipped:
        raise ValueError("Fixture semantic/leakage chưa PASS đủ, không tạo QA receipt")
    patterns = ["four_bucket_signs|zero_net_is_retained", "facts_enum_and_citations", "negative_macd_above_signal",
        "insufficient_or_stale_prefix|four_bucket_signs", "projection_all_counts", "injected_query_labels|query_outcome_and_candidate_labels",
        "future_price_append|future_prices_and_query_label", "injected_query_labels", "injected_query_labels", "full_no_target_common_streams",
        "variants_recompute_two_p", "variants_recompute_two_p", "locked_policy_fixtures", "independent_scalar_mixture|oracle_all4096",
        "full_no_target_common_streams", "zero_net_is_retained", "zero_net_is_retained", "unsupported_keeps_anchor",
        "missing_response_api_error", "revision_plan_keeps_all_bypass", "crash_gap_conservative|resume_stages_and_W12",
        "original_duplicate_is_an_independent|run_invokes_one_paired_execution"]
    required = read_json(root/"docs/plan/week11/protocol_v3.json")["offline_validation"]["required_fixture_groups"]
    if len(patterns) != len(required): raise ValueError("Mapping semantic groups khác protocol")
    groups = {name: {"status": "PASS", "test_ids": [tid for tid in result.successful if re.search(pattern, tid)]}
              for name, pattern in zip(required, patterns)}
    commit = subprocess.check_output(["git", "log", "-1", "--format=%H", "--", *CODE], cwd=root, text=True).strip()
    payload = {"status": "PASS", "source_commit": commit, "source_sha256": {name: file_hash(root/name) for name in CHECK_SOURCES},
        "runtime": runtime_identity(), "tests_run": result.testsRun, "failures": [], "errors": [],
        "successful_test_ids": sorted(result.successful), "semantic_groups": groups,
        "scope": "ORDINARY_SYNTHETIC_CONTRACT_FIXTURES_NOT_MARKET_VALIDATION", "runtime_budget_exclusion": "ORDINARY_UNIT_FIXTURES",
        "real_API_calls": 0, "real_frozen_weights_forward": False}
    validate_checks(payload, payload["source_sha256"], required)
    path = root/CHECKS/(commit+".json")
    write_envelope(path, CHECKS_VERSION, payload, immutable=True)
    return {"path": path.relative_to(root).as_posix(), "sha256": file_hash(path), "tests_run": result.testsRun}
