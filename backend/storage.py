import os
import time
import glob
import tempfile
from pathlib import Path

SHARD_DIR = Path(tempfile.gettempdir()) / "run-shards"
SHARD_DIR.mkdir(parents=True, exist_ok=True)

MAX_AGE_SECONDS = 24 * 3600

CATALOGUE_PATH = SHARD_DIR / "catalogue.json"

def _shard_path(shard_id: str) -> Path:
    return SHARD_DIR / f"{shard_id}.bin"

def save_shard(shard_id: str, data: bytes) -> None:
    path = _shard_path(shard_id)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp_path, path)

def load_shard(shard_id: str) -> bytes | None:
    path = _shard_path(shard_id)
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > MAX_AGE_SECONDS:
        path.unlink(missing_ok=True)
        return None
    return path.read_bytes()

def cleanup_old_shards() -> int:
    removed = 0
    now = time.time()
    for p in glob.glob(str(SHARD_DIR / "*.bin")):
        if now - os.path.getmtime(p) > MAX_AGE_SECONDS:
            os.remove(p)
            removed += 1
    return removed

def load_catalogue() -> dict:
    import json
    if not CATALOGUE_PATH.exists():
        return {}
    try:
        return json.loads(CATALOGUE_PATH.read_text())
    except Exception:
        return {}

def save_catalogue(cat: dict) -> None:
    import json, os
    tmp = CATALOGUE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cat))
    with open(tmp, "rb") as f:
        os.fsync(f.fileno())
    os.rename(tmp, CATALOGUE_PATH)
