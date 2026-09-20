"""Đối chiếu bảng LaTeX với artefact TASK-08/09/10 và biên dịch bản thảo."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
ESWA_DIR = ROOT / "ESWA"
RESULTS_TEX = ESWA_DIR / "sections" / "06_backtest_results.tex"
BENCHMARK_DIR = ROOT / "backtest_result"
ROBUSTNESS_DIR = ROOT / "outputs" / "robustness" / "clean_a20"
ABLATION_DIR = ROOT / "outputs" / "ablation" / "clean_a20"
SYMBOLS = ("BHN", "CMG", "FPT", "HVN", "MBB", "MWG", "VCB", "VJC", "VNM")
BANNED_PHRASES = ("pending regeneration", "legacy sum", "unresolved issue")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _single_file(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    _require(len(matches) == 1, f"Cần đúng 1 file {pattern}, tìm thấy {len(matches)}")
    return matches[0]


def _signed(value: float, decimals: int = 1) -> str:
    return f"{value:+.{decimals}f}"


def _load_benchmarks() -> list[dict]:
    rows = []
    for symbol in SYMBOLS:
        path = _single_file(BENCHMARK_DIR, f"backtest_{symbol}_*.json")
        with path.open(encoding="utf-8", errors="replace") as handle:
            payload = json.load(handle)
        _require(payload["symbol"] == symbol, f"Sai symbol trong {path}")
        _require(payload["n_tests"] == 20, f"{symbol} không có đúng 20 test points")
        _require(len(payload["test_points"]) == 20, f"{symbol} thiếu test-point records")
        rows.append(payload)
    return rows


def _verify_benchmark_table(tex: str, rows: list[dict]) -> None:
    for row in rows:
        lo, hi = row["alpha_lift_ci_95"]
        directional = (
            f'{row["symbol"]} & {row["acc_full"]:.1f} & {row["acc_no_alpha"]:.1f} '
            f'& {_signed(row["alpha_lift"])} & '
            f'$[{_signed(lo)},{_signed(hi)}]$ & {row["mcnemar_p_value"]:.4f} & 20'
        )
        economic = (
            f'{row["symbol"]} & {_signed(row["pnl_full"], 2)} & '
            f'{_signed(row["pnl_no_alpha"], 2)} & '
            f'{_signed(row["sharpe_full"], 2)} & {_signed(row["sharpe_no_alpha"], 2)} & '
            f'{row["mdd_full"]:.2f} & {row["mdd_no_alpha"]:.2f}'
        )
        _require(directional in tex, f"Table 7 thiếu/sai hàng directional {row['symbol']}")
        _require(economic in tex, f"Table 7 thiếu/sai hàng economic {row['symbol']}")

    numeric_keys = (
        "acc_full",
        "acc_no_alpha",
        "alpha_lift",
        "pnl_full",
        "pnl_no_alpha",
        "sharpe_full",
        "sharpe_no_alpha",
        "mdd_full",
        "mdd_no_alpha",
    )
    means = {key: float(np.mean([row[key] for row in rows])) for key in numeric_keys}
    expected_directional_mean = (
        f'\\textbf{{Mean}} & \\textbf{{{means["acc_full"]:.1f}}} & '
        f'\\textbf{{{means["acc_no_alpha"]:.1f}}} & '
        f'\\textbf{{{_signed(means["alpha_lift"])}}}'
    )
    expected_economic_mean = (
        f'\\textbf{{Mean}} & \\textbf{{{_signed(means["pnl_full"], 2)}}} & '
        f'\\textbf{{{_signed(means["pnl_no_alpha"], 2)}}} & '
        f'\\textbf{{{_signed(means["sharpe_full"], 2)}}} & '
        f'\\textbf{{{_signed(means["sharpe_no_alpha"], 2)}}} & '
        f'\\textbf{{{means["mdd_full"]:.2f}}} & '
        f'\\textbf{{{means["mdd_no_alpha"]:.2f}}}'
    )
    _require(expected_directional_mean in tex, "Table 7 sai trung bình directional")
    _require(expected_economic_mean in tex, "Table 7 sai trung bình economic")


def _scenario_tex(panel: str, scenario: str) -> str:
    if panel == "hyperparams":
        return f"$W={int(scenario[1:])}$"
    return rf"\texttt{{{scenario.replace('_', r'\_')}}}"


def _load_robustness() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for panel in ("hyperparams", "norm", "weights"):
        for symbol in ("FPT", "VNM"):
            path = _single_file(ROBUSTNESS_DIR, f"sweep_{panel}_{symbol}_*.csv")
            with path.open(encoding="utf-8-sig", newline="") as handle:
                panel_rows = list(csv.DictReader(handle))
            _require(len(panel_rows) == 3, f"{path} phải có đúng 3 cấu hình")
            rows.extend(panel_rows)
    return rows


def _verify_robustness_table(tex: str, rows: list[dict[str, str]]) -> None:
    panel_name = {
        "hyperparams": "Window",
        "norm": "Normalisation",
        "weights": "Weighting",
    }
    controls: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for row in rows:
        expected = (
            f'{row["symbol"]} & {panel_name[row["panel"]]} & '
            f'{_scenario_tex(row["panel"], row["scenario"])} & '
            f'{float(row["acc_full"]):.1f} & {float(row["acc_no_alpha"]):.1f} & '
            f'{_signed(float(row["alpha_lift"]))} & '
            f'{_signed(float(row["pnl_full"]), 2)} & '
            f'{_signed(float(row["pnl_no_alpha"]), 2)}'
        )
        _require(expected in tex, f"Table 8 thiếu/sai {row['symbol']} {row['scenario']}")
        if row["panel"] in {"norm", "weights"}:
            controls[(row["symbol"], row["panel"])].add(
                (row["acc_no_alpha"], row["pnl_no_alpha"])
            )
    for key, values in controls.items():
        _require(len(values) == 1, f"No-Alpha không bất biến trong {key}: {values}")


def _load_ablation() -> list[dict[str, str]]:
    path = _single_file(ABLATION_DIR, "ablation_matrix_*.csv")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    _require(len(rows) == 12, "Ablation phải có 3 symbols x 4 variants")
    return rows


def _verify_ablation_table(tex: str, rows: list[dict[str, str]]) -> None:
    by_symbol = defaultdict(dict)
    for row in rows:
        by_symbol[row["symbol"]][row["variant"]] = row

    for symbol in ("FPT", "VNM", "VCB"):
        variants = by_symbol[symbol]
        _require(set(variants) == {"full", "alpha_only", "sentiment_only", "baseline"},
                 f"Thiếu ablation variant cho {symbol}")
        full = variants["full"]
        directional = (
            f'{symbol} & {float(full["accuracy"]):.1f}\\% & '
            f'{float(variants["alpha_only"]["accuracy"]):.1f}\\% & '
            f'{float(variants["sentiment_only"]["accuracy"]):.1f}\\% & '
            f'{float(variants["baseline"]["accuracy"]):.1f}\\% & '
            f'{_signed(float(full["alpha_contribution_pp"]))} pp & '
            f'{_signed(float(full["sentiment_contribution_pp"]))} pp & '
            f'{_signed(float(full["synergy_pp"]))} pp'
        )
        economic = (
            f'{symbol} & {_signed(float(full["account_return_pct"]), 2)}\\% & '
            f'{_signed(float(variants["alpha_only"]["account_return_pct"]), 2)}\\% & '
            f'{_signed(float(variants["sentiment_only"]["account_return_pct"]), 2)}\\% & '
            f'{_signed(float(variants["baseline"]["account_return_pct"]), 2)}\\%'
        )
        _require(directional in tex, f"Table 9 thiếu/sai directional {symbol}")
        _require(economic in tex, f"Table 9 thiếu/sai economic {symbol}")

    means = {}
    for variant in ("full", "alpha_only", "sentiment_only", "baseline"):
        means[variant] = np.mean(
            [float(by_symbol[symbol][variant]["accuracy"]) for symbol in ("FPT", "VNM", "VCB")]
        )
    full_rows = [by_symbol[symbol]["full"] for symbol in ("FPT", "VNM", "VCB")]
    expected_mean = (
        f'\\textbf{{Mean}} & \\textbf{{{means["full"]:.2f}\\%}} & '
        f'\\textbf{{{means["alpha_only"]:.2f}\\%}} & '
        f'\\textbf{{{means["sentiment_only"]:.2f}\\%}} & '
        f'\\textbf{{{means["baseline"]:.2f}\\%}} & '
        f'\\textbf{{{_signed(np.mean([float(r["alpha_contribution_pp"]) for r in full_rows]), 2)} pp}} & '
        f'\\textbf{{{_signed(np.mean([float(r["sentiment_contribution_pp"]) for r in full_rows]), 2)} pp}} & '
        f'\\textbf{{{_signed(np.mean([float(r["synergy_pp"]) for r in full_rows]), 2)} pp}}'
    )
    _require(expected_mean in tex, "Table 9 sai hàng Mean")


def _verify_document_hygiene() -> None:
    labels: dict[str, list[Path]] = defaultdict(list)
    for path in ESWA_DIR.rglob("*.tex"):
        content = path.read_text(encoding="utf-8")
        lowered = content.lower()
        for phrase in BANNED_PHRASES:
            _require(phrase not in lowered, f"Còn cụm từ cấm '{phrase}' trong {path}")
        _require(
            re.search(r"\b87(?:-candidate|-alpha|\s+alpha)", content, re.IGNORECASE) is None,
            f"Còn tuyên bố 87 alpha trong {path}",
        )
        for label in re.findall(r"\\label\{([^}]*)\}", content):
            _require(bool(label.strip()), f"LaTeX label rỗng trong {path}")
            labels[label].append(path)
    duplicates = {label: paths for label, paths in labels.items() if len(paths) > 1}
    _require(not duplicates, f"Trùng LaTeX label: {duplicates}")


def _run(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        tail = "\n".join(completed.stdout.splitlines()[-80:])
        raise RuntimeError(f"Lệnh {' '.join(command)} thất bại:\n{tail}")


def _find_latex_command(name: str) -> str | None:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidate = Path(local_app_data) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64" / f"{name}.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def _compile_pdf() -> None:
    pdflatex = _find_latex_command("pdflatex")
    _require(pdflatex is not None, "Không tìm thấy pdflatex trong PATH")
    base = [
        pdflatex,
        "-enable-installer",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "main.tex",
    ]
    _run(base, ESWA_DIR)
    bibtex = _find_latex_command("bibtex")
    if bibtex is not None:
        _run([bibtex, "main"], ESWA_DIR)
    _run(base, ESWA_DIR)
    _run(base, ESWA_DIR)
    pdf = ESWA_DIR / "main.pdf"
    _require(pdf.exists() and pdf.stat().st_size > 0, "Không tạo được ESWA/main.pdf")
    aux = (ESWA_DIR / "main.aux").read_text(encoding="utf-8", errors="replace")
    for label, number in (
        ("tab:overall_results", 7),
        ("tab:robustness_results", 8),
        ("tab:disentangled_ablation", 9),
    ):
        marker = rf"\newlabel{{{label}}}{{{{{number}}}"
        _require(marker in aux, f"{label} không được đánh số Table {number}")
    log = (ESWA_DIR / "main.log").read_text(encoding="utf-8", errors="replace")
    for failure in ("multiply-defined labels", "LaTeX Error"):
        _require(failure not in log, f"LaTeX log còn lỗi/cảnh báo bố cục: {failure}")
    overfull_widths = [
        float(match.group(1))
        for match in re.finditer(r"Overfull \\hbox \(([0-9.]+)pt too wide\)", log)
    ]
    _require(
        not overfull_widths or max(overfull_widths) <= 3.0,
        f"LaTeX có overfull hbox lớn hơn 3pt: {overfull_widths}",
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-compile",
        action="store_true",
        help="Chỉ đối chiếu số liệu và vệ sinh tài liệu, không gọi pdflatex.",
    )
    args = parser.parse_args()

    tex = RESULTS_TEX.read_text(encoding="utf-8")
    benchmarks = _load_benchmarks()
    robustness = _load_robustness()
    ablation = _load_ablation()
    _verify_benchmark_table(tex, benchmarks)
    _verify_robustness_table(tex, robustness)
    _verify_ablation_table(tex, ablation)
    _verify_document_hygiene()
    if not args.skip_compile:
        _compile_pdf()

    print(
        "PASS: Table 7/8/9 khớp artefact, tài liệu sạch, "
        + ("bỏ qua biên dịch theo yêu cầu." if args.skip_compile else "main.pdf biên dịch thành công.")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
