"""Lượt R4 riêng: prompt giá trị đã khóa, pool năm key, checkpoint và resume raw response."""

from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
from typing import Any

from core.revision_common_study import digest, read_json, write_json
from core.revision72_run import CachedLLM, checked, signed
from core.revision_call_archive import StudyLock
from core.revision_r4_factorial import POLICY, VARIANTS, actual_text, factor_rows, prompt_parts


def sha(path: Path) -> str:
    """Hash byte nguồn, không hash credential."""
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime() -> dict:
    """Khóa các dependency dùng cho inference/archive/phân tích mới."""
    return {'python':sys.version.split()[0],**{name:version(name) for name in
        ('langchain-core','langchain-groq','groq','pydantic','numpy','pandas')}}


def prepare(root: Path, bank: Path, units: list[dict], sources: list[Path]) -> None:
    """Đóng băng 90 prompts/270 jobs trước API; không đổi bank/run R1."""
    if bank.exists():raise FileExistsError('Bank R4 đã có; không ghi đè hoặc refreeze sau outcome')
    if len(units)!=18 or len({u['unit']['id'] for u in units})!=18:raise ValueError('Cần đúng 18 unit IDs')
    files=[*sources,*(root/'agents').glob('*.py'),*(root/'utils').glob('*.py')]
    files += [root/p for p in ('core/revision72_run.py','core/revision72_provider.py','core/revision72_quota.py',
        'core/revision_call_archive.py','core/revision_common_study.py','core/revision_baselines.py',
        'core/alpha_compare.py','core/backtest_engine.py','default_config.py')]
    files += [root/'outputs/revision/r1_72h_run_v2/analysis/predictions.csv',root/'outputs/revision/r1_prices_v1/manifest.json',
        *sorted((root/'outputs/revision/r1_prices_v1').glob('*.csv'))]
    jobs=[]
    for u in sorted(units,key=lambda x:(x['unit']['date'],x['unit']['id'])):
        for repeat in range(3):
            offset=repeat*2;order=VARIANTS[offset:]+VARIANTS[:offset]
            for variant in order:
                prompt=u['prompts'][variant]
                if len(prompt)>=6500:raise ValueError('Prompt quá dài trước freeze')
                if variant in ('A','AS','P') and factor_rows(prompt_parts(prompt)['alpha'])!=5:raise ValueError('Mất factor rows')
                jobs.append({'unit_id':u['unit']['id'],'org':u['org'],'variant':variant,'repeat':repeat,
                    'realization':0,'stage':'decision','node':'Decision Maker','model':'openai/gpt-oss-20b','smoke':False})
    value={'schema_version':'revision_r4_value_bank_v1','created_utc':datetime.now(timezone.utc).isoformat(),
        'policy':POLICY,'model':'openai/gpt-oss-20b','temperature':0.0,'max_tokens':2048,'max_prompt_chars_exclusive':6500,
        'runtime':runtime(),'units':units,'jobs':jobs,'n_decisions':270,'n_new_vision_calls':0,
        'source_hashes':[{'path':p.relative_to(root).as_posix(),'sha256':sha(p)} for p in sorted(set(files))]}
    bank.mkdir(parents=True)
    write_json(bank/'manifest.json',signed(value),True)
    print('Đã khóa bank R4: 90 prompts, 270 Decision calls mới; 0 vision calls; chưa gọi API.')


def verify_bank(root: Path, bank: Path) -> dict:
    """Từ chối đổi code/config/input/runtime hoặc sửa prompt sau freeze."""
    m=checked(bank/'manifest.json')
    if m['runtime']!=runtime():raise ValueError('Runtime R4 đã đổi; không resume bằng môi trường khác')
    for r in m['source_hashes']:
        if sha(root/r['path'])!=r['sha256']:raise ValueError('Nguồn R4 đã đổi: '+r['path'])
    for u in m['units']:
        for v in VARIANTS:
            text=u['prompts'][v]
            if digest(text)!=u['prompt_hashes'][v] or len(text)>=6500:raise ValueError('Prompt hash/budget R4 sai')
            if v in ('A','AS','P') and factor_rows(prompt_parts(text)['alpha'])!=5:raise ValueError('Thiếu factor rows')
    return m


def point_path(run: Path, job: dict) -> Path:
    """Identity tách variant/repeat và shard, không va checkpoint cũ."""
    return run/f"shards/org{job['org']}/decisions/{job['unit_id']}_{job['variant']}_n{job['repeat']}.json"


def verify_point(path: Path, job: dict, parent: dict) -> dict:
    """Response ID/context/prompt/schema/hash phải đúng execution mới; không chỉ tin prediction."""
    from agents.decision_agent import TradeDecisionOutput
    value=checked(path)
    if value['context']!=job or value['parent']!=parent or not value['request_ids']:raise ValueError('Checkpoint R4 khác context/parent')
    shard=path.parent.parent
    for r in value['call_hashes']:
        if sha(shard/r['path'])!=r['sha256']:raise ValueError('Raw R4 đã bị sửa')
    last=None
    for attempt in value['request_ids']:
        request=checked(shard/f'calls/{attempt}.request.json');response=read_json(shard/f'calls/{attempt}.response.json')
        context={k:v for k,v in request['context'].items() if k not in ('provider_org','execution_epoch')}
        if request['bank_id']!=parent['bank_id'] or context!=job or digest(actual_text(request))!=parent['prompt_hash'] or response['parent_request_hash']!=request['sha256']:
            raise ValueError('Raw request R4 không thuộc đúng prompt/repeat')
        last=response
    message=last['response']['generations'][0][0]['message']
    # LangChain ghi message là serialized AIMessage với content/tool_calls ở cấp gốc.
    data=message['tool_calls'][0]['args'] if message.get('tool_calls') else json.loads(message['content'])
    if TradeDecisionOutput.model_validate(data).decision!=value['prediction']:raise ValueError('Prediction không khớp raw R4')
    return value


