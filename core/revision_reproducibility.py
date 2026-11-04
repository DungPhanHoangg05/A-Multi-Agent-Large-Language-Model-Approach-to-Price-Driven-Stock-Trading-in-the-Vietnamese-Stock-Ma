"""Đóng gói bằng chứng cục bộ; verify/extract chỉ dùng thư viện chuẩn."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import io
import json
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
from typing import Any, Iterator
from unittest.mock import patch
import zipfile

OUTPUT = Path('outputs/revision/reproducibility_v1')
PARENTS = ('revision_minimal_final_v1', 'sentiment_contract_v1', 'numeric_controls_v1',
           'execution_evidence_v1', 'execution_final_v1', 'final_contracts_v1')
MODEL = '5CD-AI/Vietnamese-Sentiment-visobert'
SECRET = re.compile(rb'gsk_[A-Za-z0-9]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{32,}|hf_[A-Za-z0-9]{24,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
RUNTIME_ROOTS = ('numpy','pandas','scipy','scikit-learn','TA-Lib','jsonschema','langchain',
                 'langchain-core','langchain-groq','langgraph','groq','pydantic','python-dotenv',
                 'matplotlib','mplfinance','Pillow','requests','vnstock','beautifulsoup4','Flask')
SCORER_ROOTS = ('torch','transformers','tokenizers','sentencepiece')


def require(condition: bool, message: str) -> None:
    """Dừng trước khi ghi nếu thiếu chứng cứ, không nới hash guard."""
    if not condition:
        raise ValueError(message)


def encoded(value: Any) -> bytes:
    """JSON xác định, từ chối NaN/Infinity và giữ LF trên Windows."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf-8')


def digest(data: bytes) -> str:
    """SHA-256 nguyên byte."""
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    """Đọc streaming để không giữ weights lớn trong RAM."""
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def read(path: Path) -> Any:
    """Đọc JSON cục bộ với số hữu hạn."""
    def reject(value: str) -> None:
        raise ValueError('JSON không hữu hạn')
    return json.loads(path.read_bytes(), parse_constant=reject)


@contextmanager
def offline_guard() -> Iterator[None]:
    """Chặn network kể cả DNS; không import SDK, model hoặc key loader."""
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('T22 chỉ đọc cục bộ')), \
         patch.object(socket, 'create_connection', side_effect=AssertionError('T22 không network')), \
         patch.object(socket, 'getaddrinfo', side_effect=AssertionError('T22 không DNS')):
        yield


def safe_name(name: str) -> str:
    """Từ chối path traversal, drive/ADS Windows và tên ZIP không portable."""
    require(isinstance(name,str) and bool(name) and '\\' not in name and ':' not in name and '\x00' not in name,
            'Đường dẫn archive không hợp lệ')
    path=PurePosixPath(name)
    require(not path.is_absolute() and path.as_posix()==name and all(p not in ('..','.') and not p.endswith((' ','.')) for p in path.parts),
            'Archive path vượt phạm vi')
    require(all(p.split('.')[0].upper() not in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]} for p in path.parts),
            'Archive dùng tên reserved Windows')
    return name


def local_path(root: Path, name: str) -> Path:
    """Đảm bảo nguồn ở trong root, không theo symlink ra ngoài."""
    name=safe_name(name)
    path=root/name
    require(not path.is_symlink() and path.resolve().is_relative_to(root.resolve()), 'Nguồn vượt root')
    require(not any(p.lower() in {'.git','.env','.venv','__pycache__','provider_locks'} for p in PurePosixPath(name).parts),
            'Từ chối private/runtime path')
    require(path.suffix.lower() not in {'.sqlite3','.pem','.key','.lock','.pyc'} and not path.name.startswith('.env'),
            'Từ chối secret/operational artifact')
    return path


