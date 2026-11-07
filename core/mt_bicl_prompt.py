"""Prompt chung, Decision schema legacy và journal paired; CLI tích hợp chỉ dùng fixture offline."""

from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

from agents.decision_agent import (
    DECISION_FORMAT_ATTEMPTS, TradeDecisionOutput, _BACKTEST_REPORT_CHAR_LIMITS,
    _build_compact_prompt_vi, _distill_report, _guard_backtest_prompt,
    _invoke_with_retry, _normalize_structured_result,
)
from core.mt_bicl_bank import content_hash
from core.mt_bicl_prompt_limits import check_prompt_length
from core.mt_bicl_io import read_envelope, write_envelope
from core.prior_context import REPORT_FIELDS
from core.research_invocation import CURRENT, ENABLED, RECOVERY, invocation_scope
from utils.i18n import get_horizon

COMMON_INSTRUCTION = (
    "Đối chiếu tín hiệu hiện tại với prior tasks P1/P2/P3 và target context T nếu có; Q chưa có nhãn. "
    "Bốn feature chuẩn hóa biểu diễn bằng q, xem legend; ví dụ hiển thị chỉ là projection của context. "
    "p=P(y net>0), không phải expected return hay R:R. Được bác context; không ép action theo p. "
    "Nêu bằng chứng thuận/nghịch trong evidence_for/evidence_against và justification hiện hữu. "
    "SHORT=CASH; LONG vào Open(t+1), ra Close(t+3); TP/SL mô tả không thay lịch thoát."
)
JOURNAL_VERSION = "mt_bicl_paired_decision_journal"
FORBIDDEN = {"outcome","evaluation","supervised_target","query_y","actual_direction","actual_pct_change",
             "entry_open","exit_close","net_return","net_return_pct"}


def build_prompt(shared:dict[str,Any], prefix:str) -> str:
    """Mọi nhánh dùng cùng instruction/schema/distill/cap; chỉ prefix thay đổi."""
    if (type(shared) is not dict or FORBIDDEN.intersection(shared) or shared.get("is_backtest") is not True
            or shared.get("time_frame") != "1d" or shared.get("language") != "vi"
            or type(prefix) is not str or len(prefix) > 600
            or any(type(shared.get(k)) is not str or not shared[k].strip() for k in REPORT_FIELDS)):
        raise ValueError("Shared reports/prefix không hợp lệ hoặc chứa outcome query")
    distilled = {name:_distill_report(name,shared[name+"_report"],"vi",report_limits=_BACKTEST_REPORT_CHAR_LIMITS)
                 for name in ("trend","pattern","indicator","alpha","sentiment")}
    horizon = get_horizon("1d","vi")
    base = _build_compact_prompt_vi(shared["stock_name"],"1d",5,True,True,
        horizon["horizon_desc"],horizon["horizon_val"],horizon["note"],
        *(distilled[k] for k in ("trend","pattern","indicator","alpha","sentiment")))
    marker = "### [1]"
    if base.count(marker) != 1:raise ValueError("Template Decision đổi marker, cần kiểm hợp đồng")
    head,tail = base.split(marker,1)
    prompt = head+COMMON_INSTRUCTION+"\n"+(prefix+"\n" if prefix else "")+marker+tail
    # Giữ nguyên guard; driver ghi một dòng/point và max chars trong receipt thay log lặp sáu nhánh.
    with redirect_stdout(io.StringIO()):
        _guard_backtest_prompt(prompt,lang="vi",time_frame="1d",report_lengths={k:len(v) for k,v in distilled.items()},prefix_length=len(prefix))
    check_prompt_length(prompt)
    return prompt


def canonical_request(shared:dict[str,Any], prefix:str, protocol:dict[str,Any], repeat:int=0) -> dict[str,Any]:
    """Hash đúng prompt/model/options/schema/point/repeat; tên ablation không đổi HTTP payload."""
    if type(repeat) is not int or not 0 <= repeat <= 3:raise ValueError("Repeat phải0..3")
    prompt = build_prompt(shared,prefix)
    model = protocol["decision"]["signal_config"]["models"]
    return {"point_id":shared["stock_name"]+"-"+shared["as_of_date"],"repeat_index":repeat,
            "model":model["agent_llm_model"],"temperature":model["agent_llm_temperature"],
            "max_tokens":model["agent_llm_max_tokens"],"client_max_retries":protocol["decision"]["client_max_retries"],
            "client_options":deepcopy(protocol["decision"]["client_options"]["agent"]),
            "service_tier":protocol["decision"]["service_tier"],
            "structured":{"schema":TradeDecisionOutput.model_json_schema(),"method":"json_schema","include_raw":True},
            "messages":[{"role":"user","content":prompt}]}


