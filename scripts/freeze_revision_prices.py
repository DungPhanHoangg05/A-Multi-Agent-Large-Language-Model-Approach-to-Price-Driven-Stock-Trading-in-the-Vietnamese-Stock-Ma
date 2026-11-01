"""Tải riêng OHLCV công khai phục vụ R1; không dùng fallback synthetic hoặc LLM."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.revision_audit import DEFAULT_SYMBOLS, sha256_file


def main() -> None:
    """Khóa từng mã độc lập và chỉ xuất manifest hoàn tất sau khi đủ chín mã."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/revision/r1_prices_v1")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("Thư mục đã tồn tại; không ghi đè snapshot")
    from vnstock.api.quote import Quote
    import pandas as pd

    output.mkdir(parents=True)
    records = []
    for symbol in DEFAULT_SYMBOLS:
        fetched = datetime.now(timezone.utc).isoformat()
        frame = Quote(symbol=symbol, source="VCI").history(
            start="2020-01-01", end="2026-09-30", interval="1D")
        frame = frame.rename(columns={"time": "date", "open": "Open", "high": "High",
                                      "low": "Low", "close": "Close", "volume": "Volume"})
        frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
        frame = frame.loc[frame["date"].between("2020-01-01", "2026-09-30"),
                          ["date", "Open", "High", "Low", "Close", "Volume"]].copy()
        frame = frame.sort_values("date").reset_index(drop=True)
        if len(frame) < 900 or frame["date"].duplicated().any():
            raise ValueError(f"{symbol}: snapshot thiếu lịch sử hoặc trùng ngày")
        path = output / f"{symbol}.csv"
        frame.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")
        records.append({"symbol": symbol, "path": path.name, "sha256": sha256_file(path),
                        "n_rows": len(frame), "first_date": frame["date"].iloc[0],
                        "last_date": frame["date"].iloc[-1], "retrieved_at_utc": fetched})
        print(f"Đã khóa {symbol}: {len(frame)} phiên quan sát")
    manifest = {
        "schema_version": "r1_reconstructed_prices_v1", "source": "vnstock/VCI",
        "vnstock_version": version("vnstock"), "requested_start": "2020-01-01",
        "requested_end": "2026-09-30", "timezone": "Asia/Ho_Chi_Minh",
        "status": "new_retrieval_not_authenticated_historical_run_snapshot",
        "adjustment_policy": "vendor_returned_series; action/dividend ledger unavailable",
        "calendar_policy": "observed vendor daily sessions; not independently certified exchange calendar",
        "price_unit": "vendor quote units; relative-return ledger uses consistent units",
        "symbols": records,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8", newline="\n")
    print("Snapshot hoàn tất; chưa đồng nghĩa đã xác minh snapshot dùng cho submission.")


if __name__ == "__main__":
    main()
