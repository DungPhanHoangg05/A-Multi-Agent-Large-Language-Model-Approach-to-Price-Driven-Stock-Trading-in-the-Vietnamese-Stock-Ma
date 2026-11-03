"""Đối soát màu/legend/chart-request và version prompt tiếng Anh, không gọi API."""

from __future__ import annotations

import argparse
import ast
import base64
import contextlib
import csv
import hashlib
import io
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import matplotlib.colors as mcolors
from matplotlib.collections import PolyCollection
import mplfinance as mpf
import numpy as np
import pandas as pd
from PIL import Image
from langchain_core.messages import messages_to_dict

from agents.trend_agent import create_trend_agent
from core.revision72_run import checked
from core.revision_common_study import point_state
from core.revision_baselines import load_prices
from utils import static_util
from utils.graph_util import TechnicalTools

POLICY = ROOT / "revision/chart_convention_policy.json"
OUTPUT = ROOT / "outputs/revision/chart_convention_v1"


def sha_bytes(value: bytes) -> str:
    """Hash byte không chuẩn hóa artifacts lịch sử."""
    return hashlib.sha256(value).hexdigest()


def encoded(value: Any) -> bytes:
    """Chặn NaN/Infinity; output chỉ dùng số và kiểu Python nguyên bản."""
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def fixture_frame() -> pd.DataFrame:
    """45 nến có gap khiến dấu Close/Open khác dấu Close/previous-Close; có doji."""
    index = np.arange(45)
    opens = 100. + .07 * index + np.where(index % 2 == 0, -3., 3.)
    closes = opens + np.where(index % 2 == 0, 2., -2.)
    closes[10] = opens[10]
    return pd.DataFrame({"Datetime": pd.bdate_range("2024-01-02", periods=45), "Open": opens,
                         "High": np.maximum(opens, closes) + 1., "Low": np.minimum(opens, closes) - 1.,
                         "Close": closes, "Volume": 1000 + index * 10})


@contextlib.contextmanager
def isolated_work() -> Iterator[None]:
    """Renderer ghi file phụ trong thư mục tạm riêng, không đụng chart/cache cũ."""
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="chart-audit-") as directory:
        try:
            os.chdir(directory)
            yield
        finally:
            os.chdir(previous)


