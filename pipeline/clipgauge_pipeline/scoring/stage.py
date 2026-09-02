"""Scoring stage: deterministic pre-ranking → bounded T1 rubric scoring →
cross-validation → finalists → optional visual pass and music guidance.

Cloud providers keep the richer historical path.  The local provider has a
strict expensive-work budget so a long source cannot accidentally turn dozens
of candidate windows into an hour of sequential local-model generations.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..jobs.queue import Stage, StageContext, StageError
from ..music import brief as music_brief
from . import constants as constants_mod
from . import frames as frames_mod
from . import llm as llm_mod
from . import providers as providers_mod
from . import rubric
from . import short_quality

SELECT_COUNT = 12
LOCAL_T1_CANDIDATE_LIMIT = 10
LOCAL_FINALIST_LIMIT = 6


def scoring_budget(*, local: bool, candidate_count: int) -> dict[str, int | bool]:
    """Return the deterministic expensive-work ceiling for one scoring run."""
    count = max(0, int(candidate_count))
    return {
        "candidate_count": count,
        "t1_limit": min(count, LOCAL_T1_CANDIDATE_LIMIT) if local else count,
        "finalist_limit": LOCAL_FINALIST_LIMIT if local else SELECT_COUNT,
        "music_llm": not local,
    }


def _transcript_slice(segments: list[dict], start: float, end: float) -> tuple[str, str]:
    """(speaker-labeled transcript, flat text) for a window."""
    lines: list[str] = []
    flat: list[str] = []
    for seg in segments:
        if seg["end"] < start or seg["start"] > end:
            continue
        words = [w for w in seg.get("words", []) if start <= w["start"] < end]
        if not words:
            continue
        text = " ".join(w["word"] for w in words)
        speaker = seg.get("speaker", 0)
        lines.append(f"S{speaker}: {text}")
        flat.append(text)
    return "\n".join(lines), " ".join(flat)


def _repair_to_segment_boundary(
    segments: list[dict],
    start: float,
    end: float,
    *,
    max_extension: float = 7.0,
) -> tuple[float, bool]:
    """Use one bounded ASR utterance when punctuation is unavailable."""
    for segment in segments:
        segment_start = float(segment.get("start", 0.0))
        segment_end = float(segment.get("end", 0.0))
        if segment_start <= end <= segment_end and segment_end - end <= 0.5:
            return round(end, 3), True
        if segment_start <= end < segment_end and segment_end - end <= max_extension:
            return round(segment_end, 3), True
    return round(end, 3), False


def _events_in(timeline: list[dict], start: float, end: float, pad: float = 0.0) -> list[dict]:
    return [e for e in timeline if e["end"] >= start - pad and e["start"] <= end + pad]


def _events_desc(events: list[dict]) -> str:
    if not events:
        return "none detected"
    parts = []
    for e in events[:12]:
        parts.append(f"{e['type']} at {e['start'] - 0:.0f}s (conf {e.get('confidence', 0):.2f})")
    return "; ".join(parts)


def _window_pct(values: np.ndarray, grid_sec: float, start: float, end: float) -> float:
    """Percentile rank of this window's mean vs the whole video."""
    if len(values) == 0:
        return 0.0
    a, b = int(start / grid_sec), max(int(start / grid_sec) + 1, int(end / grid_sec))
    window_mean = float(np.mean(values[a : min(b, len(values))])) if a < len(values) else 0.0
    return float(np.mean(values <= window_mean))


def _local_prerank(item: tuple[dict, str, str]) -> tuple[float, float, float]:
    """Cheap deterministic ordering before any local-model call.

    Candidate generation already combines signal curves.  Reuse those signals
    rather than asking the LLM to rediscover whether all 30-40 windows deserve
    an expensive semantic pass.
    """
    cand = item[0]
    channels = cand.get("channel_scores") or {}
    if isinstance(channels, dict):
        channel_values = [float(value) for value in channels.values() if isinstance(value, (int, float))]
    elif isinstance(channels, list):
        channel_values = [float(value) for value in channels if isinstance(value, (int, float))]
    else:
        channel_values = []
    return (
        float(cand.get("curve_score", 0.0)),
        max(channel_values, default=0.0),
        sum(channel_values),
    )


def shortlist_local_candidates(
    candidates: list[dict], segments: list[dict], limit: int = LOCAL_T1_CANDIDATE_LIMIT
) -> list[tuple[dict, str, str]]:
    """Prepare and deterministically cap expensive local scoring work."""
    prepared: list[tuple[dict, str, str]] = []
    for candidate in candidates:
        labeled, flat = _transcript_slice(segments, candidate["start"], candidate["end"])
        if len(flat.split()) >= 20:
            prepared.append((candidate, labeled, flat))
    prepared.sort(key=_local_prerank, reverse=True)
    return prepared[: max(0, int(limit))]


