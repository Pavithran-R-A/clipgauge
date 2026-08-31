"""Explainable short-form structure signals and boundary refinement."""

from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(r"[\w']+", re.UNICODE)
_FILLER = {"um", "uh", "like", "you", "know", "basically", "actually"}
_REVEAL = {"because", "but", "then", "until", "turns", "revealed", "found", "realized"}
_REACTION = {"wow", "what", "no", "oh", "laugh", "laughed", "shocked", "insane"}
_HOOK_MARKERS = {"why", "how", "what", "never", "nobody", "imagine", "watch", "look"}
_PRONOUNS = {"he", "she", "they", "it", "that", "this"}
_PUNCTUATION = (".", "!", "?")
_STORY_SCORES = {
    "hook_setup_payoff": 92.0,
    "question_answer": 86.0,
    "conflict_reaction": 84.0,
    "reveal": 76.0,
    "open_ended": 42.0,
    "none": 24.0,
}


def _words(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN.findall(text)]


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _llm_score(fields: dict[str, Any], name: str, fallback: float) -> float:
    value = fields.get(name)
    return _clamp(float(value) * 10.0) if isinstance(value, (int, float)) else fallback


def _visual_evidence(events: list[dict[str, Any]]) -> float:
    """Score actual visual changes, not merely event-type cardinality."""
    scene_cuts = sum(1 for event in events if event.get("type") in {"scene_cut", "shot_change"})
    speaker_ids = {str(event.get("speaker")) for event in events if event.get("speaker") is not None}
    subject_ids: set[str] = set()
    for event in events:
        for key in ("track", "face_id", "subject_id"):
            if event.get(key) is not None:
                subject_ids.add(str(event[key]))
        subjects = event.get("subjects")
        if isinstance(subjects, list):
            subject_ids.update(str(item.get("id", index)) for index, item in enumerate(subjects) if isinstance(item, dict))
    evidence = 18.0 + min(scene_cuts, 3) * 22.0
    evidence += min(len(speaker_ids), 3) * 12.0
    evidence += min(len(subject_ids), 3) * 14.0
    return _clamp(evidence)


def _deterministic(text: str, events: list[dict[str, Any]], duration: float) -> dict[str, Any]:
    tokens = _words(text)
    first = tokens[:8]
    last = tokens[-8:]
    first_marker = bool(set(first) & _HOOK_MARKERS)
    specific_number = any(any(character.isdigit() for character in token) for token in first)
    contrast = bool(set(first) & {"but", "except", "instead", "until"})
    hook = 38.0 + (28.0 if first_marker else 0.0) + (18.0 if specific_number else 0.0) + (12.0 if contrast else 0.0)
    if first and first[0] in _FILLER:
        hook -= 22.0
    hook_reason = "question" if first_marker and first[0] in {"why", "how", "what"} else "specific_reveal" if specific_number else "conflict" if contrast else "none"

    has_setup = len(tokens) >= 10
    reveal_indexes = [index for index, token in enumerate(tokens) if token in _REVEAL and index >= 3]
    has_reveal = bool(reveal_indexes)
    has_reaction = bool(set(last) & _REACTION) or any(
        event.get("type") in {"laugh", "gasp", "scream", "reaction"} for event in events
    )
    complete_ending = bool(last and str(text).rstrip().endswith(_PUNCTUATION))
    filler_ratio = sum(token in _FILLER for token in tokens) / max(1, len(tokens))
    density = min(100.0, len(tokens) / max(1.0, duration) * 5.0)
    payoff = 76.0 if has_reaction else 62.0 if has_reveal else 28.0
    story_shape = 35.0 + (22.0 if has_setup else 0.0) + (24.0 if has_reveal else 0.0) + (16.0 if has_reaction else 0.0)
    standalone = 78.0 if len(tokens) >= 20 else 54.0
    if tokens and tokens[0] in _PRONOUNS:
        standalone -= 20.0
    return {
        "hook": _clamp(hook),
        "hook_reason": hook_reason,
        "standalone": _clamp(standalone),
        "setup": 72.0 if has_setup else 35.0,
        "escalation": 74.0 if has_reveal else 36.0,
        "payoff": payoff,
        "ending": 84.0 if complete_ending else 38.0,
        "story_shape": story_shape,
        "information_density": density,
        "reaction": 82.0 if has_reaction else 24.0,
        "filler_ratio": filler_ratio,
        "speech_density": density,
        "visual_variety": _visual_evidence(events),
        "emotional_variety": _clamp(24.0 + (28.0 if has_reaction else 0.0) + (18.0 if has_reveal else 0.0)),
        "loopability": 68.0 if complete_ending and (has_reveal or has_reaction) else 38.0,
        "has_reveal": has_reveal,
        "has_reaction": has_reaction,
        "complete_ending": complete_ending,
    }


