import os
from pathlib import Path
import pytest

import distribute as dist
import upload as upload_module


def test_sha256_file(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello solmu")
    expected = "b53b1b0e0a3b4e6e2c2c8e1a9e5f9d9c6e1c3e7a0f2e4d6c8b0a2f4e6d8c0b2"
    # do not hardcode; compare against hashlib directly
    import hashlib
    assert dist.sha256_file(p) == hashlib.sha256(b"hello solmu").hexdigest()


def test_split_and_distribute_two_nodes(tmp_path, monkeypatch):
    """Two nodes, second one mocked over HTTP."""
    import upload as upload_module
    import storage as storage_mod
    import config as cfg_mod
    import distribute as dist

    monkeypatch.setattr(upload_module, "INCOMING_DIR", tmp_path)
    monkeypatch.setattr(storage_mod, "SHARD_DIR", tmp_path / "shards")
    (tmp_path / "shards").mkdir()

    fake_cfg = {
        "version": 1,
        "nodes": [
            {"id": 1, "host": "127.0.0.1", "port": 9001},
            {"id": 2, "host": "127.0.0.1", "port": 9002},
        ],
    }
    monkeypatch.setattr(cfg_mod, "load_config", lambda: fake_cfg)
    monkeypatch.setattr(dist, "load_config", lambda: fake_cfg)

    class FakeResp:
        status_code = 201

    def fake_post(url, data=None, json=None, timeout=None, **kwargs):
        return FakeResp()

    monkeypatch.setattr(dist.requests, "post", fake_post)

    upload_id = "abc"
    (tmp_path / f"{upload_id}.bin").write_bytes(b"the secret payload")

    result = dist.split_and_distribute(upload_id, "test.bin", 1)
    assert result["file_id"].endswith("-test.bin")
    assert "1" in result["shards"] and "2" in result["shards"]
    assert not (tmp_path / f"{upload_id}.bin").exists()
