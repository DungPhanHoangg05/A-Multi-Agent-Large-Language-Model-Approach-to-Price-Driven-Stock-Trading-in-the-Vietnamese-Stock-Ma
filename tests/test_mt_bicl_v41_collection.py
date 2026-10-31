"""Kiểm panel, một writer/bốn scope và cold canonical replay với HTTP giả hoàn toàn."""

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from core.groq_pacing import PilotStop
from core.improvement_recovery import ResilientPacer
from core.mt_bicl_v4_collect import clients
from core.mt_bicl_v4_collect_transport import OfflinePending, ReplayTransport
from core.mt_bicl_v4_completion import DataCompletionError
from core.mt_bicl_v4_dataset import immutable
from core.mt_bicl_v4_protocol import canonical, checksum, read
from core.mt_bicl_v41_bank import DATA
from core.mt_bicl_v41_collect import DIRECTORY, cold_point, collect_point, controls
from core.mt_bicl_v41_panel import RELEASE, accept
from core.mt_bicl_v41_runtime import PanelTransport, bind, read_bindings, run
from test_mt_bicl_v4_collection import runtime as old_runtime


def runtime(root: Path):
    """Tái dùng fixture SDK thật, đổi riêng namespace và transport coordinator mới."""
    row,frame,release,pacer,old_transport,old_http,_,wires=old_runtime(root)
    release.update(point_ids=[row['episode_id']], shards={'scope_1':[row['episode_id']], 'scope_2':[], 'scope_3':[], 'scope_4':[]},
                   credential_variables=[f'GROQ_API_KEY_{i}' for i in range(1,5)])
    transport=PanelTransport(pacer,root/DIRECTORY/'http_cache',old_transport.inner.inner)
    http=httpx.Client(transport=transport)
    llms=clients(release['config'],http,'fixture-not-a-real-key')
    old_http.close()
    return row,frame,release,pacer,transport,http,llms,wires


