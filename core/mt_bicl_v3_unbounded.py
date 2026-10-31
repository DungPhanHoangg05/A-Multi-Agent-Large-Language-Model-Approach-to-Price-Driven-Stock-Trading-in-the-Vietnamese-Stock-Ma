"""Bỏ trần giờ theo chỉ đạo người dùng; bảo toàn source khoa học và run/UUID đã khóa."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
from typing import Any, Callable

from core.bayesian_memory import read_json
from core.groq_pacing import PilotStop
from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v3_budget import BudgetStop
from core.mt_bicl_v3_freeze import (CODE, MANIFEST, MANIFEST_VERSION, OUTPUT, RELEASE,
    RELEASE_VERSION, SNAPSHOT_VERSION, collect, layout)
from core.mt_bicl_v3_preflight import serialization, verify_controls
from core.mt_bicl_v3_run import DevelopmentRun, SLOT_VERSION
from core.mt_bicl_v3_wire import client
from core.prior_run_lock import PriorRunLock

POLICY = Path("docs/plan/week11/runtime_policy_v3.json")
VERSION = "utility_icl_unbounded_runtime_policy_v3"
ENTRYPOINT = "scripts/continue_mt_bicl_v3.py"
SOURCES = (ENTRYPOINT, "core/mt_bicl_v3_unbounded.py", "tests/test_mt_bicl_v3_unbounded.py")
USER_REPLY = "loại bỏ hoàn toàn phần giới hạn bộ đếm này. để người dùng chạy tự do"


class OperationalError(ValueError):
    """Thông báo vận hành tự tạo, có thể hiển thị mà không lộ lỗi SDK/credential."""


def byte_sha(path: Path) -> str:
    """Hash byte bằng chứng, không đọc credential."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_bytes(root: Path, revision: str, name: str) -> bytes:
    """Đọc đúng object Git, không checkout/ghi đè file khoa học đang chạy."""
    return subprocess.check_output(["git", "show", revision+":"+name], cwd=root, stderr=subprocess.PIPE)


def seal(root: Path) -> None:
    """Ghi amendment một lần sau commit source; chụp counter/ledger/complete cũ không sửa byte."""
    with PriorRunLock(root/"outputs/bayesian_benchmark/mt_bicl_v3/runtime_budget.lock", "utility-icl-budget-v3"):
        with PriorRunLock(root/"outputs/oos_pilot/api_usage.json.lock", "shared-account-ledger-v2"):
            if (root/POLICY).exists():
                verify_policy(root)
                return
            commit = subprocess.check_output(["git", "log", "-1", "--format=%H", "--", *SOURCES], cwd=root, text=True).strip()
            for name in SOURCES:
                if git_bytes(root, commit, name) != (root/name).read_bytes():
                    raise OperationalError("Source mới chưa neo Git trước seal")
            counter = "outputs/bayesian_benchmark/mt_bicl_v3/runtime_budget.json"
            history = read_envelope(root/counter, "utility_icl_runtime_budget_v3")
            if history["active_since"] is not None: raise OperationalError("Counter cũ còn active; không sửa phiên đang chạy")
            ledger = read_json(root/"outputs/oos_pilot/api_usage.json")["requests"]
            grant = read_json(root/"docs/plan/week11/budget_v3.json")
            directory = root/OUTPUT/"run/research/slots"
            complete = {p.name: byte_sha(p) for p in sorted(directory.glob("*.json"))
                        if read_envelope(p, SLOT_VERSION)["status"] == "complete"}
            parent = (MANIFEST.as_posix(), RELEASE.as_posix(), "docs/plan/week11/protocol_v3.json", "docs/plan/week11/budget_v3.json")
            policy = {"authority": "EXPLICIT_USER_INSTRUCTION_2026_10_31", "user_reply": USER_REPLY,
                "scope": "SAME_V3_RUN_OPERATIONAL_ONLY", "runtime_hour_limit_enabled": False,
                "elapsed_counter_enabled": False, "crash_gap_charging_enabled": False,
                "calendar_changed": False, "scientific_protocol_changed": False,
                "data_stop": grant["data_stop"], "release_and_start_by": grant["release_and_start_by"],
                "source_commit": commit, "source_sha256": {name: byte_sha(root/name) for name in SOURCES},
                "parent_sha256": {name: byte_sha(root/name) for name in parent},
                "retired_counter": {"path": counter, "sha256": byte_sha(root/counter), "elapsed_seconds": history["elapsed_seconds"]},
                "ledger_baseline": {"count": len(ledger), "requests_prefix_sha256": content_hash(ledger)},
                "complete_slots_sha256": complete}
            write_envelope(root/POLICY, VERSION, policy, immutable=True)


