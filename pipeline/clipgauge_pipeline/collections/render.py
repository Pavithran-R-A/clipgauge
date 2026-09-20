"""Safe, on-demand collection MP4 compilation."""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

from ..render import ffmpeg_bin
from ..ingest import normalize
from ..enrich.stage import stable_clip_id
from .model import safe_name
from .service import list_collections


def _clip_paths(job, clips: list[dict], clip_ids: list[str]) -> list[Path]:
    mapping = {stable_clip_id(clip, index): clip for index, clip in enumerate(clips)}
    paths: list[Path] = []
    for identifier in clip_ids:
        clip = mapping.get(identifier)
        if not clip:
            raise ValueError("collection references an unknown clip")
        raw = clip.get("render_path") or clip.get("path")
        if not raw:
            raise ValueError(f"collection clip {identifier} has no rendered output")
        root = job.dir.resolve()
        raw_path = Path(str(raw))
        candidate = (root / raw_path if not raw_path.is_absolute() else raw_path).resolve()
        if root not in candidate.parents or not candidate.is_file():
            raise ValueError("collection clip is outside the managed job directory")
        paths.append(candidate)
    return paths


def render_collection(job, identifier: str, clips: list[dict]) -> Path:
    collection = next((item for item in list_collections(job, clips) if item["id"] == identifier), None)
    if collection is None:
        raise ValueError("collection not found")
    paths = _clip_paths(job, clips, collection["clip_ids"])
    if not paths:
        raise ValueError("collection has no clips")
    output_dir = job.dir / "collections"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{safe_name(collection['title'])}.mp4"
    list_path = output_dir / f".{safe_name(collection['title'])}.{uuid.uuid4().hex}.txt"
    concat_lines = []
    for path in paths:
        escaped = path.as_posix().replace("'", "'\\''")
        concat_lines.append(f"file '{escaped}'\n")
    list_path.write_text("".join(concat_lines), encoding="utf-8")
    temporary = output_dir / f".{target.name}.{uuid.uuid4().hex}.tmp.mp4"
    try:
        command = [ffmpeg_bin.ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", "-movflags", "+faststart", str(temporary)]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=3600)
        if completed.returncode != 0:
            command = [ffmpeg_bin.ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", str(temporary)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=3600)
        if completed.returncode != 0 or not temporary.is_file():
            raise ValueError("FFmpeg could not compile the collection")
        probe = normalize.probe(temporary)
        if not probe.has_audio or probe.duration_sec <= 0:
            raise ValueError("compiled collection has no verified audio/video duration")
        temporary.replace(target)
        return target
    finally:
        list_path.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
