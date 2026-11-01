"""Xuất audit R1 offline cùng hash bằng chứng, không ghi đè artifacts cũ."""

from __future__ import annotations

import argparse
import csv
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.revision_audit import DEFAULT_SYMBOLS, VARIANTS, build_legacy_report, sha256_file


def _json(payload: object) -> str:
    """Xuất JSON chuẩn, từ chối NaN/Infinity thay vì che bằng encoder tùy biến."""
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def classification_csv(report: dict[str, Any]) -> str:
    """Xuất pooled, từng mã và groups thực có, kèm common/own support."""
    buffer = StringIO(newline="")
    fields = ["scope", "symbol", "dimension", "group", "support_policy", "variant",
              "n_input", "n_valid", "n_excluded", "tp", "fn", "tn", "fp",
              "accuracy", "balanced_accuracy", "mcc", "macro_f1", "long_rate",
              "support_up", "support_down", "precision_up", "recall_up", "f1_up",
              "precision_down", "recall_down", "f1_down"]
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    scopes = [("pooled", "ALL", "", "", report["pooled_classification"])]
    scopes.extend(("symbol", s, "", "", r["classification"]) for s, r in report["per_symbol"].items())
    scopes.extend(("group", g["symbol"], g["dimension"], g["value"], g["classification"])
                  for g in report["groups"])
    for scope, symbol, dimension, group, classification in scopes:
        for policy in ("common_support", "own_support"):
            for variant in VARIANTS:
                metrics = classification[policy][variant]
                row = {"scope": scope, "symbol": symbol, "dimension": dimension, "group": group,
                       "support_policy": policy, "variant": variant,
                       **{k: metrics[k] for k in ("n_input", "n_valid", "n_excluded", "accuracy",
                           "balanced_accuracy", "mcc", "macro_f1", "long_rate")}, **metrics["confusion"]}
                for label in ("UP", "DOWN"):
                    for key in ("support", "precision", "recall", "f1"):
                        row[f"{key}_{label.lower()}"] = metrics["per_class"][label][key]
                writer.writerow({k: "NA" if v is None else v for k, v in row.items()})
    return buffer.getvalue()


def economics_csv(report: dict[str, Any]) -> str:
    """Xuất tài khoản độc lập; tỷ lệ chu kỳ LONG không đổi tên thành daily exposure."""
    buffer = StringIO(newline="")
    fields = ["symbol", "variant", "status", "n_cycles", "long_cycles", "order_count",
              "long_cycle_fraction", "net_return_pct", "cycle_end_drawdown_pct",
              "brokerage_fee_vnd", "slippage_cost_vnd", "gross_traded_notional_vnd",
              "traded_notional_over_initial_capital", "daily_exposure", "daily_turnover", "daily_drawdown_pct"]
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for symbol, record in report["per_symbol"].items():
        for variant, economic in record["economics"].items():
            row = {"symbol": symbol, "variant": variant,
                   **{k: economic.get(k) for k in fields if k not in ("symbol", "variant")}}
            writer.writerow({k: "NA" if v is None else v for k, v in row.items()})
    return buffer.getvalue()


