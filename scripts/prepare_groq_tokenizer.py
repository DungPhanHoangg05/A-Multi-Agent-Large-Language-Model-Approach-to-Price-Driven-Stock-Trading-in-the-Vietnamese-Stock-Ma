"""Chuẩn bị o200k offline trước pilot; kiểm SHA, không gọi Groq hoặc đọc key."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import tempfile
import time

import requests

URL = "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"
EXPECTED_SHA256 = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
EXPECTED_SIZE = 3613922
CHUNK_SIZE = 800000


def cache_directory() -> Path:
    """Dùng đúng thư mục cache của tiktoken; không tải ngầm bên trong request LLM."""
    value = os.environ.get("TIKTOKEN_CACHE_DIR", os.environ.get("DATA_GYM_CACHE_DIR",
        str(Path(tempfile.gettempdir()) / "data-gym-cache")))
    if not value:
        raise ValueError("Cache tiktoken đang bị tắt; cần đặt TIKTOKEN_CACHE_DIR trước khi chuẩn bị")
    return Path(value).resolve()


def prepare_tokenizer(directory: Path | None = None) -> Path:
    """Tải từng phần có giới hạn retry; chỉ công bố cache khi toàn file khớp SHA."""
    directory = (directory if directory is not None else cache_directory()).resolve()
    target = directory / hashlib.sha1(URL.encode()).hexdigest()
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == EXPECTED_SHA256:
        return target

    def fetch(start: int) -> bytes:
        end = min(start + CHUNK_SIZE - 1, EXPECTED_SIZE - 1)
        for attempt in range(3):
            try:
                response = requests.get(URL + f"?encoding_part={start}",
                    headers={"Range": f"bytes={start}-{end}"}, timeout=(8, 25))
                response.raise_for_status()
                if (response.status_code != 206 or len(response.content) != end - start + 1
                        or response.headers.get("Content-Range") != f"bytes {start}-{end}/{EXPECTED_SIZE}"):
                    raise ValueError("Phần tokenizer bị cắt cụt hoặc sai khoảng byte")
                return response.content
            except requests.RequestException:
                if attempt == 2:
                    raise RuntimeError("Không tải được tokenizer; giữ cache cũ và thử lệnh chuẩn bị lại") from None
                time.sleep(2 ** attempt)
        raise AssertionError("Không đạt được nhánh kết thúc tải")

    with ThreadPoolExecutor(max_workers=5) as executor:
        content = b"".join(executor.map(fetch, range(0, EXPECTED_SIZE, CHUNK_SIZE)))
    if len(content) != EXPECTED_SIZE or hashlib.sha256(content).hexdigest() != EXPECTED_SHA256:
        raise ValueError("Tokenizer không khớp checksum công khai đã khóa; không dùng cache này")
    directory.mkdir(parents=True, exist_ok=True)
    pending: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix="pilot-tokenizer-", delete=False) as stream:
            pending = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        pending.replace(target)
    finally:
        if pending is not None and pending.exists():
            pending.unlink()
    return target


def main() -> None:
    """Lệnh setup riêng, không thay source/model/config hoặc checkpoint pilot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    prepare_tokenizer()
    print("Tokenizer o200k đã sẵn sàng và khớp SHA; không sử dụng quota Groq")


if __name__ == "__main__":
    main()