def scan_bytes(data: bytes, name: str, depth: int = 0) -> int:
    """Dừng khi có mẫu credential; kiểm cả members ZIP, không in giá trị."""
    require(SECRET.search(data) is None, 'Có mẫu credential trong artifact: '+name)
    if name.lower().endswith('.json'):
        try:
            value=json.loads(data)
        except (ValueError,UnicodeError):
            value=None
        pending=[value]
        while pending:
            item=pending.pop()
            if isinstance(item,dict):
                for key, value in item.items():
                    field=str(key).lower()
                    if field in {'api_key','apikey','access_token','groq_api_key','hf_token'} or (
                            field=='authorization' and isinstance(value,str) and (
                                re.match(r'(?i)^(bearer|basic)\s+',value) or not re.search(r'\s',value))):
                        require(not isinstance(value,str) or len(value)<16 or value in ('[REDACTED]','[WITHHELD]'),
                                'Có trường credential trong artifact: '+name)
                    pending.append(value)
            elif isinstance(item,list):
                pending.extend(item)
    count=1
    if name.lower().endswith('.zip'):
        require(depth<3, 'Archive lồng quá sâu')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            seen=set()
            require(sum(i.file_size for i in archive.infolist())<=512_000_000, 'ZIP vượt giới hạn scan')
            for info in archive.infolist():
                safe_name(info.filename.rstrip('/'))
                require(info.filename.casefold() not in seen, 'ZIP member trùng')
                seen.add(info.filename.casefold())
                require(not stat.S_ISLNK(info.external_attr>>16), 'ZIP có symlink')
                if not info.is_dir():
                    count+=scan_bytes(archive.read(info),name+'!'+info.filename,depth+1)
    return count


def check_self_digest(value: dict) -> str | None:
    """Nhận hai cách serialization đã dùng ở các receipts, không sửa receipt."""
    if 'sha256' not in value:
        return None
    content={k:v for k,v in value.items() if k!='sha256'}
    compact=json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(',',':'),allow_nan=False).encode('utf-8')
    if digest(compact)==value['sha256']:
        return 'compact_sorted_utf8'
    require(digest(encoded(content))==value['sha256'], 'Self-digest receipt không khớp')
    return 'pretty_sorted_utf8_lf'


def collect_sources(root: Path, parents: tuple[str,...] = PARENTS) -> tuple[dict[str,bytes],list[dict]]:
    """Khóa hợp closure của sáu releases; không tự glob cache/credentials."""
    blobs: dict[str,bytes]={}
    receipts=[]
    def capture(name: str, expected: str | None = None) -> None:
        path=local_path(root,name)
        require(path.is_file(),'Thiếu source: '+name)
        if name not in blobs:
            blobs[name]=path.read_bytes()
        require(expected is None or digest(blobs[name])==expected, 'Source/output khác receipt: '+name)
    for parent in parents:
        base=Path('outputs/revision')/parent
        manifest=(base/'manifest.json').as_posix()
        capture(manifest)
        value=json.loads(blobs[manifest]); fmt=check_self_digest(value)
        for group, prefix in (('sources',Path()),('outputs',base)):
            for row in value[group]:
                capture((prefix/row['path']).as_posix(),row['sha256'])
        receipts.append({'release':parent,'manifest':manifest,'sha256':digest(blobs[manifest]),
                         'sources':len(value['sources']),'outputs':len(value['outputs']),'self_digest_format':fmt})
    return blobs,receipts


