"""Kiểm T28 từ chối coverage giả, receipt bị sửa và ngoại lệ lịch sử quá rộng."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from core.revision_reproducibility import digest, encoded
from scripts.check_revision_regression import ATTR_APPEND, historical_attributes, load_cases, output_folder, require_success, verify_parent


class RegressionAuditTests(unittest.TestCase):
    """Chỉ fixtures tạm; không sửa nguồn/run/receipt thực hoặc gọi API."""

    def test_case_plan_rejects_duplicates_and_missing_names(self) -> None:
        name = 'test_revision_regression.RegressionAuditTests.test_case_plan_rejects_duplicates_and_missing_names'
        self.assertEqual(load_cases({'guard': (name,)}).countTestCases(), 1)
        for plan in ({}, {'a': (name,), 'b': (name,)}, {'a': ('test_revision_regression.no_such_case',)}):
            with self.subTest(plan=plan), self.assertRaises(ValueError): load_cases(plan)

    def test_parent_source_and_output_tamper_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'source.json'; source.write_bytes(b'{}')
            folder = root / 'outputs/revision/fixture'; folder.mkdir(parents=True)
            value = folder / 'result.json'; value.write_bytes(b'{}')
            manifest = {'sources': [{'path': 'source.json', 'sha256': digest(b'{}')}],
                        'outputs': [{'path': 'result.json', 'sha256': digest(b'{}')}]}
            (folder / 'manifest.json').write_bytes(encoded(manifest))
            result, _ = verify_parent(root, 'fixture')
            self.assertEqual(result['source_output_hashes'], 2)
            for path in (source, value):
                path.write_bytes(b'changed')
                with self.assertRaises(ValueError): verify_parent(root, 'fixture', b'{}')
                path.write_bytes(b'{}')

    def test_failed_skipped_or_expected_failure_cannot_pass(self) -> None:
        def result(**values: object) -> SimpleNamespace:
            """Giả result để kiểm gate không mở rộng số ca hoặc lấp skip thành PASS."""
            return SimpleNamespace(**{'testsRun': 2, 'wasSuccessful': lambda: True,
                                      'skipped': [], 'expectedFailures': [], 'unexpectedSuccesses': [], **values})
        require_success(result(), 2)
        for values in ({'testsRun': 1}, {'wasSuccessful': lambda: False}, {'skipped': ['case']},
                       {'expectedFailures': ['case']}, {'unexpectedSuccesses': ['case']}):
            with self.subTest(values=values), self.assertRaises(ValueError): require_success(result(**values), 2)

    def test_output_path_never_overwrites_or_targets_paper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'outputs/revision/existing').mkdir(parents=True)
            self.assertEqual(output_folder(root, Path('outputs/revision/new')), root / 'outputs/revision/new')
            for path in ('paper', 'outputs/revision/existing', 'outputs/revision/new/nested', '../escape'):
                with self.subTest(path=path), self.assertRaises(ValueError): output_folder(root, Path(path))

    def test_historical_attributes_cannot_mask_runtime_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); original = b'original\n'; path = root / '.gitattributes'
            path.write_bytes(original + ATTR_APPEND)
            historical_attributes(root, digest(original), original)
            with self.assertRaises(ValueError): historical_attributes(root, digest(b'other'), original)
            path.write_bytes(original + ATTR_APPEND + b'other runtime rule\n')
            with self.assertRaises(ValueError): historical_attributes(root, digest(original), original)
            folder = root / 'outputs/revision/fixture'; folder.mkdir(parents=True)
            (root / 'runtime.py').write_bytes(b'new')
            (folder / 'manifest.json').write_bytes(encoded({'sources': [{'path': 'runtime.py', 'sha256': digest(b'old')}], 'outputs': []}))
            with self.assertRaises(ValueError): verify_parent(root, 'fixture', b'old')


if __name__ == '__main__': unittest.main()
