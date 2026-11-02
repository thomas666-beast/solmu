import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "nodes.json"

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def get_node(cfg, node_id):
    for n in cfg["nodes"]:
        if n["id"] == node_id:
            return n
    raise ValueError(f"node {node_id} not in config")

def cluster_token() -> str:
    return load_config().get("token", "")

def current_version():
    return load_config()["version"]

def basic_auth_credentials():
    auth = load_config().get("auth", {})
    return auth.get("user", ""), auth.get("password", "")

def secret_key() -> str:
    return load_config().get("secret_key", "")
