"""Khóa lịch development/repeat trước action, chỉ đọc context và upstream đã kiểm."""

from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from core.historical_signals import digest
from core.improvement_runtime import shared_point
from core.improvement_prior import point_request
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_adapter import OUTPUT as INTEGRATION, VARIANTS, load_inputs, resolve_episode
from core.mt_bicl_v2_decision import canonical_request
from core.mt_bicl_v2_integration import DRY_VERSION, reference_adapter
from core.mt_bicl_v2_io import read_envelope
from core.mt_bicl_v2_release import RELEASE_PATH, require_development_release
from core.mt_bicl_v21_preparation import file_hash
from core.prior_run_lock import safe_path
from core.research_cohort import read_envelope as read_legacy
from core.research_input_lock import runtime_identity

MANIFEST_PATH = Path("docs/plan/week11/development_run_manifest_v2.json")
MANIFEST_VERSION = "mt_bicl_development_run_manifest_v2"
OUTPUT = Path("outputs/bayesian_benchmark/mt_bicl_v2/development2023")
LEGACY = Path("outputs/bayesian_benchmark/improvement_v1/development/run")
LEGACY_COHORT_SHA256 = "3e04016dffe5d636e642a6811dcd6b95af7335b0f0ecc0a3e913a724fac15c7c"
RELEASE_SHA256 = "8459cfc1a4e95dae7512bc3c236fe102764d6af13ce5a7d3d19e0ce67d805121"
CODE = ("core/mt_bicl_v2_run_manifest.py", "core/mt_bicl_v2_api_preflight.py",
        "scripts/prepare_mt_bicl_development.py", "tests/test_mt_bicl_v2_run_manifest.py")


def branch_order(j: int, repeat: int = 0) -> list[str]:
    """j là chỉ số toàn cohort đã sort; Original luôn đầu, duplicate phải gọi riêng."""
    if type(j) is not int or j < 0 or type(repeat) is not int or repeat not in (0, 1, 2, 3):
        raise ValueError("Chỉ số point/repeat ngoài protocol")
    rest = [*VARIANTS[1:], *(["Original_duplicate"] if repeat else [])]
    shift = ((3*j+repeat-1) if repeat else j) % len(rest)
    return ["Original", *rest[shift:], *rest[:shift]]


def repeat_selection(rows: list[dict[str, Any]], symbols: list[str]) -> list[dict[str, Any]]:
    """Chọn ba stratum/mã trước action; bù chỉ sau khi đã xét mọi stratum hiện hữu."""
    result = []
    for symbol in symbols:
        group = sorted((r for r in rows if r["query"]["symbol"] == symbol),
                       key=lambda r: (r["query"]["as_of_date"], r["query"]["episode_id"]))
        selected: dict[str, dict[str, Any]] = {}
        used: set[str] = set()
        strata = (("m=0", lambda m: m == 0), ("m=1..3", lambda m: 1 <= m <= 3),
                  ("m>=4", lambda m: m >= 4))
        for name, predicate in strata:
            found = next((r for r in group if predicate(r["m"])), None)
            if found is not None:
                selected[name] = found
                used.add(found["query"]["episode_id"])
        for name, _ in strata:
            fallback = name not in selected
            row = selected.get(name)
            if fallback:
                row = next((r for r in group if r["query"]["episode_id"] not in used), None)
            if row is None:
                raise ValueError("Không đủ ba repeat point khác nhau cho mã: "+symbol)
            used.add(row["query"]["episode_id"])
            result.append({"symbol": symbol, "stratum_requested": name,
                           "point_id": row["query"]["episode_id"], "m": row["m"],
                           "reason": "MISSING_STRATUM_FIRST_UNSELECTED_DATE" if fallback else "FIRST_DATE_IN_STRATUM"})
    return result


def schedule(rows: list[dict[str, Any]], development: dict[str, Any], symbols: list[str]) -> dict[str, Any]:
    """Giữ đủ60 point kể cả thiếu feature, khóa612 slot; repeat không tăng N primary."""
    rows = sorted(rows, key=lambda r: (r["query"]["as_of_date"], symbols.index(r["query"]["symbol"])))
    ids = [r["query"]["episode_id"] for r in rows]
    expected = {f"{s}-{d}" for s, dates in development["symbol_cutoffs"].items() for d in dates}
    if len(ids) != 60 or len(set(ids)) != 60 or set(ids) != expected:
        raise ValueError("Cohort phải đúng60 point development2023 đã khóa")
    for row in rows:
        q = row["query"]
        if (q["episode_id"] != q["symbol"]+"-"+q["as_of_date"] or not q["as_of_date"].startswith("2023-")
                or type(row["K"]) is not int or not 0 <= row["K"] <= 3
                or type(row["m"]) is not int or not 0 <= row["m"] <= 8):
            raise ValueError("Point/K/m không đúng development2023")
    gate = development["support_gate"]
    supported = [r for r in rows if r["status"] == "AVAILABLE" and r["K"] >= gate["K_at_least"] and r["m"] >= gate["m_at_least"]]
    counts = {s: sum(r["query"]["symbol"] == s for r in supported) for s in symbols}
    if len(supported) < gate["simultaneous_points_min"] or any(n < gate["simultaneous_each_symbol_min"] for n in counts.values()):
        raise ValueError("INSUFFICIENT_CONTEXT_NO_API")
    sample = repeat_selection(rows, symbols)
    selected = {r["point_id"] for r in sample}
    blocks = [{"point_id": pid, "point_index": j, "repeat_index": 0, "order": branch_order(j)} for j, pid in enumerate(ids)]
    # Lượt repeat là vòng ngoài, j giữ chỉ số toàn cohort, không đánh số lại mẫu12.
    blocks.extend({"point_id": pid, "point_index": j, "repeat_index": r, "order": branch_order(j, r)}
                  for r in (1, 2, 3) for j, pid in enumerate(ids) if pid in selected)
    slots = [{"slot_index": i, "point_id": b["point_id"], "point_index": b["point_index"],
              "repeat_index": b["repeat_index"], "branch_id": name}
             for i, (b, name) in enumerate((b, name) for b in blocks for name in b["order"])]
    if len(sample) != 12 or len(selected) != 12 or len(slots) != 612:
        raise ValueError("Sai số repeat point/slot đã đăng ký")
    return {"point_ids": ids, "repeat_selection": sample, "blocks": blocks, "slots": slots,
            "support": {"simultaneous": len(supported), "by_symbol": counts, "gate": "PASS"}}


