"""Kiểm gói offline: nguyên byte, fail-closed, secret và extraction portable."""

from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from core.revision_reproducibility import (build_release, check_release, check_self_digest,
    collect_sources, digest, encoded, extract_release, file_hash, inspect_archive,
    local_path, offline_guard, safe_name, scan_bytes, zip_entries)


def seal(folder: Path, files: dict[str,bytes], weights: bool = False) -> dict:
    """Gói fixture không model/keys, dùng index độc lập để kiểm hợp đồng."""
    folder.mkdir()
    zip_entries(folder/'bundle.zip',files)
    archives=[{'path':'bundle.zip','sha256':file_hash(folder/'bundle.zip'),'size_bytes':(folder/'bundle.zip').stat().st_size,
               'entries':[{'path':n,'sha256':digest(b),'size_bytes':len(b)} for n,b in files.items()]}]
    if weights:
        zip_entries(folder/'model_weights.zip',{'assets/model.safetensors':b'SYNTHETIC_ONLY'})
        archives.append({'path':'model_weights.zip','sha256':file_hash(folder/'model_weights.zip'),
                         'size_bytes':(folder/'model_weights.zip').stat().st_size,
                         'entries':[{'path':'assets/model.safetensors','sha256':digest(b'SYNTHETIC_ONLY'),'size_bytes':14}]})
    manifest={'schema_version':'revision_reproducibility_v1','archives':archives,'metadata_files':[]}
    manifest['sha256']=digest(encoded(manifest)); (folder/'manifest.json').write_bytes(encoded(manifest))
    return manifest


