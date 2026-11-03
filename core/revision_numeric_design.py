"""Khóa numeric control protocol và hợp đồng fit train-only, không chạy T13 khi freeze."""

from __future__ import annotations

import hashlib
from importlib.metadata import version
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

from core import alpha_compare as alpha
from core.revision_alpha_contract import safe
from core.revision_alpha_selection import correlation, locked_units
from core.revision_audit import sha256_file
from core.revision_baselines import load_prices, numerical_features, validate_prices
from core.revision_common_study import digest, read_json, write_json
from core.revision_sentiment_inventory import BANK, RUN, require, verify_release

PROTOCOL = Path("revision/numeric_controls_protocol.json")
OUTPUT = Path("outputs/revision/numeric_controls_design_v1")


def validate_protocol(protocol: dict) -> None:
    """Từ chối thay đổi scope/cost/seed/hợp đồng chung không có amendment rõ ràng."""
    require(protocol["schema_version"] == "numeric_controls_protocol_v1", "Sai schema protocol")
    require(protocol["scope"]["top_n"] == 5 and protocol["scope"]["registry_candidates"] == len(alpha.ALPHA_REGISTRY) == 85, "Sai universe/top-five")
    fixed = protocol["strategies"]["fixed_custom5"]["ids"]
    require(fixed == [f"CURRENT_{i}_{name}" for i, name in enumerate(("FDM", "SFA", "LVR", "BFE", "OFE"), 1)], "Fixed set không phải năm custom gốc")
    require(set(fixed).issubset(alpha.ALPHA_REGISTRY), "Thiếu handler fixed")
    require(protocol["strategies"]["random_eligible5"]["seeds"] == list(range(20)), "Seeds không đúng 20 trials đã khóa")
    target = protocol["target"]
    require((target["horizon_observed_sessions"], target["fee_each_side"], target["slippage_each_side"]) == (3, .0025, .001), "Target/cost không khớp replication")
    require(protocol["decision"]["individual_threshold"] == .1 and protocol["fit"]["minimum_scale_exclusive"] == 1e-9, "Threshold/scale thay đổi")
    require(protocol["fit"]["score_weights"] == {"ic": .4, "acc": .35, "sharpe": .25}, "Weights thay đổi")
    require(protocol["features"]["warmup_first_decision"] == 599 and protocol["fit"]["minimum_train"] == protocol["fit"]["minimum_finite_train_per_factor"] == 20
            and protocol["fit"]["minimum_validation"] == 10, "Warm-up/support thay đổi")
    require(protocol["inference"]["multiplicity_family_size"] == 23 and protocol["execution"]["api_calls"] == 0, "Sai multiplicity/API policy")


def validate_scope(frame: pd.DataFrame, scope: dict, protocol: dict) -> dict:
    """Kiểm index/date/label span bằng metadata, không đọc labels/returns test để fit."""
    dates = frame["date"].astype(str).to_numpy(); horizon = protocol["target"]["horizon_observed_sessions"]
    roles = {}
    for name in ("train", "validation", "test"):
        values = scope[f"{name}_indices"]
        require(all(isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)) for value in values), "Indices phải là integers")
        roles[name] = np.asarray(values, dtype=int)
    for name, indices in roles.items():
        require(len(indices) > 0 and np.all(np.diff(indices) > 0), "Role rỗng/trùng/không tăng: " + name)
        require(int(indices.min()) >= protocol["features"]["warmup_first_decision"] and int(indices.max()) + horizon < len(frame), "Role thiếu warm-up/horizon")
    train, validation, test = roles["train"], roles["validation"], roles["test"]
    require(len(train) >= protocol["fit"]["minimum_train"] and len(validation) >= protocol["fit"]["minimum_validation"], "Thiếu support train/validation")
    require(set(train).isdisjoint(validation) and set(train).isdisjoint(test) and set(validation).isdisjoint(test), "Roles overlap")
    require(dates[train + horizon].max() < dates[validation].min(), "Train label chạm validation")
    require(dates[validation + horizon].max() < dates[test].min(), "Validation label chạm test")
    return {"train_rows": len(train), "validation_rows": len(validation), "test_rows": len(test),
            "last_train_label_date": str(dates[train + horizon].max()), "first_validation_date": str(dates[validation].min()),
            "last_validation_label_date": str(dates[validation + horizon].max()), "first_test_date": str(dates[test].min())}


