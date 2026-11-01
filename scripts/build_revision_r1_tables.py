"""Sinh các bảng R1 từ release JSON, giữ legacy và dữ liệu tái dựng tách biệt."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_revision_baselines import verify_bundle


def pct(value: float | None) -> str:
    """Đổi tỷ lệ 0–1 sang phần trăm và giữ NA cho metric không xác định."""
    return "NA" if value is None else f"{value * 100:.2f}"


def number(value: float | None) -> str:
    """Không biến null thành zero khi sinh LaTeX."""
    return "NA" if value is None else f"{value:.3f}"


def table(caption: str, label: str, header: str, alignment: str, rows: list[str], note: str) -> str:
    """Bố cục dùng chung cho các bảng nhỏ, không sửa số bằng tay."""
    return "\n".join([r"\begin{table}[!htb]", r"\centering", r"\small",
        rf"\caption{{{caption}}}", rf"\label{{{label}}}", r"\setlength{\tabcolsep}{6pt}",
        r"\renewcommand{\arraystretch}{1.12}", r"\setbox0=\hbox{%",
        rf"\begin{{tabular}}{{{alignment}}}", r"\hline", header + r" \\", r"\hline",
        *[row + r" \\" for row in rows], r"\hline", r"\end{tabular}}",
        r"\ifdim\wd0>0.98\textwidth\resizebox{0.98\textwidth}{!}{\copy0}\else\copy0\fi", r"\par\smallskip",
        r"\begin{minipage}{0.98\textwidth}\footnotesize " + note + r"\end{minipage}",
        r"\end{table}", ""])


def main() -> None:
    """Đối soát release trước khi đọc, chỉ ghi các bảng generated của bản thảo."""
    release = ROOT / "outputs/revision/r1_numeric_v1"
    verify_bundle(release)
    report = json.loads((release / "report.json").read_bytes())
    legacy = json.loads((release / "legacy_recomputed.json").read_bytes())
    models = json.loads((release / "models.json").read_bytes())
    import csv
    with (release / "summary.csv").open(encoding="utf-8", newline="") as handle:
        summary = list(csv.DictReader(handle))
    output = ROOT / "paper/generated"
    output.mkdir(exist_ok=True)
    names = {"full": "Full (legacy)", "base_reports_legacy": "Base reports (legacy)",
        "constant_down_cash": "Constant DOWN / CASH", "constant_up_cycles": "Always-LONG cycles",
        "train_majority": "Train majority", "momentum_20": "Momentum (20)",
        "logistic_price": "Logistic: price", "logistic_price_alpha_sentiment": "Logistic: price + factors + S/M",
        "factor_only_vote": "Factor-only vote", "train_momentum_exposure_control": "Train-rate random control",
        "continuous_hold_price_only": "Continuous hold (price only)"}
    rows = []
    for variant, metrics in legacy["pooled_classification"]["common_support"].items():
        rows.append(" & ".join([names[variant], str(metrics["n_valid"]), pct(metrics["accuracy"]),
            pct(metrics["balanced_accuracy"]), number(metrics["mcc"]), pct(metrics["macro_f1"]),
            pct(metrics["long_rate"]), f"{legacy['mean_independent_account_return_pct'][variant]:.2f}"]))
    (output / "r1_legacy_metrics.tex").write_text(table(
        "Legacy class-imbalance audit on the original 180 labels and cycle endpoints.", "tab:r1_legacy_metrics",
        r"Variant & $N$ & Acc. (\%) & BA (\%) & MCC & Macro-F1 (\%) & LONG (\%) & Mean return (\%)",
        "lrrrrrrr", rows, "Predictive metrics are pooled; return is the mean of nine independent accounts, "
        "not a pooled portfolio. UP/DOWN support is 56/124. Undefined values are NA. "
        "Always-LONG closes and reopens each cycle; it is not buy-and-hold."), encoding="utf-8", newline="\n")
    rows = []
    for variant, metrics in legacy["pooled_classification"]["common_support"].items():
        for label, values in metrics["per_class"].items():
            rows.append(" & ".join([names[variant], label, str(values["support"]), pct(values["precision"]),
                                     pct(values["recall"]), pct(values["f1"])]))
    (output / "r1_class_metrics.tex").write_text(table(
        "Per-class legacy precision, recall and F1, in percent.", "tab:r1_class_metrics",
        "Variant & Class & Support & Precision & Recall & F1", "llrrrr", rows,
        "A class with support but no predicted positives has undefined precision and zero recall/F1. "
        "All symbol-level confusion matrices and class metrics are retained in the reanalysis CSV/JSON."), encoding="utf-8", newline="\n")
    rows = []
    for variant, metrics in report["macro_over_symbols"].items():
        pooled = report["pooled_metrics"].get(variant, {})
        economics = [r for r in summary if r["variant"] == variant]
        rows.append(" & ".join([names[variant], pct(pooled.get("accuracy")), pct(pooled.get("balanced_accuracy")),
            number(pooled.get("mcc")), f"{metrics['net_return_pct']:.2f}",
            f"{sum(float(r['daily_close_drawdown_pct']) for r in economics)/len(economics):.2f}",
            f"{100*sum(float(r['held_session_fraction']) for r in economics)/len(economics):.2f}"]))
    (output / "r1_numeric_metrics.tex").write_text(table(
        "Exploratory numerical baselines on the newly retrieved snapshot: not a head-to-head comparison with legacy Full.",
        "tab:r1_numeric_metrics", r"Variant & Acc. (\%) & BA (\%) & MCC & Mean return (\%) & Mean daily MDD (\%) & Held sessions (\%)",
        "lrrrrrr", rows,
        "All cycle classifiers use the same 180 new-snapshot cutoffs and net targets. Predictive metrics are pooled; "
        "economic columns average independent symbol accounts. S/M denotes verified sentiment and missingness; "
        "historical scorer provenance is unavailable, so sentiment scores are missing. The train-rate control uses "
        "training momentum exposure, not Full exposure. Continuous hold has one buy and one sell per symbol; "
        "price adjustments and dividends are not independently certified. No Full row is included because 74 cycles "
        "differ at entry and/or exit from legacy, including two changed labels."), encoding="utf-8", newline="\n")
    rows = []
    for symbol, model in models.items():
        differences = [d for d in report["legacy_discrepancies"] if d["symbol"] == symbol]
        rows.append(" & ".join([symbol, str(model["n_train"]), str(model["n_validation"]), "20",
            str(len(differences)), str(sum("net_label" in d["fields"] for d in differences))]))
    (output / "r1_comparability.tex").write_text(table(
        "Training support and snapshot comparability audit.", "tab:r1_comparability",
        "Symbol & Train & Validation & Test & Different endpoints & Label changes", "lrrrrr", rows,
        "Each label exit precedes the next split's first decision. BHN uses a valid suffix beginning "
        "14 September 2022 after an unverified OHLC contradiction; raw data are preserved. All 20 test dates "
        "are retained for every symbol. Matching aggregate class counts does not establish matching labels or snapshots."), encoding="utf-8", newline="\n")
    print("Đã sinh bốn bảng R1 từ release đã đối soát hash.")


if __name__ == "__main__":
    main()
