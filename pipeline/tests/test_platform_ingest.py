from clipgauge_pipeline.ingest.platforms import SourcePlatform, caption_tracks, classify_source, select_platform_caption


def test_supported_platform_classifier():
    assert classify_source("https://www.youtube.com/watch?v=abc123") == SourcePlatform.YOUTUBE
    assert classify_source("https://bilibili.com/video/BV1xx411c7mD") == SourcePlatform.BILIBILI
    assert classify_source("https://b23.tv/abc123") == SourcePlatform.BILIBILI
    assert classify_source("https://example.com/video") == SourcePlatform.UNSUPPORTED_URL
    assert classify_source("C:/videos/talk.mp4") == SourcePlatform.LOCAL


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
