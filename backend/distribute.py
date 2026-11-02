import hashlib
import os
import struct
import time
from pathlib import Path

import requests

import config
import progress as progress_store
from config import get_node, load_config
from storage import save_shard
from upload import delete_incoming, incoming_path
from sss import PRIME, lagrange_coeffs_at_zero, reconstruct_secret, split_secret

MAIN_NODE_ID = 1
THRESHOLD = None

BLOCK = 4 * 1024 * 1024
KEY_BYTES = 32
NONCE_BYTES = 16
Y_BYTES = 256

MAGIC = b"SSS2"
HEADER = struct.Struct(f">4sB{NONCE_BYTES}s{Y_BYTES}sQ")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _crypt_block(data: bytes, key: bytes, nonce: bytes, counter: int) -> bytes:
    ks = hashlib.shake_256(key + nonce + counter.to_bytes(8, "big")).digest(len(data))
    return (
        int.from_bytes(data, "big") ^ int.from_bytes(ks, "big")
    ).to_bytes(len(data), "big")


def split_file_to_shares(
    src: Path, shares_dir: Path, n: int, k: int | None = None
) -> list[Path]:
    k = n if k is None else k
    if not 1 <= k <= n:
        raise ValueError("require 1 <= k <= n")

    key = os.urandom(KEY_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    points = split_secret(int.from_bytes(key, "big"), k, n)
    size = src.stat().st_size

    shares_dir.mkdir(parents=True, exist_ok=True)
    share_paths = [shares_dir / f"share{i}.dat" for i in range(n)]
    handles = [open(p, "wb") for p in share_paths]
    try:
        for h, (x, y) in zip(handles, points):
            h.write(HEADER.pack(MAGIC, x, nonce, y.to_bytes(Y_BYTES, "big"), size))
        with open(src, "rb") as f:
            counter = 0
            while True:
                block = f.read(BLOCK)
                if not block:
                    break
                ct = _crypt_block(block, key, nonce, counter)
                counter += 1
                for h in handles:
                    h.write(ct)
        for h in handles:
            h.flush()
            os.fsync(h.fileno())
    finally:
        for h in handles:
            h.close()
    return share_paths


def _read_header(f):
    raw = f.read(HEADER.size)
    if len(raw) != HEADER.size:
        raise ValueError("truncated share header")
    magic, x, nonce, y_raw, size = HEADER.unpack(raw)
    if magic != MAGIC:
        raise ValueError("not a share file (bad magic)")
    return x, nonce, int.from_bytes(y_raw, "big"), size


def combine_shares_to_file(
    share_paths: list[Path], dst: Path, n: int | None = None
) -> None:
    handles = [open(p, "rb") for p in share_paths]
    try:
        headers = [_read_header(h) for h in handles]
        nonces = {hd[1] for hd in headers}
        sizes = {hd[3] for hd in headers}
        if len(nonces) != 1 or len(sizes) != 1:
            raise ValueError("shares belong to different files")
        nonce = nonces.pop()
        size = sizes.pop()

        points = [(hd[0], hd[2]) for hd in headers]
        xs = [x for x, _ in points]
        coeffs = lagrange_coeffs_at_zero(xs)
        key_int = reconstruct_secret(points, PRIME, coeffs=coeffs)
        try:
            key = key_int.to_bytes(KEY_BYTES, "big")
        except OverflowError:
            raise ValueError("not enough shares to recover the key") from None

        src = handles[0]
        remaining = size
        counter = 0
        with open(dst, "wb") as out:
            while remaining > 0:
                block = src.read(min(BLOCK, remaining))
                if not block:
                    raise ValueError("share file truncated")
                out.write(_crypt_block(block, key, nonce, counter))
                remaining -= len(block)
                counter += 1
    finally:
        for h in handles:
            h.close()


def split_and_distribute(
    upload_id: str, original_name: str, sender_node_id: int
) -> dict:
    cfg = load_config()
    n = len(cfg["nodes"])
    if n < 2:
        raise ValueError("need at least 2 nodes")

    src = incoming_path(upload_id)
    if not src.exists():
        raise FileNotFoundError(f"incoming file {upload_id} not found")

    progress_store.emit(upload_id, "received", {"size": src.stat().st_size})

    file_hash = sha256_file(src)
    file_id = f"{int(time.time() * 1000)}-{original_name}"

    shares_dir = src.parent / f"{upload_id}-shares"
    try:
        progress_store.emit(upload_id, "encrypting")
        progress_store.emit(upload_id, "splitting")
        share_paths = split_file_to_shares(src, shares_dir, n, THRESHOLD)

        shard_map: dict[str, str] = {}
        results: dict[str, object] = {}

        for i, node in enumerate(cfg["nodes"]):
            share_id = f"{file_id}::{node['id']}"
            shard_map[str(node["id"])] = share_id
            share_path = share_paths[i]
            progress_store.emit(upload_id, "sending", {"node_id": node["id"]})

            if node["id"] == sender_node_id:
                save_shard(share_id, share_path.read_bytes())
                results[str(node["id"])] = "local"
            else:
                url = f"http://{node['host']}:{node['port']}/shard/{share_id}"
                with open(share_path, "rb") as f:
                    r = requests.post(
                        url,
                        data=f,
                        headers={
                            "Content-Type": "application/octet-stream",
                            "X-Solmu-Token": config.cluster_token(),
                        },
                        timeout=60,
                    )
                results[str(node["id"])] = r.status_code

        entry = {
            "file_id": file_id,
            "sender": sender_node_id,
            "shards": shard_map,
            "ts": int(time.time() * 1000),
            "hash": file_hash,
            "name": original_name,
        }

        progress_store.emit(upload_id, "broadcasting")
        main = get_node(cfg, MAIN_NODE_ID)
        broadcast_url = f"http://{main['host']}:{main['port']}/broadcast"
        requests.post(
            broadcast_url,
            json=entry,
            headers={"X-Solmu-Token": config.cluster_token()},
            timeout=10,
        )

        progress_store.emit(
            upload_id, "ready", {"file_id": file_id, "hash": file_hash}
        )

        return {
            "file_id": file_id,
            "hash": file_hash,
            "shards": shard_map,
            "distribution": results,
        }
    except Exception as e:
        progress_store.emit(upload_id, "error", {"message": str(e)})
        raise
    finally:
        delete_incoming(upload_id)
        if shares_dir.exists():
            for p in shares_dir.iterdir():
                p.unlink(missing_ok=True)
            shares_dir.rmdir()
