import json
import threading
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

USERS_PATH = Path(__file__).resolve().parent.parent / "config" / "users.json"
LOCK = threading.Lock()
PH = PasswordHasher()


def _load() -> dict:
    if not USERS_PATH.exists():
        return {}
    try:
        return json.loads(USERS_PATH.read_text())
    except Exception:
        return {}


def _save(users: dict) -> None:
    tmp = USERS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(users, indent=2))
    tmp.replace(USERS_PATH)


def register(username: str, password: str) -> bool:
    """Return True if the user was created, False if it already exists."""
    if not username or not password:
        return False
    with LOCK:
        users = _load()
        if username in users:
            return False
        users[username] = {"password_hash": PH.hash(password)}
        _save(users)
    return True


def verify(username: str, password: str) -> bool:
    with LOCK:
        users = _load()
    record = users.get(username)
    if record is None:
        return False
    try:
        PH.verify(record["password_hash"], password)
        return True
    except VerifyMismatchError:
        return False
