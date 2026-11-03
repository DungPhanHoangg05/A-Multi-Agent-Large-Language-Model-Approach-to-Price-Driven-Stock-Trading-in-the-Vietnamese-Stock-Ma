"""Đối soát fixture R12/R13 với classifier và Alpha_4, không gọi model hoặc đổi runtime."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import sys
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from agents.alpha_agent import _alpha4_bfe
from agents.indicator_agent import _classify_signals, create_indicator_agent
from core.alpha_compare import alpha_bfe
from utils.graph_util import TechnicalTools

FIXTURES = ROOT / "revision/indicator_alpha_cases.json"
OUTPUT = ROOT / "outputs/revision/indicator_alpha_rules_v1"
RUNTIME_SOURCES = ["agents/indicator_agent.py", "agents/alpha_agent.py", "agents/agent_state.py",
                   "agents/decision_agent.py", "core/alpha_compare.py", "utils/graph_util.py",
                   "utils/graph_setup.py", "utils/i18n.py", "utils/alpha_selector.py"]


def sha(path: Path) -> str:
    """Hash byte nguồn, không chuẩn hóa newline của bằng chứng cũ."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded(value: Any) -> bytes:
    """JSON chỉ chấp nhận số hữu hạn và kiểu Python nguyên bản."""
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def evaluate(cases: dict[str, Any]) -> dict[str, Any]:
    """Kiểm các expected outcomes đã khai báo, không fit hay chọn theo thị trường."""
    indicators = []
    for case in cases["indicators"]:
        result = _classify_signals(case["inputs"], {})
        observed = result[case["indicator"]]["signal"]
        if observed != case["expected"]:
            raise ValueError(f"Fixture không khớp: {case['id']}: {observed}")
        indicators.append({"id": case["id"], "indicator": case["indicator"], "expected": case["expected"], "observed": observed})
    consensus = []
    for case in cases["consensus"]:
        result = _classify_signals(case["inputs"], {})["__summary__"]
        if any(result[k] != v for k, v in case["expected"].items()):
            raise ValueError("Consensus fixture không khớp: " + case["id"])
        consensus.append({"id": case["id"], **result})
    alpha = []
    for case in cases["alpha4"]:
        result = _alpha4_bfe({"bb_pct_b": case["pct_b"], "vol_zscore_5": case["vol_z5"]}, "en")
        expected_value = round(math.tanh((case["pct_b"] - .5) * case["vol_z5"] * 1.5), 4)
        if result["signal"] != case["expected_signal"] or result["value"] != expected_value:
            raise ValueError("Alpha_4 fixture không khớp: " + case["id"])
        alpha.append({"id": case["id"], "pct_b": case["pct_b"], "vol_z5": case["vol_z5"],
                      "value": result["value"], "signal": result["signal"], "legacy_interpretation": result["interpretation"]})
    registry = []
    for case in cases["registry_alpha4"]:
        close = np.arange(100., 125.)
        volume = np.array([5.] * 20 + case["last_five_volume"])
        frame = pd.DataFrame({"Close": close, "volume": volume})
        observed = float(alpha_bfe(frame).iloc[-1])
        # Oracle dùng mảng cuối cửa sổ, độc lập với các rolling helper của registry.
        sigma = float(np.std(close[-20:], ddof=1))
        pct_b = (close[-1] - (float(np.mean(close[-20:])) - 2 * sigma)) / (4 * sigma)
        vol = volume[-5:]
        z = float((vol[-1] - np.mean(vol)) / np.std(vol, ddof=1))
        expected = math.tanh((pct_b - .5) * z * 1.5)
        if not math.isclose(observed, expected, abs_tol=1e-12) or int(np.sign(observed)) != case["expected_sign"]:
            raise ValueError("Registry Alpha_4 không khớp oracle: " + case["id"])
        registry.append({"id": case["id"], "value": observed, "expected_value": expected, "vol_z5": z})
    return {"indicator_cases": indicators, "consensus_cases": consensus, "alpha4_cases": alpha, "registry_cases": registry}


def audit_indicator_path() -> dict[str, Any]:
    """Chạy toolkit thật với frame tổng hợp; model giả sẽ báo lỗi nếu bị gọi."""
    close = np.linspace(100., 110., 45)
    kline = {"Close": close.tolist(), "Open": (close - .2).tolist(), "High": (close + 1).tolist(), "Low": (close - 1).tolist()}
    called: list[str] = []

    class Tool:
        """Ghi tên tool và chuyển nguyên tham số sang tool đang triển khai."""
        def __init__(self, name: str) -> None:
            self.name = name

        def invoke(self, args: dict[str, Any]) -> dict[str, Any]:
            called.append(self.name)
            return getattr(TechnicalTools, self.name).invoke(args)

    class NoModel:
        """Chặn mọi lời gọi model trong bằng chứng offline."""
        def invoke(self, *_: Any) -> None:
            raise AssertionError("Audit không được gọi model")

    names = ["compute_macd", "compute_rsi", "compute_roc", "compute_stoch", "compute_willr"]
    tools = SimpleNamespace(**{name: Tool(name) for name in names})
    with contextlib.redirect_stdout(io.StringIO()):
        result = create_indicator_agent(NoModel(), tools)({"kline_data": kline, "time_frame": "1d", "is_backtest": True, "language": "en"})
    if called != names or set(result) != {"messages", "indicator_report"}:
        raise ValueError("Đường Indicator không khớp năm tools/report-only contract")
    report = result["indicator_report"]
    if "5**" not in report or "SYSTEM" not in report:
        raise ValueError("Thiếu block phân loại/count trong report")
    return {"called_tools": called, "returned_keys": sorted(result), "report_chars": len(report),
            "report_sha256": hashlib.sha256(report.encode()).hexdigest(), "n_model_calls": 0,
            "bb_adx_in_consensus": False, "numeric_arrays_forwarded_by_indicator_node": False}


