import os
import time
import pytest
from storage import save_shard, load_shard, cleanup_old_shards, _shard_path, SHARD_DIR

@pytest.fixture(autouse=True)
def clean_dir():
    for p in SHARD_DIR.glob("*.bin"):
        p.unlink()
    yield
    for p in SHARD_DIR.glob("*.bin"):
        p.unlink()

def test_save_load_roundtrip():
    save_shard("a", b"hello-world")
    assert load_shard("a") == b"hello-world"

def test_load_missing_returns_none():
    assert load_shard("nope") is None

def test_expiry_deletes_on_load():
    save_shard("b", b"data")
    p = _shard_path("b")
    old = time.time() - 25 * 3600
    os.utime(p, (old, old))
    assert load_shard("b") is None
    assert not p.exists()

def test_cleanup_removes_only_old():
    save_shard("c", b"x")
    save_shard("d", b"y")
    old = time.time() - 25 * 3600
    os.utime(_shard_path("c"), (old, old))
    removed = cleanup_old_shards()
    assert removed == 1
    assert not _shard_path("c").exists()
    assert _shard_path("d").exists()

def test_no_tmp_files_left():
    save_shard("e", b"z")
    assert not any(p.suffix == ".tmp" for p in SHARD_DIR.iterdir())

def test_overwrite_same_id():
    save_shard("f", b"v1")
    save_shard("f", b"v2")
    assert load_shard("f") == b"v2"
