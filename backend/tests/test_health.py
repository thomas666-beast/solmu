import pytest


def test_health(logged_in_client):
    r = logged_in_client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"node_id": 1, "status": "ok"}


def test_post_and_get_shard(client):
    r = client.post("/shard/s1", data=b"payload-123")
    assert r.status_code == 201
    assert r.get_json()["size"] == 11
    r = client.get("/shard/s1")
    assert r.status_code == 200
    assert r.data == b"payload-123"


def test_post_empty_body_rejected(client):
    r = client.post("/shard/s2", data=b"")
    assert r.status_code == 400


def test_get_missing_shard_404(client):
    r = client.get("/shard/does-not-exist")
    assert r.status_code == 404


def test_notify_and_catalogue(logged_in_client):
    import app as app_module
    app_module.CATALOGUE.clear()
    entry = {"file_id": "FileA", "sender": 1, "shards": {"1": "s1", "2": "s2"}, "ts": 123}
    r = logged_in_client.post("/notify", json=entry)
    assert r.status_code == 200
    r = logged_in_client.get("/catalogue")
    assert r.get_json()["FileA"]["sender"] == 1


def test_broadcast_reaches_all_configured_nodes(client, monkeypatch):
    import app as app_module
    calls = []

    class FakeResp:
        status_code = 200

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        calls.append(url)
        return FakeResp()

    monkeypatch.setattr(app_module.requests, "post", fake_post)
    r = client.post("/broadcast", json={"file_id": "FileB", "sender": 1, "shards": {}})
    assert r.status_code == 200
    assert len(calls) == 5
    assert all(u.endswith("/notify") for u in calls)


def test_config_sync_stores_remote_config(logged_in_client):
    import app as app_module
    app_module.REMOTE_CONFIG["version"] = None
    new_cfg = {"version": 2, "nodes": [{"id": 1, "host": "127.0.0.1", "port": 9001}]}
    r = logged_in_client.post("/config-sync", json=new_cfg)
    assert r.status_code == 200
    assert r.get_json()["version"] == 2
    r = logged_in_client.get("/remote-config")
    assert r.get_json()["version"] == 2


def test_pull_config_from_main(client, monkeypatch):
    import app as app_module
    app_module.app.config["NODE_ID"] = 2
    app_module.REMOTE_CONFIG["version"] = None

    class FakeResp:
        ok = True

        def json(self):
            return {"version": 7, "nodes": [{"id": 1, "host": "127.0.0.1", "port": 9001}]}

    monkeypatch.setattr(
        app_module.requests, "get",
        lambda url, headers=None, timeout=None: FakeResp(),
    )
    app_module.pull_config_from_main()
    assert app_module.REMOTE_CONFIG["version"] == 7


def test_pull_skipped_for_main_node(client, monkeypatch):
    import app as app_module
    app_module.app.config["NODE_ID"] = 1
    app_module.REMOTE_CONFIG["version"] = None
    called = []
    monkeypatch.setattr(app_module.requests, "get", lambda *a, **k: called.append(1))
    app_module.pull_config_from_main()
    assert called == []
    assert app_module.REMOTE_CONFIG["version"] is None


def test_notify_persists_catalogue(client, tmp_path, monkeypatch):
    import app as app_module
    import storage
    monkeypatch.setattr(storage, "SHARD_DIR", tmp_path)
    monkeypatch.setattr(storage, "CATALOGUE_PATH", tmp_path / "catalogue.json")
    app_module.CATALOGUE.clear()
    client.post("/notify", json={"file_id": "P1", "sender": 1, "shards": {}, "ts": 1})
    assert "P1" in storage.load_catalogue()

