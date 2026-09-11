"""Scoring stage: deterministic pre-ranking → bounded T1 rubric scoring →
cross-validation → finalists → optional visual pass and music guidance.

Cloud providers keep the richer historical path.  The local provider has a
strict expensive-work budget so a long source cannot accidentally turn dozens
of candidate windows into an hour of sequential local-model generations.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from .. import config, protocol
from ..jobs.queue import Stage, StageContext, StageError, _atomic_write_json
from ..music import brief as music_brief
from . import constants as constants_mod
from . import frames as frames_mod
from . import llm as llm_mod
from . import providers as providers_mod
from . import rubric, short_quality

SELECT_COUNT = 12
LOCAL_T1_CANDIDATE_LIMIT = 20
LOCAL_T1_ROUND_SIZE = 10
LOCAL_T1_MIN_CALLS = 12
LOCAL_STRONG_MINIMUM = 3
LOCAL_T1_WALL_BUDGET_SECONDS = 180.0
CLOUD_T1_WALL_BUDGET_SECONDS = 180.0
LOCAL_FINALIST_LIMIT = 6
PAYOFF_TAIL_BONUS_MAX = 8.0
LOCAL_RECOVERABLE_PROVIDER_CODES = {
    "PROVIDER_UNAVAILABLE",
    "NETWORK_FAILED",
    "TIMEOUT",
    "STRUCTURED_OUTPUT_INVALID",
    "PROVIDER_RESPONSE_INVALID",
    "INTERNAL_PROVIDER_ERROR",
}


def _scoring_failure_code(
    error: providers_mod.ProviderError,
    *,
    provider_kind: str = "clipgauge-local",
) -> str:
    if provider_kind != "clipgauge-local":
        return error.code
    if error.code == "TIMEOUT":
        return "LOCAL_SCORING_TIMEOUT"
    if error.code in {"STRUCTURED_OUTPUT_INVALID", "PROVIDER_RESPONSE_INVALID"}:
        return "LOCAL_SCORING_INVALID_OUTPUT"
    if error.code == "PROVIDER_UNAVAILABLE" and (
        error.details.get("runtime_alive") is False
        or error.details.get("runtime_exit_code") is not None
    ):
        return "LOCAL_SCORING_RUNTIME_EXITED"
    return "LOCAL_SCORING_UNAVAILABLE"


def _safe_failure_record(
    error: providers_mod.ProviderError,
    *,
    provider_kind: str = "clipgauge-local",
) -> dict:
    safe_keys = {
        "provider_code",
        "provider_kind",
        "request_number",
        "elapsed_ms",
        "timeout_seconds",
        "structured_level",
        "structured_output_status",
        "free_disk_bytes",
        "client_rss_kb",
        "server_rss_kb",
        "mem_available_kb",
        "runtime_alive",
        "runtime_pid",
        "runtime_exit_code",
        "http_status",
    }
    return {
        "code": _scoring_failure_code(error, provider_kind=provider_kind),
        "provider_code": error.code,
        "details": {
            key: value for key, value in error.details.items() if key in safe_keys
        },
    }


def _unexpected_scoring_failure_code(provider_kind: str) -> str:
    return "LOCAL_SCORING_UNAVAILABLE" if provider_kind == "clipgauge-local" else "INTERNAL_PROVIDER_ERROR"


def recommendation_outcome(
    *,
    candidate_count: int,
    eligible_candidate_count: int,
    scored_count: int,
    clips: list[dict],
    rejection_reason_counts: dict[str, int] | None = None,
    best_candidate: dict | None = None,
) -> dict:
    """Describe scoring completion without conflating empty recommendations with failure."""
    has_clips = bool(clips)
    return {
        "outcome": "SUCCESS_WITH_CLIPS" if has_clips else "SUCCESS_NO_RECOMMENDATIONS",
        "code": "OK" if has_clips else "NO_RECOMMENDED_CLIPS",
        "counts": {
            "candidate_count": max(0, int(candidate_count)),
            "eligible_candidate_count": max(0, int(eligible_candidate_count)),
            "scored_count": max(0, int(scored_count)),
            "score_clip_count": len(clips),
            "camera_trajectory_count": 0,
            "render_attempt_count": 0,
            "render_output_count": 0,
            "rejection_reason_counts": dict(rejection_reason_counts or {}),
        },
        "best_candidate": best_candidate if not has_clips else None,
    }


def apply_output_preference(
    finalists: list[dict], preference: str, borderline: list[dict] | None = None, limit: int = 12
) -> list[dict]:
    """Apply output controls without promoting rejected candidates."""
    if preference == "best":
        return finalists[:2]
    if preference == "more":
        extra = list(borderline or [])
        return (finalists + extra)[: max(1, int(limit))]
    return finalists


def scoring_budget(*, local: bool, candidate_count: int) -> dict[str, int | float | bool]:
    """Return the deterministic expensive-work ceiling for one scoring run."""
    count = max(0, int(candidate_count))
    return {
        "candidate_count": count,
        "t1_limit": count,
        "tier_two_limit": min(count, LOCAL_T1_CANDIDATE_LIMIT) if local else count,
        "wall_time_seconds": LOCAL_T1_WALL_BUDGET_SECONDS if local else CLOUD_T1_WALL_BUDGET_SECONDS,
        "finalist_limit": LOCAL_FINALIST_LIMIT if local else SELECT_COUNT,
        "music_llm": not local,
    }


def _transcript_slice(
    segments: list[dict],
    start: float,
    end: float,
    *,
    include_sentence_ids: bool = False,
) -> tuple[str, str]:
    """(speaker-labeled transcript, flat text) for a window."""
    lines: list[str] = []
    flat: list[str] = []
    for index, seg in enumerate(segments):
        if seg["end"] < start or seg["start"] > end:
            continue
        words = [w for w in seg.get("words", []) if start <= w["start"] < end]
        if not words:
            continue
        text = " ".join(w["word"] for w in words)
        speaker = seg.get("speaker", 0)
        if include_sentence_ids:
            lines.append(f"S{index + 1:04d} (speaker {speaker}): {text}")
        else:
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


def _generate_t1(client, prompt: str, schema: dict, sentence_ids: set[str]) -> dict:
    """Run one T1 judgment and enforce managed balanced boundaries."""
    for attempt in range(2):
        try:
            result = client.generate_json(prompt, schema)
            if schema is rubric.BALANCED_T1_SCHEMA:
                result = rubric.normalize_balanced_output(result)
                rubric.validate_balanced_output(result, sentence_ids)
            return result
        except ValueError as error:
            provider_error = providers_mod.ProviderError(
                "STRUCTURED_OUTPUT_INVALID",
                "The local scorer returned invalid structured output.",
            )
            if attempt == 0 and getattr(getattr(client, "profile", None), "kind", None) == "clipgauge-local":
                client.recover_for_scoring()
                continue
            raise provider_error from error
        except providers_mod.ProviderError as error:
            can_recover = (
                attempt == 0
                and getattr(getattr(client, "profile", None), "kind", None) == "clipgauge-local"
                and error.code in LOCAL_RECOVERABLE_PROVIDER_CODES
            )
            if not can_recover:
                raise
            client.recover_for_scoring()
    raise AssertionError("bounded scoring retry exhausted")


def _ending_evidence(
    text: str,
    segments: list[dict],
    timeline: list[dict],
    end: float,
    t1: dict,
    segment_boundary: bool,
) -> dict[str, bool]:
    """Collect independent boundary signals for structural validation."""
    nearby = [
        segment for segment in segments
        if abs(float(segment.get("start", 0.0)) - end) <= 0.35
    ]
    speakers = {
        str(segment.get("speaker")) for segment in nearby if segment.get("speaker") is not None
    }
    return {
        "punctuated": text.rstrip().endswith((".", "!", "?")),
        "segment_boundary": segment_boundary,
        "silence": any(
            event.get("type") == "pause" and abs(float(event.get("start", 0.0)) - end) <= 1.0
            for event in timeline
        ),
        "speaker_turn_boundary": len(speakers) > 0,
        "semantic_complete": float(t1.get("ending_completeness", 0.0) or 0.0) >= 7.0,
    }


def _window_pct(values: np.ndarray, grid_sec: float, start: float, end: float) -> float:
    """Percentile rank of this window's mean vs the whole video."""
    if len(values) == 0:
        return 0.0
    a, b = int(start / grid_sec), max(int(start / grid_sec) + 1, int(end / grid_sec))
    window_mean = float(np.mean(values[a : min(b, len(values))])) if a < len(values) else 0.0
    return float(np.mean(values <= window_mean))


