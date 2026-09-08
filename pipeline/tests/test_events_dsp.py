"""Bounded event-DSP regression tests."""

from __future__ import annotations

import numpy as np
import pytest

from clipgauge_pipeline.events import dsp


def _reference_energy_curves(y16k: np.ndarray, sr: int = 16000) -> dict:
    hop = int(sr * dsp.GRID_SEC)
    frame = hop * 2
    padded = np.pad(np.asarray(y16k, dtype=np.float32), (frame // 2, frame // 2))
    frames = np.lib.stride_tricks.sliding_window_view(padded, frame)[::hop]
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    window = np.hanning(frame).astype(np.float32)
    stft = np.abs(np.fft.rfft(frames * window, axis=1)).T
    flux = np.sqrt(np.mean(np.diff(stft, axis=1, prepend=stft[:, :1]) ** 2, axis=0))
    flux = flux[: len(rms)]
    win = max(1, int(5.0 / dsp.GRID_SEC))
    local_mean = np.convolve(rms, np.ones(win) / win, mode="same")[: len(rms)]
    std = float(np.std(rms)) or 1.0
    dynamics = np.abs(rms - local_mean) / std
    return {
        "grid_sec": dsp.GRID_SEC,
        "rms": np.round(rms.astype(float), 5).tolist(),
        "flux": np.round(flux.astype(float), 5).tolist(),
        "dynamics": np.round(dynamics.astype(float), 4).tolist(),
    }


def _signals(length: int = 100_321) -> list[np.ndarray]:
    rng = np.random.default_rng(7)
    silence = np.zeros(length, dtype=np.float32)
    sine = np.sin(2 * np.pi * 440 * np.arange(length) / 16_000).astype(np.float32)
    noise = rng.normal(0, 0.1, length).astype(np.float32)
    impulse = np.zeros(length, dtype=np.float32)
    impulse[length // 2] = 1.0
    speech_like = (0.35 * sine + 0.05 * noise).astype(np.float32)
    boundary_impulse = np.zeros(length, dtype=np.float32)
    boundary_impulse[7 * 1_600 + 1_599] = 1.0
    return [silence, sine, noise, impulse, speech_like, boundary_impulse]


@pytest.mark.parametrize("signal", _signals())
def test_chunked_energy_curves_match_small_reference(signal: np.ndarray):
    expected = _reference_energy_curves(signal)
    actual = dsp.energy_curves(signal, chunk_frames=7)
    assert actual == expected


def test_energy_curves_accepts_bounded_sample_chunks():
    signal = _signals(19_321)[4]
    chunks = [signal[start : start + 777] for start in range(0, len(signal), 777)]
    assert dsp.energy_curves(iter(chunks), chunk_frames=5, total_samples=len(signal)) == _reference_energy_curves(signal)


def test_energy_curves_handles_empty_and_short_inputs():
    for signal in (np.zeros(0, dtype=np.float32), np.ones(123, dtype=np.float32)):
        assert dsp.energy_curves(signal, chunk_frames=3) == _reference_energy_curves(signal)


def test_energy_curves_never_sends_more_than_chunk_frames_to_fft(monkeypatch):
    calls: list[int] = []
    original = np.fft.rfft

    def checked_rfft(values, *args, **kwargs):
        calls.append(values.shape[0])
        return original(values, *args, **kwargs)

    monkeypatch.setattr(np.fft, "rfft", checked_rfft)
    dsp.energy_curves(np.zeros(31_777, dtype=np.float32), chunk_frames=11)
    assert calls
    assert max(calls) <= 11


def test_energy_curves_reports_monotonic_progress():
    messages: list[tuple[float, str]] = []
    signal = np.zeros(16_000 * 60, dtype=np.float32)
    dsp.energy_curves(signal, chunk_frames=13, progress=lambda fraction, message: messages.append((fraction, message)))
    fractions = [fraction for fraction, _ in messages]
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0
    assert any("Analyzing energy" in message for _, message in messages)
