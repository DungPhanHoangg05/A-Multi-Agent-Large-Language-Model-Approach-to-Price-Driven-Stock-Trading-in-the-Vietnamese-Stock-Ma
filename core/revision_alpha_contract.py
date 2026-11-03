"""Kiểm chứng Alpha bằng oracle tổng hợp và phân biệt cutoff với nhân quả từng dòng."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
from importlib.metadata import version
import math
from pathlib import Path
import sys
from typing import Any
from unittest.mock import patch

import numpy as np
import pandas as pd

from core import alpha_compare as alpha
from core.revision_audit import sha256_file
from core.revision_common_study import read_json, write_json
from core.revision_r4_factorial import prompt_parts
from core.revision_sentiment_inventory import BANK, RUN, require, verify_release

OUTPUT = Path("outputs/revision/alpha_contract_v1")
FIXTURE = Path("revision/alpha_translation_cases.json")


def safe(value: Any) -> Any:
    """Chuyển kiểu NumPy và số không hữu hạn thành JSON chuẩn, không xuất NaN/Infinity."""
    if isinstance(value, dict): return {k: safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray, pd.Series)): return [safe(v) for v in value]
    if isinstance(value, (bool, np.bool_)): return bool(value)
    if isinstance(value, (int, np.integer)): return int(value)
    if isinstance(value, (float, np.floating)): return float(value) if np.isfinite(value) else None
    return value


def matches(actual: Any, expected: Any) -> None:
    """Oracle chỉ PASS khi cùng shape và khớp cả vị trí undefined lẫn giá trị hữu hạn."""
    np.testing.assert_allclose(np.asarray(actual, dtype=float), np.asarray(expected, dtype=float), rtol=1e-10, atol=1e-11, equal_nan=True)


def synthetic_frame(n: int = 96) -> pd.DataFrame:
    """Chuỗi xác định có xu hướng/dao động, không phải OHLCV thực nghiệm."""
    t = np.arange(n, dtype=float)
    close = 100 + .03 * t + 2 * np.sin(t / 4.1) + .7 * np.cos(t / 9)
    return pd.DataFrame({"Datetime": pd.bdate_range("2020-01-01", periods=n),
                         "date": pd.bdate_range("2020-01-01", periods=n).strftime("%Y-%m-%d"),
                         "Open": close - .4 + .2 * np.cos(t / 3), "High": close + 1 + .2 * np.sin(t / 5),
                         "Low": close - 1.1, "Close": close, "Volume": 1000 + 30 * (t % 17) + 40 * np.cos(t / 7)})


def operator_cases(specification: dict) -> list[dict]:
    """Gọi operator native với golden arrays khai báo ngoài code, kể cả ties/NaN/warm-up."""
    rows = []
    for case in specification["operators"]:
        values = pd.Series(case["values"], dtype=float)
        kwargs = {k: case[k] for k in ("window", "period", "method", "power") if k in case}
        if isinstance(kwargs.get("power"), list): kwargs["power"] = pd.Series(kwargs["power"], dtype=float)
        args = [values, pd.Series(case["other"], dtype=float)] if "other" in case else [values]
        actual = getattr(alpha, case["operator"])(*args, **kwargs)
        matches(actual, case["expected"])
        rows.append({"id": case["id"], "operator": case["operator"], "expected": case["expected"], "observed": safe(actual), "result": "PASS"})
    return rows


def feature_cases(specification: dict) -> list[dict]:
    """Kiểm ranh giới >40%, proxy/đơn vị, ADV partial và log-volume ffill của build_features."""
    rows = []
    close = np.array([10., 12., 11., 15., 13.])
    for case in specification["volume_cases"]:
        frame = pd.DataFrame({"Open": close - .5, "Close": close, "High": close + np.arange(1., 6.), "Low": close - np.arange(1., 6.)})
        if case["volume"] is not None: frame["Volume"] = case["volume"]
        data = alpha.build_features(frame)
        require(bool(data["_has_vol"].iloc[-1]) == case["expected_real"], "Sai nhánh volume: " + case["id"])
        matches(data["volume"], case["expected_volume"])
        matches(data["vwap"], close)
        expected_adv = np.cumsum(case["expected_volume"]) / np.arange(1, 6)
        matches(data["adv20"], expected_adv)
        matches(data["returns"], np.r_[0., close[1:] / close[:-1] - 1])
        expected_log = []
        previous = 0.
        for value in case["expected_volume"]:
            if value > 0: previous = float(np.log(value))
            expected_log.append(previous)
        matches(data["log_vol"], expected_log)
        rows.append({"id": case["id"], "result": "PASS", "real_volume": bool(data["_has_vol"].iloc[-1]),
                     "volume": safe(data["volume"]), "adv20": safe(data["adv20"]),
                     "units": "Đơn vị Volume do caller cung cấp, chưa xác thực shares/lots; proxy High−Low có đơn vị giá; ADV không nhân giá nên không là dollar volume."})
    return rows


def rolling(values: np.ndarray, window: int, operation: str, other: np.ndarray | None = None) -> np.ndarray:
    """Oracle NumPy trên cửa sổ mảng, độc lập với Pandas/native rolling helpers."""
    output = np.zeros(len(values))
    for end in range(1, len(values) + 1):
        start = max(0, end - window); sample = values[start:end]
        if operation == "mean": output[end - 1] = np.mean(sample)
        elif operation == "min": output[end - 1] = np.min(sample)
        elif operation == "rank":
            output[end - 1] = np.nan if len(sample) < max(1, window // 2) else np.count_nonzero(sample[:-1] < sample[-1]) / max(len(sample) - 1, 1)
        elif operation == "corr":
            if len(sample) >= max(2, window // 2):
                value = np.corrcoef(sample, other[start:end])[0, 1]
                output[end - 1] = value if np.isfinite(value) else 0.
        elif operation == "decay":
            weights = np.arange(window - len(sample) + 1, window + 1)
            output[end - 1] = np.dot(sample, weights) / weights.sum()
        else: raise ValueError("Oracle operator chưa khai báo")
    return output


def ema(values: np.ndarray, span: int) -> np.ndarray:
    """Oracle EMA bằng recurrence vô hướng trên mảng tổng hợp."""
    result = values.copy(); weight = 2 / (span + 1)
    for position in range(1, len(values)):
        result[position] = weight * values[position] + (1 - weight) * result[position - 1]
    return result


def translation_cases() -> list[dict]:
    """Kiểm năm custom và sáu translations bằng đại số/NumPy, không suy exact WorldQuant replication."""
    frame = synthetic_frame(); frame.loc[len(frame) - 1, "Volume"] *= 3
    data = alpha.build_features(frame)
    c, o, h, l, v = (frame[k].to_numpy(float) for k in ("Close", "Open", "High", "Low", "Volume"))
    ret = np.r_[0., c[1:] / c[:-1] - 1]
    roc = ret[-1] / np.std(ret[-20:], ddof=1)
    histogram = ema(c, 12) - ema(c, 26); histogram -= ema(histogram, 9)
    deviation = (c - rolling(c, 5, "mean")) / c
    pct_b = (c[-1] - np.mean(c[-20:]) + 2 * np.std(c[-20:], ddof=1)) / (4 * np.std(c[-20:], ddof=1))
    vz = (v[-1] - np.mean(v[-5:])) / np.std(v[-5:], ddof=1)
    expected = {
        "CURRENT_1_FDM": np.tanh(roc * v[-1] / np.mean(v[-20:]) * .5),
        "CURRENT_2_SFA": np.tanh(1.5 * np.tanh(histogram[-1] / (c[-1] * .005 + 1e-9)) + .5 * roc),
        "CURRENT_3_LVR": np.tanh(-.8 * (deviation[-1] - np.mean(deviation[-20:])) / np.std(deviation[-20:], ddof=1)),
        "CURRENT_4_BFE": np.tanh((pct_b - .5) * vz * 1.5),
        "CURRENT_5_OFE": np.tanh(roc * ((c[-1] - l[-1]) / (h[-1] - l[-1]) - .5) * 3),
    }
    rows = []
    for key, oracle in expected.items():
        observed = float(alpha.ALPHA_REGISTRY[key][0](data).iloc[-1]); matches(observed, oracle)
        rows.append({"id": key, "oracle": "Đại số của handler registry, sample-SD; không dùng display template hoặc prototype làm oracle.", "expected": float(oracle), "observed": observed, "result": "PASS"})
    observed = float(alpha.wq6(data).iloc[-1]); oracle = -np.corrcoef(o[-10:], v[-10:])[0, 1]; matches(observed, oracle)
    rows.append({"id": "WQ6", "expected": float(oracle), "observed": observed, "result": "PASS"})
    d7 = np.r_[np.zeros(7), c[7:] - c[:-7]]
    oracle = -np.count_nonzero(np.abs(d7[-30:-1]) < abs(d7[-1])) / 29 * np.sign(d7[-1])
    observed = float(alpha.wq7(data).iloc[-1]); matches(observed, oracle)
    rows.append({"id": "WQ7", "expected": float(oracle), "observed": observed, "native_rank_window": 30,
                 "source_rank_window": 60, "source_window_counterfactual": float(-np.count_nonzero(np.abs(d7[-60:-1]) < abs(d7[-1])) / 59 * np.sign(d7[-1])), "result": "PASS"})
    oracle = -(l[-1] - c[-1]) * o[-1] ** 2 / ((l[-1] - h[-1]) * c[-1] ** 2)
    observed = float(alpha.wq54(data).iloc[-1]); matches(observed, oracle)
    rows.append({"id": "WQ54", "expected": float(oracle), "observed": observed,
                 "original_power5_counterfactual": float(-(l[-1] - c[-1]) * o[-1] ** 5 / ((l[-1] - h[-1]) * c[-1] ** 5)), "result": "PASS"})
    vw = (h + l + c) / 3
    rank1 = rolling(vw - rolling(vw, 16, "min"), 20, "rank")
    rank2 = rolling(rolling(vw, 18, "corr", rolling(v, 180, "mean")), 20, "rank")
    oracle = 2 * float(rank1[-1] < rank2[-1]) - 1
    observed = float(alpha.wq61(data).iloc[-1]); matches(observed, oracle)
    rows.append({"id": "WQ61", "expected": oracle, "observed": observed, "native_corr_window": 18, "source_corr_floor": 17,
                 "original_boolean_on_native_inputs": bool(rank1[-1] < rank2[-1]), "result": "PASS"})
    x = .00817205 * o + (1 - .00817205) * vw
    adv60 = rolling(v, 60, "mean")
    adv_sum = np.cumsum(adv60) - np.r_[np.zeros(9), np.cumsum(adv60)[:-9]]
    rank1 = rolling(rolling(x, 6, "corr", adv_sum), 20, "rank")
    rank2 = rolling(o - rolling(o, 14, "min"), 20, "rank")
    oracle = -(2 * float(rank1[-1] < rank2[-1]) - 1)
    observed = float(alpha.wq65(data).iloc[-1]); matches(observed, oracle)
    rows.append({"id": "WQ65", "expected": oracle, "observed": observed, "native_adv_sum_window": 9, "source_adv_sum_floor": 8,
                 "original_negative_boolean_on_native_inputs": -int(rank1[-1] < rank2[-1]), "result": "PASS"})
    first = rolling(rolling(rolling(l, 7, "corr", rolling(v, 10, "mean")), 6, "decay"), 4, "rank")
    second = rolling(rolling(np.r_[np.zeros(3), vw[3:] - vw[:-3]], 10, "decay"), 15, "rank")
    observed = float(alpha.wq89(data).iloc[-1]); oracle = first[-1] - second[-1]; matches(observed, oracle)
    rows.append({"id": "WQ89", "expected": float(oracle), "observed": observed,
                 "neutralization": "Không có ngành/universe; oracle kiểm adaptation không neutralize, không chứng minh tương đương bản gốc.", "result": "PASS"})
    return rows


def rowwise_diagnostics() -> dict:
    """Phản ví dụ tối thiểu: phát hiện noncausality nội cửa sổ thay vì xác nhận Zero-Leakage giả."""
    source = pd.Series([np.nan, 2., 3., 4.]); poisoned = source.copy(); poisoned.iloc[1] = 100
    delay_changed = not np.isclose(alpha.delay(source).iloc[0], alpha.delay(poisoned).iloc[0])
    normalization = {}
    for method in ("zscore_tanh", "minmax", "rank"):
        short = pd.Series([1., 2., 3., 4.]); extended = pd.concat([short, pd.Series([100.])], ignore_index=True)
        a, b = alpha.normalize_alpha(short, method), alpha.normalize_alpha(extended, method).iloc[:4]
        normalization[method] = {"historical_values_changed": not np.allclose(a, b), "prefix": safe(a), "extended_prefix": safe(b)}
    frame = synthetic_frame(10); frame["Volume"] = [np.nan] * 4 + [1000.] * 6
    prefix, full = alpha.build_features(frame.iloc[:4]), alpha.build_features(frame)
    volume_changed = not np.allclose(prefix["volume"], full["volume"].iloc[:4])
    require(delay_changed and volume_changed and all(r["historical_values_changed"] for r in normalization.values()), "Không tái hiện phản ví dụ native; cần kiểm lại nguồn/fixture")
    return {"diagnostic_result": "PASS_DETECTION", "native_rowwise_causal_gate": "FAIL", "delay_bfill_changes_past": bool(delay_changed),
            "normalization": normalization, "global_volume_branch_changes_past": bool(volume_changed),
            "scope": "Dữ liệu sau một dòng nhưng vẫn trong prefix quyết định thay đổi giá trị lịch sử. Đây là hạn chế selection diagnostics native, chưa chứng minh outer-test leakage.",
            "required_action": "Không dùng native full-Series scores làm walk-forward/unbiased evidence. T11 báo đúng diagnostic; T12/T13 dùng fit train/validation đã purge và adapters nhân quả riêng. Không sửa code/input frozen hoặc ghi zero-leakage toàn runtime."}


def prototype_cases() -> list[dict]:
    """Kiểm nhánh SFA riêng và threshold Alpha_4 trước display rounding, không đổi công thức."""
    from agents.alpha_agent import _alpha2_sfa, _alpha4_bfe
    rows = []
    tv = {"roc1_adjusted": .2, "macd_hist_cur": .1, "close_0": 100.}
    for reliable in (False, True):
        actual = _alpha2_sfa({"z_score": 2., "is_reliable": reliable}, tv)["value"]
        expected = round(math.tanh(1.1 if reliable else 1.5 * math.tanh(.2) + .1), 4)
        matches(actual, expected)
        rows.append({"id": f"prototype_SFA_reliable_{reliable}", "expected": expected, "observed": actual,
                     "scope": "Prototype có nhánh sentiment; registry SFA chỉ MACD proxy, không gộp hai đường.", "result": "PASS"})
    for value in (.099996, .100004, -.099996, -.100004):
        tv4 = {"bb_pct_b": .75, "vol_zscore_5": math.atanh(value) / (.25 * 1.5)}
        actual = _alpha4_bfe(tv4)
        expected_signal = "TĂNG" if value > .1 else "GIẢM" if value < -.1 else "TRUNG TÍNH"
        matches(actual["value"], round(value, 4))
        require(actual["signal"] == expected_signal, "Threshold Alpha_4 bị áp sau rounding")
        rows.append({"id": f"prototype_Alpha4_{value}", "unrounded_value": value, "observed_display": actual["value"],
                     "expected_signal": expected_signal, "observed_signal": actual["signal"], "result": "PASS"})
    return rows


def surrogate_cases() -> list[dict]:
    """Chứng minh rank surrogate khác rank xuyên mã và WQ89 không tái lập neutralization gốc."""
    values = np.array([10., 11., 12.])
    native = float(alpha.ts_rank(pd.Series(values), 3).iloc[-1])
    ranks = [float(np.mean(np.array([values[-1], peer]) <= values[-1])) for peer in (100., 1.)]
    require(native == 1. and ranks == [.5, 1.], "Fixture không phân biệt rank theo thời gian/xuyên mã")
    frame = alpha.build_features(synthetic_frame())
    before = alpha.wq89(frame)
    changed = frame.copy(); changed["industry"] = "fixture_sector"; changed["peer_vwap"] = 1e6
    matches(alpha.wq89(changed), before)
    return [{"id": "rank_surrogate", "native_time_rank": native, "cross_sectional_ranks_with_changed_peer": ranks,
             "result": "PASS", "scope": "Cùng lịch giá mã hiện tại, peer thay đổi rank xuyên mã nhưng không đổi ts_rank; hai định nghĩa không tương đương."},
            {"id": "WQ89_no_industry_inputs", "result": "PASS", "scope": "Thêm industry/peer data không đổi handler; không có phép cross-sectional demean. Không chứng minh output gốc khi thiếu universe."}]


def require_rowwise_causal(profile: dict) -> None:
    """Chặn việc dùng PASS detection thay cho causal gate khi consumer cần dữ liệu nhân quả."""
    require(profile["native_rowwise_causal_gate"] == "PASS", "Native row-wise causal gate FAIL; không được gán Zero-Leakage")


def cutoff_diagnostics() -> dict:
    """Chạy thật agent→selector→85 handlers trên synthetic, không mock backtest hoặc prediction."""
    from agents.alpha_agent import _compute_all_alphas
    from utils import alpha_selector
    frame = synthetic_frame(720); original = frame.copy(deep=True); cutoff = frame["Datetime"].iloc[649]
    changed = frame.copy(); changed.loc[650:, ["Open", "High", "Low", "Close"]] *= 1000; changed.loc[650:, "Volume"] *= 1e6
    short_window = frame.iloc[605:650].to_dict(orient="list")
    captured = []
    native_backtest = alpha_selector.run_backtest
    def observe(history: pd.DataFrame, **kwargs: Any) -> pd.DataFrame:
        """Chỉ ghi phạm vi nhận được rồi gọi nguyên backtest native."""
        captured.append({"rows": len(history), "max_date": str(history["Datetime"].max()), "min_date": str(history["Datetime"].min())})
        result = native_backtest(history, **kwargs)
        require(set(result["alpha_id"]) == set(alpha.ALPHA_REGISTRY) and len(result) == 85, "Synthetic run thiếu candidate")
        require(bool((result["n"] >= 20).all()), "Handler lỗi hoặc thiếu support bị che bằng n=0")
        captured[-1]["minimum_candidate_support"] = int(result["n"].min())
        return result
    with redirect_stdout(io.StringIO()), patch.object(alpha_selector, "load_data", side_effect=AssertionError("Cấm realtime")), patch.object(alpha_selector, "run_backtest", side_effect=observe):
        a, _ = _compute_all_alphas(short_window, {}, {}, "FIXTURE", historical_df=frame, as_of_date=cutoff, is_backtest=True)
        b, _ = _compute_all_alphas(short_window, {}, {}, "FIXTURE", historical_df=changed, as_of_date=cutoff, is_backtest=True)
    require(a == b and len(a) == 5 and len(captured) == 2, "Future poison đổi alpha tại cutoff")
    require(all(row["rows"] == 600 and row["max_date"] == str(cutoff) for row in captured), "Sai cutoff hoặc cap 600")
    pd.testing.assert_frame_equal(frame, original)
    return {"result": "PASS", "synthetic_only": True, "actual_native_backtest_runs": 2, "candidates_per_run": len(alpha.ALPHA_REGISTRY),
            "selected_factor_names": [row["name"] for row in a], "captured_history": captured,
            "scope": "Poison sau cutoff không đổi top-five/values/IC-derived orientation/metadata; không chứng nhận row-wise causality của training-window scores."}


def numeric_adapter_diagnostics() -> dict:
    """Kiểm đường numeric đã có adapters nhân quả riêng, sau warm-up và không fit nhãn test."""
    from core.revision_baselines import numerical_features
    frame = synthetic_frame(700); changed = frame.copy()
    changed.loc[401:, ["Open", "High", "Low", "Close"]] *= 20; changed.loc[401:, "Volume"] *= 1000
    original, _, columns = numerical_features(frame, [])
    future, _, _ = numerical_features(changed, [])
    prefix, _, _ = numerical_features(frame.iloc[:401].copy(), [])
    np.testing.assert_allclose(original.iloc[350:401], future.iloc[350:401], equal_nan=True)
    np.testing.assert_allclose(original.iloc[400], prefix.iloc[400], equal_nan=True)
    return {"result": "PASS", "synthetic_only": True, "alpha_columns": len(columns), "poison_checked_rows": 51,
            "prefix_cutoff_row": 400, "scope": "Đường numerical_features có năm causal adapters riêng; kiểm sau warm-up trên Volume đầy đủ. Không thay code/score của native selector và không xác thực mọi lịch sử hoặc đơn vị volume."}


def metadata_impact(root: Path, queue: dict) -> tuple[dict, set[Path]]:
    """Đếm artifact/prompt chịu metadata sai, không đọc labels, outcomes hoặc raw đang ghi."""
    identities = {(alpha.get_alpha_template(k)["name"], alpha.get_alpha_template(k)["formula"]): k for k in alpha.ALPHA_REGISTRY}
    require(len(identities) == len(alpha.ALPHA_REGISTRY), "Template identity không duy nhất")
    bad = {"CURRENT_1_FDM", "CURRENT_2_SFA"}; rows, sources = [], set()
    units = {job["unit"]["id"]: job["unit"] for job in queue["jobs"] if job["phase"] == "main"}
    affected = set()
    for key, unit in units.items():
        path = root / BANK / f"features/{unit['symbol']}_{unit['decision']}.json"; asset = read_json(path); sources.add(path)
        selected = [identities[(factor["name"], factor["formula"])] for factor in asset["alpha_factors"]]
        wrong = [value for value in selected if value in bad]
        if wrong: affected.add(key)
        rows.append({"unit_id": key, "selected_custom_metadata_mismatches": wrong, "asset_path": path.relative_to(root).as_posix(), "asset_file_sha256": sha256_file(path)})
    jobs = []
    for job in queue["jobs"]:
        block = prompt_parts(job["prompt"]).get("alpha", "")
        matches_ = [key for key in bad if alpha.get_alpha_template(key)["formula"] in block]
        if job["unit"]["id"] in affected and block:
            jobs.append({"job_id": job["id"], "phase": job["phase"], "variant": job["context"]["variant"],
                         "literal_wrong_formulas_in_alpha_block": matches_})
    return {"main_units_checked": len(rows), "main_units_with_metadata_mismatch": len(affected),
            "main_selected_mismatch_slots": sum(len(row["selected_custom_metadata_mismatches"]) for row in rows),
            "jobs_with_alpha_on_affected_units": len(jobs), "jobs_with_literal_wrong_formula": sum(bool(row["literal_wrong_formulas_in_alpha_block"]) for row in jobs),
            "units": rows, "jobs": jobs, "action": "Giữ nguyên artifacts/prompt; metadata không phải oracle số. Đính chính khi sửa bài, không gán rerun mới cho lịch sử; chưa đo tác động lên LLM outcomes."}, sources


def run_audit(root: Path, output: Path) -> dict:
    """Xuất release độc lập, chặn ghi đè; không sửa runtime, paper hoặc queue đang chạy."""
    root, output = root.resolve(), output.resolve()
    require(output.is_relative_to(root / "outputs/revision") and output != root / "outputs/revision", "Output phải là release riêng")
    require(not output.exists(), "Release đã có; dùng --check hoặc tên mới")
    verify_release(root, root / "outputs/revision/alpha_registry_v1")
    queue = read_json(root / RUN / "manifest.json")
    runtime = {"python": sys.version.split()[0], **{name: version(name) for name in ("numpy", "pandas", "scipy", "TA-Lib")}}
    require(all(queue["runtime"][key] == value for key, value in runtime.items()), "Runtime numeric khác pins queue")
    def check_sources() -> None:
        """Chỉ đọc hash nguồn frozen, không đụng lease/checkpoint/ledger."""
        for row in queue["sources"]: require(sha256_file(root / row["path"]) == row["sha256"], "Nguồn frozen đổi: " + row["path"])
    check_sources()
    cases = read_json(root / FIXTURE)
    observed = {"operators": operator_cases(cases), "features": feature_cases(cases), "translations": translation_cases(),
                "prototype": prototype_cases(), "surrogates": surrogate_cases()}
    require([r["id"] for r in observed["translations"]] == cases["translation_cases"], "Thiếu translation fixture")
    leakage = {"rowwise": rowwise_diagnostics(), "outer_cutoff": cutoff_diagnostics(), "numeric_adapters": numeric_adapter_diagnostics()}
    impact, sources = metadata_impact(root, queue)
    check_sources()
    summary = {"result": "PASS_CONTRACT_AUDIT", "fixture_cases": {k: len(v) for k, v in observed.items()},
               "runtime": runtime, "numeric_adapter_gate": leakage["numeric_adapters"]["result"],
               "native_rowwise_causal_gate": leakage["rowwise"]["native_rowwise_causal_gate"], "outer_cutoff_gate": leakage["outer_cutoff"]["result"],
               "metadata_impact": {k: v for k, v in impact.items() if k not in ("units", "jobs")},
               "limits": ["Fixtures tổng hợp xác minh code đang dùng, không thay thực nghiệm LLM hoặc chứng minh alpha/profitability.",
                          "Native causal gate FAIL là kết quả thật; detection tests PASS không cho phép ghi toàn runtime Zero-Leakage.",
                          "Không chứng minh mọi WorldQuant adaptation tương đương công thức gốc; neutralization thiếu universe/industry không thể xác nhận.",
                          "Alpha_4 và toàn bộ source/input/prompt frozen giữ nguyên; T11–T14/T30 phải giữ phân biệt native diagnostics và controls đã purge."]}
    inherited = root / "outputs/revision/alpha_registry_v1/manifest.json"; sources.add(inherited)
    sources.update(root / row["path"] for row in read_json(inherited)["sources"])
    sources.update(root / p for p in (FIXTURE, RUN / "manifest.json", Path("core/revision_alpha_contract.py"), Path("scripts/audit_alpha_contract.py"),
                   Path("core/revision_baselines.py"), Path("tests/test_revision_alpha_contract.py"), Path("tests/test_revision_alpha_contract_leakage.py")))
    source_rows = [{"path": p.relative_to(root).as_posix(), "sha256": sha256_file(p)} for p in sorted(sources)]
    output.mkdir(parents=True)
    for name, value in (("cases.json", observed), ("leakage.json", leakage), ("metadata_impact.json", impact), ("summary.json", summary)):
        write_json(output / name, safe(value), True)
    write_json(output / "manifest.json", {"schema_version": "alpha_contract_v1", "sources": source_rows,
               "queue_run_signature": queue["sha256"], "frozen_source_hashes_checked_before_after": len(queue["sources"]),
               "network_or_inference": False, "runtime_modified": False,
               "outputs": [{"path": p.name, "sha256": sha256_file(p)} for p in sorted(output.iterdir())]}, True)
    return summary


def check_release(root: Path, output: Path) -> int:
    """Kiểm hash đã khóa, không chạy lại synthetic backtests hoặc API."""
    return verify_release(root, output)