def assess(
    text: str,
    events: list[dict[str, Any]] | None = None,
    duration: float = 1.0,
    *,
    llm: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine deterministic evidence with fields from the existing T1 call."""
    evidence = _deterministic(text, events or [], duration)
    fields = llm or {}
    hook = evidence["hook"]
    if fields:
        hook = 0.4 * hook + 0.6 * _llm_score(fields, "hook_strength", hook)
    standalone = evidence["standalone"]
    setup = evidence["setup"]
    escalation = evidence["escalation"]
    payoff = evidence["payoff"]
    ending = evidence["ending"]
    reaction = evidence["reaction"]
    if fields:
        standalone = 0.35 * standalone + 0.65 * _llm_score(fields, "standalone_comprehension", standalone)
        setup = 0.35 * setup + 0.65 * _llm_score(fields, "setup_strength", setup)
        escalation = 0.35 * escalation + 0.65 * _llm_score(fields, "escalation_strength", escalation)
        payoff_llm = _llm_score(fields, "payoff_strength", payoff)
        payoff = 0.45 * payoff + 0.55 * payoff_llm if evidence["has_reveal"] or evidence["has_reaction"] else min(50.0, payoff_llm)
        ending = 0.45 * ending + 0.55 * _llm_score(fields, "ending_completeness", ending)
        reaction = 0.4 * reaction + 0.6 * _llm_score(fields, "reaction_strength", reaction)
    story_shape = _STORY_SCORES.get(str(fields.get("story_shape")), evidence["story_shape"])
    score = (
        hook * 0.20 + standalone * 0.15 + setup * 0.10 + escalation * 0.10
        + payoff * 0.18 + ending * 0.10 + evidence["information_density"] * 0.08
        + evidence["visual_variety"] * 0.04 + reaction * 0.05
        - evidence["filler_ratio"] * 100.0 * 0.12
    )
    return {
        "score": round(_clamp(score), 1),
        "hook": round(_clamp(hook), 1),
        "hook_reason": str(fields.get("hook_reason") or evidence["hook_reason"]),
        "standalone": round(_clamp(standalone), 1),
        "setup": round(_clamp(setup), 1),
        "escalation": round(_clamp(escalation), 1),
        "story_shape": round(_clamp(story_shape), 1),
        "payoff": round(_clamp(payoff), 1),
        "payoff_location": str(fields.get("payoff_location", "none")),
        "ending_completeness": round(_clamp(ending), 1),
        "information_density": round(evidence["information_density"], 1),
        "reaction_strength": round(_clamp(reaction), 1),
        "filler_ratio": round(evidence["filler_ratio"], 3),
        "speech_density": round(evidence["speech_density"], 1),
        "visual_variety": round(evidence["visual_variety"], 1),
        "emotional_variety": round(evidence["emotional_variety"], 1),
        "loopability": round(evidence["loopability"], 1),
        "llm_structured": bool(fields),
    }


def smart_boundaries(
    words: list[dict[str, Any]],
    start: float,
    end: float,
    *,
    max_extension: float = 1.5,
) -> tuple[float, float]:
    """Refine a window without cutting words or crossing completed sentences."""
    selected = [
        (index, word) for index, word in enumerate(words)
        if float(word.get("end", 0.0)) > start and float(word.get("start", 0.0)) < end
    ]
    if not selected:
        return round(start, 3), round(end, 3)
    first = selected[0][0]
    last = selected[-1][0]
    while first > 0 and start - float(words[first - 1]["start"]) <= max_extension:
        previous = str(words[first - 1].get("word", ""))
        if previous.rstrip().endswith(_PUNCTUATION):
            break
        first -= 1
    while last + 1 < len(words) and float(words[last + 1]["end"]) - end <= max_extension:
        current = str(words[last].get("word", ""))
        last += 1
        if current.rstrip().endswith(_PUNCTUATION):
            break
    return round(float(words[first]["start"]), 3), round(float(words[last]["end"]), 3)


def refine_boundaries(
    segments: list[dict[str, Any]],
    start: float,
    end: float,
    fields: dict[str, Any] | None = None,
    *,
    max_extension: float = 1.5,
) -> tuple[float, float]:
    """Apply bounded T1 offsets, then snap against aligned words."""
    words = [
        word for segment in segments
        for word in segment.get("words", [])
        if "start" in word and "end" in word
    ]
    if not words:
        return round(start, 3), round(end, 3)
    requested_start = start
    requested_end = end
    if fields:
        offset_start = fields.get("recommended_start_offset")
        offset_end = fields.get("recommended_end_offset")
        duration = end - start
        if isinstance(offset_start, (int, float)) and 0 <= float(offset_start) <= duration:
            requested_start = start + float(offset_start)
        if isinstance(offset_end, (int, float)) and 0 < float(offset_end) <= duration:
            requested_end = start + float(offset_end)
        if requested_end <= requested_start:
            requested_start, requested_end = start, end
    return smart_boundaries(words, requested_start, requested_end, max_extension=max_extension)


def rank(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable ranking with source order as the final tie-breaker."""
    return sorted(
        candidates,
        key=lambda item: (
            -float(item.get("short_quality", {}).get("score", 0.0)),
            item.get("start", 0.0),
            item.get("end", 0.0),
        ),
    )
