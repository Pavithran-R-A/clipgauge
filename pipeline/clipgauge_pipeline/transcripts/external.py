"""External subtitle acceptance and managed artifact copying."""

from __future__ import annotations

import shutil
from pathlib import Path

from .. import protocol
from ..ingest import manifest
from .formats import MAX_SUBTITLE_BYTES, SubtitleParseError, parse_srt, parse_vtt
from .timing import cues_to_transcript


class SubtitleError(ValueError):
    def __init__(self, code: str, message: str, *, malformed_cues: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.malformed_cues = malformed_cues


def _read_text(source: Path) -> str:
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise SubtitleError("SUBTITLE_READ_FAILED", f"Could not read subtitle file: {protocol.safe_message(str(exc))}") from exc
    if len(raw) > MAX_SUBTITLE_BYTES:
        raise SubtitleError("SUBTITLE_TOO_LARGE", "Subtitle file exceeds the 10 MiB limit.")
    if b"\x00" in raw:
        raise SubtitleError("SUBTITLE_BINARY", "Subtitle file is not valid text.")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SubtitleError("SUBTITLE_ENCODING_INVALID", "Subtitle file must use UTF-8 text.") from exc


def accept_external_subtitle(job, input_manifest: dict, *, duration: float) -> tuple[dict, dict]:
    subtitle = dict(input_manifest.get("subtitle") or {})
    requested = subtitle.get("requested_path")
    artifact = subtitle.get("artifact_path")
    if artifact:
        source = (job.dir / str(artifact)).resolve()
        if not source.is_file() or job.dir.resolve() not in source.parents:
            raise SubtitleError("SUBTITLE_ARTIFACT_INVALID", "Managed subtitle artifact is unavailable.")
    elif requested:
        source = Path(str(requested)).expanduser().resolve()
        if not source.is_file():
            raise SubtitleError("SUBTITLE_FILE_NOT_FOUND", "The selected subtitle file was not found.")
        target_dir = job.dir / "subtitles"
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower()
        if suffix not in {".srt", ".vtt"}:
            raise SubtitleError("SUBTITLE_FORMAT_UNSUPPORTED", "Choose an SRT or WebVTT subtitle file.")
        target = target_dir / f"source{suffix}"
        try:
            shutil.copyfile(source, target)
        except OSError as exc:
            raise SubtitleError("SUBTITLE_COPY_FAILED", f"Could not copy subtitle into the job: {protocol.safe_message(str(exc))}") from exc
        source = target
        subtitle["artifact_path"] = str(target.relative_to(job.dir))
    else:
        raise SubtitleError("SUBTITLE_PATH_MISSING", "Subtitle mode requires a subtitle file.")

    # The original picker path is never a managed artifact. Clear it after
    # acceptance so checkpoint validation cannot persist an external path.
    subtitle["requested_path"] = None

    text = _read_text(source)
    try:
        if source.suffix.lower() == ".srt":
            cues, malformed = parse_srt(text, duration)
            subtitle_format = "srt"
        elif source.suffix.lower() == ".vtt":
            cues, malformed = parse_vtt(text, duration)
            subtitle_format = "vtt"
        else:
            raise SubtitleParseError("unsupported subtitle format")
    except SubtitleParseError as exc:
        raise SubtitleError("SUBTITLE_INVALID", str(exc), malformed_cues=getattr(exc, "malformed_cues", 0)) from exc

    digest = manifest.sha256_file(source)
    subtitle.update({
        "mode": "platform" if subtitle.get("source", "").startswith("platform_") else "external",
        "format": subtitle_format,
        "source": "external_subtitle",
        "sha256": digest,
        "automatic": bool(subtitle.get("automatic", False)),
        "malformed_cues": malformed,
    })
    transcript_source = "platform_caption" if subtitle["mode"] == "platform" else "external_subtitle"
    transcript = cues_to_transcript(cues, language=subtitle.get("language"), source=transcript_source, sha256=digest)
    return subtitle, transcript
