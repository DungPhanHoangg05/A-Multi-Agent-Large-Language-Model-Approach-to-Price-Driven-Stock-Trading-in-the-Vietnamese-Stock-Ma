"""Khóa protocol advisor v4 bằng metadata; không nạp model, payoff hoặc credential."""

from __future__ import annotations

from datetime import date
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
from typing import Any

DIRECTORY = Path("docs/plan/week11")
PROTOCOL = DIRECTORY / "protocol_v4.json"
LOCK = DIRECTORY / "protocol_lock_v4.json"
PROTOCOL_SHA256 = "ce868c6373548b207bc6d7d0a03bdb2c291bbcb95f47f0f33e3a3918cc8ccdf9"
SOURCES = ("core/mt_bicl_v4_protocol.py", "scripts/verify_mt_bicl_protocol_v4.py",
           "tests/test_mt_bicl_v4_protocol.py", "tests/test_mt_bicl_v4_protocol_leakage.py")
BRANCHES = ("Original", "A_reference", "Plain_ICL", "Full_conditional_MT",
            "Target_only_K0", "Pooled_context", "No_target", "No_agent_features",
            "Numerical_MT", "Hierarchical_reference")


def canonical(value: Any) -> bytes:
    """Chỉ nhận kiểu JSON Python gốc, từ chối NaN và kiểu scalar ngoại lai."""
    def native(item: Any) -> None:
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("Khóa JSON phải là chuỗi gốc")
            for child in item.values():
                native(child)
        elif type(item) is list:
            for child in item:
                native(child)
        elif item is not None and type(item) not in (str, bool, int, float):
            raise ValueError("Protocol chứa kiểu JSON không nguyên bản")
    native(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def checksum(data: bytes) -> str:
    """Băm byte, không thay đổi bằng chứng nguồn."""
    return hashlib.sha256(data).hexdigest()


def read(data: bytes) -> dict[str, Any]:
    """Từ chối khóa JSON trùng và số không hữu hạn trước khi dùng metadata."""
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("JSON có khóa trùng")
            result[key] = value
        return result
    value = json.loads(data, object_pairs_hook=pairs)
    canonical(value)
    if type(value) is not dict:
        raise ValueError("Protocol phải là object JSON")
    return value


def safe_path(root: Path, name: str) -> Path:
    """Không nhận đường dẫn tuyệt đối, traversal hoặc symlink thoát workspace."""
    if (type(name) is not str or not name or ":" in name or "\\" in name
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise ValueError("Đường dẫn protocol không hợp lệ")
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Đường dẫn protocol vượt workspace")
    return path


def git(root: Path, *args: str) -> bytes:
    """Chỉ đọc object Git, không checkout hoặc sửa nguồn."""
    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE)


def validate_protocol(data: bytes) -> dict[str, Any]:
    """Hash cố định không cho tự nới gate rồi băm lại receipt để hợp thức hóa."""
    if checksum(data) != PROTOCOL_SHA256:
        raise ValueError("Protocol v4 khác byte đã khóa; cần revision được ghi nhận")
    value = read(data)
    development = value["development"]
    operation = value["operation"]
    if (any(value["permissions"].values()) or value["confirmation"]["allowed"]
            or operation["hour_cap"] is not None or operation["calendar_deadline"] is not None
            or operation["elapsed_counter_enabled"] or operation["crash_gap_charging_enabled"]):
        raise ValueError("Spec không cấp release hoặc áp giới hạn giờ/ngày")
    if (development["matrix"] != list(BRANCHES)
            or development["primary_action_rows"] != 60 * len(BRANCHES)
            or development["repeat_action_rows"] != 12 * 3 * (len(BRANCHES) + 1)
            or development["total_action_rows"] != 996
            or development["total_nominal_llm_slots"] != 60 * 3 + 12 * 3 * 4
            or len(value["confirmation"]["secondary"]) != 8
            or value["confirmation"]["secondary_ci"] != 1 - .05 / 8):
        raise ValueError("Ma trận, số slot hoặc family khác protocol")
    ids = development["point_ids"]
    counts = {s: sum(p.startswith(s + "-") for p in ids) for s in value["data"]["symbols"]}
    if len(ids) != 60 or len(set(ids)) != 60 or counts != development["counts_by_symbol"]:
        raise ValueError("Cohort development không đủ 60 ID đã khóa")
    for point in ids:
        if date.fromisoformat(point[4:]).year != 2023:
            raise ValueError("Không được mở năm xác nhận trong development")
    for fold in value["folds"]:
        if not fold["fit_end"] < fold["evaluation_start"] or fold["fit_end"] > "2020-12-31":
            raise ValueError("Fold vượt miền fit đã khóa")
        if any(not inner["fit_end"] < inner["evaluation_start"] for inner in fold["inner"]):
            raise ValueError("Inner fold không giữ thứ tự thời gian")
    return value


def verify_ledger(ledger: dict[str, Any], binding: dict[str, Any]) -> None:
    """Cho append, cấm reset/sửa prefix hoặc trùng UUID kể cả ở phần append."""
    rows = ledger["requests"]
    if (type(rows) is not list or len(rows) < binding["count"]
            or len({r["id"] for r in rows}) != len(rows)
            or checksum(canonical(rows[:binding["count"]])) != binding["requests_prefix_sha256"]):
        raise ValueError("Ledger bị sửa/reset hoặc trùng UUID")


def fit_eligible(entry: str, exit_date: str, fit_end: str, evaluation_start: str,
                 evaluation_end: str) -> bool:
    """Fixture purge theo khoảng entry–exit; không dùng payoff để chọn fit rows."""
    for item in (entry, exit_date, fit_end, evaluation_start, evaluation_end):
        if type(item) is not str or date.fromisoformat(item).isoformat() != item:
            raise ValueError("Ngày purge phải là ISO")
    if entry > exit_date or evaluation_start > evaluation_end or fit_end >= evaluation_start:
        raise ValueError("Khoảng thời gian fit/evaluation không hợp lệ")
    return bool(exit_date <= fit_end and exit_date < evaluation_start
                and not (entry <= evaluation_end and exit_date >= evaluation_start))


def check_episode_metadata(value: dict[str, Any], *, runtime: bool = True) -> None:
    """Fixture hợp đồng PIT, chưa phải verifier X/nguồn/nhãn cho dataset W11-18."""
    if set(value) != {"query", "prior", "target"}:
        raise ValueError("Metadata episode có trường ngoài protocol")
    query = value["query"]
    keys = {"episode_id", "symbol", "task_id", "as_of_date", "entry_date", "exit_date",
            "feature_end_date", "scaler_fit_end", "regime_fit_end"}
    if set(query) != keys or query["symbol"] not in ("FPT", "MWG", "VCB", "VNM"):
        raise ValueError("Query metadata không được chứa y hoặc payoff")
    cutoff = query["as_of_date"]
    if not "2018-01-02" <= cutoff <= "2023-12-31":
        raise ValueError("Query ngoài miền research, chưa release xác nhận")
    for row in [query, *value["target"], *(r for task in value["prior"] for r in task["observations"])]:
        if set(row) != keys:
            raise ValueError("Fixture metadata không nhận feature/nhãn chưa xác minh")
        for key in keys - {"episode_id", "symbol", "task_id"}:
            if type(row[key]) is not str or date.fromisoformat(row[key]).isoformat() != row[key]:
                raise ValueError("Ngày provenance không phải ISO")
        if (row["symbol"] != query["symbol"] or not row["as_of_date"] < row["entry_date"] <= row["exit_date"]
                or row["feature_end_date"] > row["as_of_date"]
                or row["scaler_fit_end"] > query["scaler_fit_end"]
                or row["regime_fit_end"] > min(row["as_of_date"], "2020-12-31")):
            raise ValueError("Metadata nguồn/feature/scaler/regime vi phạm PIT")
    if query["scaler_fit_end"] >= cutoff or query["scaler_fit_end"] > "2020-12-31":
        raise ValueError("Scaler query phải fit trước query và không vượt cuối train")
    prior = value["prior"]
    if (len(prior) not in ((0, 1, 3) if runtime else (0, 1, 3, 5, 8))
            or len(value["target"]) > 32 or len({t["task_id"] for t in prior}) != len(prior)):
        raise ValueError("Độ dài K/m hoặc task lặp ngoài miền train/runtime")
    context = list(value["target"])
    for task in prior:
        if (set(task) != {"task_id", "block_end_date", "observations"}
                or not task["block_end_date"] < cutoff or task["task_id"] == query["task_id"]
                or not 2 <= len(task["observations"]) <= 32
                or any(r["task_id"] != task["task_id"] or r["exit_date"] > task["block_end_date"]
                       for r in task["observations"])):
            raise ValueError("Prior task sai boundary hoặc thiếu observations")
        if date.fromisoformat(task["block_end_date"]).isoformat() != task["block_end_date"]:
            raise ValueError("Ngày cuối task không phải ISO")
        context.extend(task["observations"])
    if any(r["task_id"] != query["task_id"] for r in value["target"]):
        raise ValueError("Target context khác task query")
    rows = [*context, query]
    if (len({r["episode_id"] for r in rows}) != len(rows)
            or any(r["exit_date"] >= cutoff for r in context)):
        raise ValueError("D/C/query trùng hoặc context chưa đóng trước query")
    intervals = sorted((r["entry_date"], r["exit_date"]) for r in rows)
    if any(a[1] >= b[0] for a, b in zip(intervals, intervals[1:])):
        raise ValueError("Khoảng entry–exit của D/C/query chồng lấp")


def verify_inputs(root: Path) -> dict[str, Any]:
    """Chỉ hash nguồn/giá, không parse outcome giá hoặc forward model."""
    spec = validate_protocol((root / PROTOCOL).read_bytes())
    for group in ("parent_sha256", "baseline_source_sha256", "input_sha256"):
        for name, expected in spec[group].items():
            if checksum(safe_path(root, name).read_bytes()) != expected:
                raise ValueError("Binding nguồn khác protocol: " + name)
    authority = spec["authority"]
    git(root, "merge-base", "--is-ancestor", authority["plan_base_commit"], "HEAD")
    for name, expected in authority["plan_git_sha256"].items():
        safe_path(root, name)
        if checksum(git(root, "show", authority["plan_base_commit"] + ":" + name)) != expected:
            raise ValueError("Plan gốc không khớp object Git")
    if platform.python_version() != spec["runtime"]["python"] or platform.system() != spec["runtime"]["platform"]:
        raise ValueError("Runtime Python/platform khác protocol")
    for package, version in spec["runtime"]["packages"].items():
        if importlib.metadata.version(package) != version:
            raise ValueError("Dependency khác protocol: " + package)
    verify_ledger(read(safe_path(root, spec["ledger_baseline"]["path"]).read_bytes()), spec["ledger_baseline"])
    return spec


def source_binding(root: Path, commit: str) -> dict[str, str]:
    """Mã verifier/test phải đã commit và giống byte object Git trước khi khóa."""
    git(root, "merge-base", "--is-ancestor", commit, "HEAD")
    result = {}
    for name in (*SOURCES, PROTOCOL.as_posix()):
        data = safe_path(root, name).read_bytes()
        if data != git(root, "show", commit + ":" + name):
            raise ValueError("Nguồn chưa commit hoặc khác Git: " + name)
        result[name] = checksum(data)
    return result


def verify(root: Path) -> dict[str, Any]:
    """Cold replay receipt SPEC_LOCK_PASS; không biến spec thành release thực nghiệm."""
    spec = verify_inputs(root)
    receipt = read((root / LOCK).read_bytes())
    payload = receipt["payload"]
    if (set(receipt) != {"version", "payload", "sha256"}
            or receipt["version"] != "conditional_mt_bicl_protocol_lock_v4"
            or receipt["sha256"] != checksum(canonical(payload))
            or payload["status"] != "SPEC_LOCK_PASS"
            or payload["protocol_sha256"] != PROTOCOL_SHA256
            or payload["source_commit"] != git(root, "log", "-1", "--format=%H", "--",
                                               *SOURCES, PROTOCOL.as_posix()).decode().strip()
            or payload["source_sha256"] != source_binding(root, payload["source_commit"])
            or payload["permissions"] != spec["permissions"]
            or payload["ledger_baseline"] != spec["ledger_baseline"]):
        raise ValueError("Receipt spec sai hash/source/scope")
    return payload


def freeze(root: Path) -> dict[str, Any]:
    """Tạo receipt một lần sau commit source; không ghi counter hoặc bằng chứng cũ."""
    if (root / LOCK).exists():
        return verify(root)
    spec = verify_inputs(root)
    commit = git(root, "rev-parse", "HEAD").decode().strip()
    payload = {"status": "SPEC_LOCK_PASS", "source_commit": commit,
               "protocol_sha256": PROTOCOL_SHA256, "source_sha256": source_binding(root, commit),
               "permissions": spec["permissions"], "ledger_baseline": spec["ledger_baseline"]}
    receipt = {"version": "conditional_mt_bicl_protocol_lock_v4", "payload": payload,
               "sha256": checksum(canonical(payload))}
    with (root / LOCK).open("xb") as stream:
        stream.write((json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return verify(root)
