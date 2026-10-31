"""Kiểm sửa probe/diagnostic bằng HTTP giả; không đọc credential hoặc gọi provider thật."""

from __future__ import annotations

import base64
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

from core.groq_pacing import PilotStop
from core.mt_bicl_v4_completion import DIRECTORY, DataCompletionError
from core.mt_bicl_v4_dataset import encoded
from core.mt_bicl_v4_http_diagnostics import AMENDMENT, PARENT, PARENT_SHA, POLICY, SOURCES, error_fields, verify_hotfix
from core.mt_bicl_v4_protocol import checksum, read
from scripts.continue_mt_bicl_v4_data import control_requests, controls
from test_mt_bicl_v4_collection import runtime


class HttpDiagnosticTests(unittest.TestCase):
    """Probe mới độc lập intent cũ, request nghiên cứu và ledger đã lưu giữ nguyên."""

    def test_probe_is_valid_RGB_224_png_with_separate_synthetic_ID(self) -> None:
        request = control_requests()[1]
        self.assertEqual(request['id'], 'vision_r2')
        url = request['content'][1]['image_url']['url']
        image = Image.open(io.BytesIO(base64.b64decode(url.split(',', 1)[1])))
        self.assertEqual((image.format, image.mode, image.size), ('PNG', 'RGB', (224, 224)))

    def test_400_keeps_error_details_then_resume_preserves_old_probe_and_text(self) -> None:
        with TemporaryDirectory() as folder, redirect_stdout(io.StringIO()) as log:
            root = Path(folder)
            _, _, release, pacer, transport, http, llms, _ = runtime(root)
            normal = transport.inner.inner.handler
            old_requests = control_requests()
            small = io.BytesIO()
            Image.new('RGB', (8, 8), (255, 0, 0)).save(small, format='PNG')
            old_requests[1]['id'] = 'vision'
            old_requests[1]['content'][1]['image_url']['url'] = 'data:image/png;base64,' + base64.b64encode(small.getvalue()).decode()
            requests = []

            def provider(request: httpx.Request) -> httpx.Response:
                requests.append(request.content)
                if small.getvalue() and base64.b64encode(small.getvalue()) in request.content:
                    return httpx.Response(400, json={'error': {'code': 'invalid_image', 'param': 'messages',
                        'message': 'Fixture: image height below minimum'}}, request=request)
                return normal(request)

            transport.inner.inner.handler = provider
            with patch('scripts.continue_mt_bicl_v4_data.control_requests', return_value=old_requests):
                with self.assertRaises(PilotStop):
                    controls(root, release, 'a'*64, llms, pacer)
            failed = pacer.state['requests'][-1]
            self.assertEqual(failed['status'], 400)
            evidence = read((root/DIRECTORY/'http_errors'/(failed['id']+'.json')).read_bytes())
            self.assertEqual(evidence['error']['code'], 'invalid_image')
            self.assertEqual(evidence['body_sha256'], failed['improvement_audit']['response']['body_sha256'])
            self.assertEqual(evidence['checkpoint_attempt_id'], failed['checkpoint_attempt_id'])
            self.assertIn('Fixture: image height below minimum', log.getvalue())
            old_rows = deepcopy(pacer.state['requests'])
            old_path = root/DIRECTORY/'controls'/pacer.credential_scope/'vision.json'
            text_path = old_path.with_name('text.json')
            old_bytes, text_bytes = old_path.read_bytes(), text_path.read_bytes()
            controls(root, release, 'a'*64, llms, pacer)
            self.assertEqual(pacer.state['requests'][:2], old_rows)
            self.assertEqual(old_path.read_bytes(), old_bytes)
            self.assertEqual(text_path.read_bytes(), text_bytes)
            self.assertEqual(len(requests), 4)
            self.assertEqual(pacer.state['requests'][2]['point_id'], 'CONTROL_V4_vision_r2')
            self.assertTrue(all(r['point_id'].startswith('CONTROL_V4_') for r in pacer.state['requests']))
            controls(root, release, 'a'*64, llms, pacer)
            self.assertEqual(len(requests), 4)
            http.close()

    def test_provider_echo_is_redacted_before_storage_or_console(self) -> None:
        request = httpx.Request('POST', 'https://fixture.invalid', headers={'Authorization': 'Bearer fixture-key'})
        response = httpx.Response(400, json={'error': {'message': 'Bearer fixture-key data:image/png;base64,'+'x'*100,
            'type': 'gsk_anothersecret', 'code': 'invalid_request', 'param': 'messages'}}, request=request)
        fields = error_fields(response, request)
        self.assertNotIn('fixture-key', str(fields))
        self.assertNotIn('anothersecret', str(fields))
        self.assertNotIn('x'*100, str(fields))
        self.assertEqual(fields['code'], 'invalid_request')

    def test_non_json_and_malformed_provider_errors_are_safe(self) -> None:
        request = httpx.Request('POST', 'https://fixture.invalid')
        for response in (httpx.Response(400, content=b'not json'), httpx.Response(400, json={'error': ['bad']})):
            self.assertIn('message', error_fields(response, request))

    def fixture_hotfix(self, root: Path) -> dict:
        """Tạo receipt fixture và object Git giả; không reseal bằng chứng thật."""
        parent = root/PARENT
        parent.parent.mkdir(parents=True, exist_ok=True)
        parent.write_bytes(PARENT.read_bytes())
        for name in SOURCES:
            path = root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('fixture:'+name).encode())
        payload = {'version': 'conditional_v4_collection_http_hotfix_v1', 'parent_sha256': PARENT_SHA,
            'source_commit': 'fixture', 'source_sha256': {n: checksum((root/n).read_bytes()) for n in SOURCES}, 'policy': deepcopy(POLICY)}
        (root/AMENDMENT).write_bytes(encoded(payload))
        return payload

    def test_hotfix_requires_source_hash_and_Git_objects(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            payload = self.fixture_hotfix(root)
            def git_object(_root, command, ref):
                self.assertEqual(command, 'show')
                return (root/ref.split(':', 1)[1]).read_bytes()
            with patch('core.mt_bicl_v4_http_diagnostics.git', side_effect=git_object):
                self.assertEqual(verify_hotfix(root), payload['source_sha256'])
                (root/SOURCES[0]).write_bytes(b'changed')
                with self.assertRaises(DataCompletionError): verify_hotfix(root)

    def test_hotfix_cannot_enable_scientific_change_or_replace_parent(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            payload = self.fixture_hotfix(root)
            payload['policy']['research_requests_changed'] = True
            (root/AMENDMENT).write_bytes(encoded(payload))
            with patch('core.mt_bicl_v4_http_diagnostics.git', return_value=(root/AMENDMENT).read_bytes()):
                with self.assertRaises(DataCompletionError): verify_hotfix(root)
            self.fixture_hotfix(root)
            (root/PARENT).write_bytes(b'changed parent')
            with patch('core.mt_bicl_v4_http_diagnostics.git', return_value=(root/AMENDMENT).read_bytes()):
                with self.assertRaises(DataCompletionError): verify_hotfix(root)


if __name__ == '__main__':
    unittest.main()
