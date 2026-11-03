"""Đối soát offline T01; chỉ ghi bằng chứng mới, không sửa hai run đã khóa."""

from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def no_network(event: str, args: tuple) -> None:
    """Chặn kết nối/DNS ngay cả khi dependency vô tình yêu cầu network."""
    if event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname"}:
        raise RuntimeError("Audit offline không được phép truy cập network")


sys.addaudithook(no_network)

from core.revision72_analysis import verify
from core.revision72_provider import scientific_context
from core.revision72_run import checked, freeze, variant_state
from core.revision_baselines import load_prices
from core.revision_common_study import (
    FrozenSentiment, digest, pack_state, point_state, read_json, restore_state,
)
from core.revision_r4_factorial import VARIANTS, actual_text, controlled_prompt, prompt_parts
from core.revision_r4_run import collect, verify_bank
from scripts.prepare_chart_r4 import native_prompt
from scripts.run_chart_rerun import BANK, RUN, R4_BANK, R4_RUN, sha, verify_preparation


def require(condition: bool, message: str) -> None:
    """Dừng khi có sai lệch; không sửa dữ liệu để làm audit đạt."""
    if not condition:
        raise ValueError(message)


def save(name: str, value: object) -> None:
    """Ghi độc quyền vào release audit mới, không ghi đè bằng chứng."""
    with (OUT / name).open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def inventory() -> dict[str, str]:
    """Hash artifacts/ledger; bỏ cache tạm, bytecode và lock đang được OS giữ."""
    return {p.relative_to(ROOT).as_posix(): sha(p)
            for folder in (RUN, R4_BANK, R4_RUN)
            for p in sorted(folder.rglob("*"))
            if p.is_file() and "work" not in p.relative_to(folder).parts
            and "__pycache__" not in p.parts and p.name != "worker.lock"}


def processes() -> dict:
    """Chỉ xuất PID và runner/command/org; không xuất command line hay môi trường."""
    command = r"""
    $items = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
        $_.Name -match '^(python|pythonw|py)(\.exe)?$' -and
        $_.CommandLine -match 'run_(chart_rerun|revision_72h|revision_r4)\.py'
    } | ForEach-Object {
        $runner = [regex]::Match($_.CommandLine, 'run_(chart_rerun|revision_72h|revision_r4)\.py').Value
        $mode = [regex]::Match($_.CommandLine, '\.py["\s]+(run-r4|run|smoke|status|verify)(\s|$)').Groups[1].Value
        [pscustomobject]@{pid=$_.ProcessId; parent_pid=$_.ParentProcessId; name=$_.Name;
            runner=$runner; mode=$mode; org=[regex]::Match($_.CommandLine, '--org\s+([1-5])').Groups[1].Value}
    })
    ConvertTo-Json -InputObject $items -Compress
    """
    result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                            check=True, capture_output=True, text=True)
    rows = json.loads(result.stdout)
    active = [r for r in rows if r["mode"] in {"run", "run-r4", "smoke", ""}]
    return {"observed_utc": datetime.now(timezone.utc).isoformat(),
            "runner_processes": rows, "inference_or_unknown_processes": active}


def lock_existing(stack: ExitStack) -> list[dict]:
    """Giữ khóa OS trên byte sẵn có trong lúc đọc; không tạo/xóa/ghi lock file."""
    import msvcrt
    rows = []
    for run in (RUN, R4_RUN):
        for org in range(1, 6):
            path = run / f"shards/org{org}/worker.lock"
            require(path.exists() and path.stat().st_size > 0, "Thiếu lock worker sẵn có")
            checksum = sha(path)
            handle = stack.enter_context(path.open("r+b"))
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            rows.append({"path": path.relative_to(ROOT).as_posix(), "sha256": checksum, "exclusive_probe": "PASS"})
    return rows


