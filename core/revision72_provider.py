"""Pool key theo quota provider, giữ nguyên shard lưu trữ và treatment của nghiên cứu."""

from __future__ import annotations

from collections import Counter
import time
from typing import Any
from uuid import uuid4
from pathlib import Path
from core.revision_common_study import read_json
from core.revision_call_archive import retry_after_seconds

from core.revision_call_archive import StudyStop, StudyLock
from core.revision72_quota import PoolArchive, ProviderIssue


def scientific_context(context: dict) -> dict:
    """Thông tin routing không thay định danh market unit/variant/repeat/node."""
    return {k:v for k,v in context.items() if k not in ("provider_org", "execution_epoch")}


class PoolUnavailable(StudyStop):
    """Không còn key khả dụng cho model đang cần; worker vẫn thử các job khác."""

    def __init__(self, message: str, model: str | None = None):
        self.model = model
        super().__init__(message)


def seed_provider_state(run: Path, ledger: Any) -> None:
    """Khôi phục quota chưa reset từ archive cũ; bỏ lỗi cũ đã có response mới hơn."""
    latest = {}
    for shard in (run / "shards").glob("org*"):
        home = int(shard.name[3:])
        for path in (shard / "calls").glob("*.request.json"):
            req = read_json(path);context = req["context"]
            key = (int(context.get("provider_org", home)), context["model"])
            for suffix in ("response", "error"):
                event = path.with_name(path.name.replace(".request.", f".{suffix}."))
                if event.exists() and event.stat().st_mtime > latest.get(key, (0,None))[0]:
                    latest[key] = (event.stat().st_mtime, event if suffix == "error" else None)
    for (org,model),(stamp,path) in latest.items():
        if path is None:
            continue
        message = read_json(path)["error"]
        if "tokens per day" not in message.lower() and "requests per day" not in message.lower():
            continue
        delay = retry_after_seconds(message)
        if delay is not None and stamp+delay+1 > ledger.clock():
            ledger.block(org, model, "quota", max(0,stamp+delay-ledger.clock()), "provider quota recovered from archived error")


class RoutedLLM:
    """Mỗi invoke mượn một key còn quota, một lease/key trên toàn năm process."""

    def __init__(self, archive: PoolArchive, keys: list[str], preferred: int, kwargs: dict,
                 epoch: str, allowed: list[int] | None = None, structured: tuple | None = None):
        self.archive, self.keys, self.preferred = archive, keys, preferred
        self.kwargs, self.epoch = kwargs, epoch
        self.allowed = allowed if allowed is not None else list(range(1,6))
        self.structured = structured
        self.models: dict[int,Any] = {}

    def model(self, org: int) -> Any:
        """Tạo client riêng theo key; không dump client hoặc credentials vào archive."""
        from langchain_groq import ChatGroq
        if org not in self.models:
            self.models[org] = ChatGroq(api_key=self.keys[org-1], callbacks=[self.archive], **self.kwargs)
        delegate = self.models[org]
        if self.structured is not None:
            args, kwargs = self.structured
            return delegate.with_structured_output(*args, **kwargs)
        return delegate

    def with_structured_output(self, *args: Any, **kwargs: Any) -> RoutedLLM:
        """Kiểm hỗ trợ schema ngay tại factory, như delegate gốc; không gọi API."""
        self.model(self.preferred).with_structured_output(*args, **kwargs)
        return RoutedLLM(self.archive, self.keys, self.preferred, self.kwargs, self.epoch,
                         self.allowed, (args, kwargs))

    def invoke(self, prompt: Any, **kwargs: Any) -> Any:
        """Chỉ đổi key, giữ nguyên model/prompt/max_tokens/schema và mọi attempted calls."""
        ledger, model = self.archive.ledger, self.kwargs["model"]
        failures: Counter = Counter()
        while True:
            allowed = [org for org in self.allowed if failures[org] < 2]
            if not allowed:
                raise RuntimeError("Provider liên tục từ chối output/schema trên mọi key; giữ job thiếu, không tạo fallback")
            owner = str(uuid4())
            org = ledger.acquire(model, self.preferred, owner, allowed)
            if org is None:
                states = ledger.states(model, allowed)
                unavailable = [s for s in states if s["active"] and s["kind"] in ("quota", "quota_unknown_reset", "key_error", "incompatible")]
                if len(unavailable) == len(allowed):
                    kinds = dict(Counter(s["kind"] for s in unavailable))
                    resets = [s["until"] for s in unavailable if s["kind"] == "quota"]
                    next_at = min(resets) if resets else None
                    raise PoolUnavailable(f"Không còn key khả dụng cho {model}: {kinds}; retry sớm nhất epoch={next_at}", model)
                time.sleep(1)
                continue
            previous, secret = self.archive.context, self.archive.secret
            key_lock = StudyLock(ledger.path.parent / f"provider_locks/org{org}.lock")
            try:
                key_lock.__enter__()
            except RuntimeError:
                ledger.release(org, owner)
                time.sleep(1)
                continue
            self.archive.context = {**previous, "provider_org":org, "execution_epoch":self.epoch}
            self.archive.secret = self.keys[org-1]
            try:
                return self.model(org).invoke(prompt, **kwargs)
            except ProviderIssue as exc:
                if exc.kind in ("format", "transient"):
                    failures[org] += 1
                # Rate/quota được đánh dấu theo key/model; thử key khác còn sẵn.
                continue
            finally:
                self.archive.context, self.archive.secret = previous, secret
                ledger.release(org, owner)
                key_lock.__exit__()
