import pytest

from clipgauge_pipeline import config


def test_quality_mode_is_validated_and_snapshotted():
    settings = config.Settings(quality_mode="best")

    snapshot = settings.to_json()

    assert snapshot["quality_mode"] == "best"
    assert config.Settings.from_json(snapshot).quality_mode == "best"


def test_unknown_quality_mode_is_rejected():
    with pytest.raises(ValueError, match="quality mode"):
        config.validate_quality_mode("experimental")


def test_legacy_cloud_settings_preserve_cloud_intent_without_private_mode():
    settings = config.Settings.from_json({
        "llm_mode": "gemini",
        "provider_model": "gemini-2.5-flash",
    })

    assert settings.quality_mode == "best"


def test_private_mode_rejects_cloud_provider_data_flow():
    with pytest.raises(ValueError, match="private mode requires a local provider"):
        config.validate_quality_mode_for_provider("private", "cloud")


def test_output_preference_is_validated_and_snapshotted():
    settings = config.Settings(output_preference="best")
    snapshot = settings.to_json()
    assert snapshot["output_preference"] == "best"
    assert config.Settings.from_json(snapshot).output_preference == "best"


def test_unknown_output_preference_is_rejected():
    with pytest.raises(ValueError):
        config.validate_output_preference("quota")


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"camera": []},
        {"provider_snapshot": []},
        {"provider_snapshot": {"id": "x", "kind": "custom", "model": "m", "capabilities": []}},
    ],
)
def test_malformed_settings_snapshot_raises_typed_error(payload):
    with pytest.raises(ValueError, match="settings snapshot"):
        config.Settings.from_json(payload)
