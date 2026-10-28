"""Kiểm khóa amendment, membership train và fixture toán; không fit hoặc train."""

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.verify_mt_bicl_protocol_v2 import (
    DIRECTORY, PROTOCOL_SHA256, ROOT, digest, main, training_membership,
    validate_spec, verify_evidence,
)


class RevisionProtocolTests(unittest.TestCase):
    """Tấn công bản sao trong RAM; không thay byte v1/v2 hoặc sinh output."""

    @classmethod
    def setUpClass(cls) -> None:
        """Đọc đặc tả và input đã có; không mở checkpoint hay dùng CUDA."""
        cls.data = (ROOT / DIRECTORY / "protocol_v2.json").read_bytes()
        cls.protocol = json.loads(cls.data)
        cls.artifacts = {name: (ROOT / DIRECTORY / name).read_bytes()
                         for name in cls.protocol["artifacts"]}
        cls.membership = json.loads(cls.artifacts["training_membership_v2.json"])
        cls.bank = json.loads((ROOT / "outputs/bayesian_benchmark/mt_bicl_v1/inputs/dense_bank_v1.json")
                              .read_bytes())["payload"]

    def test_spec_does_not_authorize_fit_train_or_decision(self) -> None:
        """Khóa recipe không tự thành release; quyền ngân sách giữ bằng không."""
        result = validate_spec(self.data, self.artifacts)
        self.assertEqual(digest(self.data), PROTOCOL_SHA256)
        for name in ("teacher_fit_allowed", "training_allowed", "development_allowed",
                     "decision_calls_allowed", "is_execution_plan"):
            self.assertIs(result[name], False)
        self.assertEqual(result["budget"]["training_budget_granted_seconds"], 0)

    def test_method_cannot_self_reseal_after_observing_results(self) -> None:
        """Thay grid/loss/gate/selection/giờ hoặc seed không được tự hợp thức hóa."""
        changes = [("teacher", "mu", [.5]), ("loss", "market_BCE", True),
                   ("mechanism", "mean_kl_max_nat", .1),
                   ("selection", "eligibility", "MARKET_ONLY"),
                   ("training", "model_seeds", [42]),
                   ("budget", "training_budget_granted_seconds", 14400)]
        for section, key, value in changes:
            with self.subTest(section=section):
                changed = deepcopy(self.protocol)
                changed[section][key] = value
                changed["self_sha256"] = digest(json.dumps(changed).encode())
                with self.assertRaisesRegex(ValueError, "Protocol v2 khác"):
                    validate_spec(json.dumps(changed).encode(), self.artifacts)

    def test_corpus_fixture_and_membership_tampering_is_rejected(self) -> None:
        """Tự băm artifact sửa không đổi binding đã khóa trong protocol."""
        for name in self.artifacts:
            with self.subTest(name=name):
                changed = dict(self.artifacts)
                value = json.loads(changed[name])
                value["self_sha256"] = "0"*64
                changed[name] = json.dumps(value).encode()
                with self.assertRaisesRegex(ValueError, "Artifact v2 khác"):
                    validate_spec(self.data, changed)

    def test_no_missing_or_extra_artifact(self) -> None:
        """Không bỏ recipe khó hoặc lén thêm corpus đã chạy vào đặc tả."""
        missing = dict(self.artifacts)
        missing.pop("corpus_manifest_v2.json")
        extra = {**self.artifacts, "predictions.json": b"{}"}
        for changed in (missing, extra):
            with self.assertRaisesRegex(ValueError, "Danh mục artifact"):
                validate_spec(self.data, changed)

    def test_real_frozen_sources_runtime_and_membership(self) -> None:
        """Đối soát hash v1/runtime thật và 731 cycle/48 block, không replay GPU."""
        summary = verify_evidence(ROOT, self.protocol, self.membership)
        self.assertEqual(summary["evidence_files"], 77)
        self.assertEqual((summary["train_cycles"], summary["train_tasks"]), (731, 48))

    def test_modified_v1_raw_logits_cannot_be_accepted(self) -> None:
        """Bảo vệ kết quả FAIL gốc thay vì chỉ kiểm cờ trạng thái."""
        original = Path.read_bytes
        target = ROOT / "outputs/bayesian_benchmark/mt_bicl_v1/evaluation_v1/seed42.json"

        def read(path: Path) -> bytes:
            """Giả lập sửa logits trên bản đọc, không ghi artifact."""
            return b"modified logits" if path == target else original(path)

        with patch.object(Path, "read_bytes", read):
            with self.assertRaisesRegex(ValueError, "Nguồn/bằng chứng đã đổi"):
                verify_evidence(ROOT, self.protocol, self.membership)

    def test_changed_legacy_learner_is_rejected(self) -> None:
        """V2 không cho sửa ngầm backbone v1 đang được receipt tham chiếu."""
        original = Path.read_bytes

        def read(path: Path) -> bytes:
            """Chỉ thay bản đọc source trong RAM."""
            return b"modified model" if path == ROOT / "core/mt_bicl_model.py" else original(path)

        with patch.object(Path, "read_bytes", read):
            with self.assertRaisesRegex(ValueError, "Nguồn/bằng chứng đã đổi"):
                verify_evidence(ROOT, self.protocol, self.membership)

    def test_future_and_outcomes_cannot_change_training_membership(self) -> None:
        """Thêm tương lai hoặc đổi nhãn không làm lọt query khác vào tập fit."""
        changed = deepcopy(self.bank)
        future = deepcopy(next(row for row in changed["records"]
                               if row["split"] == "validation" and row["status"] == "AVAILABLE"))
        future["episode_id"] = "future-copy"
        changed["records"].append(future)
        for row in changed["records"]:
            row.pop("outcome", None)
        self.assertEqual(training_membership(changed), training_membership(self.bank))

    def test_future_mislabeled_train_and_duplicate_raise(self) -> None:
        """Vi phạm date/ID trong membership phải dừng, không bỏ qua âm thầm."""
        future_bank = deepcopy(self.bank)
        future = next(row for row in future_bank["records"]
                      if row["split"] == "validation" and row["status"] == "AVAILABLE")
        future["split"] = "train"
        with self.assertRaisesRegex(ValueError, "ngoài split"):
            training_membership(future_bank)
        duplicate = deepcopy(self.bank)
        duplicate["records"].append(deepcopy(next(row for row in duplicate["records"]
                                                 if row["split"] == "train" and row["status"] == "AVAILABLE")))
        with self.assertRaisesRegex(ValueError, "ID trùng"):
            training_membership(duplicate)

    def test_training_blocks_count_once_instead_of_once_per_query(self) -> None:
        """EM dùng đúng một task/block; pool feature gồm cả tám cycle thiếu prefix."""
        observed = training_membership(self.bank)
        self.assertEqual(observed["task_cycle_ids"], self.membership["task_cycle_ids"])
        all_ids = [value for group in observed["task_cycle_ids"].values() for value in group]
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertEqual(set(all_ids), set(self.membership["feature_pool_ids"]))
        self.assertEqual(len(all_ids), 731)

    def test_uniform_prior_math_fixtures_by_exact_recurrence(self) -> None:
        """Tích predictive hữu tỉ kiểm fixture nhỏ, chưa là oracle production v2."""
        fixtures = json.loads(self.artifacts["protocol_fixtures_v2.json"])

        def likelihood(a: Fraction, b: Fraction, counts: list[int]) -> Fraction:
            """Tích xác suất theo nhãn; không dùng log-beta hoặc helper teacher."""
            result = Fraction(1)
            for i, y in enumerate([1]*counts[0]+[0]*counts[1]):
                result *= (a if y else b)/(a+b)
                a, b = a+y, b+(1-y)
            return result

        for fixture in fixtures["teacher_cases"]:
            terms = []
            pooling_terms = []
            for mu in (Fraction(i, 5) for i in (1, 2, 3, 4)):
                for k in (2, 8, 32, 128):
                    a, b = mu*k, (1-mu)*k
                    s, f = fixture["target_counts"]
                    w = likelihood(a, b, [s, f])
                    for counts in fixture["prior_counts"]:
                        w *= likelihood(a, b, counts)
                    terms.append((w, (a+s)/(k+s+f)))
                    s += sum(counts[0] for counts in fixture["prior_counts"])
                    f += sum(counts[1] for counts in fixture["prior_counts"])
                    pooling_terms.append((likelihood(a, b, [s, f]), (a+s)/(k+s+f)))
            actual = sum(w*p for w, p in terms)/sum(w for w, _ in terms)
            pooled = sum(w*p for w, p in pooling_terms)/sum(w for w, _ in pooling_terms)
            n, d = fixture["p_exact_fraction"]
            self.assertEqual(actual, Fraction(int(n), int(d)))
            self.assertAlmostEqual(float(actual), fixture["p"], delta=1e-12)
            self.assertAlmostEqual(float(pooled), fixture["pooling_p"], delta=1e-12)
        conflict = next(row for row in fixtures["teacher_cases"] if row["id"] == "conflicting_tasks")
        self.assertGreater(abs(conflict["p"]-conflict["pooling_p"]), .2)

    def test_cli_rejects_run_fit_and_reseal_flags(self) -> None:
        """CLI đặc tả không có lối cấp quyền thực thi qua tham số."""
        for flag in ("run", "fit", "--train", "--reseal"):
            with patch("sys.argv", ["verify_mt_bicl_protocol_v2.py", flag]):
                with self.assertRaisesRegex(ValueError, "không nhận cờ"):
                    main()


if __name__ == "__main__":
    unittest.main()
