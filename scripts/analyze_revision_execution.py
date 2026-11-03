"""Xuất D2-07 trên predictions cố định và source giá đã khóa, không gọi LLM."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from core.revision_baselines import load_prices
from core.revision_execution import execution_ledger
from scripts.analyze_revision_statistics import load_panel, VARIANTS
from scripts.finalize_revision_r1 import table

OUTPUT = ROOT / "outputs/revision/execution_sensitivity_v1"
POLICY = ROOT / "revision/r15_execution_policy.json"
BANK = ROOT / "outputs/revision/r1_72h_bank_v2"
ANALYSIS = ROOT / "outputs/revision/r1_72h_run_v2/analysis"


def read(path: Path) -> dict:
    """Đọc JSON không đổi nguồn."""
    return json.loads(path.read_bytes())


def sha(path: Path) -> str:
    """Hash byte gốc, không chuẩn hóa artifacts lịch sử."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_bytes(value: object) -> bytes:
    """Từ chối NaN/Infinity; không giấu undefined bằng zero."""
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def csv_bytes(rows: list[dict]) -> bytes:
    """CSV có NA cho null và JSON cho nested metadata."""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(k for r in rows for k in r)), lineterminator="\n", restval="NA")
    writer.writeheader()
    writer.writerows({k: "NA" if v is None else json.dumps(v) if isinstance(v, (dict, list)) else v
                     for k, v in r.items()} for r in rows)
    return stream.getvalue().encode("utf-8")


