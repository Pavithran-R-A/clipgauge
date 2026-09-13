import pytest

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


def test_environment_identity_write_cleans_unique_temporary_on_replace_failure(monkeypatch, tmp_path):
    destination = tmp_path / "runtime-environment.json"
    destination.write_text("previous", encoding="utf-8")

    def fail_replace(*_args):
        raise OSError("replace failed")

    monkeypatch.setattr(environment.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        environment._write(destination, {"state": "new"})

    assert destination.read_text(encoding="utf-8") == "previous"
    assert list(tmp_path.glob(".runtime-environment.json.*.tmp")) == []
