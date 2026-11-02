def test_upload_streams_to_disk(logged_in_client, tmp_path, monkeypatch):
    import upload as upload_module
    import distribute as dist

    monkeypatch.setattr(upload_module, "INCOMING_DIR", tmp_path)
    monkeypatch.setattr(dist, "split_and_distribute",
                        lambda upload_id, name, sender: None)

    payload = b"x" * (3 * 1024 * 1024)
    r = logged_in_client.post("/upload", data=payload,
                              headers={"X-Filename": "big.bin"},
                              content_type="application/octet-stream")
    assert r.status_code == 202
    body = r.get_json()
    assert body["size"] == len(payload)
    assert "upload_id" in body

    path = tmp_path / f"{body['upload_id']}.bin"
    assert path.exists()
    assert path.stat().st_size == len(payload)


def test_register_and_login(client):
    r = client.post("/auth/register", json={"username": "alice", "password": "secret"})
    assert r.status_code == 201
    r = client.post("/auth/login", json={"username": "alice", "password": "secret"})
    assert r.status_code == 200
    r = client.get("/catalogue")
    assert r.status_code == 200


def test_login_wrong_password(client):
    client.post("/auth/register", json={"username": "bob", "password": "right"})
    r = client.post("/auth/login", json={"username": "bob", "password": "wrong"})
    assert r.status_code == 401


def test_protected_route_without_login(client):
    r = client.get("/catalogue")
    assert r.status_code == 401


def test_logout_clears_session(logged_in_client):
    r = logged_in_client.post("/auth/logout")
    assert r.status_code == 200
    r = logged_in_client.get("/catalogue")
    assert r.status_code == 401


def test_delete_unknown_file_404(logged_in_client):
    r = logged_in_client.delete("/delete/nope")
    assert r.status_code == 404


def test_notify_rejects_bad_token(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "cluster_token", lambda: "secret-xyz")

    r = client.post("/notify", json={"file_id": "X", "sender": 1, "shards": {}, "ts": 1})
    assert r.status_code == 401

    r = client.post("/notify", json={"file_id": "X", "sender": 1, "shards": {}, "ts": 1},
                    headers={"X-Solmu-Token": "secret-xyz"})
    assert r.status_code == 200
