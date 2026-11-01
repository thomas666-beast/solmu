import os
from pathlib import Path

import distribute as dist


def test_chunked_roundtrip(tmp_path):
    original = tmp_path / "orig.bin"
    data = os.urandom(3 * 1024 * 1024 + 123)
    original.write_bytes(data)

    shares_dir = tmp_path / "shares"
    paths = dist.split_file_to_shares(original, shares_dir, 3)
    assert len(paths) == 3
    for p in paths:
        assert p.stat().st_size > 0

    recovered = tmp_path / "recovered.bin"
    dist.combine_shares_to_file(paths, recovered, 3)
    assert recovered.read_bytes() == data


def test_single_chunk_edge_cases(tmp_path):
    for size in (0, 1, 1023, 1024, 1024 * 1024 + 1):
        original = tmp_path / f"orig_{size}.bin"
        original.write_bytes(os.urandom(size))
        shares_dir = tmp_path / f"shares_{size}"
        paths = dist.split_file_to_shares(original, shares_dir, 3)
        recovered = tmp_path / f"rec_{size}.bin"
        dist.combine_shares_to_file(paths, recovered, 3)
        assert recovered.read_bytes() == original.read_bytes(), f"size {size}"
