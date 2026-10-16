"""Audit request tại transport, giữ nguyên pacer/retry và không lưu credential/header."""

from __future__ import annotations

from contextvars import ContextVar
import hashlib
import json
from typing import Any

import httpx

from core.groq_pacing import PacedGroqTransport
from core.historical_signals import digest
from core.research_invocation import CURRENT

SLOT: ContextVar[Any] = ContextVar('improvement_slot', default=None)
VERSION = 'improvement_http_audit_v1'


def validate_client(llm: Any, role: str, models: dict[str, Any], *, online: bool = False) -> None:
    """Khóa cả defaults/kwargs của SDK; không nhận seed/stop hay lựa chọn sinh ngoài protocol."""
    from core.improvement_protocol import CLIENT_OPTIONS
    expected = {'model': models[f'{role}_llm_model'], 'stream': False, 'n': 1,
        'temperature': models[f'{role}_llm_temperature'], 'stop': None,
        'max_tokens': models[f'{role}_llm_max_tokens'], 'service_tier': 'on_demand', **CLIENT_OPTIONS[role]}
    if llm.max_retries != 0 or llm.streaming or llm.model_kwargs or llm._default_params != expected:
        raise ValueError('Client cải tiến khác model/options/retry đã khóa hoặc chứa seed/stop ngoài protocol')
    if online and not isinstance(getattr(llm.http_client, '_transport', None), ImprovementTransport):
        raise ValueError('Run cải tiến phải qua transport audit/pacer đã kiểm')


def expected_contract(llm: Any, prompt: str) -> dict[str, Any]:
    """Dựng payload bằng serializer client đã ghim; không invoke HTTP hoặc đọc key."""
    from agents.decision_agent import TradeDecisionOutput
    from langchain_core.messages import HumanMessage
    message_dicts, params = llm._create_message_dicts([HumanMessage(content=prompt)], None)
    structured = llm.with_structured_output(TradeDecisionOutput, method='json_schema', include_raw=True)
    raw = structured.steps[0].steps__['raw']
    return body_contract({'messages': message_dicts, **params, 'response_format': raw.kwargs['response_format']})


def body_contract(body: dict[str, Any]) -> dict[str, Any]:
    """Hash JSON canonical toàn body; chỉ lưu contract allowlist, không giữ headers."""
    allowed = {'messages', 'model', 'temperature', 'max_tokens', 'max_completion_tokens', 'n', 'stream',
               'stop', 'reasoning_effort', 'reasoning_format', 'response_format', 'tools', 'tool_choice',
               'parallel_tool_calls', 'top_p', 'frequency_penalty', 'presence_penalty', 'seed', 'service_tier'}
    if type(body) is not dict or set(body)-allowed or not {'model', 'messages'}.issubset(body):
        raise ValueError('Body cải tiến chứa field chưa đăng ký/credential hoặc thiếu model/messages')
    messages = body['messages']
    if type(messages) is not list or not messages or any(type(m) is not dict for m in messages):
        raise ValueError('Messages HTTP phải là list object không rỗng')
    prompt = messages[0].get('content') if len(messages) == 1 and messages[0].get('role') == 'user' else None
    return {'canonical_body_sha256': digest(body), 'messages_sha256': digest(messages),
        'response_format_sha256': digest(body.get('response_format')),
        'prompt_sha256': hashlib.sha256(prompt.encode('utf-8')).hexdigest() if type(prompt) is str else None,
        'model_options': {k: v for k, v in body.items() if k not in ('messages', 'response_format', 'tools')},
        'tools_sha256': digest(body.get('tools'))}


def message_fingerprint(payload: Any) -> str | None:
    """Nối message provider với raw AIMessage durable, kể cả structured tool call."""
    if type(payload) is not dict or not payload.get('choices'):
        return None
    message = payload['choices'][0].get('message', {})
    try:
        calls = [{'id': call['id'], 'name': call['function']['name'],
                  'args': json.loads(call['function']['arguments']), 'type': 'tool_call'}
                 for call in message.get('tool_calls') or []]
    except (ValueError, KeyError, TypeError):
        return None
    return digest({'content': message.get('content') or '', 'tool_calls': calls})


class _AuditInner(httpx.BaseTransport):
    """Base transport đã reserve intent; bổ sung audit bền vững ngay trước gửi HTTP."""

    def __init__(self, pacer: Any, inner: httpx.BaseTransport) -> None:
        self.pacer, self.inner = pacer, inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Lưu request contract/slot và fingerprint response, không thêm retry riêng."""
        body = json.loads(request.content)
        contract = body_contract(body)
        record = self.pacer.state['requests'][-1]
        slot = SLOT.get()
        if slot is not None and CURRENT.get() is None:
            raise ValueError('Decision audit thiếu invocation budget')
        record['improvement_audit'] = {'audit_version': VERSION, 'slot': slot, 'request': contract, 'response': None}
        self.pacer.save()
        response = self.inner.handle_request(request)
        response.read()
        try:
            payload = response.json()
        except ValueError:
            payload = None
        record['improvement_audit']['response'] = {'body_sha256': hashlib.sha256(response.content).hexdigest(),
            'canonical_sha256': digest(payload), 'id': payload.get('id') if type(payload) is dict else None,
            'message_sha256': message_fingerprint(payload),
            'system_fingerprint': payload.get('system_fingerprint') if type(payload) is dict else None}
        self.pacer.save()
        return response

    def close(self) -> None:
        """Nhả transport thật theo lifecycle httpx của caller."""
        self.inner.close()


class ImprovementTransport(PacedGroqTransport):
    """Chỉ thay inner để audit; admission, cooldown, 429 và usage vẫn qua wrapper cũ."""

    def __init__(self, pacer: Any, inner: httpx.BaseTransport | None = None) -> None:
        super().__init__(pacer, _AuditInner(pacer, inner or httpx.HTTPTransport(retries=0)))

    def close(self) -> None:
        """Nhả kết nối transport khi client đóng, kể cả sau unknown."""
        self.inner.close()


def verify_attempt_audit(ledger: dict[str, Any], slot: dict[str, Any], *, expected: dict[str, Any],
                         raw_message: dict[str, Any]) -> list[dict[str, Any]]:
    """Ghép HTTP bằng UUID/slot; so contract đầu và response thành công đã lưu."""
    records = [row for row in ledger['requests'] if row.get('checkpoint_attempt_id') == slot['checkpoint_attempt_id']]
    if not records or not any(row['status'] == 200 for row in records):
        raise ValueError('Decision thật thiếu HTTP thành công cùng UUID')
    for row in records:
        audit = row.get('improvement_audit')
        if (type(audit) is not dict or audit.get('audit_version') != VERSION or audit['slot'] != slot
                or row.get('run_signature') != slot['run_signature'] or row.get('point_id') != slot['point_id']
                or row.get('branch_id') != slot['branch_id'] or audit['response'] is None):
            raise ValueError('HTTP audit khác slot/UUID hoặc thiếu fingerprint')
    if records[0]['improvement_audit']['request'] != expected:
        raise ValueError('HTTP body/schema/model/options khác request tái dựng offline')
    successful = [row for row in records if row['status'] == 200]
    fingerprint = digest({'content': raw_message.get('content') or '', 'tool_calls': raw_message.get('tool_calls') or []})
    if successful[-1]['improvement_audit']['response']['message_sha256'] != fingerprint:
        raise ValueError('Response HTTP khác raw message durable')
    return records