def generate() -> tuple[dict[str, bytes], list[Path]]:
    """Giữ toàn bộ scenario family và support; reference phải khớp 510 accounts."""
    policy = read(POLICY)
    scenario_ids = [r["id"] for r in policy["scenarios"]]
    if len(set(scenario_ids)) != len(scenario_ids) or "reference" not in scenario_ids:
        raise ValueError("Scenario identity trùng hoặc thiếu reference")
    bank = read(BANK / "manifest.json")
    protocol = bank["protocol"]
    main = read(ANALYSIS / "manifest.json")
    for path in (BANK / "manifest.json",):
        expected = next(r["sha256"] for r in main["sources"] if r["path"] == path.relative_to(ROOT).as_posix())
        if sha(path) != expected:
            raise ValueError("Bank đã đổi")
    rows, sources = load_panel()
    frames, _ = load_prices(ROOT / protocol["price_snapshot"], protocol["price_quality_policy"])
    economics = ANALYSIS / "economics.csv"
    expected = next(r["sha256"] for r in main["outputs"] if r["path"] == "economics.csv")
    if sha(economics) != expected:
        raise ValueError("Economics đã đổi")
    with economics.open(encoding="utf-8", newline="") as handle:
        reference = {(r["symbol"], r["fold"], r["variant"]): r for r in csv.DictReader(handle)}
    indexed = {(r["unit_id"], r["variant"]): r for r in rows}
    by_scope = defaultdict(list)
    for unit in bank["units"]:
        if str(frames[unit["symbol"]]["date"].iloc[unit["decision"]]) != unit["date"]:
            raise ValueError("Unit/calendar không khớp")
        by_scope[(unit["symbol"], unit["fold"])].append(unit)
    cases = []
    for (symbol, fold), units in sorted(by_scope.items()):
        units.sort(key=lambda u: u["decision"])
        for variant in VARIANTS:
            cycles = [(int(u["decision"] + 1), int(u["decision"] + 3),
                       int(indexed[(u["id"], variant)]["prediction"] == "LONG"), u["id"]) for u in units]
            cases.append((symbol, fold, variant, cycles))
        cases.append((symbol, fold, "continuous_hold_price_only",
                      [(int(units[0]["decision"] + 1), int(units[-1]["decision"] + 3), 1, f"hold_{symbol}_{fold}")]))
    if len(cases) != 510 or len(reference) != 510:
        raise ValueError("Không đủ 510 economic accounts")
    accounts, events, status_counts = [], [], Counter()
    daily_buffer = io.BytesIO()
    fields = ["scenario", "symbol", "fold", "variant", "date", "settled_cash_vnd", "pending_cash_vnd", "shares",
              "stock_mtm_vnd", "settled_shares", "unsettled_shares", "equity_vnd", "held_during_session", "brokerage_fee_vnd", "slippage_cost_vnd",
              "sell_charge_vnd", "advance_fee_vnd"]
    daily_count, verified = 0, 0
    with gzip.GzipFile(fileobj=daily_buffer, mode="wb", mtime=0) as compressed:
        with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for chosen in policy["scenarios"]:
                config = {**policy["defaults"], **chosen}
                for symbol, fold, variant, cycles in cases:
                    key = {"scenario": chosen["id"], "symbol": symbol, "fold": fold, "variant": variant}
                    result = execution_ledger(frames[symbol], cycles, config, protocol["initial_capital_vnd"], policy["price_multiplier"])
                    summary = result["summary"]
                    parent = reference[(symbol, fold, variant)]
                    if chosen["id"] == "reference":
                        for metric in ("net_return_pct", "daily_close_drawdown_pct", "order_count", "brokerage_fee_vnd", "slippage_cost_vnd"):
                            if not np.isclose(summary[metric], float(parent[metric]), atol=1e-5, rtol=1e-10):
                                raise ValueError("Reference ledger khác release: " + str((symbol, fold, variant, metric)))
                        verified += 1
                    accounts.append({**key, "n_units": len(by_scope[(symbol, fold)]), **summary,
                                     "reference_net_return_pct": float(parent["net_return_pct"]),
                                     "difference_from_reference_pp": summary["net_return_pct"] - float(parent["net_return_pct"])})
                    for row in result["events"]:
                        events.append({**key, **row})
                        status_counts[row["status"]] += 1
                    for row in result["daily"]:
                        writer.writerow({**key, **row})
                        daily_count += 1
                print(f"Đã tính scenario {chosen['id']}: 510 accounts trên cùng predictions.", flush=True)
    groups = []
    for chosen in policy["scenarios"]:
        for variant in (*VARIANTS, "continuous_hold_price_only"):
            selected = [r for r in accounts if r["scenario"] == chosen["id"] and r["variant"] == variant]
            groups.append({"scenario": chosen["id"], "variant": variant, "n_accounts": len(selected),
                           "n_units": sum(r["n_units"] for r in selected),
                           "mean_account_net_return_pct": float(np.mean([r["net_return_pct"] for r in selected])),
                           "mean_daily_close_drawdown_pct": float(np.mean([r["daily_close_drawdown_pct"] for r in selected])),
                           "mean_difference_from_reference_pp": float(np.mean([r["difference_from_reference_pp"] for r in selected])),
                           "buy_fills": sum(r["n_buy_fills"] for r in selected), "sell_fills": sum(r["n_sell_fills"] for r in selected),
                           "blocked_attempts": sum(r["n_blocked_attempts"] for r in selected),
                           "residual_stock_accounts": sum(not r["terminal_is_liquidated"] for r in selected),
                           "advance_fee_vnd": float(sum(r["advance_fee_vnd"] for r in selected))})
    if verified != 510 or len(accounts) != 510 * len(policy["scenarios"]):
        raise ValueError("Scenario coverage không đủ")
    by_account = {(r["scenario"], r["symbol"], r["fold"], r["variant"]): r for r in accounts}
    for symbol, fold, variant, _ in cases:
        lo, ref, hi = [by_account[(name, symbol, fold, variant)]["net_return_pct"]
                       for name in ("lower_cost", "reference", "higher_cost")]
        if not hi - 1e-9 <= ref <= lo + 1e-9:
            raise ValueError("Fixed-fill cost ordering không khớp")
    report = {"scope": "D2-07 post-inference execution sensitivities; no execution certification or R15 closure",
              "n_scenarios": len(policy["scenarios"]), "n_account_executions": len(accounts), "n_reference_accounts_reconciled": verified,
              "n_market_units": 102, "n_classification_predictions_unchanged": 918, "n_new_api_calls": 0, "n_new_predictions": 0,
              "n_event_records": len(events), "n_daily_records": daily_count, "event_status_counts": dict(status_counts),
              "support": "51 symbol-block accounts per variant, 102 units; continuous hold is one cycle per account, not always-LONG cycles",
              "event_clock_time": None, "timezone": "Asia/Ho_Chi_Minh",
              "main_cycle_spacing_observed_sessions": sorted({units[1]["decision"] - units[0]["decision"] for units in by_scope.values()}),
              "limits": policy["unverified"], "interpretation": policy["interpretation"]}
    rows_tex = []
    for chosen in policy["scenarios"]:
        values = {r["variant"]: r for r in groups if r["scenario"] == chosen["id"]}
        rows_tex.append(" & ".join([chosen["id"].replace("_", r"\_"),
            f"{values['B']['mean_account_net_return_pct']:.3f}", f"{values['AS']['mean_account_net_return_pct']:.3f}",
            f"{0. if abs(values['AS']['mean_difference_from_reference_pp']) < .0005 else values['AS']['mean_difference_from_reference_pp']:.3f}", str(values['AS']["buy_fills"]),
            str(values['AS']["residual_stock_accounts"])]) + r" \\")
    tex = table("Execution sensitivities on fixed Full/Base decisions (percent).", "tab:d207_execution", "lrrrrr",
                "Scenario & Base return & Full return & Full delta & Full BUY & Residual", rows_tex,
                "Returns average 51 separate symbol--block accounts, not a portfolio. Full delta is the change from the frozen reference, not predictive lift. Two decisions per account are 57 observed sessions apart, limiting information about fast cash reuse. Daily proxies do not identify price-limit queues or partial fills. Scenario rates, lots and participation are assumptions; source predictions, labels and L=3 remain fixed. Residual positions are MTM, not assumed liquidated. No profitability or execution-certification claim is made.")
    outputs = {"policy.json": json_bytes(policy), "report.json": json_bytes(report), "account_results.csv": csv_bytes(accounts),
               "scenario_summary.csv": csv_bytes(groups), "events.csv": csv_bytes(events),
               "daily_ledger.csv.gz": daily_buffer.getvalue(), "execution_table.tex": tex.encode("utf-8")}
    sources += [BANK / "manifest.json", economics, ROOT / protocol["price_snapshot"] / "manifest.json"]
    sources += sorted((ROOT / protocol["price_snapshot"]).glob("*.csv"))
    sources += [POLICY, ROOT / "core/revision_execution.py", Path(__file__).resolve(), ROOT / "tests/test_revision_execution.py",
                ROOT / "core/revision_baselines.py", ROOT / "scripts/analyze_revision_statistics.py",
                ROOT / "scripts/finalize_revision_r1.py"]
    return outputs, sorted(set(sources))


