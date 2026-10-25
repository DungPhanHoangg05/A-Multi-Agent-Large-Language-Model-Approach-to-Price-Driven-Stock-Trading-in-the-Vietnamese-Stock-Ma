"""Request Decision U-BICL: cùng instruction/schema, chỉ khác prefix đã kiểm."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage

from agents import decision_agent as legacy
from core.bayesian_memory import iso_date
from core.bayesian_retriever import BayesianPriorRetriever, normalize_signals
from core.historical_signals import digest
from core.improvement_prior import build_evidence, render_prefix
from core.improvement_transport import body_contract, validate_client
from core.prior_context import REPORT_FIELDS
from core.price_feature_index import _json_bytes
from core.research_cohort import read_envelope
from core.research_input_lock import runtime_identity
from core.unified_bayes_context import UnifiedBayesContext
from core.unified_bayes_prompt import BRANCHES, assemble_prompt, check_budget, render_context

VERSION = "unified_bic_decision_instructions_v1"
PACKET_VERSION = "unified_bic_prepared_decision_v1"
LLM_BRANCHES = ("Original", "A_reference", *BRANCHES)
RENDERER_SHA = "7536eca3079db8769b4de8b4bcfbdd82b3ad521ea3a89131fb0c27bc1321f635"
COMMON = {
    "vi": "PRIOR nếu có là lịch sử, không P(query). T/P=Trend/Pattern; w0=trọng số prior. Đối chiếu với tín hiệu hiện tại; giải thích căn cứ khi LONG với mean<0,5 hoặc CASH với mean>0,5. Không buộc đồng ý prior; viện dẫn ID đã thấy nếu dùng.",
    "en": "PRIOR, if shown, is history, not P(query). T/P=Trend/Pattern; w0=prior weight. Compare current signals; explain LONG with mean<0.5 or CASH with mean>0.5. Agreement is optional; cite visible IDs when used.",
}
FORBIDDEN = {"outcome", "evaluation", "actual_direction", "net_return_pct", "entry_date", "exit_date",
             "entry_open", "exit_close", "actual_pct_change", "decision", "confidence", "justification"}
_VERIFIED = object()


def load_renderer_lock(context: UnifiedBayesContext) -> dict[str, Any]:
    """Cold loader giữ nguyên snapshot U10-05; lock instruction mới dùng artifact khác."""
    from scripts.prepare_unified_bayes_context import OUTPUT, code_identity
    if hashlib.sha256(OUTPUT.read_bytes()).hexdigest() != RENDERER_SHA:
        raise ValueError("Renderer/context khác snapshot đã khóa")
    saved = read_envelope(OUTPUT)
    if (saved["code_sha256"] != code_identity() or saved["runtime"] != runtime_identity()
            or saved["memory_sha256"] != context.statistics.memory_identity
            or saved["index_sha256"] != context.memory.index.identity):
        raise ValueError("Renderer lock khác nguồn/code/runtime/memory")
    root = Path(__file__).resolve().parents[1]
    for name, expected in saved["sources"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Nguồn renderer thay đổi: {name}")
    return saved


class _MemoryAdapter:
    """Đổi thứ tự tham số legacy; mọi record vẫn qua guard memory U-BICL."""

    def __init__(self, context: UnifiedBayesContext) -> None:
        self.memory = context.memory

    def eligible(self, cutoff: str, symbol: str | None) -> list[dict[str, Any]]:
        """A chỉ cùng mã, không mở scope pooled để tăng coverage."""
        if symbol is None:
            raise ValueError("A_reference chỉ nhận cùng mã")
        return self.memory.eligible(symbol, cutoff)


def reference_retriever(context: UnifiedBayesContext) -> BayesianPriorRetriever:
    """Dùng nguyên masks/selector/prefix A trên union đã kiểm, không sửa dependency cũ."""
    retriever = BayesianPriorRetriever.__new__(BayesianPriorRetriever)
    retriever._memory = _MemoryAdapter(context)
    retriever._verified_by_id = deepcopy(context.memory._records)
    retriever._bank_sha256 = context.memory.index.payload["provenance"]["bank"]["bank_sha256"]
    retriever._price_index_identities = set()
    return retriever


def build_prompt(shared: dict[str, Any], prefix: str) -> str:
    """Giữ cap/distill và cổng kinh tế; cả năm nhánh nhận cùng base/instruction."""
    if type(shared) is not dict or FORBIDDEN.intersection(shared):
        raise ValueError("Shared chứa nhãn query hoặc trường Decision")
    lang = shared.get("language")
    if lang not in COMMON or shared.get("is_backtest") is not True or shared.get("time_frame") not in ("1d", "1 ngày"):
        raise ValueError("Decision U-BICL chỉ nhận daily/backtest và ngôn ngữ đã đăng ký")
    iso_date(shared.get("as_of_date"))
    if any(type(shared.get(key)) is not str or not shared[key].strip() for key in REPORT_FIELDS):
        raise ValueError("Shared thiếu một trong năm report đã seal")
    reports = {key: legacy._distill_report(key.removesuffix("_report"), shared[key], lang,
        report_limits=legacy._BACKTEST_REPORT_CHAR_LIMITS) for key in REPORT_FIELDS}
    desc = "Open(t+1)→Close(t+3)"
    note = "3 phiên; SHORT=CASH" if lang == "vi" else "3 trading sessions; SHORT=CASH"
    base = getattr(legacy, f"_build_compact_prompt_{lang}")(shared["stock_name"], "1d", 5, True, True,
        desc, "T+2.5", note, **reports)
    head, marker, tail = base.partition("### [1]")
    if not marker:
        raise ValueError("Base Decision thiếu vị trí report")
    base = head + COMMON[lang] + "\n\n" + marker + tail
    return assemble_prompt(base, prefix)


def sdk_request(llm: Any, prompt: str) -> tuple[dict[str, Any], Any]:
    """Serializer SDK thật, chưa invoke HTTP; mọi nhánh dùng schema legacy duy nhất."""
    messages, params = llm._create_message_dicts([HumanMessage(content=prompt)], None)
    structured = llm.with_structured_output(legacy.TradeDecisionOutput, method="json_schema", include_raw=True)
    raw = structured.steps[0].steps__["raw"]
    body = {"messages": messages, **params, "response_format": deepcopy(raw.kwargs["response_format"])}
    _json_bytes(body)
    body_contract(body)
    return body, structured


def shared_off_allowed(*, prior_visible: bool, same_identity: bool, same_point_repeat: bool,
                       original_durable: bool, duplicate: bool) -> bool:
    """Rule fixture đã khóa; body identity gồm model/options/schema và toàn messages."""
    if any(type(value) is not bool for value in (prior_visible, same_identity, same_point_repeat, original_durable, duplicate)):
        raise ValueError("Điều kiện shared-off phải là bool gốc")
    return not prior_visible and same_identity and same_point_repeat and original_durable and not duplicate


class PreparedPoint:
    """Packet chỉ cấp từ producer đã tái kiểm source/context; không nhận cờ PASS bên ngoài."""

    def __init__(self, *, packets: dict[str, Any], source_check: Any, base: dict[str, Any],
                 reference: dict[str, Any], _verified: object) -> None:
        if _verified is not _VERIFIED:
            raise ValueError("PreparedPoint phải được producer nguồn cấp")
        self._packets = deepcopy(packets)
        self._source_check = source_check
        self._base, self._reference = deepcopy(base), deepcopy(reference)
        first = packets["Original"]
        self.point_id = first["point_id"]
        self.shared_sha256 = first["shared_sha256"]

    @property
    def base(self) -> dict[str, Any]:
        """Bản sao base dùng chung, không cho caller đổi evidence đã khóa."""
        return deepcopy(self._base)

    @property
    def reference(self) -> dict[str, Any]:
        """Bốn metric A giữ nguyên và tách khỏi posterior mục tiêu của U."""
        return deepcopy(self._reference)

    def packet(self, branch: str) -> dict[str, Any]:
        """Duplicate giữ body Original nhưng có slot riêng; không phải alias stats-only."""
        if branch == "Original_duplicate":
            packet = deepcopy(self._packets["Original"])
            packet["branch_id"] = branch
            return packet
        if branch not in LLM_BRANCHES:
            raise ValueError("Nhánh Decision chưa đăng ký hoặc là Numeric_only")
        return deepcopy(self._packets[branch])

    def verify(self, llm: Any) -> None:
        """Kiểm source và serializer hiện tại trước mọi lần resume/invoke."""
        self._source_check()
        for packet in self._packets.values():
            body, _ = sdk_request(llm, packet["prompt"])
            if digest(body) != digest(packet["body"]):
                raise ValueError("Model/options/schema/body SDK đổi sau khóa request")


def _prepare_point(context: UnifiedBayesContext, point: Any, shared: dict[str, Any], llm: Any,
                   models: dict[str, Any]) -> PreparedPoint:
    """Một Full đã seal, một base U và một A trên cùng memory; không gọi lại upstream."""
    validate_client(llm, "agent", models)
    original = deepcopy(shared)
    point.verify_source(original)
    point._adapter.verify_sources()
    proof = point.source_provenance
    if (FORBIDDEN.intersection(original) or proof["context"]["symbol"] != original.get("stock_name")
            or proof["context"]["as_of_date"] != original.get("as_of_date")):
        raise ValueError("Shared khác point/source hoặc chứa outcome")
    query = {"symbol": original["stock_name"], "as_of_date": original["as_of_date"],
        "current_regime": original["market_regime"]["regime_name"], "current_signals": normalize_signals(original["current_signals"])}
    features = point.price_features()
    base = context.evidence(**query, query_features=features)
    context.validate(base, features)
    ref = build_evidence(reference_retriever(context), "A_tp_pool", **query,
        selector=context.selector, query_features=features)
    prefixes = {"Original": "", "A_reference": render_prefix(ref, "A_tp_pool"),
                **{branch: render_context(base, branch)["prefix"] for branch in BRANCHES}}
    pid = f"{query['symbol']}-{query['as_of_date']}"
    packets = {}
    for branch, prefix in prefixes.items():
        prompt = build_prompt(deepcopy(original), prefix)
        check_budget(prefix, prompt)
        body, _ = sdk_request(llm, prompt)
        aliases = render_context(base, branch)["aliases"] if branch in BRANCHES else {}
        packets[branch] = {"packet_version": PACKET_VERSION, "instruction_version": VERSION, "renderer_sha256": RENDERER_SHA,
            "branch_id": branch, "point_id": pid, "query": deepcopy(query), "language": original["language"],
            "shared_sha256": digest(original), "source_sha256": digest(proof),
            "base_evidence_sha256": base["base_evidence_sha256"], "reference_sha256": ref["base_evidence_sha256"],
            "visible_aliases": aliases, "prefix": prefix, "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "body": body, "contract": body_contract(body)}
    if digest(shared) != digest(original):
        raise ValueError("Producer làm thay đổi Full gốc")
    def verify() -> None:
        """Nguồn thật được tái kiểm; state caller không được thay Full sau khi bind."""
        if digest(shared) != digest(original):
            raise ValueError("Full gốc thay sau khóa packet")
        point.verify_source(deepcopy(original))
        point._adapter.verify_sources()
    return PreparedPoint(packets=packets, source_check=verify, base=base, reference=ref, _verified=_VERIFIED)


def trace_ids(packet: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    """Telemetry không bắt buộc, không thêm schema, sửa action hoặc tạo format retry."""
    text = " ".join(output.get(key, "") for key in ("evidence_for", "evidence_against", "justification"))
    found = sorted(set(re.findall(r"\b[TE][1-9][0-9]*\b", text)))
    visible = packet["visible_aliases"]
    return {"trace_version": "unified_bic_id_telemetry_v1", "for_promotion": False,
            "cited_ids": [key for key in found if key in visible], "unknown_ids": [key for key in found if key not in visible]}


class DecisionPreparer:
    """Cold bind renderer một lần; producer mỗi point giữ nguyên Full và cùng năm nhánh."""

    def __init__(self, context: UnifiedBayesContext, llm: Any, models: dict[str, Any]) -> None:
        load_renderer_lock(context)
        validate_client(llm, "agent", models)
        self.context, self.llm, self.models = context, llm, deepcopy(models)

    def prepare(self, point: Any, shared: dict[str, Any]) -> PreparedPoint:
        """Không nhận evidence tự khai; tái dựng U và A từ memory/feature nguồn thật."""
        return _prepare_point(self.context, point, shared, self.llm, self.models)
