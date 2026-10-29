"""Nguồn/cohort và regime frozen cho validation v3, không fit hoặc đọc payoff2025."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
from typing import Any

import pandas as pd

from core.bayesian_memory import atomic_write_json, read_json
from core.execution_prices import load_verified_execution_data
from core.mt_bicl_bank import SYMBOLS, content_hash
from core.mt_bicl_regimes import RegimeTimeline
from core.mt_bicl_v2_adapter import load_inputs as inherited_inputs
from core.mt_bicl_v2_experiment import CONTEXT, CONTEXT_SHA256
from core.mt_bicl_v21_preparation import OUTPUT as TEACHER, TEACHER_VERSION, file_hash
from core.mt_bicl_v2_io import read_envelope
from core.mt_bicl_v3_protocol import verify as verify_protocol
from core.regime_detector import MarketRegimeDetector

OUTPUT = Path("outputs/bayesian_benchmark/mt_bicl_v3/offline_validation")
BANK = Path("outputs/bayesian_benchmark/mt_bicl_v1/inputs/dense_bank_v1.json")
IMPLEMENTATION = tuple("core/mt_bicl_v3_"+name+".py" for name in (
    "budget", "context", "contracts", "decision", "features", "policy", "utility"))
CODE = (*IMPLEMENTATION, "core/mt_bicl_v3_validation_inputs.py", "core/mt_bicl_v3_oracle.py",
        "core/mt_bicl_v3_validation.py", "scripts/validate_mt_bicl_v3.py",
        "tests/test_mt_bicl_v3_validation.py", "tests/test_mt_bicl_v3_validation_leakage.py")
CHECKS = Path("docs/plan/week11/validation_checks_v3.json")
CHECKS_VERSION = "utility_icl_validation_contract_checks_v3"
CHECK_SOURCES = (*CODE, "tests/mt_bicl_v3_support.py", "tests/test_mt_bicl_v3_budget.py",
                 "tests/test_mt_bicl_v3_decision.py", "tests/test_mt_bicl_v3_features_leakage.py",
                 "tests/test_mt_bicl_v3_utility.py", "tests/test_mt_bicl_v3_protocol.py",
                 "tests/test_mt_bicl_v2_decision.py", "tests/test_paired_protocol.py")


def validate_checks(value: dict[str, Any], sources: dict[str, str], required: list[str]) -> None:
    """Receipt fixture phải bind đúng source và đủ22 nhóm; không coi gate cũ là đã chạy lại."""
    ids = value["successful_test_ids"]
    if (value["status"] != "PASS" or value["source_sha256"] != sources or value["failures"] or value["errors"]
            or value["tests_run"] != len(ids) or len(ids) != len(set(ids)) or not ids
            or set(value["semantic_groups"]) != set(required)):
        raise ValueError("Receipt kiểm hợp đồng v3 sai source/count/semantic groups")
    for group in value["semantic_groups"].values():
        if group["status"] != "PASS" or not group["test_ids"] or not set(group["test_ids"]) <= set(ids):
            raise ValueError("Semantic fixture thiếu bằng chứng test PASS")


def cohort(bank: dict[str, Any], protocol: dict[str, Any]) -> list[dict[str, str]]:
    """Lưới cũ/giá/quyền/within-year; giữ missing feature, không mở giá trị nhãn query."""
    rows = []
    for row in bank["records"]:
        year = row["as_of_date"][:4]
        if year not in ("2021", "2022") or row["exit_date"][:4] != year or row["label_status"] != "AVAILABLE":
            continue
        rows.append({"point_id": row["episode_id"], "symbol": row["symbol"], "as_of_date": row["as_of_date"], "stage": "diagnostic"+year})
    for identifier in protocol["development"]["point_ids"]:
        rows.append({"point_id": identifier, "symbol": identifier[:3], "as_of_date": identifier[4:], "stage": "development2023"})
    rows.sort(key=lambda row: (row["as_of_date"], SYMBOLS.index(row["symbol"])))
    if len({row["point_id"] for row in rows}) != len(rows) or any(not any(r["stage"] == "diagnostic"+year for r in rows) for year in ("2021", "2022")):
        raise ValueError("Cohort thiếu năm hoặc trùng ID")
    return rows


class FrozenRegimes(RegimeTimeline):
    """Nạp JSON tham số và proof prefix đã khóa; không gọi fit của detector."""

    def __init__(self, history: pd.DataFrame, models: dict[str, Any], directory: Path) -> None:
        super().__init__(history)
        self.frozen = deepcopy(models)
        self.directory = directory

    def _model(self, cutoff: str) -> tuple[Any | None, dict[str, Any]]:
        """Chỉ tái định dạng container, tham số và hash model phải nguyên vẹn."""
        if cutoff > "2020-12-31":
            raise ValueError("Không nạp regime fit sau2020")
        prefix = self._prefix(cutoff)
        if len(prefix) < 499:
            return None, {"name": "UNKNOWN", "reason": "INSUFFICIENT_REGIME_HISTORY", "model_fit_cutoff": cutoff,
                          "prefix_rows": len(prefix), "model_training_end_date": None, "model_sha256": None, "method": "UNKNOWN"}
        if cutoff not in self._models:
            record = self.frozen[cutoff]
            parameters, proof = record["parameters"], record["proof"]
            if content_hash(parameters) != proof["model_sha256"] or proof["model_fit_cutoff"] != cutoff or proof["prefix_rows"] != len(prefix):
                raise ValueError("Regime frozen không khớp prefix/proof")
            payload = {"format_version": 2, "metadata": parameters["metadata"], "model": parameters["model"],
                       "scaler": {"mean": parameters["scaler"]["mean"], "var": parameters["scaler"]["variance"], "scale": parameters["scaler"]["scale"]}}
            envelope = {"payload": payload, "sha256": content_hash(payload)}
            path = self.directory/(cutoff+".json")
            if path.exists():
                if read_json(path) != envelope:
                    raise ValueError("Không ghi đè tham số regime v3 khác bản frozen")
            else:
                atomic_write_json(path, envelope)
            detector = MarketRegimeDetector.load(path, expected_training_hash=proof["training_data_sha256"])
            if self._serialize(detector) != parameters:
                raise ValueError("Tham số regime đổi khi nạp JSON")
            self._models[cutoff], self._proofs[cutoff] = detector, deepcopy(proof)
        return self._models[cutoff], deepcopy(self._proofs[cutoff])


def load_inputs(root: Path) -> dict[str, Any]:
    """Phải gọi trong RuntimeBudget; xác minh nguồn/runtime trước inference/validation."""
    lock = verify_protocol(root)
    inherited = inherited_inputs(root)
    protocol = read_json(root/"docs/plan/week11/protocol_v3.json")
    checks = read_envelope(root/CHECKS, CHECKS_VERSION)
    validate_checks(checks, {name: file_hash(root/name) for name in CHECK_SOURCES}, protocol["offline_validation"]["required_fixture_groups"])
    commit = subprocess.check_output(["git", "log", "-1", "--format=%H", "--", *CODE], cwd=root, text=True).strip()
    subprocess.run(["git", "diff", "--exit-code", commit, "--", *CODE], cwd=root, check=True, capture_output=True)
    for name in CODE:
        if subprocess.check_output(["git", "show", commit+":"+name], cwd=root) != (root/name).read_bytes():
            raise ValueError("Source validation chưa neo đúng byte Git: "+name)
    bank = read_json(root/BANK)
    if content_hash(bank["payload"]) != bank["sha256"] or file_hash(root/CONTEXT) != CONTEXT_SHA256:
        raise ValueError("Bank/context inherited sai checksum")
    bank = bank["payload"]
    history_path = root/"data/historical/VNINDEX.csv"
    history = pd.read_csv(history_path, parse_dates=["Datetime"])
    history = history.loc[history["Datetime"] <= "2023-12-31"].copy()
    prices = {s: load_verified_execution_data(root/"data/execution_prices_oos", s) for s in SYMBOLS}
    prices = {s: (frame.loc[frame["Datetime"] <= "2023-12-31"].copy(), [e for e in events if e["exrightDate"] <= "2023-12-31"])
              for s, (frame, events) in prices.items()}
    rows = cohort(bank, protocol)
    paths = [BANK.as_posix(), CONTEXT, "data/historical/VNINDEX.csv"]
    paths.extend(p.relative_to(root).as_posix() for p in sorted((root/"data/execution_prices_oos").rglob("*")) if p.is_file())
    identity = {"version": "utility_icl_validation_identity_v3", "source_commit": commit,
                "source_sha256": {name: file_hash(root/name) for name in CODE},
                "protocol_sha256": lock["protocol_sha256"], "protocol_lock_sha256": file_hash(root/"docs/plan/week11/protocol_lock_v3.json"),
                "contract_checks_sha256": file_hash(root/CHECKS),
                "input_sha256": {name: file_hash(root/name) for name in paths}, "runtime": protocol["runtime"],
                "candidate": protocol["candidate"], "cohort": rows, "query_outcomes_used": False,
                "development_allowed": False, "decision_calls_allowed": False, "confirmation_allowed": False}
    teacher = read_envelope(root/TEACHER/"teacher_fit.json", TEACHER_VERSION)
    regimes = FrozenRegimes(history, inherited["context"]["regime_models"], root/OUTPUT/"regime_models")
    return {"identity": identity, "protocol": protocol, "inherited": inherited, "bank": bank, "prices": prices,
            "history": history, "regimes": regimes, "pi": teacher["pi"], "cohort": rows}