def causal_factors(frame: pd.DataFrame, last_decision: int, protocol: dict) -> pd.DataFrame:
    """Đường feature riêng: strict raw input, causal adapters và loại warm-up khỏi mọi fit."""
    require(599 <= last_decision < len(frame), "Feature endpoint ngoài support")
    prefix = frame.iloc[:last_decision + 1].copy()
    validate_prices(prefix)
    require(float(prefix["Volume"].iloc[:600].sum()) > 0, "Không cho global volume proxy switch sau warm-up")
    features, _, columns = numerical_features(prefix, [])
    factors = features[columns].rename(columns=lambda name: name.removeprefix("alpha_"))
    require(set(factors) == set(alpha.ALPHA_REGISTRY), "Feature universe khác registry")
    factors.iloc[:protocol["features"]["warmup_first_decision"]] = np.nan
    return factors[sorted(alpha.ALPHA_REGISTRY)].copy()


def random_set(eligible: list[str], scope_id: str, seed: int, protocol: dict) -> list[str]:
    """Random ranking theo hash đã định nghĩa; không phụ thuộc process hash hoặc test data."""
    require(isinstance(seed, int) and not isinstance(seed, bool) and seed in protocol["strategies"]["random_eligible5"]["seeds"], "Seed ngoài whitelist")
    require(len(eligible) == len(set(eligible)) and len(eligible) >= 5, "Thiếu/trùng eligible candidates")
    require(set(eligible).issubset(alpha.ALPHA_REGISTRY), "Eligible ID ngoài registry")
    def key(identity: str) -> tuple[str, str]:
        """Giữ encoding/tie-break ổn định giữa máy và thứ tự input."""
        text = f"{protocol['protocol_id']}|{scope_id}|{seed}|{identity}"
        return hashlib.sha256(text.encode("utf-8")).hexdigest(), identity
    return sorted(eligible, key=key)[:5]


def fit_numeric(train_x: pd.DataFrame, train_returns: np.ndarray, protocol: dict) -> dict:
    """Fit imputer/scaler/IC/eligible/ranking chỉ từ arrays train do caller đã purge."""
    require(set(train_x) == set(alpha.ALPHA_REGISTRY), "Train matrix sai universe")
    returns = np.asarray(train_returns, dtype=float)
    require(len(train_x) == len(returns) >= protocol["fit"]["minimum_train"] and np.isfinite(returns).all(), "Train returns thiếu/không hữu hạn")
    records, scores = {}, []
    for identity in sorted(alpha.ALPHA_REGISTRY):
        raw = train_x[identity].to_numpy(float); finite = np.isfinite(raw)
        median = float(np.median(raw[finite])) if finite.any() else 0.
        filled = np.where(finite, raw, median); mean = float(filled.mean()); scale = float(filled.std(ddof=1))
        normalized = np.tanh((filled - mean) / scale) if scale > protocol["fit"]["minimum_scale_exclusive"] else np.zeros(len(filled))
        ic = correlation(normalized, returns, ranked=True)
        eligible = bool(finite.sum() >= protocol["fit"]["minimum_finite_train_per_factor"] and np.unique(raw[finite]).size >= 2
                        and scale > protocol["fit"]["minimum_scale_exclusive"] and ic is not None)
        records[identity] = {"median": median, "mean": mean, "scale": scale, "finite_train": int(finite.sum()),
            "eligible": eligible, "train_ic": ic, "orientation": (-1 if ic < 0 else 1) if eligible else 0}
        if eligible: scores.append({"alpha_id": identity, **alpha.compute_metrics(normalized, returns, lookahead=3)})
    eligible_ids = sorted(k for k, value in records.items() if value["eligible"])
    require(len(eligible_ids) >= 5, "Ít hơn năm eligible factors; không fallback/đổi support")
    ranked = alpha.rank_alphas(pd.DataFrame(scores), weights=protocol["fit"]["score_weights"])
    ranked = ranked.sort_values(["composite", "alpha_id"], ascending=[False, True], kind="stable")
    return safe({"train_rows": len(train_x), "factors": records, "eligible_ids": eligible_ids,
                 "dynamic_ids": ranked["alpha_id"].head(5).tolist(), "ranking": ranked.to_dict(orient="records")})


def fit_on_scope(features: pd.DataFrame, frame: pd.DataFrame, scope: dict, protocol: dict) -> dict:
    """Đường T13 phải lấy train indices đã khóa; không truyền validation/test labels vào fit."""
    validate_scope(frame, scope, protocol)
    indices = np.asarray(scope["train_indices"], dtype=int); target = protocol["target"]
    opening = frame.iloc[indices + 1]["Open"].to_numpy(float)
    closing = frame.iloc[indices + target["horizon_observed_sessions"]]["Close"].to_numpy(float)
    net = closing / opening * (1 - target["fee_each_side"]) * (1 - target["slippage_each_side"]) / ((1 + target["fee_each_side"]) * (1 + target["slippage_each_side"])) - 1
    return fit_numeric(features.iloc[indices].copy(), net, protocol)


