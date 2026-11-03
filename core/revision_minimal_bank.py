"""Khóa scope rút gọn và provenance từ corrected-chart, chỉ làm việc offline."""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from importlib.metadata import version
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any, Iterator

from agents.decision_agent import TradeDecisionOutput
from core.revision72_provider import scientific_context
from core.revision72_run import checked, freeze, signed, variant_state
from core.revision_call_archive import StudyLock
from core.revision_common_study import (
    FrozenSentiment, digest, pack_state, point_state, read_json, restore_state, write_json,
)
from core.revision_r4_factorial import CONTRASTS, VARIANTS, actual_text, controlled_prompt, prompt_parts, validate_donor

R1 = Path("outputs/revision/chart_r1_run_v1")
R4 = Path("outputs/revision/chart_r4_run_v1")
BANK = Path("outputs/revision/r1_72h_bank_v2")
R4_BANK = Path("outputs/revision/chart_r4_bank_v1")
DEST = Path("outputs/revision/revision_minimal_v1")


def sha(path: Path) -> str:
    """Hash nguyên byte, không đọc credentials."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    """Dừng khi hợp đồng sai, không tự sửa nguồn hoặc bỏ hash guard."""
    if not condition:
        raise ValueError(message)


def runtime() -> dict[str, str]:
    """Ghim dependency của adapter và đường inference đang tái dùng."""
    names = ("langchain-core", "langchain-groq", "groq", "pydantic", "numpy", "pandas",
             "scipy", "scikit-learn", "TA-Lib", "python-dotenv", "matplotlib", "mplfinance", "Pillow")
    return {"python": sys.version.split()[0], **{name: version(name) for name in names}}


def legacy_processes() -> list[dict]:
    """Chỉ lấy PID/mode của runner cũ; không xuất command line chứa dữ liệu riêng."""
    command = r"""
    $rows = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
      $_.Name -match '^(python|pythonw|py)(\.exe)?$' -and
      $_.CommandLine -match 'run_(chart_rerun|revision_72h|revision_r4)\.py["\s]+(run-r4|run|smoke)(\s|$)'
    } | ForEach-Object { [pscustomobject]@{pid=$_.ProcessId; parent_pid=$_.ParentProcessId; name=$_.Name} })
    ConvertTo-Json -InputObject $rows -Compress
    """
    result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


@contextmanager
def legacy_guard(root: Path) -> Iterator[None]:
    """Giữ các khóa shard cũ suốt prepare/run; không kill hoặc xóa trạng thái cũ."""
    from contextlib import ExitStack
    require(not legacy_processes(), "Còn worker grid cũ; tác giả cần dừng có checkpoint trước")
    with ExitStack() as stack:
        for run in (R1, R4):
            for org in range(1, 6):
                stack.enter_context(StudyLock(root / run / f"shards/org{org}/worker.lock"))
        yield


def select_panel(units: list[dict], size: int = 9) -> list[dict]:
    """Round-robin mã xếp chữ cái và ngày tăng dần; không nhận predictions/outcomes."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in units:
        groups[row["unit"]["symbol"]].append(row)
    for rows in groups.values():
        rows.sort(key=lambda r: (r["unit"]["date"], r["unit"]["id"]))
    ordered = [groups[symbol][index] for index in range(max(map(len, groups.values())))
               for symbol in sorted(groups) if index < len(groups[symbol])]
    require(len(ordered) >= size, "Không đủ metadata để chọn panel")
    return ordered[:size]


def raw_prediction(response: dict) -> str:
    """Kiểm schema thật của response cuối, không suy prediction từ fallback."""
    message = response["response"]["generations"][0][0]["message"]
    if message.get("tool_calls"):
        data = message["tool_calls"][0]["args"]
    elif not message.get("content") and message.get("additional_kwargs", {}).get("tool_calls"):
        data = json.loads(message["additional_kwargs"]["tool_calls"][0]["function"]["arguments"])
    else:
        data = json.loads(message["content"])
    return TradeDecisionOutput.model_validate(data).decision


def request_contract(request: dict) -> dict:
    """Khóa parameters/model/schema thật đã gửi, kể cả temperature do SDK chuẩn hóa."""
    return {"model_metadata": request["model_metadata"], "invocation_parameters": request["invocation_parameters"]}