def _local_prerank(item: tuple[dict, str, str]) -> tuple[float, ...]:
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
    flat = item[2]
    words = _words_for_prerank(flat)
    text = flat.strip()
    starts_complete = float(bool(words and words[0] not in {"um", "uh", "like"}))
    ends_complete = float(bool(text.endswith((".", "!", "?"))))
    question_or_open_loop = float(bool(
        "?" in text
        or (words and words[0] in {
            "why", "how", "what", "when", "where", "who", "imagine", "watch",
            "can", "could", "would", "did", "do", "does", "is", "are",
        })
    ))
    concrete_detail = float(bool(any(any(char.isdigit() for char in word) for word in words)))
    concrete_detail += float(bool(set(words) & {"money", "year", "years", "dollars", "percent", "first", "only"}))
    reaction = float(bool(set(words) & {"wow", "what", "no", "oh", "laugh", "laughed", "shocked", "insane"}))
    payoff_tail = 0.0
    if cand.get("payoff_candidate"):
        payoff_time = float(cand.get("payoff_time") or 0.0)
        payoff_tail = min(30.0, max(0.0, float(cand.get("end", 0.0)) - payoff_time))
    speaker_change = float(max(0, text.count("\n")))
    scene_change = float(cand.get("scene_change", cand.get("shot_change", 0.0)) or 0.0)
    context = float(bool(words and words[0] not in {"he", "she", "they", "it", "that", "this"}))
    density = min(100.0, len(words) / max(1.0, float(cand.get("end", 0.0)) - float(cand.get("start", 0.0))) * 5.0)
    overlap = float(cand.get("overlap", cand.get("redundancy", 0.0)) or 0.0)
    return (
        starts_complete, ends_complete, question_or_open_loop, concrete_detail,
        payoff_tail, reaction, speaker_change, scene_change, context, density, -overlap,
        float(cand.get("curve_score", 0.0)), max(channel_values, default=0.0),
        sum(channel_values),
    )


