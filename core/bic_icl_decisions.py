"""Decision ghép cặp revision: reuse đúng request, durable UUID và nguồn alias."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime
import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import UUID, uuid4

import httpx

from agents import decision_agent
from core.candidate_cohort import _checked_response
from core.historical_signals import digest
from core.improvement_recovery import ResilientTransport, recovery_scope, VERSION as RECOVERY_VERSION
from core.improvement_runtime import _attempts
from core.improvement_transport import SLOT, expected_contract, validate_client, verify_attempt_audit
from core.prior_config import copy_prior_json
from core.prior_run_lock import PriorRunLock, safe_path, utc_now
from core.prior_stage_journal import StageJournal, encode_output
from core.research_cohort import read_envelope, save_envelope
from core.research_input_lock import _write_once
from core.research_invocation import CURRENT, ENABLED, invocation_scope

ROOT = Path(__file__).resolve().parents[1]
VERSION = "bic_icl_decision_block_v1"
METHOD = "docs/plan/week10/method_protocol_v1.md"
METHOD_SHA256 = "e9c8410bed048733d1ad3faa296a200409c91bfd8be72557d98639ecd8e8313b"
DEVELOPMENT = ("original", "A_reference_shared_off", "R_pool_full", "R_pool_stats_only",
               "R_pool_examples_only", "R_task_full", "R_task_stats_only", "R_task_examples_only")
CONFIRMATION = ("original", "A_reference_shared_off", "selected_full", "selected_stats_only", "selected_examples_only")
MODELS = {"agent_llm_model": "openai/gpt-oss-20b", "agent_llm_temperature": 0., "agent_llm_max_tokens": 2048}
DEPENDENCIES = ("agents/decision_agent.py", "core/bic_icl_decisions.py", "core/candidate_cohort.py",
    "core/improvement_runtime.py", "core/improvement_transport.py", "core/improvement_recovery.py",
    "core/groq_pacing.py", "core/provider_quota.py", "core/prior_stage_journal.py",
    "core/prior_run_lock.py", "core/research_cohort.py", "core/research_input_lock.py",
    "core/research_invocation.py", "core/prior_config.py", "core/bayesian_memory.py")


def _hash(value: Any) -> bool:
    """Chỉ nhận SHA-256 hex Python gốc."""
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _point(point_id: str) -> str:
    """Point ID khóa mã/ngày; không cho đường dẫn trở thành định danh khoa học."""
    if type(point_id) is not str or point_id[:3] not in ("FPT", "MWG", "VCB", "VNM") or point_id[3:4] != "-":
        raise ValueError("Point ID Decision phải gồm mã và ngày ISO")
    day = point_id[4:]
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError("Ngày point Decision không chuẩn")
    return day


def _namespace(run_root: Path, fixture: bool) -> Path:
    """Run thật chỉ ghi namespace mới; fixture nằm ngoài workspace nguồn."""
    path = run_root.resolve()
    namespace = (ROOT/"outputs/bayesian_benchmark/bic_icl_v2").resolve()
    if (type(fixture) is not bool or fixture and path.is_relative_to(ROOT)
            or not fixture and (path == namespace or not path.is_relative_to(namespace))):
        raise ValueError("Thư mục Decision chồng nguồn hoặc không thuộc run revision mới")
    return path


def branch_order(phase: str, point_index: int, repeat_id: int = 0, *, task_enabled: bool = True) -> list[str]:
    """Original trước; index repeat theo mẫu đã sort, duplicate luôn là slot riêng."""
    if (phase not in ("development", "confirmation") or type(point_index) is not int or point_index < 0
            or type(repeat_id) is not int or repeat_id not in (0, 1, 2, 3) or type(task_enabled) is not bool):
        raise ValueError("Pha/index/lượt Decision không hợp lệ")
    names = list(DEVELOPMENT if phase == "development" else CONFIRMATION)
    if phase == "development" and not task_enabled:
        names = [n for n in names if not n.startswith("R_task_")]
    others = names[1:] + (["original_duplicate"] if repeat_id else [])
    shift = (point_index if repeat_id == 0 else 3*point_index+repeat_id-1) % len(others)
    return ["original", *others[shift:], *others[:shift]]


@contextmanager
def shared_stage_scope(run_root: Path, signature: str, point_id: str, source_sha256: str,
                       *, create: bool = False, fixture: bool = False) -> Iterator[StageJournal]:
    """Cùng journal cho primary/repeat; caller đưa callback vào graph hiện hữu.

    Component không tạo graph hoặc fetch dữ liệu. Runner phải kiểm namespace,
    nguồn và release trước scope; journal kiểm input/output từng node khi resume.
    """
    _point(point_id)
    if not _hash(signature) or not _hash(source_sha256) or type(create) is not bool:
        raise ValueError("Binding upstream revision không hợp lệ")
    directory = safe_path(_namespace(run_root, fixture), f"shared_stages/{point_id}")
    token = ENABLED.set(True)
    try:
        with PriorRunLock(directory, signature), recovery_scope():
            path, marker = safe_path(directory, "journal.json"), safe_path(directory, "ready.json")
            binding = {"namespace": "bic_icl_v2", "run_signature": signature,
                       "point_id": point_id, "source_sha256": source_sha256}
            if marker.exists() and not path.exists():
                raise ValueError("Thiếu journal upstream đã khóa; không tạo lại để gọi node")
            journal = StageJournal(path, binding, create=create)
            if not marker.exists() and (not create or journal.document["nodes"]):
                raise ValueError("Thiếu marker upstream đã bắt đầu")
            _write_once(marker, {"binding_sha256": digest(binding)})
            yield journal
    finally:
        ENABLED.reset(token)


class DecisionBlock:
    """Một block point/repeat, dùng client audited và không thực hiện evaluation.

    W10-06 cấp prompt đã render, shared bundle và verifier nguồn semantic.
    Component khóa tất cả request trước HTTP, bảo toàn thứ tự, raw và ledger;
    không là CLI/release cho phép chạy cohort thật.
    """

    def __init__(self, run_root: Path, signature: str, point_id: str, repeat_id: int, llm: Any,
                 *, language: str = "vi", fixture: bool = False) -> None:
        self.root, self.signature, self.pid = _namespace(run_root, fixture), signature, point_id
        self.day = _point(point_id)
        if (not _hash(signature) or type(repeat_id) is not int or repeat_id not in (0, 1, 2, 3)
                or language not in ("vi", "en") or type(fixture) is not bool):
            raise ValueError("Binding/lượt/ngôn ngữ Decision không hợp lệ")
        self.repeat, self.llm, self.language, self.fixture = repeat_id, llm, language, fixture
        self.transport = getattr(llm.http_client, "_transport", None)
        if not isinstance(self.transport, ResilientTransport):
            raise ValueError("Decision revision cần transport durable/pacer đã kiểm")
        if fixture:
            if not isinstance(self.transport.inner.inner, httpx.MockTransport):
                raise ValueError("Fixture Decision chỉ được dùng HTTP mock")
        self.pacer = self.transport.pacer
        self.directory = safe_path(self.root, f"decision_blocks/{repeat_id}/{point_id}")
        self.path = safe_path(self.directory, "state.json")

    def _binding(self, shared: dict[str, Any], requests: list[dict[str, Any]]) -> dict[str, Any]:
        """Tái dựng cả body/schema/model/options bằng serializer SDK thực."""
        validate_client(self.llm, "agent", MODELS, online=True)
        method_hash = hashlib.sha256((ROOT/METHOD).read_text(encoding="utf-8").encode()).hexdigest()
        if method_hash != METHOD_SHA256:
            raise ValueError("Đặc tả phương pháp đã thay đổi; cần version mới")
        required = {"reports", "current_signals", "market_regime", "prior_provenance"}
        if (type(shared) is not dict or not required.issubset(shared)
                or set(shared)-required-{"alpha_factors", "sentiment_data"}
                or type(shared["market_regime"]) is not dict or type(shared["prior_provenance"]) is not dict
                or type(shared["prior_provenance"].get("context")) is not dict
                or shared["market_regime"].get("as_of_date") != self.day
                or shared["prior_provenance"].get("context", {}).get("as_of_date") != self.day):
            raise ValueError("Shared bundle thiếu proof hoặc khác cutoff Decision")
        feature_end = shared["market_regime"].get("feature_end_date")
        if type(feature_end) is not str or date.fromisoformat(feature_end).isoformat() != feature_end or feature_end > self.day:
            raise ValueError("Regime feature vượt cutoff Decision hoặc thiếu ngày")
        if type(requests) is not list:
            raise ValueError("Danh sách request Decision phải là list")
        records = []
        allowed = set((*DEVELOPMENT, *CONFIRMATION, "original_duplicate"))
        for request in requests:
            if type(request) is not dict or set(request) != {"branch_id", "prompt", "prefix", "base_evidence_sha256"}:
                raise ValueError("Schema request Decision revision không hợp lệ")
            name, prompt, prefix, base = (request[k] for k in ("branch_id", "prompt", "prefix", "base_evidence_sha256"))
            if (type(name) is not str or name not in allowed or type(prompt) is not str or not prompt or len(prompt) >= 6500
                    or type(prefix) is not str or len(prefix) > 600
                    or prefix and prompt.count(prefix) != 1
                    or name in ("original", "original_duplicate") and (prefix or base is not None)
                    or name not in ("original", "original_duplicate") and not _hash(base)):
                raise ValueError("Request Decision sai branch/prefix/prompt/evidence")
            records.append({**request, "contract": expected_contract(self.llm, prompt)})
        names = [r["branch_id"] for r in records]
        if (not names or names[0] != "original" or len(set(names)) != len(names)
                or ("original_duplicate" in names) != (self.repeat > 0)):
            raise ValueError("Block cần Original trước, slot duy nhất và duplicate chỉ ở repeat")
        original = records[0]
        for item in records:
            if item["branch_id"] == "original_duplicate" and item["contract"] != original["contract"]:
                raise ValueError("Duplicate phải giữ nguyên canonical request Original")
        primary = self._primary_reference(shared, records) if self.repeat else None
        return {"version": VERSION, "run_signature": self.signature, "point_id": self.pid,
            "repeat_id": self.repeat, "language": self.language, "fixture": self.fixture,
            "method_sha256": method_hash, "shared_sha256": digest(shared), "requests": records,
            "primary_reference": primary,
            "ledger_path": str(self.pacer.path.resolve()),
            "code_sha256": {n: hashlib.sha256((ROOT/n).read_text(encoding="utf-8").encode()).hexdigest() for n in DEPENDENCIES}}

    def _primary_reference(self, shared: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, str]:
        """Repeat giữ nguyên base/request/shared primary, chỉ response được lặp mới."""
        primary = DecisionBlock(self.root, self.signature, self.pid, 0, self.llm,
                                language=self.language, fixture=self.fixture)
        identity, ready = primary.directory/"identity.json", primary.directory/"ready.json"
        if not all(p.is_file() for p in (primary.path, identity, ready)):
            raise ValueError("Repeat cần primary durable đã khóa cùng point")
        source_binding = read_envelope(identity)
        if type(source_binding) is not dict or type(source_binding.get("requests")) is not list:
            raise ValueError("Identity primary thiếu danh sách request hợp lệ")
        try:
            source_requests = [{k: r[k] for k in ("branch_id", "prompt", "prefix", "base_evidence_sha256")}
                               for r in source_binding["requests"]]
        except (KeyError, TypeError) as error:
            raise ValueError("Request primary sai cấu trúc") from error
        expected = primary._binding(shared, source_requests)
        if source_binding != expected or read_envelope(ready) != {"binding_sha256": digest(expected)}:
            raise ValueError("Primary khác source/shared/request/code dùng cho repeat")
        source = read_envelope(primary.path)
        primary._validate(source, expected)
        if any(b["status"] != "complete" for b in source["branches"].values()):
            raise ValueError("Primary chưa complete; không chạy repeat")
        by_name = {r["branch_id"]: r for r in expected["requests"]}
        if {r["branch_id"] for r in records}-{"original_duplicate"} != set(by_name):
            raise ValueError("Repeat phải giữ đủ ma trận primary và thêm duplicate")
        for item in records:
            name = "original" if item["branch_id"] == "original_duplicate" else item["branch_id"]
            if any(item[k] != by_name[name][k] for k in ("prompt", "prefix", "base_evidence_sha256", "contract")):
                raise ValueError("Repeat thay canonical request/prefix/base của primary")
        return {"path": primary.path.relative_to(self.root).as_posix(),
                "sha256": hashlib.sha256(primary.path.read_bytes()).hexdigest()}

    @staticmethod
    def _source(records: list[dict[str, Any]], position: int) -> tuple[str, str] | None:
        """Chỉ reuse Original off hoặc cặp stats R; không alias duplicate/full."""
        target = records[position]
        name = target["branch_id"]
        if name in ("original", "original_duplicate"):
            return None
        if not target["prefix"] and target["contract"] == records[0]["contract"]:
            return "original", "shared_original"
        pair = {"R_pool_stats_only", "R_task_stats_only"}
        if name in pair:
            for source in records[:position]:
                if (source["branch_id"] in pair and source["contract"] == target["contract"]
                        and source["base_evidence_sha256"] == target["base_evidence_sha256"]):
                    return source["branch_id"], "stats_alias"
        return None

    def _output(self, output: dict[str, Any], request: dict[str, Any]) -> None:
        """So raw với normalized, giữ horizon và không nhận field evaluation."""
        if set(output) != {"messages", "decision_prompt", "final_trade_decision"} or output["decision_prompt"] != request["prompt"]:
            raise ValueError("Output Decision khác prompt hoặc chứa field ngoài hợp đồng")
        normalized = _checked_response(output, None, self.language)
        if normalized.get("forecast_horizon") != "T+2.5":
            raise ValueError("Horizon Decision khác hợp đồng T+2.5")

    def _slot(self, name: str, attempt_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Slot audited dùng cùng UUID cho mọi HTTP retry/format repair/resume."""
        return {"run_signature": self.signature, "point_id": self.pid, "branch_id": name,
            "repeat_id": self.repeat, "checkpoint_attempt_id": attempt_id,
            "prompt_sha256": request["contract"]["prompt_sha256"]}

    def _pending_cache(self, ledger: dict[str, Any], name: str, attempt_id: str, request: dict[str, Any]) -> None:
        """Kiểm integrity trước SDK để lỗi cache không bị bọc thành lỗi kết nối."""
        slot = self._slot(name, attempt_id, request)
        for row in ledger["requests"]:
            if row.get("checkpoint_attempt_id") != attempt_id:
                continue
            if any(row.get(k) != slot[k] for k in ("run_signature", "point_id", "branch_id")):
                raise ValueError("HTTP unknown khác point/nhánh/run của scientific UUID")
            audit = row.get("improvement_audit")
            if audit is not None and (audit.get("slot") != slot or audit.get("request") != request["contract"]):
                raise ValueError("HTTP unknown khác body/schema/repeat đã khóa")
            if row.get("status") != 200:
                continue
            path = safe_path(self.transport.cache_root, str(UUID(row["id"]))+".json")
            proof = row.get("durable_response")
            if not path.exists():
                if proof is not None:
                    raise ValueError("Thiếu response cache durable đã được xác nhận")
                continue
            if proof is not None and proof != {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}:
                raise ValueError("Response cache thay đổi checksum trước SDK")
            cached = read_envelope(path)
            if (set(cached) != {"version", "request", "body_base64", "headers"}
                    or cached["version"] != RECOVERY_VERSION or cached["request"] != request["contract"]
                    or type(cached["headers"]) is not dict or type(cached["body_base64"]) is not str
                    or set(cached["headers"])-{"content-type", "x-request-id"}
                    or hashlib.sha256(base64.b64decode(cached["body_base64"], validate=True)).hexdigest()
                        != (audit or {}).get("response", {}).get("body_sha256")):
                raise ValueError("Response cache khác body/response/header đã audit")

    def _validate(self, document: dict[str, Any], binding: dict[str, Any]) -> None:
        """Tái kiểm toàn block trước HTTP tiếp theo, kể cả alias đã complete."""
        try:
            if set(document) != {"binding", "branches"} or document["binding"] != binding:
                raise ValueError("Block Decision khác identity/shared/request/code")
            records = binding["requests"]
            branches = document["branches"]
            if list(branches) != [r["branch_id"] for r in records]:
                raise ValueError("Block Decision khác thứ tự/slot đã khóa")
            stopped = False
            for position, request in enumerate(records):
                name = request["branch_id"]; item = branches[name]
                if (set(item) != {"status", "attempts", "resumes", "decision_origin", "source", "output"}
                        or item["status"] not in ("planned", "unknown", "complete")):
                    raise ValueError("Schema/trạng thái slot Decision không hợp lệ")
                if stopped and item["status"] != "planned":
                    raise ValueError("Slot sau chạy trước khi slot trước durable")
                stopped = stopped or item["status"] != "complete"
                _attempts(item["attempts"])
                if len(item["attempts"]) > 1 or any(a["authorization"] is not None for a in item["attempts"]):
                    raise ValueError("Phục hồi revision chỉ dùng cùng một scientific UUID")
                if type(item["resumes"]) is not list:
                    raise ValueError("Audit resume phải là list")
                for stamp in item["resumes"]:
                    if type(stamp) is not str or not stamp.endswith("Z"):
                        raise ValueError("Timestamp resume không hợp lệ")
                    datetime.fromisoformat(stamp)
                source = self._source(records, position)
                if item["status"] == "planned":
                    if item != self._empty():
                        raise ValueError("Slot planned chứa response/attempt giả")
                elif source is not None:
                    source_name, origin = source
                    parent = branches[source_name]
                    if (item["status"] != "complete" or parent["status"] != "complete"
                            or item["attempts"] or item["resumes"] or item["decision_origin"] != origin
                            or item["source"] != {"branch_id": source_name, "sha256": digest(parent)}
                            or item["output"] != parent["output"]):
                        raise ValueError("Alias khác nguồn durable/request hoặc giả HTTP attempt")
                else:
                    expected_origin = "independent_duplicate" if name == "original_duplicate" else "llm"
                    attempts = item["attempts"]
                    if (len(attempts) != 1 or item["decision_origin"] != expected_origin or item["source"] is not None
                            or attempts[0]["status"] != item["status"] or attempts[0]["output"] != item["output"]):
                        raise ValueError("Slot vật lý thiếu UUID/output hoặc tự đổi nguồn")
                    if item["status"] == "complete":
                        self._output(item["output"], request)
                        ledger = json.loads(self.pacer.path.read_text(encoding="utf-8"))
                        verify_attempt_audit(ledger, self._slot(name, attempts[0]["attempt_id"], request),
                            expected=request["contract"], raw_message=item["output"]["messages"][0]["data"])
                    elif self.pacer.path.exists():
                        ledger = json.loads(self.pacer.path.read_text(encoding="utf-8"))
                        self._pending_cache(ledger, name, attempts[0]["attempt_id"], request)
        except (KeyError, TypeError, AttributeError, IndexError) as error:
            raise ValueError("Cấu trúc checkpoint Decision không hợp lệ") from error

    @staticmethod
    def _empty() -> dict[str, Any]:
        """Planned không mang quyết định CASH hoặc response mặc định."""
        return {"status": "planned", "attempts": [], "resumes": [],
            "decision_origin": None, "source": None, "output": None}

    def _invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        """Dùng schema/normalizer/wrapper legacy, format repair chung invocation."""
        structured = self.llm.with_structured_output(decision_agent.TradeDecisionOutput, method="json_schema", include_raw=True)
        for index in range(decision_agent.DECISION_FORMAT_ATTEMPTS):
            result = decision_agent._invoke_with_retry(structured.invoke, request["prompt"])
            try:
                normalized, raw = decision_agent._normalize_structured_result(result, self.language)
                output = encode_output({"messages": [raw], "final_trade_decision": normalized, "decision_prompt": request["prompt"]})
                self._output(output, request)
                return output
            except ValueError:
                if index == decision_agent.DECISION_FORMAT_ATTEMPTS-1:
                    raise
                print("[Decision revision] Output sai schema; sửa định dạng trong cùng UUID.", flush=True)
        raise ValueError("Decision không trả output hợp lệ")

    def run(self, shared: dict[str, Any], requests: list[dict[str, Any]], *, verify_sources: Callable[[], None],
            create: bool = False, verify_only: bool = False) -> dict[str, Any]:
        """Khóa block, persist intent trước HTTP, resume đúng UUID và trả bản sao."""
        if (not callable(verify_sources) or type(create) is not bool or type(verify_only) is not bool
                or CURRENT.get() is not None):
            raise ValueError("Decision block cần verifier và invocation scope độc lập")
        shared, requests = copy_prior_json(shared), copy_prior_json(requests)
        verify_sources()
        binding = self._binding(shared, requests)
        with PriorRunLock(safe_path(self.root, "decision_lock"), self.signature):
            identity, ready = self.directory/"identity.json", self.directory/"ready.json"
            if ready.exists() and (not identity.exists() or not self.path.exists()):
                raise ValueError("Thiếu identity/state đã khóa; không khởi tạo lại để replay")
            if self.path.exists() and not ready.exists():
                previous = read_envelope(self.path)
                if (type(previous.get("branches")) is not dict
                        or any(type(b) is not dict or b.get("status") != "planned" for b in previous["branches"].values())):
                    raise ValueError("Thiếu marker của block đã bắt đầu; dừng thay vì tự khởi tạo")
            if not identity.exists() and (not create or verify_only):
                raise ValueError("Chưa khởi tạo block Decision")
            if identity.exists() and read_envelope(identity) != binding:
                raise ValueError("Identity Decision đã khóa khác request hiện tại")
            if not verify_only:
                _write_once(identity, binding)
                if not self.path.exists():
                    if ready.exists():
                        raise ValueError("Thiếu state đã khóa; không khởi tạo lại để replay")
                    _write_once(self.path, {"binding": binding,
                        "branches": {r["branch_id"]: self._empty() for r in binding["requests"]}})
                _write_once(ready, {"binding_sha256": digest(binding)})
            if not ready.exists() or read_envelope(ready) != {"binding_sha256": digest(binding)} or not self.path.exists():
                raise ValueError("Block Decision chưa có đủ marker/state đã khóa")
            document = read_envelope(self.path)
            self._validate(document, binding)
            for position, request in enumerate(binding["requests"]):
                name = request["branch_id"]; item = document["branches"][name]
                if item["status"] == "complete" or verify_only:
                    continue
                verify_sources()
                if self._binding(shared, requests) != binding:
                    raise ValueError("Client/request đổi trước invocation")
                self._validate(document, binding)
                source = self._source(binding["requests"], position)
                if source is not None:
                    source_name, origin = source
                    parent = document["branches"][source_name]
                    if parent["status"] != "complete":
                        raise ValueError("Nguồn alias chưa durable")
                    item.update(status="complete", decision_origin=origin,
                        source={"branch_id": source_name, "sha256": digest(parent)}, output=deepcopy(parent["output"]))
                else:
                    if item["status"] == "unknown":
                        item["resumes"].append(utc_now())
                    else:
                        item.update(status="unknown", decision_origin="independent_duplicate" if name == "original_duplicate" else "llm")
                        item["attempts"].append({"attempt_id": str(uuid4()), "started_at": utc_now(), "status": "unknown",
                            "output": None, "latency_seconds": None, "authorization": None})
                    save_envelope(self.path, document)
                    attempt = item["attempts"][0]
                    token, slot = ENABLED.set(True), SLOT.set(self._slot(name, attempt["attempt_id"], request))
                    try:
                        with recovery_scope(), invocation_scope("decision_"+name) as budget:
                            budget.run_signature, budget.point_id, budget.branch_id = self.signature, self.pid, name
                            budget.checkpoint_attempt_id = attempt["attempt_id"]
                            output = self._invoke(request)
                        item.update(status="complete", output=output)
                        attempt.update(status="complete", output=deepcopy(output), latency_seconds=float(budget.elapsed_seconds))
                    finally:
                        SLOT.reset(slot)
                        ENABLED.reset(token)
                save_envelope(self.path, document)
            verify_sources()
            if self._binding(shared, requests) != binding:
                raise ValueError("Client/request đổi trong invocation")
            self._validate(document, binding)
            return copy_prior_json(document)
