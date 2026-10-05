"""Cấu hình prior và biên state; không đọc kho, truy xuất hay xác minh nguồn PIT."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
from typing import Any, TypedDict


type JSONValue = None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]


class PriorConfig(TypedDict):
    """Tám trường cấu hình runtime độc lập với cấu hình ablation."""

    enable_bayesian_prior: bool
    mode: str
    k: int
    seed: int
    scope: str
    bank_path: str
    manifest_path: str
    audit_path: str


class MarketRegimeState(TypedDict):
    """Trạng thái regime; bằng chứng nguồn được lưu riêng trong provenance."""

    as_of_date: str
    regime_id: int
    regime_name: str
    volatility_level: str
    trend_strength: float
    source_symbol: str
    feature_end_date: str


CONTRACT_VERSION = "prior_runtime_contract_v1"
ROOT = Path(__file__).resolve().parents[1]
PRIOR_STATE_FIELDS = (
    "prior_config", "market_regime", "current_signals", "prior_provenance",
    "prior_tasks", "prior_stats", "prior_metadata", "bayesian_prior_context",
)
_DEFAULTS: PriorConfig = {
    "enable_bayesian_prior": False, "mode": "bayesian_regime", "k": 3,
    "seed": 42, "scope": "same_symbol",
    "bank_path": "data_manager/regime_memory_store.json",
    "manifest_path": "data_manager/regime_memory_store.manifest.json",
    "audit_path": "docs/plan/week2/memory_bank_audit.json",
}
_MODES = {"bayesian_regime", "random", "recent", "similarity"}
_SCOPES = {"same_symbol", "pooled"}
_PATH_FIELDS = ("bank_path", "manifest_path", "audit_path")
_DUPLICATE_FIELDS = {"current_regime", "regime_name", "selected_ids", "prior_result"}
_QUERY_OUTCOME_FIELDS = {
    "actual_direction", "actual_pct_change", "entry_date", "exit_date",
    "entry_open", "exit_close", "net_return", "net_return_pct", "outcome",
}


def _relative_path(value: Any, field: str) -> None:
    """Kiểm cú pháp POSIX tương đối mà không chạm filesystem."""
    if (type(value) is not str or not value or value.startswith("/")
            or "\\" in value or ":" in value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ValueError(f"{field} phải là đường dẫn POSIX tương đối trong repo")


def normalize_prior_config(config: dict[str, Any] | None = None) -> PriorConfig:
    """Bổ sung default trên bản sao; từ chối sai kiểu/enum/range kể cả khi tắt."""
    if config is not None and type(config) is not dict:
        raise ValueError("prior_config phải là dict Python gốc hoặc None")
    supplied = {} if config is None else config
    if any(type(key) is not str or key not in _DEFAULTS for key in supplied):
        raise ValueError("prior_config chứa trường không được hỗ trợ")
    result = _DEFAULTS.copy()
    result.update(supplied)
    if type(result["enable_bayesian_prior"]) is not bool:
        raise ValueError("enable_bayesian_prior phải là bool Python gốc")
    for field, allowed in (("mode", _MODES), ("scope", _SCOPES)):
        if type(result[field]) is not str or result[field] not in allowed:
            raise ValueError(f"{field} không thuộc enum đã khóa")
    for field, maximum in (("k", 3), ("seed", 2**32 - 1)):
        if type(result[field]) is not int or not 0 <= result[field] <= maximum:
            raise ValueError(f"{field} phải là int Python gốc trong khoảng 0..{maximum}")
    for field in _PATH_FIELDS:
        _relative_path(result[field], field)
    return result


def resolve_prior_paths(
    config: dict[str, Any] | None = None, *, root: Path = ROOT,
) -> dict[str, Path] | None:
    """Resolve đường dẫn enabled trong repo; tắt không resolve hoặc đọc file."""
    normalized = normalize_prior_config(config)
    if not normalized["enable_bayesian_prior"]:
        return None
    repository = root.resolve(strict=True)
    paths: dict[str, Path] = {}
    for field in _PATH_FIELDS:
        # Kiểm containment trước existence để cả symlink lỗi cũng không thoát repo.
        path = (repository / normalized[field]).resolve()
        if not path.is_relative_to(repository):
            raise ValueError(f"{field} resolve ra ngoài repo")
        if not path.is_file():
            raise FileNotFoundError(f"Thiếu file nguồn prior: {field}")
        paths[field] = path
    return paths


def validate_prior_execution(
    config: dict[str, Any] | None = None, *, is_backtest: Any,
    time_frame: Any, ablation_config: dict[str, Any] | None = None,
    include_alpha: Any = None,
) -> tuple[PriorConfig, dict[str, bool], Any]:
    """Kiểm Full/backtest/daily cho enabled; giữ resolver và alias legacy khi tắt."""
    normalized = normalize_prior_config(config)
    if normalized["enable_bayesian_prior"]:
        if type(is_backtest) is not bool or is_backtest is not True:
            raise ValueError("Prior enabled chỉ được dùng trong backtest")
        if type(time_frame) is not str or time_frame not in {"1d", "1 ngày"}:
            raise ValueError("Prior enabled yêu cầu daily 1d hoặc 1 ngày")
        if include_alpha is not None and (type(include_alpha) is not bool or not include_alpha):
            raise ValueError("Prior enabled yêu cầu include_alpha=None hoặc True")
        if ablation_config is not None:
            keys = {"enable_alpha_factors", "enable_sentiment"}
            if (type(ablation_config) is not dict or set(ablation_config) != keys
                    or any(type(value) is not bool or not value for value in ablation_config.values())):
                raise ValueError("Prior enabled chỉ hỗ trợ ablation Full với hai bool True")
        time_frame = "1d"
    # Import tại lúc gọi để không tạo vòng import với graph_setup.
    from utils.graph_setup import resolve_ablation_config

    ablation = resolve_ablation_config(ablation_config, include_alpha)
    return normalized, ablation, time_frame


def copy_prior_json(value: Any) -> JSONValue:
    """Kiểm scalar JSON gốc/finite và sao chép sâu; không coercion dữ liệu lỗi."""
    def check(item: Any) -> None:
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("JSON prior phải dùng key str Python gốc")
            for child in item.values():
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        elif item is None or type(item) in (bool, int, str):
            return
        elif type(item) is float:
            if not math.isfinite(item):
                raise ValueError("JSON prior chứa NaN hoặc Infinity")
        else:
            raise ValueError("JSON prior chứa kiểu runtime hoặc scalar không phải Python gốc")

    check(value)
    return deepcopy(value)


def normalize_prior_query_context(state: dict[str, Any]) -> dict[str, JSONValue]:
    """Kiểm shape/ngày/tín hiệu trên bản sao; không coi đây là xác minh nguồn PIT."""
    from core.bayesian_memory import SYMBOLS, iso_date
    from core.bayesian_retriever import normalize_signals
    from core.regime_detector import validate_regime_state

    if type(state) is not dict or _QUERY_OUTCOME_FIELDS.intersection(state):
        raise ValueError("State query không được chứa outcome của test point")
    symbol = state.get("stock_name")
    if type(symbol) is not str or symbol not in SYMBOLS:
        raise ValueError("Mã nghiên cứu phải thuộc FPT/MWG/VCB/VNM")
    cutoff = iso_date(state.get("as_of_date"))
    regime = copy_prior_json(state.get("market_regime"))
    validate_regime_state(regime)
    if regime["as_of_date"] != cutoff:
        raise ValueError("Ngày regime phải bằng cutoff của query")
    signals = copy_prior_json(state.get("current_signals"))
    signals = normalize_signals(signals)
    return {"stock_name": symbol, "as_of_date": cutoff,
            "market_regime": regime, "current_signals": signals}


def normalize_prior_state(state: dict[str, Any]) -> dict[str, Any]:
    """Giữ state legacy; chuẩn hóa field prior và chặn enabled chưa có adapter PIT."""
    if type(state) is not dict:
        raise ValueError("State phải là dict Python gốc")
    output = state.copy()
    if not any(field in state for field in PRIOR_STATE_FIELDS):
        return output
    if _DUPLICATE_FIELDS.intersection(state):
        raise ValueError("State prior chứa field trùng nguồn thông tin đã khóa")
    config = normalize_prior_config(state.get("prior_config"))
    for field in PRIOR_STATE_FIELDS:
        if field in state:
            output[field] = copy_prior_json(state[field])
    output["prior_config"] = config
    if not config["enable_bayesian_prior"]:
        for field in PRIOR_STATE_FIELDS[1:]:
            if field not in output:
                continue
            value = output[field]
            valid = (type(value) is list and not value) if field == "prior_tasks" else (
                type(value) is str and value == "" if field == "bayesian_prior_context" else value is None
            )
            if not valid:
                raise ValueError(f"Prior disabled không nhận dữ liệu còn sót ở {field}")
        return output
    validate_prior_execution(
        config, is_backtest=state.get("is_backtest"), time_frame=state.get("time_frame"),
        ablation_config=state.get("ablation_config"),
    )
    if _QUERY_OUTCOME_FIELDS.intersection(state):
        raise ValueError("State query không được chứa outcome của test point")
    if any(output.get(field) is None for field in ("market_regime", "current_signals", "prior_provenance")):
        raise ValueError("Prior enabled thiếu regime/signals/provenance đã xác minh PIT")
    normalize_prior_query_context(output)
    # Dict provenance tự khai chưa chứng minh được artifact/nguồn thật. Adapter
    # W4-09 sẽ cung cấp biên xác minh; graph hiện tại không được âm thầm bỏ prior.
    raise ValueError("Prior enabled chưa có adapter xác minh nguồn PIT; không chạy graph legacy")
