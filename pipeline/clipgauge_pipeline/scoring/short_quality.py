"""Explainable short-form structure signals and boundary refinement."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

_TOKEN = re.compile(r"[\w']+", re.UNICODE)
_FILLER = {"um", "uh", "like", "you", "know", "basically", "actually"}
_REVEAL = {"because", "but", "then", "until", "turns", "revealed", "found", "realized"}
_REACTION = {"wow", "what", "no", "oh", "laugh", "laughed", "gasp", "gasped", "shocked", "insane"}
_HOOK_MARKERS = {"why", "how", "what", "never", "nobody", "imagine", "watch", "look"}
_PRONOUNS = {"he", "she", "they", "it", "that", "this"}
_GENERIC_REACTION_WORDS = {
    "wow", "whoa", "oh", "no", "crazy", "insane", "huge", "amazing",
    "unbelievable", "wild", "awesome", "big", "way", "really",
}
_TOPIC_STOPWORDS = {
    "a", "about", "after", "all", "an", "and", "are", "as", "at", "be",
    "because", "but", "by", "for", "from", "had", "has", "have", "he",
    "her", "here", "him", "his", "how", "i", "if", "in", "is", "it", "its",
    "me", "my", "of", "on", "or", "our", "she", "so", "that", "the", "their",
    "them", "then", "there", "they", "this", "to", "was", "we", "were", "what",
    "when", "where", "which", "who", "with", "you", "your", "just", "like",
    "really", "very", "way", "people", "look", "looks", "looking",
}
_PUNCTUATION = (".", "!", "?")
_FRAGMENT_FUNCTION_WORDS = {"and", "because", "but", "here", "or", "so", "these", "then", "to", "with"}
_GRAMMATICAL_TERMINAL_MARKERS = {"my", "our", "his", "her", "its", "their", "your", "than"}
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


def _sentence_units(text: str) -> list[set[str]]:
    units = re.split(r"[.!?]+|\n+", str(text))
    return [
        {
            token for token in _words(unit)
            if token not in _TOPIC_STOPWORDS and len(token) > 2
        }
        for unit in units
        if _words(unit)
    ]


def _generic_reaction_opening(text: str) -> bool:
    opening = re.split(r"[.!?]+", str(text), maxsplit=1)[0]
    tokens = _words(opening)
    if not tokens or len(tokens) > 8:
        return False
    allowed = _GENERIC_REACTION_WORDS | _TOPIC_STOPWORDS
    return any(token in _GENERIC_REACTION_WORDS for token in tokens) and all(
        token in allowed for token in tokens
    )


def _topic_metrics(text: str, fields: dict[str, Any]) -> dict[str, Any]:
    units = _sentence_units(text)
    if len(units) < 2:
        premise = str(fields.get("central_premise") or str(text).strip())[:160]
        return {
            "central_premise": premise,
            "narrative_beats": list(fields.get("narrative_beats") or []),
            "topic_coherence_0_100": 100.0,
            "topic_shift_count": 0,
            "late_new_topic": False,
        }
    token_counts = Counter(token for unit in units for token in unit)
    anchors = {token for token, count in token_counts.items() if count >= 2}
    shifts = 0
    novel_run = 0
    seen: set[str] = set()
    for current in units:
        continuous = bool(current.intersection(seen) or current.intersection(anchors))
        if len(current) >= 2 and seen and not continuous:
            novel_run += 1
            if novel_run == 2:
                shifts += 1
        else:
            novel_run = 0
        seen.update(current)
    earlier = set().union(*units[:-1])
    closing_reaction = bool(units[-1].intersection(_REACTION))
    late_new_topic = (
        len(units[-1]) >= 2
        and not units[-1].intersection(earlier)
        and not closing_reaction
    )
    coherence = _clamp(100.0 - shifts * 16.0 - (18.0 if late_new_topic else 0.0))
    premise = str(fields.get("central_premise") or " ".join(sorted(units[0])))[:160]
    beats = fields.get("narrative_beats")
    return {
        "central_premise": premise,
        "narrative_beats": list(beats) if isinstance(beats, list) else [],
        "topic_coherence_0_100": coherence,
        "topic_shift_count": shifts,
        "late_new_topic": late_new_topic,
    }


def _effective_hook(
    rubric_hook: float | None,
    structured_hook: float | None,
    deterministic_hook: float,
) -> tuple[float, bool]:
    """Blend independent hook signals without trusting one noisy field."""
    signals = []
    if rubric_hook is not None:
        signals.append((rubric_hook * 10.0, 0.55))
    if structured_hook is not None:
        signals.append((structured_hook * 10.0, 0.15))
    signals.append((deterministic_hook, 0.30))
    weight = sum(item[1] for item in signals)
    weighted = sum(value * signal_weight for value, signal_weight in signals) / weight
    spread = max(value for value, _ in signals) - min(value for value, _ in signals)
    disagreement = spread >= 35.0
    consistency_penalty = min(10.0, max(0.0, spread - 35.0) * 0.10)
    return round(_clamp(weighted - consistency_penalty), 1), disagreement


def recommendation_score(platform_score: float, quality: dict[str, Any]) -> float:
    """Combine platform fit with a transparent short-form quality floor."""
    score = 0.65 * _clamp(platform_score) + 0.35 * _clamp(quality.get("score", 0.0))
    effective_hook = float(quality.get("effective_hook_0_100", quality.get("hook", 0.0)))
    if effective_hook < 20.0:
        score -= 20.0
    if float(quality.get("story_shape", 0.0)) <= _STORY_SCORES["none"]:
        score -= 18.0
    if float(quality.get("ending_completeness", 0.0)) < 45.0:
        score -= 16.0
    if float(quality.get("payoff", 0.0)) <= 0.0:
        score -= 24.0
    if quality.get("story_consistent") is False:
        score -= 24.0
    if quality.get("complete_ending") is False:
        score -= 24.0
    return round(_clamp(score), 1)


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


def _deterministic(
    text: str,
    events: list[dict[str, Any]],
    duration: float,
    *,
    segment_boundary: bool = False,
    ending_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tokens = _words(text)
    first = tokens[:8]
    last = tokens[-8:]
    first_marker = bool(set(first) & _HOOK_MARKERS)
    specific_number = any(any(character.isdigit() for character in token) for token in first)
    contrast = bool(set(first) & {"but", "except", "instead", "until"})
    hook = 38.0 + (28.0 if first_marker else 0.0) + (18.0 if specific_number else 0.0) + (12.0 if contrast else 0.0)
    generic_opening = _generic_reaction_opening(text)
    if generic_opening:
        hook -= 26.0
    if first and first[0] in _FILLER:
        hook -= 22.0
    hook_reason = (
        "reaction" if generic_opening else
        "question" if first_marker and first[0] in {"why", "how", "what"} else
        "specific_reveal" if specific_number else "conflict" if contrast else "none"
    )

    has_setup = len(tokens) >= 10
    reveal_indexes = [index for index, token in enumerate(tokens) if token in _REVEAL and index >= 3]
    has_reveal = bool(reveal_indexes)
    has_reaction = bool(set(last) & _REACTION) or any(
        event.get("type") in {"laugh", "gasp", "scream", "reaction"} for event in events
    )
    terminal = last[-1] if last else ""
    evidence = ending_evidence or {}
    punctuated = bool(evidence.get("punctuated", str(text).rstrip().endswith(_PUNCTUATION)))
    structural_boundary = any(
        bool(evidence.get(key, False))
        for key in ("segment_boundary", "silence", "speaker_turn_boundary", "semantic_complete")
    ) or segment_boundary
    grammatical_fragment = (
        terminal in _FRAGMENT_FUNCTION_WORDS
        or terminal in _GRAMMATICAL_TERMINAL_MARKERS
    )
    complete_ending = bool(last and (punctuated or structural_boundary) and not grammatical_fragment)
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
        "generic_opening": generic_opening,
        "complete_ending": complete_ending,
    }


def assess(
    text: str,
    events: list[dict[str, Any]] | None = None,
    duration: float = 1.0,
    *,
    llm: dict[str, Any] | None = None,
    segment_boundary: bool = False,
    ending_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine deterministic evidence with fields from the existing T1 call."""
    evidence = _deterministic(
        text,
        events or [],
        duration,
        segment_boundary=segment_boundary,
        ending_evidence=ending_evidence,
    )
    fields = llm or {}
    deterministic_hook = evidence["hook"]
    rubric_hook = None
    rubric_value = fields.get("hook", fields.get("rubric_hook_0_10", fields.get("rubric_hook")))
    if isinstance(rubric_value, (int, float)):
        rubric_hook = _clamp(float(rubric_value), 0.0, 10.0)
    structured_hook = None
    structured_value = fields.get("hook_strength")
    if isinstance(structured_value, (int, float)):
        structured_hook = _clamp(float(structured_value), 0.0, 10.0)
    effective_hook, hook_disagreement = _effective_hook(
        rubric_hook, structured_hook, deterministic_hook
    )
    hook = effective_hook
    if fields:
        hook = effective_hook
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
        payoff = 0.45 * payoff + 0.55 * payoff_llm if evidence["has_reveal"] or evidence["has_reaction"] else payoff_llm
        ending = 0.45 * ending + 0.55 * _llm_score(fields, "ending_completeness", ending)
        reaction = 0.4 * reaction + 0.6 * _llm_score(fields, "reaction_strength", reaction)
    story_name = str(fields.get("story_shape") or "none")
    story_shape = _STORY_SCORES.get(story_name, evidence["story_shape"]) if fields.get("story_shape") else evidence["story_shape"]
    requirements = {
        "conflict_reaction": ("reaction or payoff", lambda: payoff >= 20.0 and reaction >= 20.0),
        "question_answer": ("an answer or payoff", lambda: payoff >= 20.0),
        "hook_setup_payoff": ("a payoff", lambda: payoff >= 20.0),
        "reveal": ("reveal evidence", lambda: payoff >= 20.0 and (evidence["has_reveal"] or evidence["has_reaction"])),
    }
    story_consistent = True
    story_consistency_reason = ""
    if story_name in requirements:
        requirement, check = requirements[story_name]
        story_consistent = bool(check())
        if not story_consistent:
            story_consistency_reason = f"{story_name} requires {requirement}."
    topic = _topic_metrics(text, fields)
    syntactic_complete = bool(
        str(text).rstrip().endswith(_PUNCTUATION)
        or (ending_evidence or {}).get("semantic_complete", False)
    )
    open_loop_at_end = bool(
        str(text).rstrip().endswith("?")
        or story_name == "open_ended"
    )
    semantic_closure = 82.0 if syntactic_complete else 35.0
    if open_loop_at_end:
        semantic_closure -= 35.0
    if topic["late_new_topic"]:
        semantic_closure -= 30.0
    if topic["topic_shift_count"] >= 2:
        semantic_closure -= 15.0
    llm_semantic = fields.get("semantic_closure")
    llm_relevance = fields.get("payoff_relevance_to_premise")
    rich_tier = fields.get("quality_tier")
    rich_scores_conflict = (
        rich_tier in {"GOOD", "STRONG"}
        and (
            isinstance(llm_semantic, (int, float)) and float(llm_semantic) < 6.0
            or isinstance(llm_relevance, (int, float)) and float(llm_relevance) < 5.0
        )
    )
    if isinstance(llm_semantic, (int, float)) and not rich_scores_conflict:
        semantic_closure = min(semantic_closure, _clamp(float(llm_semantic), 0.0, 10.0) * 10.0)
    semantic_closure = round(_clamp(semantic_closure), 1)
    payoff_relevance = 100.0
    if topic["late_new_topic"]:
        payoff_relevance -= 65.0
    elif topic["topic_shift_count"] >= 2:
        payoff_relevance -= min(45.0, topic["topic_shift_count"] * 20.0)
    if isinstance(llm_relevance, (int, float)) and not rich_scores_conflict:
        payoff_relevance = min(payoff_relevance, _clamp(float(llm_relevance), 0.0, 10.0) * 10.0)
    payoff_relevance = round(_clamp(payoff_relevance), 1)
    quality_flags: list[str] = []
    if evidence["generic_opening"]:
        quality_flags.append("WEAK_COLD_HOOK")
    if topic["topic_shift_count"] >= 2:
        quality_flags.append("TOPIC_DRIFT")
    if topic["late_new_topic"]:
        quality_flags.append("LATE_NEW_TOPIC")
    if semantic_closure < 60.0:
        quality_flags.append("WEAK_SEMANTIC_CLOSURE")
    if payoff_relevance < 50.0:
        quality_flags.append("PAYOFF_NOT_RELEVANT")
    score = (
        hook * 0.20 + standalone * 0.15 + setup * 0.10 + escalation * 0.10
        + payoff * 0.18 + ending * 0.10 + evidence["information_density"] * 0.08
        + evidence["visual_variety"] * 0.04 + reaction * 0.05
        - evidence["filler_ratio"] * 100.0 * 0.12
    )
    rejection_reasons = _rejection_reasons(
        complete_ending=bool(evidence["complete_ending"]),
        effective_hook=effective_hook,
        payoff=payoff,
        story_consistent=story_consistent,
        standalone=standalone,
        story_name=story_name,
    )
    structurally_valid = not rejection_reasons
    if not structurally_valid:
        quality_tier = "REJECTED"
    elif quality_flags:
        quality_tier = "STRUCTURALLY_VALID"
    elif (
        effective_hook >= 65.0
        and payoff >= 65.0
        and standalone >= 65.0
        and semantic_closure >= 70.0
        and topic["topic_coherence_0_100"] >= 75.0
        and payoff_relevance >= 65.0
    ):
        quality_tier = "STRONG"
    elif (
        effective_hook >= 40.0
        and payoff >= 45.0
        and standalone >= 55.0
        and semantic_closure >= 60.0
        and topic["topic_coherence_0_100"] >= 65.0
        and payoff_relevance >= 50.0
    ):
        quality_tier = "GOOD"
    else:
        quality_tier = "STRUCTURALLY_VALID"
    return {
        "score": round(_clamp(score), 1),
        "hook": round(_clamp(hook), 1),
        "rubric_hook_0_10": round(rubric_hook, 1) if rubric_hook is not None else None,
        "structured_hook_0_10": round(structured_hook, 1) if structured_hook is not None else None,
        "deterministic_hook_0_100": round(_clamp(deterministic_hook), 1),
        "retention_hook_0_100": round(_clamp(deterministic_hook), 1),
        "effective_hook_0_100": round(_clamp(effective_hook), 1),
        "hook_disagreement": bool(hook_disagreement),
        "hook_reason": str(fields.get("hook_reason") or evidence["hook_reason"]),
        "standalone": round(_clamp(standalone), 1),
        "setup": round(_clamp(setup), 1),
        "escalation": round(_clamp(escalation), 1),
        "story_shape": round(_clamp(story_shape), 1),
        "story": story_name,
        "payoff": round(_clamp(payoff), 1),
        "payoff_location": str(fields.get("payoff_location", "none")),
        "ending_completeness": round(_clamp(ending), 1),
        "complete_ending": bool(evidence["complete_ending"]),
        "syntactic_complete": syntactic_complete,
        "semantic_closure_0_100": semantic_closure,
        "open_loop_at_end": open_loop_at_end,
        "central_premise": topic["central_premise"],
        "narrative_beats": topic["narrative_beats"],
        "topic_coherence_0_100": round(topic["topic_coherence_0_100"], 1),
        "topic_shift_count": topic["topic_shift_count"],
        "late_new_topic": topic["late_new_topic"],
        "payoff_relevance_to_premise": payoff_relevance,
        "ending_evidence": {
            "punctuated": bool(
                (ending_evidence or {}).get(
                    "punctuated", str(text).rstrip().endswith(_PUNCTUATION)
                )
            ),
            "segment_boundary": bool(
                (ending_evidence or {}).get("segment_boundary", segment_boundary)
            ),
            "silence": bool((ending_evidence or {}).get("silence", False)),
            "speaker_turn_boundary": bool(
                (ending_evidence or {}).get("speaker_turn_boundary", False)
            ),
            "semantic_complete": bool(
                (ending_evidence or {}).get("semantic_complete", False)
            ),
        },
        "information_density": round(evidence["information_density"], 1),
        "reaction_strength": round(_clamp(reaction), 1),
        "filler_ratio": round(evidence["filler_ratio"], 3),
        "speech_density": round(evidence["speech_density"], 1),
        "visual_variety": round(evidence["visual_variety"], 1),
        "emotional_variety": round(evidence["emotional_variety"], 1),
        "loopability": round(evidence["loopability"], 1),
        "story_consistent": story_consistent,
        "story_consistency_reason": story_consistency_reason,
        "eligible_to_recommend": not rejection_reasons,
        "rejection_reasons": rejection_reasons,
        "quality_flags": quality_flags,
        "structurally_valid": structurally_valid,
        "strong_recommendation": quality_tier == "STRONG",
        "quality_tier": quality_tier,
        "llm_structured": bool(fields),
    }


