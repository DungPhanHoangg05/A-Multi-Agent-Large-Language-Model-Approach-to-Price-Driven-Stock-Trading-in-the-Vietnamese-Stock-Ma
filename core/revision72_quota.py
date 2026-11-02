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
        """Caps cố định theo plan; reserve chỉ thành công khi request được phép gửi."""
        now = self.clock()
        if now >= deadline:
            raise StudyStop("Đã tới T0+60h; dừng inference, giữ job thiếu.")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            total = db.execute("SELECT count(*) FROM attempts").fetchone()[0]
            own = db.execute("SELECT count(*) FROM attempts WHERE org=?", (org,)).fetchone()[0]
            decisions = db.execute("SELECT count(*) FROM attempts WHERE stage='decision'").fetchone()[0]
            day = db.execute("SELECT count(*) FROM attempts WHERE org=? AND stage='decision' AND stamp>?", (org, now - 86400)).fetchone()[0]
            if total >= 1000 or own >= 200 or (stage == "decision" and (decisions >= 600 or day >= 40)):
                raise StudyStop("Đã chạm cap nội bộ study/org/Decision/24h; giữ checkpoint để đợi hoặc kiểm kê.")
            row = db.execute("SELECT next_at FROM pacing WHERE org=? AND model=?", (org, model)).fetchone()
            if row and row[0] > now:
                raise StudyStop(f"Limiter yêu cầu chờ {row[0] - now:.1f} giây trước request tiếp theo.")
            db.execute("INSERT INTO attempts VALUES(?,?,?,?,?)", (attempt, org, stage, model, now))
            interval = 30  # pacing bảo thủ cho cả vision và Decision, không thay quota provider
            db.execute("INSERT OR REPLACE INTO pacing VALUES(?,?,?)", (org, model, now + interval))

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
        super().__init__(directory, bank_id, 200, secret)
        self.ledger, self.org, self.deadline = ledger, org, deadline

    def on_chat_model_start(self, serialized: dict, messages: list, *, run_id: object, **kwargs: object) -> None:
        """Pacing tôn trọng reset; caps và Decision prompt phải được kiểm trước API."""
        model = self.context["model"]
        while self.ledger.next_at(self.org, model) > time.time():
            remaining = self.ledger.next_at(self.org, model) - time.time()
            if time.time() + remaining >= self.deadline or remaining > 120:
                raise StudyStop(f"Org {self.org} đang chờ quota ({remaining:.1f}s); resume sau reset.")
            time.sleep(min(remaining, 30))
        if self.context["stage"] == "decision":
            chars = sum(len(m.content) for batch in messages for m in batch if isinstance(m.content, str))
            if chars >= 6500:
                raise StudyStop("Prompt Decision phải dưới 6.500 ký tự.")
        self.ledger.reserve(str(run_id), self.org, self.context["stage"], model, self.deadline)
        super().on_chat_model_start(serialized, messages, run_id=run_id, **kwargs)

    def on_llm_error(self, error: BaseException, *, run_id: object, **kwargs: object) -> None:
        """Archive lỗi, giữ reset trên ledger và dừng shard trước fallback/repair không kiểm soát."""
        delay = retry_after_seconds(str(error))
        if delay is not None:
            self.ledger.defer(self.org, self.context["model"], delay)
        try:
            super().on_llm_error(error, run_id=run_id, **kwargs)
        finally:
            raise StudyStop(f"Org {self.org}: provider request thất bại; đã archive, giữ node thành công và dừng shard.")

    def on_llm_end(self, response: object, *, run_id: object, **kwargs: object) -> None:
        """Khóa raw response ngay trước parser để replay sau interruption kiểm được hash."""
        super().on_llm_end(response, run_id=run_id, **kwargs)
        path = self.directory / "calls" / f"{run_id}.response.json"
        write_json(path.with_name(f"{run_id}.response_digest.json"), {"sha256": digest(read_json(path))}, True)
