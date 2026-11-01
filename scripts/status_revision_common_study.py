"""Xem tiến độ thực tế của study R1; không gọi inference hoặc suy metric từ run dở."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def main() -> None:
    """Chỉ đọc số checkpoint/attempt; không in key, raw prompts hoặc chi tiết tài khoản."""
    root = Path(__file__).resolve().parents[1]
    run = root / "outputs/revision/r1_common_run_v2"
    bank = root / "outputs/revision/r1_common_bank_v2"
    def read(path: Path) -> dict:
        return json.loads(path.read_bytes()) if path.exists() else {}
    manifest = read(bank / "manifest.json")
    usage = read(run / "usage.json")
    worker = read(run / "worker_status.json")
    units = Counter()
    for path in (run / "units").glob("*.json"):
        context = read(path)["context"]
        units[context["role"] + "/" + context["kind"]] += 1
    print(json.dumps({"bank_id": manifest.get("bank_id"), "worker_phase": worker.get("phase"),
        "worker_process_id": worker.get("process_id"), "worker_log": worker.get("log"),
        "attempted_requests": usage.get("attempted_requests", 0),
        "max_requests_active_command": usage.get("max_requests_current_command"),
        "max_requests_queued": worker.get("max_requests"),
        "checkpoint_counts": dict(units), "n_decisions_saved": sum(units.values()),
        "n_decisions_required": manifest.get("n_calibration", 0) + manifest.get("n_test", 0) * (
            manifest.get("protocol", {}).get("end_to_end_repeats", 0) +
            manifest.get("protocol", {}).get("decision_only_repeats", 0) - 1),
        "inference_complete": (run / "inference_complete.json").exists(),
        "analysis_complete": (root / "outputs/revision/r1_common_analysis_v2/manifest.json").exists(),
        "scope": "live counts only; not receipt verification or scientific acceptance"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
