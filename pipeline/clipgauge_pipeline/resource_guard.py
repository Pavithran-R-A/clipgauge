"""Typed resource checks for long-running pipeline work."""

from __future__ import annotations

from dataclasses import dataclass
import shutil
from pathlib import Path

from . import storage_estimate

GIB = 1024**3
GPU_ASR_HEADROOM_BYTES = 6 * GIB
CPU_ASR_HEADROOM_BYTES = 3 * GIB


@dataclass(frozen=True)
class HeadroomDecision:
    blocked: bool
    code: str | None
    message: str
    required_bytes: int
    available_bytes: int | None
    available_ram_bytes: int | None
    available_commit_bytes: int | None
    selected_device: str

    def to_dict(self) -> dict[str, object]:
        return {
            "blocked": self.blocked,
            "code": self.code,
            "message": self.message,
            "required_bytes": self.required_bytes,
            "available_bytes": self.available_bytes,
            "available_ram_bytes": self.available_ram_bytes,
            "available_commit_bytes": self.available_commit_bytes,
            "selected_device": self.selected_device,
        }


def _positive_int(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number >= 0 else None


def asr_headroom_decision(capabilities: dict, *, selected_device: str) -> HeadroomDecision:
    """Block ASR before model load when commit headroom is unsafe."""
    ram = _positive_int(capabilities.get("available_ram_bytes"))
    commit = _positive_int(capabilities.get("available_page_file_bytes"))
    values = [value for value in (ram, commit) if value is not None]
    available = min(values) if values else None
    required = GPU_ASR_HEADROOM_BYTES if selected_device == "cuda" else CPU_ASR_HEADROOM_BYTES
    blocked = available is not None and available < required
    if blocked:
        message = (
            f"Speech recognition needs approximately {required / GIB:.1f} GiB headroom; "
            f"only {available / GIB:.1f} GiB is available. Close applications or use Low-memory mode."
        )
    else:
        message = "ASR memory and commit headroom passed."
    return HeadroomDecision(
        blocked=blocked,
        code="ASR_RESOURCE_HEADROOM_LOW" if blocked else None,
        message=message,
        required_bytes=required,
        available_bytes=available,
        available_ram_bytes=ram,
        available_commit_bytes=commit,
        selected_device=selected_device,
    )


@dataclass(frozen=True)
class AbruptExitClassification:
    code: str
    exit_code_decimal: int | None
    exit_code_hex: str | None
    allow_cpu_resume: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "exit_code_decimal": self.exit_code_decimal,
            "exit_code_hex": self.exit_code_hex,
            "allow_cpu_resume": self.allow_cpu_resume,
            "reason": self.reason,
        }


def classify_abrupt_exit(
    *,
    stage: str | None,
    accelerator: str | None,
    stderr: str,
    raw_exit_status: int | None,
) -> AbruptExitClassification:
    """Classify process exits without guessing unknown causes."""
    normalized = stderr.lower()
    is_asr = str(stage or "").lower() == "asr"
    is_cuda = "cuda" in f"{accelerator or ''} {stderr}".lower()
    is_resource = any(term in normalized for term in (
        "memory allocation", "out of memory", "out-of-memory", "cannot allocate",
        "bad alloc", "resource exhausted", "commit limit", "disk full",
    ))
    if raw_exit_status is not None:
        unsigned = int(raw_exit_status) & 0xFFFFFFFF
        exit_hex = f"0x{unsigned:08X}"
    else:
        unsigned = None
        exit_hex = None
    if unsigned == 0xC0000005:
        code = "WINDOWS_ACCESS_VIOLATION"
        reason = "Windows reported an access violation."
    elif is_resource:
        code = "PIPELINE_RESOURCE_EXHAUSTED"
        reason = "The process reported a resource allocation failure."
    elif is_asr and is_cuda:
        code = "CUDA_NATIVE_CRASH"
        reason = "CUDA-backed ASR stopped without a terminal event."
    elif is_asr:
        code = "ASR_NATIVE_CRASH"
        reason = "ASR stopped without a terminal event."
    else:
        code = "PIPELINE_NATIVE_CRASH"
        reason = "The pipeline stopped without a terminal event."
    return AbruptExitClassification(
        code=code,
        exit_code_decimal=unsigned,
        exit_code_hex=exit_hex,
        allow_cpu_resume=is_asr and is_cuda and not is_resource,
        reason=reason,
    )


@dataclass(frozen=True)
class DiskDecision:
    blocked: bool
    code: str | None
    message: str
    required_bytes: int
    available_bytes: int | None
    source_size_confidence: str

    def to_dict(self) -> dict[str, object]:
        return {
            "blocked": self.blocked,
            "code": self.code,
            "message": self.message,
            "required_bytes": self.required_bytes,
            "available_bytes": self.available_bytes,
            "source_size_confidence": self.source_size_confidence,
        }


def disk_headroom_decision(
    source: str | None,
    *,
    data_root: Path,
    estimate: dict[str, object] | None = None,
    score_only: bool = False,
) -> DiskDecision:
    """Recheck disk space before transfer, ASR, and rendering."""
    try:
        available = int(shutil.disk_usage(data_root).free)
    except (OSError, AttributeError, TypeError, ValueError):
        return DiskDecision(False, None, "Free disk space could not be measured.", 0, None, "unknown")
    if score_only:
        chosen = storage_estimate.for_cached_score()
        confidence = "cached-score"
    elif estimate is not None:
        chosen = estimate
        confidence = str(estimate.get("source_size_confidence") or "known")
    elif source and not str(source).lower().startswith(("http://", "https://")):
        try:
            source_bytes = max(0, Path(source).stat().st_size)
        except OSError:
            source_bytes = 0
        chosen = storage_estimate.for_source(source_bytes)
        confidence = "local-file"
    else:
        chosen = storage_estimate.for_url_metadata(None)
        confidence = str(chosen.get("source_size_confidence") or "duration-fallback")
    minimum = storage_estimate.CACHED_SCORE_MIN_SAFE_BYTES if score_only else storage_estimate.MIN_SAFE_BYTES
    required = max(minimum, int(chosen.get("required_bytes") or 0))
    blocked = available < required
    if blocked:
        message = (
            f"This run needs approximately {required / GIB:.1f} GiB; "
            f"only {available / GIB:.1f} GiB is free. Free disk space, then retry from Setup & Storage."
        )
    else:
        message = "Disk headroom passed for this stage."
    return DiskDecision(blocked, "DISK_SPACE_LOW" if blocked else None, message, required, available, confidence)
