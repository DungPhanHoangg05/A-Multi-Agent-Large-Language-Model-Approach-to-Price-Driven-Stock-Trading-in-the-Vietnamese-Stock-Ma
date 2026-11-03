"""Xuất registry Alpha bằng AST và catalogue gốc, không chạy selector hoặc inference."""

from __future__ import annotations

import ast
from collections import Counter
import hashlib
from pathlib import Path
import re
from typing import Any

from core.revision_audit import sha256_file
from core.revision_common_study import read_json, write_json
from core.revision_sentiment_inventory import RUN, require, verify_release

OUTPUT = Path("outputs/revision/alpha_registry_v1")
CATALOGUE = Path("revision/alpha101_catalogue.json")
RUNTIME = Path("core/alpha_compare.py")
AGENT = Path("agents/alpha_agent.py")
SELECTOR = Path("utils/alpha_selector.py")


def source_tree(root: Path, relative: Path) -> tuple[str, ast.Module]:
    """Đọc byte nguồn đã khóa; AST không thực thi imports hoặc module body."""
    source = (root / relative).read_text(encoding="utf-8-sig")
    return source, ast.parse(source)


def assignment(tree: ast.Module, name: str) -> ast.AST:
    """Tìm một khai báo top-level duy nhất, từ chối registry ghi đè âm thầm."""
    nodes = [node.value for node in tree.body if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    require(len(nodes) == 1, "Khai báo phải duy nhất: " + name)
    return nodes[0]


def pointer(path: Path, node: ast.AST) -> dict[str, Any]:
    """Trỏ chính xác dòng đầu/cuối của code mà không sửa newline runtime."""
    return {"path": path.as_posix(), "line": node.lineno, "end_line": node.end_lineno}


def function_record(path: Path, source: str, node: ast.FunctionDef) -> dict[str, Any]:
    """Tách docstring khỏi công thức thực thi để không coi prose là oracle."""
    body = node.body[1:] if ast.get_docstring(node) is not None else node.body
    return {"name": node.name, "code": pointer(path, node), "docstring": ast.get_docstring(node),
            "implementation": "\n".join(ast.unparse(statement) for statement in body),
            "source_sha256": hashlib.sha256(ast.get_source_segment(source, node).encode("utf-8")).hexdigest(),
            "ast_sha256": hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()}


def dependencies(node: ast.FunctionDef, functions: dict[str, ast.FunctionDef]) -> list[str]:
    """Lần theo helper được gọi, không chạy formula hay backtest thị trường."""
    found: set[str] = set()
    pending = [node]
    while pending:
        current = pending.pop()
        for call in ast.walk(current):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                name = call.func.id
                if name in functions and name != node.name and name not in found:
                    found.add(name)
                    pending.append(functions[name])
    return sorted(found)


def formula_requirements(formula: str) -> dict[str, Any]:
    """Nhận diện dữ liệu/operator trong công thức gốc, không suy động cơ loại lịch sử."""
    return {"industry_neutralization": "indneutralize" in formula.lower(),
            "market_cap": bool(re.search(r"\bcap\b", formula, re.I)),
            "cross_sectional_rank": bool(re.search(r"(?<![\w])rank\s*\(", formula, re.I)),
            "cross_sectional_scale": bool(re.search(r"\bscale\s*\(", formula, re.I)),
            "daily_vwap": bool(re.search(r"\bvwap\b", formula, re.I)),
            "adv_dollar_volume_windows": sorted({int(v) for v in re.findall(r"\badv(\d+)\b", formula, re.I)})}


def implementation_details(node: ast.FunctionDef) -> dict[str, Any]:
    """Ghi literal inputs và mọi lời gọi window/rank theo đúng AST handler."""
    columns = sorted({n.slice.value for n in ast.walk(node) if isinstance(n, ast.Subscript)
                      and isinstance(n.value, ast.Name) and n.value.id == "d"
                      and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str)})
    operators = []
    for call in sorted((n for n in ast.walk(node) if isinstance(n, ast.Call)), key=lambda n: (n.lineno, n.col_offset)):
        name = ast.unparse(call.func)
        if name.startswith("ts_") or name in ("delta", "delay", "decay_linear", "normalize_alpha", "signed_power") or name.endswith(".rolling"):
            operators.append({"operator": name, "expression": ast.unparse(call), "line": call.lineno})
    return {"feature_columns": columns, "operator_calls": operators}