def verify_request(path: Path, context: dict, prompt: str, bank_id: str, contract: dict, epoch: str) -> dict:
    """Kiểm request/message/model/parameters trước replay hoặc nhận checkpoint."""
    request = checked(path)
    require(request["attempt_id"] == path.name.removesuffix(".request.json"), "Sai request ID/tên file")
    require(request["bank_id"] == bank_id and scientific_context(request["context"]) == context, "Raw sai bank/context")
    require(actual_text(request) == prompt and len(prompt) < 6500, "Raw sai message/budget")
    require(request_contract(request) == contract, "Raw model/parameters/schema đã đổi")
    require(request["context"].get("execution_epoch") == epoch, "Raw sai execution epoch")
    require(request["context"].get("provider_org") in range(1, 6), "Raw sai provider org")
    return request


def verify_response(path: Path, request: dict) -> dict:
    """Kiểm raw response và digest nguyên bản; không tạo receipt recovery khi audit."""
    response = read_json(path)
    require(response["attempt_id"] == request["attempt_id"] and response["parent_request_hash"] == request["sha256"], "Response sai parent")
    receipt_path = path.with_name(path.name.replace(".response.", ".response_digest."))
    if receipt_path.exists():
        receipt = read_json(receipt_path)
        require(receipt["sha256"] == digest(response), "Raw response sai digest")
        require(receipt.get("request_hash", request["sha256"]) == request["sha256"], "Recovery receipt sai parent")
    return response


def verify_record(path: Path, job: dict, parent: dict, bank_id: str, epoch: str) -> dict:
    """Kiểm cùng hợp đồng cho checkpoint reuse và checkpoint mới, không gọi model."""
    record = checked(path)
    require(record["context"] == job["context"] and record["parent"] == parent, "Checkpoint sai context/parent")
    require(record["decision_source"] == "llm_structured" and not record.get("fallback_reason"), "Checkpoint chứa fallback")
    require(bool(record["request_ids"]), "Checkpoint thiếu raw response")
    shard = path.parent.parent
    for artifact in record["call_hashes"]:
        require(sha(shard / artifact["path"]) == artifact["sha256"], "Raw checkpoint đã đổi")
    last = None
    for attempt in record["request_ids"]:
        req = verify_request(shard / f"calls/{attempt}.request.json", job["context"], job["prompt"], bank_id, job["request_contract"], epoch)
        last = verify_response(shard / f"calls/{attempt}.response.json", req)
    require(raw_prediction(last) == record["prediction"], "Prediction không khớp raw/schema")
    return record


def parent_for(manifest: dict, job: dict) -> dict:
    """Parent mới giữ đúng input/upstream và thêm identity whitelist riêng."""
    return {"bank_id": manifest["sha256"], "job_id": job["id"], "asset_hash": job["origin_parent"]["asset_hash"],
            "donor_hash": job["origin_parent"].get("donor_hash"), "upstream_hash": job["origin_parent"]["upstream_hash"],
            "prompt_hash": job["prompt_hash"]}


def point_path(run: Path, job: dict) -> Path:
    """Shard mới theo queue workload, độc lập org lưu trữ của nguồn reuse."""
    return run / f"shards/org{job['worker']}/decisions/{job['id']}.json"


