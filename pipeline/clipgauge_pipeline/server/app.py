"""FastAPI adapter over the real ClipGauge job store."""

from __future__ import annotations

import os
from pathlib import Path

from .. import __version__
from .auth import authorize, reject_secret_payload, require_server_token


def create_app(*, host: str = "127.0.0.1", token: str | None = None, cors_origins: list[str] | None = None, import_roots: list[str] | None = None):
    try:
        from fastapi import FastAPI, Header, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as exc:
        raise RuntimeError("FastAPI is optional. Install clipgauge-pipeline[headless].") from exc
    require_server_token(host, token)
    from ..mcp_server import McpService

    service = McpService()
    roots = [Path(root).expanduser().resolve() for root in import_roots or []]
    app = FastAPI(title="ClipGauge Headless API", version=__version__)
    if cors_origins:
        if "*" in cors_origins:
            raise ValueError("wildcard CORS is not allowed")
        app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["content-type", "x-clipgauge-token"])

    def check_auth(provided: str | None) -> None:
        if not authorize(provided, token):
            raise HTTPException(status_code=401, detail="unauthorized")

    def allowed_source(body: dict) -> None:
        source = body.get("source")
        if isinstance(source, str) and not source.startswith(("http://", "https://")):
            candidate = Path(source).expanduser().resolve()
            if not roots or not any(root == candidate or root in candidate.parents for root in roots):
                raise HTTPException(status_code=400, detail="local source is outside configured import roots")

    @app.get("/v1/health")
    def health():
        return {"ok": True, "service": "clipgauge", "version": __version__}

    @app.get("/v1/readiness")
    def readiness(x_clipgauge_token: str | None = Header(default=None)):
        check_auth(x_clipgauge_token)
        return {"ok": True, "state": "READY", "concurrency": 1}

    @app.get("/v1/providers")
    def providers_route(x_clipgauge_token: str | None = Header(default=None)):
        check_auth(x_clipgauge_token)
        return service.call("list_providers", {})

    @app.get("/v1/preflight")
    def preflight(x_clipgauge_token: str | None = Header(default=None)):
        check_auth(x_clipgauge_token)
        return service.call("preflight", {})

    @app.get("/v1/jobs")
    def jobs(x_clipgauge_token: str | None = Header(default=None)):
        check_auth(x_clipgauge_token)
        return service.call("list_jobs", {})

    @app.post("/v1/jobs")
    def start(body: dict, x_clipgauge_token: str | None = Header(default=None)):
        check_auth(x_clipgauge_token)
        reject_secret_payload(body)
        allowed_source(body)
        return service.call("start_job", body)

    @app.get("/v1/jobs/{job_id}")
    def status(job_id: str, x_clipgauge_token: str | None = Header(default=None)):
        check_auth(x_clipgauge_token)
        return service.call("get_job_status", {"job_id": job_id})

    @app.get("/v1/jobs/{job_id}/results")
    def results(job_id: str, x_clipgauge_token: str | None = Header(default=None)):
        check_auth(x_clipgauge_token)
        return service.call("get_job_results", {"job_id": job_id})

    @app.post("/v1/jobs/{job_id}/cancel")
    def cancel(job_id: str, x_clipgauge_token: str | None = Header(default=None)):
        check_auth(x_clipgauge_token)
        return service.call("cancel_job", {"job_id": job_id})

    @app.get("/v1/jobs/{job_id}/collections")
    def collections(job_id: str, x_clipgauge_token: str | None = Header(default=None)):
        check_auth(x_clipgauge_token)
        return service.call("list_collections", {"job_id": job_id})

    @app.post("/v1/jobs/{job_id}/collections")
    def create_collection_route(job_id: str, body: dict, x_clipgauge_token: str | None = Header(default=None)):
        check_auth(x_clipgauge_token)
        reject_secret_payload(body)
        return service.call("create_collection", {**body, "job_id": job_id})

    @app.patch("/v1/jobs/{job_id}/collections/{collection_id}")
    def update_collection_route(job_id: str, collection_id: str, body: dict, x_clipgauge_token: str | None = Header(default=None)):
        check_auth(x_clipgauge_token)
        reject_secret_payload(body)
        return service.call("update_collection", {**body, "job_id": job_id, "collection_id": collection_id})

    @app.delete("/v1/jobs/{job_id}/collections/{collection_id}")
    def delete_collection_route(job_id: str, collection_id: str, x_clipgauge_token: str | None = Header(default=None)):
        check_auth(x_clipgauge_token)
        return service.call("delete_collection", {"job_id": job_id, "collection_id": collection_id})

    @app.post("/v1/jobs/{job_id}/collections/{collection_id}/render")
    def render_collection_route(job_id: str, collection_id: str, x_clipgauge_token: str | None = Header(default=None)):
        check_auth(x_clipgauge_token)
        return service.call("render_collection", {"job_id": job_id, "collection_id": collection_id})

    return app