def reviewed_findings() -> list[dict[str, Any]]:
    """Các sai lệch đã đọc trực tiếp; không tuyên bố đã kiểm tương đương toàn bộ công thức."""
    return [
        {"id": "custom_display_formula", "entries": ["CURRENT_1_FDM", "CURRENT_2_SFA"],
         "finding": "Template CURRENT_1 mô tả MACD trong khi handler dùng ROC_adj×Vol_Surge×0.5; template CURRENT_2 mô tả SENT_Z/LVR trong khi handler registry chỉ dùng MACD proxy và ROC_adj.",
         "action": "T10 kiểm fixtures và xác định ảnh hưởng trước mọi sửa đổi; không đổi template/prompt đã freeze."},
        {"id": "prototype_is_distinct", "entries": [f"CURRENT_{i}_{name}" for i, name in enumerate(("FDM", "SFA", "LVR", "BFE", "OFE"), 1)],
         "finding": "Dynamic dùng handler registry rồi normalize và flip theo IC; năm prototype fallback có preprocessing/threshold riêng. Backtest không chọn được dynamic thì dừng, không fallback. SFA prototype có nhánh sentiment còn registry SFA không đọc sentiment.",
         "action": "Không coi công thức/template/prototype là ba cách biểu diễn tương đương."},
        {"id": "rank_header_not_uniform", "worldquant_ids": [2, 3, 7, 13, 16, 20, 25, 27],
         "finding": "Comment chung rank→ts_rank(20) không bao quát mọi handler: có rank window 5/6/10/30; WQ7 docstring ghi 60 nhưng thực thi 30.",
         "action": "Dùng operator_calls từng entry làm nguồn, kiểm window/ties ở T10."},
        {"id": "fractional_windows", "worldquant_ids": [61, 62, 65, 66, 71, 72, 73, 74, 75, 77, 78, 84, 85, 86, 88, 89, 92, 94, 95, 96, 98, 99],
         "finding": "Nguồn gốc định nghĩa floor(d); nhiều integer windows code khác floor, ví dụ WQ61 correlation 17.9282→18, WQ65 sum 8.6911→9. Không gán chung là floor hoặc coi là exact replication.",
         "action": "Giữ nguyên số thực gốc và biểu thức code; T10 chọn fixtures window quan trọng."},
        {"id": "structural_translation", "worldquant_ids": [29, 54, 89],
         "finding": "WQ29 rút gọn chuỗi min/product/rank/log; WQ54 dùng lũy thừa open/close 2 thay 5; WQ89 bỏ IndNeutralize(vwap,industry). WQ89 vẫn retained dù 17 mục excluded khác có neutralization.",
         "action": "Không mô tả 21 exclusions đều do neutralization hoặc mọi retained đều là bản dịch nguyên vẹn."},
        {"id": "boolean_encoding", "worldquant_ids": [61, 62, 65, 74, 75, 86, 95, 99],
         "finding": "Các comparisons được mã hóa hai phía ±1; nguồn gốc là boolean 0/1 hoặc -1×boolean. Đây là đổi biên độ/offset và có thể đổi tín hiệu sau normalize.",
         "action": "T10 kiểm polarity/threshold, không sửa kết quả đã khóa."},
        {"id": "scale_and_history", "worldquant_ids": [28, 29, 31, 32, 60],
         "finding": "scale nguồn là cross-sectional L1; code gọi normalize_alpha zscore/tanh trên cả Series. delay dùng shift().bfill(); warm-up được điền hoặc dùng partial windows. Đây chưa phải chứng nhận causal per-row preprocessing.",
         "action": "T10 kiểm operator/warm-up/NaN và leakage liên quan; không đổi dữ liệu run đang dở."},
        {"id": "price_volume_proxies", "entries": ["all_retained"],
         "finding": "VWAP là typical price (H+L+C)/3; ADV là rolling volume/price-range proxy, khác dollar volume gốc. returns thực là pct_change, khác comment log return; volume thật chỉ khi >40% nonmissing và tổng dương, nếu không dùng High−Low.",
         "action": "Không suy đo order flow/order book hoặc dòng tổ chức; profile proxy ở T11."},
        {"id": "signed_alpha4", "entries": ["CURRENT_4_BFE"],
         "finding": "Alpha_4 giữ tanh((%B−0.5)×VolZ5×1.5), volume z-score có dấu; không có squeeze gate hay crossing test. Registry dùng sample-SD, prototype có preprocessing khác.",
         "action": "Giữ nguyên công thức; tái dùng evidence R13 và kiểm tiếp ở T10."},
    ]


