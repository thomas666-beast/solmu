import argparse
import json
import queue
import tempfile
import threading
import time
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, request, session
from flask_cors import CORS

import auth
import config
import distribute
import progress as progress_store
from config import current_version, get_node, load_config
from storage import (
    delete_shard,
    load_catalogue,
    load_shard,
    save_catalogue,
    save_shard,
)
from upload import delete_incoming, new_upload_id, stream_request_to_file

app = Flask(__name__, static_folder=None)
app.secret_key = config.secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False
CORS(app, supports_credentials=True)

CATALOGUE = load_catalogue()
REMOTE_CONFIG = {"version": None, "nodes": []}
MAIN_NODE_ID = 1

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"


def require_token():
    expected = config.cluster_token()
    if not expected:
        return None
    got = request.headers.get("X-Solmu-Token", "")
    if got != expected:
        return jsonify({"error": "bad token"}), 401
    return None


def require_login():
    if not session.get("user"):
        return jsonify({"error": "login required"}), 401
    return None


@app.route("/")
def index():
    return Response((FRONTEND_DIR / "index.html").read_text(), mimetype="text/html")


@app.route("/login")
def login_page():
    return Response((FRONTEND_DIR / "login.html").read_text(), mimetype="text/html")


@app.route("/register")
def register_page():
    return Response((FRONTEND_DIR / "register.html").read_text(), mimetype="text/html")


@app.route("/static/<path:filename>")
def static_files(filename):
    if filename.endswith(".js"):
        p = DIST_DIR / filename
        mime = "application/javascript"
    elif filename.endswith(".css"):
        p = FRONTEND_DIR / filename
        mime = "text/css"
    elif filename.endswith(".svg"):
        p = FRONTEND_DIR / filename
        mime = "image/svg+xml"
    else:
        return jsonify({"error": "not found"}), 404
    if not p.exists():
        return jsonify({"error": f"not found: {p.name}"}), 404
    return Response(p.read_bytes(), mimetype=mime)


@app.route("/health")
def health():
    err = require_login()
    if err:
        return err
    return jsonify({"node_id": app.config["NODE_ID"], "status": "ok"})


@app.route("/config")
def config_route():
    err = require_token()
    if err:
        err2 = require_login()
        if err2:
            return err2
    return jsonify(load_config())


@app.route("/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    if not auth.register(username, password):
        return jsonify({"error": "user already exists or invalid"}), 409
    return jsonify({"ok": True, "username": username}), 201


@app.route("/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(force=True, silent=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")
    if not auth.verify(username, password):
        return jsonify({"error": "invalid credentials"}), 401
    session["user"] = username
    return jsonify({"ok": True, "username": username}), 200


@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"ok": True}), 200


@app.route("/shard/<shard_id>", methods=["POST"])
def post_shard(shard_id):
    err = require_token()
    if err:
        return err
    data = request.get_data()
    if not data:
        return jsonify({"error": "empty body"}), 400
    save_shard(shard_id, data)
    return jsonify({"shard_id": shard_id, "size": len(data)}), 201


@app.route("/shard/<shard_id>", methods=["GET"])
def get_shard(shard_id):
    err = require_token()
    if err:
        return err
    data = load_shard(shard_id)
    if data is None:
        return jsonify({"error": "not found or expired"}), 404
    return Response(data, mimetype="application/octet-stream")


@app.route("/delete-shard/<shard_id>", methods=["DELETE"])
def delete_shard_route(shard_id):
    err = require_token()
    if err:
        return err
    ok = delete_shard(shard_id)
    return jsonify({"shard_id": shard_id, "deleted": ok}), 200


@app.route("/notify", methods=["POST"])
def notify():
    err = require_token()
    if err:
        return err
    entry = request.get_json(force=True)
    CATALOGUE[entry["file_id"]] = entry
    save_catalogue(CATALOGUE)
    return jsonify({"ok": True, "file_id": entry["file_id"]})


@app.route("/forget/<file_id>", methods=["POST"])
def forget(file_id):
    err = require_token()
    if err:
        return err
    CATALOGUE.pop(file_id, None)
    save_catalogue(CATALOGUE)
    return jsonify({"ok": True})


@app.route("/catalogue")
def catalogue():
    err = require_login()
    if err:
        return err
    return jsonify(CATALOGUE)


@app.route("/broadcast", methods=["POST"])
def broadcast():
    err = require_token()
    if err:
        return err
    entry = request.get_json(force=True)
    cfg = load_config()
    results = {}
    for node in cfg["nodes"]:
        url = f"http://{node['host']}:{node['port']}/notify"
        try:
            r = requests.post(
                url,
                json=entry,
                headers={"X-Solmu-Token": config.cluster_token()},
                timeout=2,
            )
            results[node["id"]] = r.status_code
        except requests.RequestException:
            results[node["id"]] = "unreachable"
    return jsonify({"results": results})