def _words_for_prerank(text: str) -> list[str]:
    return [word.lower() for word in text.replace("\n", " ").split() if word.strip()]


def _story_metadata(candidate: dict) -> dict:
    """Carry transparent story synthesis evidence into score checkpoints."""
    keys = (
        "candidate_id", "anchor_sentence_id", "sentence_ids", "central_premise", "hook_sentence", "hook_time",
        "setup_end", "payoff_sentence", "payoff_time", "semantic_closure", "topic_coherence",
        "topic_shift_count", "standalone_comprehension", "story_shape", "syntactic_complete",
        "story_variant", "topic_key", "boundary_confidence", "editorial_signal",
        "hook_strength", "information_density",
        "duration_fit", "start_topic_boundary", "payoff_candidate", "payoff_boundary_explicit", "source_final_boundary",
    )
    return {key: candidate.get(key) for key in keys if key in candidate}


def _payoff_tail_bonus(entry: dict) -> float:
    """Reward a bounded reaction tail after a detected payoff."""
    if not entry.get("payoff_candidate"):
        return 0.0
    payoff_time = float(entry.get("payoff_time") or 0.0)
    tail = float(entry.get("end", 0.0)) - payoff_time
    if payoff_time <= 0.0 or tail < 2.0 or tail > 30.0:
        return 0.0
    return round(min(PAYOFF_TAIL_BONUS_MAX, (tail - 2.0) * 0.8), 1)


def shortlist_local_candidates(
    candidates: list[dict],
    segments: list[dict],
    limit: int = LOCAL_T1_CANDIDATE_LIMIT,
    *,
    include_sentence_ids: bool = False,
) -> list[tuple[dict, str, str]]:
    """Prepare and deterministically cap expensive local scoring work."""
    prepared: list[tuple[dict, str, str]] = []
    for candidate in candidates:
        labeled, flat = _transcript_slice(
            segments,
            candidate["start"],
            candidate["end"],
            include_sentence_ids=include_sentence_ids,
        )
        if len(flat.split()) >= 20:
            prepared.append((candidate, labeled, flat))
    prepared.sort(key=_local_prerank, reverse=True)
    return prepared[: max(0, int(limit))]


def select_diverse_scoring_batch(
    prepared: list[tuple[dict, str, str]],
    batch_size: int,
    selected_midpoints: list[float] | None = None,
) -> list[tuple[dict, str, str]]:
    """Choose a bounded batch using prerank and temporal diversity."""
    remaining = [
        item for item in prepared
        if not any(
            item is not other
            and item[0].get("payoff_candidate")
            and other[0].get("payoff_candidate")
            and item[0].get("anchor_sentence_id") == other[0].get("anchor_sentence_id")
            and abs(float(item[0]["start"]) - float(other[0]["start"])) < 0.1
            and abs(
                float(item[0].get("payoff_time") or 0.0)
                - float(other[0].get("payoff_time") or 0.0)
            ) <= 2.0
            and float(other[0]["end"]) > float(item[0]["end"]) + 0.5
            for other in prepared
        )
    ]
    selected: list[tuple[dict, str, str]] = []
    used = list(selected_midpoints or [])
    while remaining and len(selected) < max(0, int(batch_size)):
        def key(item: tuple[dict, str, str]) -> tuple[float, ...]:
            candidate = item[0]
            midpoint = (float(candidate["start"]) + float(candidate["end"])) / 2.0
            distance = min((abs(midpoint - value) for value in used), default=10_000.0)
            prerank = _local_prerank(item)
            return (min(distance, 10_000.0), *prerank)

        winner = max(remaining, key=key)
        selected.append(winner)
        used.append((float(winner[0]["start"]) + float(winner[0]["end"])) / 2.0)
        remaining.remove(winner)
    return selected