def verify_policy(root: Path) -> dict[str, Any]:
    """Chỉ thay entrypoint vận hành đã được cho phép; mọi hash khác vẫn bắt buộc."""
    policy = read_envelope(root/POLICY, VERSION)
    if (policy["authority"] != "EXPLICIT_USER_INSTRUCTION_2026_10_31" or policy["user_reply"] != USER_REPLY
            or policy["runtime_hour_limit_enabled"] is not False or policy["elapsed_counter_enabled"] is not False
            or policy["crash_gap_charging_enabled"] is not False or policy["calendar_changed"] is not False
            or policy["scientific_protocol_changed"] is not False or policy["scope"] != "SAME_V3_RUN_OPERATIONAL_ONLY"
            or set(policy["source_sha256"]) != set(SOURCES)):
        raise OperationalError("Chính sách bỏ bộ đếm khác chỉ đạo đã khóa")
    if git_bytes(root, "HEAD", POLICY.as_posix()) != (root/POLICY).read_bytes():
        raise OperationalError("Chính sách vận hành chưa neo đúng byte Git")
    for name, checksum in policy["source_sha256"].items():
        if byte_sha(root/name) != checksum or git_bytes(root, policy["source_commit"], name) != (root/name).read_bytes():
            raise OperationalError("Source vận hành khác receipt: "+name)
    for name, checksum in policy["parent_sha256"].items():
        if byte_sha(root/name) != checksum or git_bytes(root, "HEAD", name) != (root/name).read_bytes():
            raise OperationalError("Artifact khoa học/grant cũ bị sửa: "+name)
    if byte_sha(root/policy["retired_counter"]["path"]) != policy["retired_counter"]["sha256"]:
        raise OperationalError("Lịch sử counter đã nghỉ dùng bị sửa; không reset")
    ledger = read_json(root/"outputs/oos_pilot/api_usage.json")["requests"]
    baseline = policy["ledger_baseline"]
    if (len(ledger) < baseline["count"] or len({r["id"] for r in ledger}) != len(ledger)
            or content_hash(ledger[:baseline["count"]]) != baseline["requests_prefix_sha256"]):
        raise OperationalError("Ledger/reserve trước bỏ bộ đếm bị sửa hoặc reset")
    for name, checksum in policy["complete_slots_sha256"].items():
        if byte_sha(root/OUTPUT/"run/research/slots"/name) != checksum:
            raise OperationalError("Slot complete trước amendment đã bị sửa")
    grant = read_json(root/"docs/plan/week11/budget_v3.json")
    if policy["data_stop"] != grant["data_stop"] or policy["release_and_start_by"] != grant["release_and_start_by"]:
        raise OperationalError("Amendment bộ đếm không được đổi lịch nghiên cứu")
    return policy


