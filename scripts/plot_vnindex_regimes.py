"""Vẽ regime hồi cứu trên tập train và regime PIT đã kiểm toán của Memory Bank."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.bayesian_memory import atomic_write_json, read_json
from core.regime_detector import (
    FEATURE_COLUMNS, MarketRegimeDetector, TRAIN_END, TRAIN_START,
    _fallback_regime, build_regime_features, training_data_hash,
)

COLORS = {"BULL": "#15936b", "BEAR": "#dc5260", "CHOPPY": "#e8ad36", "CONSOLIDATION": "#6484cf"}


def retrospective_states(detector: MarketRegimeDetector, train: pd.DataFrame) -> pd.DataFrame:
    """Phân loại hồi cứu bằng model toàn tập train; tuyệt đối không gọi là nhãn PIT."""
    features = build_regime_features(train, TRAIN_END)
    if training_data_hash(train) != detector.metadata["training_data_sha256"]:
        raise ValueError("Biểu đồ không khớp dữ liệu train của model")
    raw = features.loc[:, FEATURE_COLUMNS].to_numpy(dtype=float)
    meta = detector.metadata
    if meta["classification_method"] == "HMM":
        posterior = detector._model.predict_proba(detector._scaler.transform(raw))
        names = np.asarray(meta["latent_state_names"])[np.argmax(posterior, axis=1)]
    else:
        names = np.asarray([_fallback_regime(row, meta) for row in raw])
    return pd.DataFrame({"Datetime": features.Datetime.to_numpy(), "regime": names})


def plot(output: Path) -> dict:
    """Xác minh đầu vào, vẽ hai loại nhãn tường minh và ghi manifest của hình."""
    csv_path = ROOT / "data/historical/VNINDEX.csv"
    manifest = read_json(csv_path.parent / "manifest.json")
    if hashlib.sha256(csv_path.read_bytes()).hexdigest() != manifest["files"]["VNINDEX"]["sha256"]:
        raise ValueError("CSV VNINDEX sai checksum")
    archive = pd.read_csv(csv_path, parse_dates=["Datetime"])
    train = archive.loc[archive.Datetime.between(TRAIN_START, TRAIN_END)].copy()
    detector = MarketRegimeDetector.load(ROOT / "data_manager/regime_model.json",
                                         expected_training_hash=training_data_hash(train))
    states = retrospective_states(detector, train)
    bank_path = ROOT / "data_manager/regime_memory_store.json"
    qa = read_json(ROOT / "docs/plan/week2/memory_bank_audit.json")
    if qa["status"] != "PASS" or qa["bank_sha256"] != hashlib.sha256(bank_path.read_bytes()).hexdigest():
        raise ValueError("Kho dùng cho panel PIT chưa có QA khớp checksum")
    bank = pd.DataFrame(read_json(bank_path))
    if bank.groupby("as_of_date")["regime"].nunique().max() != 1:
        raise ValueError("Các episode cùng ngày có regime VNINDEX khác nhau")
    pit = bank[["as_of_date", "regime"]].drop_duplicates().sort_values("as_of_date")
    dates = pd.to_datetime(pit.as_of_date)
    if not dates.between(TRAIN_START, TRAIN_END).all():
        raise ValueError("Panel PIT chứa điểm ngoài 2018–2022")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, (ax, lower) = plt.subplots(2, 1, figsize=(14, 8), sharex=True,
        gridspec_kw={"height_ratios": [3.6, 1.3], "hspace": 0.35})
    fig.subplots_adjust(left=0.12, right=0.98, top=0.82, bottom=0.17)
    fig.suptitle("VN-INDEX · CHẾ ĐỘ THỊ TRƯỜNG 2018–2022", x=0.12, ha="left", y=0.98,
                 fontsize=19, weight="bold")
    fig.text(0.12, 0.905, "HMM 4 trạng thái · seed 42 · dữ liệu VCI/KBS đã kiểm checksum", fontsize=11)
    start_dates = states.Datetime.to_numpy()
    names = states.regime.to_numpy()
    boundaries = np.r_[0, np.flatnonzero(names[1:] != names[:-1]) + 1, len(names)]
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        end = pd.Timestamp(start_dates[right]) if right < len(names) else train.Datetime.iloc[-1]
        ax.axvspan(pd.Timestamp(start_dates[left]), end, color=COLORS[names[left]], alpha=0.19, linewidth=0)
    ax.axvspan(train.Datetime.iloc[0], states.Datetime.iloc[0], color="#dce1e7", alpha=0.6)
    ax.plot(train.Datetime, train.Close, color="#202b3a", linewidth=1.15)
    ax.set_title("A. Nhãn hồi cứu trên tập train — model/scaler fit toàn bộ 2018–2022", loc="left", fontsize=11)
    ax.set_ylabel("VN-Index (điểm)")
    ax.grid(axis="y", alpha=0.2)
    ax.legend(handles=[Patch(facecolor=color, alpha=0.45, label=name) for name, color in COLORS.items()]
              + [Patch(facecolor="#dce1e7", label="199 phiên khởi động")],
              ncol=5, loc="upper left", frameon=False, fontsize=9)
    for index, (name, color) in enumerate(COLORS.items()):
        selected = pit.regime.eq(name).to_numpy()
        lower.scatter(dates.loc[selected], np.full(int(selected.sum()), index), color=color, marker="s", s=15)
    lower.set_yticks(range(4), list(COLORS))
    lower.set_ylim(-0.7, 3.7)
    lower.set_title("B. Regime PIT của Memory Bank — model prefix chỉ học đến ngày quyết định", loc="left", fontsize=11)
    lower.grid(axis="y", alpha=0.18)
    lower.set_xlabel("Ngày giao dịch")
    lower.xaxis.set_major_locator(mdates.YearLocator())
    lower.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    lower.set_xlim(pd.Timestamp("2018-01-01"), pd.Timestamp("2022-12-31"))
    for axis in (ax, lower):
        axis.spines[["top", "right"]].set_visible(False)
    fig.text(0.12, 0.085, "Panel A dùng posterior có dữ liệu cả tập train: chỉ minh họa hồi cứu, không dùng làm nhãn giao dịch PIT.", fontsize=9)
    fig.text(0.12, 0.055, f"Panel B: {len(pit)} ngày quyết định / {len(bank)} episode; thiếu 2018–2019 do warm-up 600 phiên. Chỉ hiển thị 2018–2022.", fontsize=9)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=300, facecolor="white")
    fig.savefig(output.with_suffix(".svg"), facecolor="white")
    plt.close(fig)
    receipt = {"format_version": 1, "training_sha256": training_data_hash(train),
        "training_rows": len(train), "retrospective_rows": len(states), "pit_dates": len(pit),
        "bank_records": len(bank), "bank_sha256": qa["bank_sha256"],
        "retrospective_counts": dict(sorted(Counter(names.tolist()).items())),
        "pit_counts": dict(sorted(Counter(pit.regime.tolist()).items())),
        "png_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "svg_sha256": hashlib.sha256(output.with_suffix(".svg").read_bytes()).hexdigest(),
        "retrospective_method": "full_training_posterior", "pit_method": "audited_prefix_models"}
    atomic_write_json(output.with_suffix(".manifest.json"), receipt)
    return receipt


def main() -> None:
    """Xuất biểu đồ nghiên cứu; không fit lại model hoặc gọi LLM."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/vnindex_regimes_2018_2022.png")
    args = parser.parse_args()
    result = plot(args.output)
    print(f"Đã vẽ {result['training_rows']} phiên VNINDEX và {result['pit_dates']} ngày regime PIT: {args.output}")


if __name__ == "__main__":
    main()
