"""Quota ngày do provider quyết định; mở rộng vận hành không sửa mã nghiên cứu đã khóa."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import re
from pathlib import Path
from typing import Any, Iterator

from core.bayesian_memory import atomic_write_json, read_json
from core.groq_pacing import GroqPacer, MODEL_LIMITS
from core.prior_backtest import canonical_hash
from core.prior_run_lock import safe_path, utc_now
from core.research_cohort import read_envelope, save_envelope

POLICY = "provider_daily_quota_v1"
AMENDMENT = "provider_quota_amendment_v1"
AMENDMENT_FILE = "provider_quota_amendment.json"
EXTENSION_FILES = ("core/provider_quota.py", "scripts/run_provider_validation.py")
TECHNICAL_GATES = "docs/plan/week7/validation_gates/technical_gates_provider_v1.json"
OPERATIONS = {"daily_admission": "PROVIDER_AUTHORITATIVE", "cooldown_scope": "CREDENTIAL_SHA256",
    "minute_pacing": "UNCHANGED_PER_CREDENTIAL", "http_attempts": 3, "wait_seconds": 120,
    "unknown_replay": "EXACT_UUID_MANUAL_EXCEPT_PROVEN_QUOTA_REJECTION", "methodology": "UNCHANGED"}


def extension_code(root: Path) -> dict[str, str]:
    """Khóa riêng mã mở rộng bằng text LF, không giả mạo hash của runner cũ."""
    return {name: hashlib.sha256(safe_path(root, name).read_text(encoding="utf-8").encode()).hexdigest()
            for name in EXTENSION_FILES}


def _sha(path: Path) -> str:
    """Băm byte bằng chứng; không dùng với credential."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ledger_records(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """ID duy nhất là điều kiện nối usage; không ghi đè hoặc loại request lịch sử."""
    records = ledger["requests"]
    ids = [row.get("id") for row in records]
    if any(type(value) is not str or not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("Ledger thiếu hoặc trùng request ID")
    return dict(zip(ids, records))


def prepare_amendment(root: Path, plan_path: Path, run: Path, ledger_path: Path) -> dict[str, Any]:
    """Khóa cutover offline; caller đã verify toàn cohort và đang giữ khóa ledger/run."""
    from core.candidate_cohort import _code
    from core.research_input_lock import runtime_identity
    root, run = root.resolve(), run.resolve()
    if plan_path.name.startswith(".env") or ledger_path.name.startswith(".env"):
        raise ValueError("Amendment không được đọc credential")
    plan = read_envelope(plan_path)
    identity = read_envelope(run / "cohort.json")
    if (plan["plan_version"] != "research_cohort_plan_v3" or plan["split"] != "development_2023"
            or plan["code_sha256"] != _code() or plan["runtime"] != runtime_identity()
            or identity["plan"] != plan or identity["ledger_path"] != str(ledger_path.resolve())):
        raise ValueError("Amendment chỉ nối development đúng code/runtime/ledger đã khóa")
    target = run / AMENDMENT_FILE
    if target.exists():
        return verify_amendment(root, plan_path, run, ledger_path)
    protected = {}
    for path in (*sorted((run / "v1").rglob("*.json")), *sorted((run / "candidates").rglob("*.json"))):
        if path.name.startswith("run.") or path.name in ("results.json", "identity.json"):
            continue
        doc = read_json(path)
        payload = doc.get("payload", doc)
        attempts = payload.get("attempts", [])
        complete = payload.get("status") == "complete" or bool(attempts and attempts[-1]["status"] == "complete")
        if payload.get("version") == "agent_stage_journal_v1":
            nodes = payload["nodes"]
            complete = len(nodes) == 4 and all(node["attempts"][-1]["status"] == "complete" for node in nodes.values())
        if complete:
            protected[path.relative_to(run).as_posix()] = _sha(path)
    ledger = read_json(ledger_path)
    from core.candidate_selection import read_technical_gates
    gates_path = safe_path(root, TECHNICAL_GATES)
    if read_technical_gates(gates_path, {"code_sha256":plan["code_sha256"],"runtime":plan["runtime"]})["status"] != "PASS":
        raise ValueError("Bốn gate mở rộng chưa PASS")
    payload = {"amendment_version": AMENDMENT, "created_at_utc": utc_now(), "policy": OPERATIONS,
        "plan": {"path": plan_path.resolve().relative_to(root).as_posix(), "sha256": _sha(plan_path)},
        "run": {"path": run.relative_to(root).as_posix(), "cohort_sha256": _sha(run / "cohort.json"),
                "run_signature": canonical_hash(identity)},
        "ledger": {"path": ledger_path.resolve().relative_to(root).as_posix(), "initial_sha256": _sha(ledger_path),
                   "baseline_requests": {key: canonical_hash(value) for key, value in _ledger_records(ledger).items()}},
        "method_code_sha256": plan["code_sha256"], "runtime": plan["runtime"],
        "extension_code_sha256": extension_code(root), "protected_files": protected,
        "technical_gates": {"path":TECHNICAL_GATES,"sha256":_sha(gates_path)}}
    save_envelope(target, payload)
    return verify_amendment(root, plan_path, run, ledger_path)


def verify_amendment(root: Path, plan_path: Path, run: Path, ledger_path: Path) -> dict[str, Any]:
    """Kiểm cả nguồn mở rộng và bằng chứng cutover trước khi đọc key hoặc tiếp tục API."""
    from core.candidate_cohort import _code
    from core.research_input_lock import runtime_identity
    root, run = root.resolve(), run.resolve()
    if plan_path.name.startswith(".env") or ledger_path.name.startswith(".env"):
        raise ValueError("Amendment không được đọc credential")
    doc = read_envelope(run / AMENDMENT_FILE)
    required = {"amendment_version", "created_at_utc", "policy", "plan", "run", "ledger",
                "method_code_sha256", "runtime", "extension_code_sha256", "protected_files", "technical_gates"}
    if set(doc) != required or doc["amendment_version"] != AMENDMENT or doc["policy"] != OPERATIONS:
        raise ValueError("Schema/policy amendment khác bản đã đăng ký")
    plan = read_envelope(plan_path)
    identity = read_envelope(run / "cohort.json")
    if (doc["plan"] != {"path": plan_path.resolve().relative_to(root).as_posix(), "sha256": _sha(plan_path)}
            or doc["run"] != {"path": run.relative_to(root).as_posix(), "cohort_sha256": _sha(run / "cohort.json"),
                              "run_signature": canonical_hash(identity)}
            or identity["plan"] != plan or plan["split"] != "development_2023"
            or doc["method_code_sha256"] != plan["code_sha256"] or plan["code_sha256"] != _code()
            or doc["runtime"] != plan["runtime"] or plan["runtime"] != runtime_identity()
            or doc["extension_code_sha256"] != extension_code(root)
            or doc["ledger"]["path"] != ledger_path.resolve().relative_to(root).as_posix()
            or identity["ledger_path"] != str(ledger_path.resolve())):
        raise ValueError("Amendment khác plan/run/code/runtime/ledger đã khóa")
    from core.candidate_selection import read_technical_gates
    gates_path = safe_path(root, TECHNICAL_GATES)
    if (doc["technical_gates"] != {"path":TECHNICAL_GATES,"sha256":_sha(gates_path)} or
            read_technical_gates(gates_path, {"code_sha256":plan["code_sha256"],"runtime":plan["runtime"]})["status"] != "PASS"):
        raise ValueError("Receipt gate mở rộng khác bản đã khóa")
    for name, checksum in doc["protected_files"].items():
        if Path(name).name.startswith(".env"):
            raise ValueError("Bằng chứng amendment không được trỏ vào credential")
        if _sha(safe_path(run, name)) != checksum:
            raise ValueError("Checkpoint complete trước cutover đã bị sửa")
    records = _ledger_records(read_json(ledger_path))
    if any(key not in records or canonical_hash(records[key]) != checksum
           for key, checksum in doc["ledger"]["baseline_requests"].items()):
        raise ValueError("Usage lịch sử bị xóa hoặc sửa sau cutover")
    amendment_sha = _sha(run / AMENDMENT_FILE)
    for key, record in records.items():
        if key not in doc["ledger"]["baseline_requests"] and (record.get("daily_policy") != POLICY
                or record.get("operational_amendment_sha256") != amendment_sha
                or not re.fullmatch(r"[0-9a-f]{64}", record.get("credential_scope", ""))):
            raise ValueError("Request sau cutover thiếu audit của entrypoint quota provider")
    return doc


def rejected_attempts(run: Path, ledger_path: Path) -> list[str]:
    """Chỉ replay intent đã chứng minh bị quota từ chối; không suy từ transport_error."""
    ledger = read_json(ledger_path)
    stop = ledger.get("last_stop") or {}
    approval_path = run / "replay_authorizations.json"
    approved = read_envelope(approval_path)["attempts"] if approval_path.exists() else {}
    result = []
    for path in (*sorted((run / "v1").rglob("*.json")), *sorted((run / "candidates").rglob("*.json"))):
        doc = read_json(path)
        doc = doc.get("payload", doc)
        groups = [doc.get("attempts", [])]
        groups.extend(branch.get("attempts", []) for branch in doc.get("branches", {}).values())
        groups.extend(node.get("attempts", []) for node in doc.get("nodes", {}).values())
        signature = doc.get("run_signature", doc.get("binding", {}).get("run_signature"))
        point_id = doc.get("point_id", doc.get("binding", {}).get("point_id"))
        for attempts in groups:
            if (not attempts or attempts[-1].get("status") not in ("unknown", "running", "failed")
                    or attempts[-1].get("authorization") is not None):
                continue
            attempt = attempts[-1]["attempt_id"]
            if attempt in approved:
                continue
            rows = [row for row in ledger["requests"] if row.get("checkpoint_attempt_id") == attempt]
            refused = bool(rows) and all(row.get("status") == 429 and row.get("run_signature") == signature
                and row.get("point_id") == point_id for row in rows)
            not_sent = (not rows and stop.get("checkpoint_attempt_id") == attempt
                and stop.get("point_id") == point_id and stop.get("run_signature") == signature
                and stop.get("daily_policy") == POLICY and stop.get("reason") == "PROVIDER_DAILY_QUOTA")
            if refused or not_sent:
                result.append(attempt)
    if len(result) != len(set(result)):
        raise ValueError("UUID quota từ chối trùng ở nhiều checkpoint")
    return result


class ProviderQuotaPacer(GroqPacer):
    """Giữ ledger tổng; quota ngày do Groq, cửa sổ phút/cooldown theo key ẩn danh."""

    def __init__(self, path: Path, *, credential: str, amendment_sha256: str, **kwargs: Any) -> None:
        if not credential or type(credential) is not str:
            raise ValueError("Thiếu credential cho quota provider")
        self.credential_scope = hashlib.sha256((POLICY + "\0" + credential).encode()).hexdigest()
        self.amendment_sha256 = amendment_sha256
        self._scope_depth = 0
        super().__init__(path, **kwargs)
        _ledger_records(self.state)
        self._all_requests = self.state["requests"]

    @contextmanager
    def _scoped(self) -> Iterator[None]:
        """Chỉ lọc lúc admission; telemetry và preflight luôn nhìn toàn lịch sử."""
        if self._scope_depth:
            yield
            return
        self._scope_depth = 1
        self.state["requests"] = [row for row in self._all_requests if row.get("credential_scope") == self.credential_scope]
        try:
            yield
        finally:
            self.state["requests"] = self._all_requests
            self._scope_depth = 0

    def save(self) -> None:
        """Nối request mới vào ledger tổng trước HTTP; không xóa usage của key khác."""
        if self._scope_depth:
            ids = {row["id"] for row in self._all_requests}
            for row in self.state["requests"]:
                if row["id"] not in ids:
                    row.update(credential_scope=self.credential_scope, daily_policy=POLICY,
                               operational_amendment_sha256=self.amendment_sha256)
                    self._all_requests.append(row)
                    ids.add(row["id"])
        proof = self.state.get("preflight", {})
        ids = proof.get("request_ids", [])
        by_id = {row["id"]: row for row in self._all_requests}
        if ids and all(by_id.get(key, {}).get("credential_scope") == self.credential_scope for key in ids):
            proof["credential_scope"] = self.credential_scope
        atomic_write_json(self.path, {**self.state, "requests": self._all_requests})

    def daily_budget(self, model: str, requests: int, tokens: int) -> dict[str, int]:
        """Usage ngày chỉ là thông tin; không phát DAILY_QUOTA từ ledger local."""
        with self._scoped():
            rows = [row for row in self.state["requests"] if row["model"] == model and row["started_at"] > self.clock() - 86400]
            charged = sum(row.get("total_tokens") or row["reserved_tokens"] for row in rows)
            return {"remaining_requests": max(0, MODEL_LIMITS[model]["rpd"] - len(rows)),
                    "remaining_tokens": max(0, MODEL_LIMITS[model]["tpd"] - charged),
                    "budget_requests": requests, "budget_tokens": tokens}

    def check_provider(self, model: str) -> None:
        """Giữ kiểm header/estimator của provider, chỉ dùng lịch sử key hiện hành."""
        with self._scoped():
            super().check_provider(model)

    def reserve(self, model: str, tokens: int) -> dict[str, Any]:
        """Giữ nguyên pacing phút, trần token/request và retry budget gốc."""
        with self._scoped():
            return super().reserve(model, tokens)

    def before_point(self) -> None:
        """Không giữ điểm mới vì ngân sách ngày local; provider vẫn có quyền từ chối."""
        with self._scoped():
            super().before_point()

    def stop(self, reason: str, model: str, *, resume_at: float | None = None, **details: Any) -> None:
        """Lưu nguyên nhân dừng cùng scope ẩn danh; không ghi credential."""
        from core.research_invocation import CURRENT
        invocation = CURRENT.get()
        if invocation is not None:
            details.update(checkpoint_attempt_id=invocation.checkpoint_attempt_id, point_id=invocation.point_id,
                           run_signature=invocation.run_signature)
        super().stop(reason, model, resume_at=resume_at, credential_scope=self.credential_scope,
                     daily_policy=POLICY, **details)