class RuntimeSession:
    """Giữ khóa OS và hạn lịch; không cộng/trừ/ghi bộ đếm giờ hoặc gap qua đêm."""

    def __init__(self, root: Path, stage: str, *, now: Callable[[], datetime] | None = None) -> None:
        self.root, self.stage = root, stage
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.lock: PriorRunLock | None = None
        self.policy: dict[str, Any] | None = None

    def remaining_seconds(self) -> float:
        """Chỉ còn khoảng lịch đến data stop, không còn hạn mức số giờ chạy."""
        if self.lock is None or self.policy is None: raise OperationalError("Phiên vận hành chưa mở")
        now = self.now()
        if now.tzinfo is None or now.utcoffset() is None: raise OperationalError("Đồng hồ phải có timezone")
        return max(0., (datetime.fromisoformat(self.policy["data_stop"])-now).total_seconds())

    def check(self, required_seconds: float = 0.) -> None:
        """Không dừng do18 giờ, vẫn kiểm thời gian chờ có vượt hạn lịch độc lập không."""
        if type(required_seconds) not in (int, float) or not math.isfinite(required_seconds) or required_seconds < 0:
            raise OperationalError("Thời gian chờ không hợp lệ")
        remaining = self.remaining_seconds()
        if remaining <= 0 or required_seconds > remaining:
            raise BudgetStop("Đã đến hạn lịch dữ liệu07/11; không liên quan bộ đếm số giờ")

    def checkpoint(self) -> None:
        """Checkpoint khoa học vẫn do engine ghi; counter lịch sử không được động tới."""
        self.check()

    def __enter__(self) -> RuntimeSession:
        if self.lock is not None: raise OperationalError("Không mở lồng phiên vận hành")
        self.lock = PriorRunLock(self.root/"outputs/bayesian_benchmark/mt_bicl_v3/runtime_budget.lock", "utility-icl-budget-v3")
        self.lock.__enter__()
        try:
            self.policy = verify_policy(self.root)
            self.check()
            return self
        except BaseException:
            self.__exit__()
            raise

    def __exit__(self, *args: Any) -> None:
        if self.lock is not None:
            self.lock.__exit__(None, None, None)
            self.lock = None
        self.policy = None


def legacy_module(root: Path, manifest: dict[str, Any]) -> ModuleType:
    """Tái dùng nguyên CLI đã release; chỉ tiêm session/verifier mới theo amendment tường minh."""
    source = git_bytes(root, manifest["source_commit"], ENTRYPOINT)
    if hashlib.sha256(source).hexdigest() != manifest["source_sha256"][ENTRYPOINT]:
        raise OperationalError("Entry point cũ khác source đã release")
    module = ModuleType("utility_icl_released_cli")
    module.__file__ = str(root/ENTRYPOINT)
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    module.RuntimeBudget = RuntimeSession
    module.verify = verify
    return module