def render(data: dict[str, Any], kind: str, prototype: bool = False,
           legacy_static: ModuleType | None = None) -> tuple[bytes, dict[str, Any]]:
    """Kiểm màu từng polygon/giá thân nến từ renderer thật và legend sau khi lưu."""
    original = mpf.plot
    captured: list[Any] = []

    def capture(frame: pd.DataFrame, **kwargs: Any) -> Any:
        figure, axes = original(frame, **kwargs)
        captured.append((frame, figure, axes[0]))
        return figure, axes

    field = "pattern_image" if kind == "pattern" else "trend_image"
    with isolated_work(), patch.object(mpf, "plot", capture):
        if prototype:
            result = getattr(TechnicalTools, "generate_kline_image" if kind == "pattern" else "generate_trend_image").invoke({"kline_data": data})
        else:
            result = getattr(legacy_static or static_util, "generate_kline_image" if kind == "pattern" else "generate_trend_image")(data)
    frame, _, ax = captured[0]
    body = next(c for c in ax.collections if isinstance(c, PolyCollection))
    alpha = static_util.color.my_color_style["marketcolors"]["alpha"]
    expected = np.where((frame.Open.to_numpy() < frame.Close.to_numpy())[:, None],
                        np.array(mcolors.to_rgba("#006340", alpha))[None, :],
                        np.array(mcolors.to_rgba("#A02128", alpha))[None, :])
    if not np.allclose(body.get_facecolors(), expected, atol=1e-12):
        raise ValueError("Màu polygon không theo Close/Open")
    vertices = np.stack([path.vertices[:, 1] for path in body.get_paths()])
    if not np.allclose(vertices.min(axis=1), np.minimum(frame.Open, frame.Close)) or not np.allclose(vertices.max(axis=1), np.maximum(frame.Open, frame.Close)):
        raise ValueError("Polygon không khớp giá thân nến")
    legend = [t.get_text() for t in ax.get_legend().get_texts()] if ax.get_legend() else []
    lines = {line.get_label(): mcolors.to_hex(line.get_color()) for line in ax.lines if "Support" in line.get_label() or "Resistance" in line.get_label()}
    if kind == "trend":
        if not any("Support" in item for item in legend) or not any("Resistance" in item for item in legend):
            raise ValueError("Thiếu legend hỗ trợ/kháng cự")
        if set(lines.values()) != {"#0000ff", "#ff0000"}:
            raise ValueError("Màu đường hỗ trợ/kháng cự không khớp")
        if any(value != ("#0000ff" if "Support" in label else "#ff0000") for label, value in lines.items()):
            raise ValueError("Đảo màu đường hỗ trợ/kháng cự")
    handles = ax.get_legend().legend_handles if ax.get_legend() else []
    handle_colors = [mcolors.to_hex(h.get_color()) if hasattr(h, "get_color") else "not_line_handle" for h in handles]
    legend_matches = kind == "pattern" or handle_colors == ["#0000ff", "#ff0000"]
    if not legend_matches and legacy_static is None:
        raise ValueError("Handle legend không trỏ đúng đường blue/red")
    image = base64.b64decode(result[field], validate=True)
    pixels = np.array(Image.open(io.BytesIO(image)).convert("RGB"))
    palette = {color: int((np.max(np.abs(pixels.astype(float) - (np.array(mcolors.to_rgb(color)) * alpha + 1 - alpha) * 255), axis=2) <= 1).sum())
               for color in ("#006340", "#A02128")}
    return image, {"n_candles": len(frame), "n_up": int((frame.Close > frame.Open).sum()),
                   "n_down": int((frame.Close < frame.Open).sum()), "n_doji": int((frame.Close == frame.Open).sum()),
                   "body_geometry_and_colors_match": True, "legend": legend, "line_colors": lines,
                   "legend_handle_colors": handle_colors, "legend_handles_match_lines": legend_matches,
                   "palette_pixel_counts": palette, "body_alpha": float(alpha), "png_sha256": sha_bytes(image)}


def prior_source(path: str, policy: dict[str, Any]) -> bytes:
    """Khôi phục serialization LF/CRLF từ Git, chỉ nhận khi khớp hash nguồn R4.

    Git có thể chuẩn hóa newline; không gán commit của blob thành execution commit.
    Không nhận một bản chuyển newline nếu chưa khớp SHA-256 byte đã khóa.
    """
    raw = subprocess.check_output(["git", "show", policy["prior_source_commit"] + ":" + path], cwd=ROOT)
    frozen = json.loads((ROOT / policy["prior_source_manifest"]).read_bytes())
    expected = next(r["sha256"] for r in frozen["source_hashes"] if r["path"] == path)
    lf = raw.replace(b"\r\n", b"\n")
    for candidate in (raw, lf, lf.replace(b"\n", b"\r\n")):
        if sha_bytes(candidate) == expected:
            return candidate
    raise ValueError("Không khôi phục được byte nguồn đã khóa R4: " + path)


def capture_prompt(factory: Any, language: str) -> dict[str, Any]:
    """Model giả chỉ giữ messages, không có client hay network."""
    calls: list[Any] = []
    reply = "**Trend direction:** Up\n**Support level:** 95\n**Resistance level:** 110\n**Trendline slope:** Rising\n**Price vs support:** Bouncing\n**Detailed analysis:** Price near support\n**Trend forecast:** Up\n**Confidence:** Medium"

    class Capture:
        """Thu messages từ đúng node rồi trả report tổng hợp cố định."""
        def invoke(self, messages: Any) -> Any:
            calls.append(messages)
            return SimpleNamespace(content=reply)

    with contextlib.redirect_stdout(io.StringIO()):
        factory(None, Capture(), None)({"language": language, "time_frame": "1 ngày", "kline_data": fixture_frame().to_dict("list"),
                                      "trend_image": "ZmFrZQ==", "messages": []})
    if len(calls) != 1:
        raise ValueError("Capture prompt phát sinh fallback/retry")
    return messages_to_dict(calls[0])


