"""Soft collection proposal stage."""

from __future__ import annotations

from ..jobs.queue import Stage, StageContext
from .service import regenerate_ai_collections


class CollectionsStage(Stage):
    name = "collections"
    schema_version = 1

    def run(self, ctx: StageContext) -> dict:
        enrich = (ctx.prior or {}).get("enrich") or {}
        clips = enrich.get("clips") if isinstance(enrich, dict) else []
        if not isinstance(clips, list):
            clips = []
        try:
            collections = regenerate_ai_collections(
                ctx.job,
                clips,
                category=getattr(ctx.settings, "content_category", "auto"),
            )
            return {"collections": collections, "soft_failure": False, "warnings": []}
        except Exception as exc:  # noqa: BLE001 - collections are optional
            return {"collections": [], "soft_failure": True, "warnings": [str(exc)[:240]]}
