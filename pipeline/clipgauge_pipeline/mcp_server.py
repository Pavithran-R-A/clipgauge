"""Minimal stdio MCP boundary over persistent ClipGauge jobs."""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from . import __version__, config, protocol
from .collections.render import render_collection
from .collections.service import create_collection, delete_collection, list_collections, update_collection
from .ingest.manifest import default_manifest
from .jobs import queue
from .scoring import providers

SECRET_KEY = re.compile(r"(?i)(api[_-]?key|token|secret|authorization|cookie|password)")

TOOLS = [
    "preflight", "list_providers", "list_jobs", "start_job", "get_job_status",
    "get_job_results", "cancel_job", "render_clip", "rerender_clip",
    "list_collections", "create_collection", "update_collection", "delete_collection", "render_collection",
]


def reject_secret_arguments(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY.search(str(key)):
                raise ValueError(f"secret-shaped argument is not accepted: {key}")
            reject_secret_arguments(item)
    elif isinstance(value, list):
        for item in value:
            reject_secret_arguments(item)


class McpService:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clipgauge-mcp")

    def _run_job(self, job) -> None:
        from .cli import _stages

        try:
            queue.run_stages(
                job,
                _stages(),
                lambda stage, fraction, message: print(
                    f"mcp job={job.id} stage={stage} progress={fraction:.3f} {protocol.safe_message(message, 180)}",
                    file=sys.stderr,
                    flush=True,
                ),
            )
        except queue.StageError:
            return
        except Exception as exc:  # noqa: BLE001 - worker records through job store
            queue.set_job_status(job.id, "failed", protocol.safe_message(str(exc)))

    def start_job(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from .cli import _apply_profile

        source = str(arguments.get("source", "")).strip()
        if not source:
            raise ValueError("source is required")
        source_type = "url" if source.startswith(("http://", "https://")) else "file"
        if source_type == "file":
            source = str(Path(source).expanduser().resolve())
            if not Path(source).is_file():
                raise ValueError("source file is unavailable")
        quality_mode = config.validate_quality_mode(str(arguments.get("quality_mode", "private")))
        settings = config.Settings(quality_mode=quality_mode)
        profile_kind = arguments.get("provider") or ("clipgauge-local" if quality_mode == "private" else "gemini")
        profile = providers.preset_profile(str(profile_kind), model=arguments.get("model"))
        config.validate_quality_mode_for_provider(quality_mode, profile.locality)
        _apply_profile(settings, profile)
        settings.content_category = config.validate_content_category(arguments.get("category", "auto"))
        settings.output_preference = config.validate_output_preference(str(arguments.get("output_preference", "recommended")))
        settings.caption_preset = str(arguments.get("caption_preset", "classic"))
        input_manifest = default_manifest(source_type, source)
        subtitle_path = arguments.get("subtitle_path")
        if subtitle_path:
            input_manifest["subtitle"].update({"mode": "external", "requested_path": str(Path(str(subtitle_path)).expanduser().resolve())})
        job = queue.create_job(source_type, source, json.dumps(settings.to_json()), input_manifest=input_manifest)
        self._executor.submit(self._run_job, job)
        return {"job_id": job.id, "status": "pending"}

    def status(self, job_id: str) -> dict[str, Any]:
        job = queue.get_job(job_id)
        if job is None:
            raise ValueError("job not found")
        return {"job_id": job.id, "status": job.status, "title": job.title, "error": job.error, "stages": queue.stage_statuses(job.id)}

    def results(self, job_id: str) -> dict[str, Any]:
        job = queue.get_job(job_id)
        if job is None:
            raise ValueError("job not found")
        output: dict[str, Any] = {}
        for path in sorted(job.dir.glob("*.json")):
            if path.name in {"settings.json", "input.json", "artifact-manifest.json", "collections.json"}:
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and isinstance(value.get("data"), dict):
                output[path.stem] = value["data"]
        return output

    @staticmethod
    def _collection_clips(results: dict[str, Any]) -> list[dict[str, Any]]:
        source = (results.get("enrich") or {}).get("clips") or (results.get("score") or {}).get("clips") or []
        clips = [dict(item) for item in source if isinstance(item, dict)]
        outputs = (results.get("render") or {}).get("outputs") or []
        for index, clip in enumerate(clips):
            output = next(
                (
                    item for item in outputs
                    if isinstance(item, dict)
                    and item.get("clip_id")
                    and item.get("clip_id") == clip.get("clip_id")
                ),
                outputs[index] if index < len(outputs) and isinstance(outputs[index], dict) else None,
            )
            if isinstance(output, dict) and output.get("path"):
                clip["render_path"] = output["path"]
        return clips

    def cancel(self, job_id: str) -> dict[str, Any]:
        job = queue.get_job(job_id)
        if job is None:
            raise ValueError("job not found")
        (job.dir / "cancel.requested").write_text("requested\n", encoding="utf-8")
        if job.status == "pending":
            queue.set_job_status(job.id, "failed", "Job cancelled.")
        return {"job_id": job.id, "cancel_requested": True}

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        reject_secret_arguments(arguments)
        if name == "list_jobs":
            return [{"job_id": job.id, "status": job.status, "title": job.title} for job in queue.list_jobs()]
        if name == "start_job":
            return self.start_job(arguments)
        if name == "get_job_status":
            return self.status(str(arguments.get("job_id", "")))
        if name == "get_job_results":
            return self.results(str(arguments.get("job_id", "")))
        if name == "cancel_job":
            return self.cancel(str(arguments.get("job_id", "")))
        if name == "list_providers":
            return ["clipgauge-local", "ollama", "lmstudio", "gemini", "groq", "openrouter"]
        if name == "preflight":
            return {"ok": True, "service": "clipgauge", "protocol_version": 2}
        job = queue.get_job(str(arguments.get("job_id", "")))
        if job is None:
            raise ValueError("job not found")
        results = self.results(job.id)
        clips = self._collection_clips(results)
        if name in {"list_collections", "create_collection", "update_collection", "render_collection"}:
            if name == "list_collections":
                return list_collections(job, clips)
            if name == "create_collection":
                return create_collection(job, str(arguments.get("title", "Series")), list(arguments.get("clip_ids", [])), clips=clips)
            if name == "update_collection":
                return update_collection(job, str(arguments.get("collection_id", "")), title=arguments.get("title"), clip_ids=arguments.get("clip_ids"), clips=clips)
            return {"path": str(render_collection(job, str(arguments.get("collection_id", "")), clips))}
        if name in {"render_clip", "rerender_clip"}:
            from .edits.render_clip import render_clip_edit

            result = render_clip_edit(job.dir, int(arguments.get("clip", 0)), lambda *_: None)
            return result
        if name == "delete_collection":
            delete_collection(job, str(arguments.get("collection_id", "")), clips=clips)
            return {"deleted": True}
        raise ValueError(f"unknown MCP tool: {name}")


def serve_stdio() -> int:
    service = McpService()
    for line in sys.stdin:
        try:
            request = json.loads(line)
            method = request.get("method")
            identifier = request.get("id")
            if method == "initialize":
                result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "clipgauge", "version": __version__}}
            elif method == "tools/list":
                result = {"tools": [{"name": name, "description": f"ClipGauge {name}", "inputSchema": {"type": "object"}} for name in TOOLS]}
            elif method == "tools/call":
                params = request.get("params") or {}
                result = {"content": [{"type": "text", "text": json.dumps(service.call(str(params.get("name")), dict(params.get("arguments") or {})), ensure_ascii=False)}]}
            else:
                raise ValueError("unsupported MCP method")
            print(json.dumps({"jsonrpc": "2.0", "id": identifier, "result": result}), flush=True)
        except Exception as exc:  # noqa: BLE001 - protocol must remain valid JSON
            print(json.dumps({"jsonrpc": "2.0", "id": locals().get("identifier"), "error": {"code": -32602, "message": protocol.safe_message(str(exc))}}), flush=True)
    service._executor.shutdown(wait=False, cancel_futures=True)
    return 0