def invoke_decision(llm:Any, request:dict[str,Any], *, attempt_id:str|None=None,
                    run_signature:str|None=None, branch_id:str|None=None) -> dict[str,Any]:
    """Caller chịu release/transport/quota; dùng retry wrapper và budget chung cho format repair."""
    structured = llm.with_structured_output(TradeDecisionOutput,method="json_schema",include_raw=True)
    enable = ENABLED.set(True)
    recovery = RECOVERY.set(True)
    try:
        with invocation_scope("decision") as budget:
            if budget is not None:
                budget.checkpoint_attempt_id = attempt_id
                budget.point_id = request["point_id"]
                budget.branch_id = branch_id
                budget.run_signature = run_signature
            last = None
            for _ in range(DECISION_FORMAT_ATTEMPTS):
                raw = _invoke_with_retry(structured.invoke,request["messages"][0]["content"])
                try:
                    normalized,_ = _normalize_structured_result(raw,"vi")
                    parsed = TradeDecisionOutput.model_validate(json.loads(normalized),strict=True).model_dump()
                    return parsed
                except ValueError as error:last = error
            raise ValueError("Decision không đúng schema sau số lần sửa đã khóa") from last
    finally:
        RECOVERY.reset(recovery)
        ENABLED.reset(enable)


class DecisionSession:
    """Intent/UUID durable trước invoke; unknown giữ reserve, không tự gửi lại hoặc đổi thành CASH."""

    def __init__(self,path:Path,binding:dict[str,Any]) -> None:
        self.path,self.binding = path,deepcopy(binding)
        self.document = read_envelope(path,JOURNAL_VERSION) if path.exists() else {"binding":deepcopy(binding),"branches":{}}
        if set(self.document) != {"binding","branches"} or self.document["binding"] != binding:
            raise ValueError("Journal khác source/shared/point/repeat")
        if type(self.document["branches"]) is not dict:raise ValueError("Journal branches sai schema")

    def save(self,candidate:dict[str,Any])->None:
        """Chỉ tiến RAM sau khi ghi durable thành công; lỗi ghi vẫn giữ intent unknown."""
        write_envelope(self.path,JOURNAL_VERSION,candidate)
        self.document = deepcopy(candidate)

    def run(self,shared:dict[str,Any],branches:dict[str,Any],order:list[str],protocol:dict[str,Any],
            llm:Any, *, repeat:int=0) -> dict[str,Any]:
        """Original durable trước các nhánh; deep-copy mọi input/output và không gọi upstream tại đây."""
        if not order or order[0] != "Original" or len(set(order)) != len(order) or set(order) != set(branches):
            raise ValueError("Thứ tự paired phải Original đầu và đúng mọi nhánh")
        if set(self.document["branches"])-set(order):raise ValueError("Journal có nhánh không thuộc run")
        before = content_hash(shared)
        requests = {name:canonical_request(deepcopy(shared),branches[name]["prefix"],protocol,repeat) for name in order}
        for name in order:
            request = requests[name]
            checksum = content_hash(request)
            saved = self.document["branches"].get(name)
            if saved is not None:
                if (set(saved) != {"request","canonical_sha256","status","attempt_id","shared_off_from","decision"}
                        or saved["request"] != request or saved["canonical_sha256"] != checksum):
                    raise ValueError("Journal Decision khác canonical request hiện tại")
                if saved["status"] != "complete":raise ValueError("AMBIGUOUS_DECISION: giữ UUID/reserve, không tự replay")
                TradeDecisionOutput.model_validate(saved["decision"],strict=True)
                if saved["shared_off_from"] is None:UUID(saved["attempt_id"])
                else:
                    if (saved["shared_off_from"] != "Original" or name in ("Original","Original_duplicate")
                            or request != requests["Original"] or saved["attempt_id"] is not None
                            or saved["decision"] != self.document["branches"]["Original"]["decision"]):
                        raise ValueError("Shared-off không đúng Original durable/canonical request")
                continue
            original = self.document["branches"].get("Original")
            reuse = (name not in ("Original","Original_duplicate") and original is not None
                     and original["status"] == "complete" and request == requests["Original"])
            record = {"request":request,"canonical_sha256":checksum,"status":"unknown",
                      "attempt_id":None if reuse else str(uuid4()),"shared_off_from":"Original" if reuse else None,"decision":None}
            candidate = deepcopy(self.document)
            candidate["branches"][name] = record
            self.save(candidate)
            if reuse:decision = deepcopy(original["decision"])
            else:decision = invoke_decision(llm,request,attempt_id=record["attempt_id"],
                                          run_signature=content_hash(self.binding),branch_id=name)
            candidate = deepcopy(self.document)
            candidate["branches"][name].update(status="complete",decision=deepcopy(decision))
            self.save(candidate)
        if before != content_hash(shared):raise ValueError("Paired Decision đã mutate shared upstream")
        return deepcopy(self.document)