def runtime_snapshot(roots: tuple[str,...]) -> dict:
    """Khóa dependencies đang cài và transitive closure theo markers của máy build."""
    from packaging.requirements import Requirement
    pending=list(roots); result={}; edges=[]
    while pending:
        name=pending.pop(); dist=metadata.distribution(name); key=re.sub(r'[-_.]+','-',dist.metadata['Name']).lower()
        if key in result:
            continue
        result[key]=dist.version
        for text in dist.requires or []:
            requirement=Requirement(text)
            if requirement.marker and not requirement.marker.evaluate({'extra':''}):
                continue
            child=metadata.distribution(requirement.name)
            require(not requirement.specifier or requirement.specifier.contains(child.version,prereleases=True),
                    'Dependency đang cài không thỏa declared requirement: '+key)
            pending.append(requirement.name)
            edges.append({'parent':key,'requirement':str(requirement),'installed_version':child.version})
    return {'python':platform.python_version(),'platform':platform.platform(),'roots':list(roots),
            'distributions':dict(sorted(result.items())),'dependency_edges':edges,
            'scope':'Quan sát lúc đóng gói trên Windows, không suy execution versions từ môi trường hiện tại; không wheelhouse/interpreter bundle.'}


def zip_entries(path: Path, files: dict[str,bytes]) -> None:
    """ZIP xác định tên/thời gian/mode; ghi exclusive, không đổi byte member."""
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(safe_name(name),(1980,1,1,0,0,0))
            info.create_system=3; info.external_attr=0o100644<<16; info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,data,compresslevel=6)


def inspect_archive(path: Path, entries: list[dict], scan: bool = True) -> int:
    """Kiểm exact member set, bytes và credential patterns trước extract."""
    expected={row['path']:row for row in entries}
    require(len(expected)==len(entries),'Index có member trùng')
    require(len({name.casefold() for name in expected})==len(expected),'Index trùng tên Windows')
    count=0
    with zipfile.ZipFile(path) as archive:
        names=[i.filename for i in archive.infolist()]
        require(len(names)==len(set(names)) and set(names)==set(expected),'Archive có member thừa/thiếu/trùng')
        require(sum(i.file_size for i in archive.infolist())<=1_000_000_000,'Archive vượt giới hạn kiểm')
        for info in archive.infolist():
            safe_name(info.filename)
            require(not stat.S_ISLNK(info.external_attr>>16),'Archive symlink không được phép')
            row=expected[info.filename]
            require(info.file_size==row['size_bytes'],'Archive member khác size')
            if scan:
                data=archive.read(info)
                require(digest(data)==row['sha256'],'Archive member khác hash: '+info.filename)
                count+=scan_bytes(data,info.filename)
            else:
                with archive.open(info) as handle:
                    require(hashlib.file_digest(handle,'sha256').hexdigest()==row['sha256'],'Archive member khác hash')
                count+=1
    return count


