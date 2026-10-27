"""Kiểm khóa protocol và từ chối đổi đặc tả âm thầm trước triển khai MT-BICL."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.verify_mt_bicl_protocol import DIRECTORY, PROTOCOL_SHA256, ROOT, digest, validate_bundle, verify_sources


class ProtocolLockTests(unittest.TestCase):
    """Kiểm bằng byte trong RAM; không sửa nguồn, ledger hoặc dùng fixture tạm."""

    @classmethod
    def setUpClass(cls) -> None:
        """Nạp bản khóa đã đăng ký để kiểm lỗi trên các bản sao độc lập."""
        cls.data = (ROOT / DIRECTORY / "protocol_v1.json").read_bytes()
        cls.protocol = json.loads(cls.data)
        cls.artifacts = {name: (ROOT / DIRECTORY / name).read_bytes() for name in cls.protocol["artifacts"]}

    def test_bundle_is_spec_only_with_three_seeds_and_locked_schedule(self) -> None:
        """Bản khóa hợp lệ không tự cho phép train hoặc gọi Decision."""
        result = validate_bundle(self.data, self.artifacts)
        self.assertEqual(digest(self.data), PROTOCOL_SHA256)
        self.assertFalse(result["training_allowed"])
        self.assertFalse(result["decision_calls_allowed"])
        self.assertEqual(result["training"]["model_seeds"], [17, 42, 73])

    def test_protocol_cannot_self_reseal_after_changing_split(self) -> None:
        """Sửa split rồi tự băm lại trong payload không vượt khóa nguồn."""
        changed = deepcopy(self.protocol)
        changed["splits"]["train"][1] = "2022-12-31"
        data = json.dumps(changed).encode()
        changed["self_sha256"] = digest(data)
        with self.assertRaisesRegex(ValueError, "Protocol khác"):
            validate_bundle(json.dumps(changed).encode(), self.artifacts)

    def test_changed_simulator_is_rejected(self) -> None:
        """Không thay hệ số latent sau khi xem kết quả train."""
        artifacts = dict(self.artifacts)
        simulator = json.loads(artifacts["simulator_v1.json"])
        simulator["w_support"][0][0] += 1
        artifacts["simulator_v1.json"] = json.dumps(simulator).encode()
        with self.assertRaisesRegex(ValueError, "Artifact khác binding"):
            validate_bundle(self.data, artifacts)

    def test_removed_fixture_is_rejected(self) -> None:
        """Không bỏ fixture khó hoặc artifact khỏi danh mục đã khóa."""
        artifacts = dict(self.artifacts)
        del artifacts["protocol_fixtures_v1.json"]
        with self.assertRaisesRegex(ValueError, "Danh mục artifact"):
            validate_bundle(self.data, artifacts)

    def test_query_label_injected_into_fixture_is_rejected(self) -> None:
        """Không sửa ví dụ che nhãn mà vẫn viện dẫn binding cũ."""
        artifacts = dict(self.artifacts)
        fixture = json.loads(artifacts["protocol_fixtures_v1.json"])
        fixture["token_example"]["tokens"][-1]["values"][4] = 1
        artifacts["protocol_fixtures_v1.json"] = json.dumps(fixture).encode()
        with self.assertRaisesRegex(ValueError, "Artifact khác binding"):
            validate_bundle(self.data, artifacts)

    def test_changed_source_fails_instead_of_refreshing_hash(self) -> None:
        """Code nguồn lệch khóa bị chặn trước khi được viện dẫn gate cũ."""
        real_read = Path.read_bytes
        def read(path: Path) -> bytes:
            """Chỉ giả lập byte engine trên bản đọc, không ghi đĩa."""
            return b"changed engine" if path == ROOT / "core/backtest_engine.py" else real_read(path)
        with patch.object(Path, "read_bytes", read):
            with self.assertRaisesRegex(ValueError, "Nguồn đã đổi"):
                verify_sources(ROOT, self.protocol)

    def test_shared_ledger_can_append_without_resealing_protocol(self) -> None:
        """Snapshot audit không cản ledger sống nối request của run được release sau này."""
        real_read = Path.read_bytes
        ledger = ROOT / "outputs/oos_pilot/api_usage.json"
        def read(path: Path) -> bytes:
            """Nối ID mới trên bản đọc trong RAM, không gọi API hoặc ghi ledger."""
            data = real_read(path)
            if path == ledger:
                payload = json.loads(data)
                payload["requests"].append({"id": "protocol-test-append-only"})
                return json.dumps(payload).encode()
            return data
        with patch.object(Path, "read_bytes", read):
            verify_sources(ROOT, self.protocol)

    def test_changed_csv_is_rejected_even_if_manifest_unchanged(self) -> None:
        """Hash manifest đúng không thay kiểm tra byte dữ liệu đầu vào thật."""
        real_read = Path.read_bytes
        def read(path: Path) -> bytes:
            """Giả lập CSV bị sửa trong RAM mà giữ manifest gốc."""
            return b"changed csv" if path == ROOT / "data/execution_prices/FPT.csv" else real_read(path)
        with patch.object(Path, "read_bytes", read):
            with self.assertRaisesRegex(ValueError, "Giá/evidence/quyền"):
                verify_sources(ROOT, self.protocol)

    def test_shared_ledger_cannot_change_frozen_w9_request(self) -> None:
        """Append hợp lệ không cho phép sửa payload của request W9 đã đóng băng."""
        real_read = Path.read_bytes
        ledger = ROOT / "outputs/oos_pilot/api_usage.json"
        def read(path: Path) -> bytes:
            """Đổi status của request đầu trên bản đọc trong RAM."""
            data = real_read(path)
            if path == ledger:
                payload = json.loads(data)
                payload["requests"][0]["status"] = "CORRUPTED"
                return json.dumps(payload).encode()
            return data
        with patch.object(Path, "read_bytes", read):
            with self.assertRaisesRegex(ValueError, "request W9"):
                verify_sources(ROOT, self.protocol)


if __name__ == "__main__":
    unittest.main()
