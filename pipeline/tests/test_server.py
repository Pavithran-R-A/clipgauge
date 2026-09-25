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


def test_external_subtitle_must_stay_inside_import_root(tmp_path):
    source = tmp_path / "media.mp4"
    subtitle = tmp_path / "captions.srt"
    source.write_bytes(b"video")
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    outside = tmp_path.parent / "outside.srt"
    outside.write_text("1\n00:00:00,000 --> 00:00:01,000\nNo\n", encoding="utf-8")
    client = TestClient(create_app(host="127.0.0.1", token="local-token", import_roots=[str(tmp_path)]))
    response = client.post(
        "/v1/jobs",
        headers={"X-ClipGauge-Token": "local-token"},
        json={"source": str(source), "subtitle_path": str(outside)},
    )
    assert response.status_code == 400
    assert "subtitle" in response.json()["detail"]


def test_external_subtitle_inside_root_is_accepted(monkeypatch, tmp_path):
    from clipgauge_pipeline.mcp_server import McpService

    source = tmp_path / "media.mp4"
    subtitle = tmp_path / "captions.srt"
    source.write_bytes(b"video")
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    monkeypatch.setattr(McpService, "start_job", lambda self, body: {"source": body["source"], "subtitle_path": body["subtitle_path"]})
    client = TestClient(create_app(host="127.0.0.1", token="local-token", import_roots=[str(tmp_path)]))
    response = client.post(
        "/v1/jobs",
        headers={"X-ClipGauge-Token": "local-token"},
        json={"source": str(source), "subtitle_path": str(subtitle)},
    )
    assert response.status_code == 200


def test_resume_route_delegates_to_same_job_service(monkeypatch, tmp_path):
    from clipgauge_pipeline.mcp_server import McpService

    monkeypatch.setattr(McpService, "resume_job", lambda self, job_id: {"job_id": job_id, "resumed": True})
    client = TestClient(create_app(host="127.0.0.1", token="local-token", import_roots=[str(tmp_path)]))
    response = client.post("/v1/jobs/20260925-120000-abcdef/resume", headers={"X-ClipGauge-Token": "local-token"})
    assert response.status_code == 200
    assert response.json()["resumed"] is True