def build_release(root: Path, output: Path, snapshot: Path) -> dict:
    """Tạo gói nội bộ từ artifacts có sẵn, không model forward/API/publish."""
    root=root.resolve(); output=(root/output).resolve() if not output.is_absolute() else output.resolve()
    require(output.parent==root/'outputs/revision' and not output.exists(),'Cần release mới trực tiếp dưới outputs/revision')
    with offline_guard():
        blobs,parents=collect_sources(root)
        tracked=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode('utf-8').split('\x00')
        code=[p for p in tracked if p and (p.endswith('.py') and p.split('/')[0] in {'agents','core','data_manager','utils','scripts','tests'}
              or p.startswith('revision/') and Path(p).suffix in {'.json','.txt'})]
        code+=['core/revision_reproducibility.py','scripts/package_revision_reproducibility.py','tests/test_revision_reproducibility.py',
               'revision/reproducibility_runbook.md','.python-version','requirements.txt','revision/requirements-r1.txt',
               'THIRD_PARTY_NOTICES.md','LICENSES/QuantAgent-MIT.txt',
               'outputs/revision/chart_r1_run_v1/runtime_history/frozen_runtime_sources.zip',
               'outputs/revision/chart_r1_run_v1/runtime_history/frozen_runtime_sources.json',
               'outputs/revision/r1_72h_bank_v2/model_card.md','outputs/revision/r1_72h_bank_v2/local_scores.json',
               'outputs/revision/r1_72h_bank_v2/article_audit.json','outputs/revision/r1_72h_bank_v2/news.json',
               'outputs/revision/r1_prices_v1/manifest.json']
        for name in sorted(set(code)):
            blobs.setdefault(name,local_path(root,name).read_bytes())
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
        scorer_receipt=read(root/'outputs/revision/sentiment_contract_v1/manifest.json')
        revision=scorer_receipt['local_snapshot_revision']; modelrows=[]
        for row in scorer_receipt['external_snapshot_files']:
            name=safe_name(row['name']); path=snapshot/name
            require(path.is_file() and file_hash(path)==row['sha256'],'Model/tokenizer local thiếu hoặc sai hash: '+name)
            member=f'assets/sentiment/{revision}/{name}'
            modelrows.append({'path':member,'sha256':row['sha256'],'size_bytes':path.stat().st_size})
            if name!='model.safetensors':
                blobs[member]=path.read_bytes()
        require({Path(r['path']).name for r in modelrows}=={'config.json','model.safetensors','sentencepiece.bpe.model','special_tokens_map.json','tokenizer.json','tokenizer_config.json'},'Receipt model thiếu/thừa files')
        replay=runtime_snapshot(RUNTIME_ROOTS); scorer=runtime_snapshot(SCORER_ROOTS)
        model={'model_id':MODEL,'revision':revision,'files':modelrows,'recipe':read(root/'outputs/revision/sentiment_contract_v1/summary.json')['recipe'],
               'hosted_models':{'text':'openai/gpt-oss-20b','vision':'qwen/qwen3.8-27b','immutable_served_revision':None,'seed_observed':None},
               'scope':'Local snapshot khớp T07; weights sidecar riêng. Hosted alias không là immutable weights; không gọi model API hoặc forward.'}
        rights={'distribution':'local_private_draft_only','public_release_authorized':False,'pid':None,
                'components':[
                    {'component':'QuantAgent-derived source','status':'MIT_notice_included','evidence':'LICENSES/QuantAgent-MIT.txt'},
                    {'component':'author additions','status':'unknown_repository_wide_license_and_author_permission'},
                    {'component':'vnstock/VCI OHLCV','status':'redistribution_permission_unverified'},
                    {'component':'CafeF cached excerpts','status':'redistribution_permission_and_original_PIT_unverified'},
                    {'component':'5CD-AI/ViSoBERT assets','status':'redistribution_permission_unverified_model_card_preserved'},
                    {'component':'hosted LLM raw outputs','status':'sharing_terms_and_author_approval_pending'}],
                'scope':'Bản đóng gói nội bộ, không upload/publish/PID. Không áp MIT của upstream cho dữ liệu/model hoặc mọi phần bổ sung. T34 cần quyền chia sẻ và PID thật.'}
        attempts=read(root/'outputs/revision/revision_minimal_final_v1/attempts.json')
        records=read(root/'outputs/revision/revision_minimal_final_v1/records.json')
        summary=read(root/'outputs/revision/revision_minimal_final_v1/summary.json')
        embedded=[]
        for name,data in sorted(blobs.items()):
            if not name.endswith('.request.json'):
                continue
            request=json.loads(data)
            def images(value: Any) -> Iterator[str]:
                if isinstance(value,str) and value.startswith('data:image/'):
                    yield value
                elif isinstance(value,dict):
                    for child in value.values(): yield from images(child)
                elif isinstance(value,list):
                    for child in value: yield from images(child)
            import base64
            for uri in images(request.get('messages',[])):
                header,body=uri.split(',',1)
                require(';base64' in header,'Image URI không phải base64')
                image=base64.b64decode(body,validate=True); h=digest(image)
                member=f'assets/charts/{h}.png'
                require(image.startswith(b'\x89PNG\r\n\x1a\n'),'Ảnh không phải PNG')
                blobs.setdefault(member,image)
                embedded.append({'request_path':name,'image_path':member,'sha256':h})
        coverage={'research_executions':len(records),'main_units':summary['main_units'],
                  'raw_attempts':len(attempts),'raw_request_files_in_closure':sum(p.endswith('.request.json') for p in blobs),
                  'embedded_image_occurrences':len(embedded),'distinct_chart_pngs':len({r['sha256'] for r in embedded}),
                  'charts':embedded,'parents':parents,'source_commit_before_packaging':commit,
                  'provenance_limits':['OHLCV là retrieval 01/11/2026, không snapshot submission authenticated.',
                      'News date/content PIT và financial-domain validation chưa xác thực.',
                      'Native row-wise causal gate T10 FAIL; numerical T13 không xác nhận ngược native inputs.',
                      '40 paired groups có order khác kế hoạch, chín cross-epoch groups; không gộp thành immutable model revision.',
                      'Byte-identical offline replay không chứng minh inference mới, future validity hoặc profitability.'],
                  'excluded':['.env/credentials/Hub token','SQLite quota và locks/live scheduler state','work caches không được receipt khóa',
                              'paper/PDF builds và user DOCX','wheelhouse/interpreter/hosted model weights'],
                  't23_status':'pending_clean_environment_replay'}
        generated={'runtime.json':{'observed_at_utc':datetime.now(timezone.utc).isoformat(),
                    'replay':replay,'scorer':scorer,'frozen_T04_runtime':read(root/'outputs/revision/revision_minimal_final_v1/manifest.json')['runtime'],
                    'frozen_T07_runtime':read(root/'outputs/revision/sentiment_contract_v1/summary.json')['runtime']},
                   'model.json':model,'rights.json':rights,'coverage.json':coverage}
        files={name:encoded(value) for name,value in generated.items()}
        for label,env in [('replay',replay),('scorer',scorer)]:
            files[f'requirements-{label}.txt']=(''.join(f'{n}=={v}\n' for n,v in env['distributions'].items())).encode('utf-8')
        for name,data in files.items(): blobs['reproducibility/'+name]=data
        scans=sum(scan_bytes(data,name) for name,data in blobs.items())
        require(len({n.casefold() for n in blobs})==len(blobs),'Paths trùng case trên Windows')
        index=[{'path':n,'sha256':digest(b),'size_bytes':len(b)} for n,b in sorted(blobs.items())]
        # Kiểm lại nguồn trước xuất; dữ liệu phái sinh trong assets/reproducibility không ghi đè nguồn.
        for row in index:
            if row['path'].startswith(('assets/','reproducibility/')): continue
            require(file_hash(local_path(root,row['path']))==row['sha256'],'Nguồn thay đổi lúc đóng gói')
        output.mkdir()
        zip_entries(output/'bundle.zip',blobs)
        weightrow=next(r for r in modelrows if r['path'].endswith('/model.safetensors'))
        with zipfile.ZipFile(output/'model_weights.zip','x',compression=zipfile.ZIP_STORED) as archive:
            info=zipfile.ZipInfo(weightrow['path'],(1980,1,1,0,0,0)); info.create_system=3;info.external_attr=0o100644<<16
            with archive.open(info,'w',force_zip64=True) as handle, (snapshot/'model.safetensors').open('rb') as source:
                shutil.copyfileobj(source,handle)
        for name,data in files.items(): (output/name).write_bytes(data)
        qa={'status':'PASS','parent_checks':parents,'secret_pattern_findings':0,'scanned_files_including_nested_zip':scans,
            'archive_member_count':len(index),'source_and_output_bytes_preserved':True,'api_calls':0,'model_forwards':0,
            'tests':'Xem plan.md; T23 replay sạch chưa chạy ở T22.',
            'limitations':'Scan patterns/secret fields không thay duyệt quyền chia sẻ. Không có wheelhouse hoặc PID; đây là local private draft.'}
        (output/'qa.json').write_bytes(encoded(qa))
        metadata_files=[{'path':p.name,'sha256':file_hash(p),'size_bytes':p.stat().st_size} for p in sorted(output.iterdir()) if p.suffix!='.zip']
        manifest={'schema_version':'revision_reproducibility_v1','distribution':'local_private_draft_only',
                  'archives':[{'path':'bundle.zip','sha256':file_hash(output/'bundle.zip'),'size_bytes':(output/'bundle.zip').stat().st_size,'entries':index,'required_for':'offline_metrics_replay'},
                              {'path':'model_weights.zip','sha256':file_hash(output/'model_weights.zip'),'size_bytes':(output/'model_weights.zip').stat().st_size,'entries':[weightrow],'required_for':'scorer_asset_reconstruction_only','tracked_in_git':False}],
                  'metadata_files':metadata_files,'parents':parents}
        manifest['sha256']=digest(encoded(manifest)); (output/'manifest.json').write_bytes(encoded(manifest))
        check_release(output,with_weights=True)
        return {'files':len(index),'bundle_bytes':(output/'bundle.zip').stat().st_size,'charts':coverage['distinct_chart_pngs'],
                'model_bytes':weightrow['size_bytes'],'parents':len(parents)}


