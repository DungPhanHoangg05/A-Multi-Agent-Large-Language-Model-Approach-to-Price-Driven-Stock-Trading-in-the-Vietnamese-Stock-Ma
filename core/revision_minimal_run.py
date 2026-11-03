"""Queue whitelist chung cho T02/T03, khóa key xuyên run và resume raw offline."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack, closing
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any

from langchain_core.messages import messages_to_dict
from core.revision72_provider import RoutedLLM, scientific_context
from core.revision72_quota import PoolArchive, PoolLedger
from core.revision72_run import CachedLLM
from core.revision_call_archive import StudyLock
from core.revision_common_study import digest, read_json, write_json
from core.revision_r4_factorial import actual_text
from core.revision_r4_run import perform_call
from core.revision_minimal_bank import (
    R1, R4, collect, legacy_guard, parent_for, point_path, require, sha,
    verify_manifest, verify_record, verify_request, verify_response,
)


class SharedLedger(PoolLedger):
    """Một ledger mới cho mọi treatment; thêm khóa key tại các run nguồn cũ."""

    def __init__(self, path: Path, identity: str, root: Path, **kwargs: Any) -> None:
        self.root, self.held = root, {}
        super().__init__(path, identity, **kwargs)

    def acquire(self, model: str, preferred: int, owner: str, allowed: list[int]) -> int | None:
        """Lease dùng chung trước, rồi khóa cùng key tại cả hai run chart nguồn."""
        org = super().acquire(model, preferred, owner, allowed)
        if org is None:
            return None
        stack = ExitStack()
        try:
            for folder in (R1, R4, Path("outputs/revision/r1_72h_run_v2"), Path("outputs/revision/r4_value_run_v1")):
                stack.enter_context(StudyLock(self.root / folder / f"provider_locks/org{org}.lock"))
        except RuntimeError:
            stack.close()
            super().release(org, owner)
            return None
        except BaseException:
            stack.close()
            super().release(org, owner)
            raise
        self.held[owner] = stack
        return org

    def release(self, org: int, owner: str) -> None:
        """Nhả lease và mọi khóa thuộc đúng invocation, kể cả khi provider báo lỗi."""
        try:
            super().release(org, owner)
        finally:
            stack = self.held.pop(owner, None)
            if stack is not None:
                stack.close()


class WhitelistArchive(PoolArchive):
    """Chặn sai job/message/parameters ngay callback trước khi SDK gửi request."""

    def __init__(self, *args: Any, manifest: dict, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.manifest = manifest
        self.whitelist = {digest(j["context"]): j for j in manifest["jobs"] if j["reuse"] is None}

    def on_chat_model_start(self, serialized: dict, messages: list, *, run_id: object, **kwargs: Any) -> None:
        """Không có whitelist thì không reserve attempt hoặc gọi provider."""
        context = scientific_context(self.context)
        job = self.whitelist.get(digest(context))
        require(job is not None, "Callback chặn job ngoài whitelist hoặc job đã reuse")
        actual = {"messages": [messages_to_dict(batch) for batch in messages]}
        require(actual_text(actual) == job["prompt"] and len(job["prompt"]) < 6500, "Callback chặn message/budget sai")
        metadata_keys = {"ls_provider", "ls_model_name", "ls_temperature", "ls_max_tokens", "langgraph_node"}
        parameter_keys = {"model", "max_tokens", "temperature", "stop", "tools", "tool_choice", "response_format", "reasoning_format"}
        contract = {"model_metadata": {k: v for k, v in kwargs.get("metadata", {}).items() if k in metadata_keys},
                    "invocation_parameters": {k: v for k, v in kwargs.get("invocation_params", {}).items() if k in parameter_keys}}
        require(contract == job["request_contract"], "Callback chặn model/parameters/schema sai")
        require(self.context.get("execution_epoch") == self.manifest["sha256"], "Callback sai execution epoch")
        super().on_chat_model_start(serialized, messages, run_id=run_id, **kwargs)


def verify_calls(run: Path, manifest: dict) -> dict:
    """Kiểm toàn bộ attempts mới, kể cả lỗi và interruption trước checkpoint."""
    jobs = {digest(j["context"]): j for j in manifest["jobs"] if j["reuse"] is None}
    requests, responses, errors, interrupted = {}, 0, 0, []
    for path in sorted(run.glob("shards/org*/calls/*.request.json")):
        from core.revision72_run import checked
        req = checked(path)
        job = jobs.get(digest(scientific_context(req["context"])))
        require(job is not None, "Raw ngoài whitelist hoặc thuộc job reuse")
        require(path.parent.parent.name == f"org{job['worker']}", "Raw nằm sai shard queue")
        req = verify_request(path, job["context"], job["prompt"], manifest["sha256"], job["request_contract"], manifest["sha256"])
        attempt = req["attempt_id"]
        require(attempt not in requests, "Raw request ID trùng")
        requests[attempt] = req
        response = path.with_name(f"{attempt}.response.json")
        error = path.with_name(f"{attempt}.error.json")
        require(not (response.exists() and error.exists()), "Attempt có cả response và error")
        if response.exists():
            verify_response(response, req); responses += 1
        elif error.exists():
            value = read_json(error)
            require(value["attempt_id"] == attempt and value["context"] == req["context"], "Error sai request/context")
            errors += 1
        else:
            interrupted.append(attempt)
    for suffix in ("response", "response_digest", "error"):
        for path in run.glob(f"shards/org*/calls/*.{suffix}.json"):
            require(path.name.removesuffix(f".{suffix}.json") in requests, "Raw orphan")
    ledger_path = run / "quota.sqlite3"
    require(ledger_path.exists(), "Thiếu ledger; không tự reset counters")
    with closing(sqlite3.connect(ledger_path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        require(db.execute("PRAGMA integrity_check").fetchall() == [("ok",)], "Ledger SQLite lỗi")
        require(db.execute("SELECT value FROM identity").fetchall() == [(manifest["sha256"],)], "Ledger sai identity")
        rows = db.execute("SELECT id,org,stage,model FROM attempts").fetchall()
        require(set(requests) <= {r[0] for r in rows}, "Raw không có reservation ledger")
        for attempt, org, stage, model in rows:
            if attempt in requests:
                c = requests[attempt]["context"]
                require((org, stage, model) == (c["provider_org"], c["stage"], c["model"]), "Ledger sai routing")
    return {"new_attempts": len(rows), "archived_requests": len(requests), "responses": responses, "errors": errors,
            "interrupted_request_ids": interrupted, "reserved_before_archive_ids": sorted({r[0] for r in rows} - set(requests))}


def recover_temporary(root: Path, run: Path, manifest: dict) -> None:
    """Chỉ phục hồi checkpoint tạm đã verify; không gọi lại successful raw response."""
    allowed = {point_path(run, j).with_suffix(".tmp").resolve(): j for j in manifest["jobs"] if j["reuse"] is None}
    for path in run.glob("shards/org*/decisions/*.tmp"):
        job = allowed.get(path.resolve())
        require(job is not None and not path.with_suffix(".json").exists(), "Checkpoint tạm ngoài lịch/trùng final")
        verify_record(path, job, parent_for(manifest, job), manifest["sha256"], manifest["sha256"])
        path.rename(path.with_suffix(".json"))


def status(root: Path, run: Path, manifest: dict) -> dict:
    """Mẫu số mới cố định 375; không đánh dấu complete cho hai run lịch sử."""
    records = collect(root, run, manifest)
    done = {r["job_id"] for r in records}
    phases = {phase: {"expected": sum(j["phase"] == phase for j in manifest["jobs"]),
                      "complete": sum(r["phase"] == phase for r in records),
                      "missing": sum(j["phase"] == phase and j["id"] not in done for j in manifest["jobs"])}
              for phase in ("main", "upstream", "factorial")}
    return {"expected": len(manifest["jobs"]), "complete": len(records), "missing": len(manifest["jobs"]) - len(records),
            "reused": sum(r["origin"] == "reuse" for r in records), "phases": phases,
            "new_calls": verify_calls(run, manifest), "new_vision_calls": 0,
            "temporary_checkpoints": [p.relative_to(run).as_posix() for p in run.glob("shards/org*/decisions/*.tmp")],
            "missing_jobs": [{k: j[k] for k in ("id", "phase", "worker", "context")} for j in manifest["jobs"] if j["id"] not in done]}


def worker(root: Path, run: Path, manifest: dict, slot: int, stop: threading.Event,
           keys: list[str], factory: Any = RoutedLLM) -> None:
    """Một worker lưu một shard; mọi worker dùng cùng ledger và pool năm key."""
    from agents.decision_agent import TradeDecisionOutput
    done = {r["job_id"] for r in collect(root, run, manifest)}
    jobs = [j for j in manifest["jobs"] if j["worker"] == slot and j["id"] not in done]
    jobs.sort(key=lambda j: (j["unit"]["date"], j["context"]["repeat"], j["id"]))
    if not jobs:
        return
    shard = run / f"shards/org{slot}"
    with StudyLock(shard / "worker.lock"):
        ledger = SharedLedger(run / "quota.sqlite3", manifest["sha256"], root)
        archive = WhitelistArchive(shard, manifest["sha256"], keys[slot - 1], ledger, slot, 0, manifest=manifest)
        execution = manifest["execution"]
        delegate = factory(archive, keys, slot, {"model": execution["model"], "temperature": execution["temperature"],
                           "max_tokens": execution["max_tokens"], "max_retries": 0, "timeout": 120,
                           "reasoning_format": "hidden", "metadata": {"langgraph_node": "Decision Maker"}}, manifest["sha256"])
        llm = CachedLLM(delegate, archive).with_structured_output(TradeDecisionOutput, method="json_schema", include_raw=True)
        try:
            for job in jobs:
                if stop.is_set():
                    return
                archive.context = dict(job["context"])
                # Mọi raw dùng để replay đều đã qua verify_calls ở coordinator.
                path = point_path(run, job)
                perform_call(llm, archive, job["context"], job["prompt"], parent_for(manifest, job), path)
                verify_record(path, job, parent_for(manifest, job), manifest["sha256"], manifest["sha256"])
                print(f"Queue {slot}: {job['phase']} {job['id']} đã checkpoint.", flush=True)
        finally:
            for owner, stack in list(ledger.held.items()):
                stack.close(); ledger.held.pop(owner, None)


def run_queue(root: Path, run: Path, manifest: dict) -> None:
    """Chỉ tác giả gọi hàm này qua CLI run; các lệnh offline không tạo SDK/client."""
    from dotenv import load_dotenv
    with StudyLock(run / "runner.lock"), legacy_guard(root):
        recover_temporary(root, run, manifest)
        before = status(root, run, manifest)
        if before["missing"] == 0:
            print("Queue đã đủ 375; không đọc key hoặc gọi API.")
            return
        load_dotenv(root / ".env", override=True)
        keys = [os.getenv(f"GROQ_ORG_{i}_API_KEY", "") for i in range(1, 6)]
        require(all(keys) and len(set(keys)) == 5, "Cần năm key riêng; không gửi key qua chat")
        stop, failures = threading.Event(), []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, root, run, manifest, slot, stop, keys) for slot in range(1, 6)]
            try:
                for future in as_completed(futures):
                    try:
                        future.result()
                    except BaseException as exc:
                        stop.set(); failures.append(exc)
            except KeyboardInterrupt:
                stop.set()
                raise
        verify_manifest(root, run)
        if failures:
            raise failures[0]
        final = status(root, run, manifest)
        require(final["missing"] == 0, "Queue kết thúc nhưng còn jobs thiếu")
        print("Queue đã đủ 375 research executions; cần T04 verify/phân tích trước kết luận.")


def analyze(root: Path, run: Path, manifest: dict) -> None:
    """Xuất inventory hoàn chỉnh cho T04, tách ba scope thay vì gộp metrics sai."""
    result = status(root, run, manifest)
    require(result["missing"] == 0 and not result["temporary_checkpoints"], "Chưa đủ whitelist; không xuất analysis từ lượt dở")
    output = run / "analysis"
    require(not output.exists(), "Analysis đã có; không ghi đè release")
    records = collect(root, run, manifest)
    write_json(output / "records.json", records, True)
    write_json(output / "completion.json", {k: v for k, v in result.items() if k != "missing_jobs"}, True)
    write_json(output / "manifest.json", {"run_signature": manifest["sha256"],
               "scope": "Inventory cho T04; chưa phải bộ metrics/baseline/contrasts nghiệm thu",
               "outputs": [{"path": p.name, "sha256": sha(p)} for p in sorted(output.iterdir())]}, True)

