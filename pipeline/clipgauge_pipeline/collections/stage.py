"""Soft collection proposal stage."""

from __future__ import annotations

from ..jobs.queue import Stage, StageContext
from ..scoring import providers as providers_mod
from .service import regenerate_smart_collections


class CollectionsStage(Stage):
    name = "collections"
    schema_version = 1

    def run(self, ctx: StageContext) -> dict:
        enrich = (ctx.prior or {}).get("enrich") or {}
        clips = enrich.get("clips") if isinstance(enrich, dict) else []
        if not isinstance(clips, list):
            clips = []
        category = getattr(ctx.settings, "content_category", "auto")
        try:
            profile = providers_mod.profile_from_snapshot(ctx.settings.provider_snapshot())
            client = providers_mod.make_adapter(profile)

            def group_provider(prompt, schema):
                return client.generate_json(prompt, schema, purpose="collections", job_id=ctx.job.id)

            collections = regenerate_smart_collections(
                ctx.job,
                clips,
                category=category,
                group_provider=group_provider,
            )
            return {
                "collections": collections,
                "soft_failure": False,
                "warnings": [],
                "category": category,
                "grouping_provider": {
                    "provider_kind": profile.kind,
                    "provider_profile_id": profile.id,
                    "model": getattr(client, "actual_model", client.model),
                    "local": bool(profile.capabilities.local),
                },
            }
        except Exception as exc:  # noqa: BLE001 - collections are optional
            try:
                collections = regenerate_smart_collections(ctx.job, clips, category=category)
            except Exception:
                collections = []
            return {
                "collections": collections,
                "soft_failure": True,
                "warnings": [str(exc)[:240]],
                "category": category,
            }
