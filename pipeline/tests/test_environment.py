from clipgauge_pipeline import environment


def test_runtime_identity_requires_matching_persisted_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setattr(environment, "identity_path", lambda _root=None: tmp_path / "runtime-environment.json")

    missing = environment.status(tmp_path)
    assert missing["state"] == "UPDATE_REQUIRED"
    assert missing["reason"] == "ClipGauge runtime update required"

    environment.write_identity(tmp_path)
    assert environment.status(tmp_path)["state"] == "READY"

    monkeypatch.setattr(environment, "ENVIRONMENT_ABI_VERSION", "test-change")
    changed = environment.status(tmp_path)
    assert changed["state"] == "UPDATE_REQUIRED"
    assert changed["expected_fingerprint"] != changed["stored_fingerprint"]
