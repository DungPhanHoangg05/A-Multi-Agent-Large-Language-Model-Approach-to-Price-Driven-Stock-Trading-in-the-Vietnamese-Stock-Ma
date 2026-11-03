"""Kiểm tra audit không biến thiếu provenance hoặc trùng prediction thành xác thực."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.audit_revision_lineage import compare, json_bytes, normalize, sha, verify


def fixture() -> dict:
    """Tạo hai cutoff có thông tin quyết định và tài khoản tối thiểu."""
    return {"symbol": "FPT", "n_tests": 2, "panel": "norm", "scenario": "rank",
            "protocol": "shared_upstream_across_alpha_configs", "test_points": [
                {"test_id": i, "window_end": f"2026-09-{i:02}", "actual_direction": "UP",
                 "pred_full": "LONG", "pred_no_alpha": "SHORT", "correct_full": True,
                 "correct_no_alpha": False, "time_full_sec": 2.5, "time_no_alpha_sec": 1.5,
                 "equity_full_vnd": 50000000, "equity_no_alpha_vnd": 50000000}
                for i in (1, 2)]}


class LineageTests(unittest.TestCase):
    """Bao phủ join/support, missing, nhầm branch và chống sửa bằng chứng."""

    def test_normalize_keeps_timing_equity_and_unknown_identity(self) -> None:
        stream = normalize(fixture(), "a.json")[0]
        self.assertEqual(stream["rows"][0]["decision"]["time_sec"], 2.5)
        self.assertEqual(stream["rows"][0]["account"]["equity_vnd"], 50000000)
        self.assertIsNone(stream["request_id"])
        self.assertEqual(stream["execution_commit"], "unknown")

    def test_date_join_does_not_compare_row_indices(self) -> None:
        left = normalize(fixture(), "a.json")[0]
        right = deepcopy(left)
        right["rows"][0]["cutoff"] = "2025-01-01"
        result = compare(left, right)
        self.assertEqual(result["n_common"], 1)
        self.assertEqual(result["n_left_only"], 1)
        self.assertFalse(result["identical_prediction_sequence"])

    def test_missing_values_are_not_equal_evidence(self) -> None:
        a, b = normalize(fixture(), "a.json")
        counts = compare(a, b)["counts"]["decision.confidence"]
        self.assertEqual(counts, {"both_present": 0, "equal_present": 0, "missing_either": 2})

    def test_duplicate_treatment_is_never_authenticated_control(self) -> None:
        left = normalize(fixture(), "a.json")[1]
        right = deepcopy(left)
        right.update(variant="alpha_only", id="b.json#alpha_only")
        result = compare(left, right)
        self.assertTrue(result["identical_prediction_sequence"])
        self.assertEqual(result["classification"], "duplicate_sequence_execution_unverified")

    def test_intended_control_still_lacks_parent(self) -> None:
        left = normalize(fixture(), "a.json")[1]
        right = normalize(fixture(), "b.json")[1]
        self.assertEqual(compare(left, right)["classification"], "intended_shared_control_parent_unverified")

    def test_duplicate_dates_and_invalid_labels_fail(self) -> None:
        value = fixture()
        value["test_points"][1]["window_end"] = value["test_points"][0]["window_end"]
        with self.assertRaises(ValueError):
            normalize(value, "a.json")
        value = fixture()
        value["test_points"][0]["pred_full"] = "UNKNOWN"
        with self.assertRaises(ValueError):
            normalize(value, "a.json")

    def test_four_way_fields_and_missing_account(self) -> None:
        value = fixture()
        value["variants"] = ["alpha_only"]
        for p in value["test_points"]:
            p["variants"] = {"alpha_only": {"prediction": "LONG", "confidence": "Cao", "time_sec": 4.5}}
        stream = normalize(value, "b.json")[0]
        self.assertEqual(stream["rows"][0]["decision"]["time_sec"], 4.5)
        self.assertIsNone(stream["rows"][0]["account"]["equity"])

    def test_no_overlap_and_cross_symbol(self) -> None:
        a, b = normalize(fixture(), "a.json")
        for row in b["rows"]:
            row["cutoff"] = "2025" + row["cutoff"][4:]
        self.assertFalse(compare(a, b)["identical_prediction_sequence"])
        b["symbol"] = "VCB"
        with self.assertRaises(ValueError):
            compare(a, b)

    def test_hash_rejects_source_and_output_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "source").write_bytes(b"original\r\n")
            (root / "output").write_bytes(b"result\n")
            manifest = {"sources": [{"path": "source", "sha256": sha(b"original\r\n")}],
                        "outputs": [{"path": "output", "sha256": sha(b"result\n")}]}
            (root / "manifest.json").write_bytes(json_bytes(manifest))
            with patch("scripts.audit_revision_lineage.ROOT", root):
                self.assertEqual(verify(root), 2)
                for name, original in (("source", b"original\r\n"), ("output", b"result\n")):
                    (root / name).write_bytes(b"changed")
                    with self.assertRaises(ValueError):
                        verify(root)
                    (root / name).write_bytes(original)
            with self.assertRaises(ValueError):
                json_bytes({"metric": float("nan")})


if __name__ == "__main__":
    unittest.main()
