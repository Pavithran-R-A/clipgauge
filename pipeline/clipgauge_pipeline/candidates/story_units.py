"""Story-unit candidate synthesis for short-form editorial search.

The synthesizer keeps sentence boundaries legal, uses lexical topic evidence,
and emits a small scored shortlist from a larger cheap variant pool.  Visual
cuts and audio events support boundaries; neither can split a story alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

MIN_STORY_SECONDS = 8.0
MAX_STORY_SECONDS = 75.0
ANCHOR_LIMIT = 20
MAX_BOUNDARY_CALLS = 15
SHORTLIST_LIMIT = 24
MAX_CANDIDATES_PER_TIME_BUCKET = 4
TOPIC_BOUNDARY_THRESHOLD = 0.62
MIN_TOPIC_UNITS = 5
_TOKEN_RE = re.compile(r"[a-z0-9]+")
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
    return frozenset(
        token for token in _TOKEN_RE.findall(text.lower())
        if token not in _STOPWORDS and len(token) > 2
    )


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
    bucket_best: dict[int, SentenceUnit] = {}
    for unit in units:
        bucket = int(unit.start // 60)
        if bucket not in bucket_best or _anchor_strength(unit) > _anchor_strength(bucket_best[bucket]):
            bucket_best[bucket] = unit
    prioritized = list(sorted(bucket_best.values(), key=lambda item: item.start))
    prioritized.extend(sorted(units, key=lambda item: (_anchor_strength(item), item.start), reverse=True))
    for unit in prioritized:
        if all(abs(unit.start - other.start) >= 15.0 for other in selected):
            selected.append(unit)
        if len(selected) >= max(0, int(limit)):
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
    explicit_outcome = any(phrase in text for phrase in (
        "turns out", "ended up", "managed to",
    )) or bool(tokens & {"won", "failed", "survived", "works"})
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
        or any(unit.audio_events for unit in units)
    )
    return {
        "candidate_id": f"story-{anchor.sentence_id.lower()}-{variant}",
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
        "payoff_confidence": payoff_confidence,
        "semantic_closure": None,
        "topic_coherence": coherence,
        "topic_shift_count": topic_shifts,
        "standalone_comprehension": _standalone_score(first),
        "story_shape": proposal.story_shape if proposal else _story_shape(units),
        "syntactic_complete": syntactic_complete,
        "context_dependency": _standalone_score(first) < 30.0,
        "quality_tier": "STRUCTURALLY_VALID",
        "audio_events": sorted({event for unit in units for event in unit.audio_events}),
        "story_variant": variant,
        "topic_key": list(_semantic_key(units)),
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


def cheap_filter_and_dedupe(candidates: list[dict[str, Any]], limit: int = SHORTLIST_LIMIT) -> list[dict[str, Any]]:
    """Filter weak shapes, then dedupe story identity and timestamp overlap."""
    viable = [
        candidate for candidate in candidates
        if candidate["end"] - candidate["start"] >= MIN_STORY_SECONDS
        and candidate.get("syntactic_complete")
        and candidate.get("central_premise")
        and len(candidate.get("sentence_ids", [])) >= 2
        and candidate.get("editorial_signal")
        and not candidate.get("context_dependency", False)
    ]
    viable.sort(key=lambda item: (
        item.get("story_variant", "").startswith("llm-"),
        float(item.get("duration_fit", 0.0)),
        float(item.get("information_density", 0.0)),
        float(item.get("curve_score", 0.0)),
        float(item.get("hook_strength", 0.0)),
        float(item.get("topic_coherence", 0.0)),
        bool(item.get("payoff_candidate")),
    ), reverse=True)
    kept: list[dict[str, Any]] = []
    bucket_counts: dict[int, int] = {}
    for candidate in viable:
        duplicate_index = next(
            (index for index, other in enumerate(kept) if _story_similarity(candidate, other) >= 0.92),
            None,
        )
        if duplicate_index is not None:
            other = kept[duplicate_index]
            same_start = abs(float(candidate["start"]) - float(other["start"])) < 0.1
            materially_different_end = abs(float(candidate["end"]) - float(other["end"])) >= 8.0
            if same_start and not materially_different_end:
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
            continue
        if any(_story_similarity(candidate, other) >= 0.82 and _iou(candidate, other) >= 0.35 for other in kept):
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
            continue
        bucket = int(float(candidate["start"]) // 60)
        if bucket_counts.get(bucket, 0) >= MAX_CANDIDATES_PER_TIME_BUCKET:
            continue
        kept.append(candidate)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        if len(kept) >= max(0, int(limit)):
            break
    return sorted(kept, key=lambda item: item["start"])


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
    boundary_calls = 0
    for anchor in anchors:
        neighborhood = [unit for unit in units if anchor.start - 45.0 <= unit.start <= anchor.start + 45.0]
        proposals = []
        if boundary_proposer and boundary_calls < boundary_limit:
            boundary_calls += 1
            proposals = boundary_proposer(neighborhood, anchor)
        anchor_index = units.index(anchor)
        complete_ends = [
            index for index, unit in enumerate(units)
            if anchor.start - 30.0 <= unit.start <= anchor.start + 45.0
            and unit.end >= anchor.start
            and unit.text.rstrip().endswith((".", "!", "?"))
        ]
        payoff_ends = [index for index in complete_ends if _contains_payoff(units[index])]
        end_candidates = list(dict.fromkeys(payoff_ends[:5] + payoff_ends[-5:] + complete_ends[:4] + complete_ends[-4:] + [
            index for index in complete_ends
            if units[index].audio_events or set(_TOKEN_RE.findall(units[index].text.lower())) & _REACTION_WORDS
        ]))
        start_indices = [max(0, anchor_index - 3), max(0, anchor_index - 2), max(0, anchor_index - 1), anchor_index]
        for index in range(max(0, anchor_index - 15), anchor_index):
            text = units[index].text.lower()
            tokens = set(_TOKEN_RE.findall(text))
            if "?" in text or any(char.isdigit() for char in text) or tokens & _PREMISE_WORDS:
                start_indices.append(index)
        start_indices = list(dict.fromkeys(start_indices))
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
                    raw.append(candidate)
        for proposal_index, proposal in enumerate(proposals[:3]):
            valid_ids = {unit.sentence_id for unit in neighborhood}
            if proposal.best_start_sentence_id not in valid_ids or proposal.best_end_sentence_id not in valid_ids:
                continue
            start_index = next(index for index, unit in enumerate(units) if unit.sentence_id == proposal.best_start_sentence_id)
            end_index = next(index for index, unit in enumerate(units) if unit.sentence_id == proposal.best_end_sentence_id)
            if start_index <= end_index:
                candidate = _story_candidate(units[start_index:end_index + 1], anchor, f"llm-{proposal_index}", proposal)
                if candidate:
                    raw.append(candidate)
    for candidate in raw:
        candidate["channel_scores"] = {
            name: round(sum(values[int(candidate["start"]):max(int(candidate["start"]) + 1, int(candidate["end"]))]) / max(1, len(values[int(candidate["start"]):max(int(candidate["start"]) + 1, int(candidate["end"]))])), 4)
            for name, values in (channels or {}).items()
            if values and int(candidate["start"]) < len(values)
        }
    survivors = cheap_filter_and_dedupe(raw, shortlist_limit)
    return {
        "units": [unit.to_json() for unit in units],
        "topic_segment_count": len({unit.topic_id for unit in units}),
        "anchors": [unit.sentence_id for unit in anchors],
        "raw_span_variants": len(raw),
        "cheap_survivors": len(survivors),
        "boundary_calls": boundary_calls,
        "candidates": survivors,
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
