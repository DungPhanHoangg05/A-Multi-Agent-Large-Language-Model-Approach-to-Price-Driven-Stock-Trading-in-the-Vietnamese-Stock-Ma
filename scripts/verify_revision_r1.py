"""Đối soát nguồn, archive nguyên bản và các invariant của release R1."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.revision_audit import sha256_file
from scripts.audit_revision_baselines import verify_bundle


def main() -> None:
    """Kiểm tra read-only; manuscript đã sửa được đối chiếu bản gốc trong archive."""
    legacy_dir = ROOT / "outputs/revision/r1_legacy"
    manifest = json.loads((legacy_dir / "manifest.json").read_bytes())
    count = 0
    with zipfile.ZipFile(ROOT / "revision/manuscript_original.zip") as archive:
        for source in manifest["sources"]:
            if source["path"].startswith("paper/"):
                digest = hashlib.sha256(archive.read(source["path"])).hexdigest()
            else:
                digest = sha256_file(ROOT / source["path"])
            if digest != source["sha256"]:
                raise ValueError(f"Nguồn legacy không khớp: {source['path']}")
            count += 1
    for record in manifest["outputs"]:
        if sha256_file(legacy_dir / record["path"]) != record["sha256"]:
            raise ValueError("Output legacy thay đổi")
        count += 1
    numeric = ROOT / "outputs/revision/r1_numeric_v1"
    numeric_count = verify_bundle(numeric)
    report = json.loads((numeric / "report.json").read_bytes())
    models = json.loads((numeric / "models.json").read_bytes())
    for model in models.values():
        if not model["last_train_label_date"] < model["first_validation_date"]:
            raise ValueError("Label train chạm validation")
        if not model["last_validation_label_date"] < model["first_test_date"]:
            raise ValueError("Label validation chạm test")
    with (numeric / "predictions.csv").open(encoding="utf-8", newline="") as handle:
        predictions = list(csv.DictReader(handle))
    if len(predictions) != 1440 or any(p["variant"] == "full" for p in predictions):
        raise ValueError("Prediction count sai hoặc đã trộn Full legacy vào bảng khác snapshot")
    with (numeric / "summary.csv").open(encoding="utf-8", newline="") as handle:
        summary = list(csv.DictReader(handle))
    for record in summary:
        symbol, variant = record["symbol"], record["variant"]
        with (numeric / f"daily_{symbol}_{'continuous_hold' if variant == 'continuous_hold_price_only' else variant}.csv").open(encoding="utf-8", newline="") as handle:
            daily = list(csv.DictReader(handle))
        actual_return = (float(daily[-1]["equity_vnd"]) / 50_000_000 - 1) * 100
        if abs(actual_return - float(record["net_return_pct"])) > 1e-9:
            raise ValueError("Return summary không khớp daily ledger")
        expected_orders = 2 if variant == "continuous_hold_price_only" else 2 * sum(
            p["prediction"] == "LONG" for p in predictions if p["symbol"] == symbol and p["variant"] == variant)
        if int(record["order_count"]) != expected_orders:
            raise ValueError("Số lệnh không khớp quyết định/continuous hold")
    if report["n_legacy_price_or_label_mismatches"] and report["legacy_comparison_status"] != "blocked_snapshot_mismatch":
        raise ValueError("Sai lệch snapshot chưa chặn so sánh legacy")
    print(f"PASS: {count} hash legacy qua archive gốc; {numeric_count} hash release số.")
    print(f"PASS: {len(predictions)} dự đoán số, {len(summary)} ledger, purge và tách snapshot.")


if __name__ == "__main__":
    main()
