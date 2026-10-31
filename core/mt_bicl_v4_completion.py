"""Amendment nguồn/coverage và release thu thập W11-18; không đổi protocol nghiên cứu."""

from __future__ import annotations

import ast
from collections import Counter
from copy import deepcopy
import hashlib
import json
import importlib.metadata
from pathlib import Path
from typing import Any

from core.mt_bicl_v4_dataset import coverage as historical_coverage, encoded, immutable
from core.mt_bicl_v4_protocol import canonical, checksum, git, read, safe_path, verify as verify_spec

DIRECTORY = Path("outputs/bayesian_benchmark/mt_bicl_v4/data_completion")
RELEASE = Path("docs/plan/week11/data_completion_release_v4.json")
PARENT = Path("docs/plan/week11/dataset_manifest_v4.json")
OLD_COVERAGE = Path("docs/plan/week11/coverage_v4.json")
BASE = Path("outputs/bayesian_benchmark/mt_bicl_v4/data")
NEW = Path("outputs/bayesian_benchmark/mt_bicl_v4/data_r2")
SOURCES = ("core/mt_bicl_v4_completion.py", "core/mt_bicl_v4_warmup.py",
    "core/mt_bicl_v4_collect_transport.py", "core/mt_bicl_v4_collect.py",
    "scripts/continue_mt_bicl_v4_data.py", "tests/test_mt_bicl_v4_completion.py",
    "tests/test_mt_bicl_v4_collection.py", "tests/test_mt_bicl_v4_collection_leakage.py")
DEPENDENCIES = ("core/mt_bicl_v2_decision.py", "core/mt_bicl_v2_api_preflight.py",
    "core/improvement_recovery.py", "core/improvement_transport.py", "core/research_invocation.py",
    "core/provider_quota.py", "core/groq_pacing.py", "core/prior_stage_journal.py",
    "core/historical_signals.py", "core/execution_prices.py", "core/prior_run_lock.py",
    "core/bayesian_memory.py", "core/research_cohort.py", "core/research_input_lock.py",
    "core/prior_config.py", "utils/graph_setup.py", "utils/graph_util.py", "utils/static_util.py",
    "utils/alpha_selector.py", "agents/indicator_agent.py", "agents/pattern_agent.py",
    "agents/trend_agent.py", "agents/alpha_agent.py", "agents/decision_agent.py",
    "data_manager/sentiment_cache.py", "scripts/verify_execution_price_gate.py")
DEPENDENCIES = (*DEPENDENCIES, "utils/historical_api.py", "utils/i18n.py", "default_config.py",
                "core/alpha_compare.py", "agents/sentiment_agent.py", "scripts/prepare_historical_data.py",
                "core/mt_bicl_v2_development.py", "core/prior_context.py", "core/prior_backtest.py", "core/mt_bicl_context.py",
                "scripts/prepare_groq_tokenizer.py")
OLD_AGENT_COMMITS = {"indicator": "aa44e7eb060ccbaffc1ddda5a87bcb3ec23d93eb",
    "pattern": "db3c6deeff7044d04780cf06f3d5983711676fd9",
    "trend": "db3c6deeff7044d04780cf06f3d5983711676fd9",
    "alpha": "d6bbba955ba90a11f0011e61f0ed01ad69013c09"}


class DataCompletionError(ValueError):
    """Th?ng ?i?p ki?m tra do c?ng c? t? t?o, kh?ng ch?a l?i SDK ho?c credential."""


