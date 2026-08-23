"""Small, best-effort cleanup for long-lived CPU inference pipelines."""

from __future__ import annotations

import ctypes
import gc
import sys


def release_cpu_memory() -> None:
    """Release unreachable Python objects and trim glibc arenas when supported.

    This is intentionally best-effort: cleanup must never make a successful stage
    fail, and non-glibc platforms simply receive the portable garbage collection.
    """
    gc.collect()
    if not sys.platform.startswith("linux"):
        return
    try:
        ctypes.CDLL(None).malloc_trim(0)
    except (AttributeError, OSError):
        return
