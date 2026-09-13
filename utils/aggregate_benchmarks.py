"""Tổng hợp chín backtest và xuất Table 7 kèm kiểm định Wilcoxon."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Dict, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.statistical_tests import (
    calculate_metrics_with_significance,
    newey_west_mean_test,
    paired_wilcoxon_test,
)


DEFAULT_SYMBOLS = ("BHN", "CMG", "FPT", "HVN", "MBB", "MWG", "VCB", "VJC", "VNM")


def _latest_result_path(input_dir: Path, symbol: str) -> Path:
    candidates = sorted(input_dir.glob(f"backtest_{symbol}_*.json"))
    direct_path = input_dir / f"backtest_{symbol}.json"
    if direct_path.exists():
        candidates.append(direct_path)
    if not candidates:
        raise FileNotFoundError(
            f"Không tìm thấy kết quả JSON cho {symbol} trong {input_dir}."
        )
    return max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))


def load_latest_results(
    input_dir: str | Path,
    symbols: Sequence[str] = DEFAULT_SYMBOLS,
) -> list[Dict[str, object]]:
    """Đọc kết quả mới nhất của từng mã và kiểm tra đủ dữ liệu bắt buộc."""

    directory = Path(input_dir)
    results = []
    for symbol in symbols:
        path = _latest_result_path(directory, symbol)
        with path.open("r", encoding="utf-8") as result_file:
            payload = json.load(result_file)
        required = {"acc_full", "acc_no_alpha"}
        missing = required.difference(payload)
        if missing:
            raise ValueError(f"{path} thiếu trường bắt buộc: {sorted(missing)}")
        missing_significance = (
            "mcnemar_p_value" not in payload
            or "alpha_lift_ci_95" not in payload
        )
        if missing_significance:
            test_points = payload.get("test_points", [])
            if test_points:
                significance = calculate_metrics_with_significance(
                    [point.get("actual_direction", "UNKNOWN") for point in test_points],
                    [point.get("pred_full", "UNKNOWN") for point in test_points],
                    [point.get("pred_no_alpha", "UNKNOWN") for point in test_points],
                )
                payload.setdefault(
                    "mcnemar_p_value", significance["mcnemar_p_value"]
                )
                payload.setdefault(
                    "alpha_lift_ci_95", significance["alpha_lift_ci_95"]
                )
        payload["symbol"] = str(payload.get("symbol") or symbol).upper()
        results.append(payload)
    return results


def _significance_marker(p_value: float) -> str:
    if p_value < 0.01:
        return "^{**}"
    if p_value < 0.05:
        return "^{*}"
    return ""


def render_table_7(
    results: Iterable[Dict[str, object]],
    wilcoxon_result: Dict[str, object],
) -> str:
    """Tạo bảng LaTeX Table 7 với CI và ký hiệu ý nghĩa thống kê."""

    rows = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Paired benchmark results with statistical significance}",
        r"\label{tab:paired_benchmark_significance}",
        r"\begin{tabular}{lrrrr}",
        r"\hline",
        r"Symbol & Full Acc. & No-$\alpha$ Acc. & Lift (95\% CI) & McNemar $p$ \\",
        r"\hline",
    ]
    for result in results:
        full_accuracy = float(result["acc_full"])
        no_alpha_accuracy = float(result["acc_no_alpha"])
        lift = float(result.get("alpha_lift", full_accuracy - no_alpha_accuracy))
        interval = result.get("alpha_lift_ci_95", [0.0, 0.0])
        lower, upper = (float(interval[0]), float(interval[1]))
        p_value = float(result.get("mcnemar_p_value", 1.0))
        marker = _significance_marker(p_value)
        rows.append(
            f"{result['symbol']} & {full_accuracy:.1f} & {no_alpha_accuracy:.1f} "
            f"& {lift:+.1f} [{lower:+.1f}, {upper:+.1f}] "
            f"& $" f"{p_value:.4f}{marker}$ \\\\"
        )

    overall_p = float(wilcoxon_result["p_value"])
    overall_marker = _significance_marker(overall_p)
    rows.extend(
        [
            r"\hline",
            f"Overall & -- & -- & -- & Wilcoxon $p={overall_p:.4f}{overall_marker}$ \\\\",
            r"\hline",
            r"\end{tabular}",
            r"\begin{flushleft}\footnotesize $^{*}p<0.05$, $^{**}p<0.01$.\end{flushleft}",
            r"\end{table}",
        ]
    )
    return "\n".join(rows)


def aggregate_benchmarks(
    input_dir: str | Path,
    symbols: Sequence[str] = DEFAULT_SYMBOLS,
) -> Dict[str, object]:
    """Tổng hợp Alpha Lift theo mã và tính p-value chung trên chín cặp."""

    results = load_latest_results(input_dir, symbols)
    lifts = [
        float(
            result.get(
                "alpha_lift",
                float(result["acc_full"]) - float(result["acc_no_alpha"]),
            )
        )
        for result in results
    ]
    wilcoxon_result = paired_wilcoxon_test(lifts)
    newey_west_result = newey_west_mean_test(lifts)
    return {
        "n_symbols": len(results),
        "symbols": [str(result["symbol"]) for result in results],
        "lifts_per_symbol": lifts,
        "wilcoxon": wilcoxon_result,
        "newey_west": newey_west_result,
        "latex_table": render_table_7(results, wilcoxon_result),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tổng hợp kết quả backtest và xuất Table 7 có kiểm định thống kê."
    )
    parser.add_argument("--input-dir", default="backtest_result")
    parser.add_argument("--output", help="Tệp .tex tùy chọn để lưu bảng LaTeX.")
    arguments = parser.parse_args()

    aggregate = aggregate_benchmarks(arguments.input_dir)
    wilcoxon_result = aggregate["wilcoxon"]
    print(
        "Wilcoxon signed-rank: "
        f"n={wilcoxon_result['n_symbols']}, p={wilcoxon_result['p_value']:.6f}"
    )
    print(aggregate["latex_table"])
    if arguments.output:
        Path(arguments.output).write_text(
            str(aggregate["latex_table"]), encoding="utf-8"
        )
        print(f"Đã lưu bảng LaTeX tại {arguments.output}")


if __name__ == "__main__":
    main()
