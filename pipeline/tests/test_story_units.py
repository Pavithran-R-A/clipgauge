from __future__ import annotations

from clipgauge_pipeline.candidates.story_units import (
    BOUNDARY_SCHEMA,
    BoundaryProposal,
    _contains_payoff,
    _story_candidate,
    build_sentence_units,
    cheap_filter_and_dedupe,
    generate_anchors,
    parse_boundary_proposal,
    synthesize,
)


def _segments(texts: list[str], seconds: float = 4.0) -> list[dict]:
    return [
        {"start": index * seconds, "end": (index + 1) * seconds - 0.1, "speaker": 0, "text": text, "words": []}
        for index, text in enumerate(texts)
    ]


def test_fixture_a_prefers_specific_story_shape_over_generic_reaction():
    units = build_sentence_units(_segments([
        "Okay, so here we are.",
        "Whoa, this is huge.",
        "This ordinary shed hides a three million dollar bunker.",
        "A meter of concrete protects the entire room.",
        "The bunker also stores dangerous weapons.",
        "That is why this backyard is worth millions.",
        "Anyway, moving on.",
    ]))
    result = synthesize(units, anchor_limit=8, shortlist_limit=20)
    candidates = result["candidates"]
    assert candidates
    assert any("ordinary shed" in item["central_premise"] or "three million" in item["central_premise"] for item in candidates)
    assert any(item["end"] - item["start"] < 30 for item in candidates)


def test_fixture_b_keeps_two_close_stories_distinct():
    units = build_sentence_units(_segments([
        "This hidden room has a secret elevator.",
        "The code opens a three story bunker.",
        "The elevator finally reaches the underground house.",
        "Next, this bunker grows infinite food with hydroponics.",
        "Water replaces dirt for every plant.",
        "That keeps seventy five people alive.",
    ]))
    result = synthesize(units, anchor_limit=10, shortlist_limit=20)
    keys = {tuple(item["topic_key"]) for item in result["candidates"]}
    assert len(keys) >= 2


def test_fixture_c_scene_cut_does_not_force_topic_split():
    units = build_sentence_units(
        _segments(["This bunker has a pool.", "The pool sits three floors underground.", "It still feels like outside."]),
        scene_times=[4.0],
    )
    assert len({unit.topic_id for unit in units}) == 1


def test_fixture_d_topic_change_without_scene_cut_creates_boundary():
    units = build_sentence_units(_segments([
        "The bunker has a nuclear door.",
        "Two feet of steel stop the blast.",
        "The reinforced entrance blocks every shockwave.",
        "Hydroponics grows infinite food for residents.",
        "Water replaces dirt in the underground farm.",
        "The farm keeps every resident alive.",
    ]))
    assert units[3].topic_boundary_before >= 0.62
    assert units[3].topic_id > units[2].topic_id


def test_fixture_e_short_story_does_not_expand_to_fixed_length():
    units = build_sentence_units(_segments([
        "This door is two feet thick.",
        "It can survive a nuclear blast.",
        "Whoa, there are two doors.",
    ], seconds=6.0))
    result = synthesize(units, anchor_limit=5, shortlist_limit=20)
    assert any(item["end"] - item["start"] < 20 for item in result["candidates"])


def test_fixture_f_payoff_extension_reaches_later_sentence():
    units = build_sentence_units(_segments([
        "This normal house hides a bunker.",
        "A secret code opens its elevator.",
        "We descend three stories underground.",
        "The house below has palm trees and a pool.",
    ], seconds=5.0))
    result = synthesize(units, anchor_limit=8, shortlist_limit=20)
    assert any(item["end"] >= units[-1].end for item in result["candidates"])


def test_fixture_g_quiet_video_can_have_no_survivors():
    units = build_sentence_units(_segments([
        "The room is here.", "The room is there.", "We continue walking.",
    ], seconds=5.0))
    assert cheap_filter_and_dedupe([]) == []
    result = synthesize(units, anchor_limit=3, shortlist_limit=10)
    assert result["candidates"] == []


def test_boundary_schema_and_ids_are_strict():
    units = build_sentence_units(_segments(["Why is this bunker hidden?", "Because it is underground."]))
    payload = {
        "best_start_sentence_id": units[0].sentence_id,
        "best_end_sentence_id": units[1].sentence_id,
        "central_premise": "A hidden bunker is underground.",
        "hook_sentence_id": units[0].sentence_id,
        "payoff_sentence_id": units[1].sentence_id,
        "story_shape": "question_answer",
        "why_start": "It opens a question.",
        "why_end": "It answers the question.",
    }
    assert parse_boundary_proposal(payload, units)
    payload["payoff_sentence_id"] = "S9999"
    assert parse_boundary_proposal(payload, units) is None
    assert set(BOUNDARY_SCHEMA["required"]) == set(BOUNDARY_SCHEMA["properties"])