def prepare(root: Path, run: Path) -> dict:
    """Khóa 375 jobs/193 reuse nếu hợp lệ; không sửa manifest/runtime frozen cũ."""
    if (run / "manifest.json").exists():
        return verify_manifest(root, run)
    require(not run.exists(), "Thư mục chưa có manifest; không tự ghi đè preparation dở")
    from core.revision72_analysis import verify
    from core.revision_baselines import load_prices
    from core.revision_r4_run import collect, parent_for as old_r4_parent, verify_bank
    from scripts.prepare_chart_r4 import native_prompt
    from scripts.run_chart_rerun import verify_preparation

    verify_preparation()
    identity = freeze(root, root / BANK, root / R1)
    bank = read_json(root / BANK / "manifest.json")
    verify(root, root / BANK, root / R1)
    r4 = verify_bank(root, root / R4_BANK)
    collect(r4, root / R4)
    sources: set[Path] = set()

    def source(path: Path) -> None:
        """Chỉ ghi tham chiếu bằng chứng được dùng, không nhập secrets/work cache."""
        require(path.resolve().is_relative_to(root.resolve()), "Nguồn ngoài repo không được freeze")
        sources.add(path)

    for record in identity["sources"] + r4["source_hashes"]:
        source(root / record["path"])
    snapshot = checked(root / R1 / "runtime_history/frozen_runtime_sources.json")
    for record in snapshot["files"]:
        require(sha(root / record["path"]) == record["sha256"], "Nguồn snapshot hiện tại đã đổi")
        source(root / record["path"])
    for path in (root / R1 / "run_manifest.json", root / R1 / "chart_rerun_preparation.json", root / R4_BANK / "manifest.json",
                 root / "core/revision_minimal_bank.py", root / "core/revision_minimal_run.py",
                 root / "scripts/run_revision_minimal.py", root / "tests/test_revision_minimal.py"):
        source(path)
    frames, _ = load_prices(root / identity["protocol"]["price_snapshot"], identity["protocol"]["price_quality_policy"])
    store = FrozenSentiment(read_json(root / BANK / "news.json"))
    units = {u["id"]: u for u in bank["units"]}
    groups = {}
    for old in identity["jobs"]:
        if old["phase"] == "panel":
            continue
        key, realization, org = old["unit_id"], old["realization"], old["org"]
        unit = units[key]
        shard = root / R1 / f"shards/org{org}"
        asset_path = root / BANK / f"features/{unit['symbol']}_{unit['decision']}.json"
        donor_path = root / BANK / f"features/{unit['symbol']}_{unit['placebo_donor']}.json"
        asset, donor = checked(asset_path), checked(donor_path)
        source(asset_path); source(donor_path)
        initial = point_state(frames[unit["symbol"]], unit["symbol"], unit["decision"], identity["protocol"], store)
        chart_path = shard / f"charts/{key}.json"
        chart = checked(chart_path); source(chart_path)
        require(chart["asset_hash"] == asset["sha256"], "Chart sai asset")
        initial.update({k: chart[k] for k in ("pattern_image", "trend_image")})
        state, hashes = initial, []
        for name in ("Indicator", "Pattern", "Trend"):
            path = shard / f"nodes/{key}_r{realization}_{name}.json"
            require(path.exists(), "Thiếu corrected upstream; không được tự thêm vision calls: " + str(path))
            record = checked(path); source(path)
            require(record["parent"] == {"input_hash": digest(pack_state(state)), "asset_hash": asset["sha256"], "run_signature": identity["sha256"]}, "Node sai parent/input")
            require(record["context"] == {"unit_id": key, "realization": realization, "stage": "upstream", "node": name + " Agent",
                    "model": identity["protocol"]["graph_llm_model"], "smoke": False}, "Node sai context")
            for artifact in record["call_hashes"]:
                raw = shard / artifact["path"]
                require(sha(raw) == artifact["sha256"], "Raw upstream đã đổi"); source(raw)
                receipt = raw.with_name(raw.name.replace(".response.", ".response_digest."))
                if ".response." in raw.name and receipt.exists(): source(receipt)
            state = {**state, **restore_state(record["state"], initial)}
            hashes.append(record["sha256"])
        groups[(key, realization)] = {"state": state, "hashes": hashes, "asset": asset, "donor": donor,
                                      "shared_hash": digest(pack_state(state))}

    sample_path = next((root / R4).glob("shards/org*/calls/*.request.json"))
    contract = request_contract(checked(sample_path))
    require(contract["model_metadata"]["ls_model_name"] == r4["model"] == identity["protocol"]["agent_llm_model"], "Hai nguồn khác model")
    jobs, excluded = [], []
    panel = select_panel(r4["units"])
    selected = {u["unit"]["id"] for u in panel}

    def make_job(phase: str, context: dict, org: int, prompt: str, parent: dict, path: Path, bank_id: str, epoch: str) -> None:
        """Khóa identity/prompt trước khi nhìn outcome; checkpoint chỉ dùng để reuse."""
        unit = units[context["unit_id"]]
        row = {"id": f"{phase}__{unit['id']}_r{context['realization']}_{context['variant']}_n{context['repeat']}",
               "phase": phase, "unit": unit, "context": context, "origin_org": org, "prompt": prompt,
               "prompt_hash": digest(prompt), "origin_parent": parent, "origin_bank_id": bank_id,
               "origin_epoch": epoch, "origin_path": path.relative_to(root).as_posix(), "request_contract": contract,
               "reuse": None}
        require(len(prompt) < 6500, "Prompt vượt ngân sách")
        if path.exists():
            record = verify_record(path, row, parent, bank_id, epoch); source(path)
            if "state" in record:
                require(record["state"]["decision_prompt"] == prompt, "Prompt checkpoint R1 khác builder")
            raw_files = {path.parent.parent / r["path"] for r in record["call_hashes"]}
            for attempt in record["request_ids"]:
                raw_files.update(path.parent.parent / f"calls/{attempt}.{suffix}.json" for suffix in ("request", "response", "response_digest"))
            for raw in raw_files:
                if raw.exists(): source(raw)
            row["reuse"] = {"path": path.relative_to(root).as_posix(), "sha256": sha(path), "request_ids": record["request_ids"]}
        jobs.append(row)

    for old in identity["jobs"]:
        for decision in old["decisions"]:
            context = {"unit_id": old["unit_id"], "realization": old["realization"], **decision,
                       "stage": "decision", "node": "Decision Maker", "model": identity["protocol"]["agent_llm_model"], "smoke": False}
            path = root / R1 / f"shards/org{old['org']}/decisions/{old['unit_id']}_r{old['realization']}_{decision['variant']}_n{decision['repeat']}.json"
            if old["phase"] == "panel":
                excluded.append({"origin_path": path.relative_to(root).as_posix(), "context": context, "reason": "panel R1 rút gọn được thay bằng panel R4 chung"})
                continue
            g = groups[(old["unit_id"], old["realization"])]
            parent = {"run_signature": identity["sha256"], "asset_hash": g["asset"]["sha256"], "upstream_hash": g["shared_hash"],
                      "node_hashes": g["hashes"], "donor_hash": None}
            prompt = native_prompt(variant_state(g["state"], g["asset"], g["donor"], decision["variant"]))
            make_job(old["phase"], context, old["org"], prompt, parent, path, identity["bank_id"], identity["sha256"])

    r4_units = {u["unit"]["id"]: u for u in r4["units"]}
    for context in r4["jobs"]:
        key = context["unit_id"]
        path = root / R4 / f"shards/org{context['org']}/decisions/{key}_{context['variant']}_n{context['repeat']}.json"
        if key not in selected:
            excluded.append({"origin_path": path.relative_to(root).as_posix(), "context": context, "reason": "ngoài panel chín điểm chọn bằng metadata"})
            continue
        u = r4_units[key]; g = groups[(key, 0)]
        scope = next(s for s in bank["schedule"] if (s["symbol"], s["fold"]) == (u["unit"]["symbol"], u["unit"]["fold"]))
        validate_donor(scope, u["donor_index"], u["unit"]["decision"])
        donor_path = root / BANK / f"features/{u['unit']['symbol']}_{u['donor_index']}.json"
        donor = checked(donor_path); source(donor_path)
        require(u["asset_hash"] == g["asset"]["sha256"] and u["donor_hash"] == donor["sha256"], "R4 sai asset/donor")
        require(u["upstream_parent_hash"] == digest({"run_signature": identity["sha256"], "node_hashes": g["hashes"]}), "R4 sai corrected parent")
        base = native_prompt(variant_state(g["state"], g["asset"], donor, "AS"))
        prompt = controlled_prompt(prompt_parts(base), g["asset"], donor, context["variant"])
        require(prompt == u["prompts"][context["variant"]] and digest(prompt) == u["prompt_hashes"][context["variant"]], "R4 prompt đổi")
        make_job("factorial", context, context["org"], prompt, old_r4_parent(r4, u, context["variant"]), path, r4["sha256"], r4["sha256"])

    require(Counter(j["phase"] for j in jobs) == {"main": 204, "upstream": 36, "factorial": 135}, "Sai whitelist 375 jobs")
    require(len({j["id"] for j in jobs}) == 375, "Whitelist trùng identity")
    loads = {i: 0 for i in range(1, 6)}
    for row in sorted(jobs, key=lambda j: (-len(j["prompt"]), j["id"])):
        worker = min(loads, key=lambda i: (loads[i], i)); row["worker"] = worker
        loads[worker] += len(row["prompt"])
    whitelist_contexts = {digest(j["context"]) for j in jobs}
    for folder in (root / R1, root / R4):
        for path in folder.glob("shards/org*/calls/*.request.json"):
            req = checked(path)
            if digest(scientific_context(req["context"])) in whitelist_contexts:
                for suffix in ("request", "response", "response_digest", "error"):
                    raw = path.with_name(path.name.replace(".request.", f".{suffix}."))
                    if raw.exists(): source(raw)
    cleanup = []
    for row in excluded:
        path = root / row["origin_path"]
        if path.exists():
            record = checked(path)
            candidates = {path, *[path.parent.parent / r["path"] for r in record["call_hashes"]]}
            for attempt in record["request_ids"]:
                receipt = path.parent.parent / f"calls/{attempt}.response_digest.json"
                if receipt.exists(): candidates.add(receipt)
            for candidate in sorted(candidates):
                require(candidate not in sources, "Không được xóa file nguồn còn dùng")
                cleanup.append({"path": candidate.relative_to(root).as_posix(), "sha256": sha(candidate)})
    provider_states = []
    for folder in (root / R1, root / R4):
        with closing(sqlite3.connect((folder / "quota.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)) as db:
            provider_states.extend({"origin": folder.relative_to(root).as_posix(), "org": org, "model": model, "kind": kind, "until_at": until}
                                   for org, model, kind, until in db.execute("SELECT org,model,kind,until_at FROM provider_state"))
    value = signed({"schema_version": "revision_minimal_v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                    "scope": "historical exploratory; amendment sau một phần inference, không preregistered confirmatory",
                    "selection": "round-robin mã xếp chữ cái, ngày tăng dần; chỉ metadata từ panel R4 đã khóa",
                    "panel": [u["unit"] for u in panel], "contrasts": CONTRASTS,
                    "origin_runs": {"r1": identity["sha256"], "r4": r4["sha256"]}, "runtime": runtime(),
                    "jobs": jobs, "excluded_jobs": excluded, "cleanup_candidates": cleanup,
                    "counts": {phase: {"expected": sum(j["phase"] == phase for j in jobs),
                                       "reused": sum(j["phase"] == phase and j["reuse"] is not None for j in jobs),
                                       "missing": sum(j["phase"] == phase and j["reuse"] is None for j in jobs)}
                               for phase in ("main", "upstream", "factorial")},
                    "provider_states": provider_states, "new_vision_calls": 0,
                    "execution": {"model": r4["model"], "temperature": r4["temperature"], "max_tokens": r4["max_tokens"],
                                  "internal_attempt_caps": None, "automatic_deadline": False, "policy": "provider_only"},
                    "sources": [{"path": p.relative_to(root).as_posix(), "sha256": sha(p)} for p in sorted(sources)]})
    run.mkdir(parents=True)
    write_json(run / "manifest.json", value, True)
    from core.revision72_quota import PoolLedger
    ledger = PoolLedger(run / "quota.sqlite3", value["sha256"])
    for row in provider_states:
        if row["until_at"] > ledger.clock() or row["kind"] in ("key_error", "incompatible"):
            ledger.block(row["org"], row["model"], row["kind"], max(0, row["until_at"] - ledger.clock()), "Trạng thái provider kế thừa từ run nguồn")
    return value


def verify_manifest(root: Path, run: Path) -> dict:
    """Kiểm freeze độc lập; không yêu cầu các jobs bị loại còn nằm trong Git."""
    manifest = checked(run / "manifest.json")
    require(manifest["runtime"] == runtime(), "Runtime adapter đã đổi; không resume")
    for row in manifest["sources"]:
        require(sha(root / row["path"]) == row["sha256"], "Nguồn frozen đổi: " + row["path"])
    ids = set()
    for job in manifest["jobs"]:
        require(job["id"] not in ids and digest(job["prompt"]) == job["prompt_hash"] and len(job["prompt"]) < 6500, "Identity/prompt hash/budget sai")
        ids.add(job["id"])
    return manifest


def collect(root: Path, run: Path, manifest: dict) -> list[dict]:
    """Kiểm reuse và executions mới, chặn ID trùng và checkpoint ngoài whitelist."""
    results, ids, expected = [], set(), set()
    for job in manifest["jobs"]:
        path = point_path(run, job); expected.add(path.resolve())
        if job["reuse"] is not None:
            require(not path.exists(), "Job reuse có thêm execution mới ngoài dự kiến")
            path = root / job["reuse"]["path"]
            require(sha(path) == job["reuse"]["sha256"], "Reuse checkpoint đã đổi")
            record = verify_record(path, job, job["origin_parent"], job["origin_bank_id"], job["origin_epoch"])
        elif path.exists():
            record = verify_record(path, job, parent_for(manifest, job), manifest["sha256"], manifest["sha256"])
        else:
            continue
        require(not ids.intersection(record["request_ids"]), "Một raw response bị dùng cho nhiều jobs/repeats")
        ids.update(record["request_ids"])
        results.append({"job_id": job["id"], "phase": job["phase"], "context": job["context"],
                        "prediction": record["prediction"], "origin": "reuse" if job["reuse"] else "new",
                        "path": path.relative_to(root).as_posix(), "request_ids": record["request_ids"]})
    actual = {p.resolve() for p in run.glob("shards/org*/decisions/*.json")}
    require(actual <= expected, "Checkpoint ngoài whitelist")
    return results