def audit_prompt(policy: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    """Chỉ đổi hai literal English; tiếng Việt và mọi xử lý khác giữ nguyên."""
    old = prior_source("agents/trend_agent.py", policy)
    expected = old.decode().replace("**Green line**", "**Blue line**").replace("green support line", "blue support line")
    if ast.dump(ast.parse(expected)) != ast.dump(ast.parse((ROOT / "agents/trend_agent.py").read_text(encoding="utf-8"))):
        raise ValueError("Trend source đổi ngoài hai literal được phép")
    module = ModuleType("prior_trend_agent")
    exec(compile(old, "prior_trend_agent.py", "exec"), module.__dict__)
    old_vi, new_vi = capture_prompt(module.create_trend_agent, "vi"), capture_prompt(create_trend_agent, "vi")
    old_en, new_en = capture_prompt(module.create_trend_agent, "en"), capture_prompt(create_trend_agent, "en")
    old_text = json.dumps(old_en, ensure_ascii=False).replace("**Green line**", "**Blue line**").replace("green support line", "blue support line")
    if old_vi != new_vi or json.loads(old_text) != new_en:
        raise ValueError("Prompt Việt đổi hoặc English đổi ngoài màu hỗ trợ")
    return {"version": policy["prompt_version"], "comparison_holds_image_fixed": True,
            "vi_messages_unchanged": True, "vi_prompt_text_sha256": sha_bytes(encoded(text_parts(new_vi))),
            "en_only_two_color_literals_changed": True,
            "old_en_sha256": sha_bytes(encoded(old_en)), "new_en_sha256": sha_bytes(encoded(new_en)),
            "vi_sha256": sha_bytes(encoded(new_vi)), "n_new_api_calls": 0}, old


def text_parts(value: Any) -> list[str]:
    """Chỉ lấy text từ messages, không đưa base64 ảnh vào báo cáo."""
    if isinstance(value, dict):
        if value.get("type") == "text":
            return [value["text"]]
        if isinstance(value.get("content"), str):
            return [value["content"]]
        return [t for v in value.values() for t in text_parts(v)]
    return [t for v in value for t in text_parts(v)] if isinstance(value, list) else []


def image_parts(value: Any) -> list[bytes]:
    """Giải mã đúng inline PNG đã gửi; không render lại để thay actual request."""
    if isinstance(value, dict):
        if value.get("type") == "image_url":
            url = value["image_url"]["url"]
            if not url.startswith("data:image/png;base64,"):
                raise ValueError("Ảnh request không phải inline PNG")
            return [base64.b64decode(url.split(",", 1)[1], validate=True)]
        return [p for v in value.values() for p in image_parts(v)]
    return [p for v in value for p in image_parts(v)] if isinstance(value, list) else []


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    """CSV giữ bool/null rõ ràng, không chứa ảnh hay object runtime."""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
    return stream.getvalue().encode()


def generate() -> tuple[dict[str, bytes], list[Path]]:
    """Audit exhaustive chart/request của run đã khóa; tái tạo offline từ cùng giá."""
    policy = json.loads(POLICY.read_bytes())
    frozen_path = ROOT / policy["prior_source_manifest"]
    frozen = {r["path"]: r["sha256"] for r in json.loads(frozen_path.read_bytes())["source_hashes"]}
    old_style = prior_source("utils/color_style.py", policy)
    if sha_bytes(old_style) != frozen["utils/color_style.py"] or ast.dump(ast.parse(old_style)) != ast.dump(ast.parse((ROOT / "utils/color_style.py").read_bytes())):
        raise ValueError("Style đổi hành vi ngoài comments")
    prompt, old_trend = audit_prompt(policy)
    if sha_bytes(old_trend) != frozen["agents/trend_agent.py"]:
        raise ValueError("Blob Trend cũ không khớp source R4")
    old_static = prior_source("utils/static_util.py", policy)
    before = '    ax.legend(\n        ["Support (close)", "Resistance (close)"],'
    after = ('    legend_lines = {line.get_label(): line for line in ax.lines}\n    ax.legend(\n'
             '        handles=[legend_lines["Support"], legend_lines["Resistance"]],\n'
             '        labels=["Support (close)", "Resistance (close)"],')
    expected_static = old_static.decode().replace("\r\n", "\n").replace(before, after)
    if ast.dump(ast.parse(expected_static)) != ast.dump(ast.parse((ROOT / "utils/static_util.py").read_bytes())):
        raise ValueError("Static renderer đổi ngoài gắn legend handles")
    legacy_static = ModuleType("prior_static_util")
    exec(compile(old_static, "prior_static_util.py", "exec"), legacy_static.__dict__)
    unchanged = ["utils/graph_util.py", "agents/pattern_agent.py"]
    if any(sha_bytes((ROOT / p).read_bytes()) != frozen[p] for p in unchanged):
        raise ValueError("Renderer/Pattern source không còn nguyên byte R4")
    bank_path = ROOT / policy["bank"] / "manifest.json"
    bank = json.loads(bank_path.read_bytes()); protocol = bank["protocol"]
    frames, _ = load_prices(ROOT / protocol["price_snapshot"], protocol["price_quality_policy"])
    price_sources = sorted((ROOT / protocol["price_snapshot"]).glob("*.csv")) + [ROOT / protocol["price_snapshot"] / "manifest.json"]
    if any(sha_bytes(p.read_bytes()) != frozen[p.relative_to(ROOT).as_posix()] for p in price_sources):
        raise ValueError("Frozen prices đã đổi")
    sources = [POLICY, frozen_path, bank_path, *price_sources, *[ROOT / p for p in unchanged], ROOT / "utils/color_style.py",
               ROOT / "agents/trend_agent.py", ROOT / "utils/static_util.py", ROOT / "utils/i18n.py", ROOT / "core/backtest_engine.py",
               ROOT / "core/revision_common_study.py", ROOT / "core/revision72_run.py", ROOT / "core/revision_baselines.py",
               Path(__file__), ROOT / "tests/test_chart_convention.py", ROOT / "scripts/run_chart_rerun.py",
               ROOT / "tests/test_chart_rerun.py", ROOT / "revision/r1_provider_policy.json"]
    outputs = {"prior_sources/color_style.py": old_style, "prior_sources/trend_agent.py": old_trend,
               "prior_sources/static_util.py": old_static}
    fixture, fixture_meta = fixture_frame().to_dict("list"), {}
    for prototype in (False, True):
        for kind in ("pattern", "trend"):
            png, meta = render(fixture, kind, prototype)
            fixture_meta[("prototype_" if prototype else "static_") + kind] = meta
            if not prototype:
                outputs["fixture_" + kind + ".png"] = png
    serial_fixture = fixture_frame().copy(); serial_fixture["Datetime"] = serial_fixture.Datetime.dt.strftime("%Y-%m-%d")
    outputs["fixture_ohlcv.csv"] = serial_fixture.to_csv(index=False, lineterminator="\n").encode()
    units = {u["id"]: u for u in bank["units"] + bank["smoke"]}
    archive, cached = [], {}
    run = ROOT / policy["run"]
    for path in sorted(run.glob("shards/org*/charts/*.json")):
        chart = checked(path); unit = units[path.stem]
        feature = ROOT / policy["bank"] / f"features/{unit['symbol']}_{unit['decision']}.json"
        if checked(feature)["sha256"] != chart["asset_hash"]:
            raise ValueError("Chart trỏ khác feature asset")
        state = point_state(frames[unit["symbol"]], unit["symbol"], unit["decision"], protocol, None)
        row = {"path": path.relative_to(ROOT).as_posix(), "sha256": sha_bytes(path.read_bytes()), "unit_id": path.stem, "symbol": unit["symbol"], "smoke": path.stem.startswith("smoke_")}
        for kind, field in (("pattern", "pattern_image"), ("trend", "trend_image")):
            actual = base64.b64decode(chart[field], validate=True)
            reproduced, meta = render(state["kline_data"], kind, legacy_static=legacy_static)
            equal = np.array_equal(np.array(Image.open(io.BytesIO(actual))), np.array(Image.open(io.BytesIO(reproduced))))
            row.update({kind + "_png_sha256": sha_bytes(actual), kind + "_replay_byte_equal": actual == reproduced,
                        kind + "_replay_pixels_equal": bool(equal), kind + "_n_candles": meta["n_candles"],
                        kind + "_legacy_legend_handles_match": meta["legend_handles_match_lines"]})
            cached[(path.parent.parent, path.stem, kind)] = sha_bytes(actual)
        archive.append(row); sources += [path, feature]
        if len(archive) % 20 == 0:
            print(f"Đã đối soát {len(archive)}/107 chart caches từ renderer lịch sử.", flush=True)
    requests = []
    for path in sorted(run.glob("shards/org*/calls/*.request.json")):
        r = checked(path); c = r["context"]
        if c["stage"] != "upstream":
            continue
        kind = "pattern" if c["node"] == "Pattern Agent" else "trend" if c["node"] == "Trend Agent" else None
        if kind is None:
            raise ValueError("Upstream request ngoài hai vision nodes")
        images = image_parts(r["messages"])
        if len(images) != 1 or sha_bytes(images[0]) != cached[(path.parent.parent, c["unit_id"], kind)]:
            raise ValueError("Ảnh actual request không khớp cache cùng unit/shard")
        text = "\n".join(text_parts(r["messages"]))
        if kind == "trend" and ("Đường xanh" not in text or "Đường đỏ" not in text or "Green line" in text):
            raise ValueError("Trend archive khác nhánh Việt đã đối soát")
        requests.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha_bytes(path.read_bytes()),
                         "unit_id": c["unit_id"], "node": c["node"], "smoke": bool(c["smoke"]), "image_matches_cache": True,
                         "image_png_sha256": sha_bytes(images[0]), "en_green_support_present": "Green line" in text,
                         "vi_xanh_support_present": "Đường xanh" in text})
        sources.append(path)
    if len(archive) != 107 or len(requests) != 270:
        raise ValueError("Support chart/request thay đổi")
    r4_path = ROOT / "outputs/revision/r4_value_bank_v1/manifest.json"
    r4 = json.loads(r4_path.read_bytes())
    upstream = sorted({(j["unit_id"], j["realization"]) for j in bank["jobs"]})
    if {(j["unit_id"], j["realization"]) for j in r4["jobs"]} - set(upstream):
        raise ValueError("R4 có upstream scope ngoài protocol dự kiến")
    rerun = {"schema_version": "chart_paired_rerun_proposal_v1", "status": "execution_pending_via_existing_free_provider_pool",
             "renderer_version": policy["renderer_version"], "prompt_version": policy["prompt_version"], "language": "vi",
             "research_trend_groups": [{"unit_id": u, "realization": r} for u, r in upstream],
             "r1_jobs": bank["jobs"], "r4_jobs": r4["jobs"],
             "research_calls": {"trend": len(upstream), "r1_decisions": bank["n_decisions"], "r4_decisions": r4["n_decisions"]},
             "planned_smoke_calls": {"trend": 5, "r1_decisions": 10}, "scheduled_total_calls": 879,
             "internal_attempt_caps": None, "quota_purchase_authorized": False, "provider_policy_ref": "revision/r1_provider_policy.json",
             "model_config": {"trend": {"model": protocol["graph_llm_model"], "temperature": 0, "max_tokens": 1024},
                              "decision": {"model": protocol["agent_llm_model"], "temperature": 0, "max_tokens": 2048, "prompt_chars_exclusive": 6500}},
             "scheduled_max_output_tokens": 1672192,
             "reuse_policy": "Reuse exact OHLCV/news/numeric factors, donor maps, targets, models, branch order and unchanged Pattern reports by unit/realization. Recompute corrected Trend once per group and share it across all branches. Regenerate Decision prompts; never reuse old prompts embedding old Trend reports. Keep original compressed-R1 and full-value-R4 delivery policies separate.",
             "write_policy": "New bank/run identities and output paths only. Old bank/run/checkpoints/receipts immutable. No best-run/seed/checkpoint selection. English correction not evaluated by this VI proposal.",
             "before_api_requirements": ["Use only the five author-asserted Free orgs under the existing provider-only authorization; never buy quota", "Derived bank/source signatures and new run identities validated by existing guards", "Keep request archive/checkpoint/rate/reset guards; no internal caps or automatic deadline; stop only when complete or all eligible providers unavailable", "Review smoke delivery before research, without outcome-based protocol changes"],
             "remaining_execution_work": "Use scripts/run_chart_rerun.py prepare/smoke/run with strict exact-message Pattern cache reuse; prepare-r4/run-r4 follows corrected upstream availability. Existing artifacts stay immutable.",
             "source_hashes": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha_bytes(p.read_bytes())}
                               for p in (bank_path, r4_path, POLICY, ROOT / "utils/static_util.py", ROOT / "agents/trend_agent.py")]}
    sources.append(r4_path)
    report = {"scope": policy["archived_scope"], "n_chart_caches": len(archive), "n_replayed_images": 2 * len(archive),
              "n_actual_vision_attempts": len(requests), "n_pattern_attempts": sum(r["node"] == "Pattern Agent" for r in requests),
              "n_trend_attempts": sum(r["node"] == "Trend Agent" for r in requests),
              "n_byte_equal_images": sum(r[k + "_replay_byte_equal"] for r in archive for k in ("pattern", "trend")),
              "n_pixel_equal_images": sum(r[k + "_replay_pixels_equal"] for r in archive for k in ("pattern", "trend")),
              "n_legacy_trend_images_with_misbound_legend": sum(not r["trend_legacy_legend_handles_match"] for r in archive),
              "renderer_version": policy["renderer_version"], "paired_rerun_required": True,
              "fixture_renderers": fixture_meta, "prompt": prompt, "n_new_api_calls": 0,
              "limits": "Retained Trend images have misbound legend swatches although plotted support/resistance lines are blue/red. Corrected renderer changes historical VI inputs too; shared-upstream paired rerun required before corrected-result/R14 closure. No paid rerun or corrected performance claim. Legacy submission/model comprehension remain unverified."}
    outputs.update({"report.json": encoded(report), "chart_archive.csv": csv_bytes(archive), "request_images.csv": csv_bytes(requests),
                    "rerun_protocol.json": encoded(rerun)})
    return outputs, sorted(set(sources))


