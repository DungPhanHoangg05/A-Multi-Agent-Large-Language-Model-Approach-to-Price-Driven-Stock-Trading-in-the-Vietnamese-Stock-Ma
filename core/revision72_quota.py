"""Limiter SQLite dùng chung năm shard; đếm mọi attempt trước network."""

from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager
import sqlite3
import time
from typing import Callable
from collections.abc import Iterator

from core.revision_call_archive import CallArchive, StudyStop, retry_after_seconds
from core.revision_common_study import digest, read_json, write_json


class ProviderIssue(StudyStop):
    """Lỗi provider có loại rõ ràng để pool đổi key hoặc chờ đúng reset."""

    def __init__(self, org: int, kind: str, detail: str):
        self.org, self.kind, self.detail = org, kind, detail
        super().__init__(f"Org {org}: {kind}: {detail}")


class PoolLedger:
    """Một transaction cho caps toàn study/org/24h và pacing; không chứa secrets."""

    def __init__(self, path: Path, identity: str, clock: Callable[[], float] = time.time) -> None:
        self.path, self.clock = path, clock
        if not path.exists() and any((path.parent / "shards").glob("org*/calls/*.request.json")):
            raise ValueError("Thiếu quota ledger nhưng đã có calls; không tự reset ngân sách")
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS identity(value TEXT NOT NULL)")
            row = db.execute("SELECT value FROM identity").fetchone()
            if row and row[0] != identity:
                raise ValueError("Quota ledger thuộc run khác")
            if not row:
                db.execute("INSERT INTO identity VALUES (?)", (identity,))
            db.execute("CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY,org INTEGER,stage TEXT,model TEXT,stamp REAL)")
            db.execute("CREATE TABLE IF NOT EXISTS pacing(org INTEGER,model TEXT,next_at REAL,PRIMARY KEY(org,model))")
            db.execute("CREATE TABLE IF NOT EXISTS provider_state(org INTEGER,model TEXT,kind TEXT,until_at REAL,reason TEXT,PRIMARY KEY(org,model))")
            db.execute("CREATE TABLE IF NOT EXISTS leases(org INTEGER PRIMARY KEY,owner TEXT,until_at REAL)")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Timeout ngắn, lock transaction thay vì counters JSON dùng chung."""
        db = sqlite3.connect(self.path, timeout=15, isolation_level="IMMEDIATE")
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, attempt: str, org: int, stage: str, model: str, deadline: float) -> None:
        """Chỉ đếm attempt và pacing; bỏ mọi cap nội bộ/deadline theo yêu cầu tác giả."""
        now = self.clock()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT next_at FROM pacing WHERE org=? AND model=?", (org, model)).fetchone()
            if row and row[0] > now:
                raise StudyStop(f"Limiter yêu cầu chờ {row[0] - now:.1f} giây trước request tiếp theo.")
            db.execute("INSERT INTO attempts VALUES(?,?,?,?,?)", (attempt, org, stage, model, now))
            interval = 30  # pacing bảo thủ cho cả vision và Decision, không thay quota provider
            db.execute("INSERT OR REPLACE INTO pacing VALUES(?,?,?)", (org, model, now + interval))

    def acquire(self, model: str, preferred: int, owner: str, allowed: list[int]) -> int | None:
        """Lease liên process: mỗi key chỉ một request, shard có thể mượn key còn quota."""
        now = self.clock()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for org in sorted(allowed, key=lambda i: (i != preferred, i)):
                state = db.execute("SELECT kind,until_at FROM provider_state WHERE org=? AND model=?", (org,model)).fetchone()
                if state and (state[0] in ("key_error", "incompatible") or state[1] > now):
                    continue
                lease = db.execute("SELECT until_at FROM leases WHERE org=?", (org,)).fetchone()
                pacing = db.execute("SELECT next_at FROM pacing WHERE org=? AND model=?", (org,model)).fetchone()
                if (lease and lease[0] > now) or (pacing and pacing[0] > now):
                    continue
                db.execute("INSERT OR REPLACE INTO leases VALUES(?,?,?)", (org,owner,now+300))
                return org
        return None

    def release(self, org: int, owner: str) -> None:
        """Chỉ nhả lease của đúng invocation, không nhả request của process khác."""
        with self.connection() as db:
            db.execute("UPDATE leases SET until_at=0 WHERE org=? AND owner=?", (org,owner))

    def block(self, org: int, model: str, kind: str, seconds: float, reason: str) -> None:
        """Lưu reset provider; không gán quota ngày bằng giới hạn do chương trình đặt."""
        until = self.clock() + max(0, seconds) + 1
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO provider_state VALUES(?,?,?,?,?)", (org,model,kind,until,reason[:500]))
            db.execute("INSERT OR REPLACE INTO pacing VALUES(?,?,?)", (org,model,max(self.next_at(org,model),until)))

    def states(self, model: str, allowed: list[int]) -> list[dict]:
        """Phân biệt hết quota ngày với pacing/nghẽn tạm và lỗi key/configuration."""
        result = []
        now = self.clock()
        with self.connection() as db:
            for org in allowed:
                row = db.execute("SELECT kind,until_at,reason FROM provider_state WHERE org=? AND model=?", (org,model)).fetchone()
                result.append({"org":org,"kind":row[0] if row else "ready", "until":row[1] if row else 0,
                    "active": bool(row and (row[0] in ("key_error","incompatible") or row[1]>now)), "reason":row[2] if row else ""})
        return result

    def next_at(self, org: int, model: str) -> float:
        """Đọc pacing để worker chờ mà không chiếm transaction hoặc tính thêm attempt."""
        with self.connection() as db:
            row = db.execute("SELECT next_at FROM pacing WHERE org=? AND model=?", (org, model)).fetchone()
        return row[0] if row else 0.0

    def defer(self, org: int, model: str, seconds: float) -> None:
        """Lưu thời gian provider yêu cầu qua các lần resume."""
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO pacing VALUES(?,?,?)", (org, model, max(self.next_at(org, model), self.clock() + seconds + 1)))


class PoolArchive(CallArchive):
    """Mở rộng archive chuẩn; lỗi provider thoát trước fallback của agent gốc."""

    def __init__(self, directory: Path, bank_id: str, secret: str, ledger: PoolLedger, org: int, deadline: float):
        # Infinity chỉ là sentinel trong bộ đếm; native JSON ghi null, không NaN/Infinity.
        super().__init__(directory, bank_id, float("inf"), secret)
        self.ledger, self.org, self.deadline = ledger, org, deadline

    def on_chat_model_start(self, serialized: dict, messages: list, *, run_id: object, **kwargs: object) -> None:
        """Pacing tôn trọng reset; caps và Decision prompt phải được kiểm trước API."""
        model = self.context["model"]
        provider = int(self.context.get("provider_org", self.org))
        while self.ledger.next_at(provider, model) > time.time():
            remaining = self.ledger.next_at(provider, model) - time.time()
            time.sleep(min(remaining, 30))
        if self.context["stage"] == "decision":
            chars = sum(len(m.content) for batch in messages for m in batch if isinstance(m.content, str))
            if chars >= 6500:
                raise StudyStop("Prompt Decision phải dưới 6.500 ký tự.")
        self.ledger.reserve(str(run_id), provider, self.context["stage"], model, self.deadline)
        super().on_chat_model_start(serialized, messages, run_id=run_id, **kwargs)

    def on_llm_error(self, error: BaseException, *, run_id: object, **kwargs: object) -> None:
        """Archive lỗi, giữ reset trên ledger và dừng shard trước fallback/repair không kiểm soát."""
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            super().on_llm_error(error, run_id=run_id, **kwargs)
            raise error
        provider = int(self.context.get("provider_org", self.org))
        message = str(error)
        lower = message.lower()
        delay = retry_after_seconds(message)
        kind = ("quota" if any(v in lower for v in ("tokens per day", "requests per day")) else
                "incompatible" if "request too large" in lower or "model_not_found" in lower else
                "key_error" if "401" in lower or "403" in lower else
                "format" if "json_validate_failed" in lower else
                "rate" if "429" in lower else "transient")
        if kind == "quota" and delay is None:
            kind = "quota_unknown_reset"
        self.ledger.block(provider, self.context["model"], kind, delay if delay is not None else (60 if kind == "quota_unknown_reset" else 5), self.clean(message))
        try:
            super().on_llm_error(error, run_id=run_id, **kwargs)
        finally:
            self.not_before = 0  # reset nằm theo key/model trên SQLite, không khóa các key khác
            raise ProviderIssue(provider, kind, self.clean(message))

    def on_llm_end(self, response: object, *, run_id: object, **kwargs: object) -> None:
        """Khóa raw response ngay trước parser để replay sau interruption kiểm được hash."""
        super().on_llm_end(response, run_id=run_id, **kwargs)
        path = self.directory / "calls" / f"{run_id}.response.json"
        write_json(path.with_name(f"{run_id}.response_digest.json"), {"sha256": digest(read_json(path))}, True)
