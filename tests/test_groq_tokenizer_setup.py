"""Kiểm setup cache khi cài mới và từ chối dữ liệu tokenizer bị hỏng."""

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from scripts import prepare_groq_tokenizer as setup


class GroqTokenizerSetupTests(unittest.TestCase):
    """Không gọi mạng trong test; không công bố file tải một phần."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.content = b"tokenizer-fixture-data"
        self.digest = hashlib.sha256(self.content).hexdigest()
        self.target = self.directory / hashlib.sha1(setup.URL.encode()).hexdigest()

    def test_verified_existing_cache_never_calls_network(self) -> None:
        self.target.write_bytes(self.content)
        with patch.object(setup, "EXPECTED_SHA256", self.digest), patch.object(setup.requests, "get") as get:
            self.assertEqual(setup.prepare_tokenizer(self.directory), self.target)
            get.assert_not_called()

    def test_chunked_download_joins_exact_bytes_before_atomic_publish(self) -> None:
        def get(url: str, *, headers: dict, timeout: tuple) -> Mock:
            start, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
            response = Mock(status_code=206, content=self.content[start:end + 1],
                headers={"Content-Range": f"bytes {start}-{end}/{len(self.content)}"})
            return response
        with (patch.object(setup, "EXPECTED_SHA256", self.digest), patch.object(setup, "EXPECTED_SIZE", len(self.content)),
              patch.object(setup, "CHUNK_SIZE", 5), patch.object(setup.requests, "get", side_effect=get)):
            setup.prepare_tokenizer(self.directory)
        self.assertEqual(self.target.read_bytes(), self.content)
        self.assertFalse(list(self.directory.glob("pilot-tokenizer-*")))

    def test_wrong_checksum_preserves_old_cache(self) -> None:
        self.target.write_bytes(b"old-cache")
        response = Mock(status_code=206, content=self.content, headers={"Content-Range": f"bytes 0-{len(self.content)-1}/{len(self.content)}"})
        with (patch.object(setup, "EXPECTED_SIZE", len(self.content)), patch.object(setup.requests, "get", return_value=response),
              self.assertRaises(ValueError)):
            setup.prepare_tokenizer(self.directory)
        self.assertEqual(self.target.read_bytes(), b"old-cache")


if __name__ == "__main__":
    unittest.main()