def is_strong_recommendation(quality: dict[str, object]) -> bool:
    """Apply the final recommendation floor after structural validation."""
    return bool(
        quality.get("quality_tier") == "STRONG"
        and quality.get("eligible_to_recommend")
        and quality.get("complete_ending")
        and float(quality.get("effective_hook_0_100", 0.0)) >= 20.0
        and float(quality.get("payoff", 0.0)) >= 45.0
        and float(quality.get("standalone", 0.0)) >= 55.0
        and quality.get("story_consistent", True)
    )


def is_good_recommendation(quality: dict[str, object]) -> bool:
    """Accept only GOOD or STRONG results for final rendering."""
    return bool(
        quality.get("eligible_to_recommend")
        and quality.get("quality_tier") in {"GOOD", "STRONG"}
    )


def is_search_strong(quality: dict[str, object]) -> bool:
    """Count promising candidates before final boundary repair."""
    flags = set(quality.get("quality_flags") or [])
    # Segment-boundary evidence is collected during the repair pass.  The
    # provisional search may use the T1 ending score instead.
    flags.discard("WEAK_SEMANTIC_CLOSURE")
    rejection_reasons = set(quality.get("rejection_reasons") or [])
    provisional_ending = (
        rejection_reasons <= {"INCOMPLETE_ENDING"}
        and float(quality.get("ending_completeness", 0.0)) >= 50.0
    )
    return bool(
        (quality.get("eligible_to_recommend") or provisional_ending)
        and not flags
        and float(quality.get("effective_hook_0_100", 0.0)) >= 40.0
        and float(quality.get("payoff", 0.0)) >= 45.0
        and float(quality.get("standalone", 0.0)) >= 55.0
    )


def quality_audit(quality: dict[str, object]) -> dict[str, object]:
    """Return review metrics without transcript or private file data."""
    return {
        "rubric_hook_0_10": quality.get("rubric_hook_0_10"),
        "structured_hook_0_10": quality.get("structured_hook_0_10"),
        "deterministic_hook_0_100": quality.get("deterministic_hook_0_100"),
        "effective_hook_0_100": quality.get("effective_hook_0_100"),
        "hook_disagreement": quality.get("hook_disagreement", False),
        "payoff": quality.get("payoff"),
        "standalone": quality.get("standalone"),
        "ending_completeness": quality.get("ending_completeness"),
        "complete_ending": quality.get("complete_ending", False),
        "syntactic_complete": quality.get("syntactic_complete", False),
        "semantic_closure_0_100": quality.get("semantic_closure_0_100"),
        "open_loop_at_end": quality.get("open_loop_at_end", False),
        "central_premise": quality.get("central_premise", ""),
        "topic_coherence_0_100": quality.get("topic_coherence_0_100"),
        "topic_shift_count": quality.get("topic_shift_count", 0),
        "late_new_topic": quality.get("late_new_topic", False),
        "payoff_relevance_to_premise": quality.get("payoff_relevance_to_premise"),
        "quality_flags": quality.get("quality_flags", []),
        "quality_tier": quality.get("quality_tier", "STRUCTURALLY_VALID"),
        "story_consistent": quality.get("story_consistent", True),
        "eligible_to_recommend": quality.get("eligible_to_recommend", False),
        "structurally_valid": quality.get("structurally_valid", False),
        "strong_recommendation": quality.get("strong_recommendation", False),
    }


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


def rank_scored_candidates(entries: list[dict]) -> list[dict]:
    """Order review candidates with bounded temporal diversity."""
    eligible = [
        entry for entry in entries
        if entry.get("eligible_to_recommend", True)
    ]
    return select_diverse_finalists(eligible, len(eligible))


