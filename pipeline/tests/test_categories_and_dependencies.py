import json

import pytest

from clipgauge_pipeline import config
from clipgauge_pipeline.scoring.categories import category_profile


def test_legacy_settings_migrate_to_auto_category():
    settings = config.Settings.from_json({"settings_schema_version": 4, "llm_mode": "ollama"})
    assert settings.content_category == "auto"
    assert settings.to_json()["settings_schema_version"] == 5


def test_category_profile_is_bounded_and_serializable():
    profile = category_profile("knowledge")
    payload = json.dumps({"category": profile.category, "guidance": profile.guidance})
    assert profile.category == "knowledge"
    assert len(payload) < 2000
    assert "Do not invent facts" in profile.guidance


def test_invalid_category_is_rejected():
    with pytest.raises(ValueError):
        config.validate_content_category("viral_magic")
