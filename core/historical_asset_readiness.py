"""Phục hồi input nguyên byte và kiểm readiness lịch sử; không fit hoặc gọi API."""

from __future__ import annotations

import ast
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
from typing import Any
import zipfile

import numpy as np
import pandas as pd

from core.backtest_engine import compute_round_trip_net_return

DONOR = "9efd23f4157e0d3ab8069fccab7dccf03439a714"

OUTPUT = Path("outputs/historical_reevaluation")
PRICES = "outputs/revision/r1_prices_v1"
BANK = "outputs/revision/r1_72h_bank_v2"
EVIDENCE = "outputs/revision/execution_evidence_v1"
RELEASE = "docs/plan/week11/mt_bicl_model.json"
ARCHIVE = "docs/plan/implementation_evidence.zip"
CORE4 = {"FPT", "MWG", "VCB", "VNM"}
METHODS = ("Original_common", "bayesian_v1", "C2", "A_tp_pool", "B_semantic", "MT_BICL")


def sha(data: bytes) -> str:
    """Băm byte nguồn, không chuẩn hóa newline hoặc số thực."""
    return hashlib.sha256(data).hexdigest()


def encode(value: Any) -> bytes:
    """Mã hóa xác định và từ chối NaN trong receipt máy."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def git(root: Path, *args: str) -> bytes:
    """Chỉ đọc Git qua argv, không dùng shell hoặc thay branch."""
    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=True).stdout


def destination(root: Path, name: str) -> Path:
    """Chặn đường dẫn thoát namespace và symlink trên cây đích."""
    path = root / OUTPUT / name
    if not path.resolve().is_relative_to((root / OUTPUT).resolve()) or path.is_symlink():
        raise ValueError("Đường dẫn readiness không hợp lệ")
    return path


def preserve(path: Path, data: bytes, verify: bool = False) -> None:
    """Resume chỉ chấp nhận nguyên byte; verify không tạo hoặc sửa file."""
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("Artifact readiness đã đổi: " + path.as_posix())
    elif verify:
        raise ValueError("Thiếu artifact readiness: " + path.as_posix())
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(data)


def import_blob(root: Path, source: str, verify: bool = False) -> tuple[bytes, dict[str, Any]]:
    """Khôi phục đúng blob của fix vào input archive riêng, giữ nguyên raw."""
    oid = git(root, "rev-parse", f"{DONOR}:{source}").decode().strip()
    data = git(root, "cat-file", "blob", oid)
    path = destination(root, "inputs/fix/" + source)
    preserve(path, data, verify)
    return data, {"donor_commit": DONOR, "source_path": source, "blob_oid": oid,
                  "sha256": sha(data), "bytes": len(data),
                  "archive_path": path.relative_to(root).as_posix()}


def price_view(data: bytes) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Giữ policy suffix sau OHLC lỗi của fix, không sửa giá hoặc nối chuỗi."""
    raw = pd.read_csv(io.BytesIO(data))
    dates = pd.to_datetime(raw["date"], errors="raise")
    values = raw[["Open", "High", "Low", "Close"]].to_numpy(dtype=float)
    volume = raw["Volume"].to_numpy(dtype=float)
    if (dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing
            or not np.isfinite(values).all() or (values <= 0).any()
            or not np.isfinite(volume).all() or (volume < 0).any() or volume.sum() <= 0):
        raise ValueError("Ngày/giá/volume raw không hợp lệ")
    bad = ((values[:, 1] < values.max(axis=1)) | (values[:, 2] > values.min(axis=1)))
    offset = int(np.flatnonzero(bad)[-1]) + 1 if bad.any() else 0
    frame = raw.iloc[offset:].reset_index(drop=True)
    if frame.empty:
        raise ValueError("Không có suffix OHLC sạch")
    return frame, {"raw_rows": len(raw), "excluded_prefix_rows": offset,
                   "bad_ohlc_dates": raw.loc[bad, "date"].tolist(),
                   "analysis_first_date": str(frame["date"].iloc[0]),
                   "analysis_last_date": str(frame["date"].iloc[-1])}


