"""Ingest stage: URL or file → job-dir media + analysis audio + heatmap.

Artifacts produced in the job dir:
    media.mp4      (URL jobs; file jobs keep the source path unless normalized)
    audio16k.wav   16 kHz mono analysis audio (shared by all M1 models)
    heatmap in the checkpoint data (YouTube most-replayed, when available)
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from ..jobs.queue import Stage, StageContext, StageError
from . import normalize, ytdlp


def _sample_hash(path: Path) -> str:
    """Cheap staleness fingerprint for external source files: size + first MiB."""
    h = hashlib.sha256()
    h.update(str(path.stat().st_size).encode())
    with open(path, "rb") as fh:
        h.update(fh.read(1024 * 1024))
    return h.hexdigest()[:16]


class IngestStage(Stage):
    name = "ingest"
    schema_version = 1

    def artifacts_ok(self, ctx: StageContext, data: dict) -> bool:
        media = Path(data.get("media_path", ""))
        audio = ctx.job_dir / "audio16k.wav"
        if not (media.exists() and audio.exists()):
            return False
        if data.get("source_hash"):
            try:
                return _sample_hash(media) == data["source_hash"] or media.parent == ctx.job_dir
            except OSError:
                return False
        return True

    def run(self, ctx: StageContext) -> dict:
        job = ctx.job

        def prog(fraction: float, message: str) -> None:
            ctx.emit(fraction, message)

        heatmap = None
        title = None
        if job.source_type == "url":
            try:
                meta = ytdlp.fetch_meta(job.source, prog)
                heatmap = meta.heatmap
                title = meta.title
                media_path = ctx.job_dir / "media.mp4"
                if not media_path.exists():
                    ytdlp.download(job.source, media_path, prog)
            except ytdlp.YtDlpError as err:
                message = str(err)
                code = getattr(err, "code", None) or ("YTDLP_LOGIN_REQUIRED" if ytdlp.is_auth_error(message) else "YTDLP_METADATA_FAILED")
                if code == "YTDLP_ERROR" and ("download" in message.lower() or "connection" in message.lower()):
                    code = "YTDLP_DOWNLOAD_FAILED"
                raise StageError(
                    f"yt-dlp could not process this video: {message}",
                    code=code,
                    retryable=getattr(err, "retryable", True),
                ) from err
        else:
            source_path = Path(job.source).expanduser().resolve()
            if not source_path.exists():
                raise StageError(
                    f"File not found: {source_path}",
                    code="INPUT_FILE_NOT_FOUND",
                    retryable=False,
                )
            if not source_path.is_file():
                raise StageError(
                    f"Input is not a file: {source_path}",
                    code="INPUT_FILE_INVALID",
                    retryable=False,
                )
            # Keep all desktop-readable media inside the Rust-managed asset
            # root. This also makes resume independent of an external path
            # being moved or revoked after the run starts.
            media_path = ctx.job_dir / "media.mp4"
            if not media_path.exists():
                try:
                    shutil.copyfile(source_path, media_path)
                except OSError as err:
                    raise StageError(
                        f"Could not copy the source video into the managed job folder: {err}",
                        code="INPUT_COPY_FAILED",
                        retryable=True,
                    ) from err
            title = source_path.stem

        prog(0.96, "Probing media…")
        try:
            info = normalize.probe(media_path)
        except normalize.FfmpegError as err:
            raise StageError(str(err)) from err
        if not info.has_audio:
            raise StageError(
                "This video has no audio track. ClipGauge needs speech to find moments."
            )

        if info.vfr:
            cfr_path = ctx.job_dir / "media_cfr.mp4"
            if not cfr_path.exists():
                normalize.normalize_to_cfr(media_path, cfr_path, info.fps, prog)
            media_path = cfr_path
            info = normalize.probe(media_path)

        prog(0.98, "Extracting analysis audio…")
        audio_path = ctx.job_dir / "audio16k.wav"
        if not audio_path.exists():
            normalize.extract_analysis_audio(media_path, audio_path)

        from ..jobs import queue as jobs_queue

        jobs_queue.set_job_status(job.id, "running", title=title)

        source_hash = None
        if job.source_type == "file":
            source_hash = _sample_hash(media_path)

        return {
            "media_path": str(media_path),
            "audio_path": str(audio_path),
            "title": title,
            "probe": info.to_json(),
            "heatmap": heatmap,
            "source_hash": source_hash,
        }
