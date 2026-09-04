"""Candidates stage: signals to story-unit variants.

The stage keeps scene cuts as supporting evidence, then constructs variable
story spans before bounded local editorial boundary selection.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..jobs.queue import Stage, StageContext, StageError, _atomic_write_json


def detect_scenes(media_path: str, progress=None) -> list[float]:
    """Scene-change timestamps via PySceneDetect ContentDetector (BSD-3) on
    a downscaled decode. On a static podcast this returns camera cuts; on
    gaming/vlog footage it captures visual pacing."""
    from scenedetect import ContentDetector, open_video
    from scenedetect.scene_manager import SceneManager

    video = open_video(media_path)
    manager = SceneManager()
    manager.add_detector(ContentDetector(threshold=27.0))
    manager.auto_downscale = True
    manager.detect_scenes(video, show_progress=False)
    return [start.get_seconds() for start, _ in manager.get_scene_list()]


class CandidatesStage(Stage):
    name = "candidates"
    schema_version = 15  # v15: favor thirty-second payoff variants

    def run(self, ctx: StageContext) -> dict:
        import numpy as np

        from . import curve as curve_mod
        from . import story_units

        prior = ctx.prior or {}
        ingest = prior.get("ingest")
        diarize = prior.get("diarize")
        events = prior.get("events")
        if not (ingest and diarize and events):
            raise StageError("Candidates need ingest + diarize + events outputs.")

        segments = diarize["segments"]
        duration = float(ingest["probe"]["duration_sec"])
        n = int(np.ceil(duration))

        curves_path = Path(events["curves_path"])
        if not curves_path.exists():
            raise StageError("curves.json missing — re-run events.")
        curves = json.loads(curves_path.read_text())

        scenes_path = ctx.job_dir / "scenes.json"
        if scenes_path.exists():
            try:
                scene_times = json.loads(scenes_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                scene_times = []
        else:
            ctx.emit(-1, "Detecting scene changes…")
            try:
                scene_times = detect_scenes(ingest["media_path"])
            except Exception:  # noqa: BLE001 — scenes are a minor channel; degrade
                scene_times = []
            _atomic_write_json(scenes_path, scene_times)

        ctx.emit(0.6, "Building interest curve…")
        channels = {
            "heatmap": curve_mod.heatmap_channel(ingest.get("heatmap"), n),
            "dynamics": curve_mod.dynamics_channel(curves["dynamics"], curves["grid_sec"], n),
            "events": curve_mod.events_channel(events["timeline"], n),
            "turns": curve_mod.turns_channel(diarize["turns"], n),
            "arousal": curve_mod.arousal_channel(
                curves.get("arousal", []), curves.get("arousal_grid_sec", 0.5), n
            ),
            "scenes": curve_mod.scenes_channel(scene_times, n),
            "lexical": curve_mod.lexical_channel(segments, n),
        }
        curve, effective_weights = curve_mod.interest_curve(channels)

        ctx.emit(0.8, "Building story candidates…")
        units = story_units.build_sentence_units(
            segments,
            scene_times=scene_times,
            timeline=events["timeline"],
            interest_curve=curve.tolist(),
        )

        boundary_client = None
        boundary_attempts = 0
        try:
            from ..scoring import providers as providers_mod

            profile = providers_mod.profile_from_snapshot(ctx.settings.provider_snapshot())
            if profile.capabilities.local:
                client = providers_mod.make_adapter(profile)

                def propose(neighborhood, _anchor):
                    nonlocal boundary_attempts
                    boundary_attempts += 1
                    try:
                        payload = client.generate_json(
                            story_units.boundary_prompt(neighborhood),
                            story_units.BOUNDARY_SCHEMA,
                            purpose="boundary",
                            job_id=ctx.job_dir.name,
                        )
                    except Exception as err:  # noqa: BLE001 — deterministic fallback remains valid
                        ctx.emit(-1, f"Boundary proposal unavailable: {err}")
                        return []
                    proposal = story_units.parse_boundary_proposal(payload, neighborhood)
                    return [proposal] if proposal else []

                boundary_client = propose
        except Exception:  # noqa: BLE001 — scoring may still use a cloud provider
            boundary_client = None

        synthesis = story_units.synthesize(
            units,
            channels={name: values.tolist() for name, values in channels.items()},
            boundary_proposer=boundary_client,
            anchor_limit=story_units.ANCHOR_LIMIT,
            boundary_limit=story_units.MAX_BOUNDARY_CALLS,
            shortlist_limit=story_units.SHORTLIST_LIMIT,
        )
        candidates = synthesis["candidates"]
        if not candidates:
            raise StageError(
                "No complete story candidates found — the video may be too quiet or fragmented."
            )

        # Persist the curve for the review UI's timeline visualization.
        interest_curve_path = ctx.job_dir / "interest_curve.json"
        _atomic_write_json(
            interest_curve_path,
            {"per_sec": np.round(curve, 4).tolist()},
        )

        return {
            "candidates": candidates,
            "count": len(candidates),
            "sentence_units": synthesis["units"],
            "topic_segment_count": synthesis["topic_segment_count"],
            "anchors": synthesis["anchors"],
            "raw_span_variants": synthesis["raw_span_variants"],
            "cheap_survivors": synthesis["cheap_survivors"],
            "boundary_calls": boundary_attempts,
            "effective_weights": effective_weights,
            "scene_count": len(scene_times),
            "heatmap_present": bool(ingest.get("heatmap")),
            "artifact_paths": {
                "scenes_path": str(scenes_path),
                "interest_curve_path": str(interest_curve_path),
            },
        }
