"""Dựng venv và replay T23 offline bằng package và runtime image có hash."""

from __future__ import annotations

import base64
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile

from core.revision_reproducibility import (check_self_digest, digest, encoded, extract_release,
    file_hash, inspect_archive, local_path, read, require, safe_name, zip_entries)

OUTPUT=Path('outputs/revision/clean_replay_v1')
PACKAGE=Path('outputs/revision/reproducibility_v1')


def make_numpy_image(output: Path) -> dict:
    """Snapshot distribution local, kiểm RECORD; không gọi pip hoặc tải wheel."""
    dist=metadata.distribution('numpy'); require(dist.version=='2.1.2','NumPy phải đúng pin T04 2.1.2')
    files={}; records=[]; excluded=[]
    for item in dist.files or []:
        name=str(item).replace('\\','/'); top=name.split('/')[0]
        if top not in ('numpy','numpy.libs','numpy-2.1.2.dist-info') or '__pycache__' in name or name.endswith('.pyc'):
            excluded.append(name); continue
        safe_name(name); path=Path(dist.locate_file(item)); data=path.read_bytes()
        if item.hash:
            require(item.hash.mode=='sha256','RECORD hash algorithm ngoài scope')
            require(base64.urlsafe_b64encode(bytes.fromhex(digest(data))).decode().rstrip('=')==item.hash.value,'NumPy source khác RECORD: '+name)
        files[name]=data; records.append({'path':name,'sha256':digest(data),'size_bytes':len(data),'record_hash_checked':bool(item.hash)})
    require('numpy/__init__.py' in files and any(n.endswith('.pyd') for n in files),'Image NumPy thiếu extension')
    zip_entries(output,files)
    return {'schema_version':'numpy_installed_image_v1','distribution':'numpy','version':dist.version,
            'python':sys.version.split()[0],'platform':sys.platform,'files':records,'excluded_record_paths':excluded,
            'archive_sha256':file_hash(output),'archive_size_bytes':output.stat().st_size,
            'provenance':'Snapshot distribution đã cài và kiểm RECORD, không original wheel hoặc installation từ package index.',
            'scope':'Runtime clone riêng trong venv mới; không system-site-packages. Không gồm pycache, Scripts hoặc wheel stub.'}


def install_numpy_image(image: Path, index: dict, environment: Path) -> None:
    """Copy exact image vào venv trống; không dùng pip resolver/network."""
    require(file_hash(image)==index['archive_sha256'],'Runtime image khác hash')
    require(index['version']=='2.1.2' and index['python']==sys.version.split()[0] and index['platform']==sys.platform,'Runtime image khác platform/Python')
    require(all(safe_name(r['path']).split('/')[0] in ('numpy','numpy.libs','numpy-2.1.2.dist-info') for r in index['files']),'Runtime image chứa module ngoài scope')
    inspect_archive(image,index['files'],scan=False)
    site=environment/'Lib/site-packages' if os.name=='nt' else environment/f'lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages'
    require(site.is_dir() and not list(site.iterdir()),'Site-packages cần trống trước cài image')
    with zipfile.ZipFile(image) as archive:
        for row in index['files']:
            target=site/safe_name(row['path']); require(target.resolve().is_relative_to(site.resolve()),'Runtime image vượt site-packages')
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as handle: handle.write(archive.read(row['path']))
    for row in index['files']: require(file_hash(site/row['path'])==row['sha256'],'Runtime copy khác bytes')


