"""Bounded provider prompt and schema for finalist grouping."""

from __future__ import annotations

import json
from typing import Any

from ..creator_state import clip_id_for

SMART_COLLECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "collections": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 120},
                    "summary": {"type": "string", "maxLength": 240},
                    "clip_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                    },
                },
                "required": ["title", "summary", "clip_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["collections"],
    "additionalProperties": False,
}


def _compact(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def build_grouping_prompt(clips: list[dict[str, Any]], category: str) -> str:
    finalists = []
    for index, clip in enumerate(clips):
        quality = clip.get("short_quality") if isinstance(clip.get("short_quality"), dict) else {}
        finalists.append(
            {
                "clip_id": clip_id_for(clip, index),
                "title": _compact(clip.get("title"), 120),
                "description": _compact(clip.get("short_description"), 240),
                "premise": _compact(quality.get("central_premise") or clip.get("summary"), 240),
                "category": category,
                "score": clip.get("recommendation_score"),
                "best_platform": clip.get("best_platform"),
            }
        )
    return (
        "Group these already selected ClipGauge finalists by publishing theme. "
        "Do not change selection. Return strict JSON matching the schema. "
        "Use at most eight groups. Each group needs at least two clip IDs. "
        "Use only supplied IDs. Do not duplicate IDs. Zero groups is valid. "
        + json.dumps({"category": category, "finalists": finalists}, ensure_ascii=False)
    )
