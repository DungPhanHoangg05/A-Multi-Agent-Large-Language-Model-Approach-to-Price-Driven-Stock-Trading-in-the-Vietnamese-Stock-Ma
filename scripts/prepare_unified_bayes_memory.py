"""Dựng/kiểm memory U-BICL offline từ upstream W8/W9, không đọc Decision hoặc gọi mạng."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.bayesian_memory import read_json
from core.historical_runner import HistoricalMemoryRunner
from core.historical_signals import digest
from core.improvement_protocol import calendar
from core.improvement_runtime import shared_point
from core.pilot_readiness import build_adapter
from core.price_feature_index import _hash
from core.research_cohort import read_envelope
from core.research_input_lock import runtime_identity
from core.unified_bayes_memory import OUTPUT, build_memory, load_memory, save_memory

PROTOCOL = "docs/plan/week10/unified_bic_protocol_v1.json"
PROTOCOL_SHA = "c392c92cd6b1b6c49672adeb4ada5cf47b902e3cb4c2bef41aca5cb5857abfda"
ARCHIVE = "outputs/bayesian_benchmark/improvement_v1/holdout/frozen_results_v1.zip"


def verified_inputs(root: Path = ROOT) -> dict[str, Any]:
    """Đối chiếu archive, nguồn, seal/journal và tín hiệu trước khi cấp cho producer.

    Chỉ đọc plan/cohort/points/responses và nguồn PIT; không mở decisions,
    report hoặc evaluation. Cả producer và verifier dùng lại cùng biên này.
    """
    root = root.resolve()
    hashes: dict[str, str] = {}

    def pin(name: str, expected: str | None = None) -> str:
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Đường dẫn nguồn memory thoát workspace")
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if (expected is not None and checksum != expected
                or name in hashes and hashes[name] != checksum):
            raise ValueError(f"Nguồn memory sai checksum: {name}")
        hashes[name] = checksum
        return checksum

    protocol = read_json(root / PROTOCOL)
    if _hash(protocol) != PROTOCOL_SHA:
        raise ValueError("Protocol memory khác bản U-BICL đã khóa")
    pin(PROTOCOL)
    for name, expected in protocol["source_anchors"].items():
        pin(name, expected)
    imported = []
    with zipfile.ZipFile(root / ARCHIVE) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise ValueError("Archive W9 chứa tên trùng")

        def frozen(name: str) -> None:
            if name not in archive.NameToInfo:
                raise ValueError(f"Nguồn upstream không có trong archive W9: {name}")
            pin(name, hashlib.sha256(archive.read(name)).hexdigest())

        manifest = read_json(root / "data_manager/regime_memory_store.manifest.json")
        run_name = f"{manifest['run_dir']}/run_manifest.json"
        pin(run_name)
        original_run = HistoricalMemoryRunner._read_envelope(root / run_name)
        if (digest(original_run) != manifest["run_signature"] or original_run["models"] != manifest["models"]
                or original_run["signal_config"] != protocol["model_provenance"]["signal_config"]):
            raise ValueError("Model nguồn bank khác manifest đã khóa")
        compatibility = {"signal_config": original_run["signal_config"],
                         "client_options": protocol["model_provenance"]["client_options"]}
        inputs = None
        for cohort, expected_count in (("development", 60), ("holdout", 64)):
            prefix = f"outputs/bayesian_benchmark/improvement_v1/{cohort}"
            plan_name, cohort_name = f"{prefix}/plan.json", f"{prefix}/run/cohort.json"
            frozen(plan_name)
            frozen(cohort_name)
            plan, identity = read_envelope(root / plan_name), read_envelope(root / cohort_name)
            expected_version = "improvement_run_identity_v2" if cohort == "development" else "improvement_holdout_run_identity_v1"
            if (identity["identity_version"] != expected_version
                    or identity["plan"] != plan or identity["execution_mode"] != "research"):
                raise ValueError("Cohort upstream khác plan hoặc execution mode đã kiểm")
            if plan["runtime"] != runtime_identity():
                raise ValueError("Runtime nguồn upstream khác dependency W8/W9 đã khóa")
            for name, expected in plan["code_sha256"].items():
                if hashlib.sha256((root / name).read_text("utf-8").encode()).hexdigest() != expected:
                    raise ValueError(f"Dependency nguồn upstream khác code LF W8/W9: {name}")
                pin(name)
            adapter = build_adapter(plan["inputs"], root=root)
            for symbol, item in plan["inputs"]["news_sources"].items():
                pin(f"{plan['inputs']['news_dir']}/{symbol}.json", item["snapshot_sha256"])
            if inputs is None:
                inputs = adapter._price_feature_index_inputs()
                original = adapter._retriever._memory.records
                if len(original) != protocol["memory"]["original_count"]:
                    raise ValueError("Bank gốc không đủ 852 record")
            rows = calendar(plan)
            if len(rows) != expected_count:
                raise ValueError("Cohort upstream thiếu/thừa điểm so với audit")
            signature = digest(identity)
            for row in rows:
                point_name = f"{prefix}/run/points/{row['point_id']}.json"
                journal_name = f"{prefix}/run/responses/{row['point_id']}.json"
                frozen(point_name)
                frozen(journal_name)
                point, shared, doc = shared_point(SimpleNamespace(adapter=adapter), row,
                    root / prefix / "run", signature, verify_only=True)
                if shared is None:
                    raise ValueError("Upstream chưa hoàn tất; không được gọi lại để sinh memory")
                point.verify_source(shared)
                journal = HistoricalMemoryRunner._read_envelope(root / journal_name)
                if any(len(node["attempts"]) != 1 for node in journal["nodes"].values()):
                    raise ValueError("Upstream có số attempt khác audit một lần/stage")
                imported.append({"episode_id": f"{row['symbol']}:{row['as_of_date']}",
                    "symbol": row["symbol"], "as_of_date": row["as_of_date"],
                    "regime": shared["market_regime"]["regime_name"], "agent_signals": shared["current_signals"],
                    "source": {"cohort": plan["split"], "point_id": row["point_id"],
                        "run_signature": signature, "shared_sha256": doc["shared_sha256"],
                        "signal_config": plan["inputs"]["signal_config"],
                        "client_options": plan["inputs"]["client_options"]}})
            for name, expected in adapter.source_hashes.items():
                # Nguồn transitively bind qua manifest/point proof; archive không chứa mọi input tin.
                if name in archive.NameToInfo:
                    frozen(name)
                pin(name, expected)
        if inputs is None:
            raise ValueError("Không có nguồn upstream đã kiểm")
    # Tái kiểm mọi byte đã dùng để phát hiện nguồn đổi giữa quá trình nhập.
    for name, expected in list(hashes.items()):
        pin(name, expected)
    inputs.pop("records")
    return {**inputs, "original": original, "imported": imported,
            "compatibility": compatibility, "source_files": dict(sorted(hashes.items())),
            "protocol_sha256": PROTOCOL_SHA}


def main() -> None:
    """Mặc định verify-only; prepare không có đường gọi API hoặc key."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare", action="store_true", help="Dựng memory/index từ nguồn đã khóa")
    modes.add_argument("--verify-only", action="store_true", help="Tái kiểm toàn bộ nguồn và semantic")
    args = parser.parse_args()
    inputs = verified_inputs()
    if args.prepare:
        memory = build_memory(**inputs)
    else:
        memory = load_memory(ROOT / OUTPUT, **inputs)
    for name, expected in inputs["source_files"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Nguồn đổi trong quá trình dựng/kiểm memory: {name}")
    if args.prepare:
        save_memory(memory, ROOT / OUTPUT)
    print(f"Memory/index U-BICL PASS: {memory.payload['counts']}; chưa chạy Decision hoặc xác nhận 2025")


if __name__ == "__main__":
    main()