def check_release(folder: Path, with_weights: bool = False) -> dict:
    """Kiểm gói độc lập repo/Hub/runtime khoa học; thiếu weights chỉ hợp lệ cho replay."""
    with offline_guard():
        manifest=read(folder/'manifest.json'); require(check_self_digest(manifest)=='pretty_sorted_utf8_lf','Sai self-digest T22')
        names=[r['path'] for r in manifest['metadata_files']]+[r['path'] for r in manifest['archives']]
        require(len(names)==len(set(names)) and 'manifest.json' not in names,'Gói có tên trùng')
        members=[safe_name(e['path']).casefold() for r in manifest['archives'] for e in r['entries']]
        require(len(members)==len(set(members)),'Các archives đè cùng member')
        expected={'manifest.json',*[r['path'] for r in manifest['metadata_files']],*[r['path'] for r in manifest['archives']]}
        actual={p.name for p in folder.iterdir()}
        require(actual==expected or not with_weights and actual==expected-{'model_weights.zip'},'Gói có file thừa/thiếu')
        for row in manifest['metadata_files']:
            path=local_path(folder,row['path'])
            require(path.stat().st_size==row['size_bytes'] and file_hash(path)==row['sha256'],'Metadata khác hash')
        checked=0
        for row in manifest['archives']:
            safe_name(row['path']); path=folder/row['path']
            if row['path']=='model_weights.zip' and not with_weights:
                continue
            require(path.is_file() and path.stat().st_size==row['size_bytes'] and file_hash(path)==row['sha256'],'Archive thiếu/khác hash')
            checked+=inspect_archive(path,row['entries'],scan=row['path']=='bundle.zip')
        return {'status':'PASS','scanned_members_including_nested_zip':checked,'model_weights_verified':with_weights,
                'scope':'Kiểm bytes/archive, không inference hoặc nghiệm thu T23.'}


def extract_release(folder: Path, destination: Path, with_weights: bool = False) -> dict:
    """Verify trước, giải nén vào thư mục mới; không ghi đè repo/nguồn/model cache."""
    folder=folder.resolve(); destination=destination.resolve()
    require(not destination.exists() and not folder.is_relative_to(destination) and not destination.is_relative_to(folder),
            'Đích extract phải mới và tách khỏi gói')
    result=check_release(folder,with_weights)
    destination.mkdir(parents=True)
    manifest=read(folder/'manifest.json')
    for row in manifest['archives']:
        if row['path']=='model_weights.zip' and not with_weights: continue
        with zipfile.ZipFile(folder/row['path']) as archive:
            for item in row['entries']:
                target=destination/safe_name(item['path'])
                require(not target.exists() and target.resolve().is_relative_to(destination),'Extract đè file hoặc vượt đích')
                target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('xb') as handle, archive.open(item['path']) as source:
                    shutil.copyfileobj(source,handle)
    return result
