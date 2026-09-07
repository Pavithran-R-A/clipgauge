"""Camera stage: run the director over the selected finalist clips only —
the single biggest GPU/CPU saving vs reference implementations that reframe
the whole hour (ARCHITECTURE-DRAFT stage 7)."""

from __future__ import annotations

import json
from pathlib import Path

from ..jobs.queue import Stage, StageContext, StageError, _atomic_write_json
from ..models import registry, specs


def camera_mode_for_trajectory(trajectory: dict) -> str:
    """Expose safe fallback provenance for review and diagnostics."""
    meta = trajectory.get("meta") if isinstance(trajectory, dict) else {}
    if isinstance(meta, dict) and meta.get("faceless_fallback"):
        return "static_center"
    distribution = meta.get("camera_mode_distribution") if isinstance(meta, dict) else {}
    if isinstance(distribution, dict) and distribution.get("speaker"):
        return "speaker_tracking"
    if isinstance(distribution, dict) and distribution.get("face"):
        return "face_tracking"
    return "safe_fit"


class CameraStage(Stage):
    name = "camera"
    schema_version = 8  # v8: explicit fallback provenance

    def artifacts_ok(self, ctx: StageContext, data: dict) -> bool:
        if data.get("camera_settings") != ctx.settings.camera.__dict__:
            return False  # camera style changed → re-direct
        trajectories = data.get("trajectories", {})
        if not isinstance(trajectories, dict) or any(not isinstance(path, str) for path in trajectories.values()):
            return False
        if data.get("expected_clip_count") != len(trajectories):
            return False
        return all(Path(p).exists() for p in trajectories.values())

    def run(self, ctx: StageContext) -> dict:
        import numpy as np

        from . import asd as asd_mod
        from . import director
        from .detect import FaceDetector

        prior = ctx.prior or {}
        ingest = prior.get("ingest")
        diarize = prior.get("diarize")
        events = prior.get("events")
        score = prior.get("score")
        if not (ingest and diarize and events and score):
            raise StageError("Camera needs ingest + diarize + events + score outputs.")

        media = ingest["media_path"]
        probe = ingest["probe"]
        src_w, src_h = int(probe["width"]), int(probe["height"])

        ctx.emit(-1, "Loading vision models…")
        uf = registry.ensure(specs.ULTRAFACE, lambda f, m: ctx.emit(-1, m))
        fe = registry.ensure(specs.LR_ASD_FRONTEND, lambda f, m: ctx.emit(-1, m))
        be = registry.ensure(specs.LR_ASD_BACKEND, lambda f, m: ctx.emit(-1, m))
        detector = FaceDetector(str(uf))
        model = asd_mod.AsdModel(str(fe), str(be))

        curves = json.loads(Path(events["curves_path"]).read_text())
        dynamics = np.asarray(curves["dynamics"], dtype=float)
        grid = float(curves["grid_sec"])
        turns = diarize["turns"]
        timeline = events["timeline"]

        clips = score["clips"]
        trajectories: dict[str, str] = {}
        stats = []
        for i, clip in enumerate(clips):
            start, end = clip["start"], clip["end"]
            ctx.emit(i / max(1, len(clips)), f"Directing clip {i + 1}/{len(clips)}…")
            analysis = asd_mod.analyze_clip(media, start, end, detector, model, src_w, src_h)
            clip_turns = [t for t in turns if t["end"] > start and t["start"] < end]
            traj = director.build_trajectory(
                analysis, clip_turns, timeline, dynamics, grid,
                start, end, src_w, src_h, ctx.settings,
            )
            out_path = ctx.job_dir / f"trajectory_{i:02d}.json"
            _atomic_write_json(
                out_path,
                {
                    "clip_start": start,
                    "clip_end": end,
                    "fps": traj.fps,
                    "frames": traj.frames,
                    "cuts": traj.cuts,
                    "punches": traj.punches,
                    "meta": traj.meta,
                },
            )
            trajectories[str(i)] = str(out_path)
            stats.append(
                {
                    "clip": i,
                    "camera_mode": camera_mode_for_trajectory({"meta": traj.meta}),
                    "tracks": traj.meta["tracks"],
                    "switch_cuts": traj.meta["switch_cuts"],
                    "shot_cuts": traj.meta["shot_cuts"],
                    "punches": len(traj.punches),
                }
            )

        return {
            "trajectories": trajectories,
            "expected_clip_count": len(clips),
            "stats": stats,
            "camera_settings": ctx.settings.camera.__dict__.copy(),
        }
