"""Selection diagnostics trên cutoff frozen; không fit outer-test hoặc đổi selector native."""

from __future__ import annotations

from collections import defaultdict
from contextlib import redirect_stdout
from importlib.metadata import version
import io
from pathlib import Path
import sys
from typing import Any
from unittest.mock import patch

import numpy as np
import pandas as pd

from core import alpha_compare as alpha
from core.revision_alpha_contract import safe
from core.revision_audit import sha256_file
from core.revision_baselines import load_prices
from core.revision_common_study import read_json, write_json
from core.revision_sentiment_inventory import BANK, RUN, require, verify_release

OUTPUT = Path("outputs/revision/alpha_selection_v1")


def ratio(numerator: int | float, denominator: int | float) -> float | None:
    """Không có mẫu số thì undefined, không biến thiếu support thành zero."""
    return float(numerator / denominator) if denominator else None


def correlation(first: Any, second: Any, ranked: bool = False) -> float | None:
    """Correlation trên common finite support; ties dùng average rank, constant ghi null."""
    a, b = np.asarray(first, dtype=float), np.asarray(second, dtype=float)
    require(a.shape == b.shape and a.ndim == 1, "Correlation sai shape")
    mask = np.isfinite(a) & np.isfinite(b); a, b = a[mask], b[mask]
    if len(a) < 2 or np.unique(a).size < 2 or np.unique(b).size < 2: return None
    if ranked: a, b = pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(a, b)[0, 1])


def locked_units(queue: dict) -> list[dict]:
    """Lấy duy nhất main units từ whitelist; repeats/upstream không nhân mẫu số."""
    units = {}
    for job in queue["jobs"]:
        if job["phase"] != "main": continue
        unit = {k: job["unit"][k] for k in ("id", "symbol", "fold", "decision", "date")}
        if unit["id"] in units: require(units[unit["id"]] == unit, "Cùng unit ID nhưng khác cutoff")
        units[unit["id"]] = unit
    require(bool(units), "Không có main cutoff frozen")
    return sorted(units.values(), key=lambda row: (row["symbol"], row["date"], row["id"]))


def cutoff_history(frame: pd.DataFrame, unit: dict, history: int = 600) -> pd.DataFrame:
    """Cắt theo index trước mọi preprocessing; không đọc giá/label sau quyết định."""
    end = int(unit["decision"]) + 1
    require(history == 600 and end >= history and end <= len(frame), "Thiếu prefix 600 hoặc cutoff ngoài snapshot")
    result = frame.iloc[end - history:end].rename(columns={"date": "Datetime"}).copy()
    result["Datetime"] = pd.to_datetime(result["Datetime"], errors="raise")
    require(str(result["Datetime"].iloc[-1].date()) == unit["date"], "Index/date cutoff không khớp whitelist")
    require(result["Datetime"].is_monotonic_increasing and not result["Datetime"].duplicated().any(), "Prefix dates không tăng duy nhất")
    for name in ("Open", "High", "Low", "Close", "Volume"):
        if name in result: result[name] = pd.to_numeric(result[name], errors="coerce").fillna(0.)
    return result


