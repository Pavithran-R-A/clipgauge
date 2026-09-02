"""Render stage: finalist clips + trajectories + captions → finished 9:16
MP4s, each verified (streams present, duration sane) before being reported."""

from __future__ import annotations

import json
import time
from pathlib import Path

from ..jobs.queue import Stage, StageContext, StageError, _atomic_write_text


def captions_allowed_for_clip(clip: dict, captions_ok: bool) -> bool:
    """Avoid caption collisions when T2 confirms source-burned text."""
    visual = clip.get("t2")
    return bool(captions_ok and not (isinstance(visual, dict) and visual.get("on_screen_text") is True))


class RenderStage(Stage):
    name = "render"
    schema_version = 7  # v7: consume refreshed scoring classifications

    def artifacts_ok(self, ctx: StageContext, data: dict) -> bool:
        if data.get("caption_preset") != ctx.settings.caption_preset:
            return False  # restyle requested → re-render
        return all(Path(c["path"]).exists() for c in data.get("outputs", []))

    def run(self, ctx: StageContext) -> dict:
        import numpy as np

        from ..captions import ass as ass_mod
        from . import ffmpeg_bin, renderer, scheduler

        caption_engine_ready = ffmpeg_bin.supports_captions()
        if not caption_engine_ready:
            ctx.emit(-1, "No caption-capable FFmpeg is ready. Open Setup Center to install the Video engine.")
            # Rendering may continue without burned captions only when the user
            # explicitly selected a caption-free workflow; the default creator
            # workflow fails closed instead of starting a hidden download.
            if ctx.settings.caption_preset not in {"none", "off"}:
                raise StageError("Caption-capable FFmpeg is not installed. Open Setup Center and choose Download for Video engine.")

        prior = ctx.prior or {}
        ingest = prior.get("ingest")
        diarize = prior.get("diarize")
        events = prior.get("events")
        score = prior.get("score")
        camera = prior.get("camera")
        if not (ingest and diarize and events and score and camera):
            raise StageError("Render needs every prior stage output.")

        media = ingest["media_path"]
        probe = ingest["probe"]
        src_w, src_h = int(probe["width"]), int(probe["height"])
        segments = diarize["segments"]
        timeline = events["timeline"]
        curves = json.loads(Path(events["curves_path"]).read_text())
        rms = curves["rms"]
        grid = float(curves["grid_sec"])

        preset = ctx.settings.caption_preset
        captions_ok = caption_engine_ready and preset not in {"none", "off"}
        emoji_ok = ass_mod.emoji_probe() if captions_ok else False
        ctx.emit(-1, f"Emoji support: {'yes' if emoji_ok else 'no (dropping emoji)'}")

        out_dir = ctx.job_dir / "clips"
        out_dir.mkdir(exist_ok=True)
        out_w, out_h = renderer.output_dimensions()
        outputs = []
        clips = score["clips"]
        render_durations: list[float] = []
        encoder = renderer.selected_video_encoder()
        concurrency = scheduler.concurrency_limit(encoder)
        for i, clip in enumerate(clips):
            traj_path = camera["trajectories"].get(str(i))
            if not traj_path or not Path(traj_path).exists():
                continue
            trajectory = json.loads(Path(traj_path).read_text())
            start, end = clip["start"], clip["end"]
            ctx.emit(i / max(1, len(clips)), f"Rendering clip {i + 1}/{len(clips)}…")

            # Words within the clip, clip-relative times.
            words = []
            for seg in segments:
                for w in seg.get("words", []):
                    if start <= w["start"] < end:
                        words.append(
                            ass_mod.Word(
                                text=w["word"],
                                start=round(w["start"] - start, 3),
                                end=round(min(w["end"], end) - start, 3),
                            )
                        )
            ass_mod.mark_emphasis(words, rms, grid, clip_start=start)
            clip_events = [
                {
                    "type": e["type"],
                    "start": round(max(0.0, e["start"] - start), 3),
                    "end": round(min(e["end"], end) - start, 3),
                }
                for e in timeline
                if e["end"] > start and e["start"] < end and e["type"] != "pause"
            ]
            ass_path = out_dir / f"clip_{i:02d}.ass"
            _atomic_write_text(
                ass_path,
                ass_mod.build_ass(
                    words,
                    clip_events,
                    preset_name=preset,
                    emoji_ok=emoji_ok,
                    output_width=out_w,
                    output_height=out_h,
                ),
            )

            out_path = out_dir / f"clip_{i:02d}.mp4"
            clip_captions_ok = captions_allowed_for_clip(clip, captions_ok)
            started_at = time.monotonic()
            try:
                used_encoder = renderer.render_clip(
                    media, out_path, start, end, trajectory,
                    ass_path if clip_captions_ok else None, ass_mod.FONTS_DIR,
                    lufs=ctx.settings.lufs_target,
                    true_peak=ctx.settings.true_peak_db,
                    src_w=src_w, src_h=src_h,
                )
                encoder = used_encoder
            except RuntimeError as err:
                raise StageError(str(err)) from err
            render_durations.append(round(time.monotonic() - started_at, 3))
            check = renderer.verify_output(out_path, end - start)
            if not check["ok"]:
                raise StageError(
                    f"Clip {i} failed verification (duration {check['duration']:.1f}s, "
                    f"{check['width']}x{check['height']})."
                )
            outputs.append(
                {
                    "clip": i,
                    "path": str(out_path),
                    "ass": str(ass_path),
                    "score": clip["score"],
                    "best_platform": clip["best_platform"],
                    "duration": round(check["duration"], 2),
                    "words": len(words),
                    "event_tags": len(clip_events),
                    "captions_suppressed": bool(captions_ok and not clip_captions_ok),
                }
            )

        if not outputs:
            raise StageError("No clips were rendered.")
        return {
            "outputs": outputs,
            "emoji_ok": emoji_ok,
            "captions_burned": captions_ok,
            "caption_preset": preset,
            "performance": {
                "encoder": encoder,
                "render_count": len(outputs),
                "concurrency_limit": concurrency,
                "observed_concurrency": 1,
                "render_durations_sec": render_durations,
                "total_render_sec": round(sum(render_durations), 3),
            },
        }
