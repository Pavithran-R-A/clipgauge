import json

import pytest

from clipgauge_pipeline import config
from clipgauge_pipeline.collections.service import (
    create_collection,
    delete_collection,
    list_collections,
    regenerate_ai_collections,
    reorder_collection,
    update_collection,
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
    return [{"start": 0.0, "end": 5.0, "summary": "First"}, {"start": 8.0, "end": 12.0, "summary": "Second"}]


def test_ai_proposal_uses_stable_existing_clip_ids(tmp_path):
    job = _job(tmp_path)
    clips = _clips()
    result = regenerate_ai_collections(job, clips, category="knowledge")
    assert len(result) == 1
    assert result[0]["source"] == "ai"
    assert result[0]["clip_ids"] == [stable_clip_id(clips[0], 0), stable_clip_id(clips[1], 1)]


def test_manual_edits_are_atomic_and_preserved(tmp_path):
    job = _job(tmp_path)
    clips = _clips()
    ids = [stable_clip_id(clip, index) for index, clip in enumerate(clips)]
    created = create_collection(job, "My series", ids, clips=clips)
    changed = update_collection(job, created["id"], title="Renamed", clips=clips)
    assert changed["title"] == "Renamed"
    reordered = reorder_collection(job, created["id"], list(reversed(ids)), clips=clips)
    assert reordered["clip_ids"] == list(reversed(ids))
    assert list_collections(job, clips)[0]["user_edited"] is True
    delete_collection(job, created["id"], clips=clips)
    assert list_collections(job, clips) == []


def test_unknown_clip_id_is_rejected(tmp_path):
    job = _job(tmp_path)
    with pytest.raises(ValueError):
        create_collection(job, "Bad", ["clip-missing"], clips=_clips())
