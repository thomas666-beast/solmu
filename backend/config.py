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

def current_version():
    return load_config()["version"]