def corrected_coverage(rows: list[dict[str, Any]], folds: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Coverage agent độc lập numeric; joint coverage vẫn báo rõ, không nới ngưỡng70%."""
    report = historical_coverage(rows, folds, spec)
    by_id = {r["episode_id"]: r for r in rows}

    def replace_counts(stats: dict[str, Any], group: list[dict[str, Any]]) -> None:
        stats["joint_full_input_valid"] = stats["agent_valid"]
        stats["joint_full_input_fraction"] = stats["agent_valid_fraction"]
        agent = sum(r["label_eligible"] and r["agent"]["status"] == "AVAILABLE" for r in group)
        stats["agent_valid"] = int(agent)
        stats["agent_valid_fraction"] = agent / stats["labeled"] if stats["labeled"] else 0.
        stats["verified_agent_sources"] = sum(r["agent"]["source"] is not None for r in group)
        stats["real_legacy_reports"] = sum(bool(r["agent"]["source"]) and
            r["agent"]["source"].get("path", "").startswith("outputs/historical_memory_run/") for r in group)
    replace_counts(report["full_summary"], rows)
    failures = []
    for name, group in report["folds"].items():
        for symbol, item in group.items():
            f = [by_id[i] for i in folds[name]["fit_ids"] if by_id[i]["symbol"] == symbol]
            q = [by_id[i] for i in folds[name]["evaluation_ids"] if by_id[i]["symbol"] == symbol]
            replace_counts(item["fit"], f)
            replace_counts(item["evaluation"], q)
            item["checks"]["fit_agent"] = item["fit"]["agent_valid"] >= item["requirements"]["fit_agent"]
            if "eval_agent_fraction" in item["checks"]:
                item["checks"]["eval_agent_fraction"] = item["evaluation"]["agent_valid_fraction"] >= spec["data"]["minimum_support"]["agent_valid_fraction_each_outer_symbol"]
            failures.extend({"fold": name, "symbol": symbol, "check": key}
                            for key, ok in item["checks"].items() if not ok)
    report.update(version="conditional_mt_bicl_data_coverage_v4_r2", failed_checks=failures,
                  status="INSUFFICIENT_DATA" if failures else "DATA_READY_PASS", ready_for_W11_19=not failures,
                  coverage_definition="AGENT_VALID_OVER_LABEL_ELIGIBLE_INDEPENDENT_OF_NUMERIC;JOINT_FULL_INPUT_REPORTED_SEPARATELY")
    return report


def normalized_agent_tree(source: str) -> str:
    """Chỉ bỏ đúng guard invocation mới và bọc retry của fallback; giữ mọi prompt/parser."""
    class Normalize(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
            node = deepcopy(node)
            if node.name == "_invoke_with_retry":
                expected = ast.parse("from core.research_invocation import CURRENT, invoke_once\nif CURRENT.get() is not None:\n return invoke_once(call_fn, *args)\n").body
                if len(node.body) >= 2 and all(ast.dump(a, include_attributes=False) == ast.dump(b, include_attributes=False)
                                              for a, b in zip(node.body[:2], expected)):
                    node.body = node.body[2:]
            if node.name == "_text_fallback_analysis":
                class Unwrap(ast.NodeTransformer):
                    def visit_Call(self, call: ast.Call) -> ast.AST:
                        self.generic_visit(call)
                        if (isinstance(call.func, ast.Name) and call.func.id == "_invoke_with_retry"
                                and len(call.args) == 2 and not call.keywords
                                and ast.dump(call.args[0]) == ast.dump(ast.parse("tool_llm.invoke", mode="eval").body)):
                            return ast.Call(func=call.args[0], args=call.args[1:], keywords=[])
                        return call
                node = Unwrap().visit(node)
            return node
    return ast.dump(Normalize().visit(ast.parse(source)), include_attributes=False)


def cache_audit(root: Path) -> dict[str, Any]:
    """Audit Git/AST rõ giới hạn: prompt tương đương chưa chứng minh options HTTP cũ."""
    sources = {}
    for role, commit in OLD_AGENT_COMMITS.items():
        name = "agents/" + role + "_agent.py"
        old = git(root, "show", commit + ":" + name).decode("utf-8").replace("\r\n", "\n")
        current = (root / name).read_text(encoding="utf-8")
        equal = normalized_agent_tree(old) == normalized_agent_tree(current)
        sources[name] = {"old_commit": commit, "old_text_sha256": checksum(old.encode()),
                         "current_text_sha256": checksum(current.encode()), "prompt_and_postprocessing_AST_equivalent": equal}
    parent = read((root / PARENT).read_bytes())
    eligible = 0
    for name, sha in parent["agent_input_sha256"].items():
        if "/signals/" not in name:
            continue
        if checksum(safe_path(root, name).read_bytes()) != sha:
            raise DataCompletionError("Cache lịch sử khác snapshot")
        proof = read(safe_path(root, name).read_bytes())["payload"]["result"]["provenance"]
        if all(proof["code_sha256"].get(n) == info["old_text_sha256"] and info["prompt_and_postprocessing_AST_equivalent"]
               for n, info in sources.items()):
            eligible += 1
    return {"version": "conditional_v4_legacy_cache_compatibility", "sources": sources,
        "reports_examined": 852, "reports_prompt_AST_equivalent": eligible,
        "reuse_allowed": False, "reusable_reports": 0,
        "reason": "LEGACY_HTTP_OPTIONS_AND_RAW_REQUEST_RESPONSE_NOT_DURABLE;NO_ORIGINAL_A0",
        "action": "PRESERVE_LEGACY_BYTES_COLLECT_FRESH_WITH_PINNED_CLIENT_OPTIONS"}


def verify_release(root: Path, *, require_git: bool = True) -> dict[str, Any]:
    """Scope chỉ warmup/agent/a0≤2022; không train predictor hoặc mở development2023."""
    verify_spec(root)
    release = read((root / RELEASE).read_bytes())
    if require_git and (root / RELEASE).read_bytes() != git(root, "show", "HEAD:" + RELEASE.as_posix()):
        raise DataCompletionError("Release collection chưa neo Git")
    if (release["version"] != "conditional_v4_data_completion_release" or release["scope"] != "USER_WARMUP_AGENT_ORIGINAL_2018_2022_ONLY"
            or release["training_allowed"] or release["development_allowed"] or release["confirmation_allowed"]):
        raise DataCompletionError("Release collection sai scope")
    if (release["warmup"] != {"start": "2015-01-01", "end": "2018-01-15", "append_only_before": "2018-01-02",
            "minimum_pre_anchor_rows": 579, "source": "VCI_RAW_REST", "overlap": "EVERY_2018_RETURNED_ROW_MUST_MATCH_FROZEN_RAW_WITHIN_1e-8",
            "no_pre2018_labels_or_train_queries": True} or release["hour_cap"] is not None or release["calendar_deadline"] is not None
            or release["config"] != read((root / "docs/plan/week11/protocol_v3.json").read_bytes())["decision"]["config"]):
        raise DataCompletionError("Warmup/runtime/model options khác amendment")
    if any(importlib.metadata.version(n) != v for n, v in release["acquisition_runtime"].items()):
        raise DataCompletionError("Dependency thu thập nguồn đã đổi")
    from core.mt_bicl_v4_http_diagnostics import verify_hotfix
    hotfix = verify_hotfix(root)
    for group in ("source_sha256", "dependency_sha256", "parent_sha256", "news_sha256"):
        for name, expected in release[group].items():
            if group == "source_sha256" and name in hotfix:
                expected = hotfix[name]
            if checksum(safe_path(root, name).read_bytes()) != expected:
                raise DataCompletionError("Nguồn collection đổi: " + name)
    for name in SOURCES:
        historical = git(root, "show", release["source_commit"] + ":" + name)
        if checksum(historical) != release["source_sha256"][name]:
            raise DataCompletionError("Source cha không khớp commit khóa")
        if name not in hotfix and (root / name).read_bytes() != historical:
            raise DataCompletionError("Source collection khác commit khóa")
    parent = read((root / PARENT).read_bytes())
    ids = [r["episode_id"] for r in read((root / BASE / "observations.json").read_bytes())["rows"]]
    if release["point_ids"] != ids or release["points"] != 1640 or any(not "2018" <= i[4:8] <= "2022" for i in ids):
        raise DataCompletionError("Cohort collection khác snapshot")
    for name, expected in parent["source_sha256"].items():
        if checksum(safe_path(root, name).read_bytes()) != expected:
            raise DataCompletionError("Không sửa source dataset lịch sử")
    for name, expected in parent["artifact_sha256"].items():
        if checksum(safe_path(root, name).read_bytes()) != expected:
            raise DataCompletionError("Không sửa snapshot dataset lịch sử")
    for name, expected in parent["agent_input_sha256"].items():
        if checksum(safe_path(root, name).read_bytes()) != expected:
            raise DataCompletionError("Không sửa report/episode agent lịch sử")
    if cache_audit(root) != release["cache_compatibility"]:
        raise DataCompletionError("Cache audit khác khóa")
    return release


def prepare(root: Path) -> dict[str, Any]:
    """Khóa amendment trước fetch/LLM; chỉ hash và dựng fixture/corrected coverage offline."""
    if (root / RELEASE).exists():
        return verify_release(root, require_git=False)
    verify_spec(root)
    spec = read((root / "docs/plan/week11/protocol_v4.json").read_bytes())
    rows = read((root / BASE / "observations.json").read_bytes())["rows"]
    folds = read((root / BASE / "folds.json").read_bytes())
    source_commit = git(root, "rev-parse", "HEAD").decode().strip()
    for name in SOURCES:
        if (root / name).read_bytes() != git(root, "show", source_commit + ":" + name):
            raise DataCompletionError("Cần commit source collection trước freeze")
    release = {"version": "conditional_v4_data_completion_release", "scope": "USER_WARMUP_AGENT_ORIGINAL_2018_2022_ONLY",
        "authority": "USER_2026_11_01_HAY_THUC_HIEN_DAY_DU_CAC_BUOC_DE_HOAN_THIEN_W11_18",
        "user_instruction": "Hãy thực hiện đầy đủ các bước để hoàn thiện W11-18",
        "source_commit": source_commit, "source_sha256": {n: checksum((root / n).read_bytes()) for n in SOURCES},
        "dependency_sha256": {n: checksum((root / n).read_bytes()) for n in DEPENDENCIES},
        "parent_sha256": {n.as_posix(): checksum((root / n).read_bytes()) for n in (PARENT, OLD_COVERAGE, Path("docs/plan/week11/protocol_v4.json"))},
        "news_sha256": {f"outputs/historical_memory_run/inputs/news/{s}.json": checksum((root / f"outputs/historical_memory_run/inputs/news/{s}.json").read_bytes()) for s in spec["data"]["symbols"]},
        "warmup": {"start": "2015-01-01", "end": "2018-01-15", "append_only_before": "2018-01-02",
                   "minimum_pre_anchor_rows": 579, "source": "VCI_RAW_REST", "overlap": "EVERY_2018_RETURNED_ROW_MUST_MATCH_FROZEN_RAW_WITHIN_1e-8",
                   "no_pre2018_labels_or_train_queries": True},
        "coverage_amendment": "AGENT_COVERAGE_INDEPENDENT_OF_NUMERIC_KEEP_70_PERCENT_AND_ALL_ORIGINAL_SUPPORT_THRESHOLDS;JOINT_FULL_INPUT_SEPARATE",
        "cache_compatibility": cache_audit(root), "corrected_initial_coverage_sha256": checksum(encoded(corrected_coverage(rows, folds, spec))),
        "point_ids": [r["episode_id"] for r in rows], "points": len(rows),
        "config": read((root / "docs/plan/week11/protocol_v3.json").read_bytes())["decision"]["config"],
        "acquisition_runtime": {n: importlib.metadata.version(n) for n in ("vnstock", "vnai", "requests", "python-dotenv", "tiktoken")},
        "stages": ["indicator", "pattern", "trend", "full", "original"],
        "deterministic_stages": ["indicator", "full"], "nominal_LLM_stages": ["pattern", "trend", "original"],
        "nominal_LLM_slots": 4920, "controls_per_credential_scope": 3,
        "resume": "ONE_COMMAND_CACHE_BEFORE_KEY_SAME_INCOMPLETE_UUID_NO_COMPLETE_REPLAY_KEEP_ALL_RESERVES",
        "lost_unsealed_response": "KEEP_HTTP_ROW_AND_RESERVE_RETRY_SAME_UUID_AFTER_CACHE_AUDIT;PHYSICAL_DUPLICATE_POSSIBLE_NO_REPEAT_VOTE",
        "hour_cap": None, "calendar_deadline": None, "credential_change": "SYNTHETIC_TEXT_VISION_STRUCTURED_PREFLIGHT_PER_SCOPE",
        "collection_operator": "USER_ONLY", "training_allowed": False, "development_allowed": False, "confirmation_allowed": False}
    immutable(root / DIRECTORY / "coverage_before_collection.json", corrected_coverage(rows, folds, spec))
    immutable(root / RELEASE, release)
    return verify_release(root, require_git=False)
