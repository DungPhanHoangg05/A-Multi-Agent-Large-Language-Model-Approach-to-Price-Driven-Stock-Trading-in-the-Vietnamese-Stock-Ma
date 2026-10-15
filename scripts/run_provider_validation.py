"""Tiếp tục development với quota ngày từ Groq và amendment vận hành riêng."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.groq_pacing import PilotStop
from core.prior_backtest import canonical_hash
from core.prior_run_lock import PriorRunLock
from core.provider_quota import AMENDMENT_FILE, ProviderQuotaPacer, prepare_amendment, rejected_attempts, verify_amendment
from core.research_cohort import read_envelope
from core.research_invocation import ENABLED, invocation_scope
from scripts import run_bayesian_ablation as legacy


def execute(arguments: list[str]) -> None:
    """Adapter factory có audit; không đổi hash, source hoặc thuật toán của runner đã khóa."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-amendment", action="store_true")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, default=ROOT / "outputs/oos_pilot/api_usage.json")
    args, _ = parser.parse_known_args(arguments)
    plan_path, run, ledger_path = args.plan.resolve(), args.output_dir.resolve(), args.ledger.resolve()
    if (not plan_path.is_relative_to(ROOT) or not run.is_relative_to(ROOT)
            or ledger_path != ROOT / "outputs/oos_pilot/api_usage.json" or plan_path.name.startswith(".env")):
        raise ValueError("Entrypoint cần plan/run trong workspace và ledger chung đã khóa")
    modes = {token.split("=", 1)[0] for token in arguments if token.startswith("--")}
    allowed = {"--prepare-amendment", "--plan", "--output-dir", "--ledger", "--quota-policy", "--env-file",
               "--dry-run", "--preflight", "--run", "--resume", "--symbol", "--verify-only", "--verify-report",
               "--reconcile", "--authorize-replay", "--replay-reason", "--select-candidate", "--verify-selection",
               "--technical-gates", "--selection-output"}
    if not modes <= allowed:
        raise ValueError("Entrypoint chỉ nối development; không nhận prepare hoặc holdout")
    online = bool(modes & {"--run", "--preflight"})
    if args.prepare_amendment:
        if modes - {"--prepare-amendment", "--plan", "--output-dir", "--ledger", "--quota-policy"}:
            raise ValueError("Prepare amendment chỉ chạy offline, không kèm lệnh khác")
        _legacy_main(["--verify-only", "--plan", str(plan_path), "--output-dir", str(run),
                      "--ledger", str(ledger_path), "--quota-policy", "request_admission_v2"])
        # Dùng đúng thứ tự khóa ledger rồi run như runner; metadata owner vẫn cùng signature.
        signature = canonical_hash(read_envelope(run / "cohort.json"))
        with PriorRunLock(ledger_path.parent / (ledger_path.name + ".lock"), "shared-account-ledger-v2"):
            with PriorRunLock(run, signature):
                prepare_amendment(ROOT, plan_path, run, ledger_path)
        print(f"Amendment quota provider đã khóa tại {run / AMENDMENT_FILE}; chưa đọc key hoặc gọi API")
        return
    verify_amendment(ROOT, plan_path, run, ledger_path)
    checksum = hashlib.sha256((run / AMENDMENT_FILE).read_bytes()).hexdigest()
    plan = read_envelope(plan_path)
    if "--run" in modes:
        for attempt in rejected_attempts(run, ledger_path):
            print(f"Đối soát attempt quota bị từ chối {attempt}; cho replay đúng UUID, giữ nguyên lịch sử.", flush=True)
            _legacy_main(["--reconcile", "--plan", str(plan_path), "--output-dir", str(run), "--ledger", str(ledger_path),
                "--quota-policy", "request_admission_v2", "--authorize-replay", attempt,
                "--replay-reason", "Amendment provider_daily_quota_v1: đối soát ledger chứng minh quota từ chối, chưa có response thành công."])
    original_pacer, original_env, original_builder = legacy.GroqPacer, legacy.dotenv_values, legacy.make_builder
    captured: dict[str, Any] = {}

    def env_values(*values: Any, **options: Any) -> Any:
        """Chỉ nhận key sau khi CLI gốc đã verify plan; không log hoặc lưu key."""
        result = original_env(*values, **options)
        captured["credential"] = result.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY", "")
        return result

    def pacer_factory(path: Path, **options: Any) -> Any:
        """Offline giữ verifier gốc; online thay riêng factory quota đã ghi amendment."""
        # Constructor được CLI gọi khi đang giữ khóa ledger; kiểm lại để tránh race cutover.
        verify_amendment(ROOT, plan_path, run, ledger_path)
        if not online:
            return original_pacer(path, **options)
        pacer = ProviderQuotaPacer(path, credential=captured.get("credential", ""), amendment_sha256=checksum, **options)
        captured["pacer"] = pacer
        return pacer

    def builder_factory(inputs: dict[str, Any], key: str, client: Any) -> Any:
        """Key mới tự preflight đúng plan trước resume; proof/usage cùng ledger và budget gốc."""
        builder = original_builder(inputs, key, client)
        pacer = captured.get("pacer")
        if "--run" in modes and pacer is not None:
            proof = pacer.state.get("preflight", {})
            if proof.get("credential_scope") != pacer.credential_scope or proof.get("plan_sha256") != canonical_hash(plan):
                print("Key hiện tại chưa có preflight đúng plan; kiểm tra text/vision trước khi resume.", flush=True)
                token = ENABLED.set(True)
                try:
                    first = len(pacer.state["requests"])
                    with invocation_scope("preflight"):
                        legacy.preflight(builder)
                    pacer.state["preflight"] = {"status": "PASS", "plan_sha256": canonical_hash(plan),
                        "request_ids": [row["id"] for row in pacer.state["requests"][first:]]}
                    pacer.save()
                finally:
                    ENABLED.reset(token)
        return builder

    try:
        legacy.GroqPacer, legacy.dotenv_values, legacy.make_builder = pacer_factory, env_values, builder_factory
        _legacy_main(arguments)
    finally:
        legacy.GroqPacer, legacy.dotenv_values, legacy.make_builder = original_pacer, original_env, original_builder


def _legacy_main(arguments: list[str]) -> None:
    """Ủy quyền parser/plan/checkpoint gốc; luôn khôi phục argv khi kết thúc hoặc lỗi."""
    previous = sys.argv
    try:
        sys.argv = [str(ROOT / "scripts/run_bayesian_ablation.py"), *arguments]
        legacy.main()
    finally:
        sys.argv = previous


if __name__ == "__main__":
    try:
        execute(sys.argv[1:])
    except PilotStop as error:
        print(f"Validation dừng có kiểm soát: {error}", flush=True)
        sys.exit(2)
    except KeyboardInterrupt:
        print("Đã ngắt validation; giữ checkpoint và kiểm verify/reconcile trước resume.", flush=True)
        sys.exit(130)
