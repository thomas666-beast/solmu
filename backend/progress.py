import queue
import threading

STORE: dict[str, queue.Queue] = {}
LOCK = threading.Lock()


def emit(upload_id: str, event: str, data: dict | None = None):
    with LOCK:
        q = STORE.get(upload_id)
    if q is None:
        return
    q.put({"event": event, "data": data or {}})


def register(upload_id: str) -> queue.Queue:
    q = queue.Queue()
    with LOCK:
        STORE[upload_id] = q
    return q


def unregister(upload_id: str):
    with LOCK:
        STORE.pop(upload_id, None)