def label_oracle(source: bytes) -> Any:
    """Nạp riêng hàm target_fields đã pin, tránh import runtime của nhánh fix."""
    tree = ast.parse(source.decode("utf-8"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "target_fields")
    module = ast.Module(body=[function], type_ignores=[])
    namespace = {"np": np, "pd": pd, "Any": Any, "VERSION": "net_cycle_v1"}
    exec(compile(module, "fix/utils/target_contract.py", "exec"), namespace)
    return namespace["target_fields"]


def check_bridge(frame: pd.DataFrame, decision: int, oracle: Any) -> float:
    """Đối soát entry/exit và nhãn; không xuất outcome query sang input archive."""
    if type(decision) is not int or decision < 0 or decision + 3 >= len(frame):
        raise ValueError("Boundary label bridge không hợp lệ")
    expected = oracle(frame, decision + 1, 3)
    actual = compute_round_trip_net_return(float(frame["Open"].iloc[decision + 1]),
                                           float(frame["Close"].iloc[decision + 3]))
    error = abs(actual - expected["net_return"])
    if (error > 1e-12 or expected["decision_bar_index"] != decision
            or expected["target_horizon_bars"] != 3
            or expected["label_net"] != ("UP" if actual > 0 else "DOWN")):
        raise ValueError("Engine và oracle fix không khớp")
    return float(error)


def grid_audit(frames: dict[str, pd.DataFrame], views: dict[str, Any], bank: dict[str, Any],
               oracle: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Kiểm grid candidate và mapping suffix/raw; chưa khóa protocol hoặc eligibility quyền."""
    grid, errors = [], []
    scopes = set()
    anchors = {u["id"]: u for u in bank["units"]}
    if len(anchors) != 102 or len(bank["schedule"]) != 51:
        raise ValueError("Anchor/scope fix khác audit kế hoạch")
    for scope in bank["schedule"]:
        symbol, fold = scope["symbol"], scope["fold"]
        if (symbol, fold) in scopes:
            raise ValueError("Scope trùng")
        scopes.add((symbol, fold))
        frame, offset = frames[symbol], views[symbol]["excluded_prefix_rows"]
        first, last = scope["test"]
        if first + 57 != last or first < 599:
            raise ValueError("Endpoint/Alpha warmup không khớp")
        if (max(scope["train"]) + 3 >= min(scope["validation"])
                or max(scope["validation"]) + 3 >= first):
            raise ValueError("Label train/validation chưa trưởng thành")
        for index in (first, last):
            identity = f"{symbol}_{fold}_{index}"
            if identity not in anchors or anchors[identity]["date"] != str(frame["date"].iloc[index]):
                raise ValueError("Index/date anchor không khớp suffix")
        previous_exit = None
        for index in range(first, last + 1, 3):
            errors.append(check_bridge(frame, index, oracle))
            date, entry, exit_date = (str(frame["date"].iloc[index + k]) for k in (0, 1, 3))
            if not date < entry <= exit_date or (previous_exit is not None and not previous_exit < entry):
                raise ValueError("Holding span chồng lấn hoặc ngày không hợp lệ")
            previous_exit = exit_date
            grid.append({"id": f"{symbol}_{fold}_{index}", "symbol": symbol, "fold": fold,
                         "suffix_decision_index": index, "raw_decision_index": index + offset,
                         "date": date, "entry_date": entry, "exit_date": exit_date,
                         "core4": symbol in CORE4, "anchor": index in (first, last)})
    if len(grid) != 1020 or len({r["id"] for r in grid}) != 1020:
        raise ValueError("Grid không đủ 1.020 identity duy nhất")
    return grid, {"status": "PASS", "scope": "ENGINE_ORACLE_PARITY_ON_VENDOR_SERIES_ONLY",
                  "grid_cycles": len(grid), "historical_bank_membership_certified": False,
                  "max_abs_error": max(errors), "tolerance": 1e-12,
                  "query_outcomes_exported": False, "execution_data_certified": False,
                  "retrieval_boundary": "exit_date < query_date",
                  "ledger_boundary": "previous_exit < next_entry"}


def frozen_assets(root: Path, release: dict[str, Any], verify: bool) -> dict[str, Any]:
    """Tìm đúng hash ở local, lịch sử Git và archive; không train lại hoặc thay checkpoint."""
    objects: dict[str, list[str]] = {}
    for line in git(root, "rev-list", "--objects", "--all").decode("utf-8").splitlines():
        oid, _, name = line.partition(" ")
        objects.setdefault(name, []).append(oid)
    archive = zipfile.ZipFile(root / ARCHIVE)
    rows = []
    with archive:
        for tree, files in release["artifact_trees"].items():
            for name, expected in files.items():
                original = f"{tree}/{name}"
                path = root / original
                origin, data = None, None
                if path.is_file():
                    data, origin = path.read_bytes(), "local"
                    if sha(data) != expected["sha256"] or len(data) != expected["bytes"]:
                        raise ValueError("Asset local khác release: " + original)
                else:
                    for oid in objects.get(original, []):
                        candidate = git(root, "cat-file", "blob", oid)
                        if sha(candidate) == expected["sha256"]:
                            data, origin = candidate, "git_blob:" + oid
                            break
                    if data is None:
                        for member in archive.namelist():
                            if member == original or member.endswith("/" + original):
                                candidate = archive.read(member)
                                if sha(candidate) == expected["sha256"]:
                                    data, origin = candidate, "archive:" + member
                                    break
                restored = None
                if data is not None:
                    if len(data) != expected["bytes"]:
                        raise ValueError("Asset khác kích thước release")
                    restored = destination(root, "restored/" + original)
                    preserve(restored, data, verify)
                rows.append({"path": original, "expected": expected,
                             "status": "READY" if data is not None else "BLOCKED_ASSET",
                             "origin": origin,
                             "restored_path": restored.relative_to(root).as_posix() if restored else None})
    return {"search_scope": ["local_release_paths", "reachable_git_objects_all_refs", ARCHIVE],
            "archive_sha256": sha((root / ARCHIVE).read_bytes()),
            "expected_files": len(rows), "ready_files": sum(r["status"] == "READY" for r in rows),
            "files": rows}


def overlap_audit(root: Path, frames: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    """Đối chiếu từng ngày/giá với raw develop, giữ riêng ledger quyền cũ."""
    results = []
    for directory in ("data/execution_prices", "data/execution_prices_oos"):
        manifest = json.loads((root / directory / "manifest.json").read_bytes())
        for symbol, record in manifest["files"].items():
            for kind in ("csv", "events", "evidence"):
                item = record[kind]
                if sha((root / directory / item["file"]).read_bytes()) != item["sha256"]:
                    raise ValueError("Nguồn execution cũ khác manifest")
            old = pd.read_csv(root / directory / record["csv"]["file"])
            old["date"] = old["Datetime"].astype(str).str[:10]
            merged = frames[symbol].merge(old, on="date", suffixes=("_fix", "_develop"), validate="one_to_one")
            counts = {}
            for column in ("Open", "Close", "Volume"):
                a, b = (merged[column + suffix].to_numpy(dtype=float) for suffix in ("_fix", "_develop"))
                counts[column] = int((~np.isclose(a, b, atol=1e-8, rtol=0)).sum())
            results.append({"directory": directory, "symbol": symbol, "overlap_rows": len(merged),
                            "first_date": str(merged["date"].min()), "last_date": str(merged["date"].max()),
                            "different_rows": counts, "old_price_basis": manifest["price_basis"],
                            "old_price_unit": manifest["price_unit"], "series_spliced": False,
                            "events_coverage_end": manifest["requested_end"],
                            "corporate_action_policy": manifest["corporate_action_policy"]})
    return results


def news_audit(news: dict[str, Any], scores: dict[str, Any], articles: dict[str, Any],
               bank: dict[str, Any]) -> dict[str, Any]:
    """Đối soát membership/score và availability ngày sau, không chứng nhận archived content."""
    if sha(json.dumps(news, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()) != bank["news_hash"]:
        raise ValueError("News không khớp bank fix")
    lookup = {a["article_id"]: a for a in articles["articles"]}
    count, identities = 0, set()
    for symbol, records in news.items():
        seen = set()
        for row in records:
            identity = row["article_id"]
            article = lookup[identity]
            if (identity in seen or symbol not in article["symbols"] or not article["eligible_source"]
                    or not row.get("date_parsed") or row["date_parsed"] != article["date_parsed"]
                    or pd.Timestamp(row["available_at"]) != pd.Timestamp(row["date_parsed"]) + pd.Timedelta(days=1)
                    or row["scorer_revision"] != scores["revision"]
                    or row["numeric_score"] != scores["scores"][identity]["numeric_score"]):
                raise ValueError("Membership/score/availability tin không hợp lệ")
            seen.add(identity)
            identities.add(identity)
            count += 1
    return {"membership_count": count, "unique_scored_articles": len(identities),
            "scorer_revision": scores["revision"], "status": "FROZEN_SCORES_VERIFIED",
            "content_pit_certified": False, "availability_policy": "DATE_ONLY_NEXT_DAY",
            "downstream_normalizer_and_extended_coverage": "H04_REQUIRED"}


def run(root: Path, *, verify: bool = False) -> dict[str, Any]:
    """Tạo hoặc cold-verify readiness độc lập; không cấp quyền inference/training."""
    root = root.resolve()
    sources, blobs = [], {}
    names = [f"{PRICES}/manifest.json", f"{BANK}/manifest.json", f"{BANK}/news.json",
             f"{BANK}/article_audit.json", f"{BANK}/local_scores.json", "utils/target_contract.py",
             "core/revision_baselines.py", "core/revision72_data.py",
             *[f"{EVIDENCE}/{n}" for n in ("manifest.json", "calendar.json", "sources.json", "sample_audit.json")]]
    for name in names:
        data, receipt = import_blob(root, name, verify)
        sources.append(receipt)
        blobs[name] = data
    bank = json.loads(blobs[f"{BANK}/manifest.json"])
    price_manifest = json.loads(blobs[f"{PRICES}/manifest.json"])
    frames, views = {}, {}
    for record in price_manifest["symbols"]:
        data, receipt = import_blob(root, f"{PRICES}/{record['path']}", verify)
        if receipt["sha256"] != record["sha256"]:
            raise ValueError("CSV khác manifest fix")
        sources.append(receipt)
        frame, view = price_view(data)
        if (view["raw_rows"] != record["n_rows"] or view["analysis_last_date"] != record["last_date"]):
            raise ValueError("CSV khác khoảng ngày/số dòng manifest")
        frames[record["symbol"]], views[record["symbol"]] = frame, view
    missing_raw_news = []
    for record in bank["article_sources"]:
        # Cache legacy bị ignore trong donor; frozen news vẫn có blob độc lập.
        exists = subprocess.run(["git", "cat-file", "-e", f"{DONOR}:{record['path']}"],
                                cwd=root, capture_output=True, check=False)
        if exists.returncode:
            missing_raw_news.append({**record, "status": "BLOCKED_ASSET", "reason": "NOT_IN_DONOR_GIT"})
            continue
        _, receipt = import_blob(root, record["path"], verify)
        if receipt["sha256"] != record["sha256"]:
            raise ValueError("Cache tin raw khác manifest")
        sources.append(receipt)
    oracle = label_oracle(blobs["utils/target_contract.py"])
    grid, bridge = grid_audit(frames, views, bank, oracle)
    calendar = json.loads(blobs[f"{EVIDENCE}/calendar.json"])
    business = np.busdaycalendar(weekmask=calendar["weekmask"], holidays=calendar["holidays"])
    entries = np.asarray([r["entry_date"] for r in grid], dtype="datetime64[D]")
    exits = np.asarray([r["exit_date"] for r in grid], dtype="datetime64[D]")
    settlements = np.busday_offset(entries, 2, busdaycal=business, roll="forward")
    release = json.loads((root / RELEASE).read_bytes())
    payload = release["payload"]
    if sha(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()) != release["sha256"]:
        raise ValueError("Model package MT-BICL sai envelope")
    assets = frozen_assets(root, payload, verify)
    vnindex_path = "data/historical/VNINDEX.csv"
    vnindex = pd.read_csv(root / vnindex_path)
    end = str(vnindex["Datetime"].iloc[-1])[:10]
    missing_index = sorted({r["date"] for r in grid if r["date"] > end})
    model = json.loads((root / "data_manager/regime_model.json").read_bytes())["payload"]["metadata"]
    dependencies = {"VNINDEX_2026": {"status": "BLOCKED_ASSET" if missing_index else "READY",
                    "path": vnindex_path, "last_date": end, "missing_cutoff_dates": missing_index},
                    "FROZEN_MT_ASSETS": {"status": "READY" if assets["ready_files"] == assets["expected_files"] else "BLOCKED_ASSET"},
                    "EXECUTION_DATA": {"status": "PENDING_EXECUTION_DATA",
                    "reason": "Thiếu ledger quyền, đơn vị và lịch/khả năng khớp lệnh đã xác minh cho 9 mã tới 2026."}}
    registry = []
    for method in METHODS:
        blocked = []
        if method != "Original_common" and missing_index:
            blocked.append("VNINDEX_2026")
        if method == "MT_BICL" and assets["ready_files"] != assets["expected_files"]:
            blocked.append("FROZEN_MT_ASSETS")
        registry.append({"method": method, "status": "BLOCKED_ASSET" if blocked else "READY",
                         "blocking_dependencies": blocked, "scope": "ASSET_DATA_ONLY_FULL_1020_GRID",
                         "price_quality": "VENDOR_SERIES_LIMITED", "inference_released": False})
    # Neo các input develop và mã thực sự được dùng; không tự ghi hash nguồn đã đổi.
    local_paths = [RELEASE, ARCHIVE, vnindex_path, "data_manager/regime_model.json",
                   "docs/plan/week11/mt_bicl_protocol.json", "core/backtest_engine.py",
                   "core/historical_asset_readiness.py", "scripts/prepare_historical_assets.py"]
    local_paths.extend(p.relative_to(root).as_posix() for p in sorted((root / "core").glob("mt_bicl*.py")))
    for directory in ("data/execution_prices", "data/execution_prices_oos"):
        local_paths.extend(p.relative_to(root).as_posix() for p in sorted((root / directory).glob("*")) if p.is_file())
    source_commit = git(root, "log", "-1", "--format=%H", "--", *local_paths).decode().strip()
    local_sources = []
    for name in local_paths:
        expected = git(root, "show", f"{source_commit}:{name}")
        actual = (root / name).read_bytes()
        checkout_crlf = actual != expected and actual.replace(b"\r\n", b"\n") == expected
        if actual != expected and not checkout_crlf:
            raise ValueError("Input/source develop khác mốc khóa: " + name)
        local_sources.append({"path": name, "commit": source_commit, "sha256": sha(actual), "bytes": len(actual),
                              "git_blob_sha256": sha(expected), "git_blob_bytes": len(expected),
                              "checkout_crlf_only": checkout_crlf,
                              "blob_oid": git(root, "rev-parse", f"{source_commit}:{name}").decode().strip()})
    result = {"version": "historical_asset_readiness_v1", "status": "AUDIT_COMPLETE_WITH_BLOCKERS",
              "donor_commit": DONOR, "base_commit": source_commit, "runtime_python": platform.python_version(),
              "source_archive": sources, "local_sources": local_sources, "price_views": views,
              "grid": {"units": len(grid), "core4": sum(r["core4"] for r in grid),
                       "anchor_units": sum(r["anchor"] for r in grid), "cutoff_dates": len({r["date"] for r in grid}),
                       "by_fold": dict(Counter(r["fold"] for r in grid)), "eligibility_final": False},
              "label_bridge": bridge, "frozen_assets": assets, "dependencies": dependencies, "registry": registry,
              "hmm_existing": {"fit_end": model["train_end_date"], "method": model["classification_method"],
                               "frozen_model_compatibility_requires_verification": True},
              "news": news_audit(json.loads(blobs[f"{BANK}/news.json"]), json.loads(blobs[f"{BANK}/local_scores.json"]),
                                 json.loads(blobs[f"{BANK}/article_audit.json"]), bank),
              "legacy_raw_news_cache": missing_raw_news,
              "calendar": {"scope": "DONOR_SETTLEMENT_CALENDAR_ONLY_NOT_EXCHANGE_FILL_CERTIFICATION",
                           "nonbusiness_entries": int((~np.is_busday(entries, busdaycal=business)).sum()),
                           "nonbusiness_exits": int((~np.is_busday(exits, busdaycal=business)).sum()),
                           "exit_vs_t_plus_2_mismatches": int((settlements != exits).sum())},
              "execution_overlap": overlap_audit(root, frames),
              "authorization": {"inference": False, "training": False, "refit": False, "api": False}}
    code = ("core/historical_asset_readiness.py", "scripts/prepare_historical_assets.py")
    result["audit_source_sha256"] = {name: sha((root / name).read_bytes()) for name in code}
    preserve(destination(root, "manifests/candidate_grid.json"), encode(grid), verify)
    result["candidate_grid_sha256"] = sha(encode(grid))
    preserve(destination(root, "manifests/asset_readiness.json"), encode(result), verify)
    return result
