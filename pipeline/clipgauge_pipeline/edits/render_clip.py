"""Single-clip render with edits applied: free bounds, dead-space keep-
ranges, per-clip caption preset + camera mode, and visual overlays.

One ffmpeg graph: split → per-range trim/atrim → concat → sendcmd crop
(remapped trajectory) → scale → overlays (enable windows, opt-in fade
animations) → caption burn (remapped words) → loudnorm. Camera re-directs
only when bounds or camera mode differ from what the run produced.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

from .. import config
from ..jobs import queue
from ..captions import ass as ass_mod
from ..render import ffmpeg_bin, renderer
from . import store
from .timeline import ClipEdit, TimeRemap, detect_dead_space, keep_ranges


def _load_stage(job_dir: Path, stage: str) -> dict:
    return json.loads((job_dir / f"{stage}.json").read_text())["data"]


def _job_path(job_dir: Path, raw_path: str | Path) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else job_dir / path


def _context_error(job_dir: Path, clip_idx: int, code: str, message: str, artifacts: list[str]) -> dict:
    return {
        "ok": False,
        "code": code,
        "error": message,
        "message": message,
        "diagnostic_id": f"edit-context-{job_dir.name}-{clip_idx}",
        "missing_or_invalid_artifacts": artifacts,
    }


def _optional_stage(job_dir: Path, stage: str, feature: str, degraded: list[str], warnings: list[str]) -> dict:
    try:
        value = _load_stage(job_dir, stage)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        degraded.append(feature)
        warnings.append(f"{feature.replace('_', ' ').capitalize()} are unavailable.")
        return {}
    if not isinstance(value, dict):
        degraded.append(feature)
        warnings.append(f"{feature.replace('_', ' ').capitalize()} are unavailable.")
        return {}
    return value


def context_for_clip_result(job_dir: Path, clip_idx: int, pad: float = 45.0) -> dict:
    """Return typed editor context with safe optional degradation."""
    degraded: list[str] = []
    warnings: list[str] = []
    try:
        ingest = _load_stage(job_dir, "ingest")
        score = _load_stage(job_dir, "score")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _context_error(
            job_dir,
            clip_idx,
            "EDIT_CONTEXT_ARTIFACTS_MISSING",
            "The source analysis is incomplete. Reopen this session after processing finishes.",
            [stage for stage in ("ingest", "score") if not (job_dir / f"{stage}.json").exists()],
        )

    probe = ingest.get("probe") if isinstance(ingest, dict) else None
    clips = score.get("clips") if isinstance(score, dict) else None
    required_invalid: list[str] = []
    if not isinstance(ingest, dict) or not isinstance(ingest.get("media_path"), str) or not isinstance(probe, dict):
        required_invalid.append("ingest")
    if not isinstance(probe, dict) or any(
        not isinstance(probe.get(key), (int, float)) or float(probe[key]) <= 0
        for key in ("duration_sec", "width", "height")
    ):
        required_invalid.append("ingest.probe")
    if not isinstance(clips, list):
        required_invalid.append("score.clips")
    if required_invalid:
        return _context_error(
            job_dir,
            clip_idx,
            "EDIT_CONTEXT_ARTIFACTS_INVALID",
            "Required editor analysis is invalid. Retry processing this session.",
            list(dict.fromkeys(required_invalid)),
        )
    if not isinstance(clip_idx, int) or clip_idx < 0 or clip_idx >= len(clips):
        return _context_error(
            job_dir,
            clip_idx,
            "EDIT_CLIP_INDEX_INVALID",
            "That clip is no longer available in this session.",
            [f"score.clips[{clip_idx}]"],
        )
    clip = clips[clip_idx]
    if not isinstance(clip, dict) or any(
        not isinstance(clip.get(key), (int, float)) for key in ("start", "end")
    ) or float(clip["end"]) <= float(clip["start"]):
        return _context_error(
            job_dir,
            clip_idx,
            "EDIT_CONTEXT_ARTIFACTS_INVALID",
            "This clip has invalid timing data. Retry processing this session.",
            [f"score.clips[{clip_idx}]"],
        )
    try:
        edit = store.edit_for_clip(job_dir, clip_idx, clip)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _context_error(
            job_dir,
            clip_idx,
            "EDIT_CONTEXT_ARTIFACTS_INVALID",
            "Saved editor settings are invalid. Reset this clip and retry.",
            ["edits.json"],
        )

    duration = float(probe["duration_sec"])
    win_a = max(0.0, edit.start - pad)
    win_b = min(duration, edit.end + pad)

    diarize = _optional_stage(job_dir, "diarize", "speaker_transcript", degraded, warnings)
    segments = diarize.get("segments", [])
    if not isinstance(segments, list):
        degraded.append("speaker_transcript")
        warnings.append("Speaker transcript is unavailable.")
        segments = []
    all_words = [
        word
        for segment in segments
        if isinstance(segment, dict) and isinstance(segment.get("words", []), list)
        for word in segment.get("words", [])
        if isinstance(word, dict)
        and isinstance(word.get("word"), str)
        and isinstance(word.get("start"), (int, float))
        and isinstance(word.get("end"), (int, float))
    ]
    words = [
        {"word": word["word"], "start": word["start"], "end": word["end"], "speaker": word.get("speaker", 0)}
        for word in all_words
        if win_a <= word["start"] <= win_b
    ]

    events = _optional_stage(job_dir, "events", "event_markers", degraded, warnings)
    timeline = events.get("timeline", [])
    if not isinstance(timeline, list):
        degraded.append("event_markers")
        warnings.append("Event markers are unavailable.")
        timeline = []
    timeline = [
        event for event in timeline
        if isinstance(event, dict)
        and isinstance(event.get("type"), str)
        and isinstance(event.get("start"), (int, float))
        and isinstance(event.get("end"), (int, float))
    ]
    clip_events = [
        event for event in timeline
        if event["type"] != "pause" and event["end"] > win_a and event["start"] < win_b
    ]

    rms: list[float] = []
    grid = 0.1
    curves_path = events.get("curves_path")
    if isinstance(curves_path, (str, Path)):
        try:
            curves = json.loads(_job_path(job_dir, curves_path).read_text())
            grid_value = curves.get("grid_sec")
            curve_values = curves.get("rms")
            if not isinstance(grid_value, (int, float)) or float(grid_value) <= 0 or not isinstance(curve_values, list):
                raise ValueError("invalid curves")
            grid = float(grid_value)
            rms = [float(value) for value in curve_values if isinstance(value, (int, float))]
            rms = rms[int(win_a / grid) : int(win_b / grid)]
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            degraded.append("audio_waveform")
            warnings.append("Audio waveform is unavailable.")
    else:
        degraded.append("audio_waveform")
        warnings.append("Audio waveform is unavailable.")

    cuts = detect_dead_space(all_words, timeline, edit.start, edit.end)

    trajectory = None
    try:
        camera = _load_stage(job_dir, "camera")
        trajectory_map = camera.get("trajectories", {})
        trajectory_file = trajectory_map.get(str(clip_idx)) if isinstance(trajectory_map, dict) else None
        if trajectory_file:
            trajectory_data = json.loads(_job_path(job_dir, trajectory_file).read_text())
            frames = trajectory_data.get("frames", [])
            if isinstance(frames, list):
                trajectory = {"fps": trajectory_data.get("fps", 25), "frames": frames}
        if trajectory is None:
            raise ValueError("trajectory unavailable")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        degraded.append("camera_trajectory")
        warnings.append("Camera trajectory is unavailable. The editor will use a centered crop.")

    run_caption_preset = "classic"
    if (job_dir / "render.json").exists():
        try:
            render = _load_stage(job_dir, "render")
            run_caption_preset = str(render.get("caption_preset", "classic"))
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            warnings.append("The saved caption preset is unavailable. Classic captions will be used.")

    context = {
        "ok": True,
        "clip_index": clip_idx,
        "clip_id": str(clip.get("clip_id") or clip.get("id") or f"clip-{clip_idx}"),
        "window": {"start": win_a, "end": win_b},
        "media_path": ingest["media_path"],
        "probe": {"width": probe["width"], "height": probe["height"]},
        "trajectory": trajectory,
        "source_duration": duration,
        "edit": edit.to_json(),
        "words": words,
        "rms": rms,
        "rms_grid": grid,
        "events": clip_events,
        "auto_cuts": cuts,
        "run_caption_preset": run_caption_preset,
        "degraded_features": list(dict.fromkeys(degraded)),
        "warnings": list(dict.fromkeys(warnings)),
    }
    return context


def context_for_clip(job_dir: Path, clip_idx: int, pad: float = 45.0) -> dict:
    """Return editor context or raise its typed error message."""
    result = context_for_clip_result(job_dir, clip_idx, pad)
    if not result["ok"]:
        raise ValueError(result["error"])
    return result


def _camera_needs_redirect(job_dir: Path, clip_idx: int, edit: ClipEdit, score_clip: dict) -> bool:
    if abs(edit.start - score_clip["start"]) > 0.05 or abs(edit.end - score_clip["end"]) > 0.05:
        return True
    if edit.camera_mode:
        try:
            camera = _load_stage(job_dir, "camera")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False
        run_mode = (camera.get("camera_settings") or {}).get("speaker_change", "cut")
        return edit.camera_mode != run_mode
    return False


def _center_trajectory(src_w: int, src_h: int, fps: float = 25.0) -> dict:
    crop_w = max(2, int(src_h * 9 / 16) // 2 * 2)
    crop_h = max(2, int(src_h) // 2 * 2)
    crop_x = max(0, (int(src_w) - crop_w) // 2 // 2 * 2)
    return {"fps": fps, "frames": [[crop_x, 0, crop_w, crop_h]]}


def _trajectory_for(job_dir: Path, clip_idx: int, edit: ClipEdit, score_clip: dict, settings: config.Settings, emit) -> dict:
    ingest = _load_stage(job_dir, "ingest")
    src_w, src_h = int(ingest["probe"]["width"]), int(ingest["probe"]["height"])
    camera_path = job_dir / "camera.json"
    if not camera_path.exists():
        return _center_trajectory(src_w, src_h)
    if not _camera_needs_redirect(job_dir, clip_idx, edit, score_clip):
        try:
            traj_path = _load_stage(job_dir, "camera")["trajectories"][str(clip_idx)]
            return json.loads(_job_path(job_dir, traj_path).read_text())
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return _center_trajectory(src_w, src_h)

    emit(-1, "Re-directing camera for new bounds…")
    import numpy as np

    from ..camera import asd as asd_mod
    from ..camera import director
    from ..camera.detect import FaceDetector
    from ..models import registry, specs

    diarize = _load_stage(job_dir, "diarize")
    events = _load_stage(job_dir, "events")
    curves = json.loads(_job_path(job_dir, events["curves_path"]).read_text())

    detector = FaceDetector(str(registry.ensure(specs.ULTRAFACE, lambda f, m: None)))
    model = asd_mod.AsdModel(
        str(registry.ensure(specs.LR_ASD_FRONTEND, lambda f, m: None)),
        str(registry.ensure(specs.LR_ASD_BACKEND, lambda f, m: None)),
    )
    cam_settings = config.CameraSettings(**{**settings.camera.__dict__})
    if edit.camera_mode:
        cam_settings.speaker_change = edit.camera_mode

    analysis = asd_mod.analyze_clip(
        str(_job_path(job_dir, ingest["media_path"])), edit.start, edit.end, detector, model, src_w, src_h
    )
    clip_turns = [t for t in diarize["turns"] if t["end"] > edit.start and t["start"] < edit.end]
    traj = director.build_trajectory(
        analysis, clip_turns, events["timeline"],
        np.asarray(curves["dynamics"], dtype=float), float(curves["grid_sec"]),
        edit.start, edit.end, src_w, src_h, cam_settings,
    )
    return {"fps": traj.fps, "frames": traj.frames, "cuts": traj.cuts, "punches": traj.punches}


def _overlay_filters(overlays, input_offset: int, out_w: int, out_h: int) -> tuple[list[str], list[str], str]:
    """(extra -i args, filter chains, final label). Base video label [vb]."""
    inputs: list[str] = []
    chains: list[str] = []
    label = "vb"
    added = 0
    for k, ov in enumerate(overlays):
        if not ov.image_path or not Path(ov.image_path).exists():
            continue
        idx = input_offset + added
        added += 1
        # Bound the looped image stream — an infinite input slows the final
        # filter flush and burns CPU decoding frames nothing will consume.
        inputs += ["-loop", "1", "-t", f"{ov.end + 1.0:.2f}", "-i", ov.image_path]
        w_px = int(out_w * ov.scale)
        pre = f"[{idx}:v]scale={w_px}:-2,pad=iw+16:ih+16:8:8:white@0.95,format=rgba"
        if ov.animation == "ping":
            dur = max(0.3, ov.end - ov.start)
            pre += (
                f",fade=in:st={ov.start:.2f}:d=0.18:alpha=1"
                f",fade=out:st={max(ov.start, ov.end - 0.18):.2f}:d=0.18:alpha=1"
            )
        elif ov.animation == "pop":
            pre += f",fade=in:st={ov.start:.2f}:d=0.1:alpha=1"
        chains.append(pre + f"[ov{k}]")
        x = f"(W-w)*{ov.x:.3f}"
        y = f"(H-h)*{ov.y:.3f}"
        nxt = f"vo{k}"
        chains.append(
            f"[{label}][ov{k}]overlay=x='{x}':y='{y}':enable='between(t,{ov.start:.2f},{ov.end:.2f})'[{nxt}]"
        )
        label = nxt
    return inputs, chains, label


def _camera_filter_chain(
    boxes: list[tuple[int, int, int, int]],
    fps: float,
    src_w: int,
    src_h: int,
) -> tuple[str, str]:
    """Build the editor camera command file and stable-shape video chain.

    The encoder-facing crop remains fixed at the output dimensions. Dynamic
    trajectory dimensions are represented by scale changes, while only the
    output crop coordinates change at runtime.
    """
    out_w, out_h = renderer.output_dimensions()
    command_text = "\n".join(renderer.render_command_lines(boxes, fps, src_w, src_h, out_w, out_h))
    w0, h0, x0, y0 = boxes[0]
    sx0 = out_w / w0
    sy0 = out_h / h0
    zoom_w0 = renderer._even(src_w * sx0)  # noqa: SLF001
    zoom_h0 = renderer._even(src_h * sy0)  # noqa: SLF001
    view_x0 = renderer._even(x0 * sx0)  # noqa: SLF001
    view_y0 = renderer._even(y0 * sy0)  # noqa: SLF001
    chain = (
        f"[vc]sendcmd=f={{cmd_path}},"
        f"scale@z=w={zoom_w0}:h={zoom_h0}:flags=lanczos,"
        f"crop@o=w={out_w}:h={out_h}:x={view_x0}:y={view_y0},setsar=1[vb]"
    )
    return command_text, chain


def video_encoder_args() -> list[str]:
    """Use the same verified encoder policy as initial renders."""
    return renderer.select_video_encoder(
        nvenc_available=renderer.nvenc_available(),
        videotoolbox_available=renderer.videotoolbox_available(),
    )


def render_clip_edit(job_dir: Path, clip_idx: int, emit) -> dict:
    """The per-clip render path. Returns the updated output entry."""
    context = context_for_clip_result(job_dir, clip_idx)
    if not context["ok"]:
        raise ValueError(f"{context['code']}: {context['error']}")
    ingest = _load_stage(job_dir, "ingest")
    degraded: list[str] = []
    warnings: list[str] = []
    diarize = _optional_stage(job_dir, "diarize", "speaker_transcript", degraded, warnings)
    events = _optional_stage(job_dir, "events", "event_markers", degraded, warnings)
    score = _load_stage(job_dir, "score")
    settings = config.Settings.from_json(json.loads((job_dir / "settings.json").read_text()))
    clip = score["clips"][clip_idx]
    edit = store.edit_for_clip(job_dir, clip_idx, clip)
    segments = diarize.get("segments", [])
    if not isinstance(segments, list):
        segments = []
    all_words = [
        word
        for segment in segments
        if isinstance(segment, dict) and isinstance(segment.get("words", []), list)
        for word in segment.get("words", [])
        if isinstance(word, dict)
        and isinstance(word.get("word"), str)
        and isinstance(word.get("start"), (int, float))
        and isinstance(word.get("end"), (int, float))
    ]
    timeline = events.get("timeline", [])
    if not isinstance(timeline, list):
        timeline = []
    timeline = [
        event for event in timeline
        if isinstance(event, dict)
        and isinstance(event.get("type"), str)
        and isinstance(event.get("start"), (int, float))
        and isinstance(event.get("end"), (int, float))
    ]

    # --- keep ranges + remap ------------------------------------------------
    if edit.remove_dead_space:
        cuts = detect_dead_space(all_words, timeline, edit.start, edit.end)
        ranges = keep_ranges(edit.start, edit.end, cuts, edit.disabled_cuts)
    else:
        ranges = [(edit.start, edit.end)]
    remap = TimeRemap(ranges)

    # --- camera -------------------------------------------------------------
    trajectory = _trajectory_for(job_dir, clip_idx, edit, clip, settings, emit)
    fps = float(trajectory.get("fps", 25))
    # Trajectory frames start at edit.start whether reused (bounds unchanged
    # → edit.start == run start) or freshly re-directed for new bounds.
    frames = remap.remap_trajectory(trajectory["frames"], fps, edit.start)

    src_w, src_h = int(ingest["probe"]["width"]), int(ingest["probe"]["height"])
    boxes = renderer.crop_boxes(frames, src_w, src_h)
    if not boxes:
        boxes = [(src_h * 9 // 16 // 2 * 2, src_h - src_h % 2, 0, 0)]

    # --- captions (remapped) ------------------------------------------------
    words_src = [
        {"word": word["word"], "start": word["start"], "end": word["end"]}
        for word in all_words
        if edit.start <= word["start"] < edit.end
    ]
    words_out = remap.remap_words(words_src)
    curves: dict = {}
    curves_path = events.get("curves_path")
    if isinstance(curves_path, (str, Path)):
        try:
            candidate = json.loads(_job_path(job_dir, curves_path).read_text())
            if isinstance(candidate, dict):
                curves = candidate
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            curves = {}
    cap_words = [ass_mod.Word(text=w["word"], start=w["start"], end=w["end"]) for w in words_out]
    # Emphasis is a SOURCE-time property (per-word RMS in the original
    # audio): mark it on source-timed copies, then carry each surviving
    # word's flag across in order.
    src_cap = [
        ass_mod.Word(text=w["word"], start=w["start"] - edit.start, end=w["end"] - edit.start)
        for w in words_src
    ]
    rms = curves.get("rms")
    grid = curves.get("grid_sec")
    if isinstance(rms, list) and isinstance(grid, (int, float)) and float(grid) > 0:
        ass_mod.mark_emphasis(src_cap, rms, float(grid), clip_start=edit.start)
    out_idx = 0
    for w_src, w_flagged in zip(words_src, src_cap):
        survives = remap.to_output((w_src["start"] + w_src["end"]) / 2) is not None
        if survives and out_idx < len(cap_words):
            cap_words[out_idx].emphasized = w_flagged.emphasized
            out_idx += 1

    clip_events_out = []
    for e in timeline:
        if e["type"] == "pause" or e["end"] <= edit.start or e["start"] >= edit.end:
            continue
        mid = (e["start"] + e["end"]) / 2
        if remap.to_output(mid) is None:
            continue
        clip_events_out.append(
            {
                "type": e["type"],
                "start": remap.to_output_clamped(e["start"]),
                "end": remap.to_output_clamped(e["end"]),
            }
        )

    preset = edit.caption_preset or settings.caption_preset
    captions_ok = ffmpeg_bin.supports_captions()
    emoji_ok = ass_mod.emoji_probe() if captions_ok else False
    out_dir = job_dir / "clips"
    out_dir.mkdir(exist_ok=True)
    ass_path = out_dir / f"clip_{clip_idx:02d}.ass"
    queue._atomic_write_text(
        ass_path,
        ass_mod.build_ass(
            cap_words,
            clip_events_out,
            preset_name=preset,
            emoji_ok=emoji_ok,
            output_width=renderer.output_dimensions()[0],
            output_height=renderer.output_dimensions()[1],
        ),
    )

    # --- build the graph ----------------------------------------------------
    emit(-1, "Rendering clip…")
    span_a = ranges[0][0]
    span_b = ranges[-1][1]
    n = len(ranges)
    trims = []
    for i, (a, b) in enumerate(ranges):
        ra, rb = a - span_a, b - span_a
        trims.append(f"[0:v]trim=start={ra:.3f}:end={rb:.3f},setpts=PTS-STARTPTS[v{i}]")
        trims.append(f"[0:a]atrim=start={ra:.3f}:end={rb:.3f},asetpts=PTS-STARTPTS[a{i}]")
    concat_in = "".join(f"[v{i}][a{i}]" for i in range(n))
    graph = trims + [f"{concat_in}concat=n={n}:v=1:a=1[vc][ac]"]

    cmd_path = out_dir / f"clip_{clip_idx:02d}.cmd"
    command_text, vchain_template = _camera_filter_chain(boxes, fps, src_w, src_h)
    queue._atomic_write_text(cmd_path, command_text + "\n")
    graph.append(vchain_template.format(cmd_path=renderer._q(cmd_path)))  # noqa: SLF001

    resolved_overlays = [
        replace(overlay, image_path=str(_job_path(job_dir, overlay.image_path)))
        if overlay.image_path
        else overlay
        for overlay in edit.overlays
    ]
    ov_inputs, ov_chains, vlabel = _overlay_filters(resolved_overlays, 1, renderer.OUT_W, renderer.OUT_H)
    graph.extend(ov_chains)
    if captions_ok:
        graph.append(
            f"[{vlabel}]subtitles=filename={renderer._q(ass_path)}:fontsdir={renderer._q(ass_mod.FONTS_DIR)}[vf]"  # noqa: SLF001
        )
        vlabel = "vf"
    graph.append(f"[ac]loudnorm=I={settings.lufs_target}:TP={settings.true_peak_db}:LRA=11[af]")

    vcodec = video_encoder_args()

    out_path = out_dir / f"clip_{clip_idx:02d}.mp4"
    args = [
        ffmpeg_bin.ffmpeg(), "-nostdin", "-y", "-v", "error",
        "-ss", f"{span_a:.3f}", "-t", f"{span_b - span_a:.3f}", "-i", str(_job_path(job_dir, ingest["media_path"])),
        *ov_inputs,
        "-filter_complex", ";".join(graph),
        "-map", f"[{vlabel}]", "-map", "[af]",
        *vcodec,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", "-map_metadata", "-1",
        str(out_path),
    ]
    proc, _used_encoder = renderer.run_ffmpeg_with_encoder_fallback(args, vcodec, 1800)
    cmd_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Clip render failed: {(proc.stderr or '')[-800:]}")

    check = renderer.verify_output(out_path, remap.output_duration)
    entry = {
        "clip": clip_idx,
        "path": str(out_path),
        "ass": str(ass_path),
        "score": clip["score"],
        "best_platform": clip["best_platform"],
        "duration": round(check["duration"], 2),
        "words": len(cap_words),
        "event_tags": len(clip_events_out),
        "edited": True,
    }

    # keep render.json in sync so the review UI reflects the new file
    render_ckpt_path = job_dir / "render.json"
    if render_ckpt_path.exists():
        ckpt = json.loads(render_ckpt_path.read_text())
        outputs = ckpt["data"].get("outputs", [])
        for i, o in enumerate(outputs):
            if o["clip"] == clip_idx:
                outputs[i] = entry
                break
        else:
            outputs.append(entry)
        job = queue.get_job(job_dir.name)
        if job is None:
            raise RuntimeError("job metadata is missing; edited output cannot be committed safely")
        queue.write_checkpoint(job, "render", int(ckpt["schema_version"]), ckpt["data"])
    return entry
