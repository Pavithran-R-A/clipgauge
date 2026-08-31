"""Deterministic render resource policy."""

from __future__ import annotations


def concurrency_limit(encoder: str, *, ram_bytes: int | None = None, vram_mb: int | None = None) -> int:
    """Keep hardware encoders and memory-heavy renders bounded."""
    if encoder in {"h264_nvenc", "h264_videotoolbox"}:
        return 1
    if ram_bytes is not None and ram_bytes < 12 * 1024**3:
        return 1
    if vram_mb is not None and vram_mb < 4096:
        return 1
    return 2
