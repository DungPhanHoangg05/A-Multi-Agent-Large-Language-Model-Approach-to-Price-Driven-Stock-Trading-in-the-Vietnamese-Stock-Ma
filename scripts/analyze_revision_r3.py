"""Audit raw identity và phân tích lặp R3 từ lượt R1 hoàn tất, không gọi API."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from core.revision72_analysis import verify, target
from core.revision72_run import checked
from core.revision_baselines import daily_ledger, load_prices
from core.revision_common_study import digest, read_json
from core.revision_r3_repeats import (CONTRASTS, METRICS, POLICY, array_metrics, describe,
    panel_identity, per_run_summary, resample)
from scripts.analyze_revision_r2 import csv_text, json_text, sha, verify_closed_r1
from scripts.finalize_revision_r1 import fmt, table, validate
from utils.statistical_tests import binary_classification_metrics

BANK = ROOT / "outputs/revision/r1_72h_bank_v2"
RUN = ROOT / "outputs/revision/r1_72h_run_v2"
OUTPUT = ROOT / "outputs/revision/r3_repeats_v1"


def verify_prior_manuscript() -> None:
    """Nguồn R2 hiện đã chuyển sang R3 được đối soát đúng source ZIP lịch sử."""
    verify_closed_r1()
    folder = ROOT / "outputs/revision/r2_manuscript_v1"
    manifest = read_json(folder / "manifest.json")
    with zipfile.ZipFile(folder / "sources.zip") as archive:
        for r in manifest["sources"]:
            if sha(ROOT / r["path"]) != r["sha256"] and hashlib.sha256(archive.read(r["path"])).hexdigest() != r["sha256"]:
                raise ValueError("Nguồn manuscript R2 không khớp archive")
    for r in manifest["outputs"]:
        if sha(folder / r["path"]) != r["sha256"]:
            raise ValueError("Manuscript R2 đã bị sửa")


def legacy_inventory() -> tuple[list[dict], list[Path]]:
    """Tên default không chứng minh cùng input/prompt/model hoặc độc lập giữa các lần chạy."""
    manifest = read_json(ROOT / "outputs/revision/r1_legacy/manifest.json")
    files = []
    for r in manifest["sources"]:
        if r["path"].startswith("outputs/backtest_result/") and r["path"].endswith(".json"):
            p = ROOT / r["path"]
            if read_json(p)["symbol"] in ("FPT", "VCB", "VNM"):
                files.append(p)
    for symbol in ("FPT", "VNM"):
        files += [ROOT / f"outputs/robustness/clean_a20/checkpoint_{kind}_{symbol}_{value}.json"
                  for kind, value in (("hyperparams", "w45"), ("norm", "zscore_tanh"), ("weights", "default"))]
    files += [ROOT / f"outputs/ablation/clean_a20/checkpoint_ablation_{s}.json" for s in ("FPT", "VCB", "VNM")]
    rows = []
    for path in sorted(files):
        value = read_json(path)
        points = value["test_points"]
        for variant in ("full", "base_reports"):
            prediction = [p["variants"]["full" if variant == "full" else "baseline"]["prediction"]
                          if "variants" in p else p["pred_full" if variant == "full" else "pred_no_alpha"] for p in points]
            metrics = binary_classification_metrics([p["actual_direction"] for p in points], prediction)
            rows.append({"path": path.relative_to(ROOT).as_posix(), "source_sha256": sha(path), "symbol": value["symbol"],
                "variant": variant, "n_units": len(points), "window_size_recorded": value.get("window_size", "unknown"),
                "scenario_recorded": value.get("scenario", "unknown"), "protocol_recorded": value.get("protocol", "unknown"),
                "first_cutoff": points[0]["window_end"], "last_cutoff": points[-1]["window_end"],
                "cutoff_sequence_hash": digest([p["window_end"] for p in points]),
                "recorded_cycle_endpoints_hash": digest([{k: p.get(k) for k in ("window_end", "entry_time", "exit_time", "entry_open", "exit_close")} for p in points]),
                "prediction_hash": digest(prediction), "accuracy": metrics["accuracy"], "n_valid":metrics["n_valid"], "n_excluded":metrics["n_excluded"],
                "model_revision": "unknown", "prompt_hash": "unknown", "code_commit": "unknown",
                "comparison_status": "nominal default in legacy manuscript; actual complete inputs/reports/config and run independence unverified; not treated as repeated-run variance"})
    return rows, files


def request_audit(requests: dict[str, dict], paths: dict[str, Path]) -> tuple[list[dict], dict]:
    """Lưu config thực được SDK ghi cùng timestamp/provider/epoch và hash prompt."""
    from langchain_groq import ChatGroq
    source = inspect.getsource(ChatGroq)
    if "if self.temperature == 0:" not in source or "self.temperature = 1e-8" not in source:
        raise ValueError("SDK adapter khác source đã khảo sát; cần rà lại temperature")
    rows, temperatures = [], Counter()
    for attempt, value in sorted(requests.items()):
        metadata, context = value["model_metadata"], value["context"]
        temperatures[str(metadata.get("ls_temperature"))] += 1
        path = paths[attempt]
        response = path.with_name(path.name.replace(".request.", ".response."))
        error = path.with_name(path.name.replace(".request.", ".error."))
        result = read_json(response) if response.exists() else None
        output = (result["response"].get("llm_output") or {}) if result else {}
        stage = context["stage"]
        if metadata["ls_model_name"] != context["model"] or metadata["ls_max_tokens"] != (2048 if stage == "decision" else 1024):
            raise ValueError("SDK model/output cap khác hợp đồng")
        rows.append({"attempt_id": attempt, **context, "home_shard": int(path.parent.parent.name[3:]),
            "actual_provider_org": int(context.get("provider_org", path.parent.parent.name[3:])),
            "execution_epoch": context.get("execution_epoch", "original"),
            "started_at_utc": value["started_at_utc"], "ended_at_utc": result["ended_at_utc"] if result else None,
            "response_exists": response.exists(), "error_exists": error.exists(),
            "actual_messages_hash": digest(value["messages"]), "invocation_parameters_hash": digest(value["invocation_parameters"]),
            "sdk_model": metadata["ls_model_name"], "sdk_temperature": metadata["ls_temperature"],
            "sdk_max_tokens": metadata["ls_max_tokens"], "provider_reported_model": output.get("model_name", "unreported"),
            "system_fingerprint": output.get("system_fingerprint"), "api_seed_observed": value["invocation_parameters"].get("seed"),
            "request_sha256": sha(path), "response_sha256": sha(response) if response.exists() else None,
            "error_sha256": sha(error) if error.exists() else None})
    if set(temperatures) != {"1e-08"}:
        raise ValueError("Có temperature khác trong archive; không gộp thành cùng config")
    return rows, {"declared_temperature": 0.0, "sdk_reported_temperature": 1e-8, "n_matching_attempts": len(rows),
        "adapter_version": "langchain-groq 1.1.2", "adapter_source_sha256": sha(Path(inspect.getfile(ChatGroq))),
        "adapter_rule": "if self.temperature == 0: self.temperature = 1e-8",
        "scope": "SDK client property/metadata audited, not a provider wire trace or immutable weight revision; no hosted seed is supplied in the frozen caller"}


def analyze_panel(name: str, unit_ids: list[str], variants: list[str], upstream: bool, bank: dict,
                  records: list[dict], requests: dict[str, dict], frames: dict, raw: dict[str, dict]) -> dict:
    """Tái lập metrics/ledger trên đúng panel và dựng tensor resampling có pairing."""
    identity = panel_identity(records, requests, unit_ids, variants, upstream)
    units = [u for u in bank["units"] if u["id"] in unit_ids]
    blocks = sorted({u["fold"] for u in units})
    index = {(r["context"]["unit_id"], r["context"]["realization"], r["context"]["variant"], r["context"]["repeat"]): r for r in identity["records"]}
    truths = {}
    for unit in units:
        f, i = frames[unit["symbol"]], unit["decision"]
        labels, _ = target(f, [i], bank["protocol"])
        truths[unit["id"]] = "UP" if labels[0] else "DOWN"
    tensor = {v: np.zeros((3, len(blocks), 4), dtype=int) for v in variants}
    account_tensor = {v: np.zeros((3, len(blocks), 2), dtype=float) for v in variants}
    accounts, daily, run_metrics, lineage = [], [], [], []
    for variant in variants:
        for run in range(3):
            prediction = {u["id"]: index[(u["id"], run if upstream else 0, variant, 0 if upstream else run)]["prediction"] for u in units}
            metrics = binary_classification_metrics([truths[u["id"]] for u in units], [prediction[u["id"]] for u in units])
            values = []
            for symbol, fold in sorted({(u["symbol"], u["fold"]) for u in units}):
                selected = sorted([u for u in units if (u["symbol"], u["fold"]) == (symbol, fold)], key=lambda u: u["decision"])
                ledger = daily_ledger(frames[symbol], [(u["decision"] + 1, u["decision"] + 3, int(prediction[u["id"]] == "LONG")) for u in selected], bank["protocol"])
                key = {"panel": name, "variant": variant, "execution": run, "symbol": symbol, "fold": fold}
                daily.extend({**key, **row} for row in ledger.pop("daily"))
                accounts.append({**key, "n_panel_cycles": len(selected), **ledger})
                values.append(ledger["net_return_pct"])
                account_tensor[variant][run, blocks.index(fold)] += [ledger["net_return_pct"], 1]
            for b, block in enumerate(blocks):
                part = [u for u in units if u["fold"] == block]
                c = binary_classification_metrics([truths[u["id"]] for u in part], [prediction[u["id"]] for u in part])["confusion"]
                tensor[variant][run, b] = [c[k] for k in ("tp", "fn", "tn", "fp")]
            pooled = array_metrics(tensor[variant][run].sum(axis=0))
            for metric, value in pooled.items():
                if (metrics[metric] is None) != (not np.isfinite(value)) or (metrics[metric] is not None and not np.isclose(metrics[metric], value, atol=1e-12)):
                    raise ValueError("Tensor metric không khớp utility chuẩn")
            run_metrics.append({"panel": name, "variant": variant, "execution": run, "n_units": len(units),
                **{k: metrics[k] for k in METRICS if k != "mean_account_net_return_pct"},
                "mean_account_net_return_pct": float(np.mean(values)), "n_accounts": len(values), "confusion": metrics["confusion"]})
    for record in identity["records"]:
        c = record["context"]
        request = raw[record["request_ids"][-1]]
        lineage.append({"panel": name, **c, "request_id": record["request_ids"][-1],
            "prompt_hash": request["actual_messages_hash"], "request_started_utc": request["started_at_utc"],
            "actual_provider_org": request["actual_provider_org"], "execution_epoch": request["execution_epoch"],
            "upstream_hash": record["parent"]["upstream_hash"], "asset_hash": record["parent"]["asset_hash"],
            "donor_hash": record["parent"].get("donor_hash"), "node_hashes": record["parent"]["node_hashes"],
            "decision_source": record["decision_source"], "fallback_reason": record["fallback_reason"], "prediction": record["prediction"]})
    summaries = {v: per_run_summary([r for r in run_metrics if r["variant"] == v]) for v in variants}
    contrasts = []
    for a, b in CONTRASTS:
        if a not in variants or b not in variants:
            continue
        left, right = ([r for r in run_metrics if r["variant"] == v] for v in (a, b))
        delta = {k: [None if x[k] is None or y[k] is None else x[k] - y[k] for x, y in zip(left, right)] for k in METRICS}
        contrasts.append({"contrast": f"{a}-{b}", "by_execution": delta, "summary": {k: describe(v) for k, v in delta.items()}})
    intervals = resample(tensor, account_tensor)
    summary = {"panel": name, "n_units": len(units), "n_symbols": len({u["symbol"] for u in units}),
        "n_dates": len({u["date"] for u in units}), "n_blocks": len(blocks), "blocks": blocks,
        "n_runs": 3, "n_accounts_per_execution": len(accounts) // (3 * len(variants)),
        "n_decisions": identity["n_records"], "n_unique_successful_requests": identity["n_unique_successful_requests"],
        "up_support": sum(v == "UP" for v in truths.values()), "down_support": sum(v == "DOWN" for v in truths.values()),
        "summaries": summaries, "contrasts": contrasts, "intervals": intervals,
        "mean_pairwise_disagreement": {v: float(np.mean([r["pairwise_disagreement"] for r in identity["disagreement_by_cutoff"] if r["variant"] == v])) for v in variants}}
    return {"summary": summary, "run_metrics": run_metrics, "accounts": accounts, "daily": daily,
        "lineage": lineage, "disagreement": [{"panel": name, **r} for r in identity["disagreement_by_cutoff"]]}


def payloads() -> dict[str, str]:
    """Đọc raw archive và tái tạo mọi kết quả R3 trước khi xuất release."""
    verify_prior_manuscript()
    records_all = verify(ROOT, BANK, RUN)
    validate()
    records = [r for r in records_all if not r["context"]["smoke"]]
    bank = read_json(BANK / "manifest.json")
    frames, _ = load_prices(ROOT / bank["protocol"]["price_snapshot"], bank["protocol"]["price_quality_policy"])
    request_paths = {p.name.split(".")[0]: p for p in RUN.glob("shards/org*/calls/*.request.json")}
    requests = {k: checked(p) for k, p in request_paths.items()}
    request_rows, adapter = request_audit(requests, request_paths)
    raw = {r["attempt_id"]: r for r in request_rows}
    if len({a for r in records_all for a in r["request_ids"]}) != sum(len(r["request_ids"]) for r in records_all):
        raise ValueError("Raw decision ID bị tái dùng giữa checkpoints")
    panels = [analyze_panel("decision", bank["panel"], ["B", "A", "S", "AS", "P"], False, bank, records, requests, frames, raw),
        analyze_panel("upstream", [u["id"] for u in bank["units"] if u["upstream"]], ["B", "AS"], True, bank, records, requests, frames, raw)]
    for panel in panels:
        prior=read_json(RUN/"analysis"/(panel["summary"]["panel"]+"_panel.json"))
        for variant in prior["results"]:
            current=[r for r in panel["run_metrics"] if r["variant"]==variant["variant"]]
            for actual,old in zip(current,variant["by_repeat"]):
                if any(actual[k]!=old[k] for k in METRICS if k!="mean_account_net_return_pct"):
                    raise ValueError("Repeated metrics không khớp evidence R1 đã khóa")
    needed_nodes = {(r["unit_id"], r["realization"]) for p in panels for r in p["lineage"]}
    nodes = []
    for path in sorted(RUN.glob("shards/org*/nodes/*.json")):
        node = checked(path)
        c = node["context"]
        if (c["unit_id"], c["realization"]) not in needed_nodes:
            continue
        if c["node"] != "Indicator Agent" and not node["request_ids"]:
            raise ValueError("Upstream realization không có vision response")
        for attempt in node["request_ids"]:
            req = requests[attempt]["context"]
            if any(req.get(k) != c.get(k) for k in ("unit_id", "realization", "node", "stage")):
                raise ValueError("Upstream request khác realization/node")
        nodes.append({**c, "node_hash": node["sha256"], "input_hash": node["parent"]["input_hash"],
            "asset_hash":node["parent"]["asset_hash"], "run_signature":node["parent"]["run_signature"],
            "request_ids": node["request_ids"], "state_hash": digest(node["state"]),
            "successful_request_prompt_hashes": [raw[a]["actual_messages_hash"] for a in node["request_ids"]]})
    vision_ids = [a for n in nodes if n["node"] != "Indicator Agent" for a in n["request_ids"]]
    if len(vision_ids) != len(set(vision_ids)) or len(nodes) != 3 * len(needed_nodes):
        raise ValueError("Vision response bị tái dùng hoặc thiếu node của panel")
    identity = read_json(RUN / "run_manifest.json")
    order = []
    panel_keys={(r["unit_id"],r["realization"],r["variant"],r["repeat"]) for p in panels for r in p["lineage"]}
    index = {(r["context"]["unit_id"], r["context"]["realization"], r["context"]["variant"], r["context"]["repeat"]): r for r in records}
    for job in identity["jobs"]:
        if not any((job["unit_id"], job["realization"], d["variant"], d["repeat"]) in panel_keys for d in job["decisions"]):
            continue
        planned = [f"{d['variant']}/{d['repeat']}" for d in job["decisions"]]
        actual = sorted([(raw[index[(job["unit_id"],job["realization"],d["variant"],d["repeat"])]["request_ids"][-1]]["started_at_utc"], f"{d['variant']}/{d['repeat']}") for d in job["decisions"]])
        observed = [v for _, v in actual]
        order.append({"unit_id":job["unit_id"], "realization":job["realization"], "phase":job["phase"],
            "planned_within_job_order": ";".join(planned), "observed_success_order": ";".join(observed), "order_matches": planned==observed})
    legacy, _ = legacy_inventory()
    selected = {(r["unit_id"],r["realization"],r["variant"],r["repeat"]) for p in panels for r in p["lineage"]}
    overlap = sorted(set(bank["panel"]) & {u["id"] for u in bank["units"] if u["upstream"]})
    config = {"frozen_run_signature":identity["sha256"], "bank_id": bank["bank_id"], "frozen_source_hashes":identity["sources"],
        "temperature_audit":adapter, "window_size":45, "alpha_norm_method":"zscore_tanh", "alpha_weights":None,
        "run_git_commit":"unknown; authoritative frozen source-byte hashes retained, no retrospective commit inference",
        "served_weight_revision":"unverified; recorded aliases/fingerprints are not pinned weights",
        "n_request_attempts":len(request_rows), "n_successes":sum(r["response_exists"] for r in request_rows),
        "n_errors":sum(r["error_exists"] for r in request_rows),
        "actual_provider_orgs":dict(sorted(Counter(str(r["actual_provider_org"]) for r in request_rows).items())),
        "provider_identity_scope":"routing key-slot index (original calls use their home shard); org identity mapping is author-confirmed, not immutable provider attestation",
        "n_order_jobs":len(order), "n_order_matches":sum(r["order_matches"] for r in order),
        "order_scope":"r0 B/AS comes from the main pair; remaining A/S/P r0 executed later. r1/r2 variant order rotates; quota pauses/provider routing are observational confounds, not randomized provider experiments",
        "n_panel_union_decisions":len(selected), "n_panel_vision_successes":len(vision_ids),
        "overlap_units":overlap, "n_shared_r0_decisions":2*len(overlap),
        "variance_identification":"different panels and only decision repeat 0 under regenerated upstream; no crossed 3x3 design or subtraction of variances. Overlap does not create independent stage components",
        "r0_reuse":"same actual checkpoint contributes to main/panels by design; distinct repeated executions require their own raw successful request IDs"}
    result = {"policy.json": json_text(POLICY), "configuration_manifest.json":json_text(config),
        "requests.csv":csv_text(request_rows), "decision_lineage.json":json_text([r for p in panels for r in p["lineage"]]),
        "upstream_lineage.json":json_text(nodes), "order_audit.csv":csv_text(order),
        "legacy_default_inventory.csv":csv_text(legacy),
        "per_execution_metrics.json":json_text([r for p in panels for r in p["run_metrics"]]),
        "account_returns.csv":csv_text([r for p in panels for r in p["accounts"]]),
        "daily_panel_ledgers.csv":csv_text([r for p in panels for r in p["daily"]]),
        "disagreement_by_cutoff.json":json_text([r for p in panels for r in p["disagreement"]]),
        "report.json":json_text({"panels":[p["summary"] for p in panels], "n_new_api_calls":0,
            "n_new_predictions":0,"ensemble_evaluated":False,"best_run_selected":False,
            "scope":"conditional selected-panel descriptive repeat distributions, not 102-unit SD or full-grid variance decomposition"})}
    result.update(tex_tables(panels))
    return result


def tex_tables(panels: list[dict]) -> dict[str,str]:
    """Bảng chính gọn; JSON giữ đủ mọi metric, median/range và undefined CI counts."""
    body, returns, contrasts, classification = [], [], [], []
    for panel in panels:
        p=panel["summary"]
        for variant,s in p["summaries"].items():
            b=s["balanced_accuracy"];ci=p["intervals"]["variants"][variant]["balanced_accuracy"]
            interval=ci["percentile_95"]
            body.append(" & ".join([p["panel"],variant,str(p["n_units"]),fmt(b["mean"]),fmt(b["sd"]),fmt(b["median"]),
                f"[{fmt(b['min'])}, {fmt(b['max'])}]",f"[{interval[0]*100:.2f}, {interval[1]*100:.2f}]"]) + r" \\")
            classification.append(" & ".join([p["panel"],variant,str(p["n_units"]),fmt(s["accuracy"]["mean"]),fmt(s["accuracy"]["sd"]),
                fmt(s["mcc"]["mean"],False),fmt(s["mcc"]["sd"],False),fmt(s["long_rate"]["mean"])]) + r" \\")
            b=s["mean_account_net_return_pct"];ci=p["intervals"]["variants"][variant]["mean_account_net_return_pct"]["percentile_95"]
            returns.append(" & ".join([p["panel"],variant,str(p["n_accounts_per_execution"]),*[f"{b[k]:.2f}" for k in ("mean","sd","median")],
                f"[{b['min']:.2f}, {b['max']:.2f}]",f"[{ci[0]:.2f}, {ci[1]:.2f}]"]) + r" \\")
        for c in p["contrasts"]:
            s=c["summary"]["balanced_accuracy"];ci=p["intervals"]["contrasts"][c["contrast"]]["balanced_accuracy"]["percentile_95"]
            contrasts.append(" & ".join([p["panel"],c["contrast"],fmt(s["mean"]),fmt(s["sd"]),fmt(s["median"]),
                f"[{fmt(s['min'])}, {fmt(s['max'])}]",f"[{ci[0]*100:.2f}, {ci[1]*100:.2f}]"]) + r" \\")
    finite="; ".join(f"{p['summary']['panel']} {next(iter(p['summary']['intervals']['variants'].values()))['balanced_accuracy']['n_defined']}/10,000" for p in panels)
    note="Three executions per row. SD uses ddof=1. Intervals resample whole blocks and paired execution indices together (10,000 draws, seed 20261102). Finite BA draws: "+finite+". Other undefined counts are in JSON; return intervals use all draws. Conditional finite-draw percentiles are descriptive, with only three runs/blocks; no calibrated-coverage claim. Panel support differs and is not pooled."
    return {"r3_variability.tex":table("Selected-panel balanced accuracy across three actual executions (percent).","tab:r3_variability","llrrrrrr",
        "Panel & Variant & N & Mean & SD (pp) & Median & Range & Descriptive interval",body,note),
        "r3_classification.tex":table("Accuracy, MCC and LONG frequency across the same three executions.","tab:r3_classification","llrrrrrr",
        "Panel & Variant & N & Acc. mean & Acc. SD (pp) & MCC mean & MCC SD & LONG mean",classification,
        "Percentages except MCC. Per-execution scores and mean/SD/median/range/conditional intervals for every metric are retained in the machine-readable report. These are panel-only distributions, not 102-unit one-pass uncertainty."),
        "r3_returns.tex":table("Net account-return dispersion on fixed panel cycles (percent).","tab:r3_returns","llrrrrrr",
        "Panel & Variant & Accounts & Mean & SD & Median & Range & Descriptive interval",returns,
        "Each return is a mean over 13 decision-panel or nine upstream-panel symbol--block accounts. Accounts use the same frozen prices/costs and only panel cycles; not a portfolio or the broad 51-account result. "+note),
        "r3_contrasts.tex":table("Paired balanced-accuracy differences by execution (percentage points).","tab:r3_contrasts","llrrrrr",
        "Panel & Contrast & Mean & SD & Median & Range & Descriptive interval",contrasts,note)}


def sources() -> list[Path]:
    """Code mới và manifest đã khóa đủ để truy nguồn raw archive, không sao chép raw lần nữa."""
    _,legacy=legacy_inventory()
    return [ROOT/p for p in ["core/revision_r3_repeats.py","scripts/analyze_revision_r3.py","tests/test_revision_r3_repeats.py",
        "scripts/analyze_revision_r2.py","scripts/finalize_revision_r1.py","core/revision72_analysis.py","core/revision72_run.py",
        "core/revision_baselines.py","utils/statistical_tests.py","revision/r1_72h_protocol.json",
        "outputs/revision/r1_72h_bank_v2/manifest.json","outputs/revision/r1_72h_run_v2/run_manifest.json",
        "outputs/revision/r1_72h_run_v2/analysis/manifest.json","outputs/revision/r2_manuscript_v1/manifest.json",
        "outputs/revision/r2_manuscript_v1/sources.zip"]]+legacy


def main() -> None:
    """Không ghi đè release; --check tái lập ở tiến trình khác và đối chiếu source hash."""
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--check",action="store_true");args=parser.parse_args()
    if OUTPUT.exists() and not args.check:raise FileExistsError("Release R3 đã có; dùng --check")
    if args.check:
        m=read_json(OUTPUT/"manifest.json")
        for group,base in (("sources",ROOT),("outputs",OUTPUT)):
            for r in m[group]:
                if sha(base/r["path"])!=r["sha256"]:raise ValueError("Hash R3 đã đổi: "+r["path"])
    generated=payloads()
    for name,text in generated.items():
        path=OUTPUT/name
        if args.check:
            if path.read_bytes()!=text.encode("utf-8"):raise ValueError("R3 không tái lập: "+name)
        else:OUTPUT.mkdir(exist_ok=True);path.write_text(text,encoding="utf-8",newline="\n")
        if name.endswith(".tex"):
            p=ROOT/"paper/generated"/name
            if args.check:
                if p.read_bytes()!=text.encode("utf-8"):raise ValueError("Bảng R3 khác release")
            else:p.write_text(text,encoding="utf-8",newline="\n")
    if not args.check:
        m={"schema_version":"revision_r3_repeat_release_v1","created_utc":datetime.now(timezone.utc).isoformat(),
            "sources":[{"path":p.relative_to(ROOT).as_posix(),"sha256":sha(p)} for p in sources()],
            "outputs":[{"path":n,"sha256":sha(OUTPUT/n)} for n in generated]}
        (OUTPUT/"manifest.json").write_text(json_text(m),encoding="utf-8",newline="\n")
    print(f"PASS: R3 {'tái lập' if args.check else 'đã xuất'} {len(generated)} artifacts; không gọi API.")


if __name__=="__main__":main()
