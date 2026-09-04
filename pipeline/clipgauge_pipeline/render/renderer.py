"""Clip renderer: one ffmpeg filter_complex per clip.

The sendcmd architecture (vendored from mutonby/openshorts punch_in.py +
reframe_v2.py, MIT): the director's per-frame trajectory array becomes a
deduped sendcmd command file driving a labeled crop filter — hard cuts are
just discontinuities in the same array, pans are smooth regions, punch-ins
already live in the w/h values. One decode, one encode:

    sendcmd → crop@c → scale 1080x1920 → subtitles burn → loudnorm

Deduping to change-points matters: a 45 s clip at 25 fps is 1125 frames and
writing every parameter every frame slows the filter measurably (openshorts'
own comment). Even dimensions everywhere — x264/NVENC reject odd ones.

Encoder tiers are verified by an actual tiny encode: NVIDIA NVENC first,
VideoToolbox on Apple systems second, then libx264 as the portable fallback.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from . import ffmpeg_bin

OUT_W = 1080
OUT_H = 1920
X264_CRF = 19
NVENC_CQ = 19
VT_BITRATE = "10M"
X264_PRESETS = frozenset({"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"})
OUTPUT_SIZES = {"1080x1920": (1080, 1920), "540x960": (540, 960)}


def output_dimensions() -> tuple[int, int]:
    """Return a safe optional validation size; production defaults to 1080×1920."""
    requested = os.environ.get("CLIPGAUGE_RENDER_OUTPUT_SIZE", "1080x1920").strip().lower()
    return OUTPUT_SIZES.get(requested, OUTPUT_SIZES["1080x1920"])


def x264_preset() -> str:
    """Return a safe optional validation override; production defaults to medium."""
    requested = os.environ.get("CLIPGAUGE_RENDER_X264_PRESET", "medium").strip().lower()
    return requested if requested in X264_PRESETS else "medium"


_nvenc_checked: bool | None = None
_vt_checked: bool | None = None


def _encoder_probe(codec: str) -> bool:
    """Verify an encoder with a real tiny encode instead of trusting a name list."""
    try:
        proc = subprocess.run(
            [
                ffmpeg_bin.ffmpeg(),
                "-nostdin",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=black:s=320x240:d=0.2",
                "-an",
                "-pix_fmt",
                "yuv420p",
                *_encoder_args(codec),
                "-f",
                "null",
                "-",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _encoder_args(codec: str) -> list[str]:
    if codec == "h264_nvenc":
        return ["-c:v", codec, "-preset", "p5", "-cq", str(NVENC_CQ), "-b:v", "0"]
    if codec == "h264_videotoolbox":
        return ["-c:v", codec, "-b:v", VT_BITRATE, "-allow_sw", "1"]
    return ["-c:v", codec]


def nvenc_available() -> bool:
    """Probe once: encode 0.2 s of black through h264_nvenc."""
    global _nvenc_checked
    if platform.system() == "Darwin":
        return False
    if _nvenc_checked is None:
        _nvenc_checked = _encoder_probe("h264_nvenc")
    return _nvenc_checked


def videotoolbox_available() -> bool:
    """Probe once: encode 0.2 s of black through h264_videotoolbox."""
    global _vt_checked
    if _vt_checked is None:
        _vt_checked = _encoder_probe("h264_videotoolbox")
    return _vt_checked


def select_video_encoder(*, nvenc_available: bool, videotoolbox_available: bool) -> list[str]:
    """Return encoder arguments in acceleration preference order."""
    if nvenc_available:
        return _encoder_args("h264_nvenc")
    if videotoolbox_available:
        return _encoder_args("h264_videotoolbox")
    return ["-c:v", "libx264", "-preset", x264_preset(), "-crf", str(X264_CRF)]


def selected_video_encoder() -> str:
    """Return the verified encoder name used by production renders."""
    if nvenc_available():
        return "h264_nvenc"
    if videotoolbox_available():
        return "h264_videotoolbox"
    return "libx264"


def run_ffmpeg_with_encoder_fallback(
    args: list[str], encoder_args: list[str], timeout: float
) -> tuple[object, str]:
    """Retry only hardware initialization failures with libx264."""
    proc = subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    codec = encoder_args[1] if len(encoder_args) > 1 else "libx264"
    stderr = (proc.stderr or "").lower()
    hardware_failure = codec in {"h264_nvenc", "h264_videotoolbox"} and any(
        marker in stderr for marker in ("encoder", "nvenc", "videotoolbox", "cuda", "device")
    )
    if proc.returncode == 0 or not hardware_failure:
        return proc, codec
    start = args.index(encoder_args[0])
    fallback = select_video_encoder(nvenc_available=False, videotoolbox_available=False)
    fallback_args = args[:start] + fallback + args[start + len(encoder_args):]
    return subprocess.run(
        fallback_args,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
    ), fallback[1]


def crop_boxes(frames: list[list[float]], src_w: int, src_h: int) -> list[tuple[int, int, int, int]]:
    """Director frames [x, y, w, h] → even-int (w, h, x, y) crop boxes,
    clamped in-bounds (openshorts crop_boxes rounding rules)."""
    boxes: list[tuple[int, int, int, int]] = []
    for x, y, w, h in frames:
        wi = max(2, min(int(w) - int(w) % 2, src_w))
        hi = max(2, min(int(h) - int(h) % 2, src_h))
        xi = max(0, min(int(round(x)), src_w - wi))
        yi = max(0, min(int(round(y)), src_h - hi))
        boxes.append((wi, hi, xi - xi % 2, yi - yi % 2))
    return boxes


def sendcmd_lines(
    boxes: list[tuple[int, int, int, int]],
    fps: float,
    target: str = "crop@c",
    fields: tuple[str, ...] = ("w", "h", "x", "y"),
) -> list[str]:
    """Per-frame command updates, deduped to change-points.

    ``crop`` accepts coordinate-only updates reliably on WebKit/ffmpeg. The
    renderer uses this helper with dynamic scale dimensions and a fixed-size
    output crop so the encoder never sees a changing frame shape.
    """
    lines: list[str] = []
    prev: tuple[int, int, int, int] | None = None
    names = ("w", "h", "x", "y")
    for i, box in enumerate(boxes):
        if box == prev:
            continue
        t = i / fps
        values = dict(zip(names, box))
        previous = dict(zip(names, prev)) if prev else {}
        for field in fields:
            if values[field] != previous.get(field):
                lines.append(f"{t:.4f} {target} {field} {values[field]};")
        prev = box
    return lines


def _even(value: float) -> int:
    return max(2, int(round(value)) // 2 * 2)


def render_command_lines(
    boxes: list[tuple[int, int, int, int]],
    fps: float,
    src_w: int,
    src_h: int,
    out_w: int,
    out_h: int,
) -> list[str]:
    """Build stable-shape commands for a trajectory's crop boxes.

    Each crop box is represented by a uniform source scale followed by a
    fixed-size output crop. Only the scale dimensions and output x/y change;
    the final encoder frame remains ``out_w`` × ``out_h`` throughout.
    """
    zoom_boxes: list[tuple[int, int, int, int]] = []
    viewport_boxes: list[tuple[int, int, int, int]] = []
    for width, height, x, y in boxes:
        sx = out_w / width
        sy = out_h / height
        zoom_boxes.append((_even(src_w * sx), _even(src_h * sy), 0, 0))
        viewport_boxes.append((out_w, out_h, _even(x * sx), _even(y * sy)))
    lines = sendcmd_lines(zoom_boxes, fps, "scale@z", ("w", "h"))
    lines.extend(sendcmd_lines(viewport_boxes, fps, "crop@o", ("x", "y")))
    return sorted(lines, key=lambda line: (float(line.split()[0]), 0 if "scale@z" in line else 1))


def _q(path: str) -> str:
    """ffmpeg filter-option quoting: single quotes make the value literal;
    an embedded quote closes, escapes, reopens ('\\'').

    Windows adds two wrinkles the mac path never sees: backslash is
    ffmpeg's escape character even inside quotes (av_get_token), and the
    drive-letter colon reads as an option separator on some parse levels.
    Forward slashes (fine for libass and every filter) plus an escaped
    colon is the canonical portable form: 'C\\:/Users/…/clip.ass'."""
    text = str(path)
    if os.name == "nt":
        text = text.replace("\\", "/").replace(":", "\\:")
    return "'" + text.replace("'", "'\\''") + "'"


def render_clip(
    media_path: str,
    out_path: Path,
    clip_start: float,
    clip_end: float,
    trajectory: dict,
    ass_path: Path | None,
    fonts_dir: Path | None,
    lufs: float = -14.0,
    true_peak: float = -1.0,
    src_w: int = 1920,
    src_h: int = 1080,
    timeout: float = 1800.0,
) -> str:
    duration = clip_end - clip_start
    boxes = crop_boxes(trajectory["frames"], src_w, src_h)
    if not boxes:
        boxes = [(src_h * 9 // 16 // 2 * 2, src_h - src_h % 2, 0, 0)]
    fps = float(trajectory.get("fps", 25))

    out_w, out_h = output_dimensions()
    cmd_path = out_path.with_suffix(".cmd")
    cmd_path.write_text(
        "\n".join(render_command_lines(boxes, fps, src_w, src_h, out_w, out_h)) + "\n"
    )

    w0, h0, x0, y0 = boxes[0]
    sx0 = out_w / w0
    sy0 = out_h / h0
    zoom_w0, zoom_h0 = _even(src_w * sx0), _even(src_h * sy0)
    view_x0, view_y0 = _even(x0 * sx0), _even(y0 * sy0)
    vf_parts = [
        f"sendcmd=f={_q(cmd_path)}",
        f"scale@z=w={zoom_w0}:h={zoom_h0}:flags=lanczos",
        f"crop@o=w={out_w}:h={out_h}:x={view_x0}:y={view_y0}",
        "setsar=1",
    ]
    if ass_path is not None:
        sub = f"subtitles=filename={_q(ass_path)}"
        if fonts_dir is not None:
            sub += f":fontsdir={_q(fonts_dir)}"
        vf_parts.append(sub)

    vcodec = select_video_encoder(
        nvenc_available=nvenc_available(),
        videotoolbox_available=videotoolbox_available(),
    )

    args = [
        ffmpeg_bin.ffmpeg(), "-nostdin", "-y", "-v", "error",
        "-ss", f"{clip_start:.3f}", "-t", f"{duration:.3f}",
        "-i", media_path,
        "-vf", ",".join(vf_parts),
        "-af", f"loudnorm=I={lufs}:TP={true_peak}:LRA=11",
        *vcodec,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        "-map_metadata", "-1",  # metadata scrub (openshorts ffmpeg_utils)
        str(out_path),
    ]
    proc, used_encoder = run_ffmpeg_with_encoder_fallback(args, vcodec, timeout)
    cmd_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Render failed: {(proc.stderr or '')[-800:]}")
    return used_encoder


def verify_output(out_path: Path, expected_duration: float) -> dict:
    """Post-render sanity: exists, has both streams, duration within 1.5 s."""
    proc = subprocess.run(
        [
            ffmpeg_bin.ffprobe(), "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(out_path),
        ],
        capture_output=True, text=True, timeout=120,
    )
    import json

    info = json.loads(proc.stdout or "{}")
    streams = info.get("streams", [])
    has_v = any(s.get("codec_type") == "video" for s in streams)
    has_a = any(s.get("codec_type") == "audio" for s in streams)
    duration = float(info.get("format", {}).get("duration", 0.0))
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    return {
        "ok": has_v and has_a and abs(duration - expected_duration) < 1.5,
        "duration": duration,
        "width": video.get("width"),
        "height": video.get("height"),
    }
