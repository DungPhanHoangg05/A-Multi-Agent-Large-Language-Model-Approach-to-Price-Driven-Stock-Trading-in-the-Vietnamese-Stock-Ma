"""Phục hồi vận hành có audit cho lượt cải tiến chạy lại từ đầu."""

from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterator
from uuid import UUID

import httpx

from core.groq_pacing import PilotStop
from core.improvement_transport import ImprovementTransport, body_contract
from core.provider_quota import ProviderQuotaPacer
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once
from core.research_invocation import CURRENT, RECOVERY

VERSION = 'resilient_invocation_v1'
POLICY = {'version': VERSION, 'transient_http': [408, 425, 500, 502, 503, 504],
    'transport_retry': True, 'minute_limit': 'WAIT_RETRY_AFTER', 'daily_quota': 'STOP_KEEP_CHECKPOINT',
    'backoff_seconds': [2, 4, 8, 16, 32, 60], 'maximum_total_wait': None,
    'resume_unknown': 'SAME_UUID_RETRY_WITH_AUDIT', 'durable_success': 'REUSE_BEFORE_HTTP',
    'credential_change': 'PREFLIGHT_AND_RESUME', 'complete_replay': False}


@contextmanager
def recovery_scope(enabled: bool = True) -> Iterator[None]:
    """Chỉ entrypoint revision mới bật quyền phục hồi đã khóa trước API."""
    token = RECOVERY.set(enabled)
    try:
        yield
    finally:
        RECOVERY.reset(token)


class ResilientPacer(ProviderQuotaPacer):
    """Giữ lịch sử quota chung, bỏ trần chờ ngắn của policy legacy khi retry mạng."""

    resilient = True

    def reserve(self, model: str, tokens: int) -> dict[str, Any]:
        """Đóng dấu policy trước HTTP để nhận diện cả intent bị ngắt giữa chừng."""
        row = super().reserve(model, tokens)
        row.update(recovery_policy=VERSION, dispatch_phase='reserved')
        self.save()
        return row


