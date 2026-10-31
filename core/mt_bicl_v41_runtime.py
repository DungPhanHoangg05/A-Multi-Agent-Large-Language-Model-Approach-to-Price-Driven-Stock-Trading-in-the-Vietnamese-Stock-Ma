"""Coordinator một writer: shard cố định, cache trước key và quota riêng từng scope."""

from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
import time
from typing import Any, Callable
from uuid import uuid4

import httpx

from core.groq_pacing import PilotStop
from core.improvement_recovery import ResilientPacer, ResilientTransport
from core.mt_bicl_v4_collect import clients
from core.mt_bicl_v4_collect_transport import CollectionTransport, OfflinePending, ReplayTransport
from core.mt_bicl_v4_completion import DataCompletionError
from core.mt_bicl_v4_dataset import immutable
from core.mt_bicl_v4_protocol import canonical, checksum, read
from core.mt_bicl_v41_bank import DATA
from core.mt_bicl_v41_collect import DIRECTORY, collect_point, controls
from core.mt_bicl_v41_panel import RELEASE, identity
from core.provider_quota import POLICY
from core.research_cohort import read_envelope, save_envelope


class PanelTransport(CollectionTransport):
    """Giữ minute retry; quota ngày trả coordinator để phục vụ shard khác trước."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return ResilientTransport.handle_request(self, request)

    def _handle_once(self, request: httpx.Request) -> httpx.Response:
        response = super()._handle_once(request)
        if response.status_code == 429:
            text = str((response.json().get('error') or {}).get('message', '')).lower()
            if 'request too large' in text and ('expected output' in text or 'requested' in text):
                response.close()
                self.pacer.stop('PROVIDER_REQUEST_EXCEEDS_LIMIT', self.pacer.state['requests'][-1]['model'])
        return response


def scope_hash(key: str) -> str:
    """Định danh giống pacer, không ghi hoặc in credential thật."""
    return hashlib.sha256((POLICY+'\0'+key).encode()).hexdigest()


def read_bindings(root: Path, release: dict[str, Any]) -> list[dict[str, str]]:
    """Chuỗi binding append-only; đổi key cần thao tác rebind tường minh và giữ lịch sử."""
    files = sorted((root/DIRECTORY/'bindings').glob('*.json'))
    if not files:
        raise DataCompletionError('Chưa bind bốn scope cho panel')
    mappings, previous = [], None
    for i, path in enumerate(files):
        saved = read(path.read_bytes())
        mapping = saved['mapping']
        if (path.name != f'{i:04d}.json' or saved['previous_sha256'] != previous
                or saved['release_sha256'] != checksum((root/RELEASE).read_bytes())
                or set(mapping) != set(release['shards']) or len(set(mapping.values())) != 4):
            raise DataCompletionError('Binding scope bị đổi/trùng hoặc đứt chain')
        if i:
            changed = [n for n in mapping if mapping[n] != mappings[-1][n]]
            if len(changed) != 1 or saved['authority'] != 'USER_EXPLICIT_REBIND_'+changed[0]:
                raise DataCompletionError('Đổi scope thiếu authority rebind tường minh')
        elif saved['authority'] != 'INITIAL_FOUR_INDEPENDENT_SCOPES_USER_CONFIRMED':
            raise DataCompletionError('Binding ban đầu thiếu authority bốn quota độc lập')
        mappings.append(mapping)
        previous = checksum(path.read_bytes())
    return mappings


def bind(root: Path, release: dict[str, Any], keys: dict[str, str], *, rebind: str | None = None) -> dict[str, str]:
    """Bind trước probe/research; không tự thay key hoặc chuyển point sang shard khác."""
    if set(keys) != set(release['shards']) or any(not isinstance(k, str) or not k for k in keys.values()):
        raise DataCompletionError('Cần đủ GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_API_KEY_3, GROQ_API_KEY_4 trong .env')
    mapping = {name: scope_hash(key) for name, key in keys.items()}
    if len(set(mapping.values())) != 4:
        raise DataCompletionError('Bốn scope phải dùng bốn key khác nhau; không nhân quota một scope')
    files = sorted((root/DIRECTORY/'bindings').glob('*.json'))
    old = read_bindings(root, release)[-1] if files else None
    if old == mapping:
        return mapping
    changed = [name for name in mapping if old and old[name] != mapping[name]]
    if old is not None and changed != [rebind]:
        raise DataCompletionError('Key khác binding; chỉ đổi có chủ ý bằng --rebind-scope scope_N, mỗi lần một scope')
    if rebind is not None and old is None:
        raise DataCompletionError('Không rebind khi chưa có binding ban đầu')
    immutable(root/DIRECTORY/'bindings'/f'{len(files):04d}.json', {
        'release_sha256': checksum((root/RELEASE).read_bytes()),
        'previous_sha256': checksum(files[-1].read_bytes()) if files else None,
        'authority': 'USER_EXPLICIT_REBIND_'+rebind if rebind else 'INITIAL_FOUR_INDEPENDENT_SCOPES_USER_CONFIRMED',
        'mapping': mapping})
    return mapping


def credentials(release: dict[str, Any], root: Path) -> dict[str, str]:
    """Chỉ coordinator do người dùng chạy đọc .env sau khi thiếu durable cache."""
    from dotenv import dotenv_values
    values = dotenv_values(root/'.env')
    return {f'scope_{i+1}': values.get(name) for i, name in enumerate(release['credential_variables'])}


def progress(root: Path, release: dict[str, Any], completed: set[str], ledger: dict[str, Any], now: float) -> dict[str, Any]:
    """Báo completion/ngày và ETA theo năng lực kế hoạch; không tính accuracy/P&L."""
    day = {}
    for name, ids in release['shards'].items():
        current = set(ids)&completed
        count = 0
        for pid in current:
            actual = [r.get('completed_at', 0.) for r in ledger['requests'] if r.get('point_id') == pid
                      and r.get('branch_id') == 'original' and r['status'] == 200]
            count += bool(actual and max(actual) >= now-86400)
        day[name] = {'complete': len(current), 'total': len(ids), 'last_24h': count, 'target_per_day': 16}
    result = {'status': 'PANEL_COMPLETE_AWAITING_COLD_ACCEPTANCE' if len(completed) == 256 else 'COLLECTION_IN_PROGRESS',
        'complete': len(completed), 'remaining': len(release['point_ids'])-len(completed), 'scope_progress': day,
        'eta_days_at_planned_64_points_per_day': (len(release['point_ids'])-len(completed))/64,
        'eta_is_guarantee': False, 'training_allowed': False}
    save_envelope(root/DIRECTORY/'progress.json', result)
    print(f"Panel {result['complete']}/256 complete; còn{result['remaining']}; ETA kế hoạch{result['eta_days_at_planned_64_points_per_day']:.2f} ngày ở64 điểm/ngày; chưa cold nghiệm thu.", flush=True)
    return result


def run(root: Path, release: dict[str, Any], *, offline: bool = False, preflight_only: bool = False,
        rebind: str | None = None, clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Một writer, replay trước key; scope bị quota được chờ riêng, không đổi shard."""
    frames, _, signature = identity(root, release)
    rows = {r['episode_id']: r for r in read((root/DATA/'observations.json').read_bytes())['rows']}
    panel_ids = release['point_ids']
    ledger_path = root/'outputs/oos_pilot/api_usage.json'
    ledger = read(ledger_path.read_bytes())
    news = {s: read((root/f'outputs/historical_memory_run/inputs/news/{s}.json').read_bytes())['scored_articles']
            for s in release['config']['symbol_order']}
    done = set()
    extra = {p.parent.name for p in (root/DIRECTORY/'points').glob('*/complete.json')} - set(panel_ids)
    if extra:
        raise DataCompletionError('Complete ngoài panel đã khóa')
    for pid in panel_ids:
        if (root/DIRECTORY/'points'/pid/'complete.json').exists():
            row = rows[pid]
            collect_point(root, row, frames[row['symbol']], news[row['symbol']], release, signature, None, lambda: ledger)
            done.add(pid)
    if len(done) == len(panel_ids):
        return progress(root, release, done, ledger, clock())
    keys, mapping = None, None
    schedule_path = root/DIRECTORY/'schedule.json'
    schedule = read_envelope(schedule_path) if schedule_path.exists() else {'cooldowns': {}}
    cache = root/DIRECTORY/'http_cache'

    def configure() -> None:
        nonlocal keys, mapping
        if keys is None:
            from scripts.prepare_groq_tokenizer import prepare_tokenizer
            prepare_tokenizer()
            keys = credentials(release, root)
            mapping = bind(root, release, keys, rebind=rebind)
            # Cả bốn scope đều được kiểm synthetic trước research đầu tiên.
            for name in release['shards']:
                operate(name, None)

    def operate(name: str, pid: str | None) -> None:
        nonlocal ledger
        pacer = ResilientPacer(ledger_path, credential=keys[name], amendment_sha256=checksum((root/RELEASE).read_bytes()), policy='request_admission_v2')
        with httpx.Client(transport=PanelTransport(pacer, cache), timeout=90.) as http:
            llms = clients(release['config'], http, keys[name])
            try:
                controls(root, release, signature, llms, pacer)
                if pid is not None:
                    old = {r['id']: checksum(canonical(r)) for r in pacer.state['requests']}
                    immutable(root/DIRECTORY/'resume_events'/(str(uuid4())+'.json'), {
                        'point_id': pid, 'scope': name, 'credential_scope': mapping[name],
                        'run_signature': signature, 'authority': release['resume'],
                        'previous_point_rows': {r['id']: checksum(canonical(r)) for r in pacer.state['requests']
                                                if r.get('run_signature') == signature and r.get('point_id') == pid}})
                    row = rows[pid]
                    collect_point(root, row, frames[row['symbol']], news[row['symbol']], release, signature, llms, lambda: pacer.state)
                    current = {r['id']: checksum(canonical(r)) for r in pacer.state['requests']}
                    if any(current.get(i) != sha for i, sha in old.items()):
                        raise DataCompletionError('Coordinator sửa HTTP/reserve cũ')
                    done.add(pid)
            except PilotStop:
                stop = pacer.state.get('last_stop') or {}
                if stop.get('reason') != 'PROVIDER_DAILY_QUOTA':
                    raise
                when = stop.get('resume_not_before_utc')
                until = datetime.fromisoformat(when).timestamp() if when else clock()+86400
                schedule['cooldowns'][mapping[name]] = max(clock()+1, until)
                save_envelope(schedule_path, schedule)
                print(f'{name}: quota provider; giữ point/UUID, phục vụ shard khác; chờ reset riêng.', flush=True)
            finally:
                ledger = read(ledger_path.read_bytes())

    if preflight_only:
        if offline:
            raise DataCompletionError('Không kết hợp preflight online với verify-only')
        configure()
        for name in release['shards']:
            operate(name, None)
        return {'status': 'PREFLIGHT_WAITING_QUOTA' if any(t > clock() for t in schedule['cooldowns'].values()) else 'CONTROL_PREFLIGHT_PASS', 'complete': len(done)}
    while len(done) < len(panel_ids):
        changed = False
        with httpx.Client(transport=ReplayTransport(ledger, cache), timeout=90.) as replay:
            llms = clients(release['config'], replay, 'offline-fixture-not-a-credential')
            for pid in panel_ids:
                if pid in done:
                    continue
                name = next(n for n, ids in release['shards'].items() if pid in ids)
                if mapping is not None and schedule['cooldowns'].get(mapping[name], 0) > clock():
                    continue
                row = rows[pid]
                try:
                    collect_point(root, row, frames[row['symbol']], news[row['symbol']], release, signature, llms, lambda: ledger)
                    done.add(pid)
                except OfflinePending:
                    if offline:
                        result = progress(root, release, done, ledger, clock())
                        return {**result, 'status': 'WAITING_USER_API'}
                    configure()
                    if schedule['cooldowns'].get(mapping[name], 0) > clock():
                        continue
                    operate(name, pid)
                    replay._transport.ledger = ledger
                changed = True
                progress(root, release, done, ledger, clock())
        if not changed:
            future = [t for key, t in schedule['cooldowns'].items() if mapping and key in mapping.values() and t > clock()]
            if not future:
                raise DataCompletionError('Coordinator không tiến triển và không có quota reset hợp lệ')
            wait = min(30., max(1., min(future)-clock()))
            print(f'Các shard còn lại đang chờ quota; nghỉ{wait:.0f} giây. Ctrl+C rồi chạy lại cùng lệnh để resume.', flush=True)
            sleep(wait)
    return progress(root, release, done, ledger, clock())
