"""Adapter PIT cho student đã nghiệm thu; không fit, đổi membership hoặc gọi LLM."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import torch

from core.bayesian_memory import read_json
from core.historical_signals import digest as legacy_digest
from core.mt_bicl_bank import content_hash
from core.mt_bicl_context import project_episode, without_target
from core.mt_bicl_evaluation import market_input, probabilities
from core.mt_bicl_tasks import validate_episode
from core.mt_bicl_v2_distillation import tensor_hash
from core.mt_bicl_v2_experiment import CONTEXT, CONTEXT_SHA256, OUTPUT as TRAINING, predict
from core.mt_bicl_v2_final_evaluation import PROOF_VERSION, REPORT_VERSION
from core.mt_bicl_v2_io import read_envelope
from core.mt_bicl_v2_student import DistilledStudent, pack_input
from core.mt_bicl_v21_preparation import NAMESPACE, file_hash, load_inputs as load_teacher_inputs
from core.mt_bicl_v2_training_run import environment
from core.prior_run_lock import safe_path

OUTPUT = NAMESPACE/"integration_v2"
VARIANTS = ("Original","A_reference","Plain_ICL","Full_MT_BICL","No_target","Stats_only")
CODE = ("core/mt_bicl_v2_adapter.py","core/mt_bicl_v2_decision.py",
        "core/mt_bicl_v2_integration.py","scripts/integrate_mt_bicl_v2.py")
FROZEN = {
    "candidate.pt":"f8631d9e1bd15ac40422e58827c126e8c7eb9b0512a21c4a0697784cb86cd2dd",
    "preflight.json":"333a3abfeb74c15d853aa665c7baeb93fac24fb2ba38c05a91f5e4660ac39e91",
    "replay_verification.json":"e9e0f0349a748abcf8148c2a7e9430b143079d5983094c902807e278af4a2962",
    "report.json":"0221a4bb10247c32eb7b236a65d71a3af4d14747cdfa4fadb0f7f4d5774886e7",
    "selection.json":"af0fd252ec3020849363904d569568d83a3536f1dafd3356924bc1c5fd5d268e",
    "state.json":"67092349396c107caeed50850b5359ba3e72be1f81c38616c7431cbd214bf591"}
TRAINING_MANIFEST = "d4a462ddd0108390f86ca87a85fd2c8482b6e96928e2f7a85e4ac729a353524c"
PILOT_PLAN = "outputs/oos_pilot/inputs/plan.json"
A_INDEX = {"path":"outputs/bayesian_benchmark/price_features/candidate_index_v1.json",
           "sha256":"4f9242edcca9627437a6e37c81931d45621d48006ebd3f87a8d35952c20fb785"}


def load_inputs(root:Path) -> dict[str,Any]:
    """Đối soát131 file W10-12 và nguồn/runtime; không chạy lại train/evaluation."""
    base = load_teacher_inputs(root)
    directory = root/TRAINING
    manifest = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            name = path.relative_to(directory).as_posix()
            if path.is_symlink() or safe_path(directory,name) != path.resolve():raise ValueError("Artifact training resolve không hợp lệ")
            manifest[name] = {"bytes":path.stat().st_size,"sha256":file_hash(path)}
    digest = hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if len(manifest) != 131 or digest != TRAINING_MANIFEST:raise ValueError("Training khác nghiệm thu W10-12")
    if any(manifest[name]["sha256"] != sha for name,sha in FROZEN.items()):raise ValueError("Receipt training khác khóa")
    report = read_envelope(directory/"report.json",REPORT_VERSION)
    seal = read_envelope(directory/"selection.json","mt_bicl_selection_v2")
    proof = read_envelope(directory/"replay_verification.json",PROOF_VERSION)
    identity = report["identity"]
    for name,sha in identity["code_sha256"].items():
        if file_hash(root/name) != sha:raise ValueError("Mã train/evaluate đã khóa bị sửa: "+name)
    if (proof["identity_sha256"] != content_hash(identity) or proof["report"]["sha256"] != FROZEN["report.json"]
            or proof["selection"]["sha256"] != FROZEN["selection.json"] or proof["checkpoints"] != 60
            or proof["status"] != "FROZEN_INFERENCE_REPLAY_MATCH" or proof["optimizer_retrained"] is not False
            or seal["identity"] != identity or report["candidate_mechanism_status"] != "PASS"
            or report["release_status"] != "MECHANISM_PASS_AWAITING_INTEGRATION"
            or report["candidate_locked_before_test"] != seal["global_candidate_or_none"]
            or report["development_allowed"] is not False or report["decision_calls_allowed"] is not False):
        raise ValueError("Chưa đủ gate kỹ thuật/cơ chế/proof để tích hợp")
    if file_hash(root/CONTEXT) != CONTEXT_SHA256:raise ValueError("Context PIT không đúng bản khóa")
    envelope = read_json(root/CONTEXT)
    if content_hash(envelope["payload"]) != envelope["sha256"]:raise ValueError("Context sai envelope")
    context = envelope["payload"]
    rows = deepcopy(context["development"])
    protocol = base["protocol"]
    expected = {f"{symbol}-{cutoff}" for symbol,dates in protocol["development"]["symbol_cutoffs"].items() for cutoff in dates}
    if len(rows) != 60 or {r["query"]["episode_id"] for r in rows} != expected:raise ValueError("Không đúng60 point đã đăng ký")
    rows.sort(key=lambda r:(r["query"]["as_of_date"],protocol["decision"]["symbol_order"].index(r["query"]["symbol"])))
    for row in rows:resolve_episode(row,context)
    plan_envelope = read_json(root/PILOT_PLAN)
    if content_hash(plan_envelope["payload"]) != plan_envelope["sha256"]:raise ValueError("Plan nguồn A_reference sai envelope")
    plan = plan_envelope["payload"]
    if file_hash(root/A_INDEX["path"]) != A_INDEX["sha256"]:raise ValueError("A_reference index khác nguồn W9")
    new_identity = {"version":"mt_bicl_integration_identity_v2","training_identity_sha256":content_hash(identity),
                    "training_manifest_sha256":TRAINING_MANIFEST,"training_receipts_sha256":FROZEN,
                    "protocol_sha256":base["identity"]["protocol_sha256"],"context_sha256":CONTEXT_SHA256,
                    "legacy_plan_sha256":file_hash(root/PILOT_PLAN),"runtime":identity["runtime"],"gpu":proof["gpu"],
                    "legacy_price_index":deepcopy(A_INDEX),
                    "code_sha256":{name:file_hash(root/name) for name in CODE},
                    "point_ids":[r["query"]["episode_id"] for r in rows],"scope":"OFFLINE_CONTRACT_NO_LLM",
                    "development_allowed":False,"decision_calls_allowed":False}
    return {"identity":new_identity,"budget_identity":base["budget_identity"],"protocol":protocol,
            "context":context,"rows":rows,"pilot_gpu":proof["gpu"],"legacy_plan":plan,"selection":seal}


def resolve_episode(row:dict[str,Any], context:dict[str,Any]) -> dict[str,Any]:
    """Khôi phục scaler đã kiểm, loại payload phụ; nhãn query tuyệt đối không được nhận."""
    if any(k in row for k in ("supervised_target","outcome","evaluation","query_y")):
        raise ValueError("Adapter không nhận outcome query")
    result = deepcopy(row)
    for name in ("packed","projection_fixture","split"):result.pop(name,None)
    if "scaler_sha256" in result:
        checksum = result.pop("scaler_sha256")
        scaler = context["scalers"][checksum]
        if content_hash(scaler) != checksum:raise ValueError("Scaler sai self-hash")
        result["scaler"] = deepcopy(scaler)
    validate_episode(result)
    return result


class StudentAdapter:
    """Inference frozen với task slot37; sidecar full precision không đi vào prompt."""

    def __init__(self, root:Path, inputs:dict[str,Any]) -> None:
        self.inputs = inputs
        self.device = environment(inputs)
        payload = torch.load(root/TRAINING/"candidate.pt",map_location="cpu",weights_only=True)
        if (payload["version"] != "mt_bicl_candidate_weights_v2" or payload["seed"] != 42 or payload["step"] != 3000
                or payload["identity_sha256"] != inputs["identity"]["training_identity_sha256"]
                or payload["selection_sha256"] != FROZEN["selection.json"]):raise ValueError("Export không đúng candidate đã khóa")
        self.model = DistilledStudent().to(self.device)
        self.model.load_state_dict(payload["model"],strict=True)
        self.model.eval().requires_grad_(False)
        self.fingerprint = tensor_hash(self.model)
        if self.fingerprint != payload["model_tensor_sha256"]:raise ValueError("Tensor export khác receipt")

    def probability(self, episode:dict[str,Any]) -> float:
        """Không query y, optimizer, refit/retrieval hoặc ép action LLM."""
        data = market_input({**episode,"scaler_sha256":content_hash(episode["scaler"])},
                            {"scalers":{content_hash(episode["scaler"]):episode["scaler"]}})
        # market_input chỉ nhận một nguồn scaler, không mang bản đầy đủ trong row.
        return self.predict_input(data)

    def predict_input(self, data:dict[str,Any]) -> float:
        """Biên thuần cho semantic fixture; validate_packet vẫn loại mọi nhãn/latent query."""
        logits = predict(self.model,[pack_input(data)],128,self.device)
        p = float(probabilities(logits)[0][0])
        if not math.isfinite(p) or not 0 <= p <= 1 or tensor_hash(self.model) != self.fingerprint:
            raise ValueError("Student p/weights không hợp lệ")
        return p

    def prepare(self, row:dict[str,Any], *, a_reference:dict[str,Any]) -> dict[str,Any]:
        """Sáu nhánh dùng chung D/C/x; No_target bỏ C rồi recompute p độc lập."""
        known = {r["query"]["episode_id"]:r for r in self.inputs["rows"]}
        if row["query"]["episode_id"] not in known or content_hash(row) != content_hash(known[row["query"]["episode_id"]]):
            raise ValueError("Row khác point/membership/feature đã khóa, không tự reseal")
        episode = resolve_episode(row,self.inputs["context"])
        if (a_reference.get("candidate_id") != "A_tp_pool" or a_reference.get("decision_contract_version") != "decision_legacy_v1"
                or a_reference.get("request_sha256") != legacy_digest({k:v for k,v in a_reference.items() if k != "request_sha256"})
                or a_reference.get("query",{}).get("symbol") != episode["query"]["symbol"]
                or a_reference.get("query",{}).get("as_of_date") != episode["query"]["as_of_date"]
                or type(a_reference.get("prefix")) is not str or len(a_reference["prefix"]) > 600):
            raise ValueError("A_reference cần request từ producer A_tp_pool nguồn W9")
        available = episode["status"] == "AVAILABLE"
        p = self.probability(episode) if available else None
        no_target = without_target(episode) if available else episode
        p_no_target = self.probability(no_target) if available else None
        result = {}
        for variant in VARIANTS:
            projection = None
            if variant == "A_reference":prefix = a_reference["prefix"]
            elif variant == "Original" or not available:prefix = ""
            else:
                selected = no_target if variant == "No_target" else episode
                q = p_no_target if variant == "No_target" else p
                projection = project_episode(selected,probability=None if variant == "Plain_ICL" else q,
                    mode="examples" if variant == "Plain_ICL" else "stats" if variant == "Stats_only" else "full")
                prefix = projection["prefix"]
            result[variant] = {"variant":variant,"point_id":episode["query"]["episode_id"],"prefix":prefix,
                "probability":None if variant in ("Original","A_reference","Plain_ICL") else p_no_target if variant == "No_target" else p,
                "reason":"AVAILABLE" if available else "QUERY_FEATURE_UNAVAILABLE_CONTEXT_OFF",
                "episode_sha256":content_hash(episode),"projection":projection,
                "a_reference":deepcopy(a_reference) if variant == "A_reference" else None}
        result["Numeric_only"] = {"action":"LONG" if p is not None and p > .5 else "CASH",
                                  "probability":p,"reason":"P_GT_HALF" if p is not None and p > .5 else
                                  "P_NOT_GT_HALF" if p is not None else "QUERY_FEATURE_UNAVAILABLE"}
        return result
