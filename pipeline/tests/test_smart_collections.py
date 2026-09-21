import json

import pytest

from clipgauge_pipeline import config
from clipgauge_pipeline.collections.service import (
    create_collection,
    regenerate_smart_collections,
)
from clipgauge_pipeline.enrich.stage import stable_clip_id
from clipgauge_pipeline.ingest.manifest import default_manifest
from clipgauge_pipeline.jobs import queue


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / "home"))


def _job(tmp_path):
    source = str(tmp_path / "media.mp4")
    return queue.create_job("file", source, json.dumps(config.Settings().to_json()), default_manifest("file", source))


def _clips():
    return [
        {"start": 0.0, "end": 5.0, "title": "Payment failure", "short_description": "Payment failure explained", "summary": "payments"},
        {"start": 8.0, "end": 12.0, "title": "Refund workflow", "short_description": "Refund workflow explained", "summary": "refunds"},
        {"start": 15.0, "end": 20.0, "title": "Studio setup", "short_description": "Studio setup explained", "summary": "setup"},
    ]


def test_provider_groups_finalists_with_stable_order(tmp_path):
    job = _job(tmp_path)
    clips = _clips()
    ids = [stable_clip_id(clip, index) for index, clip in enumerate(clips)]
    calls = []

    def provider(prompt, schema):
        calls.append((prompt, schema))
        return {"collections": [{"title": "Money lessons", "summary": "Payments and refunds.", "clip_ids": [ids[1], ids[0]]}]}

    result = regenerate_smart_collections(job, clips, category="knowledge", group_provider=provider)

    assert result[0]["source"] == "ai"
    assert result[0]["clip_ids"] == ids[:2]
    assert "Payment failure" in calls[0][0]
    assert "media" not in calls[0][0]
    assert calls[0][1]["properties"]["collections"]["items"]["required"] == ["title", "summary", "clip_ids"]


def test_malformed_provider_membership_uses_deterministic_fallback(tmp_path):
    job = _job(tmp_path)
    clips = _clips()

    result = regenerate_smart_collections(
        job,
        clips,
        category="auto",
        group_provider=lambda *_: {"collections": [{"title": "Bad", "summary": "", "clip_ids": ["clip-nope", "clip-nope"]}]},
    )

    assert result[0]["source"] == "deterministic"
    assert result[0]["title"] == "Highlights"
    assert result[0]["clip_ids"] == [stable_clip_id(clips[0], 0), stable_clip_id(clips[1], 1), stable_clip_id(clips[2], 2)]


def test_provider_failure_uses_deterministic_fallback(tmp_path):
    job = _job(tmp_path)
    clips = _clips()

    def failed_provider(*_args):
        raise RuntimeError("provider unavailable")

    result = regenerate_smart_collections(job, clips, category="knowledge", group_provider=failed_provider)

    assert result[0]["source"] == "deterministic"


def test_manual_collection_survives_regeneration(tmp_path):
    job = _job(tmp_path)
    clips = _clips()
    ids = [stable_clip_id(clip, index) for index, clip in enumerate(clips)]
    manual = create_collection(job, "My series", ids[:2], clips=clips)

    result = regenerate_smart_collections(
        job,
        clips,
        category="knowledge",
        group_provider=lambda *_: {"collections": [{"title": "AI series", "summary": "", "clip_ids": ids[1:]}]},
    )

    assert result[0]["id"] == manual["id"]
    assert result[0]["user_edited"] is True
    assert result[1]["source"] == "ai"


def test_manual_collection_requires_two_clips(tmp_path):
    job = _job(tmp_path)
    clips = _clips()
    with pytest.raises(ValueError, match="at least two"):
        create_collection(job, "One clip", [stable_clip_id(clips[0], 0)], clips=clips)
