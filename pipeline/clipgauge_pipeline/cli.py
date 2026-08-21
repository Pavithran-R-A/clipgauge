"""ClipGauge CLI.

Doubles as the desktop app's sidecar: with --jsonl every progress event and
the final result are emitted as one JSON object per stdout line, so the Tauri shell spawns `clipgauge --jsonl run <source>` and streams.

"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time

from . import __version__, config, downloads, local_runtime, protocol
from .jobs import queue
from .scoring import providers as providers_mod


def _stages() -> list[queue.Stage]:
    # Grows per milestone: ingest → asr → diarize → events → candidates →
    # score → camera → render. Stage imports are deferred so `clipgauge
    # jobs` doesn't pay the torch import tax.
    from .asr.stage import AsrStage
    from .camera.stage import CameraStage
    from .candidates.stage import CandidatesStage
    from .diarize.stage import DiarizeStage
    from .events.stage import EventsStage
    from .ingest.stage import IngestStage
    from .render.stage import RenderStage
    from .scoring.stage import ScoreStage

    return [
        IngestStage(),
        AsrStage(),
        DiarizeStage(),
        EventsStage(),
        CandidatesStage(),
        ScoreStage(),
        CameraStage(),
        RenderStage(),
    ]


def _progress_printer(jsonl: bool):
    started_at = time.monotonic()
    stage_started: dict[str, float] = {}

    def emit(stage: str, fraction: float, message: str) -> None:
        now = time.monotonic()
        stage_started.setdefault(stage, now)
        elapsed = max(0.0, now - started_at)
        stage_elapsed = max(0.0, now - stage_started[stage])
        indeterminate = fraction < 0
        eta = None
        if fraction > 0.0 and fraction < 1.0 and stage_elapsed > 0.0:
            eta = max(0.0, stage_elapsed * (1.0 - fraction) / fraction)
        one_time_download = "download" in message.lower() or "install" in message.lower()
        if jsonl:
            event = {
                "event": "progress",
                "protocol_version": protocol.PROTOCOL_VERSION,
                "stage": stage,
                "stage_id": stage,
                "display_stage": protocol.DISPLAY_STAGES.get(stage, stage.replace("_", " ").title()),
                "operation": message,
                "fraction": fraction,
                "indeterminate": indeterminate,
                "message": message,
                "elapsed_seconds": round(elapsed, 3),
                "stage_elapsed_seconds": round(stage_elapsed, 3),
                "one_time_download": one_time_download,
            }
            if eta is not None:
                event["eta_seconds"] = round(eta, 3)
            accelerator = os.environ.get("CLIPGAUGE_ACCELERATOR")
            if accelerator:
                event["accelerator"] = protocol.safe_message(accelerator, limit=80)
            print(json.dumps(event), flush=True)
        else:
            pct = f"{fraction * 100:5.1f}%" if fraction >= 0 else "  ...."
            eta_label = f" ETA {eta:4.0f}s" if eta is not None else ""
            print(f"[{stage:<10}] {pct}{eta_label} {message}", file=sys.stderr, flush=True)

    return emit


def _emit_result(jsonl: bool, payload: dict) -> None:
    if jsonl:
        print(json.dumps({"event": "result", **payload}), flush=True)
    else:
        print(json.dumps(payload, indent=2))


def _preflight_terminal(jsonl: bool, job_id: str | None, code: str, message: str, retryable: bool = False) -> int:
    if jsonl:
        protocol.TerminalEmitter(
            emit=lambda event: print(json.dumps(event), flush=True),
            job_id=job_id,
        ).terminal(
            ok=False,
            code=code,
            message=message,
            retryable=retryable,
            stage="pipeline",
            exit_code=2,
        )
    else:
        print(message, file=sys.stderr)
    return 2


def _profile_from_args(args: argparse.Namespace) -> providers_mod.ProviderProfile:
    kind = args.provider or args.llm or "gemini"
    return providers_mod.preset_profile(
        kind,
        model=args.model,
        endpoint=args.endpoint,
        auth_strategy=args.auth,
        secret_header_name=args.secret_header,
    )


def _apply_profile(settings: config.Settings, profile: providers_mod.ProviderProfile) -> None:
    settings.llm_mode = profile.kind
    settings.provider_profile_id = profile.id
    settings.provider_kind = profile.kind
    settings.provider_model = profile.model
    settings.provider_endpoint_identity = profile.endpoint_identity
    settings.provider_capabilities = profile.capabilities.to_dict()
    settings.provider_auth_strategy = profile.auth_strategy
    settings.provider_locality = profile.locality
    settings.provider_metadata = dict(profile.metadata)
    settings.provider_schema_version = profile.schema_version


def _setup_runtime_asset(manager: local_runtime.LocalRuntime) -> downloads.ManagedAsset:
    spec = manager.runtime_asset()
    version = str(manager.manifest["runtimes"]["llama-server"]["version"])
    platform_key = manager._platform_key()
    archive_type = str(spec["archive_type"])
    return downloads.ManagedAsset(
        asset_id=f"runtime:llama-server:{platform_key}",
        display_name=f"ClipGauge Local runtime · llama.cpp {version}",
        purpose="Owned loopback local inference runtime",
        destination=f"downloads/llama-server-{version}-{platform_key}.{archive_type.replace('.', '-')}",
        url=str(spec["url"]),
        size_bytes=int(spec["size"]),
        sha256=str(spec["sha256"]),
        required=True,
        one_time=True,
        license=str(manager.manifest["runtimes"]["llama-server"]["license"]),
        source=str(manager.manifest["runtimes"]["llama-server"]["provenance"]),
    )


def _setup_model_asset(model: local_runtime.LocalModel) -> downloads.ManagedAsset:
    return downloads.ManagedAsset(
        asset_id=model.model_id,
        display_name=model.display_name,
        purpose="ClipGauge Local structured clip scoring",
        destination=f"models/clipgauge-local/{model.filename}",
        url=model.url,
        size_bytes=model.size_bytes,
        sha256=model.sha256,
        required=False,
        one_time=True,
        license=model.license,
        source=model.provenance,
    )


def cmd_setup(args: argparse.Namespace) -> int:
    manager = local_runtime.LocalRuntime()

    def setup_event(payload: dict[str, object]) -> None:
        if args.jsonl:
            print(json.dumps({"event": "setup-progress", "protocol_version": protocol.PROTOCOL_VERSION, **payload}), flush=True)

    downloads_manager = downloads.DownloadManager(event=setup_event)
    try:
        runtime_asset = _setup_runtime_asset(manager)
        model_assets = [_setup_model_asset(model) for model in local_runtime.MODEL_CATALOG.values()]
        if args.setup_cmd == "inventory":
            runtime_binary = manager.binary_path()
            rows = downloads_manager.inventory(model_assets)
            payload = {
                "state": "ready" if runtime_binary.is_file() else "setup-required",
                "runtime": {
                    **runtime_asset.to_json(),
                    "installed": runtime_binary.is_file(),
                    "managed_path": str(runtime_binary),
                    "version": manager.manifest["runtimes"]["llama-server"]["version"],
                },
                "models": rows,
                "storage": downloads_manager.estimate([runtime_asset, *model_assets]),
                "catalog": [
                    {
                        "model_id": model.model_id,
                        "display_name": model.display_name,
                        "license": model.license,
                        "context_window": model.context_window,
                        "capabilities": list(model.capabilities),
                        "provenance": model.provenance,
                    }
                    for model in local_runtime.MODEL_CATALOG.values()
                ],
            }
            print(json.dumps(payload))
            return 0
        if args.setup_cmd == "install-runtime":
            archive = downloads_manager.download(runtime_asset)
            binary = manager.install_runtime(archive)
            print(json.dumps({"ok": True, "asset_id": runtime_asset.asset_id, "path": str(binary)}))
            return 0
        if args.setup_cmd == "download-model":
            try:
                model = local_runtime.MODEL_CATALOG[args.model_id]
            except KeyError as exc:
                print(json.dumps({"ok": False, "code": "MODEL_NOT_FOUND", "message": "The selected local model is not in the verified catalog."}))
                return 2
            asset = _setup_model_asset(model)
            path = downloads_manager.download(asset)
            print(json.dumps({"ok": True, "asset_id": asset.asset_id, "path": str(path), "license": asset.license, "source": asset.source}))
            return 0
    except Exception as err:  # noqa: BLE001 - setup commands return one actionable JSON result
        print(json.dumps({"ok": False, "code": "SETUP_DOWNLOAD_FAILED", "message": protocol.safe_message(str(err), limit=300)}))
        return 1
    return 2


def cmd_preflight(args: argparse.Namespace) -> int:
    from . import preflight

    try:
        profile = _profile_from_args(args)
        payload = preflight.run(profile)
    except Exception as err:  # noqa: BLE001 — preflight must return an actionable JSON result
        payload = {
            "state": "blocked",
            "selected_llm": args.provider or args.llm or "gemini",
            "checks": [{"name": "preflight", "state": "blocked", "message": protocol.safe_message(str(err)), "remediation": "Repair the local installation and retry."}],
        }
    print(json.dumps(payload), flush=True)
    return 0 if payload["state"] != "blocked" else 2


def cmd_provider_test(args: argparse.Namespace) -> int:
    try:
        profile = _profile_from_args(args)
        adapter = providers_mod.make_adapter(profile)
        if args.vision_smoke:
            tiny_png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
            smoke = adapter.infer(
                providers_mod.InferenceRequest(
                    prompt='Return exactly {"vision":true}.',
                    schema={"type": "object", "properties": {"vision": {"type": "boolean"}}, "required": ["vision"]},
                    images=[tiny_png],
                    purpose="manual_live_smoke",
                    require_vision=True,
                )
            )
            result = {"state": "WARNING" if smoke.degraded_signals else "PASS", "provider": profile.kind, "model": smoke.model, "capabilities": smoke.capabilities_used, "degraded_signals": smoke.degraded_signals}
        else:
            result = adapter.test_connection()
    except Exception as err:  # noqa: BLE001 — return an actionable JSON boundary
        result = {
            "state": "FAIL",
            "provider": args.provider or args.llm or "gemini",
            "message": protocol.safe_message(str(err)),
        }
    print(json.dumps(result), flush=True)
    return 0 if result.get("state") in {"PASS", "WARNING"} else 2


def cmd_run(args: argparse.Namespace) -> int:
    source = args.source
    source_type = "url" if source.startswith(("http://", "https://")) else "file"
    settings = config.Settings()
    try:
        _apply_profile(settings, _profile_from_args(args))
    except Exception as err:  # noqa: BLE001 — profile validation is a pre-job boundary
        return _preflight_terminal(args.jsonl, None, "PROVIDER_PROFILE_INVALID", protocol.safe_message(str(err)), False)
    if args.captions:
        settings.caption_preset = args.captions
    if args.camera:
        settings.camera.speaker_change = args.camera
    try:
        job = queue.create_job(source_type, source, json.dumps(settings.to_json()))
    except Exception as err:  # noqa: BLE001 — pre-job protocol boundary
        return _preflight_terminal(args.jsonl, None, "JOB_CREATE_FAILED", f"Could not create a pipeline job: {protocol.safe_message(str(err))}", True)
    return _execute(job, args.jsonl)


def cmd_resume(args: argparse.Namespace) -> int:
    job = queue.get_job(args.job_id)
    if job is None:
        return _preflight_terminal(args.jsonl, args.job_id, "JOB_NOT_FOUND", "The requested job could not be found in the managed job store.")
    if args.llm or args.provider or args.model or args.endpoint or args.captions or args.camera:
        settings = config.Settings.from_json(json.loads(job.settings_json))
        if args.llm or args.provider or args.model or args.endpoint:
            try:
                _apply_profile(settings, _profile_from_args(args))
            except Exception as err:  # noqa: BLE001
                return _preflight_terminal(args.jsonl, args.job_id, "PROVIDER_PROFILE_INVALID", protocol.safe_message(str(err)), False)
        if args.captions:
            settings.caption_preset = args.captions
        if args.camera:
            settings.camera.speaker_change = args.camera
        new_json = json.dumps(settings.to_json())
        with queue._connect() as conn:  # noqa: SLF001 — CLI is a queue friend
            conn.execute("UPDATE jobs SET settings_json = ? WHERE id = ?", (new_json, job.id))
        job = queue.get_job(args.job_id)
    return _execute(job, args.jsonl)


def _execute(job: queue.Job, jsonl: bool) -> int:
    emit = _progress_printer(jsonl)
    terminal = protocol.TerminalEmitter(
        emit=lambda event: print(json.dumps(event), flush=True),
        job_id=job.id,
    )
    if jsonl:
        print(json.dumps({"event": "job", "job_id": job.id}), flush=True)
    else:
        print(f"job {job.id} → {job.dir}", file=sys.stderr)
    try:
        results = queue.run_stages(job, _stages(), emit)
    except queue.StageError as err:
        diagnostic = err.diagnostic_id
        if diagnostic is None and err.__cause__ is not None:
            diagnostic = protocol.write_diagnostic(job.dir, err.stage or "pipeline", err.__cause__)
        if jsonl:
            terminal.terminal(
                ok=False,
                code=err.code,
                message=str(err),
                retryable=err.retryable,
                stage=err.stage,
                diagnostic=diagnostic,
            )
        else:
            _emit_result(jsonl, {"ok": False, "job_id": job.id, "error": str(err)})
        return 1
    except queue.StageExecutionError as err:
        diagnostic = protocol.write_diagnostic(job.dir, err.stage, err.original)
        message = f"Pipeline failed unexpectedly. Diagnostic ID: {diagnostic}."
        if jsonl:
            terminal.terminal(
                ok=False,
                code="INTERNAL_ERROR",
                message=message,
                retryable=False,
                stage=err.stage,
                diagnostic=diagnostic,
            )
        else:
            _emit_result(jsonl, {"ok": False, "job_id": job.id, "error": message})
        return 1
    except Exception as err:  # noqa: BLE001 — final protocol guard
        diagnostic = protocol.write_diagnostic(job.dir, "pipeline", err)
        message = f"Pipeline failed unexpectedly. Diagnostic ID: {diagnostic}."
        if jsonl:
            terminal.terminal(
                ok=False,
                code="INTERNAL_ERROR",
                message=message,
                retryable=False,
                stage="pipeline",
                diagnostic=diagnostic,
            )
        else:
            _emit_result(jsonl, {"ok": False, "job_id": job.id, "error": message})
        return 1
    summary = {
        "ok": True,
        "job_id": job.id,
        "stages": list(results.keys()),
        "title": results.get("ingest", {}).get("title"),
        "heatmap_segments": len(results.get("ingest", {}).get("heatmap") or []),
    }
    if jsonl:
        terminal.terminal(
            ok=True,
            code="OK",
            message="Pipeline completed.",
            retryable=False,
            stage="pipeline",
        )
    else:
        _emit_result(jsonl, summary)
    return 0


def cmd_jobs(args: argparse.Namespace) -> int:
    for job in queue.list_jobs():
        stages = queue.stage_statuses(job.id)
        done = sum(1 for s in stages.values() if s == "done")
        print(f"{job.id}  {job.status:<8} {done} stage(s) done  {job.title or job.source}")
    return 0


def cmd_edit(args: argparse.Namespace) -> int:
    """Per-clip editing verbs. All output is JSON on stdout for the app."""
    from pathlib import Path

    from .edits import render_clip as rc
    from .edits import store, visuals

    job = queue.get_job(args.job_id)
    if job is None:
        print(json.dumps({"ok": False, "error": f"no job {args.job_id}"}))
        return 2
    job_dir = Path(job.dir)

    if args.edit_cmd == "context":
        print(json.dumps({"ok": True, **rc.context_for_clip(job_dir, args.clip)}))
        return 0

    if args.edit_cmd == "suggest-visuals":
        score = json.loads((job_dir / "score.json").read_text())["data"]
        clip = score["clips"][args.clip]
        edit = store.edit_for_clip(job_dir, args.clip, clip)
        # plan against OUTPUT-time words = current bounds without dead-space
        # (suggestions land on the source-bounds timeline the UI shows)
        diarize = json.loads((job_dir / "diarize.json").read_text())["data"]
        words = [
            {"word": w["word"], "start": w["start"] - edit.start, "end": w["end"] - edit.start}
            for seg in diarize["segments"]
            for w in seg.get("words", [])
            if edit.start <= w["start"] < edit.end
        ]
        settings = config.Settings.from_json(json.loads(job.settings_json))
        try:
            provider = providers_mod.profile_from_snapshot(settings.provider_snapshot())
            suggestions = visuals.suggest(job_dir, words, provider, prefer=args.prefer)
        except Exception as err:  # noqa: BLE001 — surface, don't crash the app
            print(json.dumps({"ok": False, "error": str(err)}))
            return 1
        edits = store.load(job_dir)
        current = edits.get(str(args.clip), edit)
        known = {o.id for o in current.overlays}
        current.overlays.extend(o for o in suggestions if o.id not in known)
        edits[str(args.clip)] = current
        store.save(job_dir, edits)
        print(json.dumps({"ok": True, "edit": current.to_json()}))
        return 0

    if args.edit_cmd == "render-clip":
        emit = _progress_printer(args.jsonl)
        try:
            entry = rc.render_clip_edit(job_dir, args.clip, lambda f, m: emit("render", f, m))
        except Exception as err:  # noqa: BLE001
            _emit_result(args.jsonl, {"ok": False, "error": str(err)})
            return 1
        _emit_result(args.jsonl, {"ok": True, "output": entry})
        return 0
    return 2


def cmd_ig(args: argparse.Namespace) -> int:
    from .insights import calibration, instagram

    if args.ig_cmd == "connect":
        app_secret = args.app_secret
        if args.app_secret_stdin:
            app_secret = sys.stdin.read().strip()
        if not app_secret:
            print("Meta app secret is required.", file=sys.stderr)
            return 2
        conn = instagram.connect(args.app_id, app_secret)
        print(f"Connected as @{conn['username']} (user {conn['user_id']}).")
        return 0

    # App-facing commands: exactly one JSON line on stdout (the shell's
    # ig_tool parses the last JSON line, same contract as edit_tool).
    if args.ig_cmd == "sync":
        summary = calibration.sync()
        print(json.dumps(summary))
        return 0 if summary.get("ok") else 1

    if args.ig_cmd == "overview":
        print(json.dumps(calibration.overview()))
        return 0

    if args.ig_cmd == "link":
        job = queue.get_job(args.job_id)
        if job is None:
            print(json.dumps({"ok": False, "error": f"no job {args.job_id}"}))
            return 2
        score_data = queue.read_checkpoint(job, "score", 1)
        if not score_data:
            print(json.dumps({"ok": False, "error": "job has no score checkpoint"}))
            return 2
        clips = score_data["clips"]
        if not 0 <= args.clip < len(clips):
            print(json.dumps({"ok": False, "error": f"clip index out of range (0..{len(clips) - 1})"}))
            return 2
        calibration.link_clip(
            args.job_id, args.clip, args.media_id, clips[args.clip],
            link_source=args.source,
            config_version=score_data.get("scoring_config_version", 1),
        )
        print(json.dumps({"ok": True, "linked": {"job_id": args.job_id, "clip": args.clip, "media_id": args.media_id}}))
        return 0

    if args.ig_cmd == "unlink":
        removed = calibration.unlink(args.media_id)
        print(json.dumps({"ok": True, "removed": removed}))
        return 0

    if args.ig_cmd == "reject":
        calibration.reject_match(args.media_id, args.job_id, args.clip)
        print(json.dumps({"ok": True}))
        return 0

    # Human/legacy commands.
    conn = instagram.load_connection()
    if args.ig_cmd in ("media", "pull") and conn is None:
        print("Not connected. Run: clipgauge ig connect --app-id ... --app-secret ...", file=sys.stderr)
        return 2
    if conn is not None:
        conn = instagram.refresh_if_needed(conn)

    if args.ig_cmd == "media":
        for m in instagram.recent_media(conn):
            if m.get("media_product_type") == "REELS" or m.get("media_type") == "VIDEO":
                caption = (m.get("caption") or "")[:60].replace("\n", " ")
                print(f"{m['id']}  {m.get('timestamp', '')[:10]}  {caption}")
        return 0

    if args.ig_cmd == "pull":
        rows = calibration.tracked()
        if not rows:
            print("No linked clips yet. Post an exported clip, then: clipgauge ig link ...")
            return 0
        for row in rows:
            if not row["ig_media_id"]:
                continue
            try:
                metrics = instagram.media_insights(conn, row["ig_media_id"])
            except instagram.IgError as err:
                print(f"{row['ig_media_id']}: {err}", file=sys.stderr)
                continue
            calibration.store_metrics(row["ig_media_id"], metrics)
            views = metrics.get("views")
            watch = metrics.get("ig_reels_avg_watch_time")
            print(
                f"{row['ig_media_id']}  score {row['score']:.0f} → views {views}, "
                f"avg watch {round(watch / 1000, 1) if watch else '?'}s"
            )
        return 0

    if args.ig_cmd == "report":
        print(json.dumps(calibration.report(args.metric), indent=2))
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clipgauge")
    parser.add_argument("--version", "-V", action="version", version=f"ClipGauge {__version__}")
    parser.add_argument("--jsonl", action="store_true", help="machine-readable progress on stdout")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_preflight = sub.add_parser("preflight", help="check local runtime readiness")
    p_preflight.add_argument("--llm", choices=["gemini", "ollama"], default=None, help=argparse.SUPPRESS)
    p_preflight.add_argument("--provider", default=None, help="provider preset or custom kind")
    p_preflight.add_argument("--model", default=None, help="provider model identifier")
    p_preflight.add_argument("--endpoint", default=None, help="custom provider base URL")
    p_preflight.add_argument("--auth", choices=["none", "bearer", "api_key_header", "custom_secret_header"], default=None)
    p_preflight.add_argument("--secret-header", default=None, help=argparse.SUPPRESS)
    p_preflight.set_defaults(fn=cmd_preflight)

    p_setup = sub.add_parser("setup", help="inspect or install managed local-AI assets")
    setup_sub = p_setup.add_subparsers(dest="setup_cmd", required=True)
    setup_sub.add_parser("inventory", help="show verified runtime/model inventory")
    setup_sub.add_parser("install-runtime", help="download and install the verified llama.cpp runtime")
    p_download_model = setup_sub.add_parser("download-model", help="download a verified local model")
    p_download_model.add_argument("model_id", choices=sorted(local_runtime.MODEL_CATALOG))
    p_setup.set_defaults(fn=cmd_setup)

    p_test = sub.add_parser("provider-test", help="test a configured provider connection")
    p_test.add_argument("--llm", choices=["gemini", "ollama"], default=None, help=argparse.SUPPRESS)
    p_test.add_argument("--provider", default=None, help="provider preset or custom kind")
    p_test.add_argument("--model", default=None, help="provider model identifier")
    p_test.add_argument("--endpoint", default=None, help="custom provider base URL")
    p_test.add_argument("--auth", choices=["none", "bearer", "api_key_header", "custom_secret_header"], default=None)
    p_test.add_argument("--secret-header", default=None, help=argparse.SUPPRESS)
    p_test.add_argument("--vision-smoke", action="store_true", help=argparse.SUPPRESS)
    p_test.set_defaults(fn=cmd_provider_test)

    p_run = sub.add_parser("run", help="process a YouTube URL or local video file")
    p_run.add_argument("source")
    p_run.add_argument("--llm", choices=["gemini", "ollama"], default=None, help=argparse.SUPPRESS)
    p_run.add_argument("--provider", default=None, help="provider preset or custom kind")
    p_run.add_argument("--model", default=None, help="provider model identifier")
    p_run.add_argument("--endpoint", default=None, help="custom provider base URL")
    p_run.add_argument("--auth", choices=["none", "bearer", "api_key_header", "custom_secret_header"], default=None)
    p_run.add_argument("--secret-header", default=None, help=argparse.SUPPRESS)
    p_run.add_argument("--captions", default=None, help="caption preset name")
    p_run.add_argument("--camera", choices=["cut", "pan", "locked"], default=None)
    p_run.set_defaults(fn=cmd_run)

    p_resume = sub.add_parser("resume", help="resume a job from its checkpoints")
    p_resume.add_argument("job_id")
    p_resume.add_argument("--llm", choices=["gemini", "ollama"], default=None, help=argparse.SUPPRESS)
    p_resume.add_argument("--provider", default=None, help="provider preset or custom kind")
    p_resume.add_argument("--model", default=None, help="provider model identifier")
    p_resume.add_argument("--endpoint", default=None, help="custom provider base URL")
    p_resume.add_argument("--auth", choices=["none", "bearer", "api_key_header", "custom_secret_header"], default=None)
    p_resume.add_argument("--secret-header", default=None, help=argparse.SUPPRESS)
    p_resume.add_argument("--captions", default=None, help="caption preset name")
    p_resume.add_argument("--camera", choices=["cut", "pan", "locked"], default=None)
    p_resume.set_defaults(fn=cmd_resume)

    p_jobs = sub.add_parser("jobs", help="list jobs")
    p_jobs.set_defaults(fn=cmd_jobs)

    p_edit = sub.add_parser("edit", help="per-clip editing (context / visuals / render)")
    edit_sub = p_edit.add_subparsers(dest="edit_cmd", required=True)
    p_ctx = edit_sub.add_parser("context")
    p_ctx.add_argument("job_id")
    p_ctx.add_argument("clip", type=int)
    p_sv = edit_sub.add_parser("suggest-visuals")
    p_sv.add_argument("job_id")
    p_sv.add_argument("clip", type=int)
    p_sv.add_argument("--prefer", choices=["pexels", "gemini"], default="pexels")
    p_rcl = edit_sub.add_parser("render-clip")
    p_rcl.add_argument("job_id")
    p_rcl.add_argument("clip", type=int)
    p_edit.set_defaults(fn=cmd_edit)

    p_ig = sub.add_parser("ig", help="Instagram feedback loop (your own Meta app)")
    ig_sub = p_ig.add_subparsers(dest="ig_cmd", required=True)
    p_connect = ig_sub.add_parser("connect", help="OAuth against your own Meta app")
    p_connect.add_argument("--app-id", required=True)
    p_connect.add_argument("--app-secret", default=None, help="direct CLI use; desktop uses stdin")
    p_connect.add_argument("--app-secret-stdin", action="store_true", help=argparse.SUPPRESS)
    ig_sub.add_parser("sync", help="one sync pass: media + thumbnails + insights ladder + auto-fit (JSON)")
    ig_sub.add_parser("overview", help="everything the Loop screen renders (JSON)")
    ig_sub.add_parser("media", help="list your recent Reels to link against")
    p_link = ig_sub.add_parser("link", help="link a rendered clip to a posted Reel (JSON)")
    p_link.add_argument("job_id")
    p_link.add_argument("clip", type=int)
    p_link.add_argument("media_id")
    p_link.add_argument("--source", default="manual", choices=["manual", "match_confirmed"])
    p_unlink = ig_sub.add_parser("unlink", help="remove a clip↔Reel link (JSON)")
    p_unlink.add_argument("media_id")
    p_reject = ig_sub.add_parser("reject", help="'not this' — never suggest this pair again (JSON)")
    p_reject.add_argument("media_id")
    p_reject.add_argument("job_id")
    p_reject.add_argument("clip", type=int)
    ig_sub.add_parser("pull", help="fetch metrics for every linked clip")
    p_report = ig_sub.add_parser("report", help="score-vs-outcome calibration report")
    p_report.add_argument("--metric", default="views")
    p_ig.set_defaults(fn=cmd_ig)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
