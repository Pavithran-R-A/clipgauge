"""Explicit word-alignment policy for multilingual transcripts.

The registry is intentionally conservative. Exact alignment is used only for
assets that ClipGauge verifies locally. Other languages receive bounded,
deterministic timings so downstream clip selection remains functional without
silently downloading or substituting an English model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

ALIGNMENT_SCHEMA_VERSION = 1
EXACT = "EXACT"
FALLBACK = "FALLBACK"
UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class AlignmentPolicy:
    language: str
    status: str
    asset_id: str | None
    model_name: str | None
    reason: str
    schema_version: int = ALIGNMENT_SCHEMA_VERSION


_EXACT_POLICIES = {
    "en": AlignmentPolicy(
        language="en",
        status=EXACT,
        asset_id="model:alignment:en:wav2vec2-base-960h",
        model_name="WAV2VEC2_ASR_BASE_960H",
        reason="Verified English word-alignment asset is installed and selected.",
    ),
}


def alignment_policy(language: str | None) -> AlignmentPolicy:
    normalized = (language or "").strip().lower().split("-", 1)[0]
    if normalized in _EXACT_POLICIES:
        return _EXACT_POLICIES[normalized]
    if normalized:
        return AlignmentPolicy(
            language=normalized,
            status=FALLBACK,
            asset_id=None,
            model_name=None,
            reason=(
                f"No verified exact alignment asset is installed for {normalized}; "
                "using deterministic segment-based word timings."
            ),
        )
    return AlignmentPolicy(
        language="unknown",
        status=UNAVAILABLE,
        asset_id=None,
        model_name=None,
        reason="The speech recognizer did not return a language.",
    )


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"\S+", text or "") if token.strip()]


def fallback_word_alignment(segments: list[dict[str, Any]], *, duration: float) -> list[dict[str, Any]]:
    """Build stable word timings from transcript segments only.

    Timings never leave the segment or audio bounds, and each word advances
    monotonically. The output shape matches the exact alignment path.
    """
    audio_end = max(0.0, float(duration))
    output: list[dict[str, Any]] = []
    previous_end = 0.0
    for segment in segments:
        raw_start = max(0.0, min(audio_end, float(segment.get("start", 0.0))))
        raw_end = max(raw_start, min(audio_end, float(segment.get("end", raw_start))))
        start = max(previous_end, raw_start)
        end = max(start, raw_end)
        words = _tokens(str(segment.get("text", "")))
        if words and end == start and audio_end > start:
            end = min(audio_end, start + 0.001 * len(words))
        total_weight = sum(max(1, len(word)) for word in words) or 1
        cursor = start
        aligned_words: list[dict[str, Any]] = []
        span = max(0.0, end - start)
        for index, word in enumerate(words):
            weight = max(1, len(word))
            word_start = cursor
            if index == len(words) - 1:
                word_end = end
            else:
                word_end = min(end, cursor + span * weight / total_weight)
            word_end = max(word_start, word_end)
            aligned_words.append(
                {
                    "word": word.strip(),
                    "start": round(word_start, 3),
                    "end": round(word_end, 3),
                    "score": 0.0,
                }
            )
            cursor = word_end
        output.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "text": str(segment.get("text", "")).strip(),
                "words": aligned_words,
            }
        )
        previous_end = end
    return output
