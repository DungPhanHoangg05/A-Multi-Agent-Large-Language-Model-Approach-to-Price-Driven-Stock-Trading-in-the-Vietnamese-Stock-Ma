"""Schema và identity riêng cho producer/consumer U-BICL, giữ nguyên schema legacy."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from core.bayesian_memory import read_json
from core.prior_config import copy_prior_json
from core.unified_bayes_runtime import CODE as KERNEL_CODE

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "docs/plan/week10/schemas/unified_bic_artifacts_v1.schema.json"
PLAN_VERSION = "unified_bic_cohort_plan_v1"
REQUEST_VERSION = "unified_bic_request_bundle_v1"
REPORT_VERSION = "unified_bic_cohort_report_v1"
SYMBOLS = ("FPT", "MWG", "VCB", "VNM")
MATRIX = ("Original", "A_reference", "U_full", "U_stats", "U_examples", "Numeric_only")
CODE = tuple(dict.fromkeys((*KERNEL_CODE, "core/unified_bayes_contracts.py", "core/unified_bayes_source.py",
    "core/unified_bayes_cohort.py", "core/unified_bayes_reports.py", "scripts/run_unified_bayes.py", SCHEMA,
    "core/prior_backtest.py", "core/research_metrics.py", "core/paired_candidate_report.py",
    "core/candidate_selection.py", "scripts/prepare_unified_bayes_execution.py")))


def sha(path: Path) -> str:
    """Băm byte artifact, không chuẩn hóa newline của bằng chứng."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_identity() -> dict[str, str]:
    """Ghim code LF cùng schema và primitive kinh tế/report được dùng."""
    return {name: hashlib.sha256((ROOT / name).read_text("utf-8").encode()).hexdigest() for name in CODE}


def validate(value: dict[str, Any], kind: str) -> dict[str, Any]:
    """Kiểm JSON native hữu hạn trước schema; semantic phải qua loader nguồn."""
    value = copy_prior_json(value)
    schema = read_json(ROOT / SCHEMA)
    if kind not in schema["$defs"]:
        raise ValueError("Loại artifact U-BICL chưa đăng ký")
    errors = list(Draft202012Validator({**schema, "$ref": "#/$defs/" + kind}).iter_errors(value))
    if errors:
        raise ValueError(f"Artifact U-BICL sai schema {kind}: {errors[0].json_path}")
    return value
