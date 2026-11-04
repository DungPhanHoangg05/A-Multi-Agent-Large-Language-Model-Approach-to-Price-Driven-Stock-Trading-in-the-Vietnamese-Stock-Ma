"""Kiểm auditor source T16 bằng snapshots giả lập, không network hoặc import upstream."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.audit_quantagent_attribution import file_comparison, redacted_snapshot, sha, symbols, verify


class QuantAgentAttributionTests(unittest.TestCase):
    """Byte identity, AST identity và provenance không được đánh đồng."""

    def test_ast_is_inert_and_retains_nested_locators(self) -> None:
        source = b"raise RuntimeError('must not execute')\nclass C:\n def f(self):\n  return 1\n"
        result = symbols(source)
        self.assertEqual(set(result), {'C', 'C.f'})
        self.assertEqual((result['C.f']['line'], result['C.f']['end_line']), (3, 4))

    def test_comment_and_line_endings_do_not_mean_same_bytes(self) -> None:
        upstream = b'def f():\n return 1\n'
        initial = upstream.replace(b'\n', b'\r\n')
        current = b'# modified comment\ndef f():\n    return 1\n'
        result = file_comparison(upstream, initial, current, True)
        self.assertFalse(result['initial_exact_bytes']); self.assertTrue(result['initial_equal_after_lf'])
        self.assertFalse(result['current_exact_bytes'])
        self.assertEqual(result['current_identical_ast_symbols'], ['f'])

    def test_prompt_and_algorithm_changes_change_ast_identity(self) -> None:
        result = file_comparison(b'def f():\n return "upstream prompt"\n',
                                 b'def f():\n return "upstream prompt"\n',
                                 b'def f():\n return "daily prompt"\n', True)
        self.assertEqual(result['initial_local_identical_ast_symbols'], ['f'])
        self.assertEqual(result['current_identical_ast_symbols'], [])

    def test_missing_import_snapshot_is_unknown_not_fabricated(self) -> None:
        source = b'def f():\n return 1\n'
        result = file_comparison(source, None, source, True)
        self.assertIsNone(result['initial_local_sha256'])
        self.assertIsNone(result['initial_exact_bytes'])
        self.assertIsNone(result['initial_local_identical_ast_symbols'])
        self.assertTrue(result['current_exact_bytes'])

    def test_shared_snapshot_masks_credential_pattern_without_modifying_input(self) -> None:
        original = b'key=' + b'gsk_' + b'A'*30
        safe, count = redacted_snapshot(original)
        self.assertEqual(count, 1)
        self.assertNotIn(b'A'*30, safe)
        self.assertIn(b'[REDACTED_CREDENTIAL_PATTERN]', safe)
        self.assertTrue(original.endswith(b'A'*30))
        self.assertEqual(redacted_snapshot(safe), (safe, 0))

    def fixture(self, root: Path) -> Path:
        """Sinh receipt nhỏ với copyright rõ ràng để kiểm không ghi đè/sửa nguồn."""
        folder = root / 'release'; folder.mkdir()
        current = b'def f():\n return 1\n'; license_bytes = b'MIT License\nCopyright (c) 2025 Y-Research @SBU\n'
        (root / 'current.py').write_bytes(current); (root / 'LICENSES').mkdir()
        (root / 'LICENSES/QuantAgent-MIT.txt').write_bytes(license_bytes)
        members = {'current/current.py': current, 'initial/current.py': current,
                   'upstream/current.py': current, 'upstream/LICENSE': license_bytes}
        with zipfile.ZipFile(folder / 'sources.zip', 'w') as archive:
            for name, data in members.items(): archive.writestr(name, data)
        row = {'local_path': 'current.py', 'upstream_path': 'current.py', 'classification': 'reused',
               'current_member': 'current/current.py', 'initial_member': 'initial/current.py',
               'upstream_member': 'upstream/current.py', 'comparison': file_comparison(current, current, current, True)}
        evidence = {'snapshot_members': [{'member': k, 'sha256': sha(v)} for k, v in members.items()], 'file_components': [row]}
        (folder / 'attribution.json').write_text(json.dumps(evidence), encoding='utf-8')
        self.receipt(root, folder)
        return folder

    def receipt(self, root: Path, folder: Path) -> None:
        """Tạo lại receipt ngoài để kiểm guard semantic không chỉ dựa vào hash ngoài."""
        manifest = {'sources': [{'path': 'current.py', 'sha256': sha((root / 'current.py').read_bytes())}],
                    'outputs': [{'path': p.name, 'sha256': sha(p.read_bytes())} for p in sorted(folder.iterdir()) if p.name != 'manifest.json']}
        (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    def test_verify_rejects_source_or_output_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); folder = self.fixture(root)
            self.assertEqual(verify(folder, root), 3)
            (root / 'current.py').write_bytes(b'tampered')
            with self.assertRaises(ValueError): verify(folder, root)

    def test_resigned_false_reuse_claim_cannot_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); folder = self.fixture(root)
            path = folder / 'attribution.json'; evidence = json.loads(path.read_bytes())
            evidence['file_components'][0]['classification'] = 'modified'
            path.write_text(json.dumps(evidence), encoding='utf-8'); self.receipt(root, folder)
            with self.assertRaises(ValueError): verify(folder, root)

    def test_changed_license_and_zip_members_cannot_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); folder = self.fixture(root)
            path = root / 'LICENSES/QuantAgent-MIT.txt'; original = path.read_bytes(); path.write_bytes(b'changed')
            with self.assertRaises(ValueError): verify(folder, root)
            path.write_bytes(original)
            with zipfile.ZipFile(folder / 'sources.zip', 'a') as archive: archive.writestr('extra', b'x')
            self.receipt(root, folder)
            with self.assertRaises(ValueError): verify(folder, root)


if __name__ == '__main__':
    unittest.main()