class ReproducibilityTests(unittest.TestCase):
    """Không import frozen runner, không cần SDK/model hoặc dữ liệu thật."""

    def test_roundtrip_keeps_crlf_binary_and_runs_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); original={'core/a.py':b'x=1\r\n','data/file.bin':bytes(range(256)), 'news.json':encoded({'text':'Tiếng Việt'})}
            seal(root/'package',original)
            with offline_guard():
                self.assertEqual(check_release(root/'package')['status'],'PASS')
                extract_release(root/'package',root/'clean')
                with self.assertRaises(AssertionError): socket.getaddrinfo('example.invalid',443)
            for name,data in original.items(): self.assertEqual((root/'clean'/name).read_bytes(),data)
            with self.assertRaises(ValueError): extract_release(root/'package',root/'clean')
            with self.assertRaises(ValueError): extract_release(root/'package',root/'package'/'child')

    def test_self_output_and_extra_file_tamper_fail(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); folder=root/'p'; original=seal(folder,{'x.txt':b'original'})
            (folder/'extra.txt').write_bytes(b'extra')
            with self.assertRaises(ValueError): check_release(folder)
            (folder/'extra.txt').unlink()
            data=(folder/'bundle.zip').read_bytes(); (folder/'bundle.zip').write_bytes(data+b'tamper')
            with self.assertRaises(ValueError): check_release(folder)
            (folder/'bundle.zip').write_bytes(data)
            modified=deepcopy(original); modified['schema_version']='tampered'
            (folder/'manifest.json').write_bytes(encoded(modified))
            with self.assertRaises(ValueError): check_release(folder)

    def test_exact_member_set_and_member_hash_fail(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'a.zip'; zip_entries(p,{'a.txt':b'a','b.txt':b'b'})
            expected=[{'path':'a.txt','sha256':digest(b'a'),'size_bytes':1}]
            with self.assertRaises(ValueError): inspect_archive(p,expected)
            expected.append({'path':'b.txt','sha256':digest(b'c'),'size_bytes':1})
            with self.assertRaises(ValueError): inspect_archive(p,expected)

    def test_zip_traversal_windows_aliases_duplicate_and_symlink_fail(self) -> None:
        for name in ('../x','/x','C:/x','a\\x','a//x','a/../x','a/x.','NUL.txt','a/CON','./x'):
            with self.subTest(name=name), self.assertRaises(ValueError): safe_name(name)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'a.zip'
            with zipfile.ZipFile(p,'w') as archive:
                info=zipfile.ZipInfo('safe.txt'); info.create_system=3; info.external_attr=0o120777<<16
                archive.writestr(info,b'target')
            with self.assertRaises(ValueError): inspect_archive(p,[{'path':'safe.txt','sha256':digest(b'target'),'size_bytes':6}])
            p.unlink(); zip_entries(p,{'a.txt':b'a','A.txt':b'A'})
            with self.assertRaises(ValueError): inspect_archive(p,[{'path':n,'sha256':digest(b),'size_bytes':1} for n,b in {'a.txt':b'a','A.txt':b'A'}.items()])

    def test_credentials_nested_zip_and_json_fields_stop_without_values(self) -> None:
        credential=b'gsk_'+b'A'*32
        for name,data in [('request.json',encoded({'Authorization':'Bearer '+('a'*32)})),('source.py',credential)]:
            with self.subTest(name=name),self.assertRaises(ValueError) as context: scan_bytes(data,name)
            self.assertNotIn(credential.decode(),str(context.exception))
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive: archive.writestr('old.py',credential)
        with self.assertRaises(ValueError): scan_bytes(stream.getvalue(),'history.zip')
        self.assertEqual(scan_bytes(b'KEY_NAME = "GROQ_API_KEY"','config.py'),1)
        self.assertEqual(scan_bytes(encoded({'execution_policy':{'authorization':'Author permits this local operation without publishing.'}}),'manifest.json'),1)

    def test_sidecar_absence_is_explicit_and_full_asset_check_requires_it(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/'p'; seal(folder,{'main.txt':b'one'},weights=True)
            self.assertTrue(check_release(folder,True)['model_weights_verified'])
            (folder/'model_weights.zip').unlink()
            self.assertFalse(check_release(folder)['model_weights_verified'])
            with self.assertRaises(ValueError): check_release(folder,True)

    def test_locked_parent_closure_rejects_changed_or_missing_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); parent=root/'outputs/revision/test'; parent.mkdir(parents=True)
            (root/'source.json').write_bytes(b'{"x":1}\r\n'); (parent/'result.csv').write_bytes(b'x\n1\n')
            receipt={'sources':[{'path':'source.json','sha256':file_hash(root/'source.json')}],
                     'outputs':[{'path':'result.csv','sha256':file_hash(parent/'result.csv')}]}
            (parent/'manifest.json').write_bytes(encoded(receipt))
            blobs,parents=collect_sources(root,('test',)); self.assertEqual(len(blobs),3)
            self.assertIsNone(parents[0]['self_digest_format'])
            (root/'source.json').write_bytes(b'{}')
            with self.assertRaises(ValueError): collect_sources(root,('test',))
            for name in ('.env','../outside','tokens.key','x/quota.sqlite3'):
                with self.subTest(name=name),self.assertRaises(ValueError): local_path(root,name)

    def test_deterministic_zip_and_two_legacy_receipt_digest_formats(self) -> None:
        data={'sources':[]}; pretty={**data,'sha256':digest(encoded(data))}
        compact={**data,'sha256':digest(json.dumps(data,sort_keys=True,separators=(',',':')).encode())}
        self.assertEqual(check_self_digest(pretty),'pretty_sorted_utf8_lf')
        self.assertEqual(check_self_digest(compact),'compact_sorted_utf8')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); files={'b.txt':b'b','a.txt':b'a'}
            zip_entries(root/'a.zip',files); zip_entries(root/'b.zip',dict(reversed(list(files.items()))))
            self.assertEqual(file_hash(root/'a.zip'),file_hash(root/'b.zip'))

    def test_build_rejects_overwrite_or_non_release_before_source_read(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); old=root/'outputs/revision/old'; old.mkdir(parents=True)
            for output in (old,root/'paper/new',root/'outputs/revision/new/deep'):
                with patch('core.revision_reproducibility.collect_sources') as collect:
                    with self.assertRaises(ValueError): build_release(root,output,root/'snapshot')
                    collect.assert_not_called()


if __name__=='__main__':
    unittest.main()