def parent_for(m: dict, unit: dict, variant: str) -> dict:
    """Khóa nguồn upstream, asset, donor và actual prompt trong mọi checkpoint."""
    return {'bank_id':m['sha256'],'asset_hash':unit['asset_hash'],'donor_hash':unit['donor_hash'] if variant=='P' else None,
        'upstream_hash':unit['upstream_parent_hash'],'prompt_hash':unit['prompt_hashes'][variant]}


def perform_call(llm: Any, archive: Any, job: dict, prompt: str, parent: dict, path: Path) -> dict:
    """Giữ wrapper/schema native; lưu checkpoint ngay sau mỗi successful test point."""
    from agents.decision_agent import _invoke_with_retry, _normalize_structured_result, DECISION_FORMAT_ATTEMPTS
    archive.context=dict(job);before=len(archive.ids)
    for attempt in range(DECISION_FORMAT_ATTEMPTS):
        result=_invoke_with_retry(llm.invoke,prompt,retries=1)
        try:
            normalized,_=_normalize_structured_result(result,'vi');data=json.loads(normalized)
            break
        except ValueError:
            if attempt+1==DECISION_FORMAT_ATTEMPTS:raise
    shard=path.parent.parent
    all_ids=archive.ids[before:];ids=[a for a in all_ids if (shard/f'calls/{a}.response.json').exists()]
    if not ids:raise ValueError('Không có successful raw response R4; không điền prediction')
    files=[p for a in all_ids for suffix in ('request','response','error') if (p:=shard/f'calls/{a}.{suffix}.json').exists()]
    value=signed({'context':dict(job),'parent':parent,'prediction':data['decision'],'decision_source':'llm_structured',
        'fallback_reason':'','decision':data,'request_ids':ids,'failed_request_ids':[a for a in all_ids if a not in ids],
        'call_hashes':[{'path':p.relative_to(shard).as_posix(),'sha256':sha(p)} for p in files]})
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');write_json(temporary,value,True);temporary.rename(path)
    return value


def collect(m: dict, run: Path) -> list[dict]:
    """Kiểm mọi checkpoint đang có, duplicate request ID và source lineage; không gọi API."""
    units={u['unit']['id']:u for u in m['units']};records=[];ids=set()
    for job in m['jobs']:
        path=point_path(run,job)
        if not path.exists():continue
        r=verify_point(path,job,parent_for(m,units[job['unit_id']],job['variant']))
        if ids.intersection(r['request_ids']):raise ValueError('Response R4 bị copy giữa executions')
        ids.update(r['request_ids']);records.append(r)
    return records


def worker(root: Path, bank: Path, run: Path, org: int) -> None:
    """Một process/shard, mượn mọi key còn quota cho cùng text model; không cap nội bộ."""
    from dotenv import load_dotenv
    from agents.decision_agent import TradeDecisionOutput
    from core.revision72_provider import RoutedLLM, seed_provider_state
    from core.revision72_quota import PoolArchive, PoolLedger
    m=verify_bank(root,bank);shard=run/f'shards/org{org}';shard.mkdir(parents=True,exist_ok=True)
    with StudyLock(shard/'worker.lock'):
        units={u['unit']['id']:u for u in m['units']}
        for job in m['jobs']:
            path=point_path(run,job);temporary=path.with_suffix('.tmp')
            if job['org']==org and temporary.exists() and not path.exists():
                verify_point(temporary,job,parent_for(m,units[job['unit_id']],job['variant']));temporary.rename(path)
        all_records=collect(m,run);done={(r['context']['unit_id'],r['context']['variant'],r['context']['repeat']) for r in all_records}
        jobs=[j for j in m['jobs'] if j['org']==org and (j['unit_id'],j['variant'],j['repeat']) not in done]
        if not jobs:print(f'Org {org}: đã đủ, không gọi API.');return
        load_dotenv(root/'.env',override=True)
        keys=[os.getenv(f'GROQ_ORG_{i}_API_KEY','') for i in range(1,6)]
        if not all(keys) or len(set(keys))!=5:raise ValueError('Cần đủ năm key riêng trong .env; không gửi key qua chat')
        ledger=PoolLedger(run/'quota.sqlite3',m['sha256']);seed_provider_state(run,ledger)
        archive=PoolArchive(shard,m['sha256'],keys[org-1],ledger,org,0)
        delegate=RoutedLLM(archive,keys,org,{'model':m['model'],'temperature':m['temperature'],'max_tokens':m['max_tokens'],
            'max_retries':0,'timeout':120,'reasoning_format':'hidden','metadata':{'langgraph_node':'Decision Maker'}},m['sha256'])
        llm=CachedLLM(delegate,archive).with_structured_output(TradeDecisionOutput,method='json_schema',include_raw=True)
        units={u['unit']['id']:u for u in m['units']}
        for job in jobs:
            u=units[job['unit_id']]
            perform_call(llm,archive,job,u['prompts'][job['variant']],parent_for(m,u,job['variant']),point_path(run,job))
            print(f"R4 org {org}: {job['unit_id']} {job['variant']}/{job['repeat']} đã checkpoint.",flush=True)