def raw_audit(run: Path, identity: str, copied: set[str]) -> tuple[dict, dict]:
    """Kiểm toàn bộ raw kể cả calls lỗi/chưa có checkpoint và ledger chỉ đọc."""
    counts: Counter = Counter()
    requests = {}
    for path in sorted(run.glob("shards/org*/calls/*.request.json")):
        req = checked(path)
        attempt = path.name.removesuffix(".request.json")
        require(attempt not in requests and req["attempt_id"] == attempt, "Request ID trùng/sai tên")
        require(req["bank_id"] == identity, "Request sai bank")
        requests[attempt] = req
        reused = path.relative_to(run).as_posix() in copied
        counts["reused_pattern_attempts" if reused else "new_attempts"] += 1
        if reused:
            require(req["context"]["node"] == "Pattern Agent", "Copy ngoài Pattern")
        else:
            require(req["context"].get("execution_epoch") == (
                checked(RUN / "run_manifest.json")["sha256"] if run == RUN else identity), "Epoch sai")
            require(req["context"].get("provider_org") in range(1, 6), "Provider org sai")
        response = path.with_name(f"{attempt}.response.json")
        error = path.with_name(f"{attempt}.error.json")
        require(not (response.exists() and error.exists()), "Call có cả lỗi và response")
        if response.exists():
            value = read_json(response)
            require(value["attempt_id"] == attempt and value["parent_request_hash"] == req["sha256"], "Raw parent sai")
            receipt = read_json(path.with_name(f"{attempt}.response_digest.json"))
            require(receipt["sha256"] == digest(value), "Raw digest sai")
            if "request_hash" in receipt:
                require(receipt["request_hash"] == req["sha256"], "Receipt recovery sai parent")
            counts["reused_responses" if reused else "new_responses"] += 1
        elif error.exists():
            value = read_json(error)
            require(value["attempt_id"] == attempt and value["context"] == req["context"], "Error context sai")
            counts["reused_errors" if reused else "new_errors"] += 1
            counts["error_type_" + value["type"]] += 1
        else:
            counts["unresolved_requests"] += 1
        if req["context"]["stage"] == "decision":
            chars = len(actual_text(req))
            require(chars < 6500, "Raw prompt vượt budget")
            counts["max_decision_prompt_chars"] = max(counts["max_decision_prompt_chars"], chars)
    for suffix in ("response", "response_digest", "error"):
        for path in run.glob(f"shards/org*/calls/*.{suffix}.json"):
            require(path.name.removesuffix(f".{suffix}.json") in requests, "Raw orphan")
    ledger = run / "quota.sqlite3"
    with sqlite3.connect(ledger.resolve().as_uri() + "?mode=ro", uri=True) as db:
        require(db.execute("PRAGMA integrity_check").fetchall() == [("ok",)], "SQLite lỗi")
        expected = checked(RUN / "run_manifest.json")["sha256"] if run == RUN else identity
        require(db.execute("SELECT value FROM identity").fetchall() == [(expected,)], "Ledger sai run")
        rows = db.execute("SELECT id,org,stage,model FROM attempts").fetchall()
        new_ids = {a for a, r in requests.items() if not any(p.endswith(f"/{a}.request.json") for p in copied)}
        require({r[0] for r in rows} == new_ids, "Ledger/raw thiếu hoặc thừa attempts")
        for attempt, org, stage, model in rows:
            context = requests[attempt]["context"]
            require((org, stage, model) == (context["provider_org"], context["stage"], context["model"]), "Ledger routing sai")
        live = db.execute("SELECT org,until_at FROM leases WHERE until_at > ?", (time.time(),)).fetchall()
        states = db.execute("SELECT org,model,kind,until_at FROM provider_state ORDER BY org,model").fetchall()
    require(not live, "Ledger còn lease chưa hết hạn; cần đối soát worker")
    return dict(counts), {"integrity": "PASS", "identity": expected, "attempts": len(rows),
                          "live_leases": live, "provider_states_at_audit": states,
                          "quota_availability": "unverified; chỉ đọc trạng thái cục bộ, không gọi provider"}


