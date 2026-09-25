import pytest

from clipgauge_pipeline import config
from clipgauge_pipeline.ingest.platforms import SourcePlatform, caption_tracks, classify_source, select_platform_caption


def test_supported_platform_classifier():
    assert classify_source("https://www.youtube.com/watch?v=abc123") == SourcePlatform.YOUTUBE
    assert classify_source("https://bilibili.com/video/BV1xx411c7mD") == SourcePlatform.BILIBILI
    assert classify_source("https://b23.tv/abc123") == SourcePlatform.BILIBILI
    assert classify_source("https://example.com/video") == SourcePlatform.UNSUPPORTED_URL
    assert classify_source("C:/videos/talk.mp4") == SourcePlatform.LOCAL


@pytest.mark.parametrize(
    "source",
    [
        "https://example.com/video",
        "ftp://example.com/video.mp4",
        "file:///tmp/video.mp4",
        "https://youtube.com.attacker.example/watch?v=abc123",
        "https://bilibili.com.attacker.example/video/BV1xx411c7mD",
        "https://",
    ],
)
def test_unsupported_sources_are_rejected_before_transfer(source):
    assert classify_source(source) == SourcePlatform.UNSUPPORTED_URL


def test_supported_domains_use_host_boundaries():
    assert classify_source("https://youtube.com/watch?v=abc123") == SourcePlatform.YOUTUBE
    assert classify_source("https://sub.youtube.com/watch?v=abc123") == SourcePlatform.YOUTUBE
    assert classify_source("https://bilibili.com/video/BV1xx411c7mD") == SourcePlatform.BILIBILI
    assert classify_source("https://sub.bilibili.com/video/BV1xx411c7mD") == SourcePlatform.BILIBILI


def test_unsupported_ingest_fails_before_ytdlp(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from clipgauge_pipeline.ingest.stage import IngestStage

    monkeypatch.setattr(config, "home_dir", lambda: tmp_path / "home")
    monkeypatch.setattr("clipgauge_pipeline.ingest.stage.ytdlp.fetch_meta", pytest.fail)
    job = SimpleNamespace(source_type="url", source="https://example.com/video", dir=tmp_path / "job", id="job")
    job.dir.mkdir()
    with pytest.raises(Exception) as error:
        IngestStage().run(SimpleNamespace(job=job, settings=config.Settings(), emit=lambda *_: None))
    assert getattr(error.value, "code", None) == "SOURCE_URL_UNSUPPORTED"


def test_caption_selection_prefers_requested_human_language():
    selected = select_platform_caption(
        [
            {"language": "en", "url": "auto", "automatic": True},
            {"language": "ta", "url": "human-ta", "automatic": False},
            {"language": "en", "url": "human-en", "automatic": False},
        ],
        requested_language="ta",
    )
    assert selected is not None
    assert selected.url == "human-ta"
    assert selected.automatic is False


def test_caption_selection_is_deterministic_without_request():
    selected = select_platform_caption(
        [
            {"language": "en", "url": "auto", "automatic": True},
            {"language": "de", "url": "human-de", "automatic": False},
        ]
    )
    assert selected is not None
    assert selected.url == "human-de"


def test_caption_tracks_normalizes_human_and_automatic_metadata():
    tracks = caption_tracks({
        "extractor_key": "youtube",
        "subtitles": {"en": [{"url": "human", "ext": "vtt"}]},
        "automatic_captions": {"en": [{"url": "auto", "ext": "vtt"}]},
    })
    assert tracks == [
        {"language": "en", "url": "human", "automatic": False, "ext": "vtt", "source": "platform_human", "extractor": "youtube"},
        {"language": "en", "url": "auto", "automatic": True, "ext": "vtt", "source": "platform_automatic", "extractor": "youtube"},
    ]
