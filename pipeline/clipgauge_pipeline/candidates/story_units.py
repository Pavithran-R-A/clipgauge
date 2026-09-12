"""Story-unit candidate synthesis for short-form editorial search.

The synthesizer keeps sentence boundaries legal, uses lexical topic evidence,
and emits a small scored shortlist from a larger cheap variant pool.  Visual
cuts and audio events support boundaries; neither can split a story alone.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

MIN_STORY_SECONDS = 8.0
MAX_STORY_SECONDS = 75.0
MAX_END_LOOKAHEAD_SECONDS = 60.0
ANCHOR_LIMIT = 20
MAX_BOUNDARY_CALLS = 15
SHORTLIST_LIMIT = 24
MAX_CANDIDATES_PER_TIME_BUCKET = 4
TOPIC_BOUNDARY_THRESHOLD = 0.62
MIN_TOPIC_UNITS = 5
_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
_STOPWORDS = {
    "a", "about", "after", "all", "an", "and", "are", "as", "at", "be",
    "because", "but", "by", "can", "do", "does", "for", "from", "get",
    "go", "he", "how", "i", "if", "in", "is", "it", "like", "me", "my",
    "no", "of", "on", "or", "our", "so", "that", "the", "their", "there",
    "they", "this", "to", "up", "was", "we", "were", "what", "when", "where",
    "which", "who", "why", "will", "with", "you", "your",
}
_REACTION_WORDS = {
    "ah", "crazy", "gosh", "insane", "no", "oh", "shocked", "terrifying",
    "wait", "whoa", "wow",
}
_QUESTION_STARTS = {
    "can", "could", "did", "does", "how", "imagine", "is", "what", "when",
    "where", "who", "why", "would",
}
_FILLER_STARTS = {"all", "alright", "okay", "ok", "so", "well", "yeah", "yo"}
_PREMISE_WORDS = {"billion", "million", "secret", "dangerous", "hidden", "survive", "infinite", "classified"}
_DEICTIC_WORDS = {"this", "that", "these", "those", "he", "she", "they", "it", "there", "here"}
_CONTEXT_REFERENCES = ("as i said", "like before", "again", "then", "so far", "as before")
_OUTCOME_PHRASES = ("turns out", "ended up", "managed to", "it's official", "is official")
_OUTCOME_VERBS = {
    "built", "completed", "discovered", "earned", "failed", "finished", "found",
    "got", "landed", "lost", "made", "passed", "received", "signed", "sold", "won",
}
_EDITORIAL_TERMS = {
    "challenge", "complete", "completed", "discovered", "earned", "failed", "final",
    "finished", "found", "game", "job", "money", "passed", "price", "result",
    "signed", "survive", "team", "won", "worth",
}


@dataclass(frozen=True)
class SentenceUnit:
    sentence_id: str
    start: float
    end: float
    speaker: Any
    text: str
    scene_id: int
    audio_events: tuple[str, ...]
    interest_values: tuple[float, ...]
    tokens: frozenset[str]
    topic_id: int = 0
    topic_boundary_before: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "sentence_id": self.sentence_id,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "speaker": self.speaker,
            "text": self.text,
            "scene_id": self.scene_id,
            "audio_events": list(self.audio_events),
            "interest_values": [round(value, 4) for value in self.interest_values],
            "topic_id": self.topic_id,
            "topic_boundary_before": round(self.topic_boundary_before, 4),
        }


@dataclass(frozen=True)
class BoundaryProposal:
    best_start_sentence_id: str
    best_end_sentence_id: str
    central_premise: str
    hook_sentence_id: str
    payoff_sentence_id: str
    story_shape: str
    why_start: str
    why_end: str


def _tokens(text: str) -> frozenset[str]:
    tokens: set[str] = set()
    for raw in text.lower().split():
        token = "".join(
            character
            for character in raw
            if character == "'"
            or character.isalnum()
            or unicodedata.category(character).startswith("M")
        )
        if token and token not in _STOPWORDS and len(token) > 2:
            tokens.add(token)
    return frozenset(tokens)


def _has_explicit_outcome(text: str) -> bool:
    """Recognize generic completed outcomes without domain-specific phrases."""
    normalized = text.lower().strip()
    if any(phrase in normalized for phrase in _OUTCOME_PHRASES):
        return True
    subject = r"(?:i|we|they|he|she|you|the team|the pilot|the speaker)"
    modifier = r"(?:(?:actually|finally|successfully|just|also|still|then)\s+)*"
    verbs = "|".join(sorted(_OUTCOME_VERBS))
    return bool(re.search(rf"\b{subject}\s+{modifier}(?<![\w'])({verbs})(?![\w'])", normalized))


def _scene_id(start: float, scene_times: list[float]) -> int:
    return sum(float(scene) <= start for scene in scene_times)


def _similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _boundary_confidence(
    units: list[SentenceUnit], index: int, scene_times: list[float]
) -> float:
    if index <= 0 or index >= len(units):
        return 0.0
    left = units[index - 1]
    right = units[index]
    left_context = set().union(*(unit.tokens for unit in units[max(0, index - 2):index]))
    right_context = set().union(*(unit.tokens for unit in units[index:min(len(units), index + 2)]))
    similarity = _similarity(left_context, right_context)
    gap = max(0.0, right.start - left.end)
    scene_cut = any(left.end <= scene <= right.start for scene in scene_times)
    speaker_change = left.speaker != right.speaker
    confidence = max(0.0, 1.0 - min(1.0, similarity * 5.0)) * 0.62
    confidence += min(0.25, gap / 4.0)
    confidence += 0.12 if scene_cut else 0.0
    confidence += 0.08 if speaker_change else 0.0
    if index >= 2 and _similarity(set(units[index - 2].tokens), set(left.tokens)) >= 0.12:
        confidence -= 0.22
    return round(min(1.0, confidence), 4)


def build_sentence_units(
    segments: list[dict[str, Any]],
    scene_times: list[float] | None = None,
    timeline: list[dict[str, Any]] | None = None,
    interest_curve: list[float] | None = None,
) -> list[SentenceUnit]:
    """Build aligned ASR sentence units with cheap topic labels.

    ASR segments remain legal sentence cuts.  Long segments are retained when
    punctuation is absent, avoiding invented timings from transcript text.
    """
    scenes = sorted(float(value) for value in (scene_times or []))
    events = timeline or []
    curve = list(interest_curve) if interest_curve is not None else []
    units: list[SentenceUnit] = []
    for index, segment in enumerate(segments):
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        if end <= start:
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            text = " ".join(str(word.get("word", "")) for word in segment.get("words", [])).strip()
        audio = tuple(sorted({
            str(event.get("type"))
            for event in events
            if event.get("end", 0.0) >= start and event.get("start", 0.0) <= end
            and event.get("type") not in {"pause"}
        }))
        a, b = max(0, int(start)), min(len(curve), max(int(start) + 1, int(end) + 1))
        units.append(SentenceUnit(
            sentence_id=f"S{index + 1:04d}",
            start=start,
            end=end,
            speaker=segment.get("speaker", 0),
            text=text,
            scene_id=_scene_id(start, scenes),
            audio_events=audio,
            interest_values=tuple(float(value) for value in curve[a:b]),
            tokens=_tokens(text),
        ))

    labeled: list[SentenceUnit] = []
    topic = 0
    topic_started_at = 0
    minimum_units = 1 if len(units) <= 10 else MIN_TOPIC_UNITS
    for index, unit in enumerate(units):
        confidence = _boundary_confidence(units, index, scenes)
        if index and confidence >= TOPIC_BOUNDARY_THRESHOLD and index - topic_started_at >= minimum_units:
            topic += 1
            topic_started_at = index
        labeled.append(SentenceUnit(**{
            **unit.__dict__,
            "topic_id": topic,
            "topic_boundary_before": confidence,
        }))
    return labeled


def _mean_interest(units: list[SentenceUnit]) -> float:
    values = [value for unit in units for value in unit.interest_values]
    return sum(values) / len(values) if values else 0.0


def _anchor_strength(unit: SentenceUnit) -> float:
    words = _TOKEN_RE.findall(unit.text.lower())
    first = words[0] if words else ""
    score = max(unit.interest_values, default=0.0) * 2.0
    score += 0.45 if "?" in unit.text or first in _QUESTION_STARTS else 0.0
    score += 0.32 if any(char.isdigit() for char in unit.text) else 0.0
    score += 0.28 if set(words) & _REACTION_WORDS else 0.0
    score += 0.16 * len(unit.audio_events)
    score += 0.10 if unit.topic_boundary_before >= 0.62 else 0.0
    return score


def generate_anchors(units: list[SentenceUnit], limit: int = ANCHOR_LIMIT) -> list[SentenceUnit]:
    """Choose diverse editorial anchors, rather than fixed peak windows."""
    selected: list[SentenceUnit] = []
    max_anchors = max(0, int(limit))
    if max_anchors == 0:
        return []
    topic_best: dict[int, SentenceUnit] = {}
    for unit in units:
        if unit.topic_id not in topic_best or _anchor_strength(unit) > _anchor_strength(topic_best[unit.topic_id]):
            topic_best[unit.topic_id] = unit

    topic_starts = sorted(unit.start for unit in topic_best.values())
    topic_gaps = [right - left for left, right in zip(topic_starts, topic_starts[1:])]
    dense_topic_gap = (
        sorted(topic_gaps)[len(topic_gaps) // 2]
        if topic_gaps else (
            max((unit.end for unit in units), default=0.0)
            - min((unit.start for unit in units), default=0.0)
        ) / max(1, max_anchors - 1)
    )
    minimum_anchor_gap = min(
        15.0,
        max(0.0, dense_topic_gap),
    )
    # Keep every topic when it fits. Otherwise seed source-wide coverage.
    if len(topic_best) <= max_anchors:
        selected.extend(sorted(topic_best.values(), key=lambda item: item.start))
    else:
        topics = sorted(topic_best.values(), key=lambda item: item.start)
        indexes = [
            (slot * (len(topics) - 1)) // max(1, max_anchors - 1)
            for slot in range(max_anchors)
        ]
        selected.extend(topics[index] for index in indexes)
    prioritized = sorted(topic_best.values(), key=lambda item: (_anchor_strength(item), item.start), reverse=True)
    prioritized.extend(sorted(units, key=lambda item: (_anchor_strength(item), item.start), reverse=True))
    for unit in prioritized:
        if len(selected) >= max_anchors:
            break
        if unit not in selected and all(
            abs(unit.start - other.start) >= minimum_anchor_gap for other in selected
        ):
            selected.append(unit)
    if len(selected) < max_anchors:
        for unit in sorted(units, key=lambda item: (_anchor_strength(item), item.start), reverse=True):
            if unit in selected or any(
                abs(unit.start - other.start) < minimum_anchor_gap for other in selected
            ):
                continue
            selected.append(unit)
            if len(selected) >= max_anchors:
                break
    return sorted(selected, key=lambda item: item.start)


def _payoff_evidence(
    unit: SentenceUnit, preceding: list[SentenceUnit] | None = None
) -> tuple[bool, float, str]:
    """Return weak deterministic payoff evidence, never punctuation evidence."""
    text = unit.text.lower().strip()
    tokens = set(_TOKEN_RE.findall(text))
    previous = preceding or []
    previous_question = any("?" in item.text for item in previous[-2:])
    confidence = 0.0
    reasons: list[str] = []
    if previous_question and (
        text.startswith(("because", "yes", "no", "it is", "the answer", "there is"))
        or "answer" in tokens
    ):
        confidence += 0.55
        reasons.append("answers_question")
    if tokens & _REACTION_WORDS and any(
        any(char.isdigit() for char in item.text) or item.tokens & _PREMISE_WORDS
        for item in previous[-2:]
    ):
        confidence += 0.42
        reasons.append("reacts_to_reveal")
    starts_with_resolution = text.startswith((
        "because", "which means", "that means", "that's why", "therefore", "as a result",
    ))
    explicit_outcome = _has_explicit_outcome(text)
    if starts_with_resolution or explicit_outcome:
        confidence += 0.45
        reasons.append("cause_or_outcome")
    if any(word in tokens for word in {"revealed", "reveal", "fact", "result", "conclusion", "finally"}):
        confidence += 0.35
        reasons.append("specific_reveal")
    if previous_question and any(char.isdigit() for char in text) and any(
        word in tokens for word in {"worth", "cost", "million", "billion", "dollars"}
    ):
        confidence += 0.25
        reasons.append("specific_fact")
    return bool(confidence >= 0.35), round(min(0.95, confidence), 4), ",".join(reasons)


def _contains_payoff(unit: SentenceUnit) -> bool:
    """Use payoff cues only; sentence punctuation is syntax evidence."""
    return _payoff_evidence(unit)[0]


def _standalone_score(unit: SentenceUnit) -> float:
    """Approximate context-free comprehension without fake certainty."""
    text = unit.text.lower().strip()
    words = _TOKEN_RE.findall(text)
    if not words:
        return 0.0
    score = 40.0
    specific = bool(any(char.isdigit() for char in text) or unit.tokens & _PREMISE_WORDS)
    proper_noun = any(word[:1].isupper() for word in unit.text.split()[1:] if word)
    understandable_question = "?" in text and len(unit.tokens) >= 3
    if specific:
        score += 18.0
    if proper_noun:
        score += 10.0
    if understandable_question:
        score += 8.0
    if words[0] in _DEICTIC_WORDS:
        score -= 20.0
    if any(text.startswith(reference) for reference in _CONTEXT_REFERENCES):
        score -= 18.0
    if len(unit.tokens) <= 2:
        score -= 12.0
    return round(max(10.0, min(85.0, score)), 1)


def _premise(units: list[SentenceUnit]) -> str:
    if not units:
        return ""
    def premise_score(unit: SentenceUnit) -> tuple[float, int]:
        words = set(_TOKEN_RE.findall(unit.text.lower()))
        reaction_only = bool(words & _REACTION_WORDS) and len(unit.tokens) <= 2
        specific = bool(any(char.isdigit() for char in unit.text)) or len(unit.tokens) >= 5
        return (
            float(not reaction_only) + float(specific) + 0.1 * len(unit.tokens),
            len(unit.tokens),
        )

    informative = sorted(units, key=premise_score, reverse=True)
    return informative[0].text


def _story_shape(units: list[SentenceUnit]) -> str:
    if not units:
        return "none"
    first = units[0].text.lower()
    if "?" in first or (_TOKEN_RE.findall(first)[:1] and _TOKEN_RE.findall(first)[0] in _QUESTION_STARTS):
        return "question_answer"
    if any(set(_TOKEN_RE.findall(unit.text.lower())) & _REACTION_WORDS for unit in units[1:]):
        return "hook_setup_payoff"
    return "reveal"


def _semantic_key(units: list[SentenceUnit]) -> tuple[str, ...]:
    common = set.intersection(*(set(unit.tokens) for unit in units if unit.tokens)) if any(unit.tokens for unit in units) else set()
    all_tokens = set().union(*(set(unit.tokens) for unit in units))
    return tuple(sorted((common or all_tokens) & {token for token in all_tokens if len(token) > 3}))[:8]


def _story_candidate(
    units: list[SentenceUnit], anchor: SentenceUnit, variant: str, proposal: BoundaryProposal | None = None
) -> dict[str, Any] | None:
    if not units:
        return None
    start, end = units[0].start, units[-1].end
    duration = end - start
    if duration < MIN_STORY_SECONDS or duration > MAX_STORY_SECONDS:
        return None
    words = _TOKEN_RE.findall(" ".join(unit.text for unit in units).lower())
    if len(words) < 8:
        return None
    first = units[0]
    last = units[-1]
    payoff_unit = next(
        (
            unit for index, unit in reversed(list(enumerate(units)))
            if _payoff_evidence(unit, units[:index])[0]
        ),
        None,
    )
    if proposal:
        proposed_payoff = next(
            (unit for unit in units if unit.sentence_id == proposal.payoff_sentence_id),
            None,
        )
        if proposed_payoff is not None:
            proposed_index = units.index(proposed_payoff)
            if _payoff_evidence(proposed_payoff, units[:proposed_index])[0]:
                payoff_unit = proposed_payoff
    payoff_candidate = payoff_unit is not None
    payoff_confidence = (
        _payoff_evidence(payoff_unit, units[:units.index(payoff_unit)])[1]
        if payoff_unit is not None else 0.0
    )
    explicit_payoff = bool(payoff_unit is not None and _has_explicit_outcome(payoff_unit.text))
    coherence = round(100.0 * sum(1.0 - min(1.0, unit.topic_boundary_before) for unit in units[1:]) / max(1, len(units) - 1), 1)
    topic_shifts = len({unit.topic_id for unit in units}) - 1
    start_words = set(_TOKEN_RE.findall(first.text.lower()))
    filler_penalty = 0.18 if start_words & _FILLER_STARTS else 0.0
    hook_score = min(
        1.0,
        0.30
        + 0.28 * bool("?" in first.text)
        + 0.22 * bool(set(first.tokens) & _PREMISE_WORDS)
        + 0.15 * bool(set(first.tokens) & _REACTION_WORDS)
        + 0.12 * bool(any(char.isdigit() for char in first.text))
        + 0.10 * bool(first.tokens),
    ) - filler_penalty
    syntactic_complete = bool(last.text.rstrip().endswith((".", "!", "?")))
    premise = proposal.central_premise if proposal and proposal.central_premise else _premise(units)
    editorial_signal = bool(
        any(char.isdigit() for char in " ".join(unit.text for unit in units))
        or any("?" in unit.text for unit in units)
        or any(set(_TOKEN_RE.findall(unit.text.lower())) & (_REACTION_WORDS | {"secret", "dangerous", "survive", "infinite"}) for unit in units)
        or any(set(_TOKEN_RE.findall(unit.text.lower())) & _EDITORIAL_TERMS for unit in units)
        or any(unit.audio_events for unit in units)
    )
    return {
        "candidate_id": f"story-{anchor.sentence_id.lower()}-{variant}",
        "anchor_sentence_id": anchor.sentence_id,
        "start": round(start, 3),
        "end": round(end, 3),
        "peak_time": round(anchor.start, 3),
        "curve_score": round(_mean_interest(units), 4),
        "channel_scores": {},
        "sentence_ids": [unit.sentence_id for unit in units],
        "central_premise": premise,
        "hook_sentence": first.text,
        "hook_time": round(first.start, 3),
        "setup_end": round(units[min(1, len(units) - 1)].end, 3),
        "payoff_sentence": payoff_unit.text if payoff_unit else "",
        "payoff_time": round(payoff_unit.start, 3) if payoff_unit else None,
        "payoff_sentence_id": payoff_unit.sentence_id if payoff_unit else None,
        "payoff_candidate": payoff_candidate,
        "payoff_boundary_explicit": explicit_payoff,
        "payoff_confidence": payoff_confidence,
        "semantic_closure": None,
        "topic_coherence": coherence,
        "topic_shift_count": topic_shifts,
        "standalone_comprehension": _standalone_score(first),
        "story_shape": proposal.story_shape if proposal else _story_shape(units),
        "syntactic_complete": syntactic_complete,
        "context_dependency": (
            _standalone_score(first) < 30.0
            and first.topic_boundary_before < TOPIC_BOUNDARY_THRESHOLD
            and not explicit_payoff
        ),
        "quality_tier": "STRUCTURALLY_VALID",
        "audio_events": sorted({event for unit in units for event in unit.audio_events}),
        "story_variant": variant,
        "topic_key": list(_semantic_key(units)),
        "start_topic_boundary": round(first.topic_boundary_before, 4),
        "boundary_confidence": round(max((unit.topic_boundary_before for unit in units[1:]), default=0.0), 4),
        "editorial_signal": editorial_signal,
        "hook_strength": round(max(0.0, hook_score), 4),
        "information_density": round(min(1.0, len(words) / max(1.0, duration * 2.2)), 4),
        "duration_fit": round(min(1.0, max(
            0.0,
            max((1.0 - abs(duration - target) / 30.0) * (1.15 if target == 30.0 else 1.0)
                for target in (18.0, 30.0, 45.0, 60.0)),
        )), 4),
    }


def _iou(left: dict[str, Any], right: dict[str, Any]) -> float:
    overlap = min(left["end"], right["end"]) - max(left["start"], right["start"])
    if overlap <= 0:
        return 0.0
    union = max(left["end"], right["end"]) - min(left["start"], right["start"])
    return overlap / union


def _story_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    a = set(left.get("topic_key") or [])
    b = set(right.get("topic_key") or [])
    payoff_a = set(_tokens(left.get("payoff_sentence", "")))
    payoff_b = set(_tokens(right.get("payoff_sentence", "")))
    topic = _similarity(a, b)
    payoff = _similarity(payoff_a, payoff_b)
    return max(topic, payoff)


def _candidate_quality_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(item.get("story_variant", "")).startswith("llm-"),
        bool(item.get("payoff_candidate")),
        float(item.get("duration_fit", 0.0)),
        float(item.get("information_density", 0.0)),
        float(item.get("curve_score", 0.0)),
        float(item.get("hook_strength", 0.0)),
        float(item.get("topic_coherence", 0.0)),
    )


def _is_earlier_opening_variant(candidate: dict[str, Any], other: dict[str, Any]) -> bool:
    """Prefer an earlier opening when the payoff identity remains stable."""
    return bool(
        candidate.get("payoff_candidate")
        and other.get("payoff_candidate")
        and candidate.get("anchor_sentence_id") == other.get("anchor_sentence_id")
        and float(candidate["start"]) + 3.0 < float(other["start"])
        and abs(
            float(candidate.get("payoff_time") or 0.0)
            - float(other.get("payoff_time") or 0.0)
        ) <= 2.0
        and float(candidate["end"]) - float(candidate.get("payoff_time") or 0.0) <= 30.0
    )


def cheap_filter_and_dedupe(
    candidates: list[dict[str, Any]],
    limit: int = SHORTLIST_LIMIT,
    *,
    audit: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Filter weak shapes, dedupe identity, and explain every discard."""
    viable: list[dict[str, Any]] = []
    audit_entries: dict[int, dict[str, Any]] = {}

    def record(candidate: dict[str, Any], reasons: list[str], status: str) -> None:
        if audit is not None:
            entry = {
                "candidate_id": candidate.get("candidate_id"),
                "start": candidate.get("start"),
                "end": candidate.get("end"),
                "anchor_sentence_id": candidate.get("anchor_sentence_id"),
                "payoff_time": candidate.get("payoff_time"),
                "payoff_candidate": bool(candidate.get("payoff_candidate")),
                "payoff_boundary_explicit": bool(candidate.get("payoff_boundary_explicit")),
                "source_final_boundary": bool(candidate.get("source_final_boundary")),
                "status": status,
                "rejection_reasons": list(reasons),
            }
            audit.append(entry)
            audit_entries[id(candidate)] = entry

    for candidate in candidates:
        reasons: list[str] = []
        if candidate["end"] - candidate["start"] < MIN_STORY_SECONDS:
            reasons.append("TOO_SHORT")
        if not candidate.get("syntactic_complete"):
            reasons.append("INCOMPLETE_ENDING")
        if not candidate.get("central_premise"):
            reasons.append("MISSING_PREMISE")
        if len(candidate.get("sentence_ids", [])) < 2:
            reasons.append("TOO_FEW_SENTENCES")
        if not candidate.get("editorial_signal"):
            reasons.append("NO_EDITORIAL_SIGNAL")
        if candidate.get("context_dependency", False):
            reasons.append("CONTEXT_DEPENDENT")
        if reasons:
            record(candidate, reasons, "rejected")
            continue
        viable.append(candidate)
    viable.sort(key=_candidate_quality_key, reverse=True)
    kept: list[dict[str, Any]] = []
    bucket_counts: dict[int, int] = {}
    for candidate in viable:
        later_payoff_variant = False
        duplicate_indices = [
            index
            for index, other in enumerate(kept)
            if _story_similarity(candidate, other) >= 0.92
        ]
        duplicate_index = next(
            (
                index for index in duplicate_indices
                if _is_earlier_opening_variant(candidate, kept[index])
            ),
            duplicate_indices[0] if duplicate_indices else None,
        )
        if duplicate_index is not None:
            other = kept[duplicate_index]
            same_start = abs(float(candidate["start"]) - float(other["start"])) < 0.1
            materially_different_end = abs(float(candidate["end"]) - float(other["end"])) >= 8.0
            # Semantic overlap alone cannot prove duplicate identity.  A
            # repeated topic can contain several independent moments across
            # a long source, so only temporally related or shared-unit spans
            # are duplicates.
            shared_sentence_unit = bool(
                set(candidate.get("sentence_ids") or [])
                & set(other.get("sentence_ids") or [])
            )
            strong_new_topic = (
                float(candidate.get("start_topic_boundary") or 0.0)
                >= TOPIC_BOUNDARY_THRESHOLD
                and float(candidate["start"]) - float(other["start"]) >= 8.0
            )
            better_payoff_boundary = (
                candidate.get("payoff_candidate")
                and float(candidate["end"]) > float(other["end"])
                and float(candidate.get("payoff_time") or 0.0)
                > float(other.get("payoff_time") or 0.0)
            )
            later_payoff_variant = (
                better_payoff_boundary
                and candidate.get("payoff_boundary_explicit")
            )
            better_opening_boundary = _is_earlier_opening_variant(candidate, other)
            same_explicit_payoff = (
                candidate.get("payoff_boundary_explicit")
                and other.get("payoff_boundary_explicit")
                and candidate.get("anchor_sentence_id") == other.get("anchor_sentence_id")
                and abs(
                    float(candidate.get("payoff_time") or 0.0)
                    - float(other.get("payoff_time") or 0.0)
                ) <= 2.0
            )
            candidate_compact_tail = (
                float(candidate.get("payoff_time") or 0.0) > 0.0
                and float(candidate["end"]) - float(candidate["payoff_time"]) <= 30.0
            )
            other_compact_tail = (
                float(other.get("payoff_time") or 0.0) > 0.0
                and float(other["end"]) - float(other.get("payoff_time") or 0.0) <= 30.0
            )
            if same_explicit_payoff and other_compact_tail and not candidate_compact_tail:
                record(candidate, ["DUPLICATE_STORY"], "rejected")
                continue
            final_payoff_boundary = (
                candidate.get("source_final_boundary")
                and candidate.get("payoff_boundary_explicit")
                and float(candidate["end"]) > float(other["end"])
            )
            if better_opening_boundary:
                kept[duplicate_index] = candidate
                previous_entry = audit_entries.get(id(other))
                if previous_entry is not None:
                    previous_entry["status"] = "rejected"
                    previous_entry["rejection_reasons"] = ["DUPLICATE_STORY_REPLACED"]
                record(candidate, [], "kept")
                continue
            if strong_new_topic or better_payoff_boundary or final_payoff_boundary:
                duplicate_index = None
            if not same_start and _iou(candidate, other) < 0.35 and not shared_sentence_unit:
                duplicate_index = None
            if (
                same_start
                and not materially_different_end
                and not (
                    candidate.get("payoff_candidate")
                    and float(candidate["end"]) > float(other["end"])
                    and float(candidate["end"]) - float(other["end"]) >= 0.5
                )
            ):
                record(candidate, ["DUPLICATE_STORY"], "rejected")
                continue
            if same_start and materially_different_end:
                duplicate_index = None
        if duplicate_index is not None:
            other = kept[duplicate_index]
            if (
                not str(other.get("story_variant", "")).startswith("llm-")
                and float(candidate.get("payoff_time") or 0.0) > float(other.get("payoff_time") or 0.0)
            ):
                kept[duplicate_index] = candidate
                previous_entry = audit_entries.get(id(other))
                if previous_entry is not None:
                    previous_entry["status"] = "rejected"
                    previous_entry["rejection_reasons"] = ["DUPLICATE_STORY_REPLACED"]
                record(candidate, [], "kept")
            else:
                record(candidate, ["DUPLICATE_STORY"], "rejected")
            continue
        overlap_index = next(
            (
                index for index, other in enumerate(kept)
                if _story_similarity(candidate, other) >= 0.82
                and _iou(candidate, other) >= 0.35
            ),
            None,
        )
        if overlap_index is not None and not later_payoff_variant:
            other = kept[overlap_index]
            if (
                candidate.get("payoff_candidate")
                and (
                    candidate.get("anchor_sentence_id") == other.get("anchor_sentence_id")
                    or (
                        candidate.get("source_final_boundary")
                        and candidate.get("payoff_boundary_explicit")
                    )
                )
                and float(candidate["end"]) > float(other["end"])
            ):
                kept[overlap_index] = candidate
                previous_entry = audit_entries.get(id(other))
                if previous_entry is not None:
                    previous_entry["status"] = "rejected"
                    previous_entry["rejection_reasons"] = ["DUPLICATE_STORY_REPLACED"]
                record(candidate, [], "kept")
                continue
            record(candidate, ["DUPLICATE_OVERLAP"], "rejected")
            continue
        nearby_index = next(
            (
                index for index, other in enumerate(kept)
                if abs(float(candidate["start"]) - float(other["start"])) < 12.0
                and _story_similarity(candidate, other) >= 0.6
                and abs(float(candidate["end"]) - float(other["end"])) < 8.0
            ),
            None,
        )
        if nearby_index is not None:
            record(candidate, ["NEARBY_SIMILAR"], "rejected")
            continue
        bucket = int(float(candidate["start"]) // 60)
        if bucket_counts.get(bucket, 0) >= MAX_CANDIDATES_PER_TIME_BUCKET:
            same_bucket = [
                (index, other)
                for index, other in enumerate(kept)
                if int(float(other["start"]) // 60) == bucket
            ]
            strong_new_topic = float(candidate.get("start_topic_boundary") or 0.0) >= TOPIC_BOUNDARY_THRESHOLD
            replaceable = [
                pair for pair in same_bucket
                if (
                    not pair[1].get("payoff_candidate")
                    or float(candidate.get("start_topic_boundary") or 0.0)
                    > float(pair[1].get("start_topic_boundary") or 0.0)
                )
            ]
            if strong_new_topic and replaceable:
                replace_index, replaced = min(
                    replaceable, key=lambda pair: _candidate_quality_key(pair[1])
                )
                kept[replace_index] = candidate
                previous_entry = audit_entries.get(id(replaced))
                if previous_entry is not None:
                    previous_entry["status"] = "rejected"
                    previous_entry["rejection_reasons"] = ["TIME_BUCKET_REPLACED"]
                record(candidate, [], "kept")
                continue
            record(candidate, ["TIME_BUCKET_LIMIT"], "rejected")
            continue
        kept.append(candidate)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        record(candidate, [], "kept")
    shortlist_limit = max(0, int(limit))
    shortlist = list(kept[:shortlist_limit])
    selected_ids = {id(candidate) for candidate in shortlist}
    protected_ids: set[int] = set()
    if shortlist and len(shortlist) >= shortlist_limit:
        earliest_selected = min(float(item["start"]) for item in shortlist)
        leading_candidates = [
            candidate
            for candidate in kept[shortlist_limit:]
            if float(candidate["start"]) < earliest_selected
        ]
        if leading_candidates:
            coverage_candidate = max(
                leading_candidates,
                key=lambda item: (
                    float(item["end"]) - float(item["start"]),
                    _candidate_quality_key(item),
                ),
            )
            weakest = min(shortlist, key=_candidate_quality_key)
            later_payoff_is_covered = (
                coverage_candidate.get("payoff_candidate")
                and weakest.get("payoff_candidate")
                and float(weakest.get("payoff_time") or 0.0)
                > float(coverage_candidate.get("payoff_time") or 0.0)
                and float(coverage_candidate["end"]) >= float(weakest["start"]) - 4.0
                and _story_similarity(coverage_candidate, weakest) >= 0.6
            )
            unrelated_explicit_payoff = (
                weakest.get("payoff_boundary_explicit")
                and _story_similarity(coverage_candidate, weakest) < 0.6
            )
            if not later_payoff_is_covered and not unrelated_explicit_payoff:
                shortlist[shortlist.index(weakest)] = coverage_candidate
                selected_ids.remove(id(weakest))
                selected_ids.add(id(coverage_candidate))
                protected_ids.add(id(coverage_candidate))
    boundary_candidates = [
        candidate
        for candidate in kept[shortlist_limit:]
        if candidate.get("payoff_candidate")
    ]
    for candidate in sorted(
        boundary_candidates,
        key=lambda item: (
            float(item.get("payoff_time") or item["end"]),
            float(item["end"]),
        ),
        reverse=True,
    ):
        related = [
            other
            for other in shortlist
            if (
                float(candidate["start"]) >= float(other["start"]) - 2.0
                and float(candidate["start"]) - float(other["start"]) <= 30.0
                and _iou(candidate, other) >= 0.15
                and (
                    _story_similarity(candidate, other) >= 0.6
                    or (
                        candidate.get("payoff_boundary_explicit")
                        and bool(
                            set(candidate.get("sentence_ids") or [])
                            & set(other.get("sentence_ids") or [])
                        )
                    )
                )
                and float(candidate["end"]) > float(other["end"])
                and float(candidate.get("payoff_time") or 0.0)
                > float(other.get("payoff_time") or 0.0)
            )
        ]
        if not related:
            continue
        other = min(related, key=_candidate_quality_key)
        shortlist[shortlist.index(other)] = candidate
        selected_ids.remove(id(other))
        selected_ids.add(id(candidate))
        previous_entry = audit_entries.get(id(other))
        if previous_entry is not None:
            previous_entry["status"] = "rejected"
            previous_entry["rejection_reasons"] = ["SHORTLIST_BOUNDARY_REPLACED"]
        candidate_entry = audit_entries.get(id(candidate))
        if candidate_entry is not None:
            candidate_entry["status"] = "kept"
            candidate_entry["rejection_reasons"] = []
    if shortlist and len(shortlist) >= shortlist_limit:
        selected_bucket_counts: dict[int, int] = {}
        for candidate in shortlist:
            bucket = int(float(candidate["start"]) // 60)
            selected_bucket_counts[bucket] = selected_bucket_counts.get(bucket, 0) + 1
        for index, selected in enumerate(list(shortlist)):
            selected_payoff = float(selected.get("payoff_time") or 0.0)
            span_variants = [
                candidate
                for candidate in kept
                if id(candidate) not in selected_ids
                and candidate.get("payoff_candidate")
                and selected.get("anchor_sentence_id") is not None
                and candidate.get("anchor_sentence_id") == selected.get("anchor_sentence_id")
                and abs(float(candidate.get("payoff_time") or 0.0) - selected_payoff) <= 2.0
                and int(float(candidate["start"]) // 60) == int(float(selected["start"]) // 60)
                and (
                    float(candidate["start"]) < float(selected["start"]) - 3.0
                    or float(candidate["end"]) > float(selected["end"]) + 8.0
                )
            ]
            if not span_variants:
                continue
            coverage_candidate = max(
                span_variants,
                key=lambda item: (
                    bool(item.get("payoff_boundary_explicit")),
                    float(item["end"]) - float(item["start"]),
                    -float(item["start"]),
                    _candidate_quality_key(item),
                ),
            )
            replaced = selected
            shortlist[index] = coverage_candidate
            selected_ids.remove(id(replaced))
            selected_ids.add(id(coverage_candidate))
            if id(replaced) in protected_ids:
                protected_ids.remove(id(replaced))
                protected_ids.add(id(coverage_candidate))
            previous_entry = audit_entries.get(id(replaced))
            if previous_entry is not None:
                previous_entry["status"] = "rejected"
                previous_entry["rejection_reasons"] = ["SHORTLIST_COVERAGE_REPLACED"]
            candidate_entry = audit_entries.get(id(coverage_candidate))
            if candidate_entry is not None:
                candidate_entry["status"] = "kept"
                candidate_entry["rejection_reasons"] = []
        missing_buckets = sorted({
            int(float(candidate["start"]) // 60)
            for candidate in kept
            if int(float(candidate["start"]) // 60) not in selected_bucket_counts
        })
        for bucket in missing_buckets:
            coverage_candidates = [
                candidate
                for candidate in kept
                if id(candidate) not in selected_ids
                and int(float(candidate["start"]) // 60) == bucket
            ]
            if not coverage_candidates:
                continue
            coverage_candidate = max(
                coverage_candidates,
                key=lambda item: (
                    bool(item.get("payoff_boundary_explicit")),
                    bool(item.get("payoff_candidate")),
                    _candidate_quality_key(item),
                ),
            )
            replaceable = [
                candidate
                for candidate in shortlist
                if selected_bucket_counts.get(int(float(candidate["start"]) // 60), 0) > 1
                and not candidate.get("payoff_boundary_explicit")
                and id(candidate) not in protected_ids
            ]
            if not replaceable:
                replaceable = [
                    candidate
                    for candidate in shortlist
                    if not candidate.get("payoff_boundary_explicit")
                    and id(candidate) not in protected_ids
                ]
            if not replaceable:
                if coverage_candidate.get("payoff_boundary_explicit"):
                    latest_selected_payoff = max(
                        (float(item.get("payoff_time") or 0.0) for item in shortlist),
                        default=0.0,
                    )
                    if float(coverage_candidate.get("payoff_time") or 0.0) <= latest_selected_payoff:
                        continue
                    replaceable = [
                        candidate
                        for candidate in shortlist
                        if id(candidate) not in protected_ids
                    ]
                else:
                    continue
            replaced = min(replaceable, key=_candidate_quality_key)
            replaced_bucket = int(float(replaced["start"]) // 60)
            shortlist[shortlist.index(replaced)] = coverage_candidate
            selected_ids.remove(id(replaced))
            selected_ids.add(id(coverage_candidate))
            selected_bucket_counts[replaced_bucket] -= 1
            selected_bucket_counts[bucket] = selected_bucket_counts.get(bucket, 0) + 1
    for candidate in kept:
        if id(candidate) in selected_ids:
            continue
        entry = audit_entries.get(id(candidate))
        if entry is not None:
            entry["status"] = "rejected"
            entry["rejection_reasons"] = ["SHORTLIST_LIMIT"]
    return sorted(shortlist, key=lambda item: item["start"])


def _candidate_start_indices(
    units: list[SentenceUnit],
    anchor_index: int,
    *,
    max_lookback_seconds: float = 35.0,
) -> list[int]:
    """Find bounded setup starts without relying on sentence counts."""
    if not units or anchor_index <= 0 or anchor_index >= len(units):
        return []
    anchor_start = float(units[anchor_index].start)
    earliest_start = anchor_start - max(0.0, float(max_lookback_seconds))
    indices = [
        index
        for index in range(max(0, anchor_index - 3), anchor_index)
        if float(units[index].start) >= earliest_start
    ]
    first_in_window = next(
        (
            index for index in range(anchor_index)
            if float(units[index].start) >= earliest_start
        ),
        anchor_index,
    )
    for index in range(first_in_window, anchor_index):
        text = units[index].text.lower()
        tokens = set(_TOKEN_RE.findall(text))
        if (
            units[index].topic_boundary_before >= TOPIC_BOUNDARY_THRESHOLD
            or "?" in text
            or any(char.isdigit() for char in text)
            or tokens & _PREMISE_WORDS
        ):
            indices.append(index)
    return list(dict.fromkeys(indices))


def _candidate_end_indices(
    units: list[SentenceUnit],
    anchor_index: int,
    *,
    max_lookahead_seconds: float = MAX_END_LOOKAHEAD_SECONDS,
) -> list[int]:
    """Find complete story ends within a bounded time lookahead."""
    if not units or anchor_index < 0 or anchor_index >= len(units):
        return []
    anchor_start = float(units[anchor_index].start)
    latest_start = anchor_start + max(0.0, float(max_lookahead_seconds))
    return [
        index
        for index, unit in enumerate(units)
        if anchor_start - 45.0 <= float(unit.start) <= latest_start
        and float(unit.end) >= anchor_start
        and unit.text.rstrip().endswith((".", "!", "?"))
    ]


def synthesize(
    units: list[SentenceUnit],
    curve: list[float] | None = None,
    channels: dict[str, list[float]] | None = None,
    *,
    boundary_proposer: Callable[[list[SentenceUnit], SentenceUnit], list[BoundaryProposal]] | None = None,
    anchor_limit: int = ANCHOR_LIMIT,
    boundary_limit: int = MAX_BOUNDARY_CALLS,
    shortlist_limit: int = SHORTLIST_LIMIT,
) -> dict[str, Any]:
    """Generate story variants, optionally using bounded local proposals."""
    anchors = generate_anchors(units, anchor_limit)
    raw: list[dict[str, Any]] = []
    deterministic_proposals = 0
    llm_proposals = 0
    boundary_calls = 0
    for anchor in anchors:
        neighborhood = [unit for unit in units if anchor.start - 45.0 <= unit.start <= anchor.start + 45.0]
        proposals = []
        if boundary_proposer and boundary_calls < boundary_limit:
            boundary_calls += 1
            proposals = boundary_proposer(neighborhood, anchor)
        anchor_index = units.index(anchor)
        complete_ends = _candidate_end_indices(units, anchor_index)
        payoff_ends = [index for index in complete_ends if _contains_payoff(units[index])]
        end_candidates = list(dict.fromkeys(payoff_ends[:5] + payoff_ends[-5:] + complete_ends[:4] + complete_ends[-4:] + [
            index for index in complete_ends
            if units[index].audio_events or set(_TOKEN_RE.findall(units[index].text.lower())) & _REACTION_WORDS
        ]))
        start_indices = [*(_candidate_start_indices(units, anchor_index)), anchor_index]
        for start_offset, start_index in enumerate(start_indices):
            ordered_end_candidates = sorted(
                end_candidates,
                key=lambda index: (
                    min(abs((units[index].end - units[start_index].start) - target) for target in (13.0, 22.0, 32.0, 45.0, 60.0)),
                    -units[index].end,
                ),
            )
            for offset, end_index in enumerate(ordered_end_candidates):
                if start_index > end_index:
                    continue
                candidate = _story_candidate(units[start_index:end_index + 1], anchor, f"det-{offset}-{start_offset}")
                if candidate:
                    candidate["source_final_boundary"] = bool(
                        candidate["end"] >= units[-1].end - 0.01
                    )
                    raw.append(candidate)
                    deterministic_proposals += 1
        for proposal_index, proposal in enumerate(proposals[:3]):
            valid_ids = {unit.sentence_id for unit in neighborhood}
            if proposal.best_start_sentence_id not in valid_ids or proposal.best_end_sentence_id not in valid_ids:
                continue
            start_index = next(index for index, unit in enumerate(units) if unit.sentence_id == proposal.best_start_sentence_id)
            end_index = next(index for index, unit in enumerate(units) if unit.sentence_id == proposal.best_end_sentence_id)
            if start_index <= end_index:
                candidate = _story_candidate(units[start_index:end_index + 1], anchor, f"llm-{proposal_index}", proposal)
                if candidate:
                    candidate["source_final_boundary"] = bool(
                        candidate["end"] >= units[-1].end - 0.01
                    )
                    raw.append(candidate)
                    llm_proposals += 1
    for candidate in raw:
        candidate["channel_scores"] = {
            name: round(sum(values[int(candidate["start"]):max(int(candidate["start"]) + 1, int(candidate["end"]))]) / max(1, len(values[int(candidate["start"]):max(int(candidate["start"]) + 1, int(candidate["end"]))])), 4)
            for name, values in (channels or {}).items()
            if values and int(candidate["start"]) < len(values)
        }
    filter_audit: list[dict[str, Any]] = []
    survivors = cheap_filter_and_dedupe(raw, shortlist_limit, audit=filter_audit)
    deduped_count = sum(
        item["status"] == "kept" or item.get("rejection_reasons") == ["SHORTLIST_LIMIT"]
        for item in filter_audit
    )
    return {
        "units": [unit.to_json() for unit in units],
        "topic_segment_count": len({unit.topic_id for unit in units}),
        "anchors": [unit.sentence_id for unit in anchors],
        "raw_span_variants": len(raw),
        "cheap_survivors": len(survivors),
        "boundary_calls": boundary_calls,
        "candidates": survivors,
        "candidate_audit": {
            "raw_proposals": len(raw),
            "deterministic_proposals": deterministic_proposals,
            "llm_proposals": llm_proposals,
            "story_unit_proposals": deterministic_proposals,
            "deduped_proposals": deduped_count,
            "shortlisted_proposals": len(survivors),
            "rejection_reasons": [
                item for item in filter_audit if item["status"] == "rejected"
            ],
        },
    }


def boundary_prompt(units: list[SentenceUnit]) -> str:
    """Strict boundary-selector prompt using only supplied sentence IDs."""
    transcript = "\n".join(f"{unit.sentence_id} [{unit.start:.3f}-{unit.end:.3f}] {unit.text}" for unit in units)
    return (
        "Select one short-form story from this supplied transcript neighborhood. "
        "Return JSON only. Use only the listed sentence IDs; never invent text "
        "or timestamps. Pick a complete hook, setup, and payoff when possible.\n\n"
        f"{transcript}\n\n"
        "Fields: best_start_sentence_id, best_end_sentence_id, central_premise, "
        "hook_sentence_id, payoff_sentence_id, story_shape, why_start, why_end."
    )


BOUNDARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "best_start_sentence_id": {"type": "string"},
        "best_end_sentence_id": {"type": "string"},
        "central_premise": {"type": "string"},
        "hook_sentence_id": {"type": "string"},
        "payoff_sentence_id": {"type": "string"},
        "story_shape": {"type": "string", "enum": ["hook_setup_payoff", "question_answer", "conflict_reaction", "reveal", "open_ended", "none"]},
        "why_start": {"type": "string"},
        "why_end": {"type": "string"},
    },
    "required": [
        "best_start_sentence_id", "best_end_sentence_id", "central_premise",
        "hook_sentence_id", "payoff_sentence_id", "story_shape", "why_start", "why_end",
    ],
}


def parse_boundary_proposal(payload: dict[str, Any], units: list[SentenceUnit]) -> BoundaryProposal | None:
    """Accept proposals only when every referenced ID is supplied."""
    allowed = {unit.sentence_id for unit in units}
    fields = (
        "best_start_sentence_id", "best_end_sentence_id", "hook_sentence_id", "payoff_sentence_id",
    )
    if any(str(payload.get(field, "")) not in allowed for field in fields):
        return None
    return BoundaryProposal(
        best_start_sentence_id=str(payload["best_start_sentence_id"]),
        best_end_sentence_id=str(payload["best_end_sentence_id"]),
        central_premise=str(payload.get("central_premise", "")).strip(),
        hook_sentence_id=str(payload["hook_sentence_id"]),
        payoff_sentence_id=str(payload["payoff_sentence_id"]),
        story_shape=str(payload.get("story_shape", "none")),
        why_start=str(payload.get("why_start", ""))[:240],
        why_end=str(payload.get("why_end", ""))[:240],
    )
