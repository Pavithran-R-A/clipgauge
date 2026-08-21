"""Verified runtime artifact acquisition primitives.

No caller may execute or install a downloaded file before ``download_verified``
returns.  Downloads are staged in a sibling ``.part`` file, bounded by
``max_bytes``, hashed, and atomically replaced only after identity validation.
Existing destinations remain untouched on all failures.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Callable, Iterable

import httpx

ProgressFn = Callable[[float, str], None]


class RuntimeIntegrityError(RuntimeError):
    """A downloaded runtime artifact failed an explicit integrity policy."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_size(current: int, content_length: str | None, max_bytes: int) -> int:
    try:
        announced = int(content_length or 0)
    except ValueError:
        announced = 0
    if announced and current + announced > max_bytes:
        raise RuntimeIntegrityError("runtime artifact exceeds the configured size limit")
    return announced


def download_verified(
    url: str,
    destination: Path,
    *,
    expected_sha256: str,
    max_bytes: int,
    timeout: float = 300.0,
    progress: ProgressFn | None = None,
    mode: int | None = None,
) -> Path:
    if not expected_sha256 or len(expected_sha256) != 64:
        raise RuntimeIntegrityError("a concrete SHA-256 is required for managed runtime artifacts")
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(f".{destination.name}.part")
    offset = part.stat().st_size if part.exists() else 0
    if offset > max_bytes:
        part.unlink(missing_ok=True)
        offset = 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    try:
        with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=timeout) as response:
            if offset and response.status_code == 200:
                part.unlink(missing_ok=True)
                offset = 0
            elif response.status_code not in (200, 206):
                raise RuntimeIntegrityError(f"runtime download failed: HTTP {response.status_code}")
            announced = _safe_size(offset, response.headers.get("content-length"), max_bytes)
            total = offset + announced if announced else 0
            seen = offset
            with part.open("ab" if offset else "wb") as handle:
                for chunk in response.iter_bytes():
                    seen += len(chunk)
                    if seen > max_bytes:
                        raise RuntimeIntegrityError("runtime artifact exceeded the configured size limit")
                    handle.write(chunk)
                    if progress and total:
                        progress(min(1.0, seen / total), "Downloading verified runtime artifact…")
                handle.flush()
                os.fsync(handle.fileno())
    except (httpx.HTTPError, OSError) as exc:
        raise RuntimeIntegrityError(f"runtime download interrupted: {exc}") from exc
    digest = sha256_file(part)
    if digest.lower() != expected_sha256.lower():
        part.unlink(missing_ok=True)
        raise RuntimeIntegrityError("runtime artifact SHA-256 mismatch; last-known-good copy preserved")
    if mode is not None:
        part.chmod(mode)
    os.replace(part, destination)
    return destination


def _validate_member(name: str, info: zipfile.ZipInfo, expected: set[str]) -> str:
    normalized = name.replace("\\", "/")
    if not normalized or normalized.endswith("/"):
        raise RuntimeIntegrityError("archive contains an unexpected directory entry")
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise RuntimeIntegrityError("archive contains an absolute or traversal member")
    mode = (info.external_attr >> 16) & 0o170000
    if mode == stat.S_IFLNK:
        raise RuntimeIntegrityError("archive contains an unexpected symlink entry")
    if normalized not in expected:
        raise RuntimeIntegrityError(f"archive contains an unexpected member: {normalized}")
    return normalized


def extract_zip_selected_verified(
    archive: Path,
    destination_dir: Path,
    *,
    expected_basenames: set[str],
    member_modes: dict[str, int] | None = None,
) -> list[Path]:
    """Validate every ZIP member, extracting only approved executable basenames."""
    if not expected_basenames:
        raise RuntimeIntegrityError("archive extraction requires an explicit executable allow-list")
    destination_dir.mkdir(parents=True, exist_ok=True)
    selected: dict[str, zipfile.ZipInfo] = {}
    try:
        with zipfile.ZipFile(archive) as handle:
            for info in handle.infolist():
                normalized = info.filename.replace("\\", "/")
                path = Path(normalized)
                if not normalized or normalized.endswith("/"):
                    continue
                if path.is_absolute() or ".." in path.parts:
                    raise RuntimeIntegrityError("archive contains an absolute or traversal member")
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise RuntimeIntegrityError("archive contains an unexpected symlink entry")
                basename = path.name
                if basename in expected_basenames:
                    if basename in selected:
                        raise RuntimeIntegrityError(f"archive contains duplicate executable: {basename}")
                    selected[basename] = info
            missing = expected_basenames - set(selected)
            if missing:
                raise RuntimeIntegrityError(f"archive is missing expected executables: {sorted(missing)}")
            outputs: list[Path] = []
            for basename, info in selected.items():
                output = destination_dir / basename
                part = output.with_name(f".{basename}.part")
                with handle.open(info) as source, part.open("wb") as target:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        target.write(chunk)
                    target.flush()
                    os.fsync(target.fileno())
                if member_modes and basename in member_modes:
                    part.chmod(member_modes[basename])
                os.replace(part, output)
                outputs.append(output)
            return outputs
    except (OSError, zipfile.BadZipFile) as exc:
        raise RuntimeIntegrityError(f"archive extraction failed: {exc}") from exc