def markdown_report(report: dict[str, Any]) -> str:
    """Sinh bảng đọc nhanh từ đúng số liệu JSON, không chép số liệu bằng tay."""
    def percent(value: float | None) -> str:
        return "NA" if value is None else f"{100 * value:.2f}"

    lines = ["# Audit R1 — kết quả legacy", "",
             "Đây là đối soát khám phá từ outputs đã lưu, chưa phải thực nghiệm confirmatory hoặc đóng R1.", "",
             f"Có {report['n_symbols']} mã, {report['n_points']} điểm và "
             f"{report['n_distinct_decision_dates']} ngày quyết định phân biệt. "
             "Các mã không được coi là những replication thị trường độc lập.", "",
             "Target UP: LONG có lãi sau phí từ entry_open đến exit_close; DOWN gồm hòa vốn và lỗ. "
             "SHORT giữ CASH. Base reports là pred_no_alpha lịch sử, bỏ cả alpha và sentiment.", "",
             "## Phân loại pooled trên common support", "",
             "| Variant | N | TP/FN/TN/FP | Accuracy % | BA % | MCC | Macro-F1 % | LONG % |",
             "|---|---:|---|---:|---:|---:|---:|---:|"]
    for variant in VARIANTS:
        m = report["pooled_classification"]["common_support"][variant]
        c = m["confusion"]
        mcc = "NA" if m["mcc"] is None else f"{m['mcc']:.3f}"
        lines.append(f"| {variant} | {m['n_valid']} | {c['tp']}/{c['fn']}/{c['tn']}/{c['fp']} | "
                     f"{percent(m['accuracy'])} | {percent(m['balanced_accuracy'])} | {mcc} | "
                     f"{percent(m['macro_f1'])} | {percent(m['long_rate'])} |")
    lines += ["", "Per-class support/precision/recall/F1 và support riêng nằm trong classification.csv/report.json. "
              "Tỷ lệ JSON/CSV ở thang 0–1; bảng Markdown chuyển sang %. Undefined là null/NA, không ép về 0. "
              "macro_over_symbols là trung bình đều theo mã, khác pooled; chỉ có mean khi mọi mã xác định.", "",
              "## Tài khoản theo từng mã", "",
              "| Mã | Variant | LONG cycles | Số lệnh | Net return % | Cycle-end drawdown % |",
              "|---|---|---:|---:|---:|---:|"]
    for symbol, record in report["per_symbol"].items():
        for variant, economic in record["economics"].items():
            def number(key: str) -> str:
                value = economic.get(key)
                return "NA" if value is None else f"{value:.2f}"
            lines.append(f"| {symbol} | {variant} | {economic.get('long_cycles', 'NA')} | "
                         f"{economic.get('order_count', 'NA')} | {number('net_return_pct')} | "
                         f"{number('cycle_end_drawdown_pct')} |")
    lines += ["", "Trung bình return các tài khoản độc lập (không phải một portfolio chung):", ""]
    for variant, value in report["mean_independent_account_return_pct"].items():
        lines.append(f"- {variant}: {'NA' if value is None else f'{value:+.2f}%'}.")
    lines += ["", "## Giả định và giới hạn", "",
              "- Return chính được tái tính từ giá chuẩn chưa làm tròn; trung bình return đã làm tròn "
              "trong summary legacy nằm riêng ở mean_stored_rounded_account_return_pct và có thể làm tròn khác "
              "ở chữ số cuối. Không sửa summary gốc để khớp số mới.",
              f"- Phí mỗi chiều {report['cost_assumptions']['fee_each_side']}; trượt giá mỗi chiều "
              f"{report['cost_assumptions']['slippage_each_side']}. Đây là giả định replay công khai, "
              "không chứng nhận cấu hình request lịch sử.",
              "- Fractional shares, toàn bộ vốn mỗi LONG, bán cuối chu kỳ, tiền tái dùng ngay; "
              "chưa xử lý settlement, lot size, thuế riêng, corporate actions hoặc khả năng khớp lệnh.",
              "- Always-LONG cycles đóng/mở và trả phí mỗi chu kỳ; không phải buy-and-hold. "
              "CASH ở mức lãi suất 0 và không giao dịch.",
              "- LONG cycle fraction và traded notional/initial capital có định nghĩa riêng; "
              "daily exposure/turnover/drawdown là NA vì thiếu daily snapshot và ledger.",
              "- Không fit majority trên nhãn test. Chưa có frozen train/validation features để chạy "
              "majority, momentum, hai logistic, factor-only và exposure-matched control hợp lệ.",
              "- api_error_flag_counts theo mã được giữ riêng; common support định nghĩa theo prediction "
              "parse hợp lệ, không tự bỏ prediction hợp lệ chỉ vì có cờ error. Failure policy confirmatory chưa freeze.",
              f"- Group metadata còn thiếu: {', '.join(report['missing_group_fields']) or 'không'}. "
              "Không suy regime/fold/repeat từ outcome hoặc tên file.",
              "- Có hash không chứng minh đây là snapshot submission chính thức; "
              "không dùng audit này để suy significance hoặc attribution alpha.",
              f"- Sai lệch cờ correct/return lưu so với tái tính: {len(report['legacy_discrepancies'])}; "
              "xem legacy_discrepancies trong report.json.", ""]
    return "\n".join(lines)


def evidence_paths(root: Path) -> list[Path]:
    """Thu thập bằng chứng hiện có và code replay; không đụng .env hay kết quả mới."""
    candidates = [root / p for p in (
        "AGENTS.md", "plan.md", ".gitattributes", ".python-version", "requirements.txt", "default_config.py",
        "Reviewer Comments for author.docx", "core/backtest_engine.py", "core/revision_audit.py",
        "utils/statistical_tests.py", "scripts/audit_revision_baselines.py",
        "tests/test_revision_baselines.py", "revision/target_contract.md")]
    candidates += list((root / "paper").rglob("*"))
    # Chỉ khóa artifacts phản biện; workspace còn outputs ignored của luồng KLTN.
    for relative in ("outputs/backtest_result", "outputs/robustness/clean_a20",
                     "outputs/ablation/clean_a20", "outputs/sentiment_coverage"):
        candidates += list((root / relative).rglob("*"))
    candidates += list(root.glob("sentiment_cache_*.json"))
    return sorted({p for p in candidates if p.is_file()})


