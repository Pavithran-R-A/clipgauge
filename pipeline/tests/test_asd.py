from __future__ import annotations

import pytest

from clipgauge_pipeline.camera import asd


class _Stream:
    def __init__(self, chunks: list[bytes]):
        self.chunks = iter(chunks)
        self.closed = False

    def read(self, _size: int) -> bytes:
        return next(self.chunks, b"")

    def close(self) -> None:
        self.closed = True


class _Process:
    def __init__(self, *, returncode: int | None, chunks: list[bytes]):
        self.stdout = _Stream(chunks)
        self.stderr = _Stream([])
        self.returncode = returncode
        self.killed = False
        self.waited = False

    def poll(self) -> int | None:
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self) -> int:
        self.waited = True
        return self.returncode or 0


def test_stream_frames_raises_when_ffmpeg_exits_with_error(monkeypatch):
    process = _Process(returncode=1, chunks=[b""])
    monkeypatch.setattr(asd.ffmpeg_bin, "ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(asd.subprocess, "Popen", lambda *args, **kwargs: process)

    with pytest.raises(RuntimeError, match="FFmpeg frame decode failed"):
        list(asd._stream_frames("video.mp4", 0, 1, "scale=1:1", "gray", 1))

    assert process.waited


def test_stream_frames_kills_ffmpeg_when_consumer_closes_early(monkeypatch):
    process = _Process(returncode=None, chunks=[b"x"])
    monkeypatch.setattr(asd.ffmpeg_bin, "ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(asd.subprocess, "Popen", lambda *args, **kwargs: process)

    frames = asd._stream_frames("video.mp4", 0, 1, "scale=1:1", "gray", 1)
    assert next(frames).tobytes() == b"x"
    frames.close()

    assert process.killed
    assert process.waited