def extract_archive_verified(
    archive: Path,
    destination_dir: Path,
    *,
    archive_type: str,
) -> list[Path]:
    """Safely extract every regular archive member into a staged directory."""
    staging = destination_dir.with_name(f".{destination_dir.name}.{int(time.time_ns())}.staging")
    staging.mkdir(parents=True, exist_ok=False)
    extracted: list[Path] = []

    def safe_member(name: str) -> Path:
        normalized = name.replace("\\\\", "/")
        path = Path(normalized)
        if not normalized or path.is_absolute() or ".." in path.parts:
            raise RuntimeIntegrityError("archive contains an absolute or traversal member")
        return path

    try:
        if archive_type == "zip":
            with zipfile.ZipFile(archive) as handle:
                members = handle.infolist()
                for info in members:
                    path = safe_member(info.filename)
                    mode = (info.external_attr >> 16) & 0o170000
                    if mode == stat.S_IFLNK:
                        raise RuntimeIntegrityError("archive contains an unexpected symlink entry")
                    if info.is_dir():
                        (staging / path).mkdir(parents=True, exist_ok=True)
                        continue
                    output = staging / path
                    output.parent.mkdir(parents=True, exist_ok=True)
                    with handle.open(info) as source, output.open("wb") as target:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            target.write(chunk)
                    extracted.append(output)
        elif archive_type in {"tar.gz", "tgz", "tar"}:
            mode = "r:gz" if archive_type in {"tar.gz", "tgz"} else "r:"
            with tarfile.open(archive, mode) as handle:
                for member in handle.getmembers():
                    path = safe_member(member.name)
                    if member.isdir():
                        (staging / path).mkdir(parents=True, exist_ok=True)
                        continue
                    if not member.isfile():
                        raise RuntimeIntegrityError("archive contains an unexpected non-file entry")
                    output = staging / path
                    output.parent.mkdir(parents=True, exist_ok=True)
                    source = handle.extractfile(member)
                    if source is None:
                        raise RuntimeIntegrityError("archive member could not be read")
                    with source, output.open("wb") as target:
                        for chunk in iter(lambda: source.read(1024 * 1024), b""):
                            target.write(chunk)
                    extracted.append(output)
        else:
            raise RuntimeIntegrityError(f"unsupported archive type: {archive_type}")
        destination_dir.parent.mkdir(parents=True, exist_ok=True)
        if destination_dir.exists():
            for path in sorted(destination_dir.rglob("*"), reverse=True):
                if path.is_file() or path.is_symlink():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
        else:
            destination_dir.mkdir(parents=True)
        final_paths: list[Path] = []
        for staged in extracted:
            final = destination_dir / staged.relative_to(staging)
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, final)
            final_paths.append(final)
        return final_paths
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise RuntimeIntegrityError(f"archive extraction failed: {exc}") from exc
    finally:
        if staging.exists():
            for path in sorted(staging.rglob("*"), reverse=True):
                if path.is_file() or path.is_symlink():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    path.rmdir()
            staging.rmdir()


def extract_zip_verified(
    archive: Path,
    destination_dir: Path,
    *,
    expected_members: Iterable[str],
    member_modes: dict[str, int] | None = None,
) -> list[Path]:
    expected = set(expected_members)
    if not expected:
        raise RuntimeIntegrityError("archive extraction requires an explicit member allow-list")
    staging = destination_dir.with_name(f".{destination_dir.name}.{int(time.time_ns())}.staging")
    staging.mkdir(parents=True, exist_ok=False)
    extracted: list[Path] = []
    try:
        with zipfile.ZipFile(archive) as handle:
            members = [_validate_member(info.filename, info, expected) for info in handle.infolist()]
            if set(members) != expected:
                raise RuntimeIntegrityError("archive does not contain exactly the expected members")
            for info, member in zip(handle.infolist(), members):
                output = staging / member
                output.parent.mkdir(parents=True, exist_ok=True)
                with handle.open(info) as source, output.open("wb") as target:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        target.write(chunk)
                    target.flush()
                    os.fsync(target.fileno())
                if member_modes and member in member_modes:
                    output.chmod(member_modes[member])
                extracted.append(output)
        destination_dir.parent.mkdir(parents=True, exist_ok=True)
        if destination_dir.exists():
            for path in destination_dir.iterdir():
                if path.is_file() or path.is_symlink():
                    path.unlink()
        else:
            destination_dir.mkdir(parents=True)
        final_paths: list[Path] = []
        for staged in extracted:
            final = destination_dir / staged.relative_to(staging)
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, final)
            final_paths.append(final)
        return final_paths
    except (OSError, zipfile.BadZipFile) as exc:
        raise RuntimeIntegrityError(f"archive extraction failed: {exc}") from exc
    finally:
        for path in sorted(staging.rglob("*"), reverse=True):
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                path.rmdir()
        staging.rmdir() if staging.exists() else None


def load_manifest(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeIntegrityError("runtime manifest is missing or malformed") from exc
    if not isinstance(payload, dict) or payload.get("manifest_version") != 1:
        raise RuntimeIntegrityError("runtime manifest version is unsupported")
    return payload
