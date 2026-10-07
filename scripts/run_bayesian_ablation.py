"""CLI pilot FPT 20 điểm, năm nhánh; không gọi API ở chế độ kiểm tra offline."""

from __future__ import annotations

import argparse
import base64
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from dotenv import dotenv_values
from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq
from PIL import Image

from core.backtest_engine import BacktestEngine
from core.groq_pacing import GroqPacer, PacedGroqTransport, PilotStop
from core.pilot_readiness import INPUT_DIR, build_adapter, prepare_inputs, verify_inputs
from core.prior_backtest import PriorBacktestRunner, canonical_hash
from core.prior_run_lock import PriorRunLock
from utils.graph_setup import SetGraph
from utils.graph_util import TechnicalTools


def make_builder(plan: dict[str, Any], key: str, client: httpx.Client) -> SetGraph:
    """Dùng client ChatGroq thật; transport chung bắt cả structured và fallback."""
    models = plan["signal_config"]["models"]
    def model(role: str) -> ChatGroq:
        llm = ChatGroq(model=models[f"{role}_llm_model"], temperature=models[f"{role}_llm_temperature"],
            max_tokens=models[f"{role}_llm_max_tokens"], api_key=key, max_retries=0,
            http_client=client, **plan["client_options"][role])
        # LangChain tự đổi 0 thành 1e-8 trong constructor; khôi phục đúng giá trị
        # đã khóa trước mọi request và trước validator nghiên cứu.
        llm.temperature = models[f"{role}_llm_temperature"]
        return llm
    return SetGraph(model("agent"), model("graph"), TechnicalTools())


def preflight(builder: SetGraph) -> None:
    """Hai request nhỏ kiểm text/vision thực; không đọc/gọi upstream các cutoff."""
    from utils.historical_api import _invoke_with_retry
    text = _invoke_with_retry(builder.agent_llm.invoke,
        [HumanMessage(content='Return exactly {"ok":true} as JSON, no other text.')], retries=1)
    if json.loads(text.content) != {"ok": True}:
        raise ValueError("Model text không trả JSON hợp lệ khi preflight")
    image = Image.new("RGB", (64, 64), "red")
    stream = BytesIO()
    image.save(stream, format="PNG")
    url = "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")
    response = _invoke_with_retry(builder.graph_llm.invoke, [HumanMessage(content=[
        {"type": "text", "text": 'Return exactly {"color":"red"} if the image is red; JSON only.'},
        {"type": "image_url", "image_url": {"url": url}}])], retries=1)
    if json.loads(response.content) != {"color": "red"}:
        raise ValueError("Model vision không nhận đúng ảnh ở preflight")
    print("Preflight text/vision PASS; usage và quota headers đã lưu an toàn", flush=True)


def main() -> None:
    """Mặc định dry-run; chỉ --run/--preflight mới tạo lời gọi LLM có quota."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare", action="store_true", help="Khóa nguồn/model/20 cutoff một lần, không LLM")
    mode.add_argument("--dry-run", action="store_true", help="Xác minh toàn input/plan, không LLM")
    mode.add_argument("--preflight", action="store_true", help="Kiểm text và vision thật qua transport có pacing")
    mode.add_argument("--run", action="store_true", help="Chạy pilot sau preflight thành công")
    mode.add_argument("--verify-only", action="store_true", help="Kiểm semantic checkpoint, không LLM")
    parser.add_argument("--resume", action="store_true", help="Phục hồi run năm nhánh, không dùng runner Memory Bank")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/pilot_fpt_run")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    if args.resume and not (args.run or args.verify_only):
        parser.error("--resume chỉ đi với --run hoặc --verify-only")
    plan = prepare_inputs() if args.prepare else verify_inputs()
    adapter = build_adapter(plan)
    contexts = [adapter.prepare("FPT", cutoff) for cutoff in plan["cutoffs"]]
    print(f"Input PASS: FPT {len(contexts)} cutoff, {plan['cutoffs'][0]} → {plan['cutoffs'][-1]}; "
          f"plan={canonical_hash(plan)}", flush=True)
    if args.prepare or not (args.preflight or args.run or args.verify_only):
        return
    config = plan["signal_config"]
    # Chế độ verify-only dùng client có transport cấm mạng và không đọc key.
    key = "offline-verifier-no-network"
    if not args.verify_only:
        key = dotenv_values(args.env_file).get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY", "")
        if not key:
            raise ValueError("Thiếu GROQ_API_KEY; đặt riêng trong .env")
    pacer = GroqPacer(ROOT / "outputs/oos_pilot/api_usage.json")
    def reject_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError("verify-only không được phép gọi API")
    transport = httpx.MockTransport(reject_network) if args.verify_only else PacedGroqTransport(pacer)
    # Khóa cả quota ledger để không có hai run-dir dùng chung quota sai số.
    with PriorRunLock(ROOT / "outputs/oos_pilot/runtime", canonical_hash(plan)), httpx.Client(transport=transport, timeout=90.) as client:
        builder = make_builder(plan, key, client)
        if args.preflight:
            first = len(pacer.state["requests"])
            preflight(builder)
            pacer.state["preflight"] = {"status": "PASS", "plan_sha256": canonical_hash(plan),
                "request_ids": [r["id"] for r in pacer.state["requests"][first:]]}
            pacer.save()
            return
        if args.run:
            proof = pacer.state.get("preflight", {})
            successful = {r["model"] for r in pacer.state["requests"]
                if r["id"] in proof.get("request_ids", []) and r["status"] == 200}
            if (proof.get("status") != "PASS" or proof.get("plan_sha256") != canonical_hash(plan)
                    or successful != set(plan["limits"])):
                raise ValueError("Cần --preflight PASS cho cả text và vision trước pilot")
        engine = BacktestEngine({**config["models"], "language": config["language"],
            "alpha_norm_method": config["norm_method"], "alpha_weights": config["alpha_weights"]})
        runner = PriorBacktestRunner(engine, adapter, builder, extra_source_paths=(f"{INPUT_DIR}/plan.json",),
                                     before_point=pacer.before_point)
        def progress(event: dict[str, Any]) -> None:
            print(f"Pilot: {event['completed']}/{event['total']} điểm đủ năm nhánh", flush=True)
        result = runner.run("FPT", output_dir=args.output_dir, cutoffs=tuple(plan["cutoffs"]), step=3,
                            resume=args.resume, verify_only=args.verify_only, callback=progress)
        print(f"Pilot {result['status']}: {len(result['completed_point_ids'])}/{len(result['planned_point_ids'])} điểm", flush=True)


if __name__ == "__main__":
    try:
        main()
    except PilotStop as error:
        print(f"Pilot dừng có kiểm soát: {error}", flush=True)
        sys.exit(2)
    except KeyboardInterrupt:
        print("Đã ngắt pilot; giữ checkpoint, kiểm --verify-only trước --run --resume", flush=True)
        sys.exit(130)