def build_registry(root: Path) -> dict[str, Any]:
    """Dựng đầy đủ 101 IDs và năm custom từ khai báo thực, không ép counts cho khớp prose."""
    catalogue = read_json(root / CATALOGUE)
    require(sha256_file(root / catalogue["pdf_path"]) == catalogue["pdf_sha256"], "PDF catalogue sai hash")
    formulas = catalogue["formulas"]
    require([row["id"] for row in formulas] == list(range(1, 102)), "Catalogue thiếu/trùng/sai thứ tự IDs")
    source, tree = source_tree(root, RUNTIME)
    agent_source, agent_tree = source_tree(root, AGENT)
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    prototypes = {n.name: n for n in agent_tree.body if isinstance(n, ast.FunctionDef)}
    registry = assignment(tree, "ALPHA_REGISTRY")
    require(isinstance(registry, ast.Dict), "Registry không còn là dict tường minh")
    templates_node = assignment(tree, "NEW_ALPHA_TEMPLATES")
    templates = ast.literal_eval(templates_node)
    templates_en = ast.literal_eval(assignment(tree, "NEW_ALPHA_TEMPLATES_EN"))
    template_nodes = {ast.literal_eval(k): v for k, v in zip(templates_node.keys, templates_node.values)}
    entries, ids = {}, {}
    for position, (key_node, value) in enumerate(zip(registry.keys, registry.values)):
        key = ast.literal_eval(key_node)
        require(key not in entries and isinstance(value, ast.Tuple) and len(value.elts) == 2, "Registry trùng hoặc sai schema")
        handler, description = value.elts
        require(isinstance(handler, ast.Name) and handler.id in functions, "Handler thiếu hoặc không phải tên hàm")
        match = re.fullmatch(r"WQ(\d+)_.+", key)
        if match:
            identity = int(match[1])
            require(identity in range(1, 102) and identity not in ids and handler.id == f"wq{identity}", "WQ ID/handler không khớp")
            ids[identity] = key
        else:
            require(bool(re.fullmatch(r"CURRENT_[1-5]_[A-Z]+", key)), "Có namespace ngoài WQ/custom")
        node = functions[handler.id]
        helpers = dependencies(node, functions)
        require(key in templates and key in templates_en, "Entry thiếu display template")
        entries[key] = {"registry_key": key, "registry_position": position,
                        "registry_code": pointer(RUNTIME, key_node), "description": ast.literal_eval(description),
                        "handler": function_record(RUNTIME, source, node), **implementation_details(node), "helper_dependencies": helpers,
                        "display_template": {"vi": templates[key], "en": {**templates[key], **templates_en[key]}, "code": pointer(RUNTIME, template_nodes[key])}}
    worldquant = []
    for original in formulas:
        identity = original["id"]
        requirements = formula_requirements(original["formula"])
        retained = identity in ids
        if retained:
            reason = "Có handler và key trong ALPHA_REGISTRY; đây là adaptation đang thực thi, không xác nhận tương đương bản gốc."
        elif requirements["industry_neutralization"]:
            reason = "Không có handler/key; công thức gốc cần cross-sectional industry neutralization mà pipeline single-stock không cung cấp. Quan sát dependency, không xác nhận động cơ lịch sử."
        elif requirements["market_cap"]:
            reason = "Không có handler/key; công thức gốc cần market cap ngoài feature frame OHLCV hiện tại. Quan sát dependency, không xác nhận động cơ lịch sử."
        else:
            reason = "Không có handler/key dù công thức dùng price/volume operators; chưa có hồ sơ giải thích loại, ghi unknown thay vì suy do thiếu industry/cap."
        worldquant.append({"worldquant_id": identity, "status": "retained" if retained else "excluded",
                           "reason": reason, "historical_selection_rationale": "unknown", "original": {**original, "source_version": catalogue["version"]},
                           "original_requirements": requirements, "implementation": entries[ids[identity]] if retained else None,
                           "registry_lookup_code": pointer(RUNTIME, registry)})
    custom = []
    for key, entry in entries.items():
        if not key.startswith("CURRENT_"): continue
        number = int(key.split("_")[1]); suffix = key.split("_")[2].lower()
        prototype = prototypes[f"_alpha{number}_{suffix}"]
        custom.append({"custom_id": number, "origin": "custom_in_repository", "worldquant_id": None,
                       "reason": "Candidate custom hiện diện trong registry; không coi là alpha proprietary hoặc tuyên bố tính mới/ownership.",
                       "original_formula_scope": "Định nghĩa nội bộ là handler registry; prototype fallback ghi riêng, không gán công thức WorldQuant.",
                       "implementation": entry, "prototype_fallback": function_record(AGENT, agent_source, prototype)})
    needed = sorted({name for entry in entries.values() for name in entry["helper_dependencies"]}
                    | {"build_features", "normalize_alpha", "run_backtest", "rank_alphas"})
    excluded = [row["worldquant_id"] for row in worldquant if row["status"] == "excluded"]
    excluded_types = Counter("industry_neutralization" if row["original_requirements"]["industry_neutralization"] else
                             "market_cap" if row["original_requirements"]["market_cap"] else "unexplained_price_volume_omission"
                             for row in worldquant if row["status"] == "excluded")
    return {"schema_version": "alpha_registry_v1", "catalogue": {k: v for k, v in catalogue.items() if k != "formulas"},
            "counts": {"worldquant_catalogue": len(worldquant), "worldquant_retained": len(ids), "worldquant_excluded": len(excluded),
                       "custom": len(custom), "runtime_candidates": len(entries)}, "excluded_worldquant_ids": excluded,
            "excluded_dependency_classes": dict(excluded_types),
            "count_contract_80_21_5_matches": len(ids) == 80 and len(excluded) == 21 and len(custom) == 5,
            "worldquant": worldquant, "custom": custom,
            "function_source_hash_scope": "SHA-256 của ast.get_source_segment mã hóa UTF-8 sau chuẩn hóa newline khi đọc; hash byte toàn file được giữ riêng trong manifest.",
            "helpers_and_pipeline": [function_record(RUNTIME, source, functions[name]) for name in needed],
            "selector": {"code": pointer(SELECTOR, next(n for n in source_tree(root, SELECTOR)[1].body if isinstance(n, ast.FunctionDef) and n.name == "select_top_alphas")),
                         "agent_dynamic": function_record(AGENT, agent_source, prototypes["_compute_all_alphas"])},
            "reviewed_findings": reviewed_findings(),
            "limits": ["Không chạy formula/selector trên market data; không đo IC/turnover hoặc tạo LLM predictions ở T09.",
                       "Code/templates/docstrings được xuất tách biệt; equivalence chưa được chứng minh bằng fixtures T10.",
                       "Lý do lựa chọn lịch sử unknown; dependency của công thức không chứng minh nguyên nhân loại.",
                       "Không đổi runtime, inputs, prompt hoặc source hashes frozen của T02/T03; chưa sửa paper hoặc response."]}