def verify(root: Path, *, require_anchor: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    """Cold verify đầy đủ đầu vào khoa học; chỉ entrypoint mới có quyền thay đúng hash."""
    verify_policy(root)
    manifest = read_envelope(root/MANIFEST, MANIFEST_VERSION)
    snapshot = read_envelope(root/OUTPUT/"freeze/input_snapshot.json", SNAPSHOT_VERSION)
    if (content_hash(snapshot) != manifest["snapshot_sha256"] or layout(snapshot["protocol"]) != manifest["layout"]
            or content_hash(collect(root)) != manifest["snapshot_sha256"]):
        raise OperationalError("Snapshot/layout khác validation/upstream/PIT đã khóa")
    if set(manifest["source_sha256"]) != set(CODE): raise OperationalError("Manifest thiếu/thừa source đã khóa")
    for name, checksum in manifest["source_sha256"].items():
        frozen = git_bytes(root, manifest["source_commit"], name)
        if hashlib.sha256(frozen).hexdigest() != checksum or (name != ENTRYPOINT and (root/name).read_bytes() != frozen):
            raise OperationalError("Source khoa học khác freeze: "+name)
    if require_anchor and git_bytes(root, "HEAD", MANIFEST.as_posix()) != (root/MANIFEST).read_bytes():
        raise OperationalError("Manifest không còn neo Git")
    return manifest, snapshot


def verify_only(root: Path) -> dict[str, Any]:
    """Kiểm thật complete prefix và unknown trên bản sao journal; không key/HTTP/ghi run thật."""
    import httpx

    def reject_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Đối soát offline không được network")
    class PendingHTTP(Exception):
        """Ranh giới request đầu còn thiếu, kết thúc kiểm chứng trước credential/API."""
    previous_connect, previous_socket = socket.create_connection, socket.socket.connect
    socket.create_connection = socket.socket.connect = reject_network
    try:
        with RuntimeSession(root, "cold_verification"):
            with PriorRunLock(root/"outputs/oos_pilot/api_usage.json.lock", "shared-account-ledger-v2"):
                manifest, snapshot = verify(root)
                release = read_envelope(root/RELEASE, RELEASE_VERSION)
                if verify_controls(root, manifest, snapshot, release["control_proof"]["credential_scope"]) != release["control_proof"]:
                    raise OperationalError("Control khác release")
                ledger = read_json(root/"outputs/oos_pilot/api_usage.json")
                boundary: dict[str, Any] = {}
                with TemporaryDirectory() as temporary:
                    directory = Path(temporary)/"research"
                    shutil.copytree(root/OUTPUT/"run/research", directory)
                    runner = DevelopmentRun(directory, manifest, snapshot)
                    def stop(request: dict[str, Any], slot: dict[str, Any]) -> dict[str, Any]:
                        boundary.update(slot)
                        raise PendingHTTP
                    with httpx.Client(transport=httpx.MockTransport(reject_network)) as http:
                        llm = client(snapshot["protocol"]["decision"]["config"], http, "offline-no-credential")
                        try:
                            runner.execute(stop, lambda r: serialization(llm, r), lambda: ledger,
                                root/OUTPUT/"run/http_cache", lambda: None, lambda: None)
                        except PendingHTTP:
                            pass
                    rows = [read_envelope(p, SLOT_VERSION) for p in sorted((directory/"slots").glob("*.json"))]
                return {"status": "UNBOUNDED_RESUME_VERIFIED", "complete_slots": sum(r["status"] == "complete" for r in rows),
                        "next_slot": boundary or None, "real_HTTP_calls": 0, "hour_limit_enabled": False}
    finally:
        socket.create_connection, socket.socket.connect = previous_connect, previous_socket


def main(root: Path) -> int:
    """Giữ một lệnh resume, thêm chế độ cold verify không đọc key hoặc gọi API."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=root/".env")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.verify_only:
            result = verify_only(root)
            print(f"{result['status']}: {result['complete_slots']}/804 slot; không giới hạn số giờ; HTTP=0.")
            if result["next_slot"]:
                row = result["next_slot"]
                print(f"Tiếp tục slot={row['slot_index']+1}, point={row['point_id']}, branch={row['branch_id']}; giữ UUID hiện có.")
            return 0
        verify_policy(root)
        manifest = read_envelope(root/MANIFEST, MANIFEST_VERSION)
        print("Đã bỏ giới hạn18 giờ và tính gap crash; tiếp tục cùng run/UUID, giữ lịch sử counter cũ.", flush=True)
        legacy_module(root, manifest).main()
        return 0
    except KeyboardInterrupt:
        print("Đã dừng theo người dùng; giữ UUID/cache/reserve. Chạy lại cùng lệnh, không giới hạn bộ đếm giờ.", file=sys.stderr)
        return 3
    except BudgetStop as error:
        print(str(error), file=sys.stderr)
        return 3
    except PilotStop as error:
        import json
        try: reason = json.loads(str(error)).get("reason", "PROVIDER_STOP")
        except (ValueError, TypeError): reason = "PROVIDER_OR_INVOCATION_STOP"
        print(f"Tạm dừng: {reason}; giữ UUID/cache/ledger, chạy lại cùng lệnh.", file=sys.stderr)
        return 3
    except Exception as error:
        if isinstance(error, OperationalError):
            print(f"Dừng kiểm tra bằng chứng: {error}", file=sys.stderr)
        else:
            print(f"Tạm dừng do {type(error).__name__}; giữ UUID/cache/ledger, không in lỗi SDK có thể chứa credential.", file=sys.stderr)
        return 1
