"""Storage accounting and confirmation-gated cleanup."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import os
from pathlib import Path

CATEGORIES = (
    ("components", "Components"),
    ("local-ai", "Local AI"),
    ("sessions", "Sessions/source"),
    ("rendered", "Rendered"),
    ("download-cache", "Download cache"),
    ("temp-partial", "Temp/partial"),
    ("diagnostics", "Diagnostics"),
)

_JOB_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")
_TEMP_SUFFIXES = (".part", ".tmp")
_TARGETS = {"session", "failed-session", "safe-cache", "obsolete-runtime-archives"}
_SIGNATURE_PATHS = ("models", "runtimes", "jobs", "downloads", "temp", "diagnostics", "bin")


def _size(path: Path) -> int:
    if path.is_symlink():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    if not path.is_dir():
        return 0
    total = 0
    try:
        children = list(path.iterdir())
    except OSError:
        return 0
    for child in children:
        total += _size(child)
    return total


def _scan(path: Path, *, in_diagnostics: bool = False) -> tuple[int, int, int, int]:
    """Return total, rendered, partial, and diagnostic bytes in one walk."""
    if path.is_symlink():
        return 0, 0, 0, 0
    try:
        if path.is_file():
            size = path.stat().st_size
            partial = size if path.name.endswith(_TEMP_SUFFIXES) or ".staging" in path.name else 0
            rendered = size if path.parent.name in {"outputs", "rendered"} else 0
            diagnostics = size if in_diagnostics else 0
            return size, rendered, partial, diagnostics
        if not path.is_dir():
            return 0, 0, 0, 0
        total = rendered = partial = diagnostics = 0
        with os.scandir(path) as entries:
            for entry in entries:
                child_total, child_rendered, child_partial, child_diagnostics = _scan(
                    Path(entry.path),
                    in_diagnostics=in_diagnostics or entry.name == "diagnostics",
                )
                total += child_total
                rendered += child_rendered
                partial += child_partial
                diagnostics += child_diagnostics
        return total, rendered, partial, diagnostics
    except OSError:
        return 0, 0, 0, 0


def breakdown(root: Path) -> list[dict[str, object]]:
    """Return bounded, non-destructive category totals."""
    root = root.resolve()
    paths = {
        "components": [root / "models" / "asr", root / "models" / "torch", root / "runtimes" / "ffmpeg", root / "runtimes" / "yt-dlp", root / "runtimes" / "youtube", root / "bin"],
        "local-ai": [root / "models" / "clipgauge-local", root / "runtimes" / "llama-server"],
        "sessions": [root / "jobs"],
        "rendered": [],
        "download-cache": [root / "downloads"],
        "temp-partial": [],
        "diagnostics": [root / "diagnostics"],
    }
    jobs = root / "jobs"
    jobs_total, rendered, jobs_partial, jobs_diagnostics = _scan(jobs)
    downloads_total, _, downloads_partial, _ = _scan(root / "downloads")
    _, _, temp_partial, _ = _scan(root / "temp")
    diagnostics_total, _, _, diagnostics_nested = _scan(root / "diagnostics", in_diagnostics=True)
    components_total = sum(_scan(path)[0] for path in paths["components"])
    local_ai_total = sum(_scan(path)[0] for path in paths["local-ai"])
    values = {
        "components": components_total,
        "local-ai": local_ai_total,
        "sessions": jobs_total,
        "download-cache": downloads_total,
        "diagnostics": diagnostics_total + jobs_diagnostics,
        "rendered": rendered,
        "temp-partial": jobs_partial + downloads_partial + temp_partial,
    }
    rows = []
    for category_id, display_name in CATEGORIES:
        total = values.get(category_id, sum(_size(path) for path in paths[category_id]))
        rows.append({
            "category": category_id,
            "display_name": display_name,
            "bytes": int(total),
            "deletable": category_id in {"download-cache", "temp-partial"},
            "requires_confirmation": True,
        })
    return rows


def breakdown_signature(root: Path) -> str:
    """Return a cheap signature for cached storage accounting."""
    root = root.resolve()
    facts = []
    for name in _SIGNATURE_PATHS:
        path = root / name
        try:
            stat = path.stat()
            facts.append((name, True, stat.st_mtime_ns, stat.st_size, stat.st_ino))
        except OSError:
            facts.append((name, False, 0, 0, 0))
    return hashlib.sha256(json.dumps(facts, sort_keys=True).encode("utf-8")).hexdigest()


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _safe_files(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for base in (root / "downloads", root / "temp"):
        if not base.is_dir() or base.is_symlink():
            continue
        for path in base.rglob("*"):
            if path.is_file() and not path.is_symlink() and (
                path.name.endswith(_TEMP_SUFFIXES) or ".staging" in path.name
            ):
                candidates.append(path)
    return candidates


def _runtime_archives(root: Path) -> list[Path]:
    downloads = root / "downloads"
    if not downloads.is_dir() or downloads.is_symlink():
        return []
    installed_roots = (
        root / "runtimes" / "llama-server",
        root / "runtimes" / "ffmpeg",
        root / "runtimes" / "youtube",
    )
    if not any(path.is_dir() and not path.is_symlink() for path in installed_roots):
        return []
    prefixes = ("llama-server-", "ffmpeg-", "node-", "bgutil-")
    return [
        path for path in downloads.iterdir()
        if path.is_file() and not path.is_symlink() and path.name.startswith(prefixes)
    ]


def _job_status(root: Path, job_id: str) -> str | None:
    database = root / "db.sqlite3"
    if not database.is_file() or database.is_symlink():
        return None
    try:
        with sqlite3.connect(database) as connection:
            row = connection.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    except sqlite3.Error:
        return None
    return str(row[0]) if row else None


def _job_path(root: Path, job_id: str) -> Path:
    if not _JOB_ID.fullmatch(job_id):
        raise ValueError("invalid job identifier")
    jobs = (root / "jobs").resolve()
    raw_candidate = jobs / job_id
    if raw_candidate.is_symlink():
        raise ValueError("job is unavailable")
    candidate = raw_candidate.resolve()
    if not candidate.is_dir() or not candidate.is_relative_to(jobs):
        raise ValueError("job is unavailable")
    return candidate


def _candidates(root: Path, target: str, job_id: str | None) -> list[Path]:
    if target not in _TARGETS:
        raise ValueError("unsupported cleanup target")
    if target in {"session", "failed-session"}:
        if not job_id:
            raise ValueError("a job identifier is required")
        status = _job_status(root, job_id)
        if status is None:
            raise ValueError("job is unavailable")
        if status == "running":
            raise ValueError("running sessions cannot be deleted")
        if target == "failed-session" and status != "failed":
            raise ValueError("the selected session is not failed")
        return [_job_path(root, job_id)]
    return _safe_files(root) if target == "safe-cache" else _runtime_archives(root)


def preview(root: Path, target: str, job_id: str | None = None) -> dict[str, object]:
    """Describe exact cleanup candidates without changing the filesystem."""
    root = root.resolve()
    paths = _candidates(root, target, job_id)
    return {
        "target": target,
        "job_id": job_id,
        "requires_confirmation": True,
        "bytes": sum(_size(path) for path in paths),
        "paths": [_relative(root, path) for path in paths],
    }


def cleanup(root: Path, target: str, job_id: str | None = None, *, confirmed: bool = False) -> dict[str, object]:
    """Delete only allow-listed candidates after explicit confirmation."""
    if not confirmed:
        raise ValueError("explicit confirmation is required")
    root = root.resolve()
    paths = _candidates(root, target, job_id)
    removed = [_relative(root, path) for path in paths]
    removed_bytes = sum(_size(path) for path in paths)
    for path in paths:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file() and not path.is_symlink():
            path.unlink()
    if target in {"session", "failed-session"} and job_id:
        database = root / "db.sqlite3"
        with sqlite3.connect(database) as connection:
            connection.execute("DELETE FROM stage_runs WHERE job_id = ?", (job_id,))
            connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            connection.commit()
    return {"target": target, "job_id": job_id, "removed": removed, "bytes": removed_bytes}
