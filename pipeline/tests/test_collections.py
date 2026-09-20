import json
from pathlib import Path

import pytest

from clipgauge_pipeline import config
from clipgauge_pipeline.collections.service import (
    create_collection,
    delete_collection,
    list_collections,
    regenerate_smart_collections,
    reorder_collection,
    update_collection,
)
from clipgauge_pipeline.collections.render import render_collection
from clipgauge_pipeline.collections import render as collection_render
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


def test_provider_proposal_uses_stable_existing_clip_ids(tmp_path):
    job = _job(tmp_path)
    clips = _clips()
    ids = [stable_clip_id(clip, index) for index, clip in enumerate(clips)]
    result = regenerate_smart_collections(
        job,
        clips,
        category="knowledge",
        group_provider=lambda *_: {"collections": [{"title": "Knowledge", "summary": "", "clip_ids": ids}]},
    )
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


def test_creator_service_reads_pipeline_collection_checkpoint(tmp_path):
    job = _job(tmp_path)
    clips = _clips()
    ids = [stable_clip_id(clip, index) for index, clip in enumerate(clips)]
    (job.dir / "collections.json").write_text(
        json.dumps({
            "stage": "collections",
            "schema_version": 1,
            "data": {
                "schema_version": 1,
                "job_id": job.id,
                "collections": [{
                    "id": "collection-stage",
                    "title": "Stage series",
                    "clip_ids": ids,
                    "source": "ai",
                    "user_edited": False,
                }],
            },
        }),
        encoding="utf-8",
    )

    assert list_collections(job, clips)[0]["title"] == "Stage series"


def test_render_collection_resolves_relative_render_paths_inside_job(tmp_path, monkeypatch):
    job = _job(tmp_path)
    clips_dir = job.dir / "clips"
    clips_dir.mkdir()
    (clips_dir / "clip_00.mp4").write_bytes(b"first")
    (clips_dir / "clip_01.mp4").write_bytes(b"second")
    clips = [
        {"start": 0.0, "end": 5.0, "summary": "First", "render_path": "clips/clip_00.mp4"},
        {"start": 8.0, "end": 12.0, "summary": "Second", "render_path": "clips/clip_01.mp4"},
    ]
    ids = [stable_clip_id(clip, index) for index, clip in enumerate(clips)]
    created = create_collection(job, "Relative Paths", list(reversed(ids)), clips=clips)

    def fake_run(command, **_kwargs):
        list_path = Path(command[command.index("-i") + 1])
        assert list_path.exists()
        temporary = Path(command[-1])
        temporary.write_bytes(b"compiled")
        return type("Completed", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr(collection_render.ffmpeg_bin, "ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(collection_render.subprocess, "run", fake_run)
    monkeypatch.setattr(
        collection_render.normalize,
        "probe",
        lambda _path: type("Probe", (), {"has_audio": True, "duration_sec": 10.0})(),
    )

    output = render_collection(job, created["id"], clips)

    assert output == job.dir / "collections" / "Relative-Paths.mp4"
    assert output.read_bytes() == b"compiled"
    assert list_collections(job, clips)[0]["render_path"] == str(output)
    assert not list((job.dir / "collections").glob(".*.txt"))