def select_diverse_finalists(entries: list[dict], limit: int = LOCAL_FINALIST_LIMIT) -> list[dict]:
    """Select strong clips while suppressing nearby redundant moments."""
    remaining = [
        dict(entry) for entry in entries
        if entry.get("eligible_to_recommend", True)
    ]
    selected: list[dict] = []
    separation = 120.0
    while remaining and len(selected) < max(0, int(limit)):
        def utility(entry: dict) -> tuple[float, float, float]:
            base = float(entry.get("recommendation_score", entry.get("score", 0.0)))
            midpoint = (float(entry.get("start", 0.0)) + float(entry.get("end", 0.0))) / 2.0
            if not selected:
                penalty = 0.0
            else:
                distance = min(
                    abs(midpoint - ((float(item.get("start", 0.0)) + float(item.get("end", 0.0))) / 2.0))
                    for item in selected
                )
                penalty = max(0.0, (separation - distance) / separation * 35.0)
            return (base - penalty, base, -float(entry.get("start", 0.0)))

        winner = max(remaining, key=utility)
        selected.append(winner)
        remaining.remove(winner)
    return selected


class ScoreStage(Stage):
    name = "score"
    schema_version = 4  # v4: reject every scored quality-floor violation

    def run(self, ctx: StageContext) -> dict:
        prior = ctx.prior or {}
        ingest = prior.get("ingest")
        diarize = prior.get("diarize")
        events = prior.get("events")
        cands = prior.get("candidates")
        if not (ingest and diarize and events and cands):
            raise StageError("Scoring needs ingest + diarize + events + candidates.")

        provider_snapshot = ctx.settings.provider_snapshot()
        try:
            profile = providers_mod.profile_from_snapshot(provider_snapshot)
            client = providers_mod.make_adapter(profile)
        except (llm_mod.LlmError, ValueError) as err:
            raise StageError(str(err)) from err
        llm_mode = profile.kind
        is_local = bool(profile.capabilities.local)

        segments = diarize["segments"]
        timeline = events["timeline"]
        curves = json.loads(Path(events["curves_path"]).read_text())
        arousal = np.asarray(curves.get("arousal", []), dtype=float)
        arousal_grid = float(curves.get("arousal_grid_sec", 0.5))
        arousal_source = curves.get("arousal_source", "dsp-proxy")
        heatmap = ingest.get("heatmap")
        scene_times = json.loads((ctx.job_dir / "scenes.json").read_text()) if (ctx.job_dir / "scenes.json").exists() else []

        heat_values = None
        if heatmap:
            duration = float(ingest["probe"]["duration_sec"])
            heat_values = np.zeros(int(np.ceil(duration)))
            for seg in heatmap:
                a, b = int(seg["start_time"]), int(np.ceil(seg["end_time"]))
                heat_values[max(0, a) : min(len(heat_values), b)] = seg["value"]

        # Calibrated constants (decision #13): loaded once per run, version
        # stamped into every clip's provenance.
        scoring_config = constants_mod.active()
        cv_constants = scoring_config["constants"]

        candidates = cands["candidates"]
        budget = scoring_budget(local=is_local, candidate_count=len(candidates))

        # Slice transcripts first so short/non-speech windows do not consume the
        # local model-call budget.  Cloud mode retains the original candidate
        # order and full semantic pass; local mode cheaply pre-ranks viable
        # windows and sends only the best bounded subset to the model.
        if is_local:
            prepared = shortlist_local_candidates(candidates, segments, int(budget["t1_limit"]))
        else:
            prepared = []
            for cand in candidates:
                labeled, flat = _transcript_slice(segments, cand["start"], cand["end"])
                if len(flat.split()) >= 20:
                    prepared.append((cand, labeled, flat))

        scored: list[dict] = []
        t1_calls = 0
        for i, (cand, labeled, flat) in enumerate(prepared):
            start, end = cand["start"], cand["end"]
            ctx.emit(i / max(1, len(prepared)) * 0.6, f"Scoring moment {i + 1}/{len(prepared)}…")
            window_events = _events_in(timeline, start, end)
            near_laughs = [e for e in _events_in(timeline, start, end, pad=3.0) if e["type"] == "laugh"]
            context = {
                "duration": end - start,
                "events_desc": _events_desc(window_events),
            }
            try:
                t1_calls += 1
                t1 = client.generate_json(rubric.t1_prompt(labeled, context), rubric.T1_SCHEMA)
            except llm_mod.LlmError:
                raise
            except Exception as err:  # noqa: BLE001
                ctx.emit(-1, f"moment {i + 1} scoring failed, skipping: {err}")
                continue

            quality = short_quality.assess(flat, window_events, end - start, llm=t1)
            arousal_pct = _window_pct(arousal, arousal_grid, start, end)
            heatmap_pct = (
                _window_pct(heat_values, 1.0, start, end) if heat_values is not None else None
            )
            sub, adjustments = rubric.cross_validate(
                t1,
                laughs_near=near_laughs,
                arousal_pct=arousal_pct,
                heatmap_pct=heatmap_pct,
                constants=cv_constants,
            )
            scored.append(
                {
                    "start": start,
                    "end": end,
                    "curve_score": cand["curve_score"],
                    "channel_scores": cand["channel_scores"],
                    "t1_raw": t1,
                    "subscores": {k: round(v, 2) for k, v in sub.items()},
                    "adjustments": adjustments,
                    "arousal_pct": round(arousal_pct, 3),
                    "heatmap_pct": round(heatmap_pct, 3) if heatmap_pct is not None else None,
                    "summary": t1.get("summary", ""),
                    "transcript": labeled,
                    "short_quality": quality,
                }
            )

        if not scored:
            raise StageError("No candidate produced a scoreable transcript.")

        def _apply_platform_scores(entry: dict, visual: dict | None = None) -> tuple[dict, list[dict]]:
            platform_scores, adjustments = rubric.composite(
                entry["subscores"], entry["curve_score"], entry["heatmap_pct"], visual,
                constants=cv_constants,
            )
            entry["platform_scores"] = platform_scores
            entry["platform_score"] = max(platform_scores.values())
            entry["short_quality_score"] = float(entry["short_quality"]["score"])
            entry["recommendation_score"] = short_quality.recommendation_score(
                entry["platform_score"], entry["short_quality"]
            )
            entry["score"] = entry["platform_score"]
            entry["best_platform"] = max(platform_scores, key=platform_scores.get)
            return platform_scores, adjustments

        # Compute recommendation scores before structural repair.
        for entry in scored:
            _apply_platform_scores(entry)

        # Repair every affordable candidate before ranking.  This keeps the
        # scored transcript identical to the rendered transcript and allows a
        # lower-ranked valid moment to replace a broken finalist.
        for entry in scored:
            original_start, original_end = entry["start"], entry["end"]
            refined_start, refined_end = short_quality.refine_boundaries(
                segments,
                original_start,
                original_end,
                entry.get("t1_raw"),
            )
            refined_end, segment_boundary = _repair_to_segment_boundary(
                segments, refined_start, refined_end
            )
            entry["start"], entry["end"] = refined_start, refined_end
            labeled, flat = _transcript_slice(segments, refined_start, refined_end)
            window_events = _events_in(timeline, refined_start, refined_end)
            entry["transcript"] = labeled
            entry["short_quality"] = short_quality.assess(
                flat,
                window_events,
                refined_end - refined_start,
                llm=entry.get("t1_raw"),
                segment_boundary=segment_boundary,
            )
            _apply_platform_scores(entry)
            entry["boundary_refinement"] = {
                "original_start": original_start,
                "original_end": original_end,
                "refined_start": refined_start,
                "refined_end": refined_end,
                "head_adjustment": round(refined_start - original_start, 3),
                "tail_adjustment": round(refined_end - original_end, 3),
            }

        scored = short_quality.rank(scored)
        rejected = [
            {
                "start": entry["start"],
                "end": entry["end"],
                "recommendation_score": entry["recommendation_score"],
                "rejection_reasons": entry["short_quality"].get("rejection_reasons", []),
            }
            for entry in scored
            if not entry["short_quality"].get("eligible_to_recommend", False)
        ]
        eligible = [
            entry for entry in scored
            if entry["short_quality"].get("eligible_to_recommend", False)
        ]
        finalists = select_diverse_finalists(eligible, int(budget["finalist_limit"]))

        # T2 visual pass + music brief on finalists only.  Current local models
        # are text-only and intentionally skip extra music-model generations so
        # non-essential metadata cannot dominate wall time.
        supports_vision = client.profile.capabilities.vision is True
        music_llm_calls = 0
        t2_calls = 0
        for j, entry in enumerate(finalists):
            ctx.emit(0.6 + j / max(1, len(finalists)) * 0.35, f"Visual pass {j + 1}/{len(finalists)}…")
            visual = None
            if supports_vision:
                times = frames_mod.sample_times(entry["start"], entry["end"], scene_times)
                imgs = frames_mod.extract_frames(
                    ingest["media_path"], times, ctx.job_dir / "t2frames"
                )
                if imgs:
                    try:
                        visual = client.generate_json(
                            "Rate these frames sampled from one candidate vertical clip. "
                            "Judge visual interest for short-form: expressions, motion, variety.",
                            rubric.T2_SCHEMA,
                            images=imgs,
                        )
                        t2_calls += 1
                    except Exception:  # noqa: BLE001 — visual is optional evidence
                        visual = None
            entry["t2"] = visual

            platform_scores, comp_adjustments = _apply_platform_scores(entry, visual)
            entry["adjustments"].extend(comp_adjustments)

            window_events = _events_in(timeline, entry["start"], entry["end"])
            fired, missing = rubric.signals_summary(
                laughs_near=[e for e in window_events if e["type"] == "laugh"],
                events_in_window=window_events,
                arousal_pct=entry["arousal_pct"],
                heatmap_pct=entry["heatmap_pct"],
                t2_ran=visual is not None,
                arousal_source=arousal_source,
            )
            entry["signals_fired"] = fired
            entry["signals_missing"] = missing
            provider_result = client.last_result
            structured_level = provider_result.structured_level if provider_result else client.structured_level()
            degraded_signals = list(provider_result.degraded_signals) if provider_result else []
            if not supports_vision and any("visual" in item for item in missing):
                degraded_signals.append("vision_unavailable")
            entry["confidence"] = "standard" if structured_level == "native_schema" and not profile.capabilities.local else "local-estimate" if profile.capabilities.local else "degraded"
            entry["ledger"] = {
                "score": entry["recommendation_score"],
                "platform_score": entry["platform_score"],
                "short_quality_score": entry["short_quality_score"],
                "recommendation_score": entry["recommendation_score"],
                "quality": {
                    "rubric_hook_0_10": entry["short_quality"].get("rubric_hook_0_10"),
                    "retention_hook_0_100": entry["short_quality"].get("retention_hook_0_100"),
                    "effective_hook_0_100": entry["short_quality"].get("effective_hook_0_100"),
                    "hook_disagreement": entry["short_quality"].get("hook_disagreement", False),
                    "payoff": entry["short_quality"].get("payoff"),
                    "ending_completeness": entry["short_quality"].get("ending_completeness"),
                    "complete_ending": entry["short_quality"].get("complete_ending", False),
                    "story": entry["short_quality"].get("story_shape"),
                    "story_consistent": entry["short_quality"].get("story_consistent", True),
                    "eligible_to_recommend": entry["short_quality"].get("eligible_to_recommend", False),
                },
                "composition": {
                    "subscores": entry["subscores"],
                    "curve_score": entry["curve_score"],
                    "arousal_pct": entry["arousal_pct"],
                    "heatmap_pct": entry["heatmap_pct"],
                    "visual_evidence": visual is not None,
                },
                "platform_scores": entry["platform_scores"],
                "adjustments": entry["adjustments"],
                "signals_fired": fired,
                "signals_missing": missing,
                "provenance": {
                    "llm_mode": llm_mode,
                    "provider_profile_id": profile.id,
                    "provider_kind": profile.kind,
                    "model": client.model,
                    "endpoint_identity": profile.endpoint_identity,
                    "capabilities": profile.capabilities.to_dict(),
                    "structured_level": structured_level,
                    "degraded_signals": degraded_signals,
                    "scoring_config_version": scoring_config["version"],
                    "arousal_source": arousal_source,
                    "visual_pass": supports_vision,
                },
            }

            prior_mood = music_brief.mood_prior(window_events, entry["arousal_pct"])
            if bool(budget["music_llm"]):
                try:
                    music_llm_calls += 1
                    entry["music"] = client.generate_json(
                        music_brief.music_prompt(
                            entry["summary"], entry["transcript"], prior_mood, _events_desc(window_events)
                        ),
                        music_brief.MUSIC_SCHEMA,
                    )
                    entry["music"]["mood_prior"] = prior_mood
                except Exception:  # noqa: BLE001 — a clip without a music brief still ships
                    entry["music"] = None
            else:
                entry["music"] = None

        finalists.sort(key=lambda e: (float(e.get("recommendation_score", 0.0)), -float(e.get("start", 0.0))), reverse=True)
        for entry in finalists:
            entry.pop("transcript", None)  # bulky; review UI re-slices from diarize

        return {
            "llm_mode": llm_mode,
            "provider_profile_id": profile.id,
            "provider_kind": profile.kind,
            "model": client.model,
            "capabilities": profile.capabilities.to_dict(),
            "clips": finalists,
            "rejected_candidates": rejected,
            "scored_count": len(scored),
            "t2_ran": supports_vision,
            "scoring_config_version": scoring_config["version"],
            "scoring_constants": cv_constants,
            "performance": {
                "candidate_count": len(candidates),
                "viable_candidate_count": len(prepared) if not is_local else min(len(prepared), int(budget["t1_limit"])),
                "candidate_llm_limit": int(budget["t1_limit"]),
                "t1_calls": t1_calls,
                "t2_calls": t2_calls,
                "finalist_limit": int(budget["finalist_limit"]),
                "music_llm_calls": music_llm_calls,
            },
        }
