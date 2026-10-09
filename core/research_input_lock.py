"""Khóa input W5 và dry-run PIT; giao thức benchmark cuối còn chờ W7."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from importlib.metadata import version
from io import StringIO
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile
from typing import Any, Callable

import pandas as pd

from core.backtest_engine import PRIOR_BRANCH_MODES
from core.bayesian_memory import iso_date, read_json
from core.cohort_calendar import VERSION as CALENDAR_VERSION, _read_locked_coverage, _verify_files, design_calendar
from core.execution_prices import STOCK_SYMBOLS, execution_prices_for_cycle
from core.groq_pacing import MODEL_LIMITS
from core.historical_signals import CODE_FILES, digest
from core.prior_config import copy_prior_json, normalize_prior_config
from core.prior_evidence_v2 import normalize_evidence_config
from core.prior_run_lock import safe_path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "research_input_lock_v1"
INPUT_FIELDS = ("execution_dir", "news_dir", "execution_manifest_sha256", "model", "signal_config",
                "client_options", "limits", "quota_source", "news_sources")
CODE_PATHS = tuple(sorted(set((*CODE_FILES, "core/backtest_engine.py", "core/prior_context.py",
    "core/prior_backtest.py", "core/prior_config.py", "core/decision_prior.py", "core/bayesian_retriever.py",
    "agents/decision_agent.py", "core/prior_checkpoint.py", "core/prior_run_lock.py", "core/groq_pacing.py",
    "core/prior_stage_journal.py", "core/pilot_readiness.py", "core/research_cohort.py",
    "core/research_metrics.py", "core/prior_evidence_v2.py", "core/research_invocation.py",
    "core/research_input_lock.py", "core/cohort_calendar.py", "core/oos_coverage.py",
    "core/regime_detector.py", "core/historical_runner.py", "utils/decision_parser.py", "utils/historical_api.py",
    "scripts/run_bayesian_ablation.py", "scripts/prepare_research_inputs.py",
    "docs/plan/week4/research_checkpoint.schema.json", "docs/plan/week4/checkpoint_policy.json",
    "docs/plan/week1/historical_task_record.schema.json", "docs/plan/week1/market_regime_state.schema.json",
    "requirements.txt", ".python-version"))))
PACKAGES = ("numpy", "pandas", "scipy", "TA-Lib", "langgraph", "langchain-core", "langchain-groq",
    "hmmlearn", "scikit-learn", "vnstock", "vnai", "httpx", "tiktoken", "Pillow", "groq",
    "langchain", "python-dotenv", "jsonschema", "pydantic", "matplotlib", "mplfinance", "requests")
ECONOMIC_CONTRACT = {"entry": "OPEN_T_PLUS_1", "exit": "CLOSE_T_PLUS_3", "short": "CASH",
    "fee_per_leg": .0025, "slippage_per_leg": .001, "label_function": "compute_round_trip_net_return"}


def runtime_identity() -> dict[str, str]:
    """Khóa Python và dependency đang chạy, không đọc biến môi trường/API key."""
    return {"python": platform.python_version(), **{name: version(name) for name in PACKAGES}}


def _read(path: Path) -> dict[str, Any]:
    """Envelope đúng hash canonical của CLI cohort, chặn credential trước đọc."""
    from core.prior_backtest import canonical_hash
    path = path.resolve()
    if path.name.startswith(".env"):
        raise ValueError("Input lock không được đọc credential")
    envelope = copy_prior_json(read_json(path))
    if type(envelope) is not dict or set(envelope) != {"payload", "sha256"} or canonical_hash(envelope["payload"]) != envelope["sha256"]:
        raise ValueError("Envelope input lock/plan không hợp lệ")
    return envelope["payload"]


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    """Tạo file nguyên tử độc quyền; chạy lại chỉ nhận đúng identity đã lưu."""
    from core.prior_backtest import canonical_hash
    envelope = {"payload": payload, "sha256": canonical_hash(payload)}
    if path.exists():
        if _read(path) != payload:
            raise ValueError("Input/plan đã khóa với identity khác; cần run mới")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(envelope, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if _read(path) != payload:
                raise ValueError("Tiến trình khác đã khóa input khác identity") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _smoke_plan(lock: dict[str, Any]) -> dict[str, Any]:
    """Plan năm nhánh dùng trực tiếp CLI; không tạo plan benchmark chưa khóa."""
    return {"plan_version": "research_cohort_plan_v2", "cohort_id": "four-stock-smoke-input-v1",
        "split": "development_2023", "matrix": "smoke_v1",
        "symbol_cutoffs": deepcopy(lock["cohorts"]["smoke"]),
        "evidence_config": deepcopy(lock["evidence_config_technical_defaults"]), "inputs": deepcopy(lock["inputs"])}


def validate_lock(lock: dict[str, Any], root: Path) -> None:
    """Kiểm byte nguồn/code/schema/runtime trước dry-run và trước runner dùng plan."""
    if (lock.get("lock_version") != VERSION or lock.get("status") != "LOCKED_OFFLINE_BUDGET_DEFERRED"
            or lock.get("budget_status") != "DEFERRED_BY_USER" or lock.get("benchmark_protocol") != "PENDING_W7"
            or lock.get("quota_policy") != "request_admission_v2"):
        raise ValueError("Input lock sai version hoặc tự nâng gate chưa nghiệm thu")
    if set(lock["code_sha256"]) != set(CODE_PATHS) or lock["economic_contract"] != ECONOMIC_CONTRACT:
        raise ValueError("Thiếu code/schema hoặc hợp đồng kinh tế khác bản đã khóa")
    _verify_files({**lock["sources"], **lock["code_sha256"]}, root)
    if lock["runtime"] != runtime_identity():
        raise ValueError("Runtime/dependency khác input đã khóa")
    if (lock["inputs"]["limits"] != MODEL_LIMITS or lock["prior_config"] != normalize_prior_config({"enable_bayesian_prior": True})
            or lock["evidence_config_technical_defaults"] != normalize_evidence_config()):
        raise ValueError("Config/quota/seed/scope khác input đã khóa")
    calendar, checksum = _read_locked_coverage(lock["calendar"]["path"], root)
    if (lock["calendar"]["sha256"] != checksum or lock["calendar"]["payload_sha256"] != digest(calendar)
            or lock["points"] != calendar["points"] or lock["summary"] != calendar["summary"]
            or lock["cohorts"] != {"smoke": calendar["smoke"]["symbol_cutoffs"],
                **{name: group["symbol_cutoffs"] for name, group in calendar["cohorts"].items()}}):
        raise ValueError("Manifest khác phân hoạch/ngày/proof lịch W5-10")
    required = {**calendar["sources"], lock["calendar"]["path"]: checksum}
    if any(lock["sources"].get(path) != sha for path, sha in required.items()):
        raise ValueError("Manifest bỏ nguồn đã ghim trong calendar")
    legacy = _read(safe_path(root, "outputs/oos_pilot/inputs/plan.json"))
    if lock["inputs"] != {key: legacy[key] for key in INPUT_FIELDS} or lock["smoke_matrix"] != list(PRIOR_BRANCH_MODES):
        raise ValueError("Model/config/ma trận khác nguồn đã khóa")
    if (lock["gate_c"] != "PENDING" or lock["ledger_path"] != "outputs/oos_pilot/api_usage.json"
            or lock["retry_policy"] != {"version": "invocation_budget_v2", "max_http_attempts": 3, "max_wait_seconds": 120}):
        raise ValueError("Policy/ledger hoặc gate khác trạng thái đã khóa")


def validate_bound_plan(plan: dict[str, Any], root: Path) -> dict[str, Any]:
    """Plan smoke phải khớp manifest nguyên byte; không thể đổi ngày/config rồi băm lại."""
    binding = plan["inputs"]["input_lock"]
    if type(binding) is not dict or set(binding) != {"path", "sha256"}:
        raise ValueError("Binding input lock không hợp lệ")
    path = safe_path(root, binding["path"])
    if (not path.is_relative_to((root / "outputs/bayesian_benchmark").resolve())
            or path.name.startswith(".env") or hashlib.sha256(path.read_bytes()).hexdigest() != binding["sha256"]):
        raise ValueError("Manifest input lock khác plan")
    lock = _read(path)
    validate_lock(lock, root)
    base = deepcopy(plan)
    del base["inputs"]["input_lock"]
    if base != _smoke_plan(lock):
        raise ValueError("Plan khác lịch/model/config smoke đã khóa")
    return lock


def dry_run_points(lock: dict[str, Any], adapter: Any, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Kiểm mọi ngày đã chọn, chỉ đọc giá thực thi để kiểm eligibility, không tạo nhãn."""
    from agents.decision_agent import BACKTEST_PROMPT_CHAR_LIMIT_EXCLUSIVE, _BACKTEST_REPORT_CHAR_LIMITS
    if BACKTEST_PROMPT_CHAR_LIMIT_EXCLUSIVE != 6500 or sum(_BACKTEST_REPORT_CHAR_LIMITS.values()) != 4000:
        raise ValueError("Cap prompt/báo cáo khác hợp đồng backtest")
    if adapter.prior_config != lock["prior_config"] or adapter.signal_config != lock["inputs"]["signal_config"]:
        raise ValueError("Adapter khác cấu hình đã khóa")
    verified, by_cohort = 0, {}
    seen = set()
    for cohort, stocks in lock["cohorts"].items():
        if set(stocks) != set(STOCK_SYMBOLS):
            raise ValueError("Cohort thiếu bốn mã")
        count = 0
        for symbol, cutoffs in stocks.items():
            if type(cutoffs) is not list or not cutoffs or cutoffs != sorted(set(cutoffs)):
                raise ValueError("Lịch cohort thiếu, trùng hoặc không tăng dần")
            frame, events = adapter.execution_data(symbol)
            dates = pd.DatetimeIndex(frame.Datetime)
            positions = dates.get_indexer(pd.to_datetime(cutoffs))
            if (positions < 599).any() or (positions + 3 >= len(dates)).any() or (positions[1:] - positions[:-1] < 3).any():
                raise ValueError("Chu kỳ thiếu warmup/exit hoặc chồng lấn")
            for day, position in zip(cutoffs, positions.tolist()):
                iso_date(day)
                if (symbol, day) in seen:
                    raise ValueError("Smoke/mẫu chính trùng điểm")
                seen.add((symbol, day))
                metadata = lock["points"][f"{symbol}-{day}"]
                entry, exit_date = (dates[position + offset].strftime("%Y-%m-%d") for offset in (1, 3))
                year = "2024" if cohort == "holdout_2024" else "2023"
                if ((entry, exit_date) != (metadata["entry_date"], metadata["exit_date"])
                        or any(not date.startswith(year + "-") for date in (day, entry, exit_date))):
                    raise ValueError("Entry/exit khác lịch đã khóa hoặc vượt năm")
                execution_prices_for_cycle(frame, events, day, entry, exit_date)
                with redirect_stdout(StringIO()):
                    point = adapter.prepare(symbol, day)
                if digest(point.source_provenance) != metadata["proof_sha256"] or digest(point.market_regime) != metadata["regime_state_sha256"]:
                    raise ValueError("Proof PIT/regime khác lịch đã khóa")
                verified += 1
                count += 1
                if progress and verified % 16 == 0:
                    progress(f"Đã kiểm PIT/thực thi {verified}/{len(lock['points'])} điểm")
        by_cohort[cohort] = count
    adapter.verify_sources()
    return {"status": "PASS", "verified_points": verified, "by_cohort": by_cohort,
        "source_pit_execution_identity": "PASS", "prefix_and_prompt_cap_configuration": "PASS",
        "prefix_max_chars": 600, "prompt_chars_exclusive": 6500,
        "actual_prefix_and_full_prompt": "NOT_GENERATED_NO_UPSTREAM",
        "query_outcome": "NOT_GENERATED", "budget": "DEFERRED_BY_USER", "gate_c": "PENDING"}


