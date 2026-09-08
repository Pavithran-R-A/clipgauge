"""Free DSP signal curves: RMS energy + spectral flux at a 100 ms grid, plus
long-pause detection from transcript word gaps.

These feed the interest curve (M2), punch-in triggers (M3), and prosodic
caption emphasis gets its per-word RMS from the same frame grid (M4). F0 is
deliberately NOT computed over the full video — pitch extraction is slow and
only selected clips need it (computed on-demand in M4).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Iterator

import numpy as np

GRID_SEC = 0.1  # 100 ms analysis grid shared by all curve consumers
LONG_PAUSE_SEC = 1.2
ENERGY_CHUNK_FRAMES = 1024


class _SampleStream:
    """Read bounded sample chunks while preserving absolute positions."""

    def __init__(self, samples: np.ndarray | Iterable[np.ndarray]):
        if isinstance(samples, np.ndarray):
            array = np.asarray(samples, dtype=np.float32)
            if array.ndim != 1:
                raise ValueError("audio samples must be one-dimensional")
            self._array = array
            self._chunks: deque[tuple[int, np.ndarray]] = deque()
            self._iterator: Iterator[np.ndarray] | None = None
            self._position = len(array)
            self._exhausted = True
            return
        self._array = None
        self._chunks = deque()
        self._iterator = iter(samples)
        self._position = 0
        self._exhausted = False

    @property
    def length(self) -> int | None:
        return self._position if self._exhausted else None

    def ensure(self, end: int) -> None:
        """Read through ``end`` without retaining old chunks."""
        if self._array is not None or self._exhausted:
            return
        target = max(0, end)
        while self._position < target:
            assert self._iterator is not None
            try:
                chunk = np.asarray(next(self._iterator), dtype=np.float32)
            except StopIteration:
                self._exhausted = True
                return
            if chunk.ndim != 1:
                raise ValueError("audio chunks must be one-dimensional")
            if len(chunk) == 0:
                continue
            chunk = np.ascontiguousarray(chunk, dtype=np.float32)
            self._chunks.append((self._position, chunk))
            self._position += len(chunk)

    def copy_range(self, start: int, end: int) -> np.ndarray:
        """Copy one bounded padded range into a fresh float32 array."""
        output = np.zeros(max(0, end - start), dtype=np.float32)
        if len(output) == 0:
            return output
        if self._array is not None:
            source_start = max(0, start)
            source_end = min(len(self._array), end)
            if source_end > source_start:
                output[source_start - start : source_end - start] = self._array[source_start:source_end]
            return output
        for chunk_start, chunk in self._chunks:
            chunk_end = chunk_start + len(chunk)
            overlap_start = max(start, chunk_start)
            overlap_end = min(end, chunk_end)
            if overlap_end > overlap_start:
                output[overlap_start - start : overlap_end - start] = chunk[
                    overlap_start - chunk_start : overlap_end - chunk_start
                ]
        return output

    def discard_before(self, position: int) -> None:
        while self._chunks and self._chunks[0][0] + len(self._chunks[0][1]) <= position:
            self._chunks.popleft()


def _frame_blocks(
    samples: np.ndarray | Iterable[np.ndarray],
    *,
    hop: int,
    frame: int,
    chunk_frames: int,
) -> Iterator[tuple[np.ndarray, int, int | None]]:
    stream = _SampleStream(samples)
    padding = frame // 2
    frame_index = 0
    while True:
        requested_count = chunk_frames
        requested_end = (frame_index + requested_count - 1) * hop - padding + frame
        stream.ensure(requested_end)
        if stream.length is not None:
            total_frames = stream.length // hop + 1
            count = min(requested_count, total_frames - frame_index)
            if count <= 0:
                return
        else:
            count = requested_count
        raw_start = frame_index * hop - padding
        raw_end = (frame_index + count - 1) * hop - padding + frame
        stream.ensure(raw_end)
        segment = stream.copy_range(raw_start, raw_end)
        frames = np.lib.stride_tricks.sliding_window_view(segment, frame)[::hop]
        yield frames, frame_index, stream.length
        frame_index += count
        stream.discard_before(frame_index * hop - padding)


def energy_curves(
    y16k: np.ndarray | Iterable[np.ndarray],
    sr: int = 16000,
    *,
    chunk_frames: int = ENERGY_CHUNK_FRAMES,
    total_samples: int | None = None,
    progress=None,
) -> dict:
    """RMS + spectral flux resampled onto the 100 ms grid, plus normalized
    'dynamics' (how much the local energy deviates from its neighborhood —
    flat delivery scores 0, punchy delivery spikes)."""
    if chunk_frames < 1:
        raise ValueError("chunk_frames must be positive")
    hop = int(sr * GRID_SEC)
    frame = hop * 2
    window = np.hanning(frame).astype(np.float32)
    rms_parts: list[np.ndarray] = []
    flux_parts: list[np.ndarray] = []
    previous_spectrum: np.ndarray | None = None
    for frames, frame_index, stream_length in _frame_blocks(
        y16k,
        hop=hop,
        frame=frame,
        chunk_frames=chunk_frames,
    ):
        weighted = frames * window
        rms_parts.append(np.sqrt(np.mean(frames * frames, axis=1)))
        spectrum = np.abs(np.fft.rfft(weighted, axis=1))
        prepend = spectrum[:1] if previous_spectrum is None else previous_spectrum[None, :]
        delta = np.diff(spectrum, axis=0, prepend=prepend)
        flux_parts.append(np.sqrt(np.mean(delta**2, axis=1)))
        previous_spectrum = spectrum[-1].copy()
        if progress:
            processed = frame_index + len(frames)
            known_total = total_samples
            if known_total is None and stream_length is not None:
                known_total = stream_length
            fraction = -1.0 if not known_total else min(1.0, processed * hop / known_total)
            progress(fraction, f"Analyzing energy and dynamics… {processed:,} frames")

    rms = np.concatenate(rms_parts) if rms_parts else np.zeros(0, dtype=np.float32)
    flux = np.concatenate(flux_parts) if flux_parts else np.zeros(0, dtype=np.float32)
    if progress:
        progress(1.0, f"Analyzing energy and dynamics… {len(rms):,} frames complete")

    # Local dynamics: |rms - 5s moving average|, normalized by global std.
    win = max(1, int(5.0 / GRID_SEC))
    kernel = np.ones(win) / win
    local_mean = np.convolve(rms, kernel, mode="same")[: len(rms)] if len(rms) else rms
    std = float(np.std(rms)) or 1.0
    dynamics = np.abs(rms - local_mean) / std

    return {
        "grid_sec": GRID_SEC,
        "rms": np.round(rms.astype(float), 5).tolist(),
        "flux": np.round(flux.astype(float), 5).tolist(),
        "dynamics": np.round(dynamics.astype(float), 4).tolist(),
    }


def long_pauses(segments: list[dict], min_gap: float = LONG_PAUSE_SEC) -> list[dict]:
    """Gaps between consecutive words (across segments too). A long pause is
    a beat — comedic timing, a speaker collecting themselves — and both the
    interest curve and candidate boundary snapping use them."""
    words: list[dict] = []
    for seg in segments:
        words.extend(seg.get("words", []))
    words.sort(key=lambda w: w["start"])
    pauses = []
    for prev, cur in zip(words, words[1:]):
        gap = cur["start"] - prev["end"]
        if gap >= min_gap:
            pauses.append(
                {
                    "type": "pause",
                    "start": round(prev["end"], 3),
                    "end": round(cur["start"], 3),
                    "confidence": 1.0,
                    "sources": ["transcript"],
                }
            )
    return pauses
