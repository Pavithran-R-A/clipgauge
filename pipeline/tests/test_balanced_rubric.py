import pytest

from clipgauge_pipeline.scoring import rubric, short_quality
from clipgauge_pipeline.scoring.stage import _transcript_slice


def test_balanced_schema_requires_editorial_fields():
    schema = rubric.schema_for_model("clipgauge-local/qwen3-4b-q4_k_m")

    required = set(schema["required"])
    assert {
        "central_premise",
        "payoff_sentence_id",
        "payoff_relevance_to_premise",
        "topic_coherence",
        "topic_shift_count",
        "late_new_topic",
        "syntactic_complete",
        "semantic_closure",
        "open_loop_at_end",
        "quality_tier",
    } <= required


def test_lightweight_schema_preserves_existing_contract():
    assert rubric.schema_for_model("clipgauge-local/qwen3-1.7b-q8_0") is rubric.T1_SCHEMA


def test_balanced_output_rejects_unknown_payoff_sentence():
    payload = {field: None for field in rubric.BALANCED_REQUIRED_FIELDS}
    payload.update({"payoff_sentence_id": "S9999", "quality_tier": "GOOD"})

    with pytest.raises(ValueError, match="payoff_sentence_id"):
        rubric.validate_balanced_output(payload, {"S0001", "S0002"})


def test_balanced_output_normalizes_no_payoff_sentinel():
    payload = {field: None for field in rubric.BALANCED_REQUIRED_FIELDS}
    payload.update({"payoff_sentence_id": "none", "quality_tier": "STRUCTURALLY_VALID"})

    normalized = rubric.normalize_balanced_output(payload)

    assert normalized["payoff_sentence_id"] is None


def test_sentence_ids_are_opt_in_for_balanced_prompts():
    segments = [{"start": 0.0, "end": 2.0, "speaker": 0, "words": [
        {"start": 0.0, "end": 0.5, "word": "Hello"},
    ]}]

    lightweight, _ = _transcript_slice(segments, 0.0, 2.0)
    balanced, _ = _transcript_slice(segments, 0.0, 2.0, include_sentence_ids=True)

    assert lightweight == "S0: Hello"
    assert balanced == "S0001 (speaker 0): Hello"


def test_balanced_prompt_calibrates_rich_editorial_scores():
    prompt = rubric.t1_prompt("S0001 (speaker 0): A clear reveal.", {"duration": 2})

    assert "Use 0 only when" in prompt
    assert "quality_tier must agree" in prompt


def test_contradictory_balanced_scores_use_independent_floor():
    quality = short_quality.assess(
        "This reveal answers the question completely.",
        duration=5,
        llm={
            "hook": 7,
            "hook_strength": 7,
            "standalone_comprehension": 7,
            "setup_strength": 7,
            "escalation_strength": 7,
            "payoff_strength": 7,
            "ending_completeness": 7,
            "story_shape": "hook_setup_payoff",
            "semantic_closure": 1,
            "payoff_relevance_to_premise": 0,
            "quality_tier": "GOOD",
        },
    )

    assert quality["semantic_closure_0_100"] >= 60
    assert quality["payoff_relevance_to_premise"] >= 50