def analyse_cutoff(frame: pd.DataFrame, unit: dict, protocol: dict) -> dict:
    """Chạy nguyên backtest/ranking, chỉ bọc handler để quan sát raw/error và support."""
    history = cutoff_history(frame, unit, protocol["alpha_history"])
    before_volume = frame.iloc[unit["decision"] + 1 - 600:unit["decision"] + 1].get("Volume")
    observed: dict[str, dict] = {}
    def wrapper(key: str, handler: Any) -> Any:
        """Giữ nguyên phép tính và exception; không thay lỗi bằng prediction giả."""
        def invoke(features: pd.DataFrame) -> pd.Series:
            """Ghi raw native trong tiến trình audit rồi trả nguyên Series cho engine."""
            try:
                result = handler(features)
                observed[key] = {"raw": result.copy(), "error": None}
                return result
            except Exception as error:
                observed[key] = {"raw": None, "error": f"{type(error).__name__}: {error}"}
                raise
        return invoke
    registry = dict(alpha.ALPHA_REGISTRY)
    wrapped = {key: (wrapper(key, handler), description) for key, (handler, description) in registry.items()}
    with redirect_stdout(io.StringIO()), patch.dict(alpha.ALPHA_REGISTRY, wrapped):
        metrics = alpha.run_backtest(history, lookahead=3, norm_method=protocol["alpha_norm_method"])
    require(len(metrics) == len(registry) and set(metrics["alpha_id"]) == set(registry), "Engine thiếu/trùng candidate")
    ranked = alpha.rank_alphas(metrics, weights=protocol["alpha_weights"])
    prepared = alpha.build_features(history)
    forward = alpha.build_forward_execution_returns(history, lookahead=3).to_numpy(float)
    candidates = []
    for rank, row in enumerate(ranked.to_dict(orient="records"), 1):
        key = row["alpha_id"]; capture = observed.get(key, {"raw": None, "error": "Handler không trả kết quả"})
        error = capture["error"]; raw = capture["raw"]
        if raw is not None:
            require(len(raw) == len(history), "Raw series khác chiều dài history")
            normalized = alpha.normalize_alpha(raw, protocol["alpha_norm_method"]).to_numpy(float)
            raw_values = raw.to_numpy(float)
        else:
            normalized = np.zeros(len(history)); raw_values = np.full(len(history), np.nan)
        mask = np.isfinite(normalized) & np.isfinite(forward)
        raw_mask = np.isfinite(raw_values) & np.isfinite(forward)
        ic = correlation(normalized[mask], forward[mask], ranked=True) if mask.sum() >= 20 and error is None else None
        eligible = bool(error is None and raw_mask.sum() >= 20 and np.unique(raw_values[raw_mask]).size >= 2 and ic is not None)
        if ic is not None: require(abs(ic - row["ic"]) <= .000050001, "IC recompute khác recipe native")
        flip = row["ic"] < 0
        oriented = -normalized if flip else normalized
        current = float(oriented[-1]) if np.isfinite(oriented[-1]) else 0.
        states = np.where(oriented > .1, 1, np.where(oriented < -.1, -1, 0))
        exposure = states == 1
        valid_pairs = np.isfinite(oriented[:-1]) & np.isfinite(oriented[1:])
        nonzero_pairs = valid_pairs & (states[:-1] != 0) & (states[1:] != 0)
        candidates.append({"alpha_id": key, "rank": rank, "composite": float(row["composite"]),
            "native_ic": float(row["ic"]), "ic_unrounded": ic, "ic_sign": None if ic is None else int(np.sign(row["ic"])),
            "native_accuracy": float(row["accuracy"]), "native_sharpe": float(row["sharpe"]), "native_n": int(row["n"]),
            "raw_paired_support": int(raw_mask.sum()), "raw_nonfinite_count": int((~np.isfinite(raw_values)).sum()),
            "diagnostic_eligible": eligible, "handler_error": error, "selected": rank <= 5,
            "current_value": current, "current_signal": int(states[-1]), "ic_flipped": bool(flip),
            "history_adjacent_pairs": int(valid_pairs.sum()),
            "history_state_change_rate": ratio(int(np.count_nonzero((states[1:] != states[:-1]) & valid_pairs)), int(valid_pairs.sum())) if error is None else None,
            "history_long_exposure_toggle_rate": ratio(int(np.count_nonzero((exposure[1:] != exposure[:-1]) & valid_pairs)), int(valid_pairs.sum())) if error is None else None,
            "history_nonzero_sign_flip_rate": ratio(int(np.count_nonzero((states[1:] == -states[:-1]) & nonzero_pairs)), int(nonzero_pairs.sum())) if error is None else None})
    volume = {"volume_field_present": before_volume is not None,
              "raw_volume_nonmissing": int(before_volume.notna().sum()) if before_volume is not None else 0,
              "raw_volume_zero_count": int((before_volume == 0).sum()) if before_volume is not None else 0,
              "uses_real_volume_branch": bool(prepared["_has_vol"].iloc[-1]),
              "volume_units": "unknown_shares_or_lots", "proxy_units": "price_range_when_active",
              "price_fields_missing_before_fill": int(frame.iloc[unit["decision"] + 1 - 600:unit["decision"] + 1][["Open", "High", "Low", "Close"]].isna().to_numpy().sum())}
    return {"unit": unit, "history": {"rows": len(history), "first_date": str(history["Datetime"].iloc[0].date()),
              "last_date": str(history["Datetime"].iloc[-1].date()), "last_observable_label_start_date": str(history["Datetime"].iloc[-4].date()),
              "native_warmup_rows_excluded": 0}, "volume": volume, "registered_count": len(registry),
            "native_ranking_count": len(candidates), "diagnostic_eligible_count": sum(r["diagnostic_eligible"] for r in candidates),
            "selected_ids": [r["alpha_id"] for r in candidates[:5]], "candidates": candidates}


