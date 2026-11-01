import os
import uuid
import tempfile
from pathlib import Path

INCOMING_DIR = Path(tempfile.gettempdir()) / "solmu-incoming"
INCOMING_DIR.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE = 1024 * 1024  # 1 MiB

def new_upload_id() -> str:
    return uuid.uuid4().hex

def incoming_path(upload_id: str) -> Path:
    return INCOMING_DIR / f"{upload_id}.bin"

def stream_request_to_file(stream, upload_id: str) -> int:
    """Read from a file-like stream in chunks and write to disk.

    Returns the number of bytes written. Memory usage is bounded by
    CHUNK_SIZE regardless of the request size.
    """
    path = incoming_path(upload_id)
    tmp = path.with_suffix(".tmp")
    written = 0
    with open(tmp, "wb") as f:
        while True:
            chunk = stream.read(CHUNK_SIZE)
            if not chunk:
                break
            f.write(chunk)
            written += len(chunk)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp, path)
    return written

def delete_incoming(upload_id: str) -> None:
    incoming_path(upload_id).unlink(missing_ok=True)
