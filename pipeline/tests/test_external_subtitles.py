import json
import hashlib
import sqlite3
from types import SimpleNamespace

import pytest

from clipgauge_pipeline import config
from clipgauge_pipeline.ingest.manifest import default_manifest, persist
from clipgauge_pipeline.jobs import queue
from clipgauge_pipeline.transcripts.external import SubtitleError, accept_external_subtitle
from clipgauge_pipeline.transcripts.formats import SubtitleParseError, parse_srt, parse_vtt
from clipgauge_pipeline.transcripts.timing import cues_to_transcript


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / "home"))


def _job(tmp_path):
    settings = json.dumps(config.Settings().to_json())
    return queue.create_job("file", str(tmp_path / "media.mp4"), settings, default_manifest("file", str(tmp_path / "media.mp4")))


def test_legacy_jobs_table_gets_additive_input_manifest_column(tmp_path):
    config.ensure_home()
    with sqlite3.connect(config.db_path()) as connection:
        connection.execute(
            "CREATE TABLE jobs (id TEXT PRIMARY KEY, created_at REAL NOT NULL, source_type TEXT NOT NULL, source TEXT NOT NULL, title TEXT, status TEXT NOT NULL, error TEXT, settings_json TEXT NOT NULL)"
        )
    with queue._connect() as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
    assert "input_json" in columns


def test_valid_srt_bom_and_tamil_are_preserved():
    cues, malformed = parse_srt("\ufeff1\n00:00:00,000 --> 00:00:02,000\nவணக்கம் உலகம்\n", 2.0)
    assert malformed == 0
    assert cues[0].text == "வணக்கம் உலகம்"
    assert cues[0].end == 2.0


def test_valid_vtt_is_accepted():
    cues, malformed = parse_vtt("WEBVTT\n\n00:00.000 --> 00:01.500\nHello <b>world</b>\n", 2.0)
    assert malformed == 0
    assert cues[0].text == "Hello world"
    assert cues[0].end == 1.5


def test_malformed_timestamp_is_rejected_when_no_valid_cues_exist():
    with pytest.raises(SubtitleParseError):
        parse_srt("1\n00:99:00,000 --> 00:01:00,000\nBad\n", 2.0)


def test_overlap_normalization_is_deterministic_and_clamped():
    cues, malformed = parse_srt(
        "1\n00:00:00,000 --> 00:00:03,000\nFirst\n\n2\n00:00:02,000 --> 00:00:05,000\nSecond\n",
        4.0,
    )
    assert malformed == 0
    assert [(cue.start, cue.end) for cue in cues] == [(0.0, 2.0), (2.0, 4.0)]


def test_external_subtitle_is_copied_hashed_and_resumes_without_source(tmp_path):
    job = _job(tmp_path)
    source = tmp_path / "captions.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\nKeep me\n", encoding="utf-8")
    value = default_manifest("file", job.source)
    value["subtitle"].update({"mode": "external", "requested_path": str(source)})
    subtitle, transcript = accept_external_subtitle(job, value, duration=1.0)
    value["subtitle"] = subtitle
    persist(job, value)
    source.unlink()
    resumed = json.loads((job.dir / "input.json").read_text(encoding="utf-8"))
    subtitle_again, transcript_again = accept_external_subtitle(job, resumed, duration=1.0)
    assert subtitle_again["sha256"] == subtitle["sha256"]
    assert transcript_again["segments"][0]["text"] == transcript["segments"][0]["text"]


def test_ingest_checkpoint_checks_subtitle_artifact_after_media_hash(tmp_path):
    from clipgauge_pipeline.ingest.stage import IngestStage

    job = _job(tmp_path)
    media = job.dir / "media.mp4"
    media.write_bytes(b"media")
    (job.dir / "audio16k.wav").write_bytes(b"audio")
    data = {
        "media_path": str(media),
        "audio_path": str(job.dir / "audio16k.wav"),
        "source_hash": "not-the-managed-copy-hash",
        "subtitle": {"mode": "external", "artifact_path": "subtitles/source.srt"},
    }
    data["source_hash"] = hashlib.sha256(b"5media").hexdigest()[:16]
    assert IngestStage().artifacts_ok(SimpleNamespace(job_dir=job.dir), data) is False


def test_subtitle_asr_fast_path_never_loads_transcription_model(tmp_path, monkeypatch):
    from clipgauge_pipeline.asr.stage import AsrStage
    job = _job(tmp_path)
    audio = job.dir / "audio16k.wav"
    audio.write_bytes(b"fixture")
    cues, _ = parse_srt("1\n00:00:00,000 --> 00:00:01,000\nFast path\n", 1.0)
    transcript = cues_to_transcript(cues, language="en", source="external_subtitle", sha256="abc")
    ingest = {
        "audio_path": str(audio),
        "probe": {"duration_sec": 1.0},
        "subtitle": {"mode": "external"},
        "subtitle_transcript": transcript,
    }
    monkeypatch.setattr("clipgauge_pipeline.asr.stage._point_caches_at_home", lambda: pytest.fail("runtime setup must be skipped"))
    result = AsrStage().run(SimpleNamespace(job=job, settings=config.Settings(), prior={"ingest": ingest}, emit=lambda *_: None))
    assert result["transcript_source"] == "external_subtitle"
    assert result["word_timing_source"] == "subtitle_interpolation"
