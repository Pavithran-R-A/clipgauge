"""Soft finalist metadata enrichment."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .. import protocol
from ..jobs.queue import Stage, StageContext
from ..scoring import providers as providers_mod

TITLE_LIMIT = 100
DESCRIPTION_LIMIT = 240

ENRICH_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clip_id": {"type": "string"},
                    "title": {"type": "string"},
                    "short_description": {"type": "string"},
                },
                "required": ["clip_id", "title", "short_description"],
            },
        }
    },
    "required": ["clips"],
}


def stable_clip_id(clip: dict[str, Any], index: int) -> str:
    raw = f"{index}:{float(clip.get('start', 0.0)):.3f}:{float(clip.get('end', 0.0)):.3f}"
    return "clip-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _compact(value: Any, limit: int = 360) -> str:
    return " ".join(str(value or "").split())[:limit]


def _fallback_basis(clip: dict[str, Any]) -> str:
    short_quality = clip.get("short_quality") if isinstance(clip.get("short_quality"), dict) else {}
    ledger = clip.get("ledger") if isinstance(clip.get("ledger"), dict) else {}
    return _compact(
        short_quality.get("central_premise")
        or ledger.get("central_premise")
        or clip.get("summary")
        or clip.get("hook_sentence")
        or clip.get("payoff_sentence")
    )


def build_fallback_title(clip: dict[str, Any], index: int) -> str:
    basis = _fallback_basis(clip)
    if basis:
        title = re.split(r"[.!?]", basis, maxsplit=1)[0].strip()
        if title:
            return title[:TITLE_LIMIT].rstrip()
    return f"Clip {index + 1}"


def _fallback_description(clip: dict[str, Any], index: int) -> str:
    basis = _fallback_basis(clip)
    if basis:
        return basis[:DESCRIPTION_LIMIT].rstrip()
    return f"Clip {index + 1} from the selected finalist."


def _prompt(clips: list[dict[str, Any]], category: str) -> str:
    evidence = []
    for index, clip in enumerate(clips):
        evidence.append(
            {
                "clip_id": stable_clip_id(clip, index),
                "category": category,
                "start": round(float(clip.get("start", 0.0)), 3),
                "end": round(float(clip.get("end", 0.0)), 3),
                "summary": _compact(clip.get("summary")),
                "premise": _compact((clip.get("short_quality") or {}).get("central_premise") if isinstance(clip.get("short_quality"), dict) else ""),
                "hook": _compact(clip.get("hook_sentence")),
                "payoff": _compact(clip.get("payoff_sentence")),
                "platform": clip.get("best_platform"),
                "score": clip.get("recommendation_score"),
            }
        )
    return (
        "Create concise publishing metadata for these already selected ClipGauge finalists. "
        "Do not change selection, scores, timing, or evidence. Use only supplied evidence. "
        f"Return strict JSON matching the schema. Titles max {TITLE_LIMIT} characters; "
        f"descriptions max {DESCRIPTION_LIMIT} characters. Category is bounded guidance only.\n"
        + json.dumps(evidence, ensure_ascii=False)
    )


class EnrichStage(Stage):
    name = "enrich"
    schema_version = 1

    def run(self, ctx: StageContext) -> dict:
        score = (ctx.prior or {}).get("score") or {}
        finalists = score.get("clips") if isinstance(score, dict) else []
        if not isinstance(finalists, list):
            finalists = []
        prepared: list[dict[str, Any]] = []
        for index, clip in enumerate(finalists):
            if not isinstance(clip, dict):
                continue
            item = dict(clip)
            item["clip_id"] = stable_clip_id(item, index)
            item["title"] = build_fallback_title(item, index)
            item["short_description"] = _fallback_description(item, index)
            item["title_source"] = "deterministic"
            item["description_source"] = "deterministic"
            prepared.append(item)
        if not prepared:
            return {"clips": [], "soft_failure": False, "warnings": [], "category": getattr(ctx.settings, "content_category", "auto")}

        warnings: list[str] = []
        try:
            profile = providers_mod.profile_from_snapshot(ctx.settings.provider_snapshot())
            client = providers_mod.make_adapter(profile)
            response = client.generate_json(
                _prompt(prepared, getattr(ctx.settings, "content_category", "auto")),
                ENRICH_SCHEMA,
            )
            rows = response.get("clips") if isinstance(response, dict) else None
            if not isinstance(rows, list):
                raise ValueError("enrichment response did not contain clips")
            by_id = {str(row.get("clip_id")): row for row in rows if isinstance(row, dict)}
            for item in prepared:
                row = by_id.get(item["clip_id"])
                if not isinstance(row, dict):
                    warnings.append(f"missing metadata for {item['clip_id']}")
                    continue
                title = _compact(row.get("title"), TITLE_LIMIT).strip()
                description = _compact(row.get("short_description"), DESCRIPTION_LIMIT).strip()
                if title:
                    item["title"] = title
                    item["title_source"] = "model"
                if description:
                    item["short_description"] = description
                    item["description_source"] = "model"
            provider = {
                "provider_kind": profile.kind,
                "provider_profile_id": profile.id,
                "model": getattr(client, "actual_model", client.model),
                "local": bool(profile.capabilities.local),
            }
        except Exception as exc:  # noqa: BLE001 - metadata is explicitly soft-fail
            warnings.append(protocol.safe_message(str(exc), limit=240) or "provider unavailable")
            provider = {"provider_kind": None, "provider_profile_id": None, "model": None, "local": None}
        for item in prepared:
            item["enrichment_provider"] = provider
        return {
            "clips": prepared,
            "soft_failure": bool(warnings),
            "warnings": warnings[:8],
            "category": getattr(ctx.settings, "content_category", "auto"),
        }
