import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from clipgauge_pipeline.server.app import create_app


def test_health_is_public_and_readiness_requires_token():
    client = TestClient(create_app(host="127.0.0.1", token="local-token"))
    assert client.get("/v1/health").json()["ok"] is True
    assert client.get("/v1/readiness").status_code == 401
    assert client.get("/v1/readiness", headers={"X-ClipGauge-Token": "local-token"}).status_code == 200


def test_non_loopback_and_wildcard_cors_are_rejected():
    with pytest.raises(ValueError, match="server token"):
        create_app(host="0.0.0.0", token=None)
    with pytest.raises(ValueError, match="wildcard CORS"):
        create_app(host="127.0.0.1", token=None, cors_origins=["*"])


def test_local_import_requires_configured_root(tmp_path):
    client = TestClient(create_app(host="127.0.0.1", token="local-token", import_roots=[str(tmp_path)]))
    response = client.post(
        "/v1/jobs",
        headers={"X-ClipGauge-Token": "local-token"},
        json={"source": str(tmp_path.parent / "outside.mp4")},
    )
    assert response.status_code == 400