@app.route("/config-sync", methods=["POST"])
def config_sync():
    err = require_token()
    if err:
        return err
    cfg = request.get_json(force=True)
    REMOTE_CONFIG["version"] = cfg["version"]
    REMOTE_CONFIG["nodes"] = cfg["nodes"]
    return jsonify({"ok": True, "version": cfg["version"]})


@app.route("/remote-config")
def remote_config():
    err = require_login()
    if err:
        return err
    return jsonify(REMOTE_CONFIG)


@app.route("/upload", methods=["POST"])
def upload():
    err = require_login()
    if err:
        return err

    original_name = request.headers.get("X-Filename", "upload.bin")
    upload_id = new_upload_id()
    size = stream_request_to_file(request.stream, upload_id)
    if size == 0:
        delete_incoming(upload_id)
        return jsonify({"error": "empty body"}), 400

    def worker():
        try:
            distribute.split_and_distribute(
                upload_id, original_name, app.config["NODE_ID"]
            )
        except Exception as e:
            progress_store.emit(upload_id, "error", {"message": str(e)})

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"upload_id": upload_id, "size": size}), 202


@app.route("/progress/<upload_id>", methods=["GET"])
def progress(upload_id):
    def stream():
        q = progress_store.register(upload_id)
        try:
            while True:
                try:
                    item = q.get(timeout=30)
                except queue.Empty:
                    yield "event: ping\ndata: {}\n\n"
                    continue
                yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
                if item["event"] in ("ready", "error"):
                    break
        finally:
            progress_store.unregister(upload_id)

    return Response(stream(), mimetype="text/event-stream")


@app.route("/reconstruct/<file_id>", methods=["GET"])
def reconstruct(file_id):
    err = require_login()
    if err:
        return err

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
                    r = requests.get(
                        url,
                        headers={"X-Solmu-Token": config.cluster_token()},
                        timeout=30,
                    )
                    if not r.ok:
                        return jsonify(
                            {"error": f"shard missing on node {node_id}"}
                        ), 502
                    p = tmpdir / f"remote-{node_id}.dat"
                    p.write_bytes(r.content)
                    local_paths.append(p)
                except requests.RequestException as e:
                    return jsonify(
                        {"error": f"node {node_id} unreachable: {e}"}
                    ), 502

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


@app.route("/delete/<file_id>", methods=["DELETE"])
def delete_file(file_id):
    err = require_login()
    if err:
        return err

    entry = CATALOGUE.get(file_id)
    if entry is None:
        return jsonify({"error": "unknown file_id"}), 404

    cfg = load_config()
    shards = entry["shards"]

    results: dict[str, object] = {}
    for node_id_str, shard_id in shards.items():
        node_id = int(node_id_str)
        if node_id == app.config["NODE_ID"]:
            results[str(node_id)] = delete_shard(shard_id)
        else:
            node = get_node(cfg, node_id)
            url = f"http://{node['host']}:{node['port']}/delete-shard/{shard_id}"
            try:
                r = requests.delete(
                    url,
                    headers={"X-Solmu-Token": config.cluster_token()},
                    timeout=10,
                )
                results[str(node_id)] = r.status_code
            except requests.RequestException as e:
                results[str(node_id)] = f"unreachable: {e}"

    CATALOGUE.pop(file_id, None)
    save_catalogue(CATALOGUE)

    for node in cfg["nodes"]:
        if node["id"] == app.config["NODE_ID"]:
            continue
        url = f"http://{node['host']}:{node['port']}/forget/{file_id}"
        try:
            requests.post(
                url,
                headers={"X-Solmu-Token": config.cluster_token()},
                timeout=5,
            )
        except requests.RequestException:
            pass

    return jsonify({"file_id": file_id, "shards": results}), 200


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
                requests.post(
                    url,
                    json=cfg,
                    headers={"X-Solmu-Token": config.cluster_token()},
                    timeout=2,
                )
            except requests.RequestException:
                pass


def pull_config_from_main():
    if app.config.get("NODE_ID") == MAIN_NODE_ID:
        return
    cfg = load_config()
    main = get_node(cfg, MAIN_NODE_ID)
    url = f"http://{main['host']}:{main['port']}/config"
    try:
        r = requests.get(
            url,
            headers={"X-Solmu-Token": config.cluster_token()},
            timeout=2,
        )
        if r.ok:
            remote = r.json()
            REMOTE_CONFIG["version"] = remote["version"]
            REMOTE_CONFIG["nodes"] = remote["nodes"]
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
    pull_config_from_main()
    if args.node_id == MAIN_NODE_ID:
        threading.Thread(target=watch_config, daemon=True).start()
    app.run(host=me["host"], port=me["port"])
