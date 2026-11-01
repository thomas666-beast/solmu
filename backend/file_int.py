"""Helpers to convert file bytes to and from integers and to chunk files."""

from pathlib import Path

CHUNK_SIZE = 256  # 2048 bits per chunk

def chunk_to_int(data: bytes) -> int:
    return int.from_bytes(data, "big")


def int_to_bytes(n: int, length: int | None = None) -> bytes:
    if length is None:
        length = max(1, (n.bit_length() + 7) // 8)
    return n.to_bytes(length, "big")


def iter_file_chunks(path: Path, chunk_size: int = CHUNK_SIZE):
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk_size)
            if not block:
                break
            yield block
