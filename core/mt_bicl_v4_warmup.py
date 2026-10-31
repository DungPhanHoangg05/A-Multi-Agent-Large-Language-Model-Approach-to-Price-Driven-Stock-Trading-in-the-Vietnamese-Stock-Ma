"""Bổ sung giá thô trước2018 cho Alpha, không đổi lịch/nhãn/source giá đã khóa."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from core.execution_prices import PRICE_COLUMNS, load_verified_execution_data, normalise_vci_execution_prices, validate_raw_frame
from core.mt_bicl_v4_completion import DIRECTORY, DataCompletionError
from core.mt_bicl_v4_dataset import immutable
from core.mt_bicl_v4_protocol import checksum, read


class PendingWarmup(DataCompletionError):
    """Chưa có nguồn warmup; verifier không được tự mở network."""


def combine_warmup(symbol: str, records: list[dict[str, Any]], base: pd.DataFrame,
                   settings: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Đối soát mọi nến overlap với nguồn VCI đã qua gate; chỉ append trước neo."""
    frame = normalise_vci_execution_prices(records, symbol, settings["start"], settings["end"])
    anchor = settings["append_only_before"]
    overlap = frame.loc[frame["Datetime"] >= anchor].set_index("Datetime")
    baseline = base.set_index("Datetime")
    columns = [*PRICE_COLUMNS[1:], "Reference"]
    if len(overlap) < 5 or not overlap.index.isin(baseline.index).all():
        raise DataCompletionError("Warmup thiếu overlap2018 để đối soát nguồn thô")
    if not np.allclose(overlap[columns].to_numpy(), baseline.loc[overlap.index, columns].to_numpy(), rtol=0, atol=1e-8):
        raise DataCompletionError("Warmup VCI overlap không bằng giá thực thi đã khóa")
    before = frame.loc[frame["Datetime"] < anchor].copy()
    if len(before) < settings["minimum_pre_anchor_rows"]:
        raise DataCompletionError("Nguồn trước2018 chưa đủ579 nến, không tự hạ warmup600")
    result = pd.concat([before, base.copy(deep=True)], ignore_index=True)
    validate_raw_frame(result)
    # Cột/float vùng nghiên cứu giữ nguyên; không thay bằng dữ liệu mới tải ở overlap.
    pd.testing.assert_frame_equal(result.loc[result["Datetime"] >= anchor].reset_index(drop=True),
                                  base.reset_index(drop=True), check_dtype=False)
    return result, {"symbol": symbol, "pre_anchor_rows": len(before), "overlap_rows": len(overlap),
                    "first_date": str(result["Datetime"].iloc[0].date()), "last_date": str(result["Datetime"].iloc[-1].date()),
                    "warmup_only": True, "pre2018_labels_created": False}


def load_warmup(root: Path, release: dict[str, Any], *, fetch: Callable[..., Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resume theo mã: raw đã lưu không tải lại; chỉ caller online của người dùng truyền fetch."""
    frames, receipts = {}, {}
    settings = release["warmup"]
    symbols = release["config"]["symbol_order"]
    ready_path = root / DIRECTORY / "warmup_verified.json"
    sealed = read(ready_path.read_bytes()) if ready_path.exists() else None
    for symbol in symbols:
        path = root / DIRECTORY / "warmup" / (symbol + ".json")
        if sealed is not None and (not path.exists() or checksum(path.read_bytes()) != sealed["symbols"][symbol]["sha256"]):
            raise DataCompletionError("Nguồn warmup đã seal bị mất/sửa; không tự fetch thay thế")
        if path.exists():
            document = read(path.read_bytes())
        else:
            if fetch is None:
                raise PendingWarmup("Chưa có raw warmup " + symbol + "; cần chạy lệnh thu thập của người dùng")
            url = f"https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/{symbol}/price-history"
            records, pages = fetch(url, {"fromDate": settings["start"].replace("-", ""), "toDate": settings["end"].replace("-", "")})
            document = {"symbol": symbol, "start": settings["start"], "end": settings["end"], "records": records, "pages": pages}
            # Kiểm trước khi seal để không coi response sai schema là nguồn có thể reuse.
            base, _ = load_verified_execution_data(root / "data/execution_prices", symbol)
            combine_warmup(symbol, records, base, settings)
            immutable(path, document)
        if (document["symbol"] != symbol or document["start"] != settings["start"] or document["end"] != settings["end"]):
            raise DataCompletionError("Identity raw warmup khác release")
        base, _ = load_verified_execution_data(root / "data/execution_prices", symbol)
        combined, proof = combine_warmup(symbol, document["records"], base, settings)
        frames[symbol] = combined
        receipts[symbol] = {**proof, "path": path.relative_to(root).as_posix(), "sha256": checksum(path.read_bytes())}
        print(f"Warmup {symbol}: {proof['pre_anchor_rows']} nến trước2018, overlap{proof['overlap_rows']} PASS.", flush=True)
    ready = {"version": "conditional_v4_warmup_verified", "symbols": deepcopy(receipts),
             "no_research_price_or_label_replacement": True}
    immutable(root / DIRECTORY / "warmup_verified.json", ready)
    return frames, ready
