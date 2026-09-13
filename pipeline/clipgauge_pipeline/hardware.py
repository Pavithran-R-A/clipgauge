"""Conservative hardware capability detection for setup, ASR, and local AI.

This module reports evidence that is useful for selection without claiming that a
GPU name alone guarantees that a backend or model will work. Every probe is
bounded, optional, and returns ``None`` when the capability cannot be verified.
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

GIB = 1024**3
CPU_LOW_MEMORY_LIMIT = 8 * GIB
CPU_MODERATE_MEMORY_LIMIT = 16 * GIB
CPU_HIGH_MEMORY_LIMIT = 32 * GIB


def _memory_bytes() -> int | None:
    if sys.platform == "win32":
        try:
            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_physical)
        except (AttributeError, OSError, TypeError):
            pass
    if hasattr(os, "sysconf"):
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            if isinstance(pages, int) and isinstance(page_size, int) and pages > 0 and page_size > 0:
                return pages * page_size
        except (OSError, ValueError, TypeError):
            pass
    return None


def _memory_snapshot() -> dict[str, int | None]:
    """Read physical and commit headroom without requiring psutil."""
    result: dict[str, int | None] = {
        "total_bytes": _memory_bytes(),
        "available_bytes": None,
        "total_page_file_bytes": None,
        "available_page_file_bytes": None,
    }
    if sys.platform == "win32":
        try:
            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                result.update({
                    "total_bytes": int(status.total_physical),
                    "available_bytes": int(status.available_physical),
                    "total_page_file_bytes": int(status.total_page_file),
                    "available_page_file_bytes": int(status.available_page_file),
                })
                return result
        except (AttributeError, OSError, TypeError):
            pass
    if hasattr(os, "sysconf"):
        try:
            pages = os.sysconf("SC_AVPHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            if isinstance(pages, int) and isinstance(page_size, int) and pages > 0 and page_size > 0:
                result["available_bytes"] = pages * page_size
        except (OSError, ValueError, TypeError):
            pass
    return result


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


def _cpu() -> dict[str, Any]:
    """Probe CTranslate2 CPU compute types before selecting int8."""
    try:
        import ctranslate2  # type: ignore

        supported = sorted(ctranslate2.get_supported_compute_types("cpu"))
        return {
            "available": True,
            "verified": bool(supported),
            "compute_types": supported,
            "version": str(getattr(ctranslate2, "__version__", "unknown")),
        }
    except (ImportError, RuntimeError, ValueError, AttributeError):
        return {"available": False, "verified": False, "compute_types": []}


def _pytorch_cuda() -> dict[str, Any]:
    """Probe the CUDA runtime used by WhisperX alignment."""
    try:
        import torch  # type: ignore

        available = bool(torch.cuda.is_available())
        compiled = getattr(torch.version, "cuda", None)
        if not available:
            return {
                "available": bool(compiled),
                "verified": False,
                "compiled_cuda": compiled,
                "reason": "PyTorch CUDA is unavailable.",
            }
        device_count = int(torch.cuda.device_count())
        if device_count < 1:
            return {"available": True, "verified": False, "compiled_cuda": compiled, "device_count": 0, "reason": "PyTorch reported no CUDA devices."}
        # Force the lazy CUDA path and a tiny operation.  Device names alone
        # are not evidence that WhisperX can allocate tensors.
        torch.zeros(1, device="cuda")
        return {"available": True, "verified": True, "compiled_cuda": compiled, "device_count": device_count, "device_name": torch.cuda.get_device_name(0)}
    except Exception as exc:  # noqa: BLE001 - diagnostics must remain available
        return {"available": False, "verified": False, "compiled_cuda": None, "reason": str(exc)[:240]}


def _whisperx_alignment() -> dict[str, Any]:
    """Verify that the installed WhisperX alignment API is usable."""
    try:
        import whisperx  # type: ignore

        verified = callable(getattr(whisperx, "load_align_model", None)) and callable(getattr(whisperx, "align", None))
        return {"available": True, "verified": verified, "version": getattr(whisperx, "__version__", "unknown")}
    except Exception as exc:  # noqa: BLE001 - setup diagnostics must not crash
        return {"available": False, "verified": False, "reason": str(exc)[:240]}


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
    pytorch_cuda = _pytorch_cuda()
    whisperx_alignment = _whisperx_alignment()
    vulkan = _vulkan()
    memory = _memory_snapshot()
    return {
        "os": system,
        "architecture": machine,
        "cpu_logical_cores": os.cpu_count(),
        "ram_bytes": memory["total_bytes"],
        "available_ram_bytes": memory["available_bytes"],
        "total_page_file_bytes": memory["total_page_file_bytes"],
        "available_page_file_bytes": memory["available_page_file_bytes"],
        "cpu_ctranslate2": _cpu(),
        "apple_silicon": apple_silicon,
        "nvidia": nvidia,
        "cuda_ctranslate2": cuda,
        "pytorch_cuda": pytorch_cuda,
        "whisperx_alignment": whisperx_alignment,
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
    cpu = capabilities.get("cpu_ctranslate2") or {}
    compute_types = set(cpu.get("compute_types") or [])
    if "int8" in compute_types:
        return "cpu", "int8"
    if "float32" in compute_types:
        return "cpu", "float32"
    if compute_types:
        return "cpu", min(compute_types)
    return "cpu", "int8"


def cpu_asr_policy(capabilities: dict[str, Any]) -> dict[str, Any]:
    """Choose a conservative CPU batch from physical RAM."""
    total = capabilities.get("ram_bytes")
    available = capabilities.get("available_ram_bytes")
    scarce_available = isinstance(available, int) and available <= 2 * GIB
    if scarce_available or not isinstance(total, int) or total <= CPU_LOW_MEMORY_LIMIT:
        batch_size, mode = 1, "low-memory"
    elif total <= CPU_MODERATE_MEMORY_LIMIT:
        batch_size, mode = 2, "standard"
    elif total <= CPU_HIGH_MEMORY_LIMIT:
        batch_size, mode = 4, "standard"
    else:
        batch_size, mode = 8, "standard"
    _, compute_type = select_asr_accelerator({"cpu_ctranslate2": capabilities.get("cpu_ctranslate2", {})})
    return {"device": "cpu", "compute_type": compute_type, "batch_size": batch_size, "mode": mode}


def select_asr_devices(capabilities: dict[str, Any]) -> dict[str, Any]:
    """Select transcription and alignment backends independently."""
    transcription_device, transcription_compute_type = select_asr_accelerator(capabilities)
    pytorch = capabilities.get("pytorch_cuda") or {}
    whisperx = capabilities.get("whisperx_alignment") or {}
    alignment_verified = bool(pytorch.get("verified")) and bool(whisperx.get("verified", True))
    alignment_device = "cuda" if alignment_verified else "cpu"
    result: dict[str, Any] = {
        "transcription_device": transcription_device,
        "transcription_compute_type": transcription_compute_type,
        "alignment_device": alignment_device,
    }
    if "ram_bytes" in capabilities or "cpu_ctranslate2" in capabilities:
        cpu_policy = cpu_asr_policy(capabilities)
        result.update({
            "transcription_batch_size": cpu_policy["batch_size"] if transcription_device == "cpu" else 8,
            "transcription_mode": cpu_policy["mode"] if transcription_device == "cpu" else "cuda",
            "cpu_supported_compute_types": list((capabilities.get("cpu_ctranslate2") or {}).get("compute_types") or []),
        })
    return result


def asr_readiness(capabilities: dict[str, Any]) -> dict[str, Any]:
    """Return truthful ASR readiness without equating GPU detection to use."""
    cuda = capabilities.get("cuda_ctranslate2") or {}
    nvidia = capabilities.get("nvidia") or {}
    device, compute_type = select_asr_accelerator(capabilities)
    if device == "cuda":
        pytorch = capabilities.get("pytorch_cuda")
        whisperx = capabilities.get("whisperx_alignment")
        pytorch_unavailable = isinstance(pytorch, dict) and pytorch.get("verified") is False
        whisperx_unavailable = isinstance(whisperx, dict) and whisperx.get("verified") is False
        if pytorch_unavailable or whisperx_unavailable:
            return {
                "state": "GPU TRANSCRIPTION / CPU ALIGNMENT",
                "device": device,
                "compute_type": compute_type,
                "reason": "CTranslate2 CUDA transcription is ready; PyTorch/WhisperX alignment is unavailable.",
            }
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


def local_runtime_snapshot(data_root: Path | None = None) -> dict[str, Any]:
    """Probe only launch-time GPU backends.

    Local llama.cpp selection must stay responsive.  CTranslate2 loading is
    reserved for ASR qualification and is not needed to select a llama.cpp
    binary that already has its managed companion libraries.
    """
    system = platform.system()
    machine = platform.machine()
    free_bytes = None
    if data_root is not None:
        try:
            free_bytes = shutil.disk_usage(data_root).free
        except OSError:
            free_bytes = None
    return {
        "os": system,
        "architecture": machine,
        "nvidia": _nvidia(),
        "vulkan": _vulkan(),
        "disk_free_bytes": free_bytes,
    }
