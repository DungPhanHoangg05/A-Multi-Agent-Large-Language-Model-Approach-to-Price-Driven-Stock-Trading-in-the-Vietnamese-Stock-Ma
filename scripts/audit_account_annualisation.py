"""Đối soát D2-06 trên cycle legacy và daily ledger đã lưu, không dựng lại ledger."""

from __future__ import annotations

import argparse
import ast
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from core.revision_baselines import load_prices
from scripts.finalize_revision_r1 import table
from utils.account_risk import risk_ratios

OUTPUT = ROOT / "outputs/revision/account_annualisation_v1"
ANALYSIS = ROOT / "outputs/revision/r1_72h_run_v2/analysis"
BASE_COMMIT = "c801af51"
SOURCE_FILES = ("core/backtest_engine.py", "core/run_robustness.py", "scripts/run_ablation_matrix.py")


def sha(path: Path) -> str:
    """Hash byte nguyên bản của nguồn/ledger."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    """Đọc JSON mà không sửa bằng chứng."""
    return json.loads(path.read_bytes())


def json_text(value: object) -> str:
    """Không cho NaN/Infinity lọt vào output."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def csv_text(rows: list[dict]) -> str:
    """Đổi null thành NA và giữ metadata lồng nhau dạng JSON hợp lệ."""
    handle = io.StringIO(newline="")
    fields = list(dict.fromkeys(k for row in rows for k in row))
    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows({k: "NA" if v is None else json.dumps(v) if isinstance(v, (list, dict)) else v
                     for k, v in row.items()} for row in rows)
    return handle.getvalue()


def before_sources() -> tuple[dict[str, bytes], str]:
    """Giữ source trước task, không suy commit thực thi của inference lịch sử."""
    commit = subprocess.check_output(["git", "rev-parse", BASE_COMMIT], cwd=ROOT, text=True).strip()
    return {p: subprocess.check_output(["git", "show", f"{commit}:{p}"], cwd=ROOT) for p in SOURCE_FILES}, commit


