"""Đối soát release thật và tái tạo bảng R1; không gọi API hoặc sửa analysis đã khóa."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.statistical_tests import binary_classification_metrics

ANALYSIS = ROOT / "outputs/revision/r1_72h_run_v2/analysis"
NUMERIC = ROOT / "outputs/revision/r1_72h_bank_v2/numeric"
RELEASE = ROOT / "outputs/revision/r1_manuscript_v2"
NAMES = {
    "AS": "Full (AS)", "B": "Base reports (B)",
    "constant_down_cash": "Constant CASH", "constant_up_cycles": "Always-LONG cycles",
    "train_majority": "Train majority", "momentum_20": "Momentum (20)",
    "logistic_price": "Logistic price", "logistic_matched_market_inputs": "Logistic market inputs",
    "factor_only_vote": "Factor vote", "continuous_hold_price_only": "Continuous hold",
}
ORDER = list(NAMES)


def load(path: Path) -> object:
    """Đọc JSON nghiêm ngặt, từ chối các hằng số không hữu hạn."""
    def invalid(value: str) -> None:
        raise ValueError(f"JSON không hữu hạn: {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)


def rows(path: Path) -> list[dict]:
    """Đọc CSV không làm đổi định dạng artifact nguồn."""
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def hashes(directory: Path) -> int:
    """Kiểm toàn bộ hash nguồn và đầu ra của manifest hiện có."""
    manifest = load(directory / "manifest.json")
    count = 0
    for kind, base in (("sources", ROOT), ("outputs", directory)):
        for record in manifest[kind]:
            path = base / record["path"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                # Numeric sinh trước amendment; source nguyên bản đã khóa trong ZIP.
                if directory != NUMERIC or kind != "sources" or record["path"] != "core/revision72_analysis.py":
                    raise ValueError(f"Hash không khớp: {path}")
                with zipfile.ZipFile(ROOT / "outputs/revision/r1_72h_run_v2/runtime_history/original_sources.zip") as archive:
                    if hashlib.sha256(archive.read(record["path"])).hexdigest() != record["sha256"]:
                        raise ValueError("Source numeric lịch sử không khớp archive")
            count += 1
    return count


def close(left: float, right: float) -> None:
    """Yêu cầu hai số khớp trong sai số biểu diễn CSV/JSON."""
    if not math.isfinite(left) or not math.isfinite(right) or abs(left - right) > 1e-9:
        raise ValueError(f"Số liệu không khớp: {left} != {right}")


def validate() -> tuple[list[dict], list[dict], list[dict]]:
    """Đối soát support, metrics, input, job coverage, panels và 510 daily ledgers."""
    count = hashes(ANALYSIS) + hashes(NUMERIC)
    report = load(ANALYSIS / "report.json")
    if not report["all_jobs_complete"] or report["actual_research_decisions"] != 474:
        raise ValueError("Inference chưa đủ 474 decisions")
    predictions, economics = rows(ANALYSIS / "predictions.csv"), rows(ANALYSIS / "economics.csv")
    classes = load(ANALYSIS / "classification.json")
    if len(predictions) != 918 or len(economics) != 510:
        raise ValueError("Thiếu predictions hoặc ledger")
    ids = {r["unit_id"] for r in predictions}
    if len(ids) != 102 or len({(r["unit_id"], r["variant"]) for r in predictions}) != 918:
        raise ValueError("Support trùng hoặc thiếu")
    for unit in ids:
        part = [r for r in predictions if r["unit_id"] == unit]
        for key in ("market_input_hash", "label_net", "label_gross", "date"):
            if len({r[key] for r in part}) != 1:
                raise ValueError(f"Đầu vào/target không chung: {unit}/{key}")
    for record in classes:
        group, value = record["group"], record["value"]
        part = [r for r in predictions if r["variant"] == record["variant"]]
        if group == "universe":
            part = [r for r in part if r["symbol"] != "BHN"] if value.startswith("eight_") else [r for r in part if r["fold"].startswith("f")]
        elif group != "ALL":
            part = [r for r in part if r[group] == value]
        actual = binary_classification_metrics([r["label_net"] for r in part], [r["prediction"] for r in part])
        if actual != record["metrics"]:
            raise ValueError(f"Metrics không replay được: {group}/{value}/{record['variant']}")
    for record in economics:
        variant = record["variant"]
        base = ANALYSIS if variant in ("AS", "B") else NUMERIC
        filename = f"{record['symbol']}_{record['fold']}_{'continuous_hold' if variant == 'continuous_hold_price_only' else variant}.csv"
        daily = rows(base / "daily" / filename)
        close((float(daily[-1]["equity_vnd"]) / 50_000_000 - 1) * 100, float(record["net_return_pct"]))
        n_long = sum(r["prediction"] == "LONG" for r in predictions if all(r[k] == record[k] for k in ("symbol", "fold", "variant")))
        if int(record["order_count"]) != (2 if variant == "continuous_hold_price_only" else 2 * n_long):
            raise ValueError("Số lệnh không khớp")
    for name, required in (("decision_panel.json", 18), ("upstream_panel.json", 9)):
        panel = load(ANALYSIS / name)
        if panel["n_complete_common_units"] != required or panel["n_planned_units"] != required:
            raise ValueError("Panel chưa đủ common support")
    print(f"PASS: {count} hashes; 918 predictions/189 metric groups/510 ledgers; panels 18/9 đủ.")
    return predictions, economics, classes


def fmt(value: float | None, percent: bool = True) -> str:
    """Giữ undefined là NA trong bảng."""
    return "NA" if value is None else f"{value * 100:.2f}" if percent else f"{value:.3f}"


def table(caption: str, label: str, columns: str, header: str, body: list[str], note: str) -> str:
    """Tạo bảng TeX gọn trong bề ngang trang."""
    return "\n".join([
        r"\begin{table}[htbp]", r"\centering\small", rf"\caption{{{caption}}}", rf"\label{{{label}}}",
        r"\setlength{\tabcolsep}{3.5pt}", rf"\begin{{tabular}}{{{columns}}}", r"\hline", header + r" \\",
        r"\hline", *body, r"\hline", r"\end{tabular}", rf"\par\smallskip\footnotesize {note}", r"\end{table}", "",
    ])


def artifacts(economics: list[dict], classes: list[dict]) -> dict[Path, str]:
    """Sinh bảng trình bày trực tiếp từ release đã kiểm; không fit hoặc chọn lại mẫu."""
    output: dict[Path, str] = {}
    pooled = {r["variant"]: r["metrics"] for r in classes if r["group"] == "ALL"}
    means = {v: sum(float(r["net_return_pct"]) for r in economics if r["variant"] == v) / sum(r["variant"] == v for r in economics) for v in ORDER}
    body = []
    for variant in ORDER:
        m = pooled.get(variant)
        cells = [fmt(m[k], k != "mcc") for k in ("accuracy", "balanced_accuracy", "mcc", "macro_f1", "long_rate")] if m else ["NA"] * 5
        body.append(" & ".join([NAMES[variant], *cells, f"{means[variant]:.2f}"]) + r" \\")
    output[ROOT / "paper/generated/r1_common_metrics.tex"] = table(
        "New common-snapshot comparison: 102 paired units, 25 UP and 77 DOWN net labels.", "tab:r1_common_metrics", "lrrrrrr",
        "Variant & Acc. & BA & MCC & Macro-F1 & LONG & Return", body,
        "Percentages except MCC; NA denotes undefined or inapplicable. Return is the mean over 51 independent symbol--block accounts, each with two cycles. Continuous hold buys once and sells once per account; its classification metrics are inapplicable. No joint portfolio or total-return claim is made.")
    body = []
    for variant in ORDER[:-1]:
        for label, m in pooled[variant]["per_class"].items():
            body.append(" & ".join([NAMES[variant], label, str(m["support"]), str(m["predicted"]), *[fmt(m[k]) for k in ("precision", "recall", "f1")]]) + r" \\")
    output[ROOT / "paper/generated/r1_common_classes.tex"] = table(
        "Both-class pooled metrics on the same 102 units.", "tab:r1_common_classes", "llrrrrr",
        "Variant & Class & Support & Predicted & Precision & Recall & F1", body,
        "Precision, recall and F1 are percentages. Support counts outcomes; Predicted counts calls for that class. Precision with no predicted class is NA.")
    body = []
    for filename, prefix in (("decision_panel.json", "Decision"), ("upstream_panel.json", "Upstream")):
        panel = load(ANALYSIS / filename)
        for r in panel["results"]:
            ba = r["dispersion"]["balanced_accuracy"]
            body.append(" & ".join([prefix, r["variant"], str(panel["n_complete_common_units"]), fmt(ba["mean"]), fmt(ba["sd"]), fmt(r["dispersion"]["long_rate"]["mean"]), fmt(r["pairwise_disagreement"])]) + r" \\")
    output[ROOT / "paper/generated/r1_common_panels.tex"] = table(
        "Preselected repeated panels: three executions per variant.", "tab:r1_common_panels", "llrrrrr",
        "Panel & Variant & Units & Mean BA & SD (pp) & Mean LONG & Disagree", body,
        "Decision panel: 18 units, eight symbols, five dates, three blocks; shared upstream is fixed. Upstream panel: nine units, nine symbols, three dates, three blocks; upstream is regenerated. Disagree is mean pairwise prediction disagreement in percent. Dispersion applies only to each selected panel, not to all 102 units.")
    body = []
    for r in load(ANALYSIS / "block_intervals.json"):
        other = r["contrast"][3:]
        delta = pooled["AS"]["balanced_accuracy"] - pooled[other]["balanced_accuracy"]
        lo, hi = r["percentile_95"]
        body.append(f"Full minus {NAMES[other]} & {delta*100:.2f} & [{lo*100:.2f}, {hi*100:.2f}]" + r" \\")
    output[ROOT / "paper/generated/r1_common_intervals.tex"] = table(
        "Paired balanced-accuracy contrasts, percentage points.", "tab:r1_common_intervals", "lrr",
        "Contrast & Difference & Descriptive 95\\% interval", body,
        "10,000 joint cross-sectional six-block bootstrap resamples, seed 20261102. Only six historical blocks are available; intervals are descriptive and are not a power or superiority guarantee.")
    body = []
    for r in load(ANALYSIS / "macro_by_symbol.json"):
        m = r["metrics"]
        cells = [NAMES[r["variant"]], fmt(m["accuracy"]["mean"]), fmt(m["balanced_accuracy"]["mean"]), str(m["balanced_accuracy"]["n_defined"]), fmt(m["mcc"]["mean"], False), str(m["mcc"]["n_defined"]), fmt(m["long_rate"]["mean"])]
        body.append(" & ".join(cells) + r" \\")
    output[ROOT / "paper/generated/r1_common_macro.tex"] = table(
        "Equal-symbol macro means, with defined denominators out of nine symbols.", "tab:r1_common_macro", "lrrrrrr",
        "Variant & Acc. & BA & Defined BA & MCC & Defined MCC & LONG", body,
        "Percentages except MCC. Means omit undefined symbol metrics; defined counts are shown. BHN has six observations in three blocks; the other eight symbols have twelve in six blocks. This differs from pooled weighting.")
    body = []
    for group in ("fold", "regime"):
        for value in sorted({r["value"] for r in classes if r["group"] == group}):
            for variant in ("AS", "B", "constant_down_cash", "logistic_price"):
                m = next(r["metrics"] for r in classes if r["group"] == group and r["value"] == value and r["variant"] == variant)
                body.append(" & ".join([value.replace("_", r"\_"), NAMES[variant], str(m["n_valid"]), str(m["per_class"]["UP"]["support"]), fmt(m["accuracy"]), fmt(m["balanced_accuracy"]), fmt(m["mcc"], False)]) + r" \\")
    output[ROOT / "paper/generated/r1_common_strata.tex"] = appendix_tables(
        "Full, Base, CASH and price logistic by historical block and causal regime.", "tab:r1_common_strata", "llrrrrr",
        "Stratum & Variant & N & UP & Acc. & BA & MCC", body)
    by_symbol = []
    symbol_classes = {(r["value"], r["variant"]): r["metrics"] for r in classes if r["group"] == "symbol"}
    body = []
    for symbol in sorted({r["symbol"] for r in economics}):
        for variant in ORDER:
            part = [r for r in economics if r["symbol"] == symbol and r["variant"] == variant]
            mean_return = sum(float(r["net_return_pct"]) for r in part) / len(part)
            m = symbol_classes.get((symbol, variant))
            record = {"symbol": symbol, "variant": variant, "n_accounts": len(part), "mean_net_return_pct": mean_return}
            if m:
                record.update({k: m[k] for k in ("n_valid", "accuracy", "balanced_accuracy", "mcc", "macro_f1", "long_rate")})
                record.update(m["confusion"])
                for label, details in m["per_class"].items():
                    record.update({f"{label.lower()}_{k}": v for k, v in details.items()})
            by_symbol.append(record)
            cells = [symbol, NAMES[variant], str(m["n_valid"]) if m else "NA", str(m["per_class"]["UP"]["support"]) if m else "NA"]
            cells += [fmt(m[k], k != "mcc") if m else "NA" for k in ("accuracy", "balanced_accuracy", "mcc", "long_rate")]
            body.append(" & ".join([*cells, f"{mean_return:.2f}"]) + r" \\")
    output[ROOT / "paper/generated/r1_common_symbols.tex"] = appendix_tables(
        "Every baseline by symbol on common support; percentages except MCC.", "tab:r1_common_symbols", "llrrrrrrr",
        "Symbol & Variant & N & UP & Acc. & BA & MCC & LONG & Return", body)
    output[RELEASE / "baseline_by_symbol.csv"] = csv_text(by_symbol)
    flattened = []
    for r in classes:
        m = r["metrics"]
        for label, details in m["per_class"].items():
            flattened.append({"variant": r["variant"], "group": r["group"], "value": r["value"], "class": label,
                              "n_valid": m["n_valid"], **m["confusion"], **details})
    output[RELEASE / "per_class_all_groups.csv"] = csv_text(flattened)
    return output


def appendix_tables(caption: str, label: str, columns: str, header: str, body: list[str]) -> str:
    """Chia bảng tại biên mã/block, tránh chia nhóm hoặc co chữ trên một trang."""
    size = 24 if label.endswith("strata") else 30
    chunks = [body[i:i + size] for i in range(0, len(body), size)]
    return "\n".join(table(
        f"{caption} (Part {i + 1} of {len(chunks)}.)",
        label if i == 0 else f"{label}_{i+1}", columns, header, chunk,
        "NA denotes undefined or inapplicable; all variants use common support.")
        for i, chunk in enumerate(chunks))


def csv_text(records: list[dict]) -> str:
    """Xuất CSV native, giữ undefined là NA."""
    handle = io.StringIO(newline="")
    fields = list(dict.fromkeys(k for r in records for k in r))
    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", restval="NA")
    writer.writeheader()
    writer.writerows({k: "NA" if v is None else v for k, v in r.items()} for r in records)
    return handle.getvalue()


def main() -> None:
    """Xuất hoặc kiểm bảng, chỉ trong phạm vi tài liệu R1."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    _, economics, classes = validate()
    generated = artifacts(economics, classes)
    for path, content in generated.items():
        if args.check:
            if path.read_bytes() != content.encode("utf-8"):
                raise ValueError(f"Bảng/CSV không khớp nguồn: {path}")
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
    print(f"PASS: {len(generated)} bảng/CSV {'khớp nguồn' if args.check else 'đã xuất'}; không gọi API.")


if __name__ == "__main__":
    main()
