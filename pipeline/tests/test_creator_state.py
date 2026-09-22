import json

import pytest
from clipgauge_pipeline import config
from clipgauge_pipeline.creator_state import (
    apply_title_overrides,
    creator_clips_for_job,
    load_title_overrides,
    reset_title_override,
    set_title_override,
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


def _clip(start=0.0, end=5.0, title="Generated title"):
    return {"start": start, "end": end, "title": title, "title_source": "model"}


def _write_stage(job, name, data):
    (job.dir / f"{name}.json").write_text(
        json.dumps({"stage": name, "schema_version": 1, "data": data}),
        encoding="utf-8",
    )


def test_title_override_persists_unicode_and_normalizes_whitespace(tmp_path):
    job = _job(tmp_path)
    clips = [_clip()]
    clip_id = stable_clip_id(clips[0], 0)

    stored = set_title_override(job, clip_id, "  Café — Résumé  ", clips)

    assert stored["title"] == "Café — Résumé"
    assert load_title_overrides(job)["clips"][clip_id]["title"] == "Café — Résumé"
    assert not list(job.dir.glob(".creator-overrides.json.*.tmp"))


def test_update_title_replaces_existing_override(tmp_path):
    job = _job(tmp_path)
    clips = [_clip()]
    clip_id = stable_clip_id(clips[0], 0)

    set_title_override(job, clip_id, "First", clips)
    set_title_override(job, clip_id, "Second", clips)

    assert load_title_overrides(job)["clips"][clip_id]["title"] == "Second"


def test_blank_oversized_and_unknown_titles_are_rejected(tmp_path):
    job = _job(tmp_path)
    clips = [_clip()]
    clip_id = stable_clip_id(clips[0], 0)

    with pytest.raises(ValueError, match="blank"):
        set_title_override(job, clip_id, " \t\n", clips)
    with pytest.raises(ValueError, match="120"):
        set_title_override(job, clip_id, "x" * 121, clips)
    with pytest.raises(ValueError, match="unknown clip"):
        set_title_override(job, "clip-missing", "Valid", clips)


def test_reset_removes_only_manual_override(tmp_path):
    job = _job(tmp_path)
    clips = [_clip()]
    clip_id = stable_clip_id(clips[0], 0)
    set_title_override(job, clip_id, "Edited", clips)

    reset_title_override(job, clip_id, clips)

    assert load_title_overrides(job)["clips"] == {}


def test_historical_job_without_override_file_stays_valid(tmp_path):
    job = _job(tmp_path)

    assert load_title_overrides(job) == {"schema_version": 1, "job_id": job.id, "clips": {}}


def test_override_wins_after_reload_and_enrichment_rerun(tmp_path):
    job = _job(tmp_path)
    clips = [_clip()]
    clip_id = stable_clip_id(clips[0], 0)
    set_title_override(job, clip_id, "Creator title", clips)

    reloaded_enrich = [{"clip_id": clip_id, "title": "New model title", "title_source": "model"}]
    result = apply_title_overrides(reloaded_enrich, load_title_overrides(job))

    assert result[0]["title"] == "Creator title"
    assert result[0]["title_source"] == "user"
    assert reloaded_enrich[0]["title"] == "New model title"


def test_creator_clips_normalize_legacy_score_ids_and_merge_render_paths(tmp_path):
    job = _job(tmp_path)
    score_clips = [_clip(0, 5, "First"), _clip(8, 12, "Second")]
    render_dir = job.dir / "clips"
    render_dir.mkdir()
    first_path = render_dir / "clip_00.mp4"
    second_path = render_dir / "clip_01.mp4"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    _write_stage(job, "score", {"clips": score_clips})
    _write_stage(job, "render", {
        "outputs": [
            {"clip": 0, "path": "clips/clip_00.mp4"},
            {"clip": 1, "path": "clips/clip_01.mp4"},
        ]
    })

    result = creator_clips_for_job(job)

    assert [item["clip_id"] for item in result] == [
        stable_clip_id(score_clips[0], 0),
        stable_clip_id(score_clips[1], 1),
    ]
    assert result[0]["render_path"] == str(first_path.resolve())
    assert result[1]["render_path"] == str(second_path.resolve())


def test_creator_clips_preserve_ids_and_prefer_enriched_content(tmp_path):
    job = _job(tmp_path)
    score_clips = [{**_clip(0, 5), "clip_id": "clip-custom"}]
    enrich_clips = [{**score_clips[0], "title": "Enriched title", "summary": "Evidence"}]
    _write_stage(job, "score", {"clips": score_clips})
    _write_stage(job, "enrich", {"clips": enrich_clips})

    result = creator_clips_for_job(job)

    assert result == [{
        **score_clips[0],
        "title": "Enriched title",
        "summary": "Evidence",
    }]


def test_creator_clips_do_not_pair_render_outputs_by_length(tmp_path):
    job = _job(tmp_path)
    score_clips = [_clip(0, 5), _clip(8, 12)]
    render_dir = job.dir / "clips"
    render_dir.mkdir()
    (render_dir / "clip_00.mp4").write_bytes(b"first")
    _write_stage(job, "score", {"clips": score_clips})
    _write_stage(job, "render", {
        "outputs": [{"path": "clips/clip_00.mp4"}]
    })

    result = creator_clips_for_job(job)

    assert "render_path" not in result[0]
    assert "render_path" not in result[1]


def test_legacy_creator_title_persists_after_reload(tmp_path):
    job = _job(tmp_path)
    _write_stage(job, "score", {"clips": [_clip(0, 5)]})
    clips = creator_clips_for_job(job)
    clip_id = clips[0]["clip_id"]

    set_title_override(job, clip_id, "Persistent creator title", clips)

    reloaded = apply_title_overrides(
        creator_clips_for_job(job),
        load_title_overrides(job),
    )

    assert reloaded[0]["clip_id"] == clip_id
    assert reloaded[0]["title"] == "Persistent creator title"
    assert reloaded[0]["title_source"] == "user"
