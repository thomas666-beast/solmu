import hashlib
import os
import struct
import time
from pathlib import Path

import requests

from config import load_config, get_node
from storage import save_shard
from upload import incoming_path, delete_incoming
from sss import PRIME, split_secret, reconstruct_secret, lagrange_coeffs_at_zero

MAIN_NODE_ID = 1

# None = n-of-n (every node needed). Set e.g. THRESHOLD = 2 for 2-of-n.
# Note: every node still stores a full copy of the ciphertext, so this only
# controls how many KEY shares are needed; losing nodes never loses data as
# long as THRESHOLD shares survive.
THRESHOLD = None

BLOCK = 4 * 1024 * 1024  # 4 MiB streaming block
KEY_BYTES = 32           # fits easily under the 2048-bit prime
NONCE_BYTES = 16
Y_BYTES = 256            # a share y value is < PRIME, so <= 256 bytes

# Share file layout:
#   header: magic(4) | x(1) | nonce(16) | y(256) | plaintext_len(8)
#   body  : ciphertext (identical in every share)
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
    """XOR `data` with a SHAKE-256 keystream. Encrypt == decrypt.

    Keystream block `counter` = SHAKE256(key || nonce || counter). The nonce
    is random per file, so a key is never reused with the same stream.
    """
    ks = hashlib.shake_256(key + nonce + counter.to_bytes(8, "big")).digest(len(data))
    return (int.from_bytes(data, "big") ^ int.from_bytes(ks, "big")).to_bytes(len(data), "big")


def split_file_to_shares(src: Path, shares_dir: Path, n: int, k: int | None = None) -> list[Path]:
    """Encrypt the file once with a random 256-bit key, Shamir-split the KEY
    (k-of-n, via sss.py), and write one share file per node.

    Fast: Shamir runs once per file (32 bytes), not once per chunk. The bulk
    data only goes through a stream cipher and plain file I/O.
    """
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


def combine_shares_to_file(share_paths: list[Path], dst: Path, n: int | None = None) -> None:
    """Reverse of split_file_to_shares. Pass at least k share files, in any
    order. `n` is unused and kept only for call compatibility.

    With fewer than k shares the key comes out wrong; compare the result's
    sha256 against the stored file hash to detect that.
    """
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

        # Ciphertext is identical in every share, so read it from just one.
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


def split_and_distribute(upload_id: str, original_name: str, sender_node_id: int) -> dict:
    cfg = load_config()
    n = len(cfg["nodes"])
    if n < 2:
        raise ValueError("need at least 2 nodes")

    src = incoming_path(upload_id)
    if not src.exists():
        raise FileNotFoundError(f"incoming file {upload_id} not found")

    file_hash = sha256_file(src)
    file_id = f"{int(time.time() * 1000)}-{original_name}"

    shares_dir = src.parent / f"{upload_id}-shares"
    try:
        share_paths = split_file_to_shares(src, shares_dir, n, THRESHOLD)

        shard_map: dict[str, str] = {}
        results: dict[str, object] = {}

        for i, node in enumerate(cfg["nodes"]):
            share_id = f"{file_id}::{node['id']}"
            shard_map[str(node["id"])] = share_id
            share_path = share_paths[i]

            if node["id"] == sender_node_id:
                save_shard(share_id, share_path.read_bytes())
                results[str(node["id"])] = "local"
            else:
                url = f"http://{node['host']}:{node['port']}/shard/{share_id}"
                with open(share_path, "rb") as f:
                    r = requests.post(
                        url,
                        data=f,
                        headers={"Content-Type": "application/octet-stream"},
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

        main = get_node(cfg, MAIN_NODE_ID)
        broadcast_url = f"http://{main['host']}:{main['port']}/broadcast"
        requests.post(broadcast_url, json=entry, timeout=10)

        return {
            "file_id": file_id,
            "hash": file_hash,
            "shards": shard_map,
            "distribution": results,
        }
    finally:
        delete_incoming(upload_id)
        if shares_dir.exists():
            for p in shares_dir.iterdir():
                p.unlink(missing_ok=True)
            shares_dir.rmdir()
