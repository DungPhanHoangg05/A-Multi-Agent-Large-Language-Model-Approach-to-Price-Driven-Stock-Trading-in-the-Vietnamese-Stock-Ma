"""Tạo episode từ dữ liệu offline 2018–2022; tiếp tục từ journal, không chạy lại upstream."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from core.historical_runner import HistoricalMemoryRunner
from core.historical_signals import HistoricalSignalExtractor
from default_config import DEFAULT_CONFIG


def create_extractor(runner: HistoricalMemoryRunner) -> HistoricalSignalExtractor:
    """Tạo hai LLM Groq đúng cấu hình đã ghi; chỉ dùng giá/cache tin offline."""
    from dotenv import load_dotenv
    from langchain_groq import ChatGroq
    from utils.graph_setup import SetGraph
    from utils.graph_util import TechnicalTools
    from utils.historical_api import RetryingLLM

    load_dotenv(ROOT / ".env", override=False)
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("Cần cấu hình GROQ_API_KEY để tạo tín hiệu LLM; plan/verify không cần API key")

    def model(prefix: str) -> RetryingLLM:
        name = runner.model_config[f"{prefix}_llm_model"]
        kwargs = {"model": name, "temperature": 0.0, "api_key": api_key,
                  "max_tokens": runner.model_config[f"{prefix}_llm_max_tokens"], "max_retries": 0}
        if any(tag in name.lower() for tag in ("qwen3", "gpt-oss", "deepseek", "-r1")):
            kwargs["reasoning_format"] = "hidden"
        return RetryingLLM(ChatGroq(**kwargs))

    return HistoricalSignalExtractor.from_graph_builder(
        SetGraph(model("agent"), model("graph"), TechnicalTools()), runner.output_dir / "signals",
        DEFAULT_CONFIG, execution_loader=runner.execution_data, article_loader=runner.article_loader,
    )


def main() -> None:
    """Plan/verify không gọi API; số điểm mới có thể giới hạn để chia đợt chạy."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/historical_memory_run", help="Thư mục staging và checkpoint")
    parser.add_argument("--symbols", nargs="+", default=["FPT", "VNM", "VCB", "MWG"], help="Các mã nghiên cứu")
    parser.add_argument("--start", default="2018-01-01", help="Ngày quyết định sớm nhất")
    parser.add_argument("--end", default="2022-12-31", help="Ngày tất toán muộn nhất")
    parser.add_argument("--max-new-points", type=int, help="Số điểm mới tối đa trong lần chạy này")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--plan-only", action="store_true", help="Chỉ kiểm lịch và giá; không ghi file, fit hoặc gọi LLM")
    modes.add_argument("--verify-only", action="store_true", help="Kiểm journal/kho đã có; không fit hoặc gọi LLM")
    args = parser.parse_args()
    if args.max_new_points is not None and args.max_new_points < 1:
        parser.error("--max-new-points phải là số nguyên dương")
    random.seed(42)
    import numpy as np
    np.random.seed(42)
    runner = HistoricalMemoryRunner(args.output_dir, symbols=tuple(args.symbols), start=args.start, end=args.end)
    if args.plan_only:
        plan = runner.plan()
        print(json.dumps({"candidate_count": plan["candidate_count"], "eligible_count": plan["eligible_count"],
                          "excluded_count": len(plan["excluded"]), "first_points": plan["points"][:4]},
                         ensure_ascii=False, indent=2))
        return
    if not args.verify_only:
        runner.signal_extractor = create_extractor(runner)
    result = runner.run(max_new_points=args.max_new_points, verify_only=args.verify_only)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
