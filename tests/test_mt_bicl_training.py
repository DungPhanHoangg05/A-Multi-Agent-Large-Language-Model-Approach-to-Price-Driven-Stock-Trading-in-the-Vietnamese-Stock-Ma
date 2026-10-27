"""Kiểm checkpoint/RNG, transaction resume và ngân sách trước khi người dùng train GPU."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import torch

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

from core.mt_bicl_bank import content_hash
from core.mt_bicl_model import MTBiCLLearner
from core.mt_bicl_trainer import _same_tree, preflight, save_resume, seal_training, train_seed, verify_training
from core.mt_bicl_training import configure, make_optimizer, optimizer_step, restore_rng, rng_state, selection_metrics
from core.mt_bicl_training_io import (RunBudget, checkpoint_payload, file_hash, load_checkpoint, read_manifest,
                                      save_checkpoint, write_manifest)
from test_mt_bicl_training_leakage import packets


class TrainingCheckpointTests(unittest.TestCase):
    """Chạy optimizer CPU ngắn để so resume thực, không tạo candidate ít step."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.device = configure(17, cuda=False)
        self.model = MTBiCLLearner()
        self.optimizer = make_optimizer(self.model)
        self.data = packets()
        self.identity = {"budget_seconds": 43200, "data_stop": "2099-12-31", "test": "fixture_only"}

    def payload(self, step: int = 1) -> dict:
        """Snapshot theo cùng định dạng production, không sửa protocol của CLI."""
        return checkpoint_payload(self.model, self.optimizer, identity=content_hash(self.identity),
                                  seed=17, step=step, physical_batch=4)

    def test_optimizer_contract(self) -> None:
        defaults = self.optimizer.defaults
        self.assertEqual((defaults["lr"], defaults["betas"], defaults["eps"], defaults["weight_decay"]),
                         (3e-4, (.9, .999), 1e-8, .01))
        self.assertFalse(defaults["foreach"])
        self.assertFalse(defaults["fused"])

    def test_resume_is_bit_identical_with_dropout_optimizer_and_rng(self) -> None:
        optimizer_step(self.model, self.optimizer, self.data, 4, self.device)
        record = save_checkpoint(self.directory/"checkpoint.pt", self.payload())
        expected_loss = optimizer_step(self.model, self.optimizer, self.data, 4, self.device)
        expected_weights = deepcopy(self.model.state_dict())
        expected_rng = rng_state()
        configure(73, cuda=False)
        resumed = MTBiCLLearner()
        optimizer = make_optimizer(resumed)
        payload = load_checkpoint(self.directory, record, content_hash(self.identity))
        resumed.load_state_dict(payload["model"])
        optimizer.load_state_dict(payload["optimizer"])
        restore_rng(payload["rng"])
        actual_loss = optimizer_step(resumed, optimizer, self.data, 4, self.device)
        self.assertEqual(expected_loss, actual_loss)
        self.assertTrue(all(torch.equal(v, resumed.state_dict()[k]) for k, v in expected_weights.items()))
        self.assertTrue(torch.equal(expected_rng["torch"], rng_state()["torch"]))

    def test_corrupt_byte_and_wrong_identity_rejected(self) -> None:
        path = self.directory/"checkpoint.pt"
        record = save_checkpoint(path, self.payload())
        with self.assertRaises(ValueError):
            load_checkpoint(self.directory, record, "wrong")
        path.write_bytes(path.read_bytes()+b"corrupt")
        with self.assertRaises(ValueError):
            load_checkpoint(self.directory, record, content_hash(self.identity))

    def test_wrong_step_seed_batch_and_escape_path_rejected(self) -> None:
        record = save_checkpoint(self.directory/"checkpoint.pt", self.payload())
        for key, value in (("step", 2), ("seed", 42), ("physical_batch", 2), ("file", "../checkpoint.pt")):
            with self.assertRaises(ValueError):
                load_checkpoint(self.directory, {**record, key: value}, content_hash(self.identity))

    def test_atomic_write_failure_keeps_previous_file(self) -> None:
        path = self.directory/"checkpoint.pt"
        record = save_checkpoint(path, self.payload())
        with patch("core.mt_bicl_training_io.os.replace", side_effect=OSError("fixture I/O")):
            with self.assertRaises(OSError):
                save_checkpoint(path, self.payload(2), replace=True)
        self.assertEqual(load_checkpoint(self.directory, record, content_hash(self.identity))["step"], 1)
        self.assertEqual(list(self.directory.glob("*.tmp")), [])

    def test_immutable_checkpoint_cannot_overwrite(self) -> None:
        path = self.directory/"checkpoint.pt"
        save_checkpoint(path, self.payload())
        with self.assertRaises(ValueError):
            save_checkpoint(path, self.payload(2))

    def test_resume_pointer_transaction_failure_keeps_old_checkpoint(self) -> None:
        with RunBudget(self.directory, self.identity) as budget:
            save_resume(budget, self.model, self.optimizer, 17, 0, 4)
            previous = deepcopy(budget.state["seeds"]["17"]["resume"])
            with patch.object(budget, "save", side_effect=OSError("fixture manifest")):
                with self.assertRaises(OSError):
                    save_resume(budget, self.model, self.optimizer, 17, 1, 4)
            on_disk = read_manifest(self.directory/"state.json")
            self.assertEqual(on_disk["seeds"]["17"]["resume"], previous)
            self.assertEqual(load_checkpoint(self.directory, previous, content_hash(self.identity))["step"], 0)

    def test_budget_shared_and_exhaustion_is_persistent(self) -> None:
        with RunBudget(self.directory, self.identity) as budget:
            budget.state["elapsed_seconds"] = 43200.
            with self.assertRaises(RuntimeError):
                budget.check()
        with RunBudget(self.directory, self.identity) as resumed:
            self.assertEqual(resumed.state["status"], "INCOMPLETE_NO_CANDIDATE")
            with self.assertRaises(RuntimeError):
                resumed.check()

    def test_unclean_session_is_charged_not_reset(self) -> None:
        budget = RunBudget(self.directory, self.identity)
        budget.state.update(elapsed_seconds=100., active_since=(datetime.now(timezone.utc)-timedelta(seconds=5)).isoformat())
        budget.save()
        with RunBudget(self.directory, self.identity) as resumed:
            self.assertGreaterEqual(resumed.used(), 105.)
        self.assertIsNone(read_manifest(self.directory/"state.json")["active_since"])

    def test_identity_change_and_bad_manifest_rejected(self) -> None:
        with RunBudget(self.directory, self.identity):
            pass
        with self.assertRaises(ValueError):
            RunBudget(self.directory, {**self.identity, "test": "changed"})
        path = self.directory/"state.json"
        path.write_text('{"payload":{},"sha256":"wrong"}', encoding="utf-8")
        with self.assertRaises(ValueError):
            read_manifest(path)

    def test_forecast_cap_and_calendar_gate(self) -> None:
        with RunBudget(self.directory, self.identity) as budget:
            with self.assertRaises(RuntimeError):
                budget.check(forecast_seconds=43200)

    def test_incomplete_run_cannot_seal(self) -> None:
        budget = RunBudget(self.directory, self.identity)
        budget.state["preflight"] = {"status": "PASS", "steps": 100}
        budget.save()
        write_manifest(self.directory/"preflight.json", budget.state["preflight"])
        with self.assertRaises(ValueError):
            verify_training(self.directory, self.identity, allow_unsealed=True)

    def test_macro_metrics_equal_symbols_not_query_counts(self) -> None:
        rows = [{"episode_id": f"{s}-{i}", "symbol": s, "p": p, "y": 1}
                for s, p, count in (("FPT", .9, 10), ("MWG", .5, 1), ("VCB", .5, 1), ("VNM", .5, 1))
                for i in range(count)]
        metrics = selection_metrics(rows)
        self.assertAlmostEqual(metrics["macro_brier"], (.01+.25*3)/4, delta=1e-12)
        self.assertNotAlmostEqual(metrics["macro_brier"], (.01*10+.25*3)/13)

    def test_train_pause_resume_keeps_next_episode_index(self) -> None:
        gpu = {"test": "cpu_fixture"}
        report = {"status": "PASS", "gpu": gpu, "physical_batch": 128}
        rows = [{"domain": domain, "packed": self.data[0]} for _ in range(64) for domain in ("synthetic", "market")]
        from unittest.mock import Mock
        source = Mock()
        source.batch.return_value = rows
        with RunBudget(self.directory, self.identity) as budget:
            budget.state["preflight"] = report
            write_manifest(self.directory/"preflight.json", report)
            with patch("core.mt_bicl_trainer.gpu_identity", return_value=gpu), \
                    patch("core.mt_bicl_trainer.configure", return_value=self.device), \
                    patch("core.mt_bicl_trainer.optimizer_step", return_value=.5):
                self.assertFalse(train_seed(budget, source, [], 17, resume=False, stop=lambda: True))
                self.assertEqual(source.batch.call_args.args, (0,))
                self.assertEqual(budget.state["seeds"]["17"]["resume"]["step"], 1)
                self.assertFalse(train_seed(budget, source, [], 17, resume=True, stop=lambda: True))
                self.assertEqual(source.batch.call_args.args, (1,))
                self.assertEqual(budget.state["seeds"]["17"]["resume"]["step"], 2)

    def test_seed_order_and_missing_preflight_block_training(self) -> None:
        gpu = {"test": "cpu_fixture"}
        with RunBudget(self.directory, self.identity) as budget:
            with self.assertRaises(ValueError):
                train_seed(budget, None, [], 17, resume=False, stop=lambda: False)
            budget.state["preflight"] = {"status": "PASS", "gpu": gpu, "physical_batch": 128}
            write_manifest(self.directory/"preflight.json", budget.state["preflight"])
            with patch("core.mt_bicl_trainer.gpu_identity", return_value=gpu):
                with self.assertRaises(ValueError):
                    train_seed(budget, None, [], 42, resume=False, stop=lambda: False)

    def test_full_step_schedule_and_milestones_without_real_training(self) -> None:
        # Mock optimizer/source để kiểm đủ state machine ba seed và seal trên fixture CPU.
        from unittest.mock import Mock
        gpu = {"test": "cpu_fixture"}
        report = {"status": "PASS", "gpu": gpu, "physical_batch": 128, "effective_batch": 128,
                  "accumulation": 1, "identity_sha256": content_hash(self.identity),
                  "steps": 100, "step_seconds": [.001]*100, "weights_retained": False}
        batch = [{"domain": domain, "packed": self.data[0]} for _ in range(64) for domain in ("synthetic", "market")]
        rows = [{"packed": p, "query": {"episode_id": f"{s}-{i}", "symbol": s},
                 "supervised_target": {"y": p["external_loss_labels"][-1]}}
                for i, (s, p) in enumerate(zip(("FPT", "MWG", "VCB", "VNM"), self.data))]
        source = Mock()
        source.batch.return_value = batch
        with RunBudget(self.directory, self.identity) as budget:
            budget.state["preflight"] = report
            write_manifest(self.directory/"preflight.json", report)
            with patch("core.mt_bicl_trainer.gpu_identity", return_value=gpu), \
                    patch("core.mt_bicl_trainer.configure", return_value=self.device), \
                    patch("core.mt_bicl_trainer.optimizer_step", return_value=.5) as update, \
                    patch("builtins.print"):
                for seed in (17, 42, 73):
                    self.assertTrue(train_seed(budget, source, rows, seed, resume=False, stop=lambda: False))
            state = budget.state["seeds"]["17"]
            self.assertEqual(update.call_count, 30000)
            self.assertEqual([c.args[0] for c in source.batch.call_args_list], list(range(10000))*3)
            self.assertEqual(state["status"], "COMPLETE")
            self.assertEqual([r["step"] for r in state["checkpoints"]], list(range(1000, 10001, 1000)))
            latest = load_checkpoint(self.directory, state["resume"], content_hash(self.identity))
            milestone = load_checkpoint(self.directory, state["checkpoints"][-1], content_hash(self.identity))
            self.assertTrue(_same_tree(latest, milestone))
            # Tự sửa dự báo rồi rehash mọi JSON vẫn phải bị replay weights bắt được trước seal.
            record = state["checkpoints"][0]
            original_record = deepcopy(record)
            path = self.directory/record["selection_file"]
            original = read_manifest(path)
            changed = deepcopy(original)
            changed["records"][0]["p"] = .123
            changed["metrics"] = selection_metrics(changed["records"])
            write_manifest(path, changed)
            record.update(metrics=changed["metrics"], selection_sha256=file_hash(path))
            budget.save()
            with patch("core.mt_bicl_trainer.gpu_identity", return_value=gpu), \
                    patch("core.mt_bicl_trainer.configure", return_value=self.device), patch("builtins.print"):
                with self.assertRaisesRegex(ValueError, "replay weights"):
                    seal_training(budget, rows)
                record.clear()
                record.update(original_record)
                write_manifest(path, original)
                budget.save()
                seal_training(budget, rows)
        summary = verify_training(self.directory, self.identity, rows=rows)
        seal = read_manifest(self.directory/"candidate_v1.json")
        exported = torch.load(self.directory/seal["model"]["file"], map_location="cpu", weights_only=True)
        self.assertNotIn("optimizer", exported)
        self.assertEqual(summary["mechanism_status"], "NOT_RUN")
        self.assertFalse(summary["development_allowed"])

    def test_preflight_oom_fallback_only_and_weights_discarded(self) -> None:
        from unittest.mock import Mock
        batch = [{"domain": domain, "packed": self.data[0]} for _ in range(64) for domain in ("synthetic", "market")]
        source = Mock()
        source.batch.return_value = batch
        rows = [{"packed": p, "query": {"episode_id": f"{s}-{i}", "symbol": s},
                 "supervised_target": {"y": p["external_loss_labels"][-1]}}
                for i, (s, p) in enumerate(zip(("FPT", "MWG", "VCB", "VNM"), self.data))]
        with RunBudget(self.directory, self.identity) as budget:
            with patch("core.mt_bicl_trainer.gpu_identity", return_value={"test": "cpu_fixture"}), \
                    patch("core.mt_bicl_trainer.configure", return_value=self.device), \
                    patch("core.mt_bicl_trainer.optimizer_step", side_effect=[torch.cuda.OutOfMemoryError("fixture"), *([.5]*100)]), \
                    patch("torch.cuda.reset_peak_memory_stats"), patch("torch.cuda.synchronize"), \
                    patch("torch.cuda.max_memory_allocated", return_value=0), patch("torch.cuda.empty_cache"), \
                    patch("builtins.print"):
                self.assertTrue(preflight(budget, source, rows, lambda: False))
            report = budget.state["preflight"]
            self.assertEqual(report["physical_batch"], 64)
            self.assertEqual(report["accumulation"], 2)
            self.assertEqual(report["steps"], 100)
            self.assertEqual(report["attempts"][0]["status"], "CUDA_OOM_WEIGHTS_DISCARDED")
            self.assertFalse(report["weights_retained"])
            self.assertEqual(list(self.directory.rglob("*.pt")), [])


if __name__ == "__main__":
    unittest.main()
