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


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _parse_meminfo(text: str) -> dict[str, int]:
    """Parse Linux memory values into bytes where units are provided."""
    multipliers = {"kb": 1024, "mb": 1024**2, "gb": 1024**3, "b": 1}
    values: dict[str, int] = {}
    for line in text.splitlines():
        name, separator, raw_value = line.partition(":")
        if not separator:
            continue
        fields = raw_value.strip().split()
        if not fields:
            continue
        try:
            value = int(fields[0])
        except (TypeError, ValueError):
            continue
        if value < 0:
            continue
        if len(fields) > 1:
            multiplier = multipliers.get(fields[1].casefold())
            if multiplier is None:
                continue
            value *= multiplier
        values[name.strip()] = value
    return values


def _nonnegative_int(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number >= 0 else None


def _sysconf_available_bytes() -> int | None:
    if not hasattr(os, "sysconf"):
        return None
    try:
        pages = os.sysconf("SC_AVPHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, TypeError):
        return None
    if isinstance(pages, int) and isinstance(page_size, int) and pages > 0 and page_size > 0:
        return pages * page_size
    return None


def _parse_cgroup_memory_value(raw_value: str | None) -> int | None:
    if raw_value is None:
        return None
    value = raw_value.strip()
    if value.casefold() == "max":
        return None
    return _nonnegative_int(value)


def _linux_cgroup_memory() -> tuple[int | None, int | None]:
    """Return the current cgroup memory limit and usage when readable."""
    cgroup_text = _read_text(Path("/proc/self/cgroup"))
    if cgroup_text is None:
        return None, None
    for line in cgroup_text.splitlines():
        fields = line.split(":", 2)
        if len(fields) != 3:
            continue
        hierarchy, controllers, relative_path = fields
        if hierarchy == "0" and not controllers:
            cgroup_root = Path("/sys/fs/cgroup") / relative_path.lstrip("/")
        elif "memory" in controllers.split(","):
            cgroup_root = Path("/sys/fs/cgroup/memory") / relative_path.lstrip("/")
        else:
            continue
        limit = _parse_cgroup_memory_value(_read_text(cgroup_root / "memory.max"))
        current = _parse_cgroup_memory_value(_read_text(cgroup_root / "memory.current"))
        if not (hierarchy == "0" and not controllers):
            limit = _parse_cgroup_memory_value(_read_text(cgroup_root / "memory.limit_in_bytes"))
            current = _parse_cgroup_memory_value(_read_text(cgroup_root / "memory.usage_in_bytes"))
        return limit, current
    return None, None


def _linux_memory_values(
    meminfo: dict[str, int],
    *,
    physical_total: int | None,
    sysconf_available: int | None,
    cgroup_limit: int | None,
    cgroup_current: int | None,
) -> dict[str, int | str | None]:
    total = _nonnegative_int(physical_total)
    if total is None:
        total = _nonnegative_int(meminfo.get("MemTotal"))
    if cgroup_limit is not None and total is not None:
        total = min(total, cgroup_limit)

    available = _nonnegative_int(meminfo.get("MemAvailable"))
    source = "proc_meminfo"
    if available is None:
        available = _nonnegative_int(sysconf_available)
        source = "sysconf_avphys_pages" if available is not None else "unknown"
    if cgroup_limit is not None and cgroup_current is not None and available is not None:
        available = min(available, max(0, cgroup_limit - cgroup_current))
        source += "+cgroup"
    return {
        "total_bytes": total,
        "available_bytes": available,
        "available_source": source,
        "cgroup_memory_limit_bytes": cgroup_limit,
        "cgroup_memory_current_bytes": cgroup_current,
    }


def _memory_snapshot() -> dict[str, Any]:
    """Read physical and commit headroom without requiring psutil."""
    result: dict[str, Any] = {
        "total_bytes": _memory_bytes(),
        "available_bytes": None,
        "available_source": None,
        "total_page_file_bytes": None,
        "available_page_file_bytes": None,
        "cgroup_memory_limit_bytes": None,
        "cgroup_memory_current_bytes": None,
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
                    "available_source": "windows_global_memory_status_ex",
                    "total_page_file_bytes": int(status.total_page_file),
                    "available_page_file_bytes": int(status.available_page_file),
                })
                return result
        except (AttributeError, OSError, TypeError):
            pass
    if sys.platform == "linux":
        meminfo = _parse_meminfo(_read_text(Path("/proc/meminfo")) or "")
        cgroup_limit, cgroup_current = _linux_cgroup_memory()
        result.update(_linux_memory_values(
            meminfo,
            physical_total=result["total_bytes"],
            sysconf_available=_sysconf_available_bytes(),
            cgroup_limit=cgroup_limit,
            cgroup_current=cgroup_current,
        ))
        return result
    if hasattr(os, "sysconf"):
        available = _sysconf_available_bytes()
        if available is not None:
            result["available_bytes"] = available
            result["available_source"] = "sysconf_avphys_pages"
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
        "available_ram_source": memory["available_source"],
        "total_page_file_bytes": memory["total_page_file_bytes"],
        "available_page_file_bytes": memory["available_page_file_bytes"],
        "cgroup_memory_limit_bytes": memory["cgroup_memory_limit_bytes"],
        "cgroup_memory_current_bytes": memory["cgroup_memory_current_bytes"],
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
