"""Kiểm PIT/nguồn/ledger và chống giả mạo point complete trong collection v4."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from core.mt_bicl_v4_collect import assemble, collect_point, input_state
from core.mt_bicl_v4_collect_transport import CollectionTransport, OfflinePending
from core.mt_bicl_v4_completion import BASE, DIRECTORY
from core.mt_bicl_v4_protocol import read
from core.mt_bicl_v4_warmup import PendingWarmup, load_warmup
from test_mt_bicl_v4_collection import runtime


class CollectionLeakageTests(unittest.TestCase):
    """Không dùng tương lai, không lấy báo cáo/a0 fake hoặc bỏ reserve của HTTP chưa biết."""

    def test_price_and_news_after_query_do_not_change_PIT_binding(self) -> None:
        with TemporaryDirectory() as folder:
            row,frame,release,pacer,transport,http,llms,wires=runtime(Path(folder))
            _,before=input_state(row,frame,[],release['config'],render_images=False)
            changed=frame.copy()
            changed.loc[changed['Datetime']>row['as_of_date'],['Open','High','Low','Close','Reference']]=float('nan')
            future=[{'date_parsed':'2025-01-01','label':'positive','numeric_score':1}]
            _,after=input_state(row,changed,future,release['config'],render_images=False)
            self.assertEqual(before,after)
            self.assertLessEqual(after['price_end_date'],row['as_of_date'])
            http.close()

    def test_missing_warmup_stops_before_graph_or_HTTP(self) -> None:
        with TemporaryDirectory() as folder:
            row,frame,release,pacer,transport,http,llms,wires=runtime(Path(folder))
            short=frame.loc[frame['Datetime']>='2018-01-02'].copy()
            with self.assertRaises(ValueError): input_state(row,short,[],release['config'])
            self.assertEqual(wires,[])
            http.close()

    def test_confirmation_year_is_rejected_before_any_HTTP(self) -> None:
        with TemporaryDirectory() as folder:
            row,frame,release,pacer,transport,http,llms,wires=runtime(Path(folder))
            row['as_of_date']='2025-01-02'
            with self.assertRaises(ValueError): input_state(row,frame,[],release['config'])
            self.assertFalse(wires)
            http.close()

    def test_self_modified_complete_agent_or_action_is_rejected(self) -> None:
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,transport,http,llms,wires=runtime(root)
            collect_point(root,row,frame,[],release,'a'*64,llms,lambda:pacer.state)
            path=root/DIRECTORY/'points'/row['episode_id']/'complete.json'
            original=path.read_bytes()
            saved=json.loads(original)
            saved['agent']['categories']['original_action']='CASH'
            path.write_text(json.dumps(saved,ensure_ascii=False),encoding='utf-8')
            with self.assertRaises(ValueError): collect_point(root,row,frame,[],release,'a'*64,None,lambda:pacer.state)
            self.assertEqual(len(wires),3)
            http.close()

    def test_missing_stamped_raw_cache_cannot_trigger_replay(self) -> None:
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,transport,http,llms,wires=runtime(root)
            result=collect_point(root,row,frame,[],release,'a'*64,llms,lambda:pacer.state)
            raw=next(iter(result['http']['raw_sha256']))
            (root/DIRECTORY/'http_cache'/(raw+'.json')).unlink()
            with self.assertRaises((ValueError,FileNotFoundError)): collect_point(root,row,frame,[],release,'a'*64,None,lambda:pacer.state)
            self.assertEqual(len(wires),3)
            http.close()

    def test_existing_ledger_rows_preserved_during_fresh_collection(self) -> None:
        with TemporaryDirectory() as folder,redirect_stdout(io.StringIO()):
            root=Path(folder)
            row,frame,release,pacer,transport,http,llms,wires=runtime(root)
            collect_point(root,row,frame,[],release,'a'*64,llms,lambda:pacer.state)
            old=deepcopy(pacer.state['requests'])
            collect_point(root,row,frame,[],release,'a'*64,None,lambda:pacer.state)
            self.assertEqual(old,pacer.state['requests'])
            self.assertTrue(all(r['run_signature']=='a'*64 for r in old))
            self.assertTrue(all(r['checkpoint_attempt_id'] for r in old))
            http.close()

    def test_offline_warmup_never_fetches_source(self) -> None:
        with TemporaryDirectory() as folder:
            release={'config':{'symbol_order':['FPT']},'warmup':{'start':'2015-01-01','end':'2018-01-15'}}
            with self.assertRaises(PendingWarmup): load_warmup(Path(folder),release)

    def test_duplicate_completed_point_cannot_inflate_data_cohort(self) -> None:
        root=Path('.').resolve()
        rows=read((root/BASE/'observations.json').read_bytes())['rows']
        ids=[r['episode_id'] for r in rows]
        completed=[{'binding':{'point_id':pid}} for pid in ids]
        completed.append(deepcopy(completed[0]))
        with self.assertRaises(ValueError): assemble(root,{'point_ids':ids},'a'*64,completed,{})


if __name__=='__main__':
    unittest.main()
