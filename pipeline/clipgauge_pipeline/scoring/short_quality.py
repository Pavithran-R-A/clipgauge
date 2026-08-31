"""Deterministic short-form quality signals.

These signals rank structure and retention potential. They never replace
provider scoring, and they do not inspect private viewer data.
"""

from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(r"[\w']+", re.UNICODE)
_FILLER = {"um", "uh", "like", "you", "know", "basically", "actually"}
_REVEAL = {"because", "but", "then", "until", "turns", "revealed", "found", "realized"}
_REACTION = {"wow", "what", "no", "oh", "laugh", "laughed", "shocked", "insane"}
_HOOK = {"why", "how", "what", "never", "secret", "actually", "imagine", "the"}


def _words(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN.findall(text)]


def assess(text: str, events: list[dict[str, Any]] | None = None, duration: float = 1.0) -> dict[str, float | int | bool]:
    """Return stable, explainable structure scores on a 0-100 scale."""
    tokens = _words(text)
    if not tokens:
        return {
            "score": 0.0, "hook": 0.0, "standalone": 0.0, "story_shape": 0.0,
            "payoff": 0.0, "filler_ratio": 1.0, "speech_density": 0.0,
            "visual_variety": 0.0, "emotional_variety": 0.0, "loopability": 0.0,
        }
    events = events or []
    first = tokens[:6]
    last = tokens[-6:]
    hook = 72.0 if text.strip().endswith("?") or first[:1] and first[0] in _HOOK else 42.0
    if first and first[0] in _FILLER:
        hook -= 18.0
    standalone = 82.0 if len(tokens) >= 20 else 55.0
    if tokens[:1] and tokens[0] in {"he", "she", "they", "it", "that"}:
        standalone -= 18.0
    has_setup = len(tokens) >= 8
    has_reveal = bool(set(tokens) & _REVEAL)
    has_reaction = bool(set(last) & _REACTION) or any(e.get("type") in {"laugh", "gasp", "scream"} for e in events)
    story_shape = 35.0 + (25.0 if has_setup else 0.0) + (22.0 if has_reveal else 0.0) + (18.0 if has_reaction else 0.0)
    payoff = 78.0 if has_reaction else 58.0 if has_reveal else 30.0
    filler_ratio = sum(token in _FILLER for token in tokens) / len(tokens)
    density = min(100.0, len(tokens) / max(1.0, duration) * 5.0)
    types = {str(e.get("type")) for e in events if e.get("type")}
    visual_variety = min(100.0, 25.0 + len(types) * 18.0)
    emotional_variety = min(100.0, 25.0 + len(set(tokens) & _REACTION) * 18.0 + len(types) * 8.0)
    loopability = 72.0 if last and first and last[-1] == first[0] else 48.0
    score = (
        hook * 0.22 + standalone * 0.16 + story_shape * 0.18 + payoff * 0.18
        + density * 0.10 + visual_variety * 0.06 + emotional_variety * 0.06
        + loopability * 0.04 - filler_ratio * 100.0 * 0.12
    )
    return {
        "score": round(max(0.0, min(100.0, score)), 1),
        "hook": round(max(0.0, hook), 1),
        "standalone": round(max(0.0, standalone), 1),
        "story_shape": round(story_shape, 1),
        "payoff": round(payoff, 1),
        "filler_ratio": round(filler_ratio, 3),
        "speech_density": round(density, 1),
        "visual_variety": round(visual_variety, 1),
        "emotional_variety": round(emotional_variety, 1),
        "loopability": round(loopability, 1),
    }


def smart_boundaries(
    words: list[dict[str, Any]], start: float, end: float, *, max_extension: float = 1.5
) -> tuple[float, float]:
    """Snap bounds to nearby complete sentence-like word boundaries."""
    selected = [word for word in words if float(word["end"]) > start and float(word["start"]) < end]
    if not selected:
        return round(start, 3), round(end, 3)
    first = words.index(selected[0])
    last = words.index(selected[-1])
    while first > 0 and start - float(words[first - 1]["start"]) <= max_extension:
        previous = str(words[first - 1].get("word", ""))
        first -= 1
        if previous.rstrip().endswith(('.', '!', '?')):
            break
    while last + 1 < len(words) and float(words[last + 1]["end"]) - end <= max_extension:
        current = str(words[last].get("word", ""))
        last += 1
        if current.rstrip().endswith(('.', '!', '?')):
            break
    return round(float(words[first]["start"]), 3), round(float(words[last]["end"]), 3)


def rank(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable ranking with source order as the final tie-breaker."""
    return sorted(
        candidates,
        key=lambda item: (-float(item.get("short_quality", {}).get("score", 0.0)), item.get("start", 0.0), item.get("end", 0.0)),
    )
