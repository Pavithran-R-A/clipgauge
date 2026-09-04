"""Conservative hardware capability detection for setup, ASR, and local AI.

This module reports evidence that is useful for selection without claiming that a
GPU name alone guarantees that a backend or model will work. Every probe is
bounded, optional, and returns ``None`` when the capability cannot be verified.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _memory_bytes() -> int | None:
    if hasattr(os, "sysconf"):
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            if isinstance(pages, int) and isinstance(page_size, int) and pages > 0 and page_size > 0:
                return pages * page_size
        except (OSError, ValueError, TypeError):
            pass
    return None


def _run_probe(command: list[str], timeout: float = 2.0) -> str | None:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _nvidia() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"available": False, "verified": False, "gpus": []}
    output = _run_probe(
        [executable, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"]
    )
    if output is None:
        return {"available": True, "verified": False, "gpus": []}
    gpus: list[dict[str, str]] = []
    for line in output.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) == 3:
            gpus.append({"name": fields[0], "vram_mb": fields[1], "driver": fields[2]})
    return {"available": True, "verified": bool(gpus), "gpus": gpus}


def _cuda() -> dict[str, Any]:
    try:
        import ctranslate2  # type: ignore

        supported = sorted(ctranslate2.get_supported_compute_types("cuda"))
        device_count = int(ctranslate2.get_cuda_device_count())
        return {
            "available": True,
            "verified": device_count > 0 and bool(supported),
            "device_count": device_count,
            "compute_types": supported,
        }
    except (ImportError, RuntimeError, ValueError, AttributeError):
        return {"available": False, "verified": False, "device_count": 0, "compute_types": []}


def _vulkan() -> dict[str, Any]:
    executable = shutil.which("vulkaninfo")
    if not executable:
        return {"available": False, "verified": False}
    output = _run_probe([executable, "--summary"], timeout=3.0)
    return {"available": True, "verified": bool(output)}


def snapshot(data_root: Path | None = None) -> dict[str, Any]:
    """Return a JSON-serializable capability snapshot."""
    system = platform.system()
    machine = platform.machine()
    free_bytes = None
    if data_root is not None:
        try:
            free_bytes = shutil.disk_usage(data_root).free
        except OSError:
            free_bytes = None
    apple_silicon = system == "Darwin" and machine.lower() in {"arm64", "aarch64"}
    nvidia = _nvidia()
    cuda = _cuda()
    vulkan = _vulkan()
    return {
        "os": system,
        "architecture": machine,
        "cpu_logical_cores": os.cpu_count(),
        "ram_bytes": _memory_bytes(),
        "apple_silicon": apple_silicon,
        "nvidia": nvidia,
        "cuda_ctranslate2": cuda,
        "vulkan": vulkan,
        "disk_free_bytes": free_bytes,
        "detected_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


def select_asr_accelerator(capabilities: dict[str, Any]) -> tuple[str, str]:
    """Select only a backend with positive runtime evidence."""
    cuda = capabilities.get("cuda_ctranslate2") or {}
    device_count = cuda.get("device_count")
    has_device = device_count is None or int(device_count) > 0
    if cuda.get("verified") and has_device and cuda.get("compute_types"):
        compute_types = set(cuda["compute_types"])
        for candidate in ("float16", "int8_float16", "int8"):
            if candidate in compute_types:
                return "cuda", candidate
    return "cpu", "int8"


def asr_readiness(capabilities: dict[str, Any]) -> dict[str, Any]:
    """Return truthful ASR readiness without equating GPU detection to use."""
    cuda = capabilities.get("cuda_ctranslate2") or {}
    nvidia = capabilities.get("nvidia") or {}
    device, compute_type = select_asr_accelerator(capabilities)
    if device == "cuda":
        return {
            "state": "GPU ACCELERATED",
            "device": device,
            "compute_type": compute_type,
            "reason": "CUDA runtime and device probe succeeded.",
        }
    if nvidia.get("available") and nvidia.get("verified"):
        return {
            "state": "GPU PRESENT — RUNTIME DEGRADED",
            "device": "cpu",
            "compute_type": compute_type,
            "reason": "NVIDIA hardware is present, but CUDA speech execution is unverified.",
        }
    if cuda.get("available") and not cuda.get("verified"):
        return {
            "state": "GPU PROBE FAILED",
            "device": "cpu",
            "compute_type": compute_type,
            "reason": "CUDA speech runtime did not verify a usable device.",
        }
    return {
        "state": "CPU FALLBACK",
        "device": "cpu",
        "compute_type": compute_type,
        "reason": "No verified speech accelerator is available.",
    }