def prepare_inputs(calendar_path: Path, *, root: Path = ROOT,
                   progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Khóa ba lịch và plan smoke; không refit, tạo tín hiệu hay gọi LLM."""
    from core.pilot_readiness import INPUT_DIR, build_adapter, verify_inputs
    relative = calendar_path.resolve().relative_to(root.resolve()).as_posix()
    calendar, checksum = _read_locked_coverage(relative, root)
    if calendar.get("version") != CALENDAR_VERSION or calendar["verification"]["selected_pit_and_execution"] != "PASS":
        raise ValueError("Cần calendar W5-10 đã kiểm PIT/thực thi")
    # Tái lập selection từ coverage, giữ nguyên lịch và embargo pilot/smoke.
    coverage_path = [p for p in calendar["sources"] if p.endswith("/coverage.json")]
    if len(coverage_path) != 1:
        raise ValueError("Lịch thiếu nguồn coverage duy nhất")
    coverage, _ = _read_locked_coverage(coverage_path[0], root)
    expected = design_calendar(coverage, calendar["observed_pilot"],
        points_per_quarter=calendar["selection"]["points_per_symbol_quarter"])
    if any(calendar[key] != expected[key] for key in expected):
        raise ValueError("Lịch khác phương pháp selection đã đăng ký")
    directory = safe_path(root, "outputs/bayesian_benchmark")
    lock_path = safe_path(root, "outputs/bayesian_benchmark/input_lock.json")
    plan_path = safe_path(root, "outputs/bayesian_benchmark/smoke_plan.json")
    if not lock_path.exists() and any(directory.rglob("cohort.json")):
        raise ValueError("Đã có run cohort; không khóa plan sau khi thực thi")
    legacy = verify_inputs(root)
    adapter = build_adapter(legacy, root)
    sources = {**calendar["sources"], **adapter.source_hashes, relative: checksum}
    source_plan = f"{INPUT_DIR}/plan.json"
    if source_plan not in sources:
        raise ValueError("Calendar thiếu plan nguồn đã khóa")
    cohorts = {"smoke": deepcopy(calendar["smoke"]["symbol_cutoffs"]),
        **{name: deepcopy(group["symbol_cutoffs"]) for name, group in calendar["cohorts"].items()}}
    lock = {"lock_version": VERSION, "status": "LOCKED_OFFLINE_BUDGET_DEFERRED",
        "calendar": {"path": relative, "sha256": checksum, "payload_sha256": digest(calendar)},
        "cohorts": cohorts, "points": deepcopy(calendar["points"]), "summary": deepcopy(calendar["summary"]),
        "inputs": {key: deepcopy(legacy[key]) for key in INPUT_FIELDS},
        "prior_config": adapter.prior_config, "evidence_config_technical_defaults": normalize_evidence_config(),
        "smoke_matrix": list(PRIOR_BRANCH_MODES), "benchmark_protocol": "PENDING_W7",
        "budget_status": "DEFERRED_BY_USER", "gate_c": "PENDING",
        "quota_policy": "request_admission_v2", "ledger_path": "outputs/oos_pilot/api_usage.json",
        "retry_policy": {"version": "invocation_budget_v2", "max_http_attempts": 3, "max_wait_seconds": 120},
        "economic_contract": deepcopy(ECONOMIC_CONTRACT),
        "sources": sources, "code_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in CODE_PATHS},
        "runtime": runtime_identity()}
    lock["dry_run"] = dry_run_points(lock, adapter, progress=progress)
    validate_lock(lock, root)
    _verify_files({**calendar["code_sha256"], **sources}, root)
    _write_once(lock_path, lock)
    plan = _smoke_plan(lock)
    plan["inputs"]["input_lock"] = {"path": lock_path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest()}
    validate_bound_plan(plan, root)
    _write_once(plan_path, plan)
    return lock


def verify_inputs(*, root: Path = ROOT, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Kiểm lại manifest/plan và 128 điểm bằng nguồn thật; chỉ đọc runtime."""
    from core.pilot_readiness import build_adapter
    path = safe_path(root, "outputs/bayesian_benchmark/smoke_plan.json")
    plan = _read(path)
    lock = validate_bound_plan(plan, root)
    adapter = build_adapter(lock["inputs"], root)
    result = dry_run_points(lock, adapter, progress=progress)
    validate_lock(lock, root)
    if result != lock["dry_run"]:
        raise ValueError("Kết quả dry-run khác manifest đã khóa")
    return lock