def predict_vote(features: pd.DataFrame, fitted: dict, identities: list[str], protocol: dict, no_flip: bool = False) -> np.ndarray:
    """Transform bằng train statistics và vote cố định; không fit trên phân phối đang dự đoán."""
    require(len(identities) == len(set(identities)) == 5, "Vote cần đúng năm IDs duy nhất")
    votes = np.zeros((len(features), 5), dtype=int)
    for column, identity in enumerate(identities):
        record = fitted["factors"][identity]
        if not record["eligible"]: continue
        raw = features[identity].to_numpy(float); filled = np.where(np.isfinite(raw), raw, record["median"])
        values = np.tanh((filled - record["mean"]) / record["scale"]) * (1 if no_flip else record["orientation"])
        threshold = protocol["decision"]["individual_threshold"]
        votes[:, column] = np.where(values > threshold, 1, np.where(values < -threshold, -1, 0))
    return (votes.mean(axis=1) > 0).astype(int)


def strategy_sets(fitted: dict, scope_id: str, protocol: dict) -> dict:
    """Materialize đủ 23 controls từ cùng fit, không chọn seed hoặc rerank no-flip."""
    signature = digest(fitted)
    sets = {"fixed_custom5": list(protocol["strategies"]["fixed_custom5"]["ids"]),
            "dynamic_train_top5": list(fitted["dynamic_ids"]), "dynamic_train_top5_no_flip": list(fitted["dynamic_ids"])}
    sets.update({f"random_seed_{seed:02d}": random_set(fitted["eligible_ids"], scope_id, seed, protocol)
                 for seed in protocol["strategies"]["random_eligible5"]["seeds"]})
    require(len(sets) == 23 and all(len(ids) == len(set(ids)) == 5 for ids in sets.values()), "Sai số strategies/cardinality")
    return {name: {"ids": ids, "no_flip": name == "dynamic_train_top5_no_flip", "fit_digest": signature,
                   "inactive_ids": [identity for identity in ids if not fitted["factors"][identity]["eligible"]]}
            for name, ids in sets.items()}


def build_design(queue: dict, bank: dict, frames: dict[str, pd.DataFrame], protocol: dict) -> dict:
    """Khóa metadata/scopes/draw IDs, tuyệt đối không tính feature/IC hoặc chọn factor bằng outcome."""
    validate_protocol(protocol)
    units = locked_units(queue); require(len(units) == protocol["scope"]["main_units"], "Sai main whitelist")
    index = {(u["symbol"], u["fold"]): [] for u in units}
    for unit in units: index[(unit["symbol"], unit["fold"])].append(unit)
    scopes, draws = [], []
    for original in bank["schedule"]:
        pair = original["symbol"], original["fold"]
        require(pair in index, "Bank scope ngoài whitelist")
        test_units = sorted(index[pair], key=lambda u: u["decision"])
        require([u["decision"] for u in test_units] == original["test"], "Bank test khác whitelist")
        scope_id = "/".join(pair)
        scope = {"scope_id": scope_id, "symbol": pair[0], "fold": pair[1],
                 **{f"{role}_indices": original[role] for role in ("train", "validation", "test")}, "test_units": test_units}
        scope["support"] = validate_scope(frames[pair[0]], scope, protocol)
        require(float(frames[pair[0]]["Volume"].iloc[:600].sum()) > 0, "Không đủ positive volume trước warm-up")
        scopes.append(scope)
        draws.extend({"scope_id": scope_id, "seed": seed, "draw_id": f"{scope_id}/random_seed_{seed:02d}",
                      "eligible_set_status": "train_only_materialized_in_T13"} for seed in protocol["strategies"]["random_eligible5"]["seeds"])
    require(len(scopes) == len(index) == protocol["scope"]["symbol_blocks"] and len({s["scope_id"] for s in scopes}) == len(scopes), "Scope thiếu/trùng")
    strategies = ["fixed_custom5", "dynamic_train_top5", "dynamic_train_top5_no_flip"] + [f"random_seed_{seed:02d}" for seed in range(20)]
    contrasts = protocol["inference"]["primary_contrasts"] + [f"dynamic_vs_random_seed_{seed:02d}" for seed in range(20)]
    require(len(strategies) == 23 and len(contrasts) == len(set(contrasts)) == 23, "Sai trial/contrast family")
    return {"schema_version": "numeric_controls_design_v1", "protocol": protocol, "protocol_digest": digest(protocol),
            "candidate_ids": sorted(alpha.ALPHA_REGISTRY), "scopes": scopes, "random_draws": draws, "strategy_ids": strategies,
            "contrast_ids": contrasts, "expected_predictions": len(units) * len(strategies),
            "T13_status": "not_run", "T12_real_data_fits": 0}