def verify_bundle(directory: Path, root: Path = ROOT) -> int:
    """Kiểm tra nguyên byte nguồn và outputs; thiếu nguồn cũng là thất bại rõ ràng."""
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    checked = 0
    for key, base in (("sources", root), ("outputs", directory)):
        for record in manifest[key]:
            path = (base / record["path"]).resolve()
            if not path.is_relative_to(base.resolve()):
                raise ValueError("Đường dẫn manifest vượt thư mục cho phép")
            if not path.is_file() or sha256_file(path) != record["sha256"]:
                raise ValueError(f"Hash không khớp hoặc thiếu file: {record['path']}")
            checked += 1
    return checked


def run_audit(result_dir: Path, output_dir: Path, symbols: Sequence[str], root: Path = ROOT,
              fee: float = 0.0025, slippage: float = 0.001) -> dict[str, Any]:
    """Chọn chính xác một file/mã và xuất bundle mới, không chọn checkpoint tốt nhất."""
    if output_dir.exists():
        raise FileExistsError("Thư mục output đã tồn tại; dùng --verify hoặc chọn run_id mới")
    if not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("Danh sách symbol phải không rỗng và không trùng")
    paths = []
    for symbol in symbols:
        if not symbol.isascii() or not symbol.isalnum():
            raise ValueError("Symbol phải là chữ/số ASCII")
        matches = sorted(result_dir.glob(f"backtest_{symbol}_*.json"))
        if len(matches) != 1:
            raise ValueError(f"{symbol}: cần đúng một artifact, tìm thấy {len(matches)}")
        paths.append(matches[0])
        if json.loads(matches[0].read_bytes())["symbol"] != symbol:
            raise ValueError(f"Symbol trong artifact không khớp tên file: {symbol}")
    report = build_legacy_report(paths, root, fee, slippage)
    # Hash toàn bộ bằng chứng trước khi ghi output; không đọc lại vendor/API.
    sources = [{"path": p.relative_to(root).as_posix(), "sha256": sha256_file(p),
                "size_bytes": p.stat().st_size} for p in sorted(set(evidence_paths(root) + paths))]
    for record in report["sources"]:
        if next(r["sha256"] for r in sources if r["path"] == record["path"]) != record["sha256"]:
            raise ValueError("Artifact thay đổi trong khi audit; không xuất bundle")
    rendered = {"report.json": _json(report), "classification.csv": classification_csv(report),
                "economics.csv": economics_csv(report), "README.md": markdown_report(report)}
    try:
        base_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                                             stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        base_commit = None
    output_dir.mkdir(parents=True, exist_ok=False)
    for filename, content in rendered.items():
        (output_dir / filename).write_text(content, encoding="utf-8", newline="\n")
    manifest = {"schema_version": "revision_evidence_manifest_v1", "submission_version": "unverified",
                "git_head_at_generation": base_commit,
                "code_identity_policy": "source byte hashes are authoritative, including uncommitted files",
                "source_access": "local files only; presence/hash does not establish publication rights or run lineage",
                "missing_expected_sources": [p for p in (
                    "paper/main.pdf", "paper/main.tex", "paper/main_submit.tex",
                    "Reviewer Comments for author.docx") if not (root / p).is_file()],
                "sources": sources,
                "outputs": [{"path": filename, "sha256": sha256_file(output_dir / filename)}
                            for filename in sorted(rendered)]}
    (output_dir / "manifest.json").write_text(_json(manifest), encoding="utf-8", newline="\n")
    verify_bundle(output_dir, root)
    return report


def main() -> None:
    """Giao diện CLI mặc định trỏ đúng outputs/backtest_result của đợt phản biện."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, default=ROOT / "outputs/backtest_result")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/revision/r1_legacy")
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--fee", type=float, default=0.0025)
    parser.add_argument("--slippage", type=float, default=0.001)
    parser.add_argument("--verify", type=Path, help="Chỉ đối soát hash của bundle đã có")
    args = parser.parse_args()
    try:
        if args.verify:
            count = verify_bundle(args.verify)
            print(f"Đối soát PASS: {count} hash nguồn/đầu ra khớp.")
        else:
            report = run_audit(args.result_dir.resolve(), args.output_dir.resolve(), args.symbols,
                               fee=args.fee, slippage=args.slippage)
            print(f"Đã audit {report['n_symbols']} mã/{report['n_points']} điểm: {args.output_dir}")
            print("R1 đang thực hiện; bundle này chưa đóng các yêu cầu thực nghiệm còn lại.")
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"Audit thất bại: {exc}\n")


if __name__ == "__main__":
    main()
