"""Runner paired rút gọn, năm shard độc lập, cache từng node và raw response."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from collections import Counter
from typing import Any

from core.revision_audit import sha256_file
from core.revision_call_archive import GuardedLLM, StudyLock, StudyStop
from core.revision_common_study import (FrozenSentiment, digest, pack_state, point_state,
    read_json, restore_state, write_json)
from core.revision72_quota import PoolArchive, PoolLedger
from core.revision72_provider import RoutedLLM, PoolUnavailable, scientific_context, seed_provider_state


def signed(value: dict) -> dict:
    """Content hash không tự tham chiếu."""
    return {**value, "sha256": digest(value)}


def checked(path: Path) -> dict:
    """Từ chối cache tự bị sửa, không tự sửa receipt hoặc prediction."""
    value = read_json(path)
    if digest({k: v for k, v in value.items() if k != "sha256"}) != value["sha256"]:
        raise ValueError(f"Cache sai hash: {path.name}")
    return value


def allocate(manifest: dict) -> list[dict]:
    """LPT theo tải cố định của market unit; giữ mọi treatment trên cùng org."""
    groups: dict[str, list[dict]] = {}
    for job in manifest["jobs"]:
        groups.setdefault(job["unit_id"], []).append(job)
    loads = {i: [2, 4, {}] for i in range(1, 6)}  # bao gồm smoke cố định
    owner = {}
    units = {u["id"]: u for u in manifest["units"]}
    def weight(key: str) -> tuple[int, int]:
        jobs = groups[key]
        decisions = sum(len(j["decisions"]) for j in jobs)
        return decisions, decisions + 2 * len({j["realization"] for j in jobs})
    for key in sorted(groups, key=lambda k: (-weight(k)[0], -weight(k)[1], units[k]["date"], k)):
        decisions, calls = weight(key)
        block = units[key]["fold"]
        org = min(loads, key=lambda i: (loads[i][0], loads[i][1], loads[i][2].get(block, 0), i))
        owner[key] = org
        loads[org][0] += decisions; loads[org][1] += calls
        loads[org][2][block] = loads[org][2].get(block, 0) + 1
    if any(v[0] > 120 or v[1] >= 200 for v in loads.values()):
        raise ValueError("Phân shard vượt cap ba cửa sổ quota, cần sửa trước freeze")
    return [{**j, "org": owner[j["unit_id"]]} for j in manifest["jobs"]]


def freeze(root: Path, bank: Path, run: Path, amend: bool = False) -> dict:
    """Freeze sau assets/tests, trước API; plan tiến độ và secrets không phải runtime input."""
    from importlib.metadata import version
    manifest = read_json(bank / "manifest.json")
    protocol_path = root / "revision/r1_72h_protocol.json"
    protocol = read_json(protocol_path)
    for field in ("price_snapshot", "price_quality_policy", "window_size", "alpha_history", "alpha_norm_method",
                  "alpha_weights", "horizon_observed_sessions", "training_step", "fee_each_side", "slippage_each_side",
                  "initial_capital_vnd", "logistic_C_grid", "logistic_threshold_grid", "logistic_solver", "logistic_max_iter"):
        if protocol[field] != manifest["protocol"][field]:
            raise ValueError("Execution protocol không khớp các điều kiện tạo numeric assets")
    if protocol["n_main_units"] != len(manifest["units"]) or protocol["sentiment_gate"] != manifest["gate"]:
        raise ValueError("Execution protocol khác schedule/gate đã khóa")
    if digest({k: v for k, v in manifest.items() if k != "bank_id"}) != manifest["bank_id"]:
        raise ValueError("Bank identity sai")
    receipt = read_json(bank / "assets_complete.json")
    expected = {f"features/{s['symbol']}_{i}.json" for s in manifest["schedule"] for role in ("train", "validation", "test") for i in s[role]}
    expected |= {f"features/{s['symbol']}_{s['decision']}.json" for s in manifest["smoke"]}
    if receipt["bank_id"] != manifest["bank_id"] or {r["path"] for r in receipt["files"]} != expected or len(receipt["files"]) != len(expected):
        raise ValueError("Asset receipt thiếu/trùng/sai bank")
    if digest(read_json(bank / "news.json")) != manifest["news_hash"]:
        raise ValueError("Frozen news đã đổi")
    for artifact in receipt["files"]:
        if sha256_file(bank / artifact["path"]) != artifact["sha256"]:
            raise ValueError("Asset đã đổi")
    files = [p for folder in ("agents", "utils") for p in (root / folder).glob("*.py")]
    files += [root / p for p in ("core/backtest_engine.py", "core/alpha_compare.py", "core/revision_audit.py",
        "core/revision_baselines.py", "core/revision_common_study.py", "core/revision_call_archive.py",
        "core/revision72_data.py", "core/revision72_quota.py", "core/revision72_run.py", "core/revision72_analysis.py",
        "core/revision72_provider.py",
        "scripts/run_revision_72h.py", "scripts/evaluate_revision_baselines.py", "default_config.py")]
    inputs = [bank / p for p in ("manifest.json", "article_audit.json", "local_scores.json", "news.json", "assets_complete.json")]
    inputs.append(protocol_path)
    policy_path = root / "revision/r1_provider_policy.json"
    inputs.append(policy_path)
    numeric = read_json(bank / "numeric/manifest.json")
    for artifact in numeric["outputs"]:
        if sha256_file(bank / "numeric" / artifact["path"]) != artifact["sha256"]:
            raise ValueError("Numeric release đã đổi")
    inputs.append(bank / "numeric/manifest.json")
    prices = root / manifest["protocol"]["price_snapshot"]
    inputs += [prices / "manifest.json", *sorted(prices.glob("*.csv"))]
    runtime = {k: version(k) for k in (*manifest["runtime"].keys(), "torch", "transformers", "tokenizers") if k != "python"}
    runtime["python"] = sys.version.split()[0]
    source = [{"path": p.relative_to(root).as_posix(), "sha256": sha256_file(p)} for p in sorted(set(files + inputs))]
    path = run / "run_manifest.json"
    if path.exists():
        old = checked(path)
        if old["runtime"] != runtime or old["bank_id"] != manifest["bank_id"]:
            raise ValueError("Runtime hoặc bank đã đổi; không được migrate quota policy")
        if old["sources"] != source:
            amendment_path = run / "execution_amendment.json"
            allowed = {"core/revision72_quota.py", "core/revision72_run.py", "core/revision72_analysis.py",
                "scripts/run_revision_72h.py", "core/revision72_provider.py", "revision/r1_provider_policy.json"}
            previous = {s["path"]:s["sha256"] for s in old["sources"]}
            current = {s["path"]:s["sha256"] for s in source}
            if any(current.get(p) != h and p not in allowed for p,h in previous.items()) or set(current)-set(previous)-allowed:
                raise ValueError("Có thay đổi ngoài routing/quota được cho phép; giữ nguyên nghiên cứu")
            archive = run / "runtime_history/original_sources.zip"
            from zipfile import ZipFile
            import hashlib
            with ZipFile(archive) as archived:
                for record in old["sources"]:
                    if hashlib.sha256(archived.read(record["path"])).hexdigest() != record["sha256"]:
                        raise ValueError("Archive code/runtime cũ không khớp")
                import ast
                for filename, names in (("core/revision72_analysis.py", {"numeric","target","block_interval","panel_summary"}),
                                         ("core/revision72_run.py", {"variant_state","allocate"})):
                    def functions(text: str) -> dict:
                        return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(text).body
                                if isinstance(n,ast.FunctionDef) and n.name in names}
                    if functions(archived.read(filename).decode("utf8")) != functions((root/filename).read_text(encoding="utf8")):
                        raise ValueError("Thay đổi quota không được sửa numerical/variant estimand")
            if not amendment_path.exists():
                if not amend:
                    raise ValueError("Cần migrate-provider-pool offline một lần trước khi resume bằng policy mới")
                with StudyLock(run / "migration.lock"):
                    probes = []
                    try:
                        for org in range(1,6):
                            lock = StudyLock(run / f"shards/org{org}/worker.lock")
                            lock.__enter__(); probes.append(lock)
                        snapshot = read_json(run / "runtime_history/before_provider_only.json")
                        for record in snapshot["artifacts"]:
                            if sha256_file(run / record["path"]) != record["sha256"]:
                                raise ValueError("Checkpoint trước migration đã đổi; không sửa prediction")
                        value = signed({"original_run_signature":old["sha256"], "sources":source,
                            "runtime":runtime, "policy":read_json(policy_path), "original_source_archive_sha256":sha256_file(archive),
                            "checkpoint_snapshot_sha256":sha256_file(run / "runtime_history/before_provider_only.json"),
                            "created_utc":datetime.now(timezone.utc).isoformat(),
                            "scope":"operational routing/quota only; original manifest, prompts, checkpoints and scientific run identity retained"})
                        write_json(amendment_path, value, True)
                    finally:
                        for lock in reversed(probes): lock.__exit__()
            value = checked(amendment_path)
            if value["sources"] != source or value["original_run_signature"] != old["sha256"] or value["runtime"] != runtime:
                raise ValueError("Nguồn không khớp operational amendment đã khóa")
            if value["original_source_archive_sha256"] != sha256_file(archive):
                raise ValueError("Archive gốc đã đổi")
            if value["checkpoint_snapshot_sha256"] != sha256_file(run / "runtime_history/before_provider_only.json"):
                raise ValueError("Snapshot trước thay đổi quota đã đổi")
        return old
    import re
    match = re.search(r"T0 = ([^*\s]+)", (root / "plan.md").read_text(encoding="utf8"))
    if not match:
        raise ValueError("Phải ghi T0 trong kế hoạch trước freeze")
    t0 = datetime.fromisoformat(match.group(1).rstrip("."))
    value = signed({"profile": "revision_72h", "bank_id": manifest["bank_id"], "run_id": run.name,
        "sources": source, "runtime": runtime, "t0_utc": t0.astimezone(timezone.utc).isoformat(),
        "deadline_epoch": t0.timestamp() + 60 * 3600, "required_decisions": manifest["n_decisions"],
        "org_identity": "five author-asserted org slots; distinct keys checked privately; provider org identity unverified unless returned",
        "protocol": protocol, "bank_template_scope": "bank protocol retains numerical-generation template fields; this execution protocol is authoritative for sample/repeats/calibration/exposure",
        "execution_policy":read_json(policy_path),
        "jobs": allocate(manifest), "allocation": "LPT by fixed unit decision/call load; source bank round-robin is replaced before inference; no treatment split or outcome input"})
    write_json(path, value, True)
    return value


class CachedLLM:
    """Replay response thật đã archive trước khi gọi mới; giữ schema/parser của agent."""

    def __init__(self, delegate: Any, archive: PoolArchive, structured: bool = False, used: set | None = None):
        self.delegate, self.archive, self.structured = delegate, archive, structured
        self.used = used if used is not None else set()

    def with_structured_output(self, *args: Any, **kwargs: Any) -> CachedLLM:
        """Underlying Groq vẫn kiểm schema; replay đi qua cùng schema Pydantic."""
        return CachedLLM(self.delegate.with_structured_output(*args, **kwargs), self.archive, True, self.used)

    def invoke(self, prompt: Any, **kwargs: Any) -> Any:
        """Đối chiếu context lẫn messages; không chuyển response sang variant/node khác."""
        from langchain_core.messages import AIMessage, HumanMessage, messages_to_dict
        messages = [HumanMessage(content=prompt)] if isinstance(prompt, str) else prompt
        expected = messages_to_dict(messages)
        paths = sorted((self.archive.directory / "calls").glob("*.request.json"), key=lambda p: p.stat().st_mtime_ns)
        for path in paths:
            key = path.name.removesuffix(".request.json")
            response_path = path.with_name(f"{key}.response.json")
            if key in self.used or not response_path.exists():
                continue
            request = checked(path)
            if scientific_context(request["context"]) != scientific_context(self.archive.context) or request["messages"] != [expected]:
                continue
            response = read_json(response_path)
            if response["parent_request_hash"] != request["sha256"]:
                raise ValueError("Response archive sai parent")
            checksum = path.with_name(f"{key}.response_digest.json")
            if not checksum.exists():
                # Crash có thể xảy ra sau raw response atomic logic nhưng trước
                # receipt checksum; giữ nguyên raw bytes và ghi rõ recovery.
                write_json(checksum, {"sha256": digest(response), "request_hash": request["sha256"],
                    "recovered_after_interruption": True}, True)
            if digest(response) != read_json(checksum)["sha256"]:
                raise ValueError("Raw response đã đổi trước replay node")
            message = AIMessage.model_validate(response["response"]["generations"][0][0]["message"])
            self.used.add(key)
            self.archive.ids.append(key)
            if not self.structured:
                return message
            from agents.decision_agent import TradeDecisionOutput
            try:
                data = message.tool_calls[0]["args"] if message.tool_calls else json.loads(message.content)
                parsed = TradeDecisionOutput.model_validate(data)
                return {"parsed": parsed, "raw": message, "parsing_error": None}
            except Exception as exc:
                return {"parsed": None, "raw": message, "parsing_error": exc}
        # Proxy chuẩn là nơi duy nhất invoke SDK, mọi attempts vẫn qua callback.
        before = len(self.archive.ids)
        try:
            return GuardedLLM(self.delegate).invoke(prompt, **kwargs)
        finally:
            self.used.update(self.archive.ids[before:])


def variant_state(shared: dict, asset: dict, donor: dict, variant: str) -> dict:
    """Reuse công tắc four-way; P thay vector past giữ headings/schema/missingness."""
    from agents.alpha_agent import _build_alpha_report
    from utils.graph_setup import ABLATION_CONFIGS
    from utils.i18n import t, signal_label
    name = {"B": "baseline", "A": "alpha_only", "S": "sentiment_only", "AS": "full", "P": "full"}[variant]
    config = ABLATION_CONFIGS[name]
    state = deepcopy(shared)
    for field in ("alpha_report", "sentiment_report", "sentiment_data", "sentiment_norm", "final_trade_decision", "decision_prompt"):
        state.pop(field, None)
    state["ablation_config"] = dict(config)
    if config["enable_alpha_factors"]:
        factors = deepcopy(asset["alpha_factors"])
        if variant == "P":
            for factor, past in zip(factors, donor["alpha_factors"]):
                if set(factor["components"]) != set(past["components"]):
                    raise ValueError("Donor không khớp alpha schema/missingness")
                for key in ("value", "signal", "components"):
                    factor[key] = deepcopy(past[key])
                factor["interpretation"] = f"IC={past['components']['ic']}; accuracy={past['components']['accuracy']}"
        # Cùng phong cách cho treatment và placebo, tránh chỉ P bị đổi format.
        for factor in factors:
            factor["interpretation"] = f"IC={factor['components']['ic']}; accuracy={factor['components']['accuracy']}"
        up, down = sum(f["signal"] == "TĂNG" for f in factors), sum(f["signal"] == "GIẢM" for f in factors)
        consensus = "TĂNG" if up > down else "GIẢM" if down > up else "TRUNG TÍNH"
        state["alpha_report"] = _build_alpha_report(factors, asset["tech_vars"], {}, asset["symbol"], "vi") + (
            f"\n**{t('alpha_summary', 'vi')}: {signal_label(consensus, 'vi')} ({up} {signal_label('TĂNG', 'vi')} / "
            f"{down} {signal_label('GIẢM', 'vi')} / {5-up-down} {signal_label('TRUNG TÍNH', 'vi')})**\n")
    if config["enable_sentiment"]:
        state.update({k: deepcopy(asset[k]) for k in ("sentiment_report", "sentiment_data", "sentiment_norm")})
    return state


def worker(root: Path, bank: Path, run: Path, org: int, smoke: bool) -> None:
    """Một process/org, một request đang xử lý, shard và charts tách biệt."""
    from dotenv import load_dotenv
    from langchain_groq import ChatGroq
    from groq import Groq
    from core.revision_baselines import load_prices
    from agents.indicator_agent import create_indicator_agent
    from agents.pattern_agent import create_pattern_agent
    from agents.trend_agent import create_trend_agent
    from agents.decision_agent import create_final_trade_decider
    from core.backtest_engine import BacktestEngine
    from utils.graph_util import TechnicalTools
    from utils import static_util
    identity = freeze(root, bank, run)
    manifest = read_json(bank / "manifest.json")
    protocol = identity.get("protocol", manifest["protocol"])
    load_dotenv(root / ".env")
    keys = [os.getenv(f"GROQ_ORG_{i}_API_KEY", "") for i in range(1, 6)]
    if not all(keys) or len(set(keys)) != 5:
        raise ValueError("Cần năm key khác nhau; không in/lưu key hoặc hash key")
    key = keys[org - 1]
    # Smoke kiểm riêng từng key; run đã có năm smoke markers và dùng pool.
    if smoke:
        available = {m.id for m in Groq(api_key=key, max_retries=0, timeout=20).models.list().data}
        if not {protocol["agent_llm_model"], protocol["graph_llm_model"]}.issubset(available):
            raise ValueError("Org thiếu model đã khóa; không đổi model")
    if not smoke:
        for i in range(1, 6):
            marker = checked(run / f"shards/org{i}/smoke_complete.json")
            if marker["run_signature"] != identity["sha256"]:
                raise ValueError("Smoke không cùng run")
            for artifact in marker["files"]:
                if sha256_file(run / f"shards/org{i}" / artifact["path"]) != artifact["sha256"]:
                    raise ValueError("Artifact smoke đã đổi")
    shard = run / f"shards/org{org}"
    shard.mkdir(parents=True, exist_ok=True)
    ledger = PoolLedger(run / "quota.sqlite3", identity["sha256"])
    seed_provider_state(run, ledger)
    archive = PoolArchive(shard, identity["bank_id"], key, ledger, org, identity["deadline_epoch"])
    amendment = run / "execution_amendment.json"
    epoch = checked(amendment)["sha256"] if amendment.exists() else identity["sha256"]
    status_path = shard / "status.json"
    with StudyLock(shard / "worker.lock"):
        write_json(status_path, {"phase": "smoke" if smoke else "inference", "pid": os.getpid(), "updated_utc": datetime.now(timezone.utc).isoformat()})
        previous_cwd = Path.cwd()
        work = shard / "work"
        work.mkdir(exist_ok=True)
        try:
            os.chdir(work)
            frames, _ = load_prices(root / protocol["price_snapshot"], protocol["price_quality_policy"])
            store = FrozenSentiment(read_json(bank / "news.json"))
            toolkit = TechnicalTools()
            parser = BacktestEngine({"use_historical_sentiment": False})
            def model(node: str, role: str) -> CachedLLM:
                prefix = "agent" if role == "text" else "graph"
                delegate = RoutedLLM(archive, keys, org, {
                    "model":protocol[f"{prefix}_llm_model"], "temperature":0,
                    "max_tokens":protocol[f"{prefix}_llm_max_tokens"], "max_retries":0, "timeout":120,
                    "reasoning_format":"hidden", "metadata":{"langgraph_node":node}}, epoch,
                    allowed=[org] if smoke else list(range(1,6)))
                return CachedLLM(delegate, archive)
            class NoFallback:
                def invoke(self, *args: Any, **kwargs: Any) -> Any:
                    raise StudyStop("Không dùng text fallback thay vision model đã khóa")
            nodes = [("Indicator Agent", create_indicator_agent(None, toolkit)),
                ("Pattern Agent", create_pattern_agent(NoFallback(), model("Pattern Agent", "vision"), toolkit)),
                ("Trend Agent", create_trend_agent(NoFallback(), model("Trend Agent", "vision"), toolkit))]
            decision_node = create_final_trade_decider(model("Decision Maker", "text"))
            units = {u["id"]: u for u in manifest["units"] + manifest["smoke"]}
            jobs = [{"unit_id": f"smoke_org{org}", "realization": 0, "id": f"smoke{org}",
                     "decisions": [{"variant": v, "repeat": 0} for v in ("B", "AS")]}] if smoke else [j for j in identity["jobs"] if j["org"] == org]
            def execute_job(job: dict) -> None:
                unit = units[job["unit_id"]]
                symbol, index, realization = unit["symbol"], unit["decision"], job["realization"]
                asset = checked(bank / f"features/{symbol}_{index}.json")
                donor = checked(bank / f"features/{symbol}_{unit['placebo_donor']}.json")
                initial = point_state(frames[symbol], symbol, index, protocol, store)
                chart_path = shard / f"charts/{unit['id']}.json"
                if chart_path.exists():
                    charts = checked(chart_path)
                    if charts["asset_hash"] != asset["sha256"]:
                        raise ValueError("Chart cache khác input")
                else:
                    charts = signed({"asset_hash": asset["sha256"],
                        "pattern_image": static_util.generate_kline_image(initial["kline_data"])["pattern_image"],
                        "trend_image": static_util.generate_trend_image(initial["kline_data"])["trend_image"]})
                    write_json(chart_path, charts, True)
                initial.update({k: charts[k] for k in ("pattern_image", "trend_image")})
                state, parents = initial, []
                for name, node in nodes:
                    parent = {"input_hash": digest(pack_state(state)), "asset_hash": asset["sha256"], "run_signature": identity["sha256"]}
                    path = shard / f"nodes/{unit['id']}_r{realization}_{name.split()[0]}.json"
                    context = {"unit_id": unit["id"], "realization": realization, "stage": "upstream", "node": name,
                        "model": protocol["graph_llm_model"], "smoke": smoke}
                    archive.context = context
                    if path.exists():
                        result = checked(path)
                        if result["parent"] != parent:
                            raise ValueError("Node parent/input khác")
                    else:
                        before = len(archive.ids)
                        value = node(deepcopy(state))
                        all_ids = archive.ids[before:]
                        ids = [a for a in all_ids if (shard / f"calls/{a}.response.json").exists()]
                        if name != "Indicator Agent" and not ids:
                            raise ValueError("Vision node thiếu raw response thật")
                        result = signed({"parent": parent, "context": context, "state": pack_state(value), "request_ids": ids,
                            "execution_epoch":epoch, "failed_request_ids":[a for a in all_ids if a not in ids],
                            "call_hashes": [{"path": p.relative_to(shard).as_posix(), "sha256": sha256_file(p)} for a in all_ids for p in
                                (shard / f"calls/{a}.request.json", shard / f"calls/{a}.response.json", shard / f"calls/{a}.error.json") if p.exists()]})
                        write_json(path, result, True)
                    for record in result["call_hashes"]:
                        if sha256_file(shard / record["path"]) != record["sha256"]:
                            raise ValueError("Raw node response đã đổi")
                    state = {**state, **restore_state(result["state"], initial)}
                    parents.append(result["sha256"])
                shared_hash = digest(pack_state(state))
                for treatment in job["decisions"]:
                    variant, repeat = treatment["variant"], treatment["repeat"]
                    path = shard / f"decisions/{unit['id']}_r{realization}_{variant}_n{repeat}.json"
                    context = {"unit_id": unit["id"], "realization": realization, "variant": variant, "repeat": repeat,
                        "stage": "decision", "node": "Decision Maker", "model": protocol["agent_llm_model"], "smoke": smoke}
                    parent = {"run_signature": identity["sha256"], "asset_hash": asset["sha256"], "upstream_hash": shared_hash,
                              "node_hashes": parents, "donor_hash": donor["sha256"] if variant == "P" else None}
                    if path.exists():
                        if checked(path)["parent"] != parent:
                            raise ValueError("Decision parent khác variant/repeat")
                        continue
                    archive.context = context
                    before = len(archive.ids)
                    value = decision_node(variant_state(state, asset, donor, variant))
                    prediction, confidence, ratio, source, reason = parser._parse_prediction(value)
                    if prediction not in ("LONG", "SHORT"):
                        raise ValueError("Không lưu prediction fallback")
                    all_ids = archive.ids[before:]
                    ids = [a for a in all_ids if (shard / f"calls/{a}.response.json").exists()]
                    value = signed({"parent": parent, "context": context, "prediction": prediction,
                        "confidence": confidence, "decision_source": source, "fallback_reason": reason,
                        "state": pack_state(value), "request_ids": ids, "execution_epoch":epoch,
                        "failed_request_ids":[a for a in all_ids if a not in ids],
                        "call_hashes": [{"path": p.relative_to(shard).as_posix(), "sha256": sha256_file(p)} for a in all_ids for p in
                            (shard / f"calls/{a}.request.json", shard / f"calls/{a}.response.json", shard / f"calls/{a}.error.json") if p.exists()]})
                    write_json(path, value, True)
                    print(f"Org {org}: {unit['id']} r{realization} {variant}/{repeat} đã checkpoint.", flush=True)
            remaining_jobs = jobs
            while remaining_jobs:
                pending = []
                blocked_models = set()
                for job in remaining_jobs:
                    try:
                        execute_job(job)
                    except PoolUnavailable as exc:
                        pending.append(job)
                        if exc.model: blocked_models.add(exc.model)
                if not pending:
                    break
                usable = any(any(not s["active"] or s["kind"] not in ("quota","quota_unknown_reset","key_error","incompatible")
                             for s in ledger.states(m, [org] if smoke else list(range(1,6)))) for m in blocked_models)
                if not usable:
                    raise PoolUnavailable(f"Shard {org} đã thử mọi job; {len(pending)} job còn chờ quota/model. Các job có key khả dụng đã tiếp tục.")
                # Quota có thể reset trong lúc worker xử lý model/job khác.
                remaining_jobs = pending
                time.sleep(1)
            name = "smoke_complete.json" if smoke else "shard_complete.json"
            marker = signed({"run_signature": identity["sha256"], "org": org, "smoke": smoke,
                "org_identity_verified": False, "quota_capacity_verified": False,
                "files": [{"path": p.relative_to(shard).as_posix(), "sha256": sha256_file(p)}
                    for folder in ("nodes", "decisions", "calls", "charts") for p in sorted((shard / folder).glob("*.json"))]})
            if (shard / name).exists():
                if smoke:
                    # Smoke marker chỉ khóa artifacts smoke, không bao gồm evaluation về sau.
                    return
                if checked(shard / name) != marker:
                    raise ValueError("Shard completion đã đổi")
            else:
                write_json(shard / name, marker, True)
            write_json(status_path, {"phase": "smoke_complete" if smoke else "shard_complete", "updated_utc": datetime.now(timezone.utc).isoformat()})
        except BaseException as exc:
            message = str(exc)
            for secret in keys:
                message = message.replace(secret, "[REDACTED]")
            write_json(status_path, {"phase": "paused", "reason": message[:500], "updated_utc": datetime.now(timezone.utc).isoformat()})
            raise
        finally:
            os.chdir(previous_cwd)


def dispatch(root: Path, bank: Path, run: Path, command: str, org: int | None, all_orgs: bool) -> None:
    """Không suy trạng thái process từ receipt cũ; API chỉ trong smoke/run."""
    if command == "migrate-provider-pool":
        original = freeze(root, bank, run, amend=True)
        seed_provider_state(run, PoolLedger(run / "quota.sqlite3", original["sha256"]))
        print(f"Đã đổi policy vận hành, giữ nguyên nghiên cứu/checkpoint {original['sha256']}.")
    elif command == "freeze":
        print(f"Đã freeze runtime: {freeze(root, bank, run)['sha256']}")
    elif command == "verify":
        freeze(root, bank, run)
        from core.revision72_analysis import verify
        verify(root, bank, run)
    elif command == "status":
        manifest = read_json(bank / "manifest.json")
        amendment_path = run / "execution_amendment.json"
        amendment_data = checked(amendment_path) if amendment_path.exists() else None
        rows = []
        pair_variants: dict[str, set] = {}
        for i in range(1, 6):
            shard = run / f"shards/org{i}"
            decisions = [checked(p) for p in (shard / "decisions").glob("*.json")]
            event = read_json(shard / "status.json") if (shard / "status.json").exists() else None
            research = [v for v in decisions if not v["context"]["smoke"]]
            for value in research:
                c = value["context"]
                if c["realization"] == 0 and c["repeat"] == 0 and c["variant"] in ("B", "AS"):
                    pair_variants.setdefault(c["unit_id"], set()).add(c["variant"])
            rows.append({"org": i, "smoke": sum(v["context"]["smoke"] for v in decisions),
                "research": len(research), "unique_market_units": len({v["context"]["unit_id"] for v in research}),
                "variants": dict(Counter(v["context"]["variant"] for v in research)),
                "repeat_ids": sorted({v["context"]["repeat"] for v in research}),
                "requests": len(list((shard / "calls").glob("*.request.json"))),
                "errors": len(list((shard / "calls").glob("*.error.json"))),
                "last_worker_event":event, "event_predates_provider_only_policy":bool(event and amendment_data and event.get("updated_utc","") < amendment_data["created_utc"])})
        from core.revision72_analysis import system_costs
        provider_states = []
        amendment = run / "execution_amendment.json"
        if amendment.exists():
            identity = checked(run / "run_manifest.json")
            ledger = PoolLedger(run / "quota.sqlite3", identity["sha256"])
            for model in (manifest["protocol"]["agent_llm_model"], manifest["protocol"]["graph_llm_model"]):
                provider_states.append({"model":model,"states":ledger.states(model,list(range(1,6)))})
        print(json.dumps({"profile": "revision_72h", "required_pairs": 102,
            "complete_main_pairs": sum(v == {"B", "AS"} for v in pair_variants.values()),
            "required_decisions": manifest["n_decisions"], "orgs": rows, "usage": system_costs(run),
            "execution_policy": "provider_only" if amendment.exists() else "original_caps", "internal_caps":None if amendment.exists() else "original",
            "automatic_deadline_stop":not amendment.exists(), "provider_states":provider_states,
            "scope": "live artifact counts and last worker events; no process liveness inferred from old receipts"}, ensure_ascii=False, indent=2))
    elif all_orgs:
        children = [subprocess.Popen([sys.executable, "-X", "utf8", str(root / "scripts/run_revision_72h.py"), command,
            "--bank", str(bank), "--run", str(run), "--org", str(i)], cwd=root) for i in range(1, 6)]
        codes = [child.wait() for child in children]
        if any(code not in (0,3) for code in codes):
            raise RuntimeError(f"Có shard gặp lỗi cần kiểm tra, không phải quota đơn thuần; mã thoát: {codes}")
        if any(codes):
            raise StudyStop(f"Các job còn lại chưa có key khả dụng; pool đã tiếp tục mọi job có thể chạy. Mã thoát home shards: {codes}; xem status để biết quota từng provider.")
        if command == "run":
            complete(bank, run)
    elif org:
        worker(root, bank, run, org, command == "smoke")
        if command == "run":
            complete(bank, run)
    else:
        raise ValueError("smoke/run cần --org 1..5 hoặc --all")


def complete(bank: Path, run: Path) -> None:
    """Chỉ có receipt tổng khi đủ mọi shard/job, kể cả smoke tách khỏi evaluation."""
    identity = checked(run / "run_manifest.json")
    records, markers = [], []
    for org in range(1, 6):
        shard = run / f"shards/org{org}"
        path = shard / "shard_complete.json"
        if not path.exists():
            return
        marker = checked(path)
        if marker["run_signature"] != identity["sha256"]:
            raise ValueError("Shard completion khác run")
        for artifact in marker["files"]:
            if sha256_file(shard / artifact["path"]) != artifact["sha256"]:
                raise ValueError("Shard artifact đã đổi")
        markers.append({"path": path.relative_to(run).as_posix(), "sha256": sha256_file(path)})
        records += [checked(p) for p in (shard / "decisions").glob("*.json")]
    research = [r for r in records if not r["context"]["smoke"]]
    expected = {(j["unit_id"], j["realization"], d["variant"], d["repeat"]) for j in identity["jobs"] for d in j["decisions"]}
    actual = {(r["context"]["unit_id"], r["context"]["realization"], r["context"]["variant"], r["context"]["repeat"]) for r in research}
    if actual != expected or len(research) != len(expected):
        raise ValueError("Shard markers chưa đủ/sai jobs")
    receipt = signed({"run_signature": identity["sha256"], "n_research_decisions": len(research), "markers": markers,
                      "execution_amendment_sha256":sha256_file(run/"execution_amendment.json") if (run/"execution_amendment.json").exists() else None,
                      "status": "inference_complete_pending_analysis_and_scientific_review"})
    path = run / "inference_complete.json"
    if path.exists():
        if checked(path) != receipt:
            raise ValueError("Completion receipt khác")
    else:
        write_json(path, receipt, True)
    print(f"Inference đủ {len(research)} research decisions; có thể analyze offline.")
