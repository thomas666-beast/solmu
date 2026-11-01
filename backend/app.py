import argparse
import threading
import time
import requests
from flask import Flask, jsonify, request, Response
from config import load_config, get_node, current_version
from storage import save_shard, load_shard
from pathlib import Path
from flask_cors import CORS
from storage import save_shard, load_shard, load_catalogue, save_catalogue
from upload import new_upload_id, stream_request_to_file, delete_incoming, incoming_path
import distribute
import tempfile

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = Flask(__name__)

CORS(app)

CATALOGUE = load_catalogue()
REMOTE_CONFIG = {"version": None, "nodes": []}
MAIN_NODE_ID = 1


@app.route("/reconstruct/<file_id>", methods=["GET"])
def reconstruct(file_id):
    entry = CATALOGUE.get(file_id)
    if entry is None:
        return jsonify({"error": "unknown file_id"}), 404

    shards = entry["shards"]
    cfg = load_config()

    tmpdir = Path(tempfile.mkdtemp(prefix="solmu-recon-"))
    local_paths: list[Path] = []

    try:
        for node_id_str, shard_id in shards.items():
            node_id = int(node_id_str)
            local = load_shard(shard_id)
            if local is not None:
                p = tmpdir / f"local-{node_id}.dat"
                p.write_bytes(local)
                local_paths.append(p)
            else:
                node = get_node(cfg, node_id)
                url = f"http://{node['host']}:{node['port']}/shard/{shard_id}"
                try:
                    r = requests.get(url, timeout=30)
                    if not r.ok:
                        return jsonify({"error": f"shard missing on node {node_id}"}), 502
                    p = tmpdir / f"remote-{node_id}.dat"
                    p.write_bytes(r.content)
                    local_paths.append(p)
                except requests.RequestException as e:
                    return jsonify({"error": f"node {node_id} unreachable: {e}"}), 502

        out = tmpdir / "reconstructed.bin"
        distribute.combine_shares_to_file(local_paths, out, None)

        import hashlib
        h = hashlib.sha256()
        with open(out, "rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        if entry.get("hash") and h.hexdigest() != entry["hash"]:
            return jsonify({"error": "hash mismatch"}), 500

    except Exception:
        # cleanup on any pre-streaming error
        for p in tmpdir.iterdir():
            p.unlink(missing_ok=True)
        tmpdir.rmdir()
        raise

    def generate():
        try:
            with open(out, "rb") as f:
                while True:
                    block = f.read(1024 * 1024)
                    if not block:
                        break
                    yield block
        finally:
            for p in tmpdir.iterdir():
                p.unlink(missing_ok=True)
            tmpdir.rmdir()

    filename = entry.get("name", "download.bin")
    return Response(
        generate(),
        mimetype="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@app.route("/upload", methods=["POST"])
def upload():
    original_name = request.headers.get("X-Filename", "upload.bin")
    upload_id = new_upload_id()
    size = stream_request_to_file(request.stream, upload_id)
    if size == 0:
        delete_incoming(upload_id)
        return jsonify({"error": "empty body"}), 400
    try:
        result = distribute.split_and_distribute(upload_id, original_name, app.config["NODE_ID"])
    except Exception as e:
        delete_incoming(upload_id)
        return jsonify({"error": str(e)}), 500
    return jsonify({"size": size, **result}), 201

@app.route("/")
def index():
    return Response((FRONTEND_DIR / "index.html").read_text(), mimetype="text/html")

@app.route("/static/bundle.js")
def bundle():
    return Response((FRONTEND_DIR / "dist" / "bundle.js").read_text(), mimetype="application/javascript")

@app.route("/health")
def health():
    return jsonify({"node_id": app.config["NODE_ID"], "status": "ok"})

@app.route("/config")
def config():
    return jsonify(load_config())

@app.route("/shard/<shard_id>", methods=["POST"])
def post_shard(shard_id):
    data = request.get_data()
    if not data:
        return jsonify({"error": "empty body"}), 400
    save_shard(shard_id, data)
    return jsonify({"shard_id": shard_id, "size": len(data)}), 201

@app.route("/shard/<shard_id>", methods=["GET"])
def get_shard(shard_id):
    data = load_shard(shard_id)
    if data is None:
        return jsonify({"error": "not found or expired"}), 404
    return Response(data, mimetype="application/octet-stream")

@app.route("/notify", methods=["POST"])
def notify():
    entry = request.get_json(force=True)
    CATALOGUE[entry["file_id"]] = entry
    save_catalogue(CATALOGUE)
    return jsonify({"ok": True, "file_id": entry["file_id"]})

@app.route("/catalogue")
def catalogue():
    return jsonify(CATALOGUE)

@app.route("/static/style.css")
def style():
    return Response((FRONTEND_DIR / "style.css").read_text(), mimetype="text/css")

@app.route("/static/logo.svg")
def logo():
    return Response((FRONTEND_DIR / "logo.svg").read_text(), mimetype="image/svg+xml")

@app.route("/broadcast", methods=["POST"])
def broadcast():
    entry = request.get_json(force=True)
    cfg = load_config()
    results = {}
    for node in cfg["nodes"]:
        url = f"http://{node['host']}:{node['port']}/notify"
        try:
            r = requests.post(url, json=entry, timeout=2)
            results[node["id"]] = r.status_code
        except requests.RequestException:
            results[node["id"]] = "unreachable"
    return jsonify({"results": results})

@app.route("/config-sync", methods=["POST"])
def config_sync():
    cfg = request.get_json(force=True)
    REMOTE_CONFIG["version"] = cfg["version"]
    REMOTE_CONFIG["nodes"] = cfg["nodes"]
    return jsonify({"ok": True, "version": cfg["version"]})

@app.route("/remote-config")
def remote_config():
    return jsonify(REMOTE_CONFIG)

def pull_config_from_main():
    if app.config.get("NODE_ID") == MAIN_NODE_ID:
        return
    cfg = load_config()
    main = get_node(cfg, MAIN_NODE_ID)
    url = f"http://{main['host']}:{main['port']}/config"
    try:
        r = requests.get(url, timeout=2)
        if r.ok:
            remote = r.json()
            REMOTE_CONFIG["version"] = remote["version"]
            REMOTE_CONFIG["nodes"] = remote["nodes"]
    except requests.RequestException:
        pass

def watch_config():
    last = current_version()
    while True:
        time.sleep(5)
        v = current_version()
        if v == last:
            continue
        last = v
        cfg = load_config()
        for node in cfg["nodes"]:
            if node["id"] == MAIN_NODE_ID:
                continue
            url = f"http://{node['host']}:{node['port']}/config-sync"
            try:
                requests.post(url, json=cfg, timeout=2)
            except requests.RequestException:
                pass

if __name__ == "__main__":
    from storage import cleanup_old_shards
    cleanup_old_shards()
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-id", type=int, required=True)
    args = parser.parse_args()
    cfg = load_config()
    me = get_node(cfg, args.node_id)
    app.config["NODE_ID"] = args.node_id
    if args.node_id == MAIN_NODE_ID:
        threading.Thread(target=watch_config, daemon=True).start()
    
    pull_config_from_main()
    if args.node_id == MAIN_NODE_ID:
        threading.Thread(target=watch_config, daemon=True).start()

    app.run(host=me["host"], port=me["port"])