def clean_environment(work: Path) -> dict[str,str]:
    """Chỉ chuyển các biến Windows bắt buộc, không chuyển secrets/proxy/PYTHONPATH."""
    result={k:os.environ[k] for k in ('SYSTEMROOT','WINDIR','COMSPEC') if k in os.environ}
    home=work/'empty_home'; temporary=work/'temp'; home.mkdir(); temporary.mkdir()
    result.update({'USERPROFILE':str(home),'HOME':str(home),'HF_HOME':str(home/'hf'),
                   'TEMP':str(temporary),'TMP':str(temporary),'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
    return result


def check_release(root: Path, output: Path) -> dict:
    """Kiểm nguồn/output/runtime image; không chạy lại metrics hoặc network."""
    output=output if output.is_absolute() else root/output; manifest=read(output/'manifest.json')
    require(check_self_digest(manifest)=='pretty_sorted_utf8_lf','Self-digest T23 sai')
    for group,base in (('sources',root),('outputs',output)):
        for row in manifest[group]: require(file_hash(local_path(base,row['path']))==row['sha256'],'T23 source/output khác hash: '+row['path'])
    require({p.name for p in output.iterdir()}=={'manifest.json',*[r['path'] for r in manifest['outputs']]},'T23 file thừa/thiếu')
    index=read(output/'numpy_runtime.json'); inspect_archive(output/'numpy_runtime.zip',index['files'],scan=False)
    return {'status':'PASS','hashes':len(manifest['sources'])+len(manifest['outputs']),'runtime_image_files':len(index['files'])}


def build_release(root: Path, output: Path, package: Path, runtime_release: Path | None = None) -> dict:
    """Tạo release sau khi child sạch PASS và frozen package không đổi byte."""
    root=root.resolve(); output=(root/output).resolve() if not output.is_absolute() else output.resolve()
    package=(root/package).resolve() if not package.is_absolute() else package.resolve()
    require(output.parent==root/'outputs/revision' and not output.exists(),'Cần output release mới, không overwrite')
    require(sys.version.split()[0]=='3.13.5','T23 khóa Python 3.13.5')
    source_names=['core/revision_clean_replay.py','core/revision_clean_metrics.py','scripts/run_revision_clean_replay.py',
                  'tests/test_revision_clean_replay.py','revision/clean_replay_runbook.md','core/revision_reproducibility.py']
    source_names +=[(package/name).relative_to(root).as_posix() for name in ('bundle.zip','manifest.json')]
    source_rows=[{'path':p,'sha256':file_hash(root/p)} for p in source_names]
    work=Path(tempfile.mkdtemp(prefix='revision_clean_')).resolve()
    try:
        package_root=work/'package'; extract_release(package,package_root)
        environment=work/'venv'; venv.EnvBuilder(with_pip=False,system_site_packages=False).create(environment)
        image=work/'numpy_runtime.zip'
        if runtime_release is None:
            index=make_numpy_image(image)
        else:
            runtime_release=(root/runtime_release).resolve() if not runtime_release.is_absolute() else runtime_release.resolve()
            check_release(root,runtime_release); index=read(runtime_release/'numpy_runtime.json'); shutil.copyfile(runtime_release/'numpy_runtime.zip',image)
            source_rows.extend({'path':(runtime_release/n).relative_to(root).as_posix(),'sha256':file_hash(runtime_release/n)} for n in ('manifest.json','numpy_runtime.json','numpy_runtime.zip'))
        install_numpy_image(image,index,environment)
        runner=work/'metrics_worker.py'; shutil.copyfile(root/'core/revision_clean_metrics.py',runner)
        child_output=work/'result'; child_output.mkdir(); env=clean_environment(work)
        python=environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        result=subprocess.run([str(python),'-I','-X','utf8',str(runner),str(package_root),str(child_output)],cwd=package_root,
                              env=env,capture_output=True,text=True,encoding='utf-8',timeout=600,check=False)
        require(result.returncode==0,'Worker sạch FAIL:\n'+result.stderr[-4000:])
        require(not result.stderr,'Worker có stderr chưa được giải thích')
        qa=read(child_output/'metrics_qa.json'); require(qa['status']=='PASS','Metrics replay chưa PASS')
        package_manifest=read(package/'manifest.json')
        for row in package_manifest['archives'][0]['entries']:
            require(file_hash(package_root/row['path'])==row['sha256'],'Worker đã đổi frozen package')
        for row in source_rows: require(file_hash(root/row['path'])==row['sha256'],'Nguồn thay đổi trong replay')
        output.mkdir()
        for path in child_output.iterdir(): shutil.copyfile(path,output/path.name)
        shutil.copyfile(image,output/'numpy_runtime.zip'); (output/'numpy_runtime.json').write_bytes(encoded(index))
        (output/'worker.log').write_bytes(result.stdout.encode('utf-8'))
        isolation={'python_version':sys.version.split()[0],'python_executable_sha256':file_hash(Path(sys.executable)),
                   'system_site_packages':False,'venv_created_without_pip':True,'worker_flag':'-I',
                   'environment_variable_names':sorted(env),'runtime_image_provenance':index['provenance'],
                   'extracted_package_members_unchanged':len(package_manifest['archives'][0]['entries']),
                   'original_workspace_or_hub_reads_by_worker':0,'unexpected_network_or_process_attempts':0,
                   'scope':'Fresh filesystem/venv, archived NumPy clone; interpreter và stdlib Python cài sẵn dùng chung. Không nguyên bản wheelhouse hoặc portability ngoài Windows/Python pin.'}
        (output/'isolation.json').write_bytes(encoded(isolation))
        manifest={'schema_version':'clean_offline_replay_v1','sources':source_rows,
                  'outputs':[{'path':p.name,'sha256':file_hash(p)} for p in sorted(output.iterdir())]}
        manifest['sha256']=digest(encoded(manifest)); (output/'manifest.json').write_bytes(encoded(manifest))
        check_release(root,output)
        return qa
    finally:
        # Chỉ xóa đúng thư mục tạm do lần gọi này tạo, sau khi kiểm absolute target.
        require(work.parent==Path(tempfile.gettempdir()).resolve() and work.name.startswith('revision_clean_'),'Không được dọn ngoài temp root')
        shutil.rmtree(work)
