"""Thống kê lặp và audit identity R3; không sửa inference hoặc chọn run tốt nhất."""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from core.revision_common_study import digest

METRICS = ("accuracy", "balanced_accuracy", "mcc", "macro_f1", "long_rate", "mean_account_net_return_pct")
CONTRASTS = (("AS", "B"), ("A", "B"), ("AS", "S"), ("AS", "A"), ("S", "B"), ("AS", "P"))
POLICY = {
    "schema_version": "revision_r3_repeats_v1",
    "scope": "descriptive repeat analysis on frozen preselected panels; no model calls or new predictions",
    "analysis_timing": "two-level CI procedure added after inference; panel/repeat allocation itself was frozen before calls",
    "decision_panel": "18 units x B/A/S/AS/P x 3 decisions, shared upstream realization 0",
    "upstream_panel": "9 units x B/AS x 3 upstream realizations, decision repeat 0 only",
    "estimand": "mean of three per-execution metrics on common panel support; SD uses ddof=1; median/min/max all reported",
    "return": "mean net return of separate symbol-block accounts formed only from panel cycles; not portfolio return",
    "bootstrap": "10000 joint whole-block x paired-run weighted resamples, seed 20261102; same block/run draws for all variants",
    "undefined": "null/NA; CIs conditional on finite draws with n_defined/n_undefined disclosed; no imputed zero",
    "limits": "three executions and three historical blocks per panel; descriptive, not calibrated coverage or variance-component identification",
    "selection": "all repeats retained; no best seed/run/checkpoint or ensemble substituted for the broad r0 one-pass result",
}


def describe(values: list[float | None]) -> dict:
    """Không giấu mẫu số khi metric của một execution không xác định."""
    valid = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    return {"n_planned": len(values), "n_defined": len(valid),
        "mean": float(valid.mean()) if len(valid) else None,
        "sd": float(valid.std(ddof=1)) if len(valid) > 1 else None,
        "median": float(np.median(valid)) if len(valid) else None,
        "min": float(valid.min()) if len(valid) else None,
        "max": float(valid.max()) if len(valid) else None}


def array_metrics(counts: np.ndarray) -> dict[str, np.ndarray]:
    """Tính vector hóa đúng cùng hợp đồng TP/FN/TN/FP và undefined của R1."""
    tp, fn, tn, fp = (counts[..., i].astype(float) for i in range(4))
    with np.errstate(divide="ignore", invalid="ignore"):
        return {"accuracy": (tp + tn) / (tp + fn + tn + fp),
            "balanced_accuracy": (tp / (tp + fn) + tn / (tn + fp)) / 2,
            "mcc": (tp * tn - fn * fp) / np.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)),
            "macro_f1": (2 * tp / (2 * tp + fn + fp) + 2 * tn / (2 * tn + fn + fp)) / 2,
            "long_rate": (tp + fp) / (tp + fn + tn + fp)}


def interval(values: np.ndarray) -> dict:
    """Ghi rõ số draws bị mất class/dispersion, không nhận CI là calibrated."""
    finite = values[np.isfinite(values)]
    return {"n_resamples": len(values), "n_defined": len(finite), "n_undefined": len(values) - len(finite),
        "percentile_95": np.quantile(finite, [.025, .975]).tolist() if len(finite) else None,
        "scope": "conditional finite-draw descriptive percentiles, only three runs/blocks; no p-value or calibrated coverage claim"}


