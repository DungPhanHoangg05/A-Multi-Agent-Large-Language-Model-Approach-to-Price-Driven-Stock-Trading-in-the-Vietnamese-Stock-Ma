"""Renderer U-BICL giới hạn 600 ký tự, projection độc lập stats/examples."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.historical_signals import digest
from core.price_feature_index import _json_bytes

VERSION = "unified_bic_prefix_v1"
BRANCHES = ("U_full", "U_stats", "U_examples")
SIGNS = {"BULLISH": "+", "BEARISH": "-", "NEUTRAL": "0"}
UNCERTAINTY = "Lịch sử; không P(query)/E(return); SHORT=CASH."
TASK_LEGEND = "T=task,E=cycle; n=support,s=số LONG ròng>0; T/P:+ tăng,- giảm,0 trung tính; y=% ròng."
EPISODE_LEGEND = "E=cycle; T/P:+ tăng,- giảm,0 trung tính; y=% LONG ròng lịch sử."


def check_budget(prefix: str, prompt: str) -> None:
    """Đếm Unicode code point: nhận đúng 600/6499, từ chối 601/6500."""
    if type(prefix) is not str or type(prompt) is not str or len(prefix) > 600 or len(prompt) >= 6500:
        raise ValueError("Ngân sách U-BICL cần BRPP≤600 và prompt<6500 ký tự")


def project_context(evidence: dict[str, Any], branch: str) -> dict[str, Any]:
    """Chiếu whitelist từ base đã kiểm; stats-only không nhận mode, nhóm hoặc ID."""
    _json_bytes(evidence)
    if type(branch) is not str or branch not in BRANCHES:
        raise ValueError("Nhánh renderer U-BICL chưa đăng ký")
    if evidence.get("base_evidence_sha256") != digest({key: value for key, value in evidence.items() if key != "base_evidence_sha256"}):
        raise ValueError("Base evidence chưa có seal hợp lệ")
    stats_ready = branch != "U_examples" and evidence["posterior"]["gate"]["ready"]
    examples_ready = branch != "U_stats" and evidence["selection"]["gate"]["ready"]
    view: dict[str, Any] = {"renderer_version": VERSION, "branch": branch,
        "base_evidence_sha256": evidence["base_evidence_sha256"],
        "query": {key: evidence["query"][key] for key in ("symbol", "as_of_date", "current_regime")},
        "statistics": None, "demonstrations": None, "aliases": {}}
    if stats_ready:
        p = evidence["posterior"]
        view["statistics"] = {"posterior_mean": p["posterior_mean"], "credible_interval": deepcopy(p["credible_interval"]),
            "prior_weight": p["prior_weight"], "counts": deepcopy(evidence["statistics"]["counts"])}
    if examples_ready:
        mode = evidence["context_mode"]
        if mode not in ("task", "episode_fallback") or not 1 <= len(evidence["examples"]) <= 3:
            raise ValueError("Mode/examples khác readiness đã khai")
        rows = []
        for number, example in enumerate(evidence["examples"], 1):
            episode_alias = f"E{number}"
            view["aliases"][episode_alias] = {"kind": "episode", "episode_id": example["episode_id"]}
            row = {"episode_alias": episode_alias, "trend": example["trend"], "pattern": example["pattern"],
                "net_return_pct": example["net_return_pct"]}
            if mode == "task":
                task_alias = f"T{number}"
                group = evidence["task_groups"][example["task_id"]]
                view["aliases"][task_alias] = {"kind": "task", "task_id": example["task_id"],
                    "episode_ids": list(group["episode_ids"])}
                row.update(task_alias=task_alias, n=group["n"], s=group["s"])
            rows.append(row)
        view["demonstrations"] = {"context_mode": mode, "examples": rows}
    return view


def render_context(evidence: dict[str, Any], branch: str) -> dict[str, Any]:
    """Dùng sau verifier semantic; không rút K hoặc cắt legend để vừa ngân sách."""
    view = project_context(evidence, branch)
    stats, examples = view["statistics"], view["demonstrations"]
    lines = []
    if stats is not None or examples is not None:
        lines.append(f"[U-BICL v1] R={view['query']['current_regime']}; Open(t+1)→Close(t+3) theo phiên.")
        if stats is not None:
            c, interval = stats["counts"], stats["credible_interval"]
            lines.append(f"W=LONG ròng>0: {c['sC']}/{c['nC']}; Beta mean={stats['posterior_mean']:.3f}; "
                f"CrI95% plug-in=[{interval['lower']:.3f},{interval['upper']:.3f}]; "
                f"nC/n1/n2={c['nC']}/{c['n1']}/{c['n2']}; w0={stats['prior_weight']:.3f}.")
        if examples is not None:
            mode = examples["context_mode"]
            lines.append(("mode=task; " + TASK_LEGEND) if mode == "task" else
                         "mode=episode_fallback (không phải multi-task); " + EPISODE_LEGEND)
            for example in examples["examples"]:
                value = example["net_return_pct"]
                percent = f"{value:.2f}" if abs(value) < 1000 else f"{value:.3g}"
                line = f"{example['episode_alias']} T/P={SIGNS[example['trend']]}/{SIGNS[example['pattern']]}→{percent}%"
                if mode == "task":
                    line = f"{example['task_alias']} n={example['n']},s/n={example['s']}/{example['n']}; " + line
                lines.append(line)
        lines.append(UNCERTAINTY)
    prefix = "\n".join(lines)
    check_budget(prefix, "")
    return {**view, "prefix": prefix, "prefix_sha256": digest(prefix), "prefix_chars": len(prefix)}


def assemble_prompt(base_prompt: str, prefix: str) -> str:
    """Chèn block nguyên vẹn trước report đầu; instruction chung do U10-06 cấp."""
    check_budget(prefix, base_prompt)
    if not prefix:
        return base_prompt
    head, marker, tail = base_prompt.partition("### [1]")
    if not marker or any(tag in base_prompt for tag in ("[U-BICL", "[BRPP")):
        raise ValueError("Prompt thiếu vị trí chèn hoặc đã có prior")
    prompt = head + prefix + "\n\n" + marker + tail
    check_budget(prefix, prompt)
    return prompt
