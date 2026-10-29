"""Renderer/request v3 dùng distill/cap cũ; transport chỉ qua wrapper đã có."""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any
from uuid import UUID

from agents.decision_agent import DECISION_FORMAT_ATTEMPTS, _invoke_with_retry
from core.mt_bicl_bank import content_hash
from core.mt_bicl_context import check_prompt_length
from core.mt_bicl_v2_decision import build_prompt as legacy_prompt, canonical_request as legacy_request
from core.mt_bicl_v3_contracts import REVISION_BRANCHES, validate_branch, validate_fact_packet, validate_wire, wire_schema
from core.mt_bicl_v3_policy import apply_revision, validate_anchor
from core.research_invocation import ENABLED, RECOVERY, invocation_scope

OUTPUT_MARKER = "Chỉ trả về một JSON hợp lệ, không Markdown hay chữ ngoài JSON:\n"
FACT_INSTRUCTION = (
    "FACTS là số PIT; chép đủ ba fact_ids/assertions, phân biệt dưới0/dưới Signal. "
    "Báo cáo agent chưa phải sự thật số đã chứng minh. "
)
CONTRACT = "T+2.5: LONG mua toàn vốn Open(t+1), tất toán Close(t+3); phí0,25%+slippage0,10% mỗi chiều. SHORT=CASH, không bán khống; TP/SL không đổi lịch thoát. "
PRIORITY = "Trend/Pattern: xu hướng/cản/thời điểm; Indicator: động lượng. Alpha có thể veto breakout thiếu dòng tiền, đảo chiều cần≥3/5 đồng thuận. Sentiment trọng số thấp nhất. Trend+Pattern cùng giảm: LONG chỉ khi có hỗ trợ mạnh+alpha đảo chiều áp đảo+nến/chỉ báo xác nhận."


def fact_card(packet: dict[str, Any]) -> str:
    """Số .8g luôn kèm enum raw; warnings không trở thành hard assertion."""
    validate_fact_packet(packet)
    n, a = packet["numeric"], packet["assertions"]
    def number(value: float | None) -> str:
        """NA giữ missing, không fill0 hoặc dùng số tròn để xác định dấu."""
        return "NA" if value is None else f"{value:.8g}"
    lines = ["FACTS PIT "+packet["as_of_date"]+"; horizon=T+2.5",
             f"MACD_SIGNAL: MACD={number(n['macd'])}; Signal={number(n['signal'])}; Δ={number(n['macd_minus_signal'])}; {a['MACD_SIGNAL']}",
             f"MACD_ZERO: {a['MACD_ZERO']}",
             f"PRICE_SMA20: Close={number(n['close'])}; SMA20={number(n['sma20'])}; Δ={number(n['close_minus_sma20'])}; {a['PRICE_SMA20']}",
             "bucket="+packet["bucket"]]
    lines.extend("Báo cáo, chưa chứng minh số: "+value for value in packet["reported_warnings"])
    card = "\n".join(lines)
    if len(card) > 700:
        raise ValueError("FAIL_PROMPT_BUDGET: fact card vượt700, không cắt facts/warnings")
    return card


def _legacy_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    """Chỉ đổi vị trí config v3; không sửa model/options hoặc schema Original/A."""
    return {"decision": deepcopy(protocol["decision"]["config"])}


def build_anchored_prompt(shared: dict[str, Any], packet: dict[str, Any], *, branch_id: str,
                          projection: dict[str, Any] | None = None, anchor: dict[str, Any] | None = None) -> str:
    """Thay instruction/schema cho nhánh mới, giữ reports/distill/cap và toàn bộ guard."""
    if branch_id not in ("Fact_Anchor", *REVISION_BRANCHES):
        raise ValueError("Branch prompt anchored không hợp lệ")
    if shared["stock_name"]+"-"+shared["as_of_date"] != packet["point_id"]:
        raise ValueError("Reports/facts khác point")
    base = legacy_prompt(deepcopy(shared), "")
    priority_marker = "THỨ TỰ ƯU TIÊN BẰNG CHỨNG:"
    marker = "### [1]"
    if base.count(priority_marker) != 1 or base.count(OUTPUT_MARKER) != 1 or base.count(marker) != 1:
        raise ValueError("Template legacy đổi, cần kiểm hợp đồng prompt v3")
    reports = marker+base.split(marker, 1)[1].split(priority_marker, 1)[0]
    instruction = FACT_INSTRUCTION
    cards = [fact_card(packet)]
    if branch_id == "Fact_Anchor":
        if anchor is not None or projection is not None:
            raise ValueError("Fact_Anchor không nhận p/U/examples/a0")
        context_reason = "NOT_APPLICABLE"
    else:
        if anchor is None or projection is None:
            raise ValueError("Revision cần a0 và context đủ support trước API")
        validate_anchor(anchor, packet)
        if not anchor["policy"]["fact_assertions_valid"]:
            raise ValueError("Anchor sai facts phải bypass về Original, không gửi revision")
        prefix = projection["prefix"]
        if type(prefix) is not str or len(prefix) > 600 or projection["prefix_chars"] != len(prefix):
            raise ValueError("FAIL_PROMPT_BUDGET: projection v3 không hợp lệ")
        anchor_card = "a0="+anchor["policy"]["final_action"]+"; nguồn="+anchor["policy"]["anchor_source_sha256"][:16]
        if len(anchor_card) > 80:
            raise ValueError("FAIL_PROMPT_BUDGET: anchor card vượt80")
        cards.extend((anchor_card, prefix))
        instruction += "Q chưa có nhãn; n/w/l/r là toàn tập, e chỉ là projection. "
        if branch_id in ("Plain_revision", "No_utility"):
            instruction += "Đề xuất giữ/sửa a0 theo facts/context; không có utility/numeric veto. "
        else:
            instruction += "p≠ER; U teacher+bootstrap đã net phí, chưa distill/đảm bảo coverage. Chỉ sửa nếu Q10ΔU>0: CASH→LONG dùng Q10U, LONG→CASH dùng −Q90U; đúng0 giữ a0. "
        context_reason = "SUPPORTED"
    example = {"version": "utility_icl_reply_v3", "decision": "LONG hoặc SHORT", "forecast_horizon": "T+2.5",
               "confidence": "Cao|Trung bình|Thấp", "risk_reward_ratio": 1., "evidence_for": "thuận≤2 câu",
               "evidence_against": "nghịch≤1 câu", "justification": "lý do≤2 câu",
               "fact_ids": list(packet["assertions"]), "fact_assertions": deepcopy(packet["assertions"]), "context_reason": context_reason}
    prompt = f"Mã {shared['stock_name']}; khung1d. "+CONTRACT+instruction+"\n"+"\n".join(cards)+"\n"+reports+PRIORITY+"\n"+OUTPUT_MARKER+json.dumps(example, ensure_ascii=False, separators=(",", ":"))
    check_prompt_length(prompt)
    return prompt


