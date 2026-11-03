"""Kiểm guard và reuse raw Pattern cho chart rerun, không gọi provider."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from langchain_core.messages import messages_from_dict
from core.revision72_run import CachedLLM, checked, signed
from core.revision_common_study import write_json
from core.revision_call_archive import StudyStop
import scripts.run_chart_rerun as runner


class ChartRerunTests(unittest.TestCase):
    """Không dùng response cũ như lời gọi mới; cache miss không được gọi Pattern API."""

    def test_pattern_cache_miss_stops_before_client_creation(self) -> None:
        llm = object.__new__(runner.PatternCacheOnly)
        llm.kwargs = {"metadata": {"langgraph_node": "Pattern Agent"}}
        with self.assertRaises(StudyStop):
            llm.invoke("missing")

    def test_exact_archived_pattern_request_replays_without_sdk(self) -> None:
        request = next(p for p in sorted(runner.OLD.glob("shards/org*/calls/*.request.json"))
                       if checked(p)["context"].get("node") == "Pattern Agent" and p.with_name(p.name.replace(".request.", ".response.")).exists())
        value = checked(request)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "calls").mkdir()
            for suffix in ("request", "response", "response_digest"):
                source = request.with_name(request.name.replace(".request.", "." + suffix + "."))
                if source.exists(): shutil.copy2(source, root / "calls" / source.name)
            archive = SimpleNamespace(directory=root, context=deepcopy(value["context"]), ids=[])
            no_network = object.__new__(runner.PatternCacheOnly)
            no_network.kwargs = {"metadata": {"langgraph_node": "Pattern Agent"}}
            result = CachedLLM(no_network, archive).invoke(messages_from_dict(value["messages"][0]))
            self.assertTrue(result.content)
            self.assertEqual(len(archive.ids), 1)

    def test_preparation_rejects_changed_sources_and_raw_copies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); run = root / "run"; run.mkdir()
            source = root / "source.txt"; source.write_bytes(b"source")
            raw = run / "raw.json"; raw.write_bytes(b"raw")
            identity = signed({"test": 1}); write_json(run / "run_manifest.json", identity, True)
            preparation = signed({"run_signature": identity["sha256"], "sources": [{"path": "source.txt", "sha256": runner.sha(source)}],
                                  "copies": [{"path": "raw.json", "sha256": runner.sha(raw)}]})
            write_json(run / "chart_rerun_preparation.json", preparation, True)
            with patch.object(runner, "ROOT", root), patch.object(runner, "RUN", run):
                runner.verify_preparation()
                source.write_bytes(b"tamper")
                with self.assertRaises(ValueError): runner.verify_preparation()
                source.write_bytes(b"source"); raw.write_bytes(b"tamper")
                with self.assertRaises(ValueError): runner.verify_preparation()

    def test_ledger_bootstrap_rejects_unlisted_new_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory); calls = run / "shards/org1/calls"; calls.mkdir(parents=True)
            (calls / "new.request.json").write_bytes(b"new")
            with patch.object(runner, "RUN", run):
                with self.assertRaisesRegex(ValueError, "đã có request mới"):
                    runner.initialize_reuse_ledger({"run_signature": "test", "copies": []})


if __name__ == "__main__":
    unittest.main()
