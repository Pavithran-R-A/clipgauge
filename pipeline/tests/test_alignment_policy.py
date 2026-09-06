import pytest

from clipgauge_pipeline.asr.alignment import (
    ALIGNMENT_SCHEMA_VERSION,
    FALLBACK,
    EXACT,
    alignment_policy,
    fallback_word_alignment,
)
from clipgauge_pipeline.readiness import READINESS_SCHEMA_VERSION, contract


def test_english_uses_verified_exact_alignment_policy():
    policy = alignment_policy("en")

    assert policy.status == EXACT
    assert policy.asset_id == "model:alignment:en:wav2vec2-base-960h"
    assert policy.schema_version == ALIGNMENT_SCHEMA_VERSION


def test_readiness_contract_is_versioned_and_honest():
    row = contract(
        asset_id="runtime:test",
        installed=True,
        verified=True,
        usable=False,
        repair=True,
        selected_runtime="cpu",
        selected_model="model:test",
        actual_additional_bytes=0,
        repair_reason="health check failed",
    )

    assert row["readiness_schema_version"] == READINESS_SCHEMA_VERSION
    assert row["asset_id"] == "runtime:test"
    assert row["installed"] is True
    assert row["verified"] is True
    assert row["usable"] is False
    assert row["repair"] is True
    assert row["actual_additional_bytes"] == 0


def test_tamil_has_explicit_deterministic_fallback_without_model_download():
    policy = alignment_policy("ta")

    assert policy.status == FALLBACK
    assert policy.asset_id is None
    assert "deterministic" in policy.reason.lower()


def test_fallback_word_alignment_is_bounded_and_monotonic():
    aligned = fallback_word_alignment(
        [{"start": 2.0, "end": 4.0, "text": "வணக்கம் world"}],
        duration=4.0,
    )

    words = aligned[0]["words"]
    assert [word["word"] for word in words] == ["வணக்கம்", "world"]
    assert all(2.0 <= word["start"] <= word["end"] <= 4.0 for word in words)
    assert all(left["end"] <= right["start"] for left, right in zip(words, words[1:]))


@pytest.mark.parametrize("language", ["ta", "hi", "ml", "unknown"])
def test_non_english_policy_never_promises_an_exact_asset(language):
    policy = alignment_policy(language)

    assert policy.status in {FALLBACK, "UNAVAILABLE"}
    assert policy.asset_id is None
