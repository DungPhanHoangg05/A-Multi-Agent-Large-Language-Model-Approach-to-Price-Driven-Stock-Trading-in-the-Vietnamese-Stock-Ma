"""Freeze R4 từ corrected upstream thật; dựng prompt native nhưng không gọi model."""

from __future__ import annotations

import contextlib
from copy import deepcopy
import io
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agents.decision_agent import create_final_trade_decider
from core.revision72_run import checked, freeze, variant_state
from core.revision_r4_factorial import VARIANTS, controlled_prompt, prompt_parts
from core.revision_common_study import digest
from core.revision_r4_run import prepare, verify_bank
from scripts.run_chart_rerun import BANK, RUN, R4_BANK, sha, verify_preparation


class PromptCaptured(BaseException):
    """Thoát trước SDK/retry; không trả về prediction giả."""


def native_prompt(state: dict) -> str:
    """Lấy đúng prompt trước invoke của Decision native, không sinh LLM result."""
    prompts: list[str] = []

    class Capture:
        """Interface tối thiểu dừng tại ranh giới invoke."""
        def invoke(self, prompt: str) -> None:
            prompts.append(prompt)
            raise PromptCaptured()

    with contextlib.redirect_stdout(io.StringIO()):
        try:
            create_final_trade_decider(Capture())(state)
        except PromptCaptured:
            pass
    if len(prompts) != 1 or len(prompts[0]) >= 6500:
        raise ValueError("Native prompt thiếu hoặc vượt cap trước API")
    return prompts[0]


def prepare_from_nodes() -> None:
    """Không phụ thuộc outcome/Decision AS; chỉ đọc ba reports actual đã checkpoint."""
    verify_preparation(); identity = freeze(ROOT, BANK, RUN)
    if R4_BANK.exists():
        verify_bank(ROOT, R4_BANK); print("Corrected R4 bank vẫn khớp."); return
    old_path = ROOT / "outputs/revision/r4_value_bank_v1/manifest.json"
    old = checked(old_path); sources = [old_path, Path(__file__), ROOT / "tests/test_prepare_chart_r4.py",
                                       RUN / "run_manifest.json", RUN / "chart_rerun_preparation.json"]
    units, matched_decisions = [], 0
    for original in old["units"]:
        unit = original["unit"]; key = unit["id"]
        shared = {"stock_name": unit["symbol"], "time_frame": "1 ngày", "language": "vi", "is_backtest": True}
        hashes = []
        for node, field in (("Indicator", "indicator_report"), ("Pattern", "pattern_report"), ("Trend", "trend_report")):
            matches = list(RUN.glob(f"shards/org*/nodes/{key}_r0_{node}.json"))
            if len(matches) != 1:
                raise ValueError("Thiếu corrected node trước R4: " + key + "/" + node)
            path = matches[0]; value = checked(path)
            if value["context"]["unit_id"] != key or value["context"]["realization"] != 0 or value["parent"]["run_signature"] != identity["sha256"] or value["parent"]["asset_hash"] != original["asset_hash"]:
                raise ValueError("Node sai unit/source/parent")
            for call in value["call_hashes"]:
                raw = path.parent.parent / call["path"]
                if sha(raw) != call["sha256"]: raise ValueError("Raw node đã đổi")
                sources.append(raw)
            shared[field] = value["state"][field]; hashes.append(value["sha256"]); sources.append(path)
        asset_path = BANK / f"features/{unit['symbol']}_{unit['decision']}.json"
        donor_path = BANK / f"features/{unit['symbol']}_{original['donor_index']}.json"
        asset, donor = checked(asset_path), checked(donor_path)
        if (asset["sha256"], donor["sha256"]) != (original["asset_hash"], original["donor_hash"]):
            raise ValueError("Asset/donor gốc bị đổi")
        prompt = native_prompt(variant_state(shared, asset, donor, "AS"))
        for path in RUN.glob(f"shards/org*/decisions/{key}_r0_AS_n0.json"):
            if checked(path)["state"]["decision_prompt"] != prompt:
                raise ValueError("Prompt dựng offline khác actual AS prompt")
            matched_decisions += 1
        row = deepcopy(original)
        row["prompts"] = {v: controlled_prompt(prompt_parts(prompt), asset, donor, v) for v in VARIANTS}
        row["prompt_hashes"] = {v: digest(t) for v, t in row["prompts"].items()}
        row["upstream_parent_hash"] = digest({"run_signature": identity["sha256"], "node_hashes": hashes})
        row["original_request_id"] = None
        row["source_prompt_kind"] = "native builder from actual corrected reports, not a completed AS response"
        units.append(row); sources += [asset_path, donor_path]
    prepare(ROOT, R4_BANK, units, sources)
    print(f"Đối soát {matched_decisions} actual AS prompts có sẵn; 90 R4 prompts/270 jobs đã freeze offline.")


if __name__ == "__main__":
    prepare_from_nodes()
