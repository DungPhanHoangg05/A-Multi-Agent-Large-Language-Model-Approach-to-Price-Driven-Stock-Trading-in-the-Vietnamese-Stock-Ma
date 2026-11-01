"""Đối soát bank, releases số và các run dừng; không gọi API hoặc tự đóng R1."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.revision_audit import sha256_file
from core.revision_common_study import digest, read_json, verify_bank, verify_features
from core.revision_common_analysis import checked_unit


def main() -> None:
    """Nguồn cũ đối chiếu archive đúng hash; runtime hiện hành phải khớp trực tiếp."""
    base = ROOT / "outputs/revision"
    archives = [ZipFile(base / f"r1_common_bank_{v}/source_snapshot.zip") for v in ("v1", "v2")]
    try:
        def source_ok(source: dict) -> None:
            path = ROOT / source["path"]
            if path.exists() and sha256_file(path) == source["sha256"]:
                return
            for archive in archives:
                if source["path"] in archive.namelist() and hashlib.sha256(archive.read(source["path"])).hexdigest() == source["sha256"]:
                    return
            raise ValueError(f"Nguồn không khớp file hiện hành hoặc archive: {source['path']}")

        verify_bank(ROOT, base / "r1_common_bank_v3")
        for version in ("v1", "v2", "v3"):
            bank = base / f"r1_common_bank_{version}"
            manifest = read_json(bank / "manifest.json")
            assert digest({k: v for k, v in manifest.items() if k != "bank_id"}) == manifest["bank_id"]
            for source in manifest["sources"]:
                source_ok(source)
            verify_features(bank, manifest)
            if (bank / "feature_reuse.json").exists():
                for source in read_json(bank / "feature_reuse.json")["sources"]:
                    source_ok(source)
        for version in ("v2", "v3"):
            output = base / f"r1_common_numeric_{version}"
            release = read_json(output / "manifest.json")
            for source in release["sources"]:
                source_ok(source)
            for artifact in release["outputs"]:
                assert sha256_file(output / artifact["path"]) == artifact["sha256"]
        for version, receipt in (("v1", "smoke_status.json"), ("v2", "stopped_receipt.json"), ("v3", "stopped_receipt.json")):
            run = base / f"r1_common_run_{version}"
            for artifact in read_json(run / receipt)["artifacts"]:
                assert sha256_file(run / artifact["path"]) == artifact["sha256"]
        run = base / "r1_common_run_v2"
        signature = read_json(run / "run_manifest.json")["run_signature"]
        for path in (run / "units").glob("*.json"):
            checked_unit(run, path.stem, signature, base / "r1_common_bank_v2")
        print("PASS: ba bank/feature receipts, hai numeric releases, ba stopped receipts và replay calibration chẩn đoán. Không phải nghiệm thu Full/R1.")
    finally:
        for archive in archives:
            archive.close()


if __name__ == "__main__":
    main()