def main() -> None:
    """Tạo release riêng; --check tái lập toàn bộ ảnh/records và kiểm hash/runtime."""
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    runtime = {"python": platform.python_version(), **{p: version(p) for p in ("numpy", "pandas", "matplotlib", "mplfinance", "Pillow", "langchain-core")}}
    if OUTPUT.exists() and not args.check:
        raise FileExistsError("Release đã tồn tại; dùng --check")
    if args.check:
        manifest = json.loads((OUTPUT / "manifest.json").read_bytes())
        if manifest["runtime"] != runtime:
            raise ValueError("Runtime không khớp")
        for group, base in (("sources", ROOT), ("outputs", OUTPUT)):
            for r in manifest[group]:
                if sha_bytes((base / r["path"]).read_bytes()) != r["sha256"]:
                    raise ValueError("Hash đã đổi: " + r["path"])
    outputs, sources = generate()
    for name, content in outputs.items():
        path = OUTPUT / name
        if args.check:
            if path.read_bytes() != content:
                raise ValueError("Tái lập không khớp: " + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
        if name in ("fixture_pattern.png", "fixture_trend.png"):
            paper = ROOT / "paper/figs" / ("chart_" + name)
            if args.check:
                if paper.read_bytes() != content:
                    raise ValueError("Fixture bản thảo không khớp")
            else:
                paper.write_bytes(content)
    if not args.check:
        manifest = {"schema_version": "chart_convention_v1", "runtime": runtime,
                    "sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha_bytes(p.read_bytes())} for p in sources],
                    "outputs": [{"path": p, "sha256": sha_bytes((OUTPUT / p).read_bytes())} for p in outputs]}
        (OUTPUT / "manifest.json").write_bytes(encoded(manifest))
    print("PASS: chart/prompt audit và replay offline hoàn tất; không gọi API.")


if __name__ == "__main__":
    main()
