"""Journal paired v3 với anchor động, policy bypass và resume cùng UUID."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

from core.mt_bicl_bank import content_hash
from core.mt_bicl_v2_io import read_envelope, write_envelope
from core.mt_bicl_v3_contracts import REVISION_BRANCHES
from core.mt_bicl_v3_decision import canonical_request
from core.mt_bicl_v3_policy import apply_revision, resolve_anchor
from core.mt_bicl_v3_wire import audit_attempt

SLOT_VERSION = "utility_icl_development_slot_v3"
RUN_VERSION = "utility_icl_development_run_v3"


def raw_source(record: dict[str, Any]) -> str:
    """Bind nguồn a0 bằng request/UUID/raw Decision, không vòng lặp qua policy dẫn xuất."""
    return content_hash({key: record[key] for key in ("slot", "request", "attempt_id", "decision", "request_ids", "cache_hashes")})


class DevelopmentRun:
    """Một lịch804 slot, không filter point/nhánh/repeat hoặc promote fixture sang research."""

    def __init__(self, directory: Path, manifest: dict[str, Any], snapshot: dict[str, Any], *, mode: str = "research") -> None:
        if mode not in ("research", "offline_fixture"): raise ValueError("Mode run v3 không hợp lệ")
        self.directory, self.manifest, self.snapshot = directory, manifest, snapshot
        self.identity = {"manifest_sha256": content_hash(manifest), "mode": mode}
        self.signature = content_hash(self.identity)
        self.slots = manifest["layout"]["slots"]
        self.originals = {(s["point_id"], s["repeat_index"]): s["slot_index"] for s in self.slots if s["branch_id"] == "Original"}
        self.anchors = {(s["point_id"], s["repeat_index"]): s["slot_index"] for s in self.slots if s["branch_id"] == "Fact_Anchor"}

    def path(self, i: int) -> Path:
        """Path chỉ theo index đã khóa, không theo text do LLM cung cấp."""
        return self.directory/"slots"/f"{i:04d}.json"

    def empty(self, slot: dict[str, Any]) -> dict[str, Any]:
        """Pending không chứa action hoặc request/UUID giả."""
        return {"run_signature": self.signature, "slot": deepcopy(slot), "status": "pending", "request": None,
                "contract": None, "reserved_tokens": None, "attempt_id": None, "decision": None, "policy": None,
                "request_ids": [], "cache_hashes": {}, "anchor": None, "bypass": False}

    def initialize(self) -> None:
        """Tạo đủ slot trước intent đầu; slot đã ready bị mất không được tái tạo ngầm."""
        ready = self.directory/"ready.json"
        if ready.exists() and not (self.directory/"identity.json").exists():
            raise ValueError("Mất identity sau ready, không tái tạo run")
        if not ready.exists() and any(read_envelope(p, SLOT_VERSION).get("status") != "pending"
                                      for p in (self.directory/"slots").glob("*.json")):
            raise ValueError("Mất ready sau intent, không tái tạo run")
        write_envelope(self.directory/"identity.json", RUN_VERSION, self.identity, immutable=True)
        for slot in self.slots:
            path = self.path(slot["slot_index"])
            if not path.exists():
                if ready.exists(): raise ValueError("Mất slot sau ready, không reset run")
                write_envelope(path, SLOT_VERSION, self.empty(slot), immutable=True)
        if {p.name for p in (self.directory/"slots").iterdir()} != {f"{s['slot_index']:04d}.json" for s in self.slots}:
            raise ValueError("Slot nằm ngoài manifest v3")
        write_envelope(ready, RUN_VERSION, self.identity, immutable=True)

    def anchor(self, records: list[dict[str, Any]], slot: dict[str, Any]) -> dict[str, Any]:
        """Cùng a0/proof cho mọi revision trong đúng point/repeat."""
        key = slot["point_id"], slot["repeat_index"]
        original, anchor = records[self.originals[key]], records[self.anchors[key]]
        if original["status"] != "complete" or anchor["status"] != "complete": raise ValueError("Anchor/Original chưa durable")
        point = self.snapshot["points"][slot["point_id"]]
        return resolve_anchor(point["facts"], original["decision"], anchor["decision"], original_source_sha256=raw_source(original),
                              anchor_source_sha256=raw_source(anchor), request_id=anchor["attempt_id"])

    def request(self, records: list[dict[str, Any]], slot: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Sinh request đúng renderer frozen, hoặc bypass có proof; không dùng response v2."""
        point, name = self.snapshot["points"][slot["point_id"]], slot["branch_id"]
        options = {"branch_id": name, "repeat": slot["repeat_index"]}
        anchor = None
        if name == "A_reference": options["prefix"] = point["a_reference"]["prefix"]
        elif name == "Fact_Anchor": options["packet"] = point["facts"]
        elif name in REVISION_BRANCHES:
            anchor = self.anchor(records, slot)
            branch = point["variants"][name]
            if not branch["eligible"] or not anchor["policy"]["fact_assertions_valid"]:
                return None, anchor
            options.update(packet=point["facts"], projection=branch["projection"], anchor=anchor)
        return canonical_request(deepcopy(point["shared"]), self.snapshot["protocol"], **options), anchor

    def policy(self, record: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Tái dựng policy từ raw/facts/U frozen, không tin final_action đã khai trong checkpoint."""
        slot, name = record["slot"], record["slot"]["branch_id"]
        point = self.snapshot["points"][slot["point_id"]]
        if name == "Fact_Anchor":
            original = records[self.originals[(slot["point_id"], slot["repeat_index"])]]
            return resolve_anchor(point["facts"], original["decision"], record["decision"], original_source_sha256=raw_source(original),
                                  anchor_source_sha256=raw_source(record), request_id=record["attempt_id"])["policy"]
        if name in REVISION_BRANCHES:
            return apply_revision(point["facts"], record["anchor"], point["variants"][name], reply=record["decision"], request_id=record["attempt_id"])
        return None

    def dispatch_slot(self, record: dict[str, Any]) -> dict[str, Any]:
        """Cùng intent UUID qua retry; duplicate có UUID khác dù body bằng Original."""
        return {"run_signature": self.signature, **record["slot"], "canonical_sha256": content_hash(record["request"]),
                "checkpoint_attempt_id": record["attempt_id"]}

    def execute(self, dispatch: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
                serialize: Callable[[dict[str, Any]], tuple[dict[str, Any], int]], ledger: Callable[[], dict[str, Any]],
                cache: Path, check: Callable[[], None], checkpoint: Callable[[], None]) -> dict[str, Any]:
        """Đối soát complete, phục hồi durable trước callback; chỉ retry same UUID còn dở."""
        self.initialize()
        headers = [read_envelope(self.path(i), SLOT_VERSION) for i in range(len(self.slots))]
        gap, intents = False, set()
        for slot, row in zip(self.slots, headers):
            if set(row) != set(self.empty(slot)) or row["slot"] != slot or row["run_signature"] != self.signature:
                raise ValueError("Checkpoint header khác run/manifest")
            if gap and row["status"] != "pending": raise ValueError("Slot chạy sau khoảng missing/unknown")
            if row["status"] == "pending" and row != self.empty(slot): raise ValueError("Pending chứa intent hoặc action giả")
            if row["status"] != "complete": gap = True
            if row["attempt_id"] is not None:
                UUID(row["attempt_id"])
                if row["attempt_id"] in intents: raise ValueError("UUID trùng giữa slot")
                intents.add(row["attempt_id"])
        initial_rows = ledger()["requests"]
        if len({row["id"] for row in initial_rows}) != len(initial_rows):
            raise ValueError("Ledger có ID request trùng")
        if any(row.get("run_signature") == self.signature and row.get("checkpoint_attempt_id") not in intents for row in initial_rows):
            raise ValueError("Ledger có request run không thuộc intent đã ghi")
        records, seen = [], set()
        before_shared = content_hash(self.snapshot)
        for i, slot in enumerate(self.slots):
            check()
            saved = read_envelope(self.path(i), SLOT_VERSION)
            if set(saved) != set(self.empty(slot)) or saved["run_signature"] != self.signature or saved["slot"] != slot:
                raise ValueError("Checkpoint khác manifest/schema/run")
            request, anchor = self.request(records, slot)
            if request is None:
                expected = {**self.empty(slot), "status": "complete", "anchor": anchor, "bypass": True}
                expected["policy"] = self.policy(expected, records)
                if saved["status"] != "pending" and saved != expected: raise ValueError("Bypass sai nguồn a0 hoặc giả request/cache")
                if saved["status"] == "pending":
                    if saved != self.empty(slot): raise ValueError("Pending bypass bị sửa")
                    write_envelope(self.path(i), SLOT_VERSION, expected)
                records.append(expected)
            else:
                contract, reserve = serialize(request)
                cap = self.manifest["request_bounds"][slot["point_id"]][slot["branch_id"]]["reserved_tokens_upper"]
                if reserve > cap: raise ValueError("Request động vượt upper bound đã khóa")
                if saved["status"] == "pending":
                    if saved != self.empty(slot): raise ValueError("Pending chứa dữ liệu chưa đăng ký")
                    saved.update(status="unknown", request=request, contract=contract, reserved_tokens=reserve,
                                 attempt_id=str(uuid4()), anchor=anchor)
                    write_envelope(self.path(i), SLOT_VERSION, saved)
                elif (saved["request"] != request or saved["contract"] != contract or saved["reserved_tokens"] != reserve
                      or saved["anchor"] != anchor or saved["bypass"] or saved["status"] not in ("unknown", "complete")):
                    raise ValueError("Checkpoint khác canonical request/anchor động")
                UUID(saved["attempt_id"])
                if saved["attempt_id"] in seen: raise ValueError("UUID bị dùng cho nhiều scientific slot")
                seen.add(saved["attempt_id"])
                descriptor = self.dispatch_slot(saved)
                parsed, ids, hashes = audit_attempt(ledger(), cache, descriptor, request, contract)
                if saved["status"] == "complete":
                    if parsed != saved["decision"] or ids != saved["request_ids"] or hashes != saved["cache_hashes"] or saved["policy"] != self.policy(saved, records):
                        raise ValueError("Complete khác raw/ledger/policy; không tự replay")
                else:
                    if parsed is None:
                        old_rows = {row["id"]: content_hash(row) for row in ledger()["requests"]}
                        result = dispatch(deepcopy(request), descriptor)
                        current_rows = {row["id"]: content_hash(row) for row in ledger()["requests"]}
                        if any(current_rows.get(rid) != checksum for rid, checksum in old_rows.items()):
                            raise ValueError("Retry đã sửa ledger/reserve cũ")
                        parsed, ids, hashes = audit_attempt(ledger(), cache, descriptor, request, contract)
                        if parsed is None or parsed != result: raise ValueError("Response SDK khác raw durable; giữ unknown")
                    saved.update(status="complete", decision=parsed, request_ids=ids, cache_hashes=hashes)
                    saved["policy"] = self.policy(saved, records)
                    write_envelope(self.path(i), SLOT_VERSION, saved)
                records.append(saved)
            checkpoint()
            if i+1 == len(self.slots) or self.slots[i+1]["point_id"] != slot["point_id"] or self.slots[i+1]["repeat_index"] != slot["repeat_index"]:
                print(f"Đã lưu {i+1}/{len(self.slots)} slot v3; point={slot['point_id']}, repeat={slot['repeat_index']}; chưa P&L.", flush=True)
        if content_hash(self.snapshot) != before_shared: raise ValueError("Run mutate snapshot/upstream dùng chung")
        result = {"status": "COMPLETE_AWAITING_AUDIT", "run_signature": self.signature, "complete_slots": len(records),
                  "primary_complete": sum(r["slot"]["repeat_index"] == 0 for r in records),
                  "repeat_complete": sum(r["slot"]["repeat_index"] != 0 for r in records),
                  "bypass_slots": sum(r["bypass"] for r in records), "HTTP_attempts": sum(len(r["request_ids"]) for r in records)}
        write_envelope(self.directory/"progress.json", RUN_VERSION, result)
        return result