class PanelTests(unittest.TestCase):
    """Không HTTP thật, không .env thật và không xóa/rewrite bằng chứng cũ."""

    def test_three_research_calls_then_cold_rebuild_without_new_HTTP(self) -> None:
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,transport,http,llms,wires=runtime(root)
            saved=collect_point(root,row,frame,[],release,'a'*64,llms,lambda:pacer.state)
            self.assertEqual(len(wires),3)
            before=deepcopy(pacer.state['requests'])
            self.assertEqual(saved,cold_point(root,row,frame,[],release,'a'*64,pacer.state))
            self.assertEqual(len(wires),3)
            self.assertEqual(before,pacer.state['requests'])
            self.assertEqual(saved,collect_point(root,row,frame,[],release,'a'*64,None,lambda:pacer.state))
            self.assertEqual(saved['version'],'conditional_v4_1_collected_point')
            http.close()

    def test_point_outside_panel_cannot_create_HTTP_or_journal(self) -> None:
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,_,http,llms,wires=runtime(root)
            release['point_ids']=[]
            with self.assertRaises(DataCompletionError): collect_point(root,row,frame,[],release,'a'*64,llms,lambda:pacer.state)
            self.assertFalse((root/DIRECTORY/'points').exists())
            self.assertEqual(wires,[])
            http.close()

    def test_same_UUID_after_interruption_reuses_raw_before_HTTP(self) -> None:
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,transport,http,llms,wires=runtime(root)
            original_store=transport._store
            stopped=[]
            def once(request,response):
                original_store(request,response)
                if not stopped:
                    stopped.append(True)
                    raise KeyboardInterrupt()
            with patch.object(transport,'_store',once):
                with self.assertRaises(KeyboardInterrupt): collect_point(root,row,frame,[],release,'a'*64,llms,lambda:pacer.state)
            first=deepcopy(pacer.state['requests'][0])
            collect_point(root,row,frame,[],release,'a'*64,llms,lambda:pacer.state)
            self.assertEqual(len(wires),3)
            self.assertEqual(pacer.state['requests'][0],first)
            http.close()

    def test_daily_quota_returns_to_coordinator_instead_of_waiting_inside_transport(self) -> None:
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()):
            root=Path(folder)
            _,_,release,pacer,transport,http,llms,wires=runtime(root)
            transport.inner.inner.handler=lambda request:httpx.Response(429,json={'error':{'message':'TPD daily limit, retry after 10 seconds'}},
                headers={'retry-after':'10'},request=request)
            with self.assertRaises(PilotStop): controls(root,release,'a'*64,llms,pacer)
            self.assertEqual(pacer.state['last_stop']['reason'],'PROVIDER_DAILY_QUOTA')
            self.assertEqual(len(pacer.state['requests']),1)
            http.close()

    def test_intrinsically_too_large_request_does_not_retry_forever(self) -> None:
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()):
            root=Path(folder)
            _,_,release,pacer,transport,http,llms,_=runtime(root)
            transport.inner.inner.handler=lambda request:httpx.Response(429,json={'error':{'message':'Request too large, Requested 1024 exceeds OTPM Limit 1000'}},request=request)
            with self.assertRaises(PilotStop): controls(root,release,'a'*64,llms,pacer)
            self.assertEqual(pacer.state['last_stop']['reason'],'PROVIDER_REQUEST_EXCEEDS_LIMIT')
            self.assertEqual(len(pacer.state['requests']),1)
            http.close()

    def test_four_scope_binding_and_explicit_rebind_keep_old_chain(self) -> None:
        with TemporaryDirectory() as folder:
            root=Path(folder)
            release={'shards':{f'scope_{i}':[] for i in range(1,5)}}
            immutable(root/RELEASE,{'fixture':True})
            keys={n:'fixture-key-'+n for n in release['shards']}
            first=bind(root,release,keys)
            before=(root/DIRECTORY/'bindings'/'0000.json').read_bytes()
            keys['scope_2']='fixture-changed-key'
            with self.assertRaises(DataCompletionError): bind(root,release,keys)
            second=bind(root,release,keys,rebind='scope_2')
            self.assertNotEqual(first['scope_2'],second['scope_2'])
            self.assertEqual(read_bindings(root,release),[first,second])
            self.assertEqual(before,(root/DIRECTORY/'bindings'/'0000.json').read_bytes())
            keys['scope_3']=keys['scope_2']
            with self.assertRaises(DataCompletionError): bind(root,release,keys)

    def test_full_command_fixtures_then_resume_never_reads_key_or_downloads(self) -> None:
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,transport,http,llms,wires=runtime(root)
            immutable(root/RELEASE,{'fixture':True})
            immutable(root/DATA/'observations.json',{'rows':[row]})
            for symbol in release['config']['symbol_order']:
                immutable(root/f'outputs/historical_memory_run/inputs/news/{symbol}.json',{'scored_articles':[]})
            pacer.path=root/'outputs/oos_pilot/api_usage.json';pacer.save()
            keys={f'scope_{i}':'fixture-key-'+str(i) for i in range(1,5)}
            normal=transport.inner.inner.handler
            def pacer_factory(path,credential,amendment_sha256,**kwargs):
                return ResilientPacer(path,credential=credential,amendment_sha256=amendment_sha256,
                    clock=pacer.clock,monotonic=pacer.monotonic,sleep=pacer.sleep,**kwargs)
            def transport_factory(actual,cache):
                return PanelTransport(actual,cache,httpx.MockTransport(normal))
            with patch('core.mt_bicl_v41_runtime.identity',return_value=({'FPT':frame},{},'a'*64)), \
                 patch('core.mt_bicl_v41_runtime.credentials',return_value=keys) as credential, \
                 patch('core.mt_bicl_v41_runtime.ResilientPacer',side_effect=pacer_factory), \
                 patch('core.mt_bicl_v41_runtime.PanelTransport',side_effect=transport_factory), \
                 patch('scripts.prepare_groq_tokenizer.prepare_tokenizer') as tokenizer:
                result=run(root,release,clock=pacer.clock,sleep=pacer.sleep)
                self.assertEqual(result['complete'],1)
                credential.assert_called_once();tokenizer.assert_called_once()
            self.assertEqual(len(wires),15)
            recorded=read(pacer.path.read_bytes())['requests']
            self.assertTrue(all(r['point_id'].startswith('CONTROL_V4_') for r in recorded[:12]))
            with patch('core.mt_bicl_v41_runtime.identity',return_value=({'FPT':frame},{},'a'*64)), \
                 patch('core.mt_bicl_v41_runtime.credentials',side_effect=AssertionError('Không được đọc key')), \
                 patch('scripts.prepare_groq_tokenizer.prepare_tokenizer',side_effect=AssertionError('Không được tải setup')):
                self.assertEqual(run(root,release,offline=True,clock=pacer.clock)['complete'],1)
            self.assertEqual(len(wires),15)
            http.close()

    def test_acceptance_is_incomplete_without_256_unique_points(self) -> None:
        with TemporaryDirectory() as folder,patch('core.mt_bicl_v41_panel.verify_release',return_value={'point_ids':['fixture-'+str(i) for i in range(256)]}), \
             patch('core.mt_bicl_v41_panel.build',return_value={'status':'NUMERIC_BANK_PASS'}):
            result=accept(Path(folder))
            self.assertEqual(result['status'],'INCOMPLETE_PANEL')
            self.assertEqual(result['remaining'],256)
            self.assertFalse(result['ready_for_W11_19'])

    def test_coordinator_serves_other_shard_then_resumes_quota_scope(self) -> None:
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,transport,http,_,wires=runtime(root)
            second={**row,'episode_id':'FPT-2018-01-31','as_of_date':'2018-01-31'}
            release['point_ids']=[row['episode_id'],second['episode_id']]
            release['shards']['scope_2']=[second['episode_id']]
            immutable(root/RELEASE,{'fixture':True})
            immutable(root/DATA/'observations.json',{'rows':[row,second]})
            for symbol in release['config']['symbol_order']:
                immutable(root/f'outputs/historical_memory_run/inputs/news/{symbol}.json',{'scored_articles':[]})
            pacer.path=root/'outputs/oos_pilot/api_usage.json';pacer.save()
            keys={f'scope_{i}':'fixture-key-'+str(i) for i in range(1,5)}
            normal=transport.inner.inner.handler
            failed=[]
            def provider(request):
                if request.headers.get('authorization')=='Bearer fixture-key-1' and not failed:
                    failed.append(True)
                    return httpx.Response(429,json={'error':{'message':'TPD daily limit, retry after 1 seconds'}},
                        headers={'retry-after':'1'},request=request)
                return normal(request)
            def pacer_factory(path,credential,amendment_sha256,**kwargs):
                return ResilientPacer(path,credential=credential,amendment_sha256=amendment_sha256,
                    clock=pacer.clock,monotonic=pacer.monotonic,sleep=pacer.sleep,**kwargs)
            with patch('core.mt_bicl_v41_runtime.identity',return_value=({'FPT':frame},{},'a'*64)), \
                 patch('core.mt_bicl_v41_runtime.credentials',return_value=keys), \
                 patch('core.mt_bicl_v41_runtime.ResilientPacer',side_effect=pacer_factory), \
                 patch('core.mt_bicl_v41_runtime.PanelTransport',side_effect=lambda p,c:PanelTransport(p,c,httpx.MockTransport(provider))), \
                 patch('scripts.prepare_groq_tokenizer.prepare_tokenizer'):
                result=run(root,release,clock=pacer.clock,sleep=pacer.sleep)
            self.assertEqual(result['complete'],2)
            records=read(pacer.path.read_bytes())['requests']
            market=[r for r in records if not r['point_id'].startswith('CONTROL_V4_')]
            self.assertEqual(market[0]['point_id'],second['episode_id'])
            self.assertEqual(len(market),6)
            recovered=[r for r in records if r.get('checkpoint_attempt_id')==records[0]['checkpoint_attempt_id']]
            self.assertEqual([r['status'] for r in recovered],[429,200])
            self.assertEqual(len(wires),18)
            http.close()

    def test_cold_future_price_and_news_poison_cannot_change_point_binding(self) -> None:
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,_,http,llms,wires=runtime(root)
            collect_point(root,row,frame,[],release,'a'*64,llms,lambda:pacer.state)
            altered=frame.copy(deep=True)
            altered.loc[altered['Datetime']>row['as_of_date'],['Open','High','Low','Close']]*=100
            article={'date_parsed':'2025-01-01','sentiment':'positive','title':'Tin sau query không được đọc'}
            cold_point(root,row,altered,[article],release,'a'*64,pacer.state)
            self.assertEqual(len(wires),3)
            http.close()


if __name__=='__main__':
    unittest.main()
