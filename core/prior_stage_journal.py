"""Journal output agent trong checkpoint; không suy đoán request từ xa đã thành công."""

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

from langchain_core.messages import messages_from_dict, messages_to_dict

from core.bayesian_memory import atomic_write_json, read_json
from core.historical_signals import digest, native_json
from core.prior_config import PRIOR_STATE_FIELDS, copy_prior_json
from core.prior_run_lock import utc_now

STAGES = ("indicator", "pattern", "trend", "full")
VERSION = "agent_stage_journal_v1"
OUTPUT_FIELDS = {
    "indicator": {"indicator_report"}, "pattern": {"pattern_report"},
    "trend": {"trend_report", "trend_image", "trend_image_filename", "trend_image_description"},
    "full": {"alpha_report", "sentiment_report", "sentiment_data", "sentiment_norm"},
}


def encode_output(value: dict[str, Any]) -> dict[str, Any]:
    """Giữ message có kiểu, không serialize đối tượng runtime bằng repr/pickle."""
    result = native_json({k: v for k, v in value.items() if k != "messages"})
    if "messages" in value:
        result["messages"] = messages_to_dict(value["messages"])
    return copy_prior_json(result)


def decode_output(value: dict[str, Any]) -> dict[str, Any]:
    """Khôi phục output node đã lưu; không cấp source/evaluation từ journal."""
    result = deepcopy(value)
    if "messages" in result:
        result["messages"] = messages_from_dict(result["messages"])
    return result


