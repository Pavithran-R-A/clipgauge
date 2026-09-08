"""Measure bounded event DSP across the supported long-form matrix."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from clipgauge_pipeline.events import dsp


def _chunks(total_samples: int, chunk_samples: int = 160_000):
    remaining = total_samples
    while remaining:
        size = min(remaining, chunk_samples)
        yield np.zeros(size, dtype=np.float32)
        remaining -= size


def measure(duration_sec: int) -> dict[str, float | int]:
    sr = 16_000
    hop = int(sr * dsp.GRID_SEC)
    frame = hop * 2
    frame_count = duration_sec * sr // hop + 1
    old_fft_operand_bytes = frame_count * frame * np.dtype(np.float64).itemsize
    peak_fft_operand_bytes = 0
    original_rfft = np.fft.rfft

    def tracked_rfft(values, *args, **kwargs):
        nonlocal peak_fft_operand_bytes
        peak_fft_operand_bytes = max(peak_fft_operand_bytes, int(values.nbytes))
        return original_rfft(values, *args, **kwargs)

    np.fft.rfft = tracked_rfft
    started = time.perf_counter()
    try:
        curves = dsp.energy_curves(
            _chunks(duration_sec * sr),
            sr,
            total_samples=duration_sec * sr,
        )
    finally:
        np.fft.rfft = original_rfft
    return {
        "duration_sec": duration_sec,
        "frame_count": frame_count,
        "old_fft_operand_gib": old_fft_operand_bytes / 2**30,
        "bounded_peak_fft_operand_mib": peak_fft_operand_bytes / 2**20,
        "curve_points": len(curves["rms"]),
        "elapsed_sec": round(time.perf_counter() - started, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = [measure(duration) for duration in (5 * 60, 30 * 60, 60 * 60, 3 * 60 * 60, 6 * 60 * 60)]
    rendered = json.dumps(results, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