def test_bounded_boundary_proposer_can_return_multiple_variants():
    units = build_sentence_units(_segments([
        "Why is this bunker hidden?", "It sits under an ordinary house.",
        "The secret elevator opens below.", "Whoa, there is a pool underground.",
    ], seconds=5.0))

    def proposer(neighborhood, _anchor):
        assert all(unit in units for unit in neighborhood)
        return [BoundaryProposal(
            units[0].sentence_id, units[2].sentence_id, "A hidden house opens underground.",
            units[0].sentence_id, units[2].sentence_id, "question_answer", "question", "reveal",
        )]

    result = synthesize(units, boundary_proposer=proposer, anchor_limit=4, boundary_limit=1, shortlist_limit=20)
    assert result["boundary_calls"] == 1
    assert any(item["story_variant"].startswith("llm-") for item in result["candidates"])


def test_punctuation_is_not_payoff_evidence():
    units = build_sentence_units(_segments([
        "This bunker is underground.",
        "The room has a steel door.",
    ], seconds=5.0))
    assert _contains_payoff(units[-1]) is False


def test_syntax_and_semantic_closure_are_separate():
    units = build_sentence_units(_segments([
        "This bunker is underground.",
        "The room has a steel door.",
    ], seconds=5.0))
    candidate = _story_candidate(units, units[0], "plain")
    assert candidate is not None
    assert candidate["syntactic_complete"] is True
    assert candidate["payoff_candidate"] is False
    assert candidate["semantic_closure"] is None


def test_standalone_score_does_not_assume_any_token_is_context_free():
    units = build_sentence_units(_segments([
        "This is an incredible room in the bunker.",
        "It has a steel door.",
    ], seconds=5.0))
    candidate = _story_candidate(units, units[0], "plain")
    assert candidate is not None
    assert 0.0 < candidate["standalone_comprehension"] < 80.0


def test_minute_bucket_keeps_semantically_distinct_stories():
    def candidate(start: float, topic: str) -> dict:
        return {
            "start": start,
            "end": start + 10.0,
            "sentence_ids": [f"{topic}-1", f"{topic}-2"],
            "central_premise": f"A story about {topic}.",
            "payoff_sentence": f"The {topic} result is surprising.",
            "topic_key": [topic],
            "story_variant": f"det-{topic}",
            "syntactic_complete": True,
            "editorial_signal": True,
            "hook_strength": 0.5,
            "duration_fit": 1.0,
            "semantic_closure": None,
            "topic_coherence": 80.0,
            "curve_score": 0.5,
        }

    result = cheap_filter_and_dedupe([
        candidate(0.0, "bunker"),
        candidate(20.0, "hydroponics"),
        candidate(40.0, "weapons"),
    ], limit=3)
    assert len(result) == 3


def test_duplicate_with_unknown_payoff_time_does_not_crash():
    base = {
        "start": 0.0,
        "end": 10.0,
        "sentence_ids": ["one", "two"],
        "central_premise": "A bunker story.",
        "payoff_sentence": "The bunker opens.",
        "topic_key": ["bunker"],
        "story_variant": "det-one",
        "syntactic_complete": True,
        "editorial_signal": True,
        "hook_strength": 0.5,
        "duration_fit": 1.0,
        "semantic_closure": None,
        "topic_coherence": 80.0,
        "curve_score": 0.5,
        "payoff_time": None,
    }
    duplicate = {**base, "start": 20.0, "end": 30.0, "story_variant": "det-two", "payoff_time": 25.0}
    assert len(cheap_filter_and_dedupe([base, duplicate], limit=2)) == 1


def test_positive_story_has_cheap_payoff_evidence():
    units = build_sentence_units(_segments([
        "Why is this bunker worth a million dollars?",
        "Because it contains dangerous weapons.",
    ], seconds=5.0))
    candidate = _story_candidate(units, units[0], "positive")
    assert candidate is not None
    assert candidate["payoff_candidate"] is True
    assert candidate["payoff_confidence"] > 0.0


def test_plain_story_has_no_cheap_payoff_evidence():
    units = build_sentence_units(_segments([
        "This bunker is underground.",
        "The room has a steel door.",
    ], seconds=5.0))
    candidate = _story_candidate(units, units[0], "negative")
    assert candidate is not None
    assert candidate["payoff_candidate"] is False


def test_premise_fact_is_not_mistaken_for_payoff():
    units = build_sentence_units(_segments([
        "If you're wondering why this bunker is worth $3 million, it's because of dangerous weapons.",
        "That is a backpack flamethrower.",
        "Oh my gosh, this is crazy.",
    ], seconds=5.0))
    candidate = _story_candidate(units, units[0], "premise")
    assert candidate is not None
    assert candidate["payoff_sentence_id"] == units[-1].sentence_id
