"""Khóa lại bank sau sửa guard smoke; tái dùng đúng feature số, không tái dùng Full."""

from __future__ import annotations

import ast
from pathlib import Path
import sys
from zipfile import ZipFile
import hashlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.revision_audit import sha256_file
from core.revision_common_study import digest, prepare_bank, read_json, verify_features, write_json


def refreeze() -> None:
    """Chỉ chấp nhận thay guard/CLI; kiểm nguồn archive và AST các hàm sinh feature."""
    old = ROOT / "outputs/revision/r1_common_bank_v1"
    new = ROOT / "outputs/revision/r1_common_bank_v2"
    previous = read_json(old / "manifest.json")
    verify_features(old, previous)
    if digest({k: v for k, v in previous.items() if k != "bank_id"}) != previous["bank_id"]:
        raise ValueError("Manifest cũ sai hash")
    allowed = {"revision/r1_common_protocol.json", "core/revision_common_study.py",
               "core/revision_common_analysis.py", "scripts/run_revision_common_study.py"}
    with ZipFile(old / "source_snapshot.zip") as archive:
        for source in previous["sources"]:
            if hashlib.sha256(archive.read(source["path"])).hexdigest() != source["sha256"]:
                raise ValueError("Archive không bảo toàn source cũ")
            if source["path"] not in allowed and sha256_file(ROOT / source["path"]) != source["sha256"]:
                raise ValueError(f"Đổi nguồn tính feature: {source['path']}")
        code_path = "core/revision_common_study.py"
        old_ast = ast.parse(archive.read(code_path).decode("utf8"))
        new_ast = ast.parse((ROOT / code_path).read_text(encoding="utf8"))
        names = {"native", "digest", "make_schedule", "FrozenSentiment", "point_state", "pack_state",
                 "restore_state", "market_features", "_init_feature_worker", "_feature_worker"}
        def parts(tree: ast.Module) -> dict:
            return {node.name: ast.dump(node, include_attributes=False) for node in tree.body
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names}
        if parts(old_ast) != parts(new_ast) or set(parts(old_ast)) != names:
            raise ValueError("Hàm tính feature đã đổi; cần tính lại thay vì tái dùng")
    protocol = read_json(ROOT / "revision/r1_common_protocol.json")
    if {k: v for k, v in protocol.items() if k != "backtest_node_policy"} != previous["protocol"]:
        raise ValueError("Đổi protocol thị trường/selection/repeats; không tái dùng")
    manifest = prepare_bank(ROOT, new, ROOT / "revision/r1_common_protocol.json")
    if any(previous[key] != manifest[key] for key in ("schedule", "runtime", "news_hash", "price_manifest")):
        raise ValueError("Lịch/runtime/tin/giá đã đổi")
    for source in read_json(old / "features_complete.json")["files"]:
        record = read_json(old / source["path"])
        if record["bank_id"] != previous["bank_id"] or digest({k: v for k, v in record.items() if k != "sha256"}) != record["sha256"]:
            raise ValueError("Feature cũ sai identity/hash")
        record["bank_id"] = manifest["bank_id"]
        record["sha256"] = digest({k: v for k, v in record.items() if k != "sha256"})
        write_json(new / source["path"], record, exclusive=True)
    files = [{"path": p.relative_to(new).as_posix(), "sha256": sha256_file(p)}
             for p in sorted((new / "features").glob("*.json"))]
    write_json(new / "features_complete.json", {"bank_id": manifest["bank_id"], "n_points": len(files), "files": files}, exclusive=True)
    write_json(new / "feature_reuse.json", {"previous_bank_id": previous["bank_id"], "bank_id": manifest["bank_id"],
        "reason": "smoke found deterministic Indicator; guard and nominal request count corrected before any Full decision",
        "equality": "source archive hashes, feature function AST, schedule, runtime, news and prices checked; only bank_id/self-hash changed in features",
        "sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p)} for p in
            (old / "manifest.json", old / "features_complete.json", old / "source_snapshot.zip", Path(__file__).resolve())]}, exclusive=True)
    verify_features(new, manifest)
    print(f"Đã khóa lại {len(files)} feature số; không sao chép response/decision Full.")


if __name__ == "__main__":
    refreeze()