class ScoreStage(Stage):
    name = "score"
    schema_version = 30  # v30: transcript-verified candidate evidence hints

    def dependency_settings(self, ctx: StageContext) -> dict:
        settings = super().dependency_settings(ctx)
        settings.update({
            "rubric_version": providers_mod.RUBRIC_CACHE_VERSION,
            "scoring_constants_version": constants_mod.active().get("version", 1),
        })
        return settings

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
        requested_model = getattr(client, "requested_model", client.model)
        is_local = bool(profile.capabilities.local)
        t1_schema = (
            rubric.T1_SCHEMA
            if profile.metadata.get("managed") is False
            else rubric.schema_for_model(client.model)
        )
        include_sentence_ids = t1_schema is rubric.BALANCED_T1_SCHEMA

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
        output_preference = getattr(ctx.settings, "output_preference", "recommended")
        quality_mode = getattr(ctx.settings, "quality_mode", "private")
        try:
            config.validate_quality_mode_for_provider(quality_mode, profile.locality)
        except ValueError as err:
            raise StageError(str(err)) from err

        # Slice transcripts first so short/non-speech windows do not consume the
        # local model-call budget.  Cloud mode retains the original candidate
        # order and full semantic pass; local mode cheaply pre-ranks viable
        # windows and sends only the best bounded subset to the model.
        if is_local:
            prepared = shortlist_local_candidates(
                candidates,
                segments,
                len(candidates),
                include_sentence_ids=include_sentence_ids,
            )
        else:
            prepared = []
            for cand in candidates:
                labeled, flat = _transcript_slice(
                    segments,
                    cand["start"],
                    cand["end"],
                    include_sentence_ids=include_sentence_ids,
                )
                if len(flat.split()) >= 20:
                    prepared.append((cand, labeled, flat))

        scored: list[dict] = []
        failure_records: list[dict] = []
        t1_calls = 0
        scoring_started = time.monotonic()
        if not is_local and isinstance(client, providers_mod.ProviderAdapter):
            client.set_scoring_deadline(scoring_started + float(budget["wall_time_seconds"]))
        round_one = (
            select_diverse_scoring_batch(prepared, LOCAL_T1_ROUND_SIZE)
            if is_local else prepared
        )
        for i, (cand, labeled, flat) in enumerate(round_one):
            if float(budget["wall_time_seconds"]) > 0 and time.monotonic() - scoring_started >= float(budget["wall_time_seconds"]):
                break
            start, end = cand["start"], cand["end"]
            ctx.emit(i / max(1, len(prepared)) * 0.6, f"Scoring moment {i + 1}/{len(prepared)}…")
            window_events = _events_in(timeline, start, end)
            near_laughs = [e for e in _events_in(timeline, start, end, pad=3.0) if e["type"] == "laugh"]
            context = {
                "duration": end - start,
                "events_desc": _events_desc(window_events),
                "candidate_evidence": {
                    "hook_sentence": cand.get("hook_sentence"),
                    "payoff_sentence": cand.get("payoff_sentence"),
                    "story_shape": cand.get("story_shape"),
                    "central_premise": cand.get("central_premise"),
                },
            }
            try:
                t1_calls += 1
                t1 = _generate_t1(
                    client,
                    rubric.t1_prompt(labeled, context),
                    t1_schema,
                    set(cand.get("sentence_ids", [])),
                )
            except providers_mod.ProviderError as err:
                failure_records.append(_safe_failure_record(err, provider_kind=profile.kind))
                ctx.emit(-1, f"moment {i + 1} scoring unavailable ({failure_records[-1]['code']}); skipping")
                continue
            except Exception:  # noqa: BLE001
                failure_code = _unexpected_scoring_failure_code(profile.kind)
                failure_records.append({"code": failure_code, "provider_code": "UNEXPECTED_SCORING_ERROR", "details": {}})
                ctx.emit(-1, f"moment {i + 1} scoring unavailable ({failure_code}); skipping")
                continue

            quality = short_quality.assess(flat, window_events, end - start, llm=t1)
            arousal_pct = _window_pct(arousal, arousal_grid, start, end)
            heatmap_pct = (
                _window_pct(heat_values, 1.0, start, end) if heat_values is not None else None
            )
            sub, adjustments = rubric.cross_validate(
                t1,
                transcript=labeled,
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
                    **_story_metadata(cand),
                }
            )

        rounds_run = 1 if round_one else 0
        refill_rounds = 0
        if is_local and t1_calls < int(budget["t1_limit"]):
            refill: list[tuple[dict, str, str]] = []
            selected_midpoints: list[float] = []
            remaining: list[tuple[dict, str, str]] = []
            strong_count = sum(is_search_strong(item["short_quality"]) for item in scored)
            if t1_calls < LOCAL_T1_MIN_CALLS or strong_count < LOCAL_STRONG_MINIMUM:
                selected_midpoints = [
                    (float(item[0]["start"]) + float(item[0]["end"])) / 2.0
                    for item in round_one
                ]
                remaining = [item for item in prepared if item not in round_one]
                refill = select_diverse_scoring_batch(
                    remaining,
                    min(LOCAL_T1_ROUND_SIZE, len(remaining)),
                    selected_midpoints,
                )
                refill_calls_before = t1_calls
                for i, (cand, labeled, flat) in enumerate(refill, start=len(round_one)):
                    if time.monotonic() - scoring_started >= LOCAL_T1_WALL_BUDGET_SECONDS:
                        break
                    start, end = cand["start"], cand["end"]
                    window_events = _events_in(timeline, start, end)
                    near_laughs = [
                        e for e in _events_in(timeline, start, end, pad=3.0)
                        if e["type"] == "laugh"
                    ]
                    context = {"duration": end - start, "events_desc": _events_desc(window_events)}
                    try:
                        t1_calls += 1
                        t1 = _generate_t1(
                            client,
                            rubric.t1_prompt(labeled, context),
                            t1_schema,
                            set(cand.get("sentence_ids", [])),
                        )
                    except providers_mod.ProviderError as err:
                        failure_records.append(_safe_failure_record(err, provider_kind=profile.kind))
                        ctx.emit(-1, f"moment {i + 1} scoring unavailable ({failure_records[-1]['code']}); skipping")
                        continue
                    except Exception:  # noqa: BLE001
                        failure_code = _unexpected_scoring_failure_code(profile.kind)
                        failure_records.append({"code": failure_code, "provider_code": "UNEXPECTED_SCORING_ERROR", "details": {}})
                        ctx.emit(-1, f"moment {i + 1} scoring unavailable ({failure_code}); skipping")
                        continue
                    quality = short_quality.assess(flat, window_events, end - start, llm=t1)
                    arousal_pct = _window_pct(arousal, arousal_grid, start, end)
                    heatmap_pct = (
                        _window_pct(heat_values, 1.0, start, end) if heat_values is not None else None
                    )
                    sub, adjustments = rubric.cross_validate(
                        t1,
                        transcript=labeled,
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
                            **_story_metadata(cand),
                        }
                    )
                if refill and t1_calls > refill_calls_before:
                    rounds_run += 1
                    refill_rounds = 1
            strong_count = sum(is_search_strong(item["short_quality"]) for item in scored)
            remaining = [item for item in remaining if item not in refill]
            if remaining and (
                t1_calls < LOCAL_T1_MIN_CALLS or strong_count < LOCAL_STRONG_MINIMUM
            ):
                tier_three = select_diverse_scoring_batch(
                    remaining,
                    len(remaining),
                    selected_midpoints + [
                        (float(item[0]["start"]) + float(item[0]["end"])) / 2.0
                        for item in refill
                    ],
                )
                tier_three_calls_before = t1_calls
                for i, (cand, labeled, flat) in enumerate(tier_three, start=t1_calls):
                    if time.monotonic() - scoring_started >= LOCAL_T1_WALL_BUDGET_SECONDS:
                        break
                    start, end = cand["start"], cand["end"]
                    window_events = _events_in(timeline, start, end)
                    near_laughs = [
                        e for e in _events_in(timeline, start, end, pad=3.0)
                        if e["type"] == "laugh"
                    ]
                    context = {"duration": end - start, "events_desc": _events_desc(window_events)}
                    try:
                        t1_calls += 1
                        t1 = _generate_t1(
                            client,
                            rubric.t1_prompt(labeled, context),
                            t1_schema,
                            set(cand.get("sentence_ids", [])),
                        )
                    except providers_mod.ProviderError as err:
                        failure_records.append(_safe_failure_record(err, provider_kind=profile.kind))
                        ctx.emit(-1, f"moment {i + 1} scoring unavailable ({failure_records[-1]['code']}); skipping")
                        continue
                    except Exception:  # noqa: BLE001
                        failure_code = _unexpected_scoring_failure_code(profile.kind)
                        failure_records.append({"code": failure_code, "provider_code": "UNEXPECTED_SCORING_ERROR", "details": {}})
                        ctx.emit(-1, f"moment {i + 1} scoring unavailable ({failure_code}); skipping")
                        continue
                    quality = short_quality.assess(flat, window_events, end - start, llm=t1)
                    arousal_pct = _window_pct(arousal, arousal_grid, start, end)
                    heatmap_pct = (
                        _window_pct(heat_values, 1.0, start, end) if heat_values is not None else None
                    )
                    sub, adjustments = rubric.cross_validate(
                        t1,
                        transcript=labeled,
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
                            **_story_metadata(cand),
                        }
                    )
                if tier_three and t1_calls > tier_three_calls_before:
                    rounds_run += 1
                    refill_rounds = 2

        failure_reason_counts = dict(Counter(item["code"] for item in failure_records))
        if not scored and prepared:
            if failure_reason_counts:
                dominant_code = max(failure_reason_counts, key=failure_reason_counts.get)
            else:
                dominant_code = "LOCAL_SCORING_UNAVAILABLE"
            diagnostic_id = protocol.write_json_diagnostic(
                ctx.job_dir,
                "score",
                {
                    "code": dominant_code,
                    "provider": profile.kind,
                    "attempted_count": t1_calls,
                    "successful_count": 0,
                    "failed_count": len(failure_records),
                    "failure_reason_counts": failure_reason_counts,
                    "failures": failure_records,
                },
            )
            raise StageError(
                f"{profile.display_name} could not score any candidate.",
                code=dominant_code,
                diagnostic_id=diagnostic_id,
            )

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
            payoff_bonus = _payoff_tail_bonus(entry)
            if payoff_bonus:
                entry["recommendation_score"] = round(
                    min(100.0, entry["recommendation_score"] + payoff_bonus), 1
                )
                adjustments.append({
                    "rule": "payoff_tail_completeness",
                    "bonus": payoff_bonus,
                    "reason": "bounded reaction tail follows the detected payoff",
                })
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
                preserve_candidate_opening=float(entry.get("start_topic_boundary") or 0.0) >= 0.62,
                preserve_candidate_payoff=bool(
                    entry.get("payoff_candidate")
                    or entry.get("payoff_boundary_explicit")
                    or entry.get("source_final_boundary")
                ),
            )
            refined_end, segment_boundary = _repair_to_segment_boundary(
                segments, refined_start, refined_end
            )
            entry["start"], entry["end"] = refined_start, refined_end
            labeled, flat = _transcript_slice(
                segments,
                refined_start,
                refined_end,
                include_sentence_ids=include_sentence_ids,
            )
            window_events = _events_in(timeline, refined_start, refined_end)
            entry["transcript"] = labeled
            entry["short_quality"] = short_quality.assess(
                flat,
                window_events,
                refined_end - refined_start,
                llm=entry.get("t1_raw"),
                segment_boundary=segment_boundary,
                ending_evidence=_ending_evidence(
                    flat,
                    segments,
                    timeline,
                    refined_end,
                    entry.get("t1_raw") or {},
                    segment_boundary,
                ),
            )
            _apply_platform_scores(entry)
            entry["short_quality"]["structurally_valid"] = bool(
                entry["short_quality"].get("eligible_to_recommend", False)
            )
            entry["short_quality"]["strong_recommendation"] = is_strong_recommendation(
                entry["short_quality"]
            )
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
                "quality": quality_audit(entry["short_quality"]),
            }
            for entry in scored
            if not entry["short_quality"].get("eligible_to_recommend", False)
        ]
        eligible = [
            entry for entry in scored
            if entry["short_quality"].get("eligible_to_recommend", False)
        ]
        eligible = rank_scored_candidates(eligible)
        strong = [entry for entry in eligible if is_strong_recommendation(entry["short_quality"])]
        good = [
            entry for entry in eligible
            if entry not in strong and is_good_recommendation(entry["short_quality"])
        ]
        borderline = [entry for entry in eligible if entry not in strong and entry not in good]
        finalists = select_diverse_finalists(strong + good, int(budget["finalist_limit"]))
        borderline_for_more = borderline[: max(0, int(budget["finalist_limit"]) - len(finalists))]
        review_entries = finalists + borderline_for_more if output_preference == "more" else finalists

        # T2 visual pass + music brief on finalists only.  Current local models
        # are text-only and intentionally skip extra music-model generations so
        # non-essential metadata cannot dominate wall time.
        supports_vision = client.profile.capabilities.vision is True
        music_llm_calls = 0
        t2_calls = 0
        for j, entry in enumerate(review_entries):
            ctx.emit(0.6 + j / max(1, len(review_entries)) * 0.35, f"Visual pass {j + 1}/{len(review_entries)}…")
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
                    "structured_hook_0_10": entry["short_quality"].get("structured_hook_0_10"),
                    "deterministic_hook_0_100": entry["short_quality"].get("deterministic_hook_0_100"),
                    "retention_hook_0_100": entry["short_quality"].get("retention_hook_0_100"),
                    "effective_hook_0_100": entry["short_quality"].get("effective_hook_0_100"),
                    "hook_disagreement": entry["short_quality"].get("hook_disagreement", False),
                    "payoff": entry["short_quality"].get("payoff"),
                    "ending_completeness": entry["short_quality"].get("ending_completeness"),
                    "complete_ending": entry["short_quality"].get("complete_ending", False),
                    "syntactic_complete": entry["short_quality"].get("syntactic_complete", False),
                    "semantic_closure_0_100": entry["short_quality"].get("semantic_closure_0_100"),
                    "open_loop_at_end": entry["short_quality"].get("open_loop_at_end", False),
                    "central_premise": entry["short_quality"].get("central_premise", ""),
                    "topic_coherence_0_100": entry["short_quality"].get("topic_coherence_0_100"),
                    "topic_shift_count": entry["short_quality"].get("topic_shift_count", 0),
                    "late_new_topic": entry["short_quality"].get("late_new_topic", False),
                    "payoff_relevance_to_premise": entry["short_quality"].get("payoff_relevance_to_premise"),
                    "quality_flags": entry["short_quality"].get("quality_flags", []),
                    "quality_tier": entry["short_quality"].get("quality_tier", "STRUCTURALLY_VALID"),
                    "story": entry["short_quality"].get("story_shape"),
                    "story_consistent": entry["short_quality"].get("story_consistent", True),
                    "eligible_to_recommend": entry["short_quality"].get("eligible_to_recommend", False),
                    "strong_recommendation": is_strong_recommendation(entry["short_quality"]),
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
                    "model": getattr(client, "actual_model", client.model),
                    "requested_model": requested_model,
                    "actual_model": getattr(client, "actual_model", client.model),
                    "endpoint_identity": profile.endpoint_identity,
                    "capabilities": profile.capabilities.to_dict(),
                    "structured_level": structured_level,
                    "degraded_signals": degraded_signals,
                    "scoring_config_version": scoring_config["version"],
                    "rubric_version": providers_mod.RUBRIC_CACHE_VERSION,
                    "quality_mode": quality_mode,
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
        finalists = apply_output_preference(
            finalists,
            output_preference,
            borderline_for_more,
            int(budget["finalist_limit"]),
        )
        for entry in finalists:
            entry.pop("transcript", None)  # bulky; review UI re-slices from diarize

        rejection_reason_counts = Counter(
            reason
            for entry in rejected
            for reason in entry.get("rejection_reasons", [])
        )
        rejection_reason_counts.update(
            "STRONG_RECOMMENDATION_REQUIRED" for _ in borderline
        )
        best_candidate = None
        if not finalists and scored:
            best = scored[0]
            best_candidate = {
                "start": best["start"],
                "end": best["end"],
                "recommendation_score": best["recommendation_score"],
            }
        outcome = recommendation_outcome(
            candidate_count=len(candidates),
            eligible_candidate_count=len(eligible),
            scored_count=len(scored),
            clips=finalists,
            rejection_reason_counts=rejection_reason_counts,
            best_candidate=best_candidate,
        )

        actual_model = getattr(client, "actual_model", client.model)
        provider_metadata = getattr(ctx.settings, "provider_metadata", None)
        if isinstance(provider_metadata, dict):
            provider_metadata.update({
                "requested_model": requested_model,
                "actual_model": actual_model,
                "structured_output_mode": client.structured_level(),
                "rubric_version": providers_mod.RUBRIC_CACHE_VERSION,
                "scoring_constants_version": scoring_config["version"],
            })
        settings_snapshot = getattr(ctx.settings, "to_json", None)
        if callable(settings_snapshot):
            _atomic_write_json(ctx.job_dir / "settings.json", settings_snapshot())

        return {
            **outcome,
            "llm_mode": llm_mode,
            "provider_profile_id": profile.id,
            "provider_kind": profile.kind,
            "model": actual_model,
            "requested_model": requested_model,
            "actual_model": actual_model,
            "quality_mode": quality_mode,
            "output_preference": output_preference,
            "rubric_version": providers_mod.RUBRIC_CACHE_VERSION,
            "capabilities": profile.capabilities.to_dict(),
            "clips": finalists,
            "rejected_candidates": rejected,
            "borderline_candidates": [
                {
                    "start": entry["start"],
                    "end": entry["end"],
                    "recommendation_score": entry["recommendation_score"],
                    "reasons": ["STRONG_RECOMMENDATION_REQUIRED"],
                    "quality": quality_audit(entry["short_quality"]),
                }
                for entry in borderline
            ],
            "strong_recommendation_count": len(strong),
            "good_recommendation_count": len(good),
            "scored_count": len(scored),
            "scoring_degraded": bool(failure_records),
            "scoring_failures": {
                "attempted_count": t1_calls,
                "successful_count": len(scored),
                "failed_count": len(failure_records),
                "failure_reason_counts": failure_reason_counts,
            },
            "t2_ran": supports_vision,
            "scoring_config_version": scoring_config["version"],
            "scoring_constants": cv_constants,
            "performance": {
                "candidate_count": len(candidates),
                "viable_candidate_count": len(prepared),
                "candidate_llm_limit": len(prepared),
                "t1_calls": t1_calls,
                "attempted_count": t1_calls,
                "successful_count": len(scored),
                "failed_count": len(failure_records),
                "failure_reason_counts": failure_reason_counts,
                "hard_t1_limit": len(prepared),
                "t1_wall_budget_seconds": LOCAL_T1_WALL_BUDGET_SECONDS if is_local else None,
                "rounds_run": rounds_run,
                "refill_rounds": refill_rounds,
                "strong_recommendation_count": len(strong),
                "good_recommendation_count": len(good),
                "t2_calls": t2_calls,
                "finalist_limit": int(budget["finalist_limit"]),
                "music_llm_calls": music_llm_calls,
            },
        }
