"""Khóa renderer/context U-BICL offline từ upstream development đã kiểm, không Decision."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.historical_signals import digest
from core.pit_price_features import extract_pit_price_features
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once, runtime_identity
from core.unified_bayes_context import CHOICE_SHA, UnifiedBayesContext
from core.unified_bayes_memory import OUTPUT as MEMORY_PATH, load_memory
from core.unified_bayes_prompt import VERSION, BRANCHES, render_context
from scripts.prepare_unified_bayes_memory import PROTOCOL_SHA, verified_inputs
from scripts.prepare_unified_bayes_pooling import MEMORY_SHA, NAMESPACE, sha, load_protocol

OUTPUT = NAMESPACE / "renderer_contract_v1.json"
CODE = ("core/unified_bayes_context.py", "core/unified_bayes_prompt.py",
        "scripts/prepare_unified_bayes_context.py", "core/prior_price_similarity.py",
        "core/prior_example_selection.py", "agents/decision_agent.py")


def code_identity() -> dict[str, str]:
    """Khóa code LF mới và primitive similarity/lịch/report cap đang dùng."""
    return {name: hashlib.sha256((ROOT / name).read_text("utf-8").encode()).hexdigest() for name in CODE}


def build_contract() -> dict[str, Any]:
    """Tái kiểm nguồn, context và prefix của 60 điểm; không đọc Decision/query payoff."""
    protocol = load_protocol()
    if sha(ROOT / MEMORY_PATH) != MEMORY_SHA:
        raise ValueError("Memory khác bản đã nghiệm thu; không đổi nguồn context")
    inputs = verified_inputs()
    memory = load_memory(ROOT / MEMORY_PATH, **inputs)
    context = UnifiedBayesContext(memory, inputs["calendar"])
    schedule = sorted((row for row in inputs["imported"] if row["source"]["cohort"] == "development_2023"),
                      key=lambda row: (row["as_of_date"], row["symbol"]))
    if len(schedule) != 60:
        raise ValueError("Context không đủ 60 upstream development đã khóa")
    points = []
    for row in schedule:
        frame, events = inputs["prices"][row["symbol"]]
        features = extract_pit_price_features(frame, events, inputs["calendar"], row["as_of_date"], source=inputs["source"])
        query = {"symbol": row["symbol"], "as_of_date": row["as_of_date"],
                 "current_regime": row["regime"], "current_signals": row["agent_signals"]}
        evidence = context.evidence(**query, query_features=features)
        context.validate(evidence, features)
        views = {branch: render_context(evidence, branch) for branch in BRANCHES}
        points.append({"query": query, "evidence": evidence, "views": views})
    modes = dict(sorted(Counter(point["evidence"]["context_mode"] for point in points).items()))
    multi = Counter(point["query"]["symbol"] for point in points
                    if point["evidence"]["context_mode"] == "task" and len(point["evidence"]["examples"]) >= 2)
    claim = protocol["task_context"]["multi_task_claim_gate"]
    sources = {**inputs["source_files"], MEMORY_PATH: MEMORY_SHA,
        "outputs/bayesian_benchmark/unified_bic_v1/inputs/backbone_choice_v1.json": CHOICE_SHA}
    for name, expected in sources.items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"Nguồn đổi khi kiểm context: {name}")
    return {"artifact_kind": "renderer_and_context_lock", "status": "LOCKED", "renderer_version": VERSION,
        "protocol_sha256": PROTOCOL_SHA, "choice_sha256": CHOICE_SHA,
        "memory_sha256": memory.identity, "index_sha256": memory.index.identity,
        "code_sha256": code_identity(), "runtime": runtime_identity(), "sources": dict(sorted(sources.items())),
        "decision_calls": 0, "is_execution_plan": False, "confirmation_allowed": False,
        "query_count": len(points), "modes": modes,
        "points_with_two_visible_tasks": sum(multi.values()), "two_task_count_by_symbol": dict(sorted(multi.items())),
        "multi_task_support_gate": sum(multi.values()) >= claim["minimum_points_with_two_visible_tasks"]
            and all(multi[symbol] >= claim["minimum_per_symbol"] for symbol in ("FPT", "MWG", "VCB", "VNM")),
        "max_prefix_chars": max(view["prefix_chars"] for point in points for view in point["views"].values()),
        "points": points, "common_instruction_status": "PENDING_U10_06",
        "limitations": ["Chỉ kiểm context/renderer offline, chưa là dry-run runtime U10-09 hoặc bằng chứng hiệu quả LLM.",
            "Không dùng outcome query để chọn mode/ranking; membership PIT có thể chứa cycle development trước đó đã đóng.",
            "Support gate chỉ cho mô tả multi-task, không thay nomination/release; không tune rule để tăng coverage."]}


def main() -> None:
    """Prepare ghi một lần; verifier tái dựng semantic, không tin cờ hoặc tự reseal."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare", action="store_true", help="Khóa context/renderer offline")
    modes.add_argument("--verify-only", action="store_true", help="Tái kiểm toàn bộ 60 context và nguồn")
    args = parser.parse_args()
    if not args.prepare and not OUTPUT.exists():
        raise ValueError("Chưa có renderer lock; verifier không tạo artifact")
    expected = build_contract()
    if args.prepare:
        _write_once(OUTPUT, expected)
    if digest(read_envelope(OUTPUT)) != digest(expected):
        raise ValueError("Renderer/context khác nguồn, membership, ranking, projection hoặc code/runtime")
    print(f"Context/renderer PASS: {expected['query_count']} điểm; mode={expected['modes']}; "
          f"BRPP tối đa {expected['max_prefix_chars']}/600; chưa gọi LLM hoặc phát hành xác nhận")


if __name__ == "__main__":
    main()
