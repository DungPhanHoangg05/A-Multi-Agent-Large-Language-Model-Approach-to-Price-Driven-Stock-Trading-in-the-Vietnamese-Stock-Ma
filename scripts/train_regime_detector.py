"""Fit HMM một lần trên VN-Index 2018–2022 và lưu artifact nghiên cứu."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.regime_detector import MarketRegimeDetector, TRAIN_END, TRAIN_START, training_data_hash


def main() -> None:
    """Xác thực CSV với manifest, cắt tập train tường minh rồi fit hoặc kiểm tra."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="Chỉ kiểm tra artifact hiện có, không refit")
    args = parser.parse_args()
    csv_path = REPO_ROOT / "data/historical/VNINDEX.csv"
    manifest = json.loads((csv_path.parent / "manifest.json").read_text(encoding="utf-8"))
    if (manifest["source_library"] != "vnstock" or manifest["sources"] != ["VCI", "KBS"]
            or hashlib.sha256(csv_path.read_bytes()).hexdigest() != manifest["files"]["VNINDEX"]["sha256"]):
        raise ValueError("Nguồn hoặc checksum CSV VNINDEX không khớp manifest W1")
    archive = pd.read_csv(csv_path, parse_dates=["Datetime"])
    train = archive.loc[archive.Datetime.between(TRAIN_START, TRAIN_END)].copy()
    artifact = REPO_ROOT / "data_manager/regime_model.json"
    if args.verify_only:
        detector = MarketRegimeDetector.load(artifact, expected_training_hash=training_data_hash(train))
    else:
        if artifact.exists():
            raise ValueError("Artifact đã tồn tại; dùng --verify-only hoặc lưu bản cũ trước khi fit lại")
        detector = MarketRegimeDetector().fit(train)
        detector.save(artifact)
    meta = detector.metadata
    print(f"Đã {'kiểm tra' if args.verify_only else 'fit và lưu'} VNINDEX: {meta['training_rows']} nến, "
          f"{meta['feature_rows']} đặc trưng, {meta['train_start_date']} đến {meta['train_end_date']}")
    print(f"Hash train: {meta['training_data_sha256']}; giá PIT chưa xác minh, chỉ dùng nghiên cứu")


if __name__ == "__main__":
    main()
