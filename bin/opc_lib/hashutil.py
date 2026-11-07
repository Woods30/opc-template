"""文件指纹：统一按 LF 计算，避免 CRLF 造成无意义差异。"""

import hashlib
from pathlib import Path


def sha256_bytes(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())