def replay_nodes(identity: dict, manifest: dict) -> dict:
    """Khôi phục đúng parent/input từng node và upstream, không gọi node/model."""
    frames, _ = load_prices(ROOT / identity["protocol"]["price_snapshot"], identity["protocol"]["price_quality_policy"])
    store = FrozenSentiment(read_json(BANK / "news.json"))
    units = {u["id"]: u for u in manifest["units"] + manifest["smoke"]}
    expected = {(j["org"], j["unit_id"], j["realization"]) for j in identity["jobs"]}
    expected.update((u["org"], u["id"], 0) for u in manifest["smoke"])
    groups = {}
    all_ids = set()
    total = 0
    for org, key, realization in sorted(expected):
        shard = RUN / f"shards/org{org}"
        paths = [shard / f"nodes/{key}_r{realization}_{n}.json" for n in ("Indicator", "Pattern", "Trend")]
        if not any(p.exists() for p in paths):
            continue
        u = units[key]
        asset = checked(BANK / f"features/{u['symbol']}_{u['decision']}.json")
        initial = point_state(frames[u["symbol"]], u["symbol"], u["decision"], identity["protocol"], store)
        chart = checked(shard / f"charts/{key}.json")
        require(chart["asset_hash"] == asset["sha256"], "Chart sai asset")
        initial.update({k: chart[k] for k in ("pattern_image", "trend_image")})
        state, hashes = initial, []
        for path, node in zip(paths, ("Indicator Agent", "Pattern Agent", "Trend Agent")):
            if not path.exists():
                break
            r = checked(path)
            parent = {"input_hash": digest(pack_state(state)), "asset_hash": asset["sha256"], "run_signature": identity["sha256"]}
            require(r["parent"] == parent and r["context"] == {
                "unit_id": key, "realization": realization, "stage": "upstream", "node": node,
                "model": identity["protocol"]["graph_llm_model"], "smoke": key.startswith("smoke_org")}, "Node parent/context sai")
            for attempt in r["request_ids"]:
                require(attempt not in all_ids, "Raw response dùng cho nhiều nodes")
                all_ids.add(attempt)
                req = checked(shard / f"calls/{attempt}.request.json")
                require(scientific_context(req["context"]) == r["context"], "Raw/node context sai")
            require(node == "Indicator Agent" or bool(r["request_ids"]), "Vision node thiếu response")
            state = {**state, **restore_state(r["state"], initial)}
            hashes.append(r["sha256"])
            total += 1
        if len(hashes) == 3:
            groups[(org, key, realization)] = {"hash": digest(pack_state(state)), "nodes": hashes, "state": state}
    require(total == len(list(RUN.glob("shards/org*/nodes/*.json"))), "Node ngoài lịch/chuỗi đứt")
    return {"groups": groups, "nodes": total, "request_ids": all_ids}


