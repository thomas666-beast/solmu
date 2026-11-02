import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest

import auth
import config
from app import app


@pytest.fixture(autouse=True)
def disable_cluster_token(monkeypatch):
    monkeypatch.setattr(config, "cluster_token", lambda: "")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "USERS_PATH", tmp_path / "users.json")
    app.config["NODE_ID"] = 1
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def logged_in_client(client):
    client.post("/auth/register", json={"username": "tester", "password": "pw"})
    client.post("/auth/login", json={"username": "tester", "password": "pw"})
    return client