def freeze_design(root: Path, output: Path) -> dict:
    """Chỉ xuất thiết kế mới và hash nguồn; không chạy controls hoặc sửa release/API runtime."""
    root, output = root.resolve(), output.resolve()
    require(output.is_relative_to(root / "outputs/revision") and output != root / "outputs/revision", "Output phải là release riêng")
    require(not output.exists(), "Release đã có; dùng --check hoặc tên mới")
    for name in ("alpha_registry_v1", "alpha_contract_v1", "alpha_selection_v1"): verify_release(root, root / "outputs/revision" / name)
    protocol = read_json(root / PROTOCOL); queue = read_json(root / RUN / "manifest.json"); bank = read_json(root / BANK / "manifest.json")
    def frozen() -> None:
        """Không mở worker/checkpoints; đối soát đúng sources đã khóa của queue."""
        for row in queue["sources"]: require(sha256_file(root / row["path"]) == row["sha256"], "Nguồn frozen đổi: " + row["path"])
    frozen()
    target = protocol["target"]
    require(all(bank["protocol"][key] == target[key] for key in ("horizon_observed_sessions", "fee_each_side", "slippage_each_side", "initial_capital_vnd")), "Bank target/cost khác controls")
    runtime = {"python": sys.version.split()[0], **{name: version(name) for name in ("numpy", "pandas", "scipy", "TA-Lib")}}
    require(all(queue["runtime"][key] == value for key, value in runtime.items()), "Runtime numeric khác pins")
    directory = root / bank["protocol"]["price_snapshot"]
    frames, prices = load_prices(directory, bank["protocol"]["price_quality_policy"])
    design = build_design(queue, bank, frames, protocol)
    frozen()
    summary = {"result": "PASS_DESIGN_FROZEN_NOT_EVALUATED", "fit_scopes": len(design["scopes"]),
        "role_rows": {role: sum(len(s[f"{role}_indices"]) for s in design["scopes"]) for role in ("train", "validation", "test")},
        "strategies": len(design["strategy_ids"]), "random_draws": len(design["random_draws"]), "random_seeds": list(range(20)),
        "expected_test_predictions": design["expected_predictions"], "paired_BA_contrasts": len(design["contrast_ids"]),
        "runtime": runtime, "real_data_fits": 0, "api_calls": 0, "T13_status": "not_run",
        "limits": ["Thiết kế khóa sau T11 nên historical exploratory, không gọi preregistered confirmatory.",
            "Dynamic control thay đổi theo mã/block trên train; không replay native per-cutoff/LLM pipeline hoặc xóa causal limitation T10.",
            "Validation không chọn tham số; không dùng T11 frequency/test outcomes để chọn fixed/random/best seed.",
            "Sáu market blocks phụ thuộc, Holm/CI/sign-flip chỉ diagnostics; không chứng minh profitability hoặc LLM superiority."]}
    sources = {root / PROTOCOL, root / RUN / "manifest.json", root / BANK / "manifest.json", directory / "manifest.json"}
    sources.update(directory / r["path"] for r in prices["symbols"])
    for name in ("alpha_registry_v1", "alpha_contract_v1", "alpha_selection_v1"):
        path = root / "outputs/revision" / name / "manifest.json"; sources.add(path)
        sources.update(root / row["path"] for row in read_json(path)["sources"])
    sources.update(root / p for p in ("core/revision_numeric_design.py", "scripts/freeze_numeric_controls.py", "tests/test_revision_numeric_design.py", "tests/test_revision_numeric_design_leakage.py"))
    output.mkdir(parents=True)
    write_json(output / "design.json", design, True); write_json(output / "summary.json", summary, True)
    write_json(output / "manifest.json", {"schema_version": "numeric_controls_design_v1", "queue_run_signature": queue["sha256"],
        "protocol_digest": design["protocol_digest"], "frozen_source_hashes_checked_before_after": len(queue["sources"]),
        "sources": [{"path": p.relative_to(root).as_posix(), "sha256": sha256_file(p)} for p in sorted(sources)],
        "outputs": [{"path": p.name, "sha256": sha256_file(p)} for p in sorted(output.iterdir())]}, True)
    return summary


def check_release(root: Path, output: Path) -> int:
    """Chỉ kiểm hashes, không fit hoặc tạo dự đoán T13."""
    return verify_release(root, output)