def run_audit(root: Path, output: Path) -> dict[str, Any]:
    """Khóa nguồn/đầu ra mới độc quyền, đối soát queue trước/sau khi xuất registry."""
    root, output = root.resolve(), output.resolve()
    require(output.is_relative_to(root / "outputs/revision") and output != root / "outputs/revision", "Output phải là release riêng")
    require(not output.exists(), "Release đã có; dùng --check hoặc tên mới")
    queue = read_json(root / RUN / "manifest.json")
    def check_frozen() -> None:
        """Chỉ đọc hash nguồn frozen; không mở worker/ledger hoặc raw chưa hoàn chỉnh."""
        for row in queue["sources"]:
            require(sha256_file(root / row["path"]) == row["sha256"], "Nguồn frozen đổi: " + row["path"])
    check_frozen()
    registry = build_registry(root)
    check_frozen()
    summary = {"result": "PASS", "scope": "T09 registry nguồn và sai lệch; T10/T11 chưa thực hiện", "counts": registry["counts"],
               "count_contract_80_21_5_matches": registry["count_contract_80_21_5_matches"],
               "excluded_worldquant_ids": registry["excluded_worldquant_ids"], "excluded_dependency_classes": registry["excluded_dependency_classes"],
               "reviewed_findings": registry["reviewed_findings"], "limits": registry["limits"]}
    source_paths = [RUNTIME, AGENT, SELECTOR, CATALOGUE, Path(registry["catalogue"]["pdf_path"]), RUN / "manifest.json",
                    Path("core/revision_alpha_registry.py"), Path("scripts/audit_alpha_registry.py"), Path("tests/test_revision_alpha_registry.py"),
                    Path("core/revision_audit.py"), Path("core/revision_common_study.py"), Path("core/revision_sentiment_inventory.py")]
    source_rows = [{"path": path.as_posix(), "sha256": sha256_file(root / path)} for path in source_paths]
    output.mkdir(parents=True)
    write_json(output / "registry.json", registry, True)
    write_json(output / "summary.json", summary, True)
    write_json(output / "manifest.json", {"schema_version": "alpha_registry_v1", "sources": source_rows,
               "queue_run_signature": queue["sha256"], "frozen_source_hashes_checked_before_after": len(queue["sources"]),
               "network_or_inference": False, "historical_inputs_modified": False,
               "outputs": [{"path": p.name, "sha256": sha256_file(p)} for p in sorted(output.iterdir())]}, True)
    return summary


def check_release(root: Path, output: Path) -> int:
    """Kiểm source/output hashes, không tái sinh release hoặc chạy runtime Alpha."""
    return verify_release(root, output)
