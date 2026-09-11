"""Per-clip edit state, persisted as <job_dir>/clip_edits.json.

The app writes this file directly (Rust fs) and the pipeline reads it at
render-clip time — artifacts-are-truth, same as every checkpoint. Defaults
for a clip that has never been edited come from the score checkpoint."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .timeline import ClipEdit


def path_for(job_dir: Path) -> Path:
    return job_dir / "clip_edits.json"


def load(job_dir: Path) -> dict[str, ClipEdit]:
    p = path_for(job_dir)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    edits: dict[str, ClipEdit] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        try:
            edits[key] = ClipEdit.from_json(value)
        except (KeyError, TypeError, ValueError):
            continue
    return edits


def save(job_dir: Path, edits: dict[str, ClipEdit]) -> None:
    path = path_for(job_dir)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps({k: e.to_json() for k, e in edits.items()}, indent=1))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _migrate_overlays(edit: ClipEdit) -> ClipEdit:
    """Overlays still sitting on RETIRED defaults get moved to the
    face-safe band; user-customized values are untouched."""
    for o in edit.overlays:
        if abs(o.y - 0.28) < 0.02 or abs(o.y - 0.10) < 0.02:
            o.y = 0.04
        if abs(o.scale - 0.62) < 0.02 or abs(o.scale - 0.42) < 0.02:
            o.scale = 0.38
    return edit


def edit_for_clip(job_dir: Path, clip_idx: int, score_clip: dict) -> ClipEdit:
    """The stored edit, or defaults derived from the run."""
    edits = load(job_dir)
    if str(clip_idx) in edits:
        return _migrate_overlays(edits[str(clip_idx)])
    return ClipEdit(start=float(score_clip["start"]), end=float(score_clip["end"]))