def economics_ast_check(before: bytes, after: bytes) -> dict:
    """Chứng minh phần mua/bán/fees/wealth/label/parser không đổi, bỏ riêng risk block."""
    def nodes(source: bytes) -> dict[str, ast.AST]:
        return {n.name: n for n in ast.walk(ast.parse(source)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    old, new = nodes(before), nodes(after)
    def target(statement: ast.AST, name: str) -> bool:
        return isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in statement.targets)
    def part(body: list[ast.stmt], start: str | None, stop: str | None) -> str:
        left = next(i for i, n in enumerate(body) if target(n, start)) if start else 0
        right = next(i for i, n in enumerate(body) if target(n, stop)) if stop else next(i for i, n in enumerate(body) if isinstance(n, ast.Return))
        return ast.dump(ast.Module(body=body[left:right], type_ignores=[]), include_attributes=False)
    matched = {"buy_sell_fees_wealth_and_point_updates": part(old["compute_variant"].body, None, "returns_array") ==
               part(new["compute_variant"].body, None, "frequency"),
               "drawdown_hit_rate_and_average_trade": part(old["compute_variant"].body, "equity_array", None) ==
               part(new["compute_variant"].body, "equity_array", None)}
    for name in ("_validate_account_costs", "compute_round_trip_net_return", "_get_actual_direction", "_parse_prediction", "_run_ablation_variants", "_run_paired_point"):
        matched[name] = ast.dump(old[name], include_attributes=False) == ast.dump(new[name], include_attributes=False)
    if not all(matched.values()):
        raise ValueError("Task đã đổi phần kinh tế/inference ngoài annualisation: " + str(matched))
    return matched


def daily_returns(equity: list[float], initial: float) -> np.ndarray:
    """Dùng cả return ngày đầu so với initial capital và giữ mọi CASH gap zero."""
    values = np.asarray([initial, *equity], dtype=float)
    if len(values) < 2 or not np.all(np.isfinite(values)) or np.any(values <= 0):
        raise ValueError("Daily equity/initial capital phải dương hữu hạn")
    return values[1:] / values[:-1] - 1


def generate() -> tuple[dict[str, bytes], list[Path]]:
    """Thêm risk report riêng; không sửa CSV daily, raw predictions hoặc nhãn cũ."""
    before, commit = before_sources()
    ast_check = economics_ast_check(before["core/backtest_engine.py"], (ROOT / "core/backtest_engine.py").read_bytes())
    snapshot = io.BytesIO()
    with zipfile.ZipFile(snapshot, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(before.items()):
            info = zipfile.ZipInfo(path, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    bank_path = ROOT / "outputs/revision/r1_72h_bank_v2/manifest.json"
    protocol = read(bank_path)["protocol"]
    frames, _ = load_prices(ROOT / protocol["price_snapshot"], protocol["price_quality_policy"])
    legacy_manifest = ROOT / "outputs/revision/legacy_lineage_v1/manifest.json"
    sources = [bank_path, legacy_manifest, ANALYSIS / "manifest.json", ANALYSIS / "economics.csv"]
    sources += sorted((ROOT / protocol["price_snapshot"]).glob("*.csv"))
    sources.append(ROOT / protocol["price_snapshot"] / "manifest.json")
    records = [r for r in read(legacy_manifest)["sources"] if r["path"].startswith("outputs/backtest_result/") and r["path"].endswith(".json")]
    legacy, calendars = [], []
    for record in records:
        path = ROOT / record["path"]
        if sha(path) != record["sha256"]:
            raise ValueError("Legacy source đã đổi")
        sources.append(path)
        value = read(path)
        frame = frames[value["symbol"]]
        lookup = {str(day): i for i, day in enumerate(frame["date"])}
        pairs, mismatch = [], 0
        for point in value["test_points"]:
            a = lookup[pd.Timestamp(point["entry_time"]).date().isoformat()]
            b = lookup[pd.Timestamp(point["exit_time"]).date().isoformat()]
            pairs.append((a, b))
            mismatch += int(not np.isclose(frame["Open"].iloc[a], point["entry_open"], atol=1e-8, rtol=0) or
                            not np.isclose(frame["Close"].iloc[b], point["exit_close"], atol=1e-8, rtol=0))
        calendars.append({"symbol": value["symbol"], "n_cycles": len(pairs),
                          "observed_calendar_spans": sorted({b - a + 1 for a, b in pairs}),
                          "observed_calendar_steps": sorted({pairs[i][0] - pairs[i - 1][0] for i in range(1, len(pairs))}),
                          "n_price_mismatches_with_current_snapshot": mismatch,
                          "historical_snapshot_authenticated": False})
        for variant, suffix in (("full", "full"), ("base_reports", "no_alpha")):
            returns = [float(p[f"account_return_{suffix}"]) / 100 for p in value["test_points"]]
            old = risk_ratios(returns, 252)
            conditional = risk_ratios(returns, 84)
            for metric in ("sharpe", "sortino"):
                old_value = old[f"{metric}_ratio"]
                if old_value is not None and not np.isclose(round(old_value, 2), value[f"{metric}_{suffix}"], atol=.011, rtol=0):
                    raise ValueError("Legacy risk arithmetic không khớp stored value")
            legacy.append({"symbol": value["symbol"], "variant": variant, "n_cycles": len(returns),
                "n_long_cycles": sum(p[f"pred_{suffix}"] == "LONG" for p in value["test_points"]),
                "stored_sharpe": value[f"sharpe_{suffix}"], "stored_sortino": value[f"sortino_{suffix}"],
                "recomputed_wrong_252_sharpe": old["sharpe_ratio"], "recomputed_wrong_252_sortino": old["sortino_ratio"],
                "conditional_declared_3_session_sharpe": conditional["sharpe_ratio"],
                "conditional_declared_3_session_sortino": conditional["sortino_ratio"],
                "authenticated_annualised_sharpe": None, "authenticated_annualised_sortino": None,
                "frequency_status": "unverified_legacy_bar_index_and_snapshot_provenance",
                "drawdown_basis": "cycle_end", "risk_convention": conditional["downside_convention"]})
    main_manifest = read(ANALYSIS / "manifest.json")
    numeric = ROOT / "outputs/revision/r1_72h_bank_v2/numeric"
    numeric_manifest = numeric / "manifest.json"
    for required in (bank_path, numeric_manifest):
        relative = required.relative_to(ROOT).as_posix()
        expected = next(r["sha256"] for r in main_manifest["sources"] if r["path"] == relative)
        if sha(required) != expected:
            raise ValueError("Bank/manifest đã đổi: " + relative)
    sources.append(numeric_manifest)
    with (ANALYSIS / "economics.csv").open(encoding="utf-8", newline="") as handle:
        economics = list(csv.DictReader(handle))
    expected_economics = next(r["sha256"] for r in main_manifest["outputs"] if r["path"] == "economics.csv")
    if sha(ANALYSIS / "economics.csv") != expected_economics:
        raise ValueError("Economics đã đổi")
    ledger_paths = {r["path"]: (base / r["path"], r["sha256"])
                    for base, manifest in ((ANALYSIS, main_manifest), (numeric, read(numeric_manifest)))
                    for r in manifest["outputs"] if r["path"].startswith("daily/")}
    daily = []
    for row in economics:
        # Tên hiển thị R1 phân biệt price-only; file ledger đã khóa dùng tên cũ.
        ledger_variant = "continuous_hold" if row["variant"] == "continuous_hold_price_only" else row["variant"]
        name = f"daily/{row['symbol']}_{row['fold']}_{ledger_variant}.csv"
        path, expected = ledger_paths[name]
        if sha(path) != expected:
            raise ValueError("Daily ledger đã đổi")
        sources.append(path)
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        dates = [r["date"] for r in rows]
        if dates != sorted(set(dates)):
            raise ValueError("Ngày ledger thiếu thứ tự hoặc trùng")
        equity = [float(r["equity_vnd"]) for r in rows]
        returns = daily_returns(equity, protocol["initial_capital_vnd"])
        if not np.isclose((equity[-1] / protocol["initial_capital_vnd"] - 1) * 100, float(row["net_return_pct"]), atol=1e-10):
            raise ValueError("Return ledger và economics không khớp")
        daily.append({"symbol": row["symbol"], "fold": row["fold"], "variant": row["variant"],
                      "return_basis": "stored_daily_close_mtm_including_cash_gaps", "first_date": dates[0], "last_date": dates[-1],
                      "n_zero_returns": int(np.count_nonzero(returns == 0)),
                      "daily_drawdown_pct_unchanged": float(row["daily_close_drawdown_pct"]),
                      **risk_ratios(returns.tolist(), 252)})
    if len(records) != 9 or len(daily) != 510 or len(ledger_paths) != 510:
        raise ValueError("Support audit không đủ 9 legacy/510 daily accounts")
    report = {"scope": "D2-06 frequency correction; no ledger reconstruction, prediction or target changes",
              "base_source_commit": commit, "base_is_not_historical_execution_commit": True,
              "economics_and_inference_ast_unchanged": ast_check,
              "n_legacy_accounts": len(legacy), "n_daily_accounts": len(daily),
              "n_daily_sharpe_defined": sum(r["sharpe_ratio"] is not None for r in daily),
              "n_daily_sortino_defined": sum(r["sortino_ratio"] is not None for r in daily),
              "n_new_api_calls": 0, "n_new_predictions": 0,
              "risk_free_and_mar": 0, "sd_ddof": 0,
              "downside_convention": "population SD negative subset retained from legacy; not downside RMS",
              "daily_frequency_assumption": "252 observed vendor daily bars/year; no exchange-session certification; CASH gaps retained",
              "legacy_policy": "sqrt(84) outputs are conditional on declared S=L=3; original snapshot/bar-index provenance unavailable; authenticated ratios remain null",
              "limits": "few trades; daily series are sparse evaluated accounts, not a pooled portfolio or profitability evidence; source PDFs remain historical until manuscript integration"}
    def fmt(v: float | None) -> str:
        return "NA" if v is None else f"{v:.3f}"
    body = [" & ".join([r["symbol"], "Full" if r["variant"] == "full" else "Base", str(r["n_long_cycles"]),
            fmt(r["stored_sharpe"]), fmt(r["conditional_declared_3_session_sharpe"]), fmt(r["stored_sortino"]),
            fmt(r["conditional_declared_3_session_sortino"])]) + r" \\" for r in legacy]
    tex = table("Legacy cycle ratios under the declared three-session assumption.", "tab:d206_cycle_risk", "llrrrrr",
                "Symbol & Variant & LONG & Stored SR & Conditional SR & Stored Sortino & Conditional Sortino", body,
                "Conditional columns use saved cycle returns (rather than rounded ratios) and the declared scale $\\sqrt{252/3}$, not $\\sqrt{252}$. They do not authenticate the legacy snapshot or bar schedule. SD is population SD; the Sortino-like diagnostic retains negative-subset population SD, not downside RMS; risk-free/MAR are zero. Original values/artifacts remain unchanged. Few LONG cycles preclude a profitability claim; daily ratios from existing ledgers are reported separately.")
    outputs = {"report.json": json_text(report).encode("utf-8"), "legacy_cycle_ratios.csv": csv_text(legacy).encode("utf-8"),
               "calendar_crosscheck.csv": csv_text(calendars).encode("utf-8"), "daily_risk_ratios.csv": csv_text(daily).encode("utf-8"),
               "cycle_risk_table.tex": tex.encode("utf-8"), "before_sources.zip": snapshot.getvalue()}
    return outputs, sources


def main() -> None:
    """Khóa output mới hoặc kiểm source/runtime và tái lập nguyên byte."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if OUTPUT.exists() and not args.check:
        raise FileExistsError("Release đã có; dùng --check")
    checked = 0
    runtime = {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__}
    if args.check:
        manifest = read(OUTPUT / "manifest.json")
        if manifest["runtime"] != runtime:
            raise ValueError("Runtime khác release")
        for group, base in (("sources", ROOT), ("outputs", OUTPUT)):
            for record in manifest[group]:
                if sha(base / record["path"]) != record["sha256"]:
                    raise ValueError("Hash đã đổi: " + record["path"])
                checked += 1
    outputs, sources = generate()
    for name, data in outputs.items():
        if args.check:
            if (OUTPUT / name).read_bytes() != data:
                raise ValueError("Tái lập không khớp: " + name)
        else:
            OUTPUT.mkdir(exist_ok=True)
            (OUTPUT / name).write_bytes(data)
    if not args.check:
        sources += [ROOT / p for p in (*SOURCE_FILES, "utils/account_risk.py", "scripts/audit_account_annualisation.py",
                    "tests/test_account_risk.py", "tests/test_account_pnl.py", "tests/test_ablation_matrix.py",
                    "tests/test_robustness_sweep.py", "tests/test_significance.py", "tests/test_revision_baselines.py",
                    "core/revision_baselines.py", "scripts/finalize_revision_r1.py")]
        manifest = {"schema_version": "account_annualisation_release_v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                    "runtime": runtime, "sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)} for p in sorted(set(sources))],
                    "outputs": [{"path": n, "sha256": sha(OUTPUT / n)} for n in outputs]}
        (OUTPUT / "manifest.json").write_text(json_text(manifest), encoding="utf-8", newline="\n")
    print(f"PASS D2-06: {len(outputs)} outputs; {checked} hashes khi kiểm lại; 510 daily ledgers giữ nguyên.")


if __name__ == "__main__":
    main()