def _rejection_reasons(
    *,
    complete_ending: bool,
    effective_hook: float,
    payoff: float,
    story_consistent: bool,
    standalone: float,
    story_name: str,
) -> list[str]:
    reasons: list[str] = []
    if not complete_ending:
        reasons.append("INCOMPLETE_ENDING")
    if standalone < 40.0:
        reasons.append("LOW_STANDALONE_CONTEXT")
    if effective_hook < 15.0:
        reasons.append("EXTREMELY_WEAK_HOOK")
    if story_name in {"conflict_reaction", "question_answer", "hook_setup_payoff", "reveal"} and payoff <= 0.0:
        reasons.append("MISSING_PAYOFF")
    if not story_consistent:
        reasons.append("STORY_INCONSISTENT")
    return reasons


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
        if str(words[last].get("word", "")).rstrip().endswith(_PUNCTUATION):
            break
        last += 1
        if str(words[last].get("word", "")).rstrip().endswith(_PUNCTUATION):
            break
    return round(float(words[first]["start"]), 3), round(float(words[last]["end"]), 3)


def refine_boundaries(
    segments: list[dict[str, Any]],
    start: float,
    end: float,
    fields: dict[str, Any] | None = None,
    *,
    max_extension: float = 7.0,
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
            -float(item.get("recommendation_score", item.get("short_quality", {}).get("score", 0.0))),
            item.get("start", 0.0),
            item.get("end", 0.0),
        ),
    )


def select_eligible_finalists(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Return only structurally valid finalists, up to the product maximum."""
    eligible = [
        item for item in candidates
        if item.get("eligible_to_recommend", True) and not item.get("rejection_reasons")
    ]
    return rank(eligible)[: max(0, int(limit))]