class ResilientTransport(ImprovementTransport):
    """Giữ request/schema; retry lỗi tạm thời và phục hồi response durable trước SDK."""

    def __init__(self, pacer: ResilientPacer, cache_root: Path,
                 inner: httpx.BaseTransport | None = None) -> None:
        super().__init__(pacer, inner)
        self.cache_root, self.used_cache = cache_root, set()

    def _event(self, reason: str, row: dict[str, Any], **details: Any) -> None:
        """Ghi lý do phục hồi không chứa credential, prompt hoặc chuỗi lỗi thô."""
        budget = CURRENT.get()
        self.pacer.state.setdefault('recovery_events', []).append({'reason': reason,
            'at': float(self.pacer.clock()), 'request_id': row['id'],
            'checkpoint_attempt_id': row.get('checkpoint_attempt_id'),
            'invocation_id': budget.invocation_id if budget else None,
            'run_signature': row.get('run_signature'), **details})
        self.pacer.save()

    def _cached(self, request: httpx.Request) -> httpx.Response | None:
        """Chỉ dùng response 200 cùng UUID/body của invocation trước đã lưu đầy đủ."""
        budget = CURRENT.get()
        if budget is None or not budget.checkpoint_attempt_id:
            return None
        contract = body_contract(json.loads(request.content))
        with self.pacer._mutex:
            for row in reversed(self.pacer.state['requests']):
                if (row.get('checkpoint_attempt_id') != budget.checkpoint_attempt_id or row['status'] != 200
                        or row.get('run_signature') != budget.run_signature
                        or row.get('invocation_id') == budget.invocation_id or row.get('recovery_policy') != VERSION):
                    continue
                key = (budget.invocation_id, row['id'])
                path = self.cache_root/(str(UUID(row['id']))+'.json')
                if key in self.used_cache:
                    continue
                if not path.exists():
                    if row.get('durable_response') is not None:
                        raise ValueError('Thiếu response cache đã xác nhận; dừng trước HTTP')
                    continue
                audit = row.get('improvement_audit') or {}
                # Một stage có thể gọi nhiều prompt khác nhau; chỉ phục hồi đúng body đang cần.
                if audit.get('request') != contract:
                    continue
                proof = row.get('durable_response')
                if proof is not None and proof != {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}:
                    raise ValueError('Response cache khác hash đã lưu')
                saved = read_envelope(path)
                if (set(saved) != {'version', 'request', 'body_base64', 'headers'} or saved['version'] != VERSION
                        or saved['request'] != contract or audit.get('request') != contract):
                    raise ValueError('Response cache khác request/model/schema đã khóa')
                content = base64.b64decode(saved['body_base64'], validate=True)
                if hashlib.sha256(content).hexdigest() != (audit.get('response') or {}).get('body_sha256'):
                    raise ValueError('Response cache khác HTTP response đã audit')
                if set(saved['headers']) - {'content-type', 'x-request-id'}:
                    raise ValueError('Response cache chứa header ngoài allowlist')
                self.used_cache.add(key)
                self._event('DURABLE_RESPONSE_REUSED', row)
                print('[Phục hồi] Dùng response đã lưu; tiếp tục từ checkpoint.', flush=True)
                return httpx.Response(200, content=content, headers=saved['headers'], request=request)
        return None

    def _store(self, request: httpx.Request, response: httpx.Response) -> None:
        """Ghi response trước khi trả về SDK, không lưu request headers hoặc credential."""
        budget = CURRENT.get()
        if response.status_code != 200 or budget is None or not budget.checkpoint_attempt_id:
            return
        with self.pacer._mutex:
            row = next(r for r in self.pacer.state['requests'] if r['id'] == response.extensions['improvement_request_id'])
            saved = {'version': VERSION, 'request': body_contract(json.loads(request.content)),
                'body_base64': base64.b64encode(response.content).decode('ascii'),
                'headers': {k: response.headers[k] for k in ('content-type', 'x-request-id') if k in response.headers}}
            path = self.cache_root/(str(UUID(row['id']))+'.json')
            _write_once(path, saved)
            row['durable_response'] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            self.pacer.save()

    def _wait(self, seconds: float) -> None:
        """Chia nhỏ backoff để Ctrl+C vẫn giữ được timer và checkpoint."""
        remaining = seconds
        while remaining > 0:
            before = self.pacer.monotonic()
            self.pacer.sleep(min(30., remaining))
            elapsed = max(0., self.pacer.monotonic()-before)
            if elapsed <= 0:
                raise ValueError('Đồng hồ pacing không tiến')
            budget = CURRENT.get()
            if budget is not None:
                budget.wait_seconds += elapsed
            with self.pacer._mutex:
                self.pacer.state['pacing_seconds'] = float(self.pacer.state.get('pacing_seconds', 0.)+elapsed)
                self.pacer.save()
            remaining -= elapsed

    @staticmethod
    def _daily(response: httpx.Response) -> bool:
        """Phân biệt quota ngày với TPM/RPM; không suy quota ngày chỉ từ HTTP 429."""
        if response.headers.get('x-ratelimit-remaining-requests') == '0':
            return True
        try:
            error = response.json().get('error', {})
        except (ValueError, AttributeError):
            return False
        text = str(error.get('message', ''))+' '+str(error.get('code', '')) if isinstance(error, dict) else ''
        return bool(re.search(r'\b(?:TPD|RPD)\b|per[ _-]*day|daily[ _-]*(?:quota|limit)', text, re.I))

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Retry trong cùng scientific UUID; quota ngày/auth/config/integrity vẫn dừng."""
        budget = CURRENT.get()
        if budget is None or not budget.recovery_enabled:
            return super().handle_request(request)
        cached = self._cached(request)
        if cached is not None:
            return cached
        failures = 0
        while True:
            budget.before_http()
            try:
                response = self._handle_once(request)
            except PilotStop as error:
                with self.pacer._mutex:
                    row = next((r for r in self.pacer.state['requests'] if r['id'] == getattr(error, 'request_record_id', None)), None)
                    if row is None or row['status'] not in ('transport_error', *POLICY['transient_http']):
                        raise
                    failures += 1
                    delay = float(POLICY['backoff_seconds'][min(failures-1, 5)])
                    cause = error.__context__
                    category = type(cause).__name__ if isinstance(cause, (httpx.HTTPError, OSError)) else 'HTTP_TRANSIENT'
                    row['failure_category'] = category
                    self._event('TRANSIENT_RETRY', row, category=category, delay_seconds=delay)
                print(f'[Phục hồi] Lỗi tạm thời {category}; thử lại sau {delay:.0f} giây.', flush=True)
                self._wait(delay)
                continue
            if response.status_code == 429:
                with self.pacer._mutex:
                    row = next(r for r in self.pacer.state['requests'] if r['id'] == response.extensions['improvement_request_id'])
                    if self._daily(response):
                        response.close()
                        self.pacer.stop('PROVIDER_DAILY_QUOTA', row['model'], resume_at=row.get('retry_until'))
                    self._event('RATE_LIMIT_WAIT', row)
                response.close()
                print('[Phục hồi] Provider giới hạn tốc độ; chờ retry-after rồi tiếp tục.', flush=True)
                continue
            self._store(request, response)
            return response
