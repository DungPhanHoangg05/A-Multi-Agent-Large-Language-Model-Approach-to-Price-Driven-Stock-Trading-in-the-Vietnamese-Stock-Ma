"""Kiểm runner collection bằng SDK/pacer/transport thật và provider hoàn toàn giả lập."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from core.improvement_recovery import ResilientPacer
from core.mt_bicl_v4_collect import clients, collect_point
from core.mt_bicl_v4_collect_transport import CollectionTransport, OfflinePending, ReplayTransport
from core.mt_bicl_v4_completion import DIRECTORY
from core.mt_bicl_v4_protocol import read
from scripts.continue_mt_bicl_v4_data import controls
from scripts.continue_mt_bicl_v4_data import run as run_collection
from core.mt_bicl_v4_dataset import immutable
from core.mt_bicl_v4_completion import BASE, RELEASE
from test_mt_bicl_v4_completion import warmup_fixture
from core.mt_bicl_v4_warmup import combine_warmup


DECISION = {"decision": "LONG", "forecast_horizon": "T+2.5", "confidence": "Thấp", "risk_reward_ratio": 1.,
            "evidence_for": "Fixture offline.", "evidence_against": "Không là dự báo thật.", "justification": "Chỉ kiểm hợp đồng."}
REPORT = "\n".join(["**Đồng thuận chủ đạo:** Tăng", "**Hướng xu hướng:** Tăng", "**Thiên lệch dự báo:** Tăng",
    "**Mô hình:** Tăng giá", "**Độ tin cậy:** Trung bình", "**Bằng chứng:** Fixture nến giả lập.",
    "**Nến quan trọng:** Nến cuối", "**Hàm ý giao dịch:** Chỉ kiểm giao thức.",
    "**Hỗ trợ:** 99", "**Kháng cự:** 101", "**Xu hướng:** Tăng"])


class Clock:
    """Đồng hồ tiến bằng sleep giả để không chờ quota thật trong test."""
    def __init__(self) -> None:
        self.value = 1_800_000_000.
    def now(self) -> float:
        return self.value
    def sleep(self, seconds: float) -> None:
        self.value += seconds


def runtime(root: Path, *, fail_store: bool = False) -> tuple:
    """Một point2018 có đủ warmup synthetic; mọi HTTP đi vào MockTransport."""
    records, base, settings = warmup_fixture()
    import warnings
    from scipy.stats import ConstantInputWarning
    warnings.filterwarnings("ignore", category=ConstantInputWarning)
    frame, _ = combine_warmup('FPT', records, base, settings)
    cutoff = str(base['Datetime'].iloc[20].date())
    row = {'episode_id': 'FPT-' + cutoff, 'symbol': 'FPT', 'as_of_date': cutoff}
    release = {'config': read(Path('docs/plan/week11/protocol_v3.json').read_bytes())['decision']['config'],
               'resume':'FIXTURE_SAME_UUID_CACHE_FIRST'}
    wires = []
    def provider(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        wires.append(body)
        texts = str(body['messages'])
        if 'CONTROL ONLY' in texts:
            if body.get('response_format'):
                result = {'decision': 'SHORT', 'forecast_horizon': 'T+2.5', 'confidence': 'Thấp', 'risk_reward_ratio': 1.,
                    'evidence_for': 'Kiểm giao thức giả lập.', 'evidence_against': 'Không có dữ liệu thị trường.', 'justification': 'Chỉ kiểm schema.'}
                content = json.dumps(result, ensure_ascii=False)
            else:
                content = 'CONTROL_PASS'
        else:
            content = json.dumps(DECISION, ensure_ascii=False) if body.get('response_format') else REPORT
        return httpx.Response(200, json={'id': 'chat_fixture_' + str(len(wires)), 'object': 'chat.completion',
            'model': body['model'], 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 30, 'completion_tokens': 10, 'total_tokens': 40}}, headers={'x-request-id': 'fixture-' + str(len(wires))}, request=request)
    clock = Clock()
    pacer = ResilientPacer(root/'ledger.json', credential='fixture-not-a-real-key', amendment_sha256='a'*64,
        clock=clock.now, monotonic=clock.now, sleep=clock.sleep, policy='request_admission_v2')
    transport = CollectionTransport(pacer, root/DIRECTORY/'http_cache', httpx.MockTransport(provider))
    http = httpx.Client(transport=transport)
    llms = clients(release['config'], http, 'fixture-not-a-real-key')
    return row, frame, release, pacer, transport, http, llms, wires


class CollectionTests(unittest.TestCase):
    """Paired một upstream/point, cache trước credential, UUID không đổi sau interruption."""

    def test_real_pipeline_and_second_pass_do_not_replay_complete(self) -> None:
        with TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            root = Path(folder)
            row, frame, release, pacer, transport, http, llms, wires = runtime(root)
            result = collect_point(root,row,frame,[],release,'a'*64,llms,lambda:pacer.state)
            count = len(wires)
            self.assertEqual(count,3)
            self.assertEqual(result['original'],DECISION)
            self.assertEqual(result['agent']['categories']['original_action'],'LONG')
            again = collect_point(root,row,frame,[],release,'a'*64,None,lambda:pacer.state)
            self.assertEqual(result,again)
            self.assertEqual(count,len(wires))
            http.close()

    def test_interrupted_stage_replays_durable_HTTP_before_next_missing_stage(self) -> None:
        from core.prior_stage_journal import StageJournal
        with TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,transport,http,llms,wires=runtime(root)
            original_save=StageJournal.save
            stopped=[]
            def stop_after_response(journal,candidate):
                if candidate['nodes'].get('pattern',{}).get('attempts') and candidate['nodes']['pattern']['attempts'][-1]['status']=='complete' and not stopped:
                    stopped.append(True)
                    raise KeyboardInterrupt()
                return original_save(journal,candidate)
            with patch.object(StageJournal,'save',stop_after_response):
                with self.assertRaises(KeyboardInterrupt): collect_point(root,row,frame,[],release,'a'*64,llms,lambda:pacer.state)
            attempt=pacer.state['requests'][0]['checkpoint_attempt_id']
            replay_http=httpx.Client(transport=ReplayTransport(pacer.state,root/DIRECTORY/'http_cache'))
            replay_llms=clients(release['config'],replay_http,'offline-fixture')
            with self.assertRaises(OfflinePending): collect_point(root,row,frame,[],release,'a'*64,replay_llms,lambda:pacer.state)
            self.assertEqual(len(wires),1)
            result=collect_point(root,row,frame,[],release,'a'*64,llms,lambda:pacer.state)
            self.assertEqual(pacer.state['requests'][0]['checkpoint_attempt_id'],attempt)
            self.assertEqual(len(wires),3)
            self.assertEqual(result['original'],DECISION)
            replay_http.close();http.close()

    def test_lost_unsealed_response_retains_old_row_and_same_UUID(self) -> None:
        with TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,transport,http,llms,wires=runtime(root)
            original_store=transport._store
            stopped=[]
            def lose_once(request,response):
                if not stopped:
                    stopped.append(True)
                    raise KeyboardInterrupt()
                return original_store(request,response)
            with patch.object(transport,'_store',lose_once):
                with self.assertRaises(KeyboardInterrupt): collect_point(root,row,frame,[],release,'a'*64,llms,lambda:pacer.state)
            old=deepcopy(pacer.state['requests'][0])
            result=collect_point(root,row,frame,[],release,'a'*64,llms,lambda:pacer.state)
            self.assertEqual(pacer.state['requests'][0],old)
            self.assertEqual(pacer.state['requests'][1]['checkpoint_attempt_id'],old['checkpoint_attempt_id'])
            self.assertIn(old['id'],result['http']['unsealed_response_missing_ids'])
            self.assertEqual(len(wires),4)
            http.close()

    def test_synthetic_controls_complete_once_per_credential_scope(self) -> None:
        with TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,transport,http,llms,wires=runtime(root)
            controls(root,release,'a'*64,llms,pacer)
            self.assertEqual(len(wires),3)
            controls(root,release,'a'*64,llms,pacer)
            self.assertEqual(len(wires),3)
            self.assertTrue(all(r['point_id'].startswith('CONTROL_V4_') for r in pacer.state['requests']))
            http.close()

    def test_model_options_remain_pinned_for_both_roles(self) -> None:
        with TemporaryDirectory() as folder:
            values=runtime(Path(folder))
            llms=values[-2]
            self.assertEqual(llms[0]._default_params['reasoning_effort'],'low')
            self.assertEqual(llms[1]._default_params['reasoning_effort'],'none')
            self.assertEqual(llms[0].max_retries,0)
            values[5].close()

    def test_new_credential_repeats_only_synthetic_controls_keeps_old_rows(self) -> None:
        with TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,transport,http,llms,wires=runtime(root)
            controls(root,release,'a'*64,llms,pacer)
            old=deepcopy(pacer.state['requests'])
            second=ResilientPacer(root/'ledger.json',credential='fixture-second-key',amendment_sha256='a'*64,
                clock=pacer.clock,monotonic=pacer.monotonic,sleep=pacer.sleep,policy='request_admission_v2')
            second_http=httpx.Client(transport=CollectionTransport(second,root/DIRECTORY/'http_cache',transport.inner.inner))
            controls(root,release,'a'*64,clients(release['config'],second_http,'fixture-second-key'),second)
            self.assertEqual(len(wires),6)
            self.assertEqual(second.state['requests'][:3],old)
            self.assertNotEqual(pacer.credential_scope,second.credential_scope)
            second_http.close();http.close()

    def test_daily_quota_waits_then_retries_same_UUID_without_hour_cap(self) -> None:
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,transport,http,llms,wires=runtime(root)
            normal=transport.inner.inner.handler
            first=[]
            def limited(request):
                if not first:
                    first.append(True)
                    return httpx.Response(429,json={'error':{'message':'Daily quota, retry after 2 seconds','code':'RPD'}},
                        headers={'retry-after':'2','x-ratelimit-remaining-requests':'0','x-ratelimit-reset-requests':'2s'},request=request)
                return normal(request)
            transport.inner.inner.handler=limited
            controls(root,release,'a'*64,llms,pacer)
            failed=pacer.state['requests'][0]
            successful=pacer.state['requests'][1]
            self.assertEqual(failed['status'],429)
            self.assertEqual(successful['status'],200)
            self.assertEqual(failed['checkpoint_attempt_id'],successful['checkpoint_attempt_id'])
            self.assertGreaterEqual(pacer.state.get('pacing_seconds',0),2.)
            http.close()

    def test_failed_control_stops_before_any_market_point(self) -> None:
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,transport,http,llms,wires=runtime(root)
            normal=transport.inner.inner.handler
            def wrong(request):
                response=normal(request)
                value=response.json();value['choices'][0]['message']['content']='WRONG_CONTROL'
                return httpx.Response(200,json=value,request=request)
            transport.inner.inner.handler=wrong
            with self.assertRaises(ValueError): controls(root,release,'a'*64,llms,pacer)
            self.assertEqual(len(wires),1)
            self.assertTrue(all(r['point_id'].startswith('CONTROL_V4_') for r in pacer.state['requests']))
            previous=deepcopy(pacer.state['requests'][0])
            transport.inner.inner.handler=normal
            controls(root,release,'a'*64,llms,pacer)
            self.assertEqual(len(wires),4)
            self.assertEqual(pacer.state['requests'][0],previous)
            self.assertEqual(pacer.state['requests'][1]['checkpoint_attempt_id'],previous['checkpoint_attempt_id'])
            http.close()

    def test_single_command_pipeline_then_offline_resume_never_reads_key(self) -> None:
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,transport,http,llms,wires=runtime(root)
            release['point_ids']=[row['episode_id']]
            immutable(root/RELEASE,{'fixture':True})
            immutable(root/BASE/'observations.json',{'rows':[row]})
            for symbol in release['config']['symbol_order']:
                immutable(root/f'outputs/historical_memory_run/inputs/news/{symbol}.json',{'scored_articles':[]})
            pacer.path=root/'outputs/oos_pilot/api_usage.json'
            pacer.save()
            synthetic_warmup=({'FPT':frame},{'fixture_warmup':True})
            with patch('scripts.continue_mt_bicl_v4_data.load_warmup',return_value=synthetic_warmup), \
                 patch('scripts.continue_mt_bicl_v4_data.verify_release',return_value=release), \
                 patch('scripts.continue_mt_bicl_v4_data.ResilientPacer',return_value=pacer), \
                 patch('scripts.continue_mt_bicl_v4_data.CollectionTransport',return_value=transport), \
                 patch('scripts.continue_mt_bicl_v4_data.assemble',return_value={'status':'FIXTURE_ONLY','points':1}), \
                 patch('scripts.continue_mt_bicl_v4_data.prepare_tokenizer',return_value=Path('fixture')) as tokenizer, \
                 patch('dotenv.dotenv_values',return_value={'GROQ_API_KEY':'fixture-not-a-real-key'}) as key:
                result=run_collection(root,release)
                self.assertEqual(result['points'],1)
                key.assert_called_once()
                tokenizer.assert_called_once()
            self.assertEqual(len(wires),6)
            with patch('scripts.continue_mt_bicl_v4_data.load_warmup',return_value=synthetic_warmup), \
                 patch('scripts.continue_mt_bicl_v4_data.verify_release',return_value=release), \
                 patch('scripts.continue_mt_bicl_v4_data.assemble',return_value={'status':'FIXTURE_ONLY','points':1}), \
                 patch('scripts.continue_mt_bicl_v4_data.prepare_tokenizer',side_effect=AssertionError('Không tải lại setup khi complete')), \
                 patch('dotenv.dotenv_values',side_effect=AssertionError('Không được đọc key sau complete')):
                run_collection(root,release,offline=True)
            self.assertEqual(len(wires),6)
            http.close()


if __name__=='__main__':
    unittest.main()