class StageJournal:
    """Một file mỗi point, chỉ dùng trong khóa OS của run đã xác minh identity."""

    def __init__(self, path: Path, binding: dict[str, str], *, create: bool = False) -> None:
        self.path = path
        if not path.exists():
            if not create:
                raise ValueError("Thiếu journal đã khởi tạo; không tự replay upstream")
            self.document = {"version": VERSION, "binding": binding, "nodes": {}}
            self.save(self.document)
        envelope = read_json(path)
        if set(envelope) != {"payload", "sha256"} or digest(envelope["payload"]) != envelope["sha256"]:
            raise ValueError("Journal sai envelope/hash")
        self.document = copy_prior_json(envelope["payload"])
        try:
            self._validate(binding)
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError("Cấu trúc journal không hợp lệ") from error

    def _validate(self, binding: dict[str, str]) -> None:
        """Kiểm schema/quan hệ toàn journal trước khi cho phép phục hồi."""
        doc = self.document
        if set(doc) != {"version", "binding", "nodes"} or doc["version"] != VERSION or doc["binding"] != binding:
            raise ValueError("Journal khác version/identity/point/source")
        nodes = doc["nodes"]
        if type(nodes) is not dict or list(nodes) != list(STAGES[:len(nodes)]):
            raise ValueError("Thứ tự node journal sai")
        ids = set()
        for name, node in nodes.items():
            if set(node) != {"input_sha256", "attempts"} or not self.is_hash(node["input_sha256"]):
                raise ValueError("Input hash node không hợp lệ")
            if type(node["attempts"]) is not list or not node["attempts"]:
                raise ValueError("Node thiếu attempt")
            for index, attempt in enumerate(node["attempts"]):
                if set(attempt) != {"attempt_id", "started_at", "status", "output", "authorization"}:
                    raise ValueError("Schema attempt không hợp lệ")
                UUID(attempt["attempt_id"])
                if attempt["attempt_id"] in ids:
                    raise ValueError("Attempt trùng")
                ids.add(attempt["attempt_id"])
                from datetime import datetime
                datetime.fromisoformat(attempt["started_at"])
                if attempt["status"] not in ("unknown", "complete"):
                    raise ValueError("Trạng thái attempt sai")
                authorization = attempt["authorization"]
                if authorization is not None:
                    if (type(authorization) is not dict or set(authorization) != {"at", "reason", "attempt_id"}
                            or authorization["attempt_id"] != attempt["attempt_id"]
                            or type(authorization["reason"]) is not str or not authorization["reason"].strip()):
                        raise ValueError("Audit replay không hợp lệ")
                    datetime.fromisoformat(authorization["at"])
                if attempt["status"] == "complete":
                    self.check_output(name, attempt["output"])
                    if index != len(node["attempts"]) - 1 or authorization is not None:
                        raise ValueError("Output complete không được replay")
                elif attempt["output"] is not None or (index < len(node["attempts"]) - 1 and authorization is None):
                    raise ValueError("Attempt unknown không có audit replay")
            if name != list(nodes)[-1] and node["attempts"][-1]["status"] != "complete":
                raise ValueError("Node sau đã chạy trước khi node trước durable")

    @staticmethod
    def is_hash(value: Any) -> bool:
        """Chỉ chấp nhận SHA-256 dạng hex chuẩn."""
        return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)

    @staticmethod
    def check_output(name: str, value: Any) -> None:
        """Chặn nguồn/P&L hoặc đối tượng runtime lọt vào output hồi phục."""
        if type(value) is not dict or set(value) - OUTPUT_FIELDS[name] - set(PRIOR_STATE_FIELDS) - {"messages"}:
            raise ValueError("Output node có field ngoài hợp đồng")
        required = ("alpha_report", "sentiment_report", "sentiment_data") if name == "full" else (f"{name}_report",)
        if any(field not in value for field in required):
            raise ValueError("Output node thiếu báo cáo")
        for field in required:
            if field.endswith("_report") and (type(value[field]) is not str or not value[field].strip()):
                raise ValueError("Báo cáo durable rỗng")
        decode_output(value)

    def save(self, candidate: dict[str, Any]) -> None:
        """RAM chỉ tiến khi journal được ghi nguyên tử thành công."""
        atomic_write_json(self.path, {"payload": candidate, "sha256": digest(candidate)})
        self.document = deepcopy(candidate)

    def assert_resumable(self) -> None:
        """Unknown chưa được người vận hành xác nhận phải dừng trước agent."""
        for name, node in self.document["nodes"].items():
            last = node["attempts"][-1]
            if last["status"] == "unknown" and last["authorization"] is None:
                raise ValueError(f"AMBIGUOUS_{name.upper()}: {last['attempt_id']}; cần --reconcile")

    def invoke(self, name: str, function: Callable, state: dict[str, Any]) -> dict[str, Any]:
        """Lưu intent trước node; dùng lại output durable hoặc gọi phần chưa bắt đầu."""
        inputs = encode_output({k: v for k, v in state.items() if k not in ("point_in_time_df", "sentiment_store")})
        checksum = digest(inputs)
        nodes = self.document["nodes"]
        if name in nodes:
            node = nodes[name]
            if node["input_sha256"] != checksum:
                raise ValueError("Input node khác journal; không được replay")
            last = node["attempts"][-1]
            if last["status"] == "complete":
                return decode_output(last["output"])
            self.assert_resumable()
        elif name != STAGES[len(nodes)]:
            raise ValueError("Node journal không đúng thứ tự")
        candidate = deepcopy(self.document)
        node = candidate["nodes"].setdefault(name, {"input_sha256": checksum, "attempts": []})
        node["attempts"].append({"attempt_id": str(uuid4()), "started_at": utc_now(),
                                 "status": "unknown", "output": None, "authorization": None})
        self.save(candidate)
        from core.research_invocation import invocation_scope
        with invocation_scope(name) as budget:
            if budget is not None:
                budget.checkpoint_attempt_id = node["attempts"][-1]["attempt_id"]
                budget.point_id = self.document["binding"]["point_id"]
                budget.run_signature = self.document["binding"]["run_signature"]
            output = function(state)
        encoded = encode_output(output)
        self.check_output(name, encoded)
        candidate = deepcopy(self.document)
        candidate["nodes"][name]["attempts"][-1].update(status="complete", output=encoded)
        self.save(candidate)
        return output

    def reconcile(self, *, attempt_id: str | None = None, reason: str | None = None) -> list[dict[str, Any]]:
        """Chỉ trả metadata; xác nhận replay cụ thể được lưu audit, không xóa unknown."""
        rows = [{"node": name, "attempt_id": a["attempt_id"], "status": a["status"],
                 "replay_authorized": a["authorization"] is not None}
                for name, node in self.document["nodes"].items() for a in node["attempts"]]
        if attempt_id is not None:
            if type(reason) is not str or not reason.strip() or len(reason) > 1000:
                raise ValueError("Xác nhận replay cần lý do không rỗng, tối đa 1000 ký tự; không ghi key")
            candidate = deepcopy(self.document)
            matches = [node["attempts"][-1] for node in candidate["nodes"].values()
                       if node["attempts"][-1]["attempt_id"] == attempt_id]
            if len(matches) != 1 or matches[0]["status"] != "unknown" or matches[0]["authorization"] is not None:
                raise ValueError("Chỉ xác nhận attempt unknown cuối cùng, chưa được xác nhận")
            matches[0]["authorization"] = {"at": utc_now(), "reason": reason.strip(), "attempt_id": attempt_id}
            self.save(candidate)
            return self.reconcile()
        return rows