def canonical_request(shared: dict[str, Any], protocol: dict[str, Any], *, branch_id: str,
                      packet: dict[str, Any] | None = None, prefix: str = "", projection: dict[str, Any] | None = None,
                      anchor: dict[str, Any] | None = None, repeat: int = 0) -> dict[str, Any]:
    """Original/A giữ nguyên request legacy; UUID/cache namespace mới do runner quản lý."""
    if branch_id in ("Original", "Original_duplicate", "A_reference"):
        if branch_id != "A_reference" and prefix:
            raise ValueError("Original không được nhận prefix")
        if projection is not None or anchor is not None:
            raise ValueError("Original/A không nhận context/anchor v3")
        return legacy_request(deepcopy(shared), prefix, _legacy_protocol(protocol), repeat)
    if prefix or packet is None:
        raise ValueError("Nhánh mới dùng fact packet/projection thay prefix tùy ý")
    request = legacy_request(deepcopy(shared), "", _legacy_protocol(protocol), repeat)
    request["messages"] = [{"role": "user", "content": build_anchored_prompt(deepcopy(shared), packet, branch_id=branch_id, projection=projection, anchor=anchor)}]
    request["structured"]["schema"] = deepcopy(wire_schema()["$defs"]["reply"])
    return request


def invoke_revision(llm: Any, request: dict[str, Any], *, attempt_id: str,
                    run_signature: str, branch_id: str) -> dict[str, Any]:
    """Caller cần release; lỗi transport không được catch thành abstention hoặc CASH."""
    UUID(attempt_id)
    if (branch_id not in ("Fact_Anchor", *REVISION_BRANCHES) or type(run_signature) is not str
            or len(run_signature) != 64 or any(c not in "0123456789abcdef" for c in run_signature)
            or request["structured"]["schema"] != wire_schema()["$defs"]["reply"]):
        raise ValueError("Invocation v3 không đúng schema reply đã khóa")
    structured = llm.with_structured_output(request["structured"]["schema"], method="json_schema", include_raw=True)
    enable, recovery = ENABLED.set(True), RECOVERY.set(True)
    try:
        with invocation_scope("decision") as budget:
            if budget is not None:
                budget.checkpoint_attempt_id, budget.point_id = attempt_id, request["point_id"]
                budget.branch_id, budget.run_signature = branch_id, run_signature
            last = None
            for _ in range(DECISION_FORMAT_ATTEMPTS):
                raw = _invoke_with_retry(structured.invoke, request["messages"][0]["content"])
                try:
                    if type(raw) is not dict or raw.get("parsing_error") is not None or type(raw.get("parsed")) is not dict:
                        raise ValueError("Response v3 thiếu parsed JSON hợp lệ")
                    reply = deepcopy(raw["parsed"])
                    validate_wire(reply, "reply")
                    return reply
                except ValueError as error:
                    last = error
            raise ValueError("Response v3 sai schema sau hai lần sửa format; giữ checkpoint") from last
    finally:
        RECOVERY.reset(recovery)
        ENABLED.reset(enable)


def revision_plan(shared: dict[str, Any], packet: dict[str, Any], anchor: dict[str, Any],
                  prepared: dict[str, Any], protocol: dict[str, Any], *, repeat: int = 0) -> dict[str, Any]:
    """Năm slot giữ đủ, bypass có proof; không gọi upstream/LLM hoặc giả cache hit."""
    before = content_hash(shared)
    validate_anchor(anchor, packet)
    result = {}
    for name in REVISION_BRANCHES:
        branch = prepared["branches"][name]
        validate_branch(branch)
        if name in ("Plain_revision", "No_utility") and (
                branch["eligible"] != prepared["branches"]["Full_utility_ICL"]["eligible"]
                or branch["membership_sha256"] != prepared["branches"]["Full_utility_ICL"]["membership_sha256"]):
            raise ValueError("Plain/No_utility phải dùng cùng Full support mask/membership")
        enabled = branch["eligible"] and anchor["policy"]["fact_assertions_valid"]
        result[name] = {"request": canonical_request(deepcopy(shared), protocol, branch_id=name, packet=deepcopy(packet),
                           projection=deepcopy(branch["projection"]), anchor=deepcopy(anchor), repeat=repeat) if enabled else None,
                        "bypass_policy": None if enabled else apply_revision(deepcopy(packet), deepcopy(anchor), deepcopy(branch))}
    if content_hash(shared) != before:
        raise ValueError("Revision planner đã mutate shared upstream")
    return result
