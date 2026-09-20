"""Deterministic cue-to-word timing without claiming model alignment."""

from __future__ import annotations

import re

from .formats import SubtitleCue


def cue_to_segment(cue: SubtitleCue) -> dict:
    words = [word for word in re.split(r"\s+", cue.text.strip()) if word]
    span = max(0.001, cue.end - cue.start)
    step = span / max(1, len(words))
    return {
        "start": round(cue.start, 3),
        "end": round(cue.end, 3),
        "text": cue.text,
        "words": [
            {
                "word": word,
                "start": round(cue.start + index * step, 3),
                "end": round(cue.start + (index + 1) * step, 3),
                "score": 0.0,
            }
            for index, word in enumerate(words)
        ],
    }


def cues_to_transcript(cues: list[SubtitleCue], *, language: str | None, source: str, sha256: str | None) -> dict:
    return {
        "language": language or "und",
        "segments": [cue_to_segment(cue) for cue in cues],
        "transcript_source": source,
        "word_timing_source": "subtitle_interpolation",
        "subtitle_language": language,
        "subtitle_sha256": sha256,
    }
