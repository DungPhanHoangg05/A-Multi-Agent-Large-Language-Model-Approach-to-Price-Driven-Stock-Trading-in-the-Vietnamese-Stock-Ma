"""Kiểm export T32 không biến undefined thành zero hoặc che source bị đổi."""
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile
from unittest.mock import patch

from core.revision_reproducibility import digest,encoded
from scripts.build_revision_manuscript import build,check_release,esc,historical_bytes,interval,num,panel


class ManuscriptExportTests(unittest.TestCase):
    """Fixtures nhỏ độc lập, không ghi vào paper hoặc gọi provider."""
    def test_metric_scale_na_and_nonfinite(self) -> None:
        self.assertEqual(num(.5296103896,100),'52.96')
        self.assertEqual(num(.060053,1,3),'0.060')
        self.assertEqual(num(None),'NA');self.assertEqual(num('NA'),'NA')
        self.assertEqual(num(-.00000001),'0.00')
        for value in (float('nan'),float('inf')):
            with self.assertRaises(ValueError):num(value)

    def test_interval_never_fills_missing_endpoint(self) -> None:
        self.assertEqual(interval(-.0117647,.08125),'[-1.18, 8.12]')
        self.assertEqual(interval(None,.1),'NA');self.assertEqual(interval('NA','NA'),'NA')

    def test_tex_escapes_source_ids_and_rejects_misaligned_columns(self) -> None:
        self.assertEqual(esc('A_B & 20%'),r'A\_B \& 20\%')
        with self.assertRaises(ValueError):panel('fixture',['one','two'],[['only one']])

    def test_historical_paper_needs_exact_archive_member(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);file=root/'paper/main.tex';file.parent.mkdir();file.write_bytes(b'new')
            archive=root/'source.zip'
            with ZipFile(archive,'w') as z:z.writestr('paper/main.tex',b'old')
            value,where=historical_bytes(root,'paper/main.tex',digest(b'old'),archive)
            self.assertEqual((value,where),(b'old','original_sources.zip'))
            self.assertEqual(historical_bytes(root,'paper/main.tex',digest(b'new'),archive)[1],'current')
            with self.assertRaises(ValueError):historical_bytes(root,'paper/main.tex',digest(b'wrong'),archive)

    def test_archive_cannot_hide_changed_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'runtime.py').write_bytes(b'new');archive=root/'source.zip'
            with ZipFile(archive,'w') as z:z.writestr('runtime.py',b'old')
            with self.assertRaises(ValueError):historical_bytes(root,'runtime.py',digest(b'old'),archive)

    def test_build_refuses_existing_generation_before_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out=root/'outputs/revision/manuscript_rewrite_v1';out.mkdir(parents=True)
            (out/'original_sources.zip').write_bytes(b'fixture');(out/'generation.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):build(root)
            self.assertFalse((root/'paper').exists())

    def test_release_path_cannot_target_paper_or_nested_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for path in ('paper','outputs/revision/new/nested','../escape'):
                with self.subTest(path=path),self.assertRaises(ValueError):build(Path(directory),Path(path),True)

    def test_receipt_checker_catches_source_output_and_extra_file(self) -> None:
        from core.revision_minimal_bank import runtime
        from importlib.metadata import version
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'outputs/revision/manuscript_rewrite_v1';folder.mkdir(parents=True)
            source=root/'source.txt';source.write_bytes(b'source');value=folder/'value.json';value.write_bytes(b'{}')
            report=root/'outputs/revision/final_regression_v1/report.json';report.parent.mkdir()
            report.write_bytes(encoded({'runtime_after':{**runtime(),'jsonschema':version('jsonschema')}}))
            m={'sources':[{'path':'source.txt','sha256':digest(b'source')}],'outputs':[{'path':'value.json','sha256':digest(b'{}')}]}
            m['sha256']=digest(encoded(m));(folder/'manifest.json').write_bytes(encoded(m))
            with patch('scripts.build_revision_manuscript.verify_parents',return_value={}):
                self.assertEqual(check_release(root)['source_output_hashes'],2)
                for path,original in ((source,b'source'),(value,b'{}')):
                    path.write_bytes(b'changed')
                    with self.assertRaises(ValueError):check_release(root)
                    path.write_bytes(original)
                (folder/'extra.txt').write_bytes(b'extra')
                with self.assertRaises(ValueError):check_release(root)


if __name__=='__main__':unittest.main()