def verify_selected(point: dict, asset: dict) -> None:
    """Đối soát đủ danh tính, thứ tự, value/signal và metrics với asset frozen."""
    factors = asset["alpha_factors"]
    require(len(factors) == 5, "Frozen asset không đủ năm factors")
    for row, factor in zip(point["candidates"][:5], factors):
        template = alpha.get_alpha_template(row["alpha_id"], "vi")
        require((factor["name"], factor["formula"]) == (template["name"], template["formula"]), "Top-five identity/order khác frozen")
        require(factor["value"] == round(row["current_value"], 4), "Value khác frozen")
        signal = {1: "TĂNG", -1: "GIẢM", 0: "TRUNG TÍNH"}[row["current_signal"]]
        require(factor["signal"] == signal, "Signal khác frozen")
        components = factor["components"]
        require(components["ic"] == row["native_ic"] and components["composite_score"] == round(row["composite"], 4)
                and components["accuracy"] == f"{row['native_accuracy']:.1%}", "Selection metrics khác frozen")


def transitions(points: list[dict]) -> list[dict]:
    """Chỉ nối cutoff liền kề cùng mã; ghi riêng within-block/between-block và khoảng cách."""
    symbols: dict[str, list[dict]] = defaultdict(list)
    for point in points: symbols[point["unit"]["symbol"]].append(point)
    rows = []
    for symbol, chain in sorted(symbols.items()):
        chain = sorted(chain, key=lambda p: p["unit"]["date"])
        for previous, current in zip(chain[:-1], chain[1:]):
            require(previous["unit"]["date"] < current["unit"]["date"] and previous["unit"]["decision"] < current["unit"]["decision"], "Transition không tăng thời gian/index")
            a = {r["alpha_id"]: r for r in previous["candidates"]}; b = {r["alpha_id"]: r for r in current["candidates"]}
            require(set(a) == set(b), "Transition khác candidate universe")
            first, second = set(previous["selected_ids"]), set(current["selected_ids"])
            require(len(first) == len(previous["selected_ids"]) == len(second) and bool(first), "Top set sai cardinality")
            keys = sorted(a); eligible = [k for k in keys if a[k]["diagnostic_eligible"] and b[k]["diagnostic_eligible"]]
            common = first & second
            ic_pairs = [k for k in keys if a[k]["ic_sign"] not in (None, 0) and b[k]["ic_sign"] not in (None, 0)]
            flips = [k for k in ic_pairs if a[k]["ic_sign"] != b[k]["ic_sign"]]
            rows.append({"symbol": symbol, "previous_id": previous["unit"]["id"], "current_id": current["unit"]["id"],
                "scope": "within_block" if previous["unit"]["fold"] == current["unit"]["fold"] else "between_blocks",
                "previous_date": previous["unit"]["date"], "current_date": current["unit"]["date"],
                "observed_bar_gap": int(current["unit"]["decision"] - previous["unit"]["decision"]),
                "calendar_day_gap": (pd.Timestamp(current["unit"]["date"]) - pd.Timestamp(previous["unit"]["date"])).days,
                "top5_common_count": len(common), "top5_overlap_fraction": ratio(len(common), len(first)),
                "top5_jaccard": ratio(len(common), len(first | second)), "basket_replacement_turnover": 1 - len(common) / len(first),
                "entered": sorted(second - first), "exited": sorted(first - second), "common_eligible_count": len(eligible),
                "native_full_registry_spearman": correlation([a[k]["composite"] for k in keys], [b[k]["composite"] for k in keys], ranked=True),
                "common_eligible_spearman": correlation([a[k]["composite"] for k in eligible], [b[k]["composite"] for k in eligible], ranked=True),
                "common_selected_mean_abs_rank_change": mean([abs(a[k]["rank"] - b[k]["rank"]) for k in common]),
                "common_selected_signal_changes": sum(a[k]["current_signal"] != b[k]["current_signal"] for k in common),
                "ic_nonzero_pair_ids": ic_pairs, "ic_sign_flip_ids": flips})
    return rows


def mean(values: list[Any]) -> float | None:
    """Bình quân chỉ trên values đã định nghĩa, mẫu số zero giữ null."""
    valid = [float(value) for value in values if value is not None and np.isfinite(value)]
    return float(np.mean(valid)) if valid else None