def weighted_runs(scores: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Một run không được chọn có thể undefined; run đã chọn undefined làm draw undefined."""
    defined = np.all((weights == 0) | np.isfinite(scores), axis=1)
    result = np.sum(np.where(np.isfinite(scores), scores, 0) * weights, axis=1) / weights.sum(axis=1)
    return np.where(defined, result, np.nan)


def resample(counts: dict[str, np.ndarray], accounts: dict[str, np.ndarray], repeats: int = 10000, seed: int = 20261102) -> dict:
    """Resample block toàn cross-section và execution index có pairing giữa variants."""
    shapes = {v.shape for v in counts.values()}
    if len(shapes) != 1 or not counts:
        raise ValueError("Các variant không cùng tensor support")
    runs, blocks, cells = next(iter(shapes))
    if runs != 3 or blocks < 1 or cells != 4 or set(counts) != set(accounts):
        raise ValueError("Tensor phải có ba runs, block và bốn confusion cells")
    base = next(iter(counts.values())).sum(axis=-1)
    account_base = next(iter(accounts.values()))[..., 1]
    actual_up = next(iter(counts.values()))[..., 0] + next(iter(counts.values()))[..., 1]
    if not np.array_equal(base, np.broadcast_to(base[0], base.shape)):
        raise ValueError("Khác unit support giữa executions")
    for variant in counts:
        if accounts[variant].shape != (runs, blocks, 2) or not np.array_equal(counts[variant].sum(axis=-1), base):
            raise ValueError("Khác unit support giữa variants/runs")
        if not np.array_equal(accounts[variant][..., 1], account_base) or np.any(account_base <= 0):
            raise ValueError("Khác account support hoặc block rỗng")
        if not np.array_equal(counts[variant][..., 0] + counts[variant][..., 1], np.broadcast_to(actual_up[0], actual_up.shape)):
            raise ValueError("Khác nhãn thật giữa variants/executions")
    rng = np.random.default_rng(seed)
    block_weights = rng.multinomial(blocks, np.full(blocks, 1 / blocks), repeats)
    run_weights = rng.multinomial(runs, np.full(runs, 1 / runs), repeats)
    samples = {}
    for variant in sorted(counts):
        sums = np.einsum("bk,rkc->brc", block_weights, counts[variant])
        scores = array_metrics(sums)
        account_sums = np.einsum("bk,rkc->brc", block_weights, accounts[variant])
        scores["mean_account_net_return_pct"] = account_sums[..., 0] / account_sums[..., 1]
        samples[variant] = {k: weighted_runs(v, run_weights) for k, v in scores.items()}
    return {"n_runs": runs, "n_blocks": blocks, "seed": seed,
        "variants": {v: {k: interval(a) for k, a in data.items()} for v, data in samples.items()},
        "contrasts": {f"{a}-{b}": {k: interval(samples[a][k] - samples[b][k]) for k in METRICS}
                      for a, b in CONTRASTS if a in samples and b in samples}}


def panel_identity(records: list[dict], requests: dict[str, dict], unit_ids: list[str], variants: list[str], upstream: bool) -> dict:
    """Từ chối copied response ID, thiếu run, prompt thay đổi hoặc parent ghép sai."""
    indexed = {(v["context"]["unit_id"], v["context"]["realization"], v["context"]["variant"], v["context"]["repeat"]): v for v in records}
    if len(indexed) != len(records):
        raise ValueError("Duplicate decision identity")
    used, selected, disagreement = set(), [], []
    for unit in unit_ids:
        parents: dict[int, set] = defaultdict(set)
        for variant in variants:
            values, prompts, ids = [], [], []
            for run in range(3):
                key = (unit, run if upstream else 0, variant, 0 if upstream else run)
                if key not in indexed:
                    raise ValueError("Thiếu execution đã đăng ký")
                record = indexed[key]
                if not record["request_ids"] or record.get("fallback_reason") or record["decision_source"] != "llm_structured":
                    raise ValueError("Decision không có response thật hoặc có fallback")
                for attempt in record["request_ids"]:
                    if attempt in used:
                        raise ValueError("Một successful request bị dùng cho nhiều execution")
                    req = requests[attempt]
                    if any(req["context"].get(k) != record["context"].get(k) for k in ("unit_id", "realization", "variant", "repeat", "model", "smoke", "stage")):
                        raise ValueError("Request không thuộc đúng repeat/realization")
                    used.add(attempt)
                req = requests[record["request_ids"][-1]]
                prompts.append(digest(req["messages"]))
                parents[run if upstream else 0].add(record["parent"]["upstream_hash"])
                ids.append(record["request_ids"][-1])
                values.append(int(record["prediction"] == "LONG"))
                selected.append(record)
            if not upstream and len(set(prompts)) != 1:
                raise ValueError("Decision repeats không giữ cùng actual prompt")
            disagreement.append({"unit_id": unit, "variant": variant, "n_unique_prompt_hashes": len(set(prompts)),
                "n_successful_requests": len(ids), "n_unique_successful_requests": len(set(ids)),
                "prediction_vector": ["LONG" if v else "SHORT" for v in values],
                "pairwise_disagreement": float(np.mean([values[a] != values[b] for a, b in ((0, 1), (0, 2), (1, 2))])),
                "sample_variance_long_indicator": float(np.var(values, ddof=1))})
        if any(len(v) != 1 for v in parents.values()):
            raise ValueError("Variants trong cùng realization không chia sẻ upstream")
    return {"n_records": len(selected), "n_unique_successful_requests": len(used), "disagreement_by_cutoff": disagreement,
        "records": selected}


def per_run_summary(metrics: list[dict]) -> dict:
    """Giữ danh sách execution trước khi mô tả; không chọn run tốt nhất."""
    return {metric: describe([r[metric] for r in metrics]) for metric in METRICS}
