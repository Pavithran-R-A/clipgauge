"""Renderer + caption engine tests. The render smoke test builds a real
20 s synthetic clip through the FULL ffmpeg path — sendcmd crop, caption
burn, loudnorm — and verifies the output probes clean."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from clipgauge_pipeline.captions import ass as ass_mod
from clipgauge_pipeline.render import ffmpeg_bin, renderer


def test_windows_ffmpeg_managed_path_uses_one_filesystem_safe_version_component(monkeypatch, tmp_path):
    monkeypatch.setattr(ffmpeg_bin.platform, "system", lambda: "Windows")
    monkeypatch.setattr(ffmpeg_bin.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(ffmpeg_bin.config, "runtimes_dir", lambda: tmp_path / "runtimes")

    managed = ffmpeg_bin._managed_dir()

    assert managed == tmp_path / "runtimes" / "ffmpeg" / "autobuild-2026-08-18-15-03-N-126207-g21bbd98e7b" / "win64-gpl"
    assert len(managed.relative_to(tmp_path / "runtimes" / "ffmpeg").parts) == 2


def test_crop_boxes_even_and_bounded():
    frames = [[10.7, 5.3, 607.9, 1080.0], [1900.0, 0.0, 608.0, 1080.0]]
    boxes = renderer.crop_boxes(frames, 1920, 1080)
    for w, h, x, y in boxes:
        assert w % 2 == 0 and h % 2 == 0 and x % 2 == 0 and y % 2 == 0
        assert x + w <= 1920 and y + h <= 1080


def test_sendcmd_dedupes_to_change_points():
    boxes = [(608, 1080, 100, 0)] * 50 + [(608, 1080, 700, 0)] * 50
    lines = renderer.sendcmd_lines(boxes, 25.0)
    # initial 4 params + 1 change (x only)
    assert len(lines) == 5
    assert lines[-1].startswith("2.0000 crop@c x 700")


def test_chunking_rules():
    words = [ass_mod.Word(f"w{i}", i * 0.3, i * 0.3 + 0.25) for i in range(6)]
    chunks = ass_mod.chunk_words(words)
    assert [len(c.words) for c in chunks] == [4, 2]  # budget break

    words = [
        ass_mod.Word("hey.", 0.0, 0.3),
        ass_mod.Word("so", 0.4, 0.6),
        ass_mod.Word("anyway", 2.0, 2.4),  # >0.6s pause before this
    ]
    chunks = ass_mod.chunk_words(words)
    assert len(chunks) == 3  # punctuation break + pause break


def test_caption_layout_scales_and_wraps_long_unicode_text():
    layout = ass_mod.caption_layout(540, 960, ass_mod.PRESETS["classic"])
    wrapped = ass_mod.wrap_caption("बहुतलंबाUnicodeCaptionWord with readable words", layout["max_chars"])
    document = ass_mod.build_ass(
        [ass_mod.Word("hello", 0.0, 0.4)],
        [],
        output_width=540,
        output_height=960,
    )

    assert layout["font_size"] < ass_mod.PRESETS["classic"].size
    assert "PlayResX: 540" in document and "PlayResY: 960" in document
    assert wrapped.count(r"\N") <= 1
    assert wrapped


def test_emphasis_or_combination():
    words = [
        ass_mod.Word("million", 0.0, 0.5),   # power word
        ass_mod.Word("okay", 0.5, 1.0),      # quiet filler
        ass_mod.Word("LOUD", 1.0, 1.5),      # top-RMS word
    ]
    rms = [0.1] * 10 + [0.9] * 5  # 0.1s grid; frames 10-14 are loud
    ass_mod.mark_emphasis(words, rms, 0.1, clip_start=0.0)
    assert words[0].emphasized      # power word
    assert not words[1].emphasized
    assert words[2].emphasized      # prosodic


def test_ass_document_structure():
    words = [ass_mod.Word("hello", 0.0, 0.4), ass_mod.Word("world", 0.4, 0.8)]
    events = [{"type": "laugh", "start": 1.0, "end": 2.0}]
    doc = ass_mod.build_ass(words, events, preset_name="beast")
    assert "[Script Info]" in doc and "[Events]" in doc
    # one Dialogue per word transition + one event tag
    assert doc.count("Dialogue: 0,") == 2
    assert doc.count("Dialogue: 1,") == 1
    assert "[laughs]" in doc
    assert "\\k" not in doc  # never native karaoke tags
    assert "HELLO" in doc    # beast preset uppercases


def test_ass_no_word_scaling():
    """Words must never be individually scaled — only the chunk-entrance pop
    on the first event of a chunk."""
    words = [ass_mod.Word("one", 0.0, 0.4), ass_mod.Word("two", 0.4, 0.8)]
    doc = ass_mod.build_ass(words, [], preset_name="beast")
    lines = [l for l in doc.splitlines() if l.startswith("Dialogue: 0")]
    assert "\\fscx" in lines[0]      # entrance pop on chunk start
    assert "\\fscx" not in lines[1]  # no per-word scaling afterwards


def test_render_is_non_interactive(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(renderer, "videotoolbox_available", lambda: False)
    monkeypatch.setattr(renderer.subprocess, "run", fake_run)
    renderer.render_clip(
        "source.mp4",
        tmp_path / "out.mp4",
        0.0,
        1.0,
        {"fps": 25, "frames": [[100.0, 0.0, 404.0, 720.0]]},
        None,
        None,
        src_w=1280,
        src_h=720,
    )

    render_calls = [(args, kwargs) for args, kwargs in calls if "-ss" in args]
    assert len(render_calls) == 1
    args, kwargs = render_calls[0]
    assert "-nostdin" in args
    assert kwargs["stdin"] is subprocess.DEVNULL


def test_encoder_probe_uses_the_selected_encoder_quality_contract(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(renderer.subprocess, "run", fake_run)

    assert renderer._encoder_probe("h264_nvenc")
    assert calls[0][calls[0].index("-c:v") + 1] == "h264_nvenc"
    assert "-preset" in calls[0]
    assert "-cq" in calls[0]


def test_render_retries_hardware_initialization_with_software(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            return SimpleNamespace(returncode=1, stderr="h264_nvenc: Cannot load libcuda", stdout="")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(renderer, "nvenc_available", lambda: True)
    monkeypatch.setattr(renderer, "videotoolbox_available", lambda: False)
    monkeypatch.setattr(renderer.subprocess, "run", fake_run)
    used = renderer.render_clip(
        "source.mp4",
        tmp_path / "out.mp4",
        0.0,
        1.0,
        {"fps": 25, "frames": [[100.0, 0.0, 404.0, 720.0]]},
        None,
        None,
        src_w=1280,
        src_h=720,
    )

    assert len(calls) == 2
    assert "h264_nvenc" in calls[0]
    assert "libx264" in calls[1]
    assert used == "libx264"


@pytest.mark.slow
def test_render_smoke(tmp_path):
    """Full path: synthetic source → sendcmd crop with a mid-clip cut →
    caption burn → verified 9:16 output."""
    src = tmp_path / "src.mp4"
    # Resolve like the product does — on a bare machine (Windows CI) the only
    # ffmpeg is the fetched static one, reachable via CLIPGAUGE_FFMPEG.
    subprocess.run(
        [
            ffmpeg_bin.ffmpeg(), "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=20",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(src),
        ],
        check=True, timeout=300,
    )
    n = 20 * 25
    crop_w = 720 * 9 / 16
    frames = [[100.0, 0.0, crop_w, 720.0]] * (n // 2) + [[700.0, 0.0, crop_w, 720.0]] * (n // 2)
    trajectory = {"fps": 25, "frames": frames, "cuts": [n // 2], "punches": []}

    words = [ass_mod.Word(f"word{i}", i * 0.5, i * 0.5 + 0.4) for i in range(30)]
    ass_path = tmp_path / "caps.ass"
    ass_path.write_text(ass_mod.build_ass(words, [{"type": "laugh", "start": 2.0, "end": 3.5}]))

    out = tmp_path / "out.mp4"
    renderer.render_clip(
        str(src), out, 0.0, 20.0, trajectory, ass_path, ass_mod.FONTS_DIR,
        src_w=1280, src_h=720,
    )
    check = renderer.verify_output(out, 20.0)
    assert check["ok"], check
    assert check["width"] == 1080 and check["height"] == 1920


def test_windows_system_ffmpeg_with_spaces_is_capable_and_needs_no_managed_download(monkeypatch, tmp_path):
    binary = tmp_path / "Windows User" / "ffmpeg.exe"
    binary.parent.mkdir()
    binary.write_text("placeholder")
    monkeypatch.setattr(ffmpeg_bin, "_EXE", ".exe")
    monkeypatch.setattr(ffmpeg_bin.platform, "system", lambda: "Windows")
    monkeypatch.setattr(ffmpeg_bin.platform, "machine", lambda: "AMD64")
    monkeypatch.setenv("CLIPGAUGE_FFMPEG", str(binary))
    monkeypatch.setattr(ffmpeg_bin, "_platform_asset", lambda: None)
    monkeypatch.setattr(ffmpeg_bin, "_probe", lambda path: ("ffmpeg version test", {"starts": True, "subtitles": True}, "ok") if path == str(binary) else (None, {"starts": False, "subtitles": False}, "unused"))
    ffmpeg_bin.readiness.cache_clear()
    ffmpeg_bin.resolve.cache_clear()
    try:
        result = ffmpeg_bin.readiness()
        assert result.ready is True
        assert result.source == "configured"
        assert result.executable == str(binary)
        assert result.managed_download_needed is False
    finally:
        ffmpeg_bin.readiness.cache_clear()
        ffmpeg_bin.resolve.cache_clear()


def test_windows_managed_ffmpeg_is_used_when_it_is_the_first_capable_candidate(monkeypatch, tmp_path):
    binary = tmp_path / "managed" / "ffmpeg.exe"
    binary.parent.mkdir()
    binary.write_text("placeholder")
    monkeypatch.setattr(ffmpeg_bin, "_EXE", ".exe")
    monkeypatch.setattr(ffmpeg_bin.platform, "system", lambda: "Windows")
    monkeypatch.setattr(ffmpeg_bin.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(ffmpeg_bin, "_managed_dir", lambda: binary.parent)
    monkeypatch.delenv("CLIPGAUGE_FFMPEG", raising=False)
    monkeypatch.setattr(ffmpeg_bin, "_platform_asset", lambda: {"key": "win64-gpl", "version": "test", "size": 163})
    monkeypatch.setattr(ffmpeg_bin, "_probe", lambda _path: ("ffmpeg version managed", {"starts": True, "subtitles": True}, "ok"))
    ffmpeg_bin.readiness.cache_clear()
    try:
        result = ffmpeg_bin.readiness()
        assert result.ready is True
        assert result.source == "managed"
        assert result.managed_download_needed is False
    finally:
        ffmpeg_bin.readiness.cache_clear()
        ffmpeg_bin.resolve.cache_clear()


def test_windows_incompatible_system_ffmpeg_offers_managed_fallback(monkeypatch, tmp_path):
    binary = tmp_path / "ffmpeg.exe"
    binary.write_text("placeholder")
    monkeypatch.setattr(ffmpeg_bin, "_EXE", ".exe")
    monkeypatch.setattr(ffmpeg_bin.platform, "system", lambda: "Windows")
    monkeypatch.setattr(ffmpeg_bin.platform, "machine", lambda: "AMD64")
    monkeypatch.setenv("CLIPGAUGE_FFMPEG", str(binary))
    monkeypatch.setattr(ffmpeg_bin, "_platform_asset", lambda: {"key": "win64-gpl", "version": "test", "size": 163})
    monkeypatch.setattr(ffmpeg_bin, "_probe", lambda _path: ("ffmpeg version old", {"starts": True, "subtitles": False}, "missing subtitles"))
    ffmpeg_bin.readiness.cache_clear()
    try:
        result = ffmpeg_bin.readiness()
        assert result.ready is False
        assert result.source == "configured"
        assert result.managed_download_needed is True
        assert result.reason == "missing subtitles"
    finally:
        ffmpeg_bin.readiness.cache_clear()
        ffmpeg_bin.resolve.cache_clear()


def test_windows_ffmpeg_missing_offers_managed_fallback(monkeypatch):
    monkeypatch.setattr(ffmpeg_bin, "_EXE", ".exe")
    monkeypatch.setattr(ffmpeg_bin.platform, "system", lambda: "Windows")
    monkeypatch.setattr(ffmpeg_bin.platform, "machine", lambda: "AMD64")
    monkeypatch.delenv("CLIPGAUGE_FFMPEG", raising=False)
    monkeypatch.setattr(ffmpeg_bin, "_managed_dir", lambda: None)
    monkeypatch.setattr(ffmpeg_bin, "_platform_asset", lambda: {"key": "win64-gpl", "version": "test", "size": 163})
    monkeypatch.setattr(ffmpeg_bin, "_candidates", lambda: [])
    ffmpeg_bin.readiness.cache_clear()
    try:
        result = ffmpeg_bin.readiness()
        assert result.ready is False
        assert result.source == "missing"
        assert result.managed_download_needed is True
    finally:
        ffmpeg_bin.readiness.cache_clear()
        ffmpeg_bin.resolve.cache_clear()