def group_statistics(points: list[dict]) -> dict:
    """Frequency/eligibility/sign stability có mẫu số cutoff và slots riêng, không lọc lại selection."""
    chains = transitions(points)
    by_factor: dict[str, list[dict]] = defaultdict(list)
    for point in points:
        for row in point["candidates"]: by_factor[row["alpha_id"]].append(row)
    factors = []
    slots = sum(len(p["selected_ids"]) for p in points)
    for key, records in sorted(by_factor.items()):
        require(len(records) == len(points), "Thiếu candidate trong mẫu số group")
        selected = [r for r in records if r["selected"]]; eligible = [r for r in records if r["diagnostic_eligible"]]
        positive = sum(r["ic_sign"] == 1 for r in records); negative = sum(r["ic_sign"] == -1 for r in records)
        pairs = sum(key in row["ic_nonzero_pair_ids"] for row in chains); flips = sum(key in row["ic_sign_flip_ids"] for row in chains)
        factors.append({"alpha_id": key, "cutoff_opportunities": len(records), "diagnostic_eligible_opportunities": len(eligible),
            "selected_count": len(selected), "selected_cutoff_frequency": ratio(len(selected), len(points)), "selected_slot_share": ratio(len(selected), slots),
            "selected_eligible_count": sum(r["diagnostic_eligible"] for r in selected),
            "selected_given_eligible": ratio(sum(r["selected"] for r in eligible), len(eligible)),
            "selected_ineligible_count": sum(not r["diagnostic_eligible"] for r in selected),
            "ic_positive": positive, "ic_negative": negative, "ic_zero": sum(r["ic_sign"] == 0 for r in records),
            "ic_undefined": sum(r["ic_sign"] is None for r in records), "ic_nonzero_majority_share": ratio(max(positive, negative), positive + negative),
            "selected_ic_positive": sum(r["ic_sign"] == 1 for r in selected), "selected_ic_negative": sum(r["ic_sign"] == -1 for r in selected),
            "selected_ic_zero": sum(r["ic_sign"] == 0 for r in selected), "selected_ic_undefined": sum(r["ic_sign"] is None for r in selected),
            "adjacent_nonzero_ic_pairs": pairs, "adjacent_nonzero_ic_flips": flips, "adjacent_nonzero_ic_flip_rate": ratio(flips, pairs),
            "mean_history_long_exposure_toggle_rate": mean([r["history_long_exposure_toggle_rate"] for r in records]),
            "mean_history_state_change_rate": mean([r["history_state_change_rate"] for r in records]),
            "mean_current_rank": mean([r["rank"] for r in records])})
    return {"cutoffs": len(points), "selected_slots": slots, "registered_opportunities": sum(p["registered_count"] for p in points),
            "diagnostic_eligible_opportunities": sum(p["diagnostic_eligible_count"] for p in points),
            "diagnostic_eligible_per_cutoff_min": min(p["diagnostic_eligible_count"] for p in points),
            "diagnostic_eligible_per_cutoff_max": max(p["diagnostic_eligible_count"] for p in points),
            "real_volume_cutoffs": sum(p["volume"]["uses_real_volume_branch"] for p in points),
            "proxy_volume_cutoffs": sum(not p["volume"]["uses_real_volume_branch"] for p in points),
            "raw_volume_missing_observations": sum(p["history"]["rows"] - p["volume"]["raw_volume_nonmissing"] for p in points),
            "raw_volume_zero_observations": sum(p["volume"]["raw_volume_zero_count"] for p in points),
            "raw_price_missing_observations": sum(p["volume"]["price_fields_missing_before_fill"] for p in points),
            "raw_volume_observation_opportunities": sum(p["history"]["rows"] for p in points),
            "selected_ineligible_slots": sum(r["selected_ineligible_count"] for r in factors),
            "selected_negative_ic_slots": sum(r["selected_ic_negative"] for r in factors),
            "transitions": len(chains), "mean_basket_replacement_turnover": mean([r["basket_replacement_turnover"] for r in chains]),
            "mean_native_registry_spearman": mean([r["native_full_registry_spearman"] for r in chains]), "factors": factors}


