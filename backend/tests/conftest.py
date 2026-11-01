import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from app import app


@pytest.fixture
def client():
    app.config["NODE_ID"] = 1
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
