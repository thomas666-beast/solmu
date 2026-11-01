def test_upload_streams_to_disk(client, tmp_path, monkeypatch):
    import upload as upload_module
    import distribute as dist

    monkeypatch.setattr(upload_module, "INCOMING_DIR", tmp_path)
    monkeypatch.setattr(dist, "split_and_distribute",
                        lambda upload_id, name, sender: {
                            "file_id": "fake-id",
                            "hash": "deadbeef",
                            "shards": {},
                            "distribution": {},
                        })

    payload = b"x" * (3 * 1024 * 1024)
    r = client.post("/upload", data=payload,
                    headers={"X-Filename": "big.bin"},
                    content_type="application/octet-stream")
    assert r.status_code == 201
    body = r.get_json()
    assert body["size"] == len(payload)
    assert body["file_id"] == "fake-id"
    assert body["hash"] == "deadbeef"