def main() -> None:
    """Chốt bằng chứng hash/count/lineage và danh sách thiếu sau khi mọi kiểm tra đạt."""
    require(not (OUT / "manifest.json").exists(), "Release đã tồn tại; không ghi đè")
    started = datetime.now(timezone.utc).isoformat()
    before_process = processes()
    require(not before_process["inference_or_unknown_processes"], "Còn worker inference/không rõ lệnh")
    with ExitStack() as stack:
        locks = lock_existing(stack)
        before = inventory()
        preparation = verify_preparation()
        identity = freeze(ROOT, BANK, RUN)
        manifest = read_json(BANK / "manifest.json")
        r4 = verify_bank(ROOT, R4_BANK)
        snapshot_path = RUN / "runtime_history/frozen_runtime_sources.json"
        snapshot = checked(snapshot_path)
        archive_path = snapshot_path.with_name("frozen_runtime_sources.zip")
        require(snapshot["run_signature"] == identity["sha256"] and sha(archive_path) == snapshot["archive_sha256"], "Source archive sai identity/hash")
        with ZipFile(archive_path) as archive:
            import hashlib
            require(set(archive.namelist()) == {r["path"] for r in snapshot["files"]}, "Archive thiếu/thừa file")
            for r in snapshot["files"]:
                require(sha(ROOT / r["path"]) == r["sha256"] == hashlib.sha256(archive.read(r["path"])).hexdigest(), "Snapshot source sai")
        for r in preparation["copies"]:
            require(sha(ROOT / r["origin"]) == r["sha256"], "Pattern origin đã đổi")
        records = verify(ROOT, BANK, RUN)
        r4_records = collect(r4, R4_RUN)
        replay = replay_nodes(identity, manifest)
        used = set(replay["request_ids"])
        for path in RUN.glob("shards/org*/decisions/*.json"):
            r = checked(path)
            c = r["context"]
            org = int(path.parent.parent.name[3:])
            g = replay["groups"][(org, c["unit_id"], c["realization"])]
            require(r["parent"]["upstream_hash"] == g["hash"] and r["parent"]["node_hashes"] == g["nodes"], "Decision sai upstream")
            require(r["execution_epoch"] == identity["sha256"], "Checkpoint sai epoch")
            unit = next(u for u in manifest["units"] + manifest["smoke"] if u["id"] == c["unit_id"])
            asset = checked(BANK / f"features/{unit['symbol']}_{unit['decision']}.json")
            donor = checked(BANK / f"features/{unit['symbol']}_{unit['placebo_donor']}.json")
            require(r["parent"]["donor_hash"] == (donor["sha256"] if c["variant"] == "P" else None), "Decision sai donor")
            require(native_prompt(variant_state(g["state"], asset, donor, c["variant"])) == r["state"]["decision_prompt"], "R1 prompt khác upstream/variant")
            for attempt in r["request_ids"]:
                require(attempt not in used, "Response tái dùng giữa checkpoints")
                used.add(attempt)
                req = checked(path.parent.parent / f"calls/{attempt}.request.json")
                require(actual_text(req) == r["state"]["decision_prompt"], "Decision prompt không khớp raw")
        for org in range(1, 6):
            shard = RUN / f"shards/org{org}"
            marker = checked(shard / "smoke_complete.json")
            require(marker["run_signature"] == identity["sha256"] and marker["org"] == org and marker["smoke"], "Smoke marker sai")
            for r in marker["files"]:
                require(sha(shard / r["path"]) == r["sha256"], "Smoke artifacts đã đổi")
        original = checked(ROOT / "outputs/revision/r4_value_bank_v1/manifest.json")
        old_units = {r["unit"]["id"]: r for r in original["units"]}
        require(r4["jobs"] == original["jobs"], "Lịch R4 đổi variant/order/repeat")
        for u in r4["units"]:
            key = u["unit"]["id"]
            matching = [g for (_, unit_id, realization), g in replay["groups"].items()
                        if unit_id == key and realization == 0]
            require(len(matching) == 1, "R4 thiếu/trùng upstream R1")
            g = matching[0]
            require(u["upstream_parent_hash"] == digest({"run_signature": identity["sha256"], "node_hashes": g["nodes"]}), "R4 sai corrected upstream")
            for field in ("unit", "org", "donor_index", "asset_hash", "donor_hash"):
                require(u[field] == old_units[key][field], "Panel/donor R4 đã đổi")
            unit = u["unit"]
            asset = checked(BANK / f"features/{unit['symbol']}_{unit['decision']}.json")
            donor = checked(BANK / f"features/{unit['symbol']}_{u['donor_index']}.json")
            shared = {"stock_name": unit["symbol"], "time_frame": "1 ngày", "language": "vi", "is_backtest": True}
            shared.update({field: g["state"][field] for field in ("indicator_report", "pattern_report", "trend_report")})
            prompt = native_prompt(variant_state(shared, asset, donor, "AS"))
            for variant in VARIANTS:
                require(controlled_prompt(prompt_parts(prompt), asset, donor, variant) == u["prompts"][variant], "R4 prompt khác corrected reports")
        copied = {r["path"] for r in preparation["copies"] if r["path"].endswith(".request.json")}
        r1_raw, r1_ledger = raw_audit(RUN, identity["bank_id"], copied)
        r4_raw, r4_ledger = raw_audit(R4_RUN, r4["sha256"], set())
        require(not (set(p.name for p in RUN.glob("shards/org*/calls/*.request.json")) &
                     set(p.name for p in R4_RUN.glob("shards/org*/calls/*.request.json"))), "Hai run trùng request IDs")
        require(len(r4_records) == len(list(R4_RUN.glob("shards/org*/decisions/*.json"))), "R4 có checkpoint ngoài lịch")
        temporary = [p.relative_to(ROOT).as_posix() for run in (RUN, R4_RUN) for p in run.glob("shards/org*/decisions/*.tmp")]
        require(not temporary, "Còn checkpoint tạm cần recovery")
        jobs = [{"unit_id": j["unit_id"], "org": j["org"], "realization": j["realization"], **d}
                for j in identity["jobs"] for d in j["decisions"]]
        done = {(r["context"]["unit_id"], r["context"]["realization"], r["context"]["variant"], r["context"]["repeat"]) for r in records if not r["context"]["smoke"]}
        missing = [j for j in jobs if (j["unit_id"], j["realization"], j["variant"], j["repeat"]) not in done]
        r4_done = {(r["context"]["unit_id"], r["context"]["variant"], r["context"]["repeat"]) for r in r4_records}
        r4_missing = [j for j in r4["jobs"] if (j["unit_id"], j["variant"], j["repeat"]) not in r4_done]
        after = inventory()
        require(before == after, "Artifacts thay đổi trong khi audit")
        after_process = processes()
        require(not after_process["inference_or_unknown_processes"], "Worker khởi động trong khi audit")
    for row in locks:
        require(sha(ROOT / row["path"]) == row["sha256"], "Lock file đã đổi byte")
    pairs = Counter(r["context"]["unit_id"] for r in records if not r["context"]["smoke"]
                    and r["context"]["realization"] == 0 and r["context"]["repeat"] == 0 and r["context"]["variant"] in {"B", "AS"})
    shard_rows = []
    for org in range(1, 6):
        actual = [r for r in records if not r["context"]["smoke"] and
                  any(j["unit_id"] == r["context"]["unit_id"] and j["org"] == org for j in identity["jobs"])]
        shard_rows.append({"org": org, "r1_complete": len(actual), "r1_missing": sum(j["org"] == org for j in missing),
                           "r4_complete": sum(r["context"]["org"] == org for r in r4_records),
                           "r4_missing": sum(j["org"] == org for j in r4_missing)})
    report = {"schema_version": "chart_resume_audit_v1", "started_utc": started,
              "finished_utc": datetime.now(timezone.utc).isoformat(), "result": "PASS",
              "scope": "T01: kiểm toán offline hai run chưa hoàn tất; không nghiệm thu kết quả nghiên cứu",
              "network": "bị chặn bằng Python audit hook; không đọc credentials/khởi động worker",
              "r1": {"run": RUN.relative_to(ROOT).as_posix(), "bank_id": identity["bank_id"], "run_signature": identity["sha256"],
                     "runtime": identity["runtime"], "source_records": len(identity["sources"]),
                     "archived_source_files": len(snapshot["files"]), "pattern_copy_files": len(preparation["copies"]),
                     "expected_research": len(jobs), "research_complete": len(done), "research_missing": len(missing),
                     "smoke_complete": sum(r["context"]["smoke"] for r in records),
                     "complete_main_pairs": sum(n == 2 for n in pairs.values()), "expected_main_pairs": 102,
                     "nodes_checked": replay["nodes"], "complete_upstream_groups": len(replay["groups"]),
                     "raw": r1_raw, "ledger": r1_ledger},
              "r4": {"run": R4_RUN.relative_to(ROOT).as_posix(), "bank_id": r4["sha256"], "runtime": r4["runtime"],
                     "source_records": len(r4["source_hashes"]), "prompt_reconstructions_checked": len(r4["units"]) * len(VARIANTS),
                     "expected": len(r4["jobs"]), "complete": len(r4_records), "missing": len(r4_missing), "raw": r4_raw, "ledger": r4_ledger},
              "shards": shard_rows, "process_snapshots": [before_process, after_process], "worker_locks": locks,
              "historical_artifacts_unchanged": True, "inventory_files": len(before), "temporary_checkpoints": temporary,
              "checks": ["source/runtime guards", "byte archive/current source", "Pattern copy/origin",
                         "checkpoint/raw hashes", "raw parent/context/response digests", "node input/upstream replay",
                         "raw prediction replay", "smoke receipts", "R4 panel/order/donor/prompt reconstruction",
                         "job/shard membership and missing identities", "read-only ledger identity/attempts",
                         "request-ID isolation", "process inventory and ten OS locks", "before/after byte hashes"],
              "limits": ["Ảnh chụp tiến trình/khóa chỉ phản ánh thời điểm audit, phải kiểm lại trước resume.",
                         "Không xác minh quota/provider org/immutable model revision qua network.",
                         "Không chạy lại unit/E2E/leakage suite vì không đổi runtime/input; không đóng R1–R18.",
                         "Hai ledger là riêng từng run; khóa worker không ngăn hai run cùng dùng key. Tác giả phải chạy tuần tự T02 rồi T03."]}
    save("inventory.json", before)
    save("missing_jobs.json", {"chart_r1_run_v1": missing, "chart_r4_run_v1": r4_missing})
    save("report.json", report)
    sources = sorted(set(before) | {r["path"] for r in identity["sources"]} |
                     {r["path"] for r in preparation["sources"]} | {r["origin"] for r in preparation["copies"]} |
                     {r["path"] for r in snapshot["files"]} | {r["path"] for r in r4["source_hashes"]})
    save("manifest.json", {"schema_version": "chart_resume_audit_manifest_v1",
                           "sources": [{"path": p, "sha256": sha(ROOT / p)} for p in sources],
                           "outputs": [{"path": p.name, "sha256": sha(p)} for p in sorted(OUT.iterdir()) if p.is_file()],
                           "git_head_at_audit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()})
    print(f"T01 PASS: R1 {len(done)}/{len(jobs)}, thiếu {len(missing)}; R4 {len(r4_records)}/{len(r4['jobs'])}, thiếu {len(r4_missing)}.")


if __name__ == "__main__":
    main()
