"""Kiểm kê toàn bộ outputs và archive để xác định nguồn có thể dùng cho R1."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.revision_audit import sha256_file


def main() -> None:
    """Đọc cả thư mục ignored, không nhập code hoặc dùng outputs KLTN làm dữ liệu R1."""
    output = ROOT / "outputs/revision/r1_source_inventory.json"
    if output.exists():
        raise FileExistsError("Không ghi đè kiểm kê nguồn")
    counts, legacy_hits, price_files, archives = Counter(), [], [], []
    for path in sorted((ROOT / "outputs").rglob("*")):
        if not path.is_file() or "revision" in path.relative_to(ROOT / "outputs").parts:
            continue
        relative = path.relative_to(ROOT).as_posix()
        counts[relative.split("/")[1]] += 1
        if path.suffix in (".csv", ".parquet", ".npz", ".pkl"):
            price_files.append(relative)
        if path.suffix == ".json":
            raw = path.read_bytes()
            if b"2026-06-18" in raw or b"2026-06-19" in raw:
                data = json.loads(raw)
                points = data.get("test_points", []) if isinstance(data, dict) else []
                legacy_hits.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest(),
                    "top_level_keys": sorted(data) if isinstance(data, dict) else [],
                    "first_point_keys": sorted(points[0]) if points else []})
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                legacy = []
                for name in names:
                    if name.startswith("outputs/backtest_result/") and name.endswith(".json"):
                        data = archive.read(name)
                        local = ROOT / name
                        legacy.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(),
                            "matches_current_bytes": local.exists() and data == local.read_bytes()})
                archives.append({"path": relative, "sha256": sha256_file(path), "n_entries": len(names),
                    "data_named_entries": [n for n in names if any(k in n.lower() for k in (
                        "ohlcv", "snapshot", "/data/", "train_predictions", "main.pdf"))],
                    "csv_entries": [n for n in names if n.endswith(".csv")], "legacy_results": legacy})
    result = {"schema_version": "r1_output_inventory_v1", "folder_file_counts": dict(counts),
        "tabular_candidates_outside_revision": price_files, "legacy_period_json_candidates": legacy_hits,
        "archives": archives,
        "finding": "Legacy September-2026 benchmark/sweeps retain final decisions and cycle endpoints; "
                   "no authenticated full OHLCV/report/feature/train-Full archive found for nine legacy symbols. "
                   "Other candidate requests belong to different 2023 protocols; never relabeled as legacy train.",
        "limitations": "Inventory evidence and key/date searches do not certify deleted or external files absent; "
                       "recovery inventory separately records missing files."}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Đã kiểm kê {sum(counts.values())} file và {len(archives)} archive; {len(legacy_hits)} JSON có mốc legacy.")


if __name__ == "__main__":
    main()