def generate() -> dict[str, bytes]:
    """Sinh kết quả số học và bảng dấu; không sửa artifacts hoặc prompts cũ."""
    bank = json.loads((ROOT / "outputs/revision/r4_value_bank_v1/manifest.json").read_bytes())
    frozen = {r["path"]: r["sha256"] for r in bank["source_hashes"]}
    for path in RUNTIME_SOURCES:
        if sha(ROOT / path) != frozen[path]:
            raise ValueError("Runtime/prompt nguồn không còn nguyên byte R4: " + path)
    cases = json.loads(FIXTURES.read_bytes())
    results = evaluate(cases)
    path = audit_indicator_path()
    rows = [r for r in results["alpha4_cases"] if r["pct_b"] in (.25, .5, .75) and r["vol_z5"] in (-1, 0, 1)]
    table = [r"\begin{table}[htbp]", r"\centering\small", r"\caption{Synthetic signed-volume examples for the unchanged custom $\alpha_4$.}",
             r"\label{tab:alpha4_signed_cases}", r"\begin{tabular}{rrrrl}\hline", r"$\%B$ & $\mathrm{VolZ}_5$ & Raw product & $\tanh(\mathrm{raw})$ & Signal \\\hline"]
    labels = {"TĂNG": "BULLISH", "GIẢM": "BEARISH", "TRUNG TÍNH": "NEUTRAL"}
    for r in rows:
        table.append(f"{r['pct_b']:.2f} & {r['vol_z5']:+.0f} & {(r['pct_b']-.5)*r['vol_z5']*1.5:+.3f} & {r['value']:+.4f} & {labels[r['signal']]} " + r"\\")
    table += [r"\hline\end{tabular}", r"\par\smallskip\footnotesize Arithmetic fixtures, not market observations or performance estimates. Signals use the prototype's strict $\pm0.10$ thresholds before value rounding. Negative volume z-scores reverse sign; zero volume z-score or $\%B=0.5$ suppresses the interaction. No band-width squeeze gate is present.", r"\end{table}", ""]
    report = {"counts": {key: len(value) for key, value in results.items()}, "indicator_path": path,
              "scoped_runtime_sources_unchanged_against_r4": True, "n_new_api_calls": 0,
              "limits": "Synthetic boundary evidence only; no new predictive/alpha claim. Prototype and registry use different preprocessing. Legacy breakout/flow names and language are identifiers, not proof of expansion, squeeze or measured order flow."}
    return {"cases.json": encoded(results), "report.json": encoded(report), "alpha4_signed_cases.tex": ("\n".join(table)).encode()}


def main() -> None:
    """Khóa release mới hoặc tái lập byte trên nguồn/runtime đã khóa."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    runtime = {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "talib": version("TA-Lib"), "langchain_core": version("langchain-core")}
    if OUTPUT.exists() and not args.check:
        raise FileExistsError("Release đã tồn tại; dùng --check")
    if args.check:
        manifest = json.loads((OUTPUT / "manifest.json").read_bytes())
        if manifest["runtime"] != runtime:
            raise ValueError("Runtime không khớp")
        for group, base in (("sources", ROOT), ("outputs", OUTPUT)):
            for record in manifest[group]:
                if sha(base / record["path"]) != record["sha256"]:
                    raise ValueError("Hash đã đổi: " + record["path"])
    outputs = generate()
    for name, content in outputs.items():
        if args.check:
            if (OUTPUT / name).read_bytes() != content:
                raise ValueError("Tái lập không khớp: " + name)
        else:
            OUTPUT.mkdir(exist_ok=True)
            (OUTPUT / name).write_bytes(content)
        if name.endswith(".tex"):
            dest = ROOT / "paper/generated" / name
            if args.check:
                if dest.read_bytes() != content:
                    raise ValueError("Bảng manuscript khác release")
            else:
                dest.write_bytes(content)
    if not args.check:
        sources = [*RUNTIME_SOURCES, "revision/indicator_alpha_cases.json", "scripts/audit_indicator_alpha_rules.py",
                   "tests/test_indicator_alpha_rules.py", "outputs/revision/r4_value_bank_v1/manifest.json"]
        manifest = {"schema_version": "indicator_alpha_rules_v1", "runtime": runtime, "sources": [{"path": p, "sha256": sha(ROOT / p)} for p in sources],
                    "outputs": [{"path": p, "sha256": sha(OUTPUT / p)} for p in outputs]}
        (OUTPUT / "manifest.json").write_bytes(encoded(manifest))
    print("PASS: fixture chỉ báo/Alpha_4, source R4 và ba outputs; không gọi API.")


if __name__ == "__main__":
    main()
