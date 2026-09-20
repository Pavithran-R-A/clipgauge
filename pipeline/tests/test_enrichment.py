from types import SimpleNamespace

from clipgauge_pipeline.enrich.stage import EnrichStage, build_fallback_title, stable_clip_id
from clipgauge_pipeline import config


def _context(clips):
    return SimpleNamespace(
        prior={"score": {"clips": clips}},
        settings=config.Settings(content_category="knowledge"),
        job=SimpleNamespace(id="job-test"),
    )


def test_enrichment_always_returns_deterministic_metadata_without_provider(monkeypatch):
    def unavailable(_profile):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        "clipgauge_pipeline.enrich.stage.providers_mod.make_adapter",
        unavailable,
    )
    clip = {"start": 1.0, "end": 4.0, "summary": "A useful explanation."}
    result = EnrichStage().run(_context([clip]))
    assert result["clips"][0]["clip_id"] == stable_clip_id(clip, 0)
    assert result["clips"][0]["title"] == "A useful explanation"
    assert result["clips"][0]["title_source"] == "deterministic"


def test_fallback_title_has_bounded_default():
    assert build_fallback_title({}, 2) == "Clip 3"
