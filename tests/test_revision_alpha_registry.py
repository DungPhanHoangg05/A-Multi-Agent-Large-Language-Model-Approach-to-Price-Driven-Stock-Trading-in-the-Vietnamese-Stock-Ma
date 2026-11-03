"""Kiểm registry audit, provenance và fail-closed; không backtest hoặc gọi model."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import alpha_compare
from core.revision_common_study import read_json, write_json
from core.revision_alpha_registry import (
    AGENT, CATALOGUE, RUNTIME, RUN, SELECTOR, build_registry, check_release,
    formula_requirements, run_audit, source_tree,
)

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = [48, 56, 58, 59, 63, 64, 67, 68, 69, 70, 76, 79, 80, 81, 82, 87, 90, 91, 93, 97, 100]


class AlphaRegistryTests(unittest.TestCase):
    """Đối chiếu AST với registry/template import thật và các facts gốc độc lập."""

    @classmethod
    def setUpClass(cls) -> None:
        """Xuất một lần trong bộ nhớ, không tạo artifacts thật hoặc chạy handlers."""
        cls.registry = build_registry(ROOT)

    def fixture(self) -> Path:
        """Tạo repo nhỏ với byte nguồn thật để thử tamper mà không sửa nguồn frozen."""
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        paths = [RUNTIME, AGENT, SELECTOR, CATALOGUE,
                 Path("core/revision_alpha_registry.py"), Path("scripts/audit_alpha_registry.py"), Path("tests/test_revision_alpha_registry.py"),
                 Path("core/revision_audit.py"), Path("core/revision_common_study.py"), Path("core/revision_sentiment_inventory.py"),
                 Path(read_json(ROOT / CATALOGUE)["pdf_path"])]
        for path in paths:
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, root / path)
        write_json(root / RUN / "manifest.json", {"sha256": "fixture_signature", "sources": [
            {"path": RUNTIME.as_posix(), "sha256": hashlib.sha256((root / RUNTIME).read_bytes()).hexdigest()}]})
        return root

    def test_all_ids_counts_and_absence_reasons_are_explicit(self) -> None:
        registry = self.registry
        self.assertEqual(registry["counts"], {"worldquant_catalogue": 101, "worldquant_retained": 80,
                                            "worldquant_excluded": 21, "custom": 5, "runtime_candidates": 85})
        self.assertEqual([r["worldquant_id"] for r in registry["worldquant"]], list(range(1, 102)))
        self.assertEqual(registry["excluded_worldquant_ids"], EXCLUDED)
        self.assertEqual(registry["excluded_dependency_classes"], {"industry_neutralization": 17, "market_cap": 1,
                                                                 "unexplained_price_volume_omission": 3})
        for row in registry["worldquant"]:
            self.assertEqual(row["historical_selection_rationale"], "unknown")
            self.assertTrue(row["reason"])
            self.assertEqual(row["implementation"] is None, row["worldquant_id"] in EXCLUDED)

    def test_matches_actual_runtime_handlers_order_and_bilingual_templates(self) -> None:
        entries = [r["implementation"] for r in self.registry["worldquant"] if r["implementation"]]
        entries += [r["implementation"] for r in self.registry["custom"]]
        entries.sort(key=lambda row: row["registry_position"])
        self.assertEqual([r["registry_key"] for r in entries], list(alpha_compare.ALPHA_REGISTRY))
        for row in entries:
            key = row["registry_key"]
            self.assertEqual(row["handler"]["name"], alpha_compare.ALPHA_REGISTRY[key][0].__name__)
            for lang in ("vi", "en"):
                self.assertEqual(row["display_template"][lang], alpha_compare.get_alpha_template(key, lang))

    def test_original_formula_and_source_pages_are_not_docstrings(self) -> None:
        rows = self.registry["worldquant"]
        self.assertIn("60", rows[6]["original"]["formula"])
        self.assertIn("rank_abs = ts_rank(abs_delta7, 30)", rows[6]["implementation"]["handler"]["implementation"])
        self.assertIn("open^5", rows[53]["original"]["formula"])
        self.assertIn("d['Open'] ** 2", rows[53]["implementation"]["handler"]["implementation"])
        self.assertIn("IndNeutralize(vwap", rows[88]["original"]["formula"])
        self.assertNotIn("IndNeutralize", rows[88]["implementation"]["handler"]["implementation"])
        self.assertEqual(rows[88]["original"]["pdf_page"], 14)
        self.assertEqual(rows[-1]["original"]["formula"], "((close - open) / ((high - low) + .001))")
        self.assertTrue(all(r["original"]["source_version"] == "arXiv:1601.00991v3" for r in rows))

    def test_requirements_do_not_confuse_ts_rank_or_claim_all_exclusions_industry(self) -> None:
        self.assertFalse(formula_requirements("ts_rank(volume, 5)")["cross_sectional_rank"])
        self.assertTrue(formula_requirements("rank(volume)")["cross_sectional_rank"])
        for identity in (64, 68, 81):
            row = self.registry["worldquant"][identity - 1]
            self.assertFalse(row["original_requirements"]["industry_neutralization"])
            self.assertFalse(row["original_requirements"]["market_cap"])
        self.assertTrue(self.registry["worldquant"][55]["original_requirements"]["market_cap"])
        self.assertTrue(self.registry["worldquant"][88]["original_requirements"]["industry_neutralization"])
        self.assertEqual(self.registry["worldquant"][88]["status"], "retained")

    def test_code_pointers_and_dependency_closure_are_real(self) -> None:
        source, tree = source_tree(ROOT, RUNTIME)
        definitions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        for row in self.registry["worldquant"]:
            if row["implementation"] is None: continue
            handler = row["implementation"]["handler"]
            node = definitions[handler["name"]]
            self.assertEqual(handler["code"]["line"], node.lineno)
            self.assertEqual(handler["source_sha256"], hashlib.sha256(ast.get_source_segment(source, node).encode()).hexdigest())
        wq32 = self.registry["worldquant"][31]["implementation"]
        self.assertTrue({"normalize_alpha", "delay", "ts_corr", "ts_mean"}.issubset(wq32["helper_dependencies"]))
        names = {r["name"] for r in self.registry["helpers_and_pipeline"]}
        self.assertTrue({"build_features", "normalize_alpha", "run_backtest", "rank_alphas"}.issubset(names))

    def test_custom_display_and_prototype_are_separate(self) -> None:
        first, second, _, fourth, _ = self.registry["custom"]
        self.assertIn("vol_surge", first["implementation"]["handler"]["implementation"])
        self.assertIn("MACD", first["implementation"]["display_template"]["vi"]["formula"])
        self.assertNotIn("SENT_Z", second["implementation"]["handler"]["implementation"])
        self.assertIn("SENT_Z", second["implementation"]["display_template"]["vi"]["formula"])
        self.assertIn("is_reliable", second["prototype_fallback"]["implementation"])
        self.assertIn("vol_z5", fourth["prototype_fallback"]["implementation"])
        self.assertIsNone(fourth["worldquant_id"])

    def test_original_pdf_tamper_or_catalogue_id_tamper_rejected(self) -> None:
        root = self.fixture()
        catalogue = read_json(root / CATALOGUE)
        pdf = root / catalogue["pdf_path"]
        original = pdf.read_bytes(); pdf.write_bytes(original + b"changed")
        with self.assertRaisesRegex(ValueError, "PDF catalogue sai hash"): build_registry(root)
        pdf.write_bytes(original)
        catalogue["formulas"][1]["id"] = 1
        write_json(root / CATALOGUE, catalogue)
        with self.assertRaisesRegex(ValueError, "Catalogue"): build_registry(root)

    def test_runtime_duplicate_or_mismatched_handler_rejected(self) -> None:
        root = self.fixture(); path = root / RUNTIME
        original = path.read_text(encoding="utf-8")
        for changed in (original.replace('"WQ02_PriceVolDiv":    (wq2,', '"WQ02_PriceVolDiv":    (wq3,'),
                        original.replace('"WQ03_OpenVolCorr":', '"WQ02_PriceVolDiv":', 1)):
            self.assertNotEqual(changed, original)
            path.write_text(changed, encoding="utf-8")
            with self.assertRaises(ValueError): build_registry(root)

    def test_counts_report_actual_changes_instead_of_filling_to_eighty(self) -> None:
        root = self.fixture(); path = root / RUNTIME
        source = path.read_text(encoding="utf-8")
        lines = [line for line in source.splitlines() if not ('"WQ06_OpenVol":' in line and '(wq6,' in line)]
        path.write_text("\n".join(lines), encoding="utf-8")
        result = build_registry(root)
        self.assertEqual(result["counts"]["worldquant_retained"], 79)
        self.assertFalse(result["count_contract_80_21_5_matches"])
        self.assertIn(6, result["excluded_worldquant_ids"])

    def test_ast_audit_does_not_execute_module_body(self) -> None:
        root = self.fixture(); path = root / RUNTIME
        path.write_text('raise AssertionError("Không được thực thi module body")\n' + path.read_text(encoding="utf-8"), encoding="utf-8")
        self.assertEqual(build_registry(root)["counts"]["runtime_candidates"], 85)

    def test_release_hash_check_and_immutable_output_guard(self) -> None:
        root = self.fixture(); output = root / "outputs/revision/fixture_registry"
        result = run_audit(root, output)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(check_release(root, output), 14)
        with self.assertRaisesRegex(ValueError, "Release đã có"): run_audit(root, output)
        (output / "registry.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Hash sai"): check_release(root, output)

    def test_frozen_source_tamper_and_outside_output_rejected_before_write(self) -> None:
        root = self.fixture(); output = root / "outputs/revision/fixture_registry"
        with (root / RUNTIME).open("ab") as stream: stream.write(b"\n# fixture\n")
        with self.assertRaisesRegex(ValueError, "Nguồn frozen đổi"): run_audit(root, output)
        self.assertFalse(output.exists())
        with self.assertRaisesRegex(ValueError, "release riêng"): run_audit(root, root / "paper/generated")
        self.assertFalse((root / "paper").exists())


if __name__ == "__main__":
    unittest.main()