def main() -> None:
    """Release độc lập không ghi đè; --check đối soát hashes và tái lập toàn bộ."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if OUTPUT.exists() and not args.check:
        raise FileExistsError("Output đã có; dùng --check")
    checked = 0
    runtime = {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__}
    if args.check:
        manifest = read(OUTPUT / "manifest.json")
        if manifest["runtime"] != runtime:
            raise ValueError("Runtime không khớp")
        for group, base in (("sources", ROOT), ("outputs", OUTPUT)):
            for r in manifest[group]:
                if sha(base / r["path"]) != r["sha256"]:
                    raise ValueError("Hash đã đổi: " + r["path"])
                checked += 1
    outputs, sources = generate()
    for name, data in outputs.items():
        if args.check:
            if (OUTPUT / name).read_bytes() != data:
                raise ValueError("Không tái lập: " + name)
        else:
            OUTPUT.mkdir(exist_ok=True)
            (OUTPUT / name).write_bytes(data)
    if not args.check:
        manifest = {"schema_version": "execution_sensitivity_release_v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                    "runtime": runtime, "sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)} for p in sources],
                    "outputs": [{"path": name, "sha256": sha(OUTPUT / name)} for name in outputs]}
        (OUTPUT / "manifest.json").write_bytes(json_bytes(manifest))
    print(f"PASS D2-07: {len(outputs)} outputs, {checked} hashes khi kiểm lại; không gọi API.")


if __name__ == "__main__":
    main()
