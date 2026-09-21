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


def test_knowledge_enrichment_uses_provider_and_preserves_category_guidance(monkeypatch):
    prompts = []
    clip = {"start": 1.0, "end": 4.0, "summary": "A useful explanation."}

    class Client:
        model = "fixture-model"
        actual_model = "fixture-model"

        def generate_json(self, prompt, _schema):
            prompts.append(prompt)
            return {
                "clips": [{
                    "clip_id": stable_clip_id(clip, 0),
                    "title": "Knowledge hook",
                    "short_description": "A concise explanation.",
                }]
            }

    monkeypatch.setattr(
        "clipgauge_pipeline.enrich.stage.providers_mod.profile_from_snapshot",
        lambda _snapshot: SimpleNamespace(
            id="fixture-profile",
            kind="ollama",
            capabilities=SimpleNamespace(local=True),
        ),
    )
    monkeypatch.setattr("clipgauge_pipeline.enrich.stage.providers_mod.make_adapter", lambda _profile: Client())

    result = EnrichStage().run(_context([clip]))

    assert '"category": "knowledge"' in prompts[0]
    assert result["category"] == "knowledge"
    assert result["clips"][0]["title"] == "Knowledge hook"
    assert result["clips"][0]["title_source"] == "model"
    assert result["clips"][0]["enrichment_provider"]["local"] is True
