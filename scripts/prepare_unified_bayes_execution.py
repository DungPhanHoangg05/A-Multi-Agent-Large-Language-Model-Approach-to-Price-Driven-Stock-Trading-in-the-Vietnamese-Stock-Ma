"""Khóa instruction và canonical request U-BICL offline; không tạo execution plan/API run."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from langchain_groq import ChatGroq

from agents.decision_agent import TradeDecisionOutput
from core.historical_signals import digest
from core.improvement_protocol import calendar
from core.improvement_runtime import shared_point
from core.research_input_lock import _write_once, runtime_identity
from core.research_cohort import read_envelope
from core.unified_bayes_context import UnifiedBayesContext
from core.unified_bayes_decision import COMMON, VERSION, RENDERER_SHA, DecisionPreparer, LLM_BRANCHES
from core.unified_bayes_memory import OUTPUT as MEMORY_PATH, load_memory
from core.unified_bayes_runtime import code_identity as kernel_code
from scripts.prepare_unified_bayes_memory import PROTOCOL_SHA, verified_inputs
from scripts.prepare_unified_bayes_pooling import NAMESPACE, MEMORY_SHA, load_protocol, sha
from core.pilot_readiness import build_adapter

OUTPUT = NAMESPACE / "execution_contract_v1.json"
SOURCE = "outputs/bayesian_benchmark/improvement_v1/development"


class DenyTransport(httpx.BaseTransport):
    """Serializer SDK được dùng; bất kỳ HTTP nào đều là lỗi offline."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError("Khóa request offline không được gọi HTTP")


def code_identity() -> dict[str, str]:
    """Khóa kernel cùng producer input; không đổi dependency hoặc hash W9."""
    names = ("scripts/prepare_unified_bayes_execution.py", "scripts/prepare_unified_bayes_memory.py")
    return {**kernel_code(), **{name: hashlib.sha256((ROOT / name).read_text("utf-8").encode()).hexdigest() for name in names}}


def build_contract() -> dict[str, Any]:
    """Dựng 300 body thật từ cache Full đã kiểm; không đọc Decision hoặc chấm target mới."""
    load_protocol()
    if sha(ROOT / MEMORY_PATH) != MEMORY_SHA:
        raise ValueError("Memory không còn là snapshot đã khóa")
    inputs = verified_inputs()
    memory = load_memory(ROOT / MEMORY_PATH, **inputs)
    context = UnifiedBayesContext(memory, inputs["calendar"])
    plan = read_envelope(ROOT / SOURCE / "plan.json")
    identity = read_envelope(ROOT / SOURCE / "run/cohort.json")
    if digest(identity["plan"]) != digest(plan):
        raise ValueError("Nguồn cohort khác plan development đã khóa")
    adapter = build_adapter(plan["inputs"], root=ROOT)
    models = plan["inputs"]["signal_config"]["models"]
    with httpx.Client(transport=DenyTransport()) as client:
        llm = ChatGroq(model=models["agent_llm_model"], api_key="offline-placeholder", temperature=models["agent_llm_temperature"],
            max_tokens=models["agent_llm_max_tokens"], max_retries=0, reasoning_effort="low", reasoning_format="hidden", http_client=client)
        llm.temperature = models["agent_llm_temperature"]
        producer = DecisionPreparer(context, llm, models)
        points, eligible, lengths = [], Counter(), []
        for row in calendar(plan):
            point, shared, doc = shared_point(SimpleNamespace(adapter=adapter), row, ROOT / SOURCE / "run", digest(identity), verify_only=True)
            if shared is None:
                raise ValueError("Thiếu upstream cache; không fallback fresh trong run")
            prepared = producer.prepare(point, shared)
            packets = {branch: prepared.packet(branch) for branch in LLM_BRANCHES}
            original = packets["Original"]["body"]
            for branch, packet in packets.items():
                lengths.append(len(packet["prompt"]))
                if branch != "Original" and not packet["prefix"] and digest(packet["body"]) == digest(original):
                    eligible[branch] += 1
            points.append({"point_id": row["point_id"], "source_shared_sha256": doc["shared_sha256"], "packets": packets})
    if len(points) != 60:
        raise ValueError("Request lock không đủ 60 điểm nguồn đã khóa")
    adapter.verify_sources()
    sources = {**inputs["source_files"], **adapter.source_hashes, MEMORY_PATH: MEMORY_SHA,
        "outputs/bayesian_benchmark/unified_bic_v1/inputs/renderer_contract_v1.json": RENDERER_SHA}
    for name, value in sources.items():
        if sha(ROOT / name) != value:
            raise ValueError(f"Nguồn thay đổi khi khóa execution contract: {name}")
    return {"artifact_kind": "instruction_and_request_contract_lock", "status": "LOCKED",
        "instruction_version": VERSION, "common_instructions": COMMON,
        "protocol_sha256": PROTOCOL_SHA, "renderer_sha256": RENDERER_SHA,
        "memory_sha256": memory.identity, "index_sha256": memory.index.identity,
        "schema_sha256": digest(TradeDecisionOutput.model_json_schema()), "code_sha256": code_identity(),
        "runtime": runtime_identity(), "sources": dict(sorted(sources.items())), "query_count": len(points),
        "prepared_llm_requests": len(points) * len(LLM_BRANCHES), "actual_http_requests": 0, "decision_calls": 0,
        "max_prompt_chars": max(lengths), "shared_off_eligible": dict(sorted(eligible.items())),
        "duplicate_policy": "INDEPENDENT_INVOCATION", "stats_alias_whitelist": [],
        "retry_policy": "resilient_invocation_v1", "ledger_path": "outputs/oos_pilot/api_usage.json",
        "is_execution_plan": False, "confirmation_allowed": False, "points": points,
        "limitations": ["Đây là lock instruction/body offline, chưa là CLI producer/report hoặc dry-run runtime U10-07–09.",
            "HTTP/response/UUID/usage chỉ phát sinh khi operator chạy runtime; không tạo invocation hay decision giả từ lock này.",
            "Cold loader vẫn kiểm toàn snapshot lịch sử; không dùng payoff query để chọn instruction, alias hoặc action."]}


def main() -> None:
    """Prepare ghi một lần; verifier rebuild source/SDK body và phân biệt native types."""
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare", action="store_true", help="Khóa instruction và request offline")
    modes.add_argument("--verify-only", action="store_true", help="Dựng lại toàn bộ 300 request từ nguồn thật")
    args = parser.parse_args()
    if not args.prepare and not OUTPUT.exists():
        raise ValueError("Chưa có execution contract; verifier không tạo input")
    expected = build_contract()
    if args.prepare:
        _write_once(OUTPUT, expected)
    if digest(read_envelope(OUTPUT)) != digest(expected):
        raise ValueError("Execution contract khác source/body/schema/instruction/code/runtime đã tái dựng")
    print(f"Instruction/request PASS: {expected['query_count']} điểm, {expected['prepared_llm_requests']} body; "
          f"prompt tối đa {expected['max_prompt_chars']}/6499; chưa gọi HTTP/LLM hoặc phát hành xác nhận")


if __name__ == "__main__":
    main()