def verified_upstream(root: Path, inputs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Kiểm code/runtime/config/source/journal W9; không đọc action hoặc gọi graph mới."""
    cohort_path = root/LEGACY/"cohort.json"
    if file_hash(cohort_path) != LEGACY_COHORT_SHA256:
        raise ValueError("Cohort upstream lịch sử khác identity đã nghiệm thu")
    cohort = read_legacy(cohort_path)
    plan = cohort["plan"]
    decision = inputs["protocol"]["decision"]
    if (plan["split"] != "development_2023" or plan["symbol_cutoffs"] != inputs["protocol"]["development"]["symbol_cutoffs"]
            or plan["inputs"]["signal_config"] != decision["signal_config"]
            or plan["inputs"]["client_options"] != decision["client_options"]
            or plan["runtime"] != runtime_identity()):
        raise ValueError("Upstream lịch sử khác cohort/model/options/runtime; cần revision trước API")
    for name, expected in plan["code_sha256"].items():
        actual = hashlib.sha256(safe_path(root, name).read_text(encoding="utf-8").encode()).hexdigest()
        if actual != expected:
            raise ValueError("Mã tạo upstream lịch sử đã đổi: "+name)
    adapter, index = reference_adapter(root, inputs)
    for name, expected in cohort["sources"].items():
        adapter._files.pin(name, expected)
    shared, points, references = {}, {}, {}
    runner = SimpleNamespace(adapter=adapter)
    for number, row in enumerate(inputs["rows"], 1):
        query = row["query"]
        pid = query["episode_id"]
        with redirect_stdout(io.StringIO()):
            point, state, doc = shared_point(runner, {"point_id": pid, "symbol": query["symbol"], "as_of_date": query["as_of_date"]},
                                           root/LEGACY, digest(cohort), verify_only=True)
        if state is None:
            raise ValueError("Upstream chưa durable: "+pid)
        shared[pid] = deepcopy(state)
        evidence, request = point_request(point, deepcopy(state), index, "A_tp_pool")
        references[pid] = request
        if number % 15 == 0:
            print(f"Đối soát upstream/PIT/A_reference {number}/60 PASS; không API.", flush=True)
        points[pid] = {"point_path": (LEGACY/"points"/(pid+".json")).as_posix(),
                       "point_sha256": file_hash(root/LEGACY/"points"/(pid+".json")),
                       "journal_path": (LEGACY/"responses"/(pid+".json")).as_posix(),
                       "journal_sha256": doc["journal_sha256"], "shared_sha256": content_hash(state),
                       "source_proof_sha256": content_hash(doc["source_proof"]),
                       "a_reference_evidence_sha256": content_hash(evidence)}
    return shared, {"policy": "REUSE_VERIFIED_DURABLE_UPSTREAM_ONCE_NO_VISION_FOR_BRANCH_OR_REPEAT",
                    "cohort_path": (LEGACY/"cohort.json").as_posix(), "cohort_sha256": file_hash(cohort_path),
                    "historical_signature": digest(cohort), "points": points, "new_upstream_calls": 0}, references


def collect(root: Path) -> dict[str, Any]:
    """Chỉ dữ liệu đã release; tái dùng p frozen trên cùng episode, không student/GPU/refit."""
    release = require_development_release(root)
    if file_hash(root/RELEASE_PATH) != RELEASE_SHA256:
        raise ValueError("Release không đúng byte W10-14 đã nghiệm thu")
    inputs = load_inputs(root)
    for row in inputs["rows"]:
        resolve_episode(row, inputs["context"])
    dry = read_envelope(root/INTEGRATION/"dry_run.json", DRY_VERSION)
    variants = {p["point_id"]: p["variants"] for p in dry["points"]}
    for row in inputs["rows"]:
        pid = row["query"]["episode_id"]
        episode_hash = content_hash(resolve_episode(row, inputs["context"]))
        if any(variants[pid][v]["episode_sha256"] != episode_hash for v in VARIANTS):
            raise ValueError("p/projection frozen khác membership query hiện hành")
    layout = schedule(inputs["rows"], release["development"], release["decision"]["symbol_order"])
    shared, upstream, references = verified_upstream(root, inputs)
    # A phụ thuộc current_signals thật; không tái dùng prefix W10 sinh từ reports fixture.
    for pid, request in references.items():
        variants[pid]["A_reference"].update(prefix=request["prefix"], a_reference=deepcopy(request))
    requests = {}
    for block in layout["blocks"]:
        pid, repeat = block["point_id"], block["repeat_index"]
        for name in block["order"]:
            base = "Original" if name == "Original_duplicate" else name
            requests[(pid, repeat, name)] = canonical_request(deepcopy(shared[pid]), variants[pid][base]["prefix"], inputs["protocol"], repeat)
    return {"release": release, "inputs": inputs, "layout": layout, "shared": shared,
            "upstream": upstream, "variants": variants, "requests": requests}