def aggregate(points: list[dict]) -> dict:
    """Tách pooled/macro và support từng mã, block, symbol×block mà không tính repeats."""
    require(len({p["unit"]["id"] for p in points}) == len(points), "Trùng cutoff khi aggregate")
    groups: dict[str, list[dict]] = defaultdict(list)
    for point in points:
        unit = point["unit"]
        for key in ("symbol:" + unit["symbol"], "block:" + unit["fold"], "symbol_block:" + unit["symbol"] + ":" + unit["fold"]): groups[key].append(point)
    stats = {key: group_statistics(values) for key, values in sorted(groups.items())}
    symbols = [value for key, value in stats.items() if key.startswith("symbol:")]
    return {"pooled": group_statistics(points), "groups": stats,
            "macro_unweighted_symbols": {"symbols": len(symbols), "basket_replacement_turnover": mean([r["mean_basket_replacement_turnover"] for r in symbols]),
                "registry_spearman": mean([r["mean_native_registry_spearman"] for r in symbols])}}


def run_audit(root: Path, output: Path) -> dict:
    """Xuất diagnostics riêng từ dữ liệu local; không API/fit test/ghi đè evidence cũ."""
    root, output = root.resolve(), output.resolve()
    require(output.is_relative_to(root / "outputs/revision") and output != root / "outputs/revision", "Output phải là release riêng")
    require(not output.exists(), "Release đã có; dùng --check hoặc tên mới")
    for release in ("alpha_registry_v1", "alpha_contract_v1"): verify_release(root, root / "outputs/revision" / release)
    queue = read_json(root / RUN / "manifest.json")
    def check_frozen() -> None:
        """Chỉ đối soát source hashes, không mở worker state hoặc checkpoint đang ghi."""
        for row in queue["sources"]: require(sha256_file(root / row["path"]) == row["sha256"], "Nguồn frozen đổi: " + row["path"])
    check_frozen()
    runtime = {"python": sys.version.split()[0], **{name: version(name) for name in ("numpy", "pandas", "scipy", "TA-Lib")}}
    require(all(queue["runtime"][key] == value for key, value in runtime.items()), "Runtime numeric khác pins")
    bank_path = root / BANK / "manifest.json"; bank = read_json(bank_path); protocol = bank["protocol"]
    require(protocol["horizon_observed_sessions"] == 3 and protocol["alpha_history"] == 600, "Protocol không còn L3/history600")
    require(protocol["fee_each_side"] == .0025 and protocol["slippage_each_side"] == .001, "Chi phí protocol khác native selector")
    price_dir = root / protocol["price_snapshot"]
    frames, prices = load_prices(price_dir, protocol["price_quality_policy"])
    sources = {bank_path, root / RUN / "manifest.json", price_dir / "manifest.json"}
    sources.update(price_dir / row["path"] for row in prices["symbols"])
    points = []
    units = locked_units(queue)
    for index, unit in enumerate(units, 1):
        asset_path = root / BANK / f"features/{unit['symbol']}_{unit['decision']}.json"; sources.add(asset_path)
        point = analyse_cutoff(frames[unit["symbol"]], unit, protocol)
        verify_selected(point, read_json(asset_path))
        point["frozen_top5_verified"] = True; point["asset_path"] = asset_path.relative_to(root).as_posix()
        points.append(point)
        if index % 17 == 0 or index == len(units): print(f"T11: đã đối soát {index}/{len(units)} cutoff, không gọi API.", flush=True)
    result = aggregate(points); changes = transitions(points)
    check_frozen()
    pooled = result["pooled"]
    summary = {"result": "PASS_NATIVE_DIAGNOSTIC_AUDIT", "scope": "Native in-sample scores; không walk-forward/unbiased/confirmatory evidence", "runtime": runtime,
        "main_cutoffs": len(points), "symbols": len(frames), "blocks": len({p["unit"]["fold"] for p in points}),
        "registered_candidates": len(alpha.ALPHA_REGISTRY), "registered_opportunities": pooled["registered_opportunities"],
        "diagnostic_eligible_opportunities": pooled["diagnostic_eligible_opportunities"], "selected_slots_verified": pooled["selected_slots"],
        "diagnostic_eligible_per_cutoff_range": [pooled["diagnostic_eligible_per_cutoff_min"], pooled["diagnostic_eligible_per_cutoff_max"]],
        "selected_negative_ic_slots": pooled["selected_negative_ic_slots"],
        "selected_ineligible_slots": pooled["selected_ineligible_slots"], "handler_errors": sum(r["handler_error"] is not None for p in points for r in p["candidates"]),
        "transitions": {kind: sum(r["scope"] == kind for r in changes) for kind in ("within_block", "between_blocks")},
        "transition_scope_means": {kind: {"count": sum(r["scope"] == kind for r in changes),
            "basket_replacement_turnover": mean([r["basket_replacement_turnover"] for r in changes if r["scope"] == kind]),
            "registry_spearman": mean([r["native_full_registry_spearman"] for r in changes if r["scope"] == kind])}
            for kind in ("within_block", "between_blocks")},
        "pooled_mean_basket_replacement_turnover": pooled["mean_basket_replacement_turnover"], "pooled_mean_registry_spearman": pooled["mean_native_registry_spearman"],
        "macro_unweighted_symbols": result["macro_unweighted_symbols"], "volume": {k: pooled[k] for k in ("real_volume_cutoffs", "proxy_volume_cutoffs", "raw_volume_missing_observations", "raw_volume_zero_observations", "raw_price_missing_observations", "raw_volume_observation_opportunities")},
        "price_provenance": {k: prices[k] for k in ("source", "status", "adjustment_policy", "calendar_policy", "price_unit")},
        "definitions": {"diagnostic_eligible": "Handler không lỗi; >=20 raw-finite paired observations, raw không constant và Spearman normalized/label xác định. Chỉ mẫu số audit, không lọc/rerank native.",
            "native_ranking": "Mọi registered candidate vẫn vào ranking; warm-up/zero-fill/constant-IC=0 và lỗi n=0 không bị che bằng diagnostic eligibility.",
            "ic_sign": "Dấu IC native làm tròn bốn chữ số dùng cho flip; IC undefined ghi null dù native thay bằng zero.",
            "frequency": "selected_count/cutoffs; share=selected_count/(5×cutoffs); selected_given_eligible có mẫu số eligible riêng.",
            "rank_stability": "Spearman trên composites cùng universe, ties average; báo thêm common diagnostic-eligible support, constant/thiếu support=null.",
            "basket_turnover": "1−|top5_prev∩top5_next|/5 giữa hai cutoffs liền kề cùng mã; within/between block tách riêng, không phải daily trading turnover.",
            "history_turnover": "Tỷ lệ đổi trạng thái {-1,0,+1} và toggle LONG/CASH (oriented normalized >0.1) trên adjacent bars trong prefix. Không ledger, không đo fill, không annualize.",
            "dependence": "Prefix600 và cutoffs chồng lấn; các transitions không độc lập, không p-value hoặc chứng minh stability phổ quát."},
        "limits": ["Native row-wise causal gate T10 vẫn FAIL; outer-cutoff isolation không làm training-window scores thành out-of-sample.",
            "Không chọn thresholds/hyperparameters/seed/cutoffs từ outcome, không dùng outer-test labels hoặc LLM predictions; không thay đầu vào queue.",
            "Giá là snapshot tái thu thập đã khóa, không xác thực ngược submission hoặc corporate actions; volume shares/lots chưa xác thực.",
            "T12/T13 phải khóa causal preprocessing/train-validation purge riêng; T11 không chứng minh selector tạo alpha/profitability hoặc LLM superiority."]}
    for release in ("alpha_registry_v1", "alpha_contract_v1"):
        path = root / "outputs/revision" / release / "manifest.json"; sources.add(path)
        sources.update(root / row["path"] for row in read_json(path)["sources"])
    sources.update(root / p for p in ("core/revision_alpha_selection.py", "scripts/audit_alpha_selection.py", "tests/test_revision_alpha_selection.py", "tests/test_revision_alpha_selection_leakage.py"))
    source_rows = [{"path": p.relative_to(root).as_posix(), "sha256": sha256_file(p)} for p in sorted(sources)]
    output.mkdir(parents=True)
    for name, value in (("cutoffs.json", points), ("aggregate.json", result), ("transitions.json", changes), ("summary.json", summary)):
        write_json(output / name, safe(value), True)
    write_json(output / "manifest.json", {"schema_version": "alpha_selection_v1", "sources": source_rows,
        "queue_run_signature": queue["sha256"], "frozen_source_hashes_checked_before_after": len(queue["sources"]),
        "network_or_inference": False, "runtime_modified": False, "outputs": [{"path": p.name, "sha256": sha256_file(p)} for p in sorted(output.iterdir())]}, True)
    return summary


def check_release(root: Path, output: Path) -> int:
    """Chỉ kiểm source/output hashes, không tái tính 102 cutoff hoặc gọi API."""
    return verify_release(root, output)
