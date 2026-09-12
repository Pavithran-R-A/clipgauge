from __future__ import annotations

from dataclasses import replace

from clipgauge_pipeline.candidates.story_units import (
    BOUNDARY_SCHEMA,
    BoundaryProposal,
    _contains_payoff,
    _has_explicit_outcome,
    _candidate_start_indices,
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


def test_story_units_preserve_non_latin_tokens():
    units = build_sentence_units(_segments(["தமிழ் மொழி மிகவும் அழகானது."]))

    assert units
    assert units[0].tokens
    assert any("தமிழ்" in token for token in units[0].tokens)


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
    audit = result["candidate_audit"]
    assert audit["raw_proposals"] == audit["story_unit_proposals"]
    assert audit["deduped_proposals"] >= audit["shortlisted_proposals"]
    assert audit["rejection_reasons"]


def test_anchor_generation_preserves_distinct_story_topics():
    units = build_sentence_units(_segments([
        "The first story reveals a hidden bunker.",
        "The second story reveals a secret elevator.",
        "The third story reveals an underground pool.",
    ], seconds=10.0))
    labeled = [replace(unit, topic_id=index) for index, unit in enumerate(units)]

    anchors = generate_anchors(labeled, limit=3)

    assert {anchor.topic_id for anchor in anchors} == {0, 1, 2}


def test_anchor_generation_respects_zero_limit():
    units = build_sentence_units(_segments(["A complete story starts here.", "The story ends clearly."], seconds=5.0))

    assert generate_anchors(units, limit=0) == []


def test_fixture_g_quiet_video_can_have_no_survivors():
    units = build_sentence_units(_segments([
        "The room is here.", "The room is there.", "We continue walking.",
    ], seconds=5.0))
    assert cheap_filter_and_dedupe([]) == []
    result = synthesize(units, anchor_limit=3, shortlist_limit=10)
    assert result["candidates"] == []


def test_candidate_filter_reports_every_discard_reason():
    def candidate(candidate_id: str, topic: str, *, complete: bool = True) -> dict:
        return {
            "candidate_id": candidate_id,
            "anchor_sentence_id": "S1",
            "start": 0.0 if topic == "alpha" else 60.0,
            "end": 20.0 if topic == "alpha" else 80.0,
            "syntactic_complete": complete,
            "central_premise": topic,
            "sentence_ids": ["S1", "S2"],
            "editorial_signal": True,
            "story_variant": "det",
            "duration_fit": 1.0,
            "information_density": 1.0,
            "curve_score": 1.0,
            "hook_strength": 1.0,
            "payoff_candidate": True,
            "topic_coherence": 100.0,
            "topic_key": [topic],
            "payoff_sentence": f"{topic} payoff",
        }

    audit: list[dict] = []
    result = cheap_filter_and_dedupe(
        [
            candidate("incomplete", "alpha", complete=False),
            candidate("kept", "alpha"),
            candidate("duplicate", "alpha"),
            candidate("over_limit", "beta"),
            candidate("over_limit_two", "gamma"),
        ],
        limit=2,
        audit=audit,
    )

    assert [item["candidate_id"] for item in result] == ["kept", "over_limit"]
    reasons = {reason for item in audit for reason in item.get("rejection_reasons", [])}
    assert {"INCOMPLETE_ENDING", "DUPLICATE_STORY", "SHORTLIST_LIMIT"} <= reasons


def test_candidate_filter_keeps_distant_story_units_with_shared_terms():
    def candidate(candidate_id: str, start: float) -> dict:
        return {
            "candidate_id": candidate_id,
            "start": start,
            "end": start + 20.0,
            "syntactic_complete": True,
            "central_premise": "A surprising result",
            "sentence_ids": [f"{candidate_id}-1", f"{candidate_id}-2"],
            "editorial_signal": True,
            "story_variant": "det",
            "duration_fit": 1.0,
            "information_density": 1.0,
            "curve_score": 1.0,
            "hook_strength": 1.0,
            "payoff_candidate": True,
            "topic_coherence": 100.0,
            "topic_key": ["challenge", "result"],
            "payoff_sentence": "The result changes everything.",
        }

    result = cheap_filter_and_dedupe([
        candidate("early-story", 0.0),
        candidate("late-story", 180.0),
    ], limit=10)

    assert [item["candidate_id"] for item in result] == ["early-story", "late-story"]


def test_shortlist_preserves_uncovered_leading_story_coverage():
    def candidate(candidate_id: str, start: float, quality: float) -> dict:
        return {
            "candidate_id": candidate_id,
            "start": start,
            "end": start + 20.0,
            "syntactic_complete": True,
            "central_premise": f"A distinct premise for {candidate_id}.",
            "sentence_ids": [f"{candidate_id}-1", f"{candidate_id}-2"],
            "editorial_signal": True,
            "story_variant": "det",
            "duration_fit": quality,
            "information_density": quality,
            "curve_score": quality,
            "hook_strength": quality,
            "payoff_candidate": True,
            "topic_coherence": quality * 100.0,
            "topic_key": [candidate_id],
            "payoff_sentence": f"The {candidate_id} payoff is clear.",
        }

    candidates = [
        candidate("early-story", 0.0, 0.1),
        candidate("later-story-same-bucket", 30.0, 1.0),
    ]
    candidates.extend(
        candidate(f"story-{index}", 60.0 + bucket * 60.0, 1.0)
        for bucket in range(6)
        for index in range(bucket * 4, bucket * 4 + 4)
    )

    result = cheap_filter_and_dedupe(candidates, limit=7)

    result_ids = {item["candidate_id"] for item in result}
    assert "early-story" in result_ids


def test_shortlist_preserves_later_payoff_boundary_variant():
    def candidate(candidate_id: str, start: float, end: float, payoff_time: float, quality: float) -> dict:
        return {
            "candidate_id": candidate_id,
            "anchor_sentence_id": candidate_id,
            "start": start,
            "end": end,
            "syntactic_complete": True,
            "central_premise": "A distinct result is revealed.",
            "sentence_ids": [f"{candidate_id}-1", f"{candidate_id}-2"],
            "editorial_signal": True,
            "story_variant": "det",
            "duration_fit": quality,
            "information_density": quality,
            "curve_score": quality,
            "hook_strength": quality,
            "payoff_candidate": True,
            "payoff_time": payoff_time,
            "topic_coherence": quality * 100.0,
            "topic_key": ["distinct", "result"],
            "payoff_sentence": "The result is revealed.",
        }

    result = cheap_filter_and_dedupe([
        candidate("early", 0.0, 30.0, 28.0, 1.0),
        candidate("late", 20.0, 60.0, 58.0, 0.9),
    ], limit=1)

    assert [item["candidate_id"] for item in result] == ["late"]


def test_shortlist_does_not_replace_later_payoff_with_leading_duplicate():
    def candidate(candidate_id: str, anchor: str, start: float, end: float, payoff_time: float, quality: float) -> dict:
        return {
            "candidate_id": candidate_id,
            "anchor_sentence_id": anchor,
            "start": start,
            "end": end,
            "syntactic_complete": True,
            "central_premise": "A plane landing result.",
            "sentence_ids": [f"{anchor}-1", f"{anchor}-2"],
            "editorial_signal": True,
            "story_variant": "det",
            "duration_fit": quality,
            "information_density": quality,
            "curve_score": quality,
            "hook_strength": quality,
            "payoff_candidate": True,
            "payoff_time": payoff_time,
            "payoff_boundary_explicit": True,
            "topic_coherence": 90.0,
            "topic_key": ["plane", "landing"],
            "payoff_sentence": "I landed a plane!",
            "start_topic_boundary": 0.8,
        }

    result = cheap_filter_and_dedupe([
        candidate("early", "S1", 349.6, 383.1, 379.4, 0.9),
        candidate("late", "S2", 380.9, 426.3, 425.4, 1.0),
    ], limit=1)

    assert [item["candidate_id"] for item in result] == ["late"]


def test_shortlist_keeps_explicit_payoff_against_unrelated_leading_coverage():
    def candidate(candidate_id: str, start: float, quality: float, explicit: bool = False) -> dict:
        return {
            "candidate_id": candidate_id,
            "start": start,
            "end": start + 20.0,
            "syntactic_complete": True,
            "central_premise": f"A distinct premise for {candidate_id}.",
            "sentence_ids": [f"{candidate_id}-1", f"{candidate_id}-2"],
            "editorial_signal": True,
            "story_variant": "det",
            "duration_fit": quality,
            "information_density": quality,
            "curve_score": quality,
            "hook_strength": quality,
            "payoff_candidate": True,
            "payoff_time": start + 18.0,
            "payoff_boundary_explicit": explicit,
            "topic_coherence": quality * 100.0,
            "topic_key": [candidate_id],
            "payoff_sentence": f"The {candidate_id} payoff is clear.",
        }

    result = cheap_filter_and_dedupe([
        candidate("leading", 0.0, 0.1),
        candidate("filler", 200.0, 1.0),
        candidate("explicit-payoff", 400.0, 0.2, explicit=True),
    ], limit=2)

    assert "explicit-payoff" in {item["candidate_id"] for item in result}


def test_dedupe_keeps_overlapping_later_payoff_variant():
    def candidate(candidate_id: str, anchor: str, start: float, end: float, payoff_time: float) -> dict:
        return {
            "candidate_id": candidate_id,
            "anchor_sentence_id": anchor,
            "start": start,
            "end": end,
            "syntactic_complete": True,
            "central_premise": "A plane landing result.",
            "sentence_ids": [f"{anchor}-1", f"{anchor}-2"],
            "editorial_signal": True,
            "story_variant": "det",
            "duration_fit": 1.0,
            "information_density": 1.0,
            "curve_score": 1.0,
            "hook_strength": 0.8,
            "payoff_candidate": True,
            "payoff_time": payoff_time,
            "payoff_boundary_explicit": True,
            "topic_coherence": 90.0,
            "topic_key": ["plane", "landing"],
            "payoff_sentence": "I landed a plane!",
            "start_topic_boundary": 0.8,
        }

    result = cheap_filter_and_dedupe([
        candidate("early", "S1", 0.0, 50.0, 30.0),
        candidate("late", "S2", 10.0, 60.0, 55.0),
    ], limit=10)

    assert [item["candidate_id"] for item in result] == ["early", "late"]


def test_dedupe_preserves_later_payoff_boundary_variant():
    def candidate(candidate_id: str, end: float, payoff: bool, quality: float) -> dict:
        return {
            "candidate_id": candidate_id,
            "anchor_sentence_id": "S1",
            "start": 0.0,
            "end": end,
            "syntactic_complete": True,
            "central_premise": "A distinct result is revealed.",
            "sentence_ids": ["S1", "S2", "S3"],
            "editorial_signal": True,
            "story_variant": "det",
            "duration_fit": quality,
            "information_density": quality,
            "curve_score": 0.5,
            "hook_strength": 0.7,
            "payoff_candidate": payoff,
            "payoff_time": end - 2.0 if payoff else None,
            "topic_coherence": 90.0,
            "topic_key": ["distinct", "result"],
            "payoff_sentence": "The result is revealed.",
        }

    result = cheap_filter_and_dedupe([
        candidate("short-boundary", 20.0, False, 1.0),
        candidate("payoff-boundary", 35.0, True, 0.9),
    ], limit=10)

    assert [item["candidate_id"] for item in result] == ["payoff-boundary"]


def test_dedupe_keeps_a_strong_new_topic_separate():
    def candidate(candidate_id: str, start: float, boundary: float) -> dict:
        return {
            "candidate_id": candidate_id,
            "anchor_sentence_id": candidate_id,
            "start": start,
            "end": start + 30.0,
            "syntactic_complete": True,
            "central_premise": "The tournament game begins.",
            "sentence_ids": [f"{candidate_id}-1", f"{candidate_id}-2"],
            "editorial_signal": True,
            "story_variant": "det",
            "duration_fit": 1.0,
            "information_density": 1.0,
            "curve_score": 0.5,
            "hook_strength": 0.7,
            "payoff_candidate": True,
            "payoff_time": start + 28.0,
            "topic_coherence": 90.0,
            "topic_key": ["tournament", "game"],
            "payoff_sentence": "The tournament game begins.",
            "start_topic_boundary": boundary,
        }

    result = cheap_filter_and_dedupe([
        candidate("setup", 720.0, 0.0),
        candidate("game", 742.0, 0.8),
    ], limit=2)

    assert [item["candidate_id"] for item in result] == ["setup", "game"]


def test_dedupe_preserves_earlier_payoff_aligned_opening():
    def candidate(candidate_id: str, start: float, end: float) -> dict:
        return {
            "candidate_id": candidate_id,
            "anchor_sentence_id": "shared-anchor",
            "start": start,
            "end": end,
            "syntactic_complete": True,
            "central_premise": "A result is revealed after setup.",
            "sentence_ids": ["S1", "S2", "S3"],
            "editorial_signal": True,
            "story_variant": "det",
            "duration_fit": 0.9 if start > 20 else 0.8,
            "information_density": 1.0,
            "curve_score": 0.5,
            "hook_strength": 0.7,
            "payoff_candidate": True,
            "payoff_boundary_explicit": True,
            "payoff_time": 39.0,
            "topic_coherence": 90.0,
            "topic_key": ["result", "setup"],
            "payoff_sentence": "The result is revealed.",
            "start_topic_boundary": 0.8,
        }

    result = cheap_filter_and_dedupe([
        candidate("late-opening", 38.0, 66.0),
        candidate("setup-opening", 15.0, 62.0),
    ], limit=10)

    assert [item["candidate_id"] for item in result] == ["setup-opening"]


def test_dedupe_preserves_earlier_opening_for_same_nonexplicit_payoff():
    def candidate(candidate_id: str, start: float, end: float, quality: float) -> dict:
        return {
            "candidate_id": candidate_id,
            "anchor_sentence_id": "shared-anchor",
            "start": start,
            "end": end,
            "syntactic_complete": True,
            "central_premise": "A result is revealed after setup.",
            "sentence_ids": ["S1", "S2", "S3", "S4"],
            "editorial_signal": True,
            "story_variant": "det",
            "duration_fit": quality,
            "information_density": 1.0,
            "curve_score": 0.5,
            "hook_strength": 0.7,
            "payoff_candidate": True,
            "payoff_boundary_explicit": False,
            "payoff_time": 39.0,
            "topic_coherence": 90.0,
            "topic_key": ["result", "setup"],
            "payoff_sentence": "The result is revealed.",
            "start_topic_boundary": 0.8,
        }

    result = cheap_filter_and_dedupe([
        candidate("late-opening", 38.0, 66.0, 0.9),
        candidate("setup-opening", 15.0, 62.0, 0.8),
    ], limit=10)

    assert [item["candidate_id"] for item in result] == ["setup-opening"]


def test_candidate_start_lookback_reaches_bounded_story_setup():
    units = build_sentence_units(_segments([
        "Earlier context explains the $10 result.",
        "The setup continues with useful background.",
        "The story adds another detail here.",
        "The story adds another detail there.",
        "The anchor reveals the final result.",
    ], seconds=8.0))

    indexes = _candidate_start_indices(units, anchor_index=4)

    assert 0 in indexes
    assert all(units[index].start >= units[4].start - 35.0 for index in indexes)


def test_anchor_selection_spreads_across_long_sources():
    segments = [
        {
            "start": index * 5.0,
            "end": index * 5.0 + 4.8,
            "speaker": 0,
            "text": f"Alpha{index} beta{index} gamma{index} delta{index} epsilon{index}.",
            "words": [],
        }
        for index in range(120)
    ]

    anchors = generate_anchors(
        build_sentence_units(segments, scene_times=[index * 5.0 for index in range(1, 120)]),
        limit=12,
    )

    assert len(anchors) == 12
    assert anchors[-1].start >= 500.0
    assert len({int(anchor.start // 60) for anchor in anchors}) >= 8


def test_anchor_selection_keeps_dense_topics_over_anchor_limit():
    segments = [
        {
            "start": index * 8.0,
            "end": index * 8.0 + 7.5,
            "speaker": 0,
            "text": f"Topic {index} reveals a distinct result.",
            "words": [],
        }
        for index in range(21)
    ]
    units = build_sentence_units(segments)
    labeled = [replace(unit, topic_id=index) for index, unit in enumerate(units)]

    anchors = generate_anchors(labeled, limit=20)

    assert len(anchors) == 20
    assert len({anchor.topic_id for anchor in anchors}) == 20
    assert anchors[-1].start >= 152.0


def test_anchor_selection_ignores_sparse_tail_for_dense_topic_capacity():
    segments = [
        {
            "start": index * 8.0,
            "end": index * 8.0 + 7.5,
            "speaker": 0,
            "text": f"Topic {index} reveals a distinct result.",
            "words": [],
        }
        for index in range(21)
    ]
    segments.append({
        "start": 1000.0,
        "end": 1007.5,
        "speaker": 0,
        "text": "The epilogue reveals a distant result.",
        "words": [],
    })
    units = build_sentence_units(segments)
    labeled = [replace(unit, topic_id=index) for index, unit in enumerate(units)]

    anchors = generate_anchors(labeled, limit=20)

    assert len(anchors) == 20
    assert sum(anchor.start < 200.0 for anchor in anchors) >= 19


def test_anchor_selection_keeps_uneven_dense_topics_over_anchor_limit():
    starts = [0.0]
    for index in range(1, 21):
        starts.append(starts[-1] + (1.0 if index % 2 else 9.0))
    segments = [
        {
            "start": start,
            "end": start + 0.8,
            "speaker": 0,
            "text": f"Topic {index} reveals a distinct result.",
            "words": [],
        }
        for index, start in enumerate(starts)
    ]
    units = build_sentence_units(segments)
    labeled = [replace(unit, topic_id=index) for index, unit in enumerate(units)]

    anchors = generate_anchors(labeled, limit=20)

    assert len(anchors) == 20


def test_candidate_audit_distinguishes_deduped_from_shortlisted():
    units = build_sentence_units(_segments([
        "The first room hides a bunker.",
        "A secret elevator opens below.",
        "The underground pool is worth millions.",
        "The second room grows food indoors.",
        "Hydroponics feeds seventy five people.",
        "That keeps the entire shelter alive.",
    ], seconds=5.0))

    result = synthesize(units, anchor_limit=8, shortlist_limit=1)

    assert len(result["candidates"]) == 1
    audit = result["candidate_audit"]
    assert audit["deduped_proposals"] > audit["shortlisted_proposals"]
    assert any("SHORTLIST_LIMIT" in item["rejection_reasons"] for item in audit["rejection_reasons"])


def test_candidate_audit_separates_deterministic_and_llm_proposals():
    units = build_sentence_units(_segments([
        "Why is this bunker hidden?", "Because it is underground.",
        "The secret elevator opens below.", "Whoa, there is a pool underground.",
    ], seconds=5.0))

    def proposer(neighborhood, _anchor):
        return [BoundaryProposal(
            neighborhood[0].sentence_id,
            neighborhood[1].sentence_id,
            "A hidden bunker is underground.",
            neighborhood[0].sentence_id,
            neighborhood[1].sentence_id,
            "question_answer",
            "question",
            "answer",
        )]

    result = synthesize(
        units,
        boundary_proposer=proposer,
        anchor_limit=2,
        boundary_limit=1,
        shortlist_limit=20,
    )

    audit = result["candidate_audit"]
    assert audit["deterministic_proposals"] > 0
    assert audit["llm_proposals"] > 0
    assert audit["raw_proposals"] == (
        audit["deterministic_proposals"] + audit["llm_proposals"]
    )
    assert audit["story_unit_proposals"] == audit["deterministic_proposals"]


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


def test_minute_bucket_replaces_weak_story_for_new_topic():
    def candidate(candidate_id: str, start: float, quality: float, boundary: float) -> dict:
        return {
            "candidate_id": candidate_id,
            "start": start,
            "end": start + 10.0,
            "sentence_ids": [f"{candidate_id}-1", f"{candidate_id}-2"],
            "central_premise": f"A story about {candidate_id}.",
            "payoff_sentence": f"The {candidate_id} result is surprising.",
            "topic_key": [candidate_id],
            "story_variant": f"det-{candidate_id}",
            "syntactic_complete": True,
            "editorial_signal": True,
            "hook_strength": quality,
            "duration_fit": quality,
            "information_density": quality,
            "curve_score": quality,
            "topic_coherence": quality * 100.0,
            "start_topic_boundary": boundary,
        }

    result = cheap_filter_and_dedupe([
        candidate("ordinary-1", 0.0, 1.0, 0.0),
        candidate("ordinary-2", 10.0, 0.9, 0.0),
        candidate("ordinary-3", 20.0, 0.8, 0.0),
        candidate("ordinary-4", 30.0, 0.7, 0.0),
        candidate("new-topic", 40.0, 0.1, 0.8),
    ], limit=5)

    assert "new-topic" in {item["candidate_id"] for item in result}


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


def test_common_outcome_phrases_have_cheap_payoff_evidence():
    units = build_sentence_units(_segments([
        "The pilot is too close to the runway.",
        "I won the final round!",
    ], seconds=5.0))

    candidate = _story_candidate(units, units[0], "outcome")

    assert candidate is not None
    assert candidate["payoff_candidate"] is True


def test_domain_agnostic_outcome_verbs_have_cheap_payoff_evidence():
    units = build_sentence_units(_segments([
        "Can I finish the final round?",
        "I won the final round!",
    ], seconds=5.0))

    candidate = _story_candidate(units, units[0], "generic-outcome")

    assert candidate is not None
    assert candidate["payoff_candidate"] is True


def test_editorial_signal_accepts_generic_outcome_language():
    units = build_sentence_units(_segments([
        "The team won the final match.",
        "The result surprised everyone.",
    ], seconds=5.0))

    candidate = _story_candidate(units, units[0], "generic-signal")

    assert candidate is not None
    assert candidate["editorial_signal"] is True


def test_explicit_outcome_detection_accepts_common_completion_modifiers():
    assert _has_explicit_outcome(
        "We still got them on billboards all across the country."
    ) is True
    assert _has_explicit_outcome(
        "And now it's official."
    ) is True


def test_explicit_payoff_can_close_a_contextual_opening():
    units = build_sentence_units(_segments([
        "Can I compete in the final round?",
        "I finally won the final round and led the team out.",
    ], seconds=5.0))

    candidate = _story_candidate(units, units[0], "contextual-outcome")

    assert candidate is not None
    assert candidate["payoff_candidate"] is True
    assert candidate["context_dependency"] is False


def test_plain_story_has_no_cheap_payoff_evidence():
    units = build_sentence_units(_segments([
        "This bunker is underground.",
        "The room has a steel door.",
    ], seconds=5.0))
    candidate = _story_candidate(units, units[0], "negative")
    assert candidate is not None
    assert candidate["payoff_candidate"] is False


def test_negated_outcome_word_is_not_payoff_evidence():
    units = build_sentence_units(_segments([
        "I won't let the team down.",
    ], seconds=8.5))

    assert _contains_payoff(units[0]) is False


def test_premise_fact_is_not_mistaken_for_payoff():
    units = build_sentence_units(_segments([
        "If you're wondering why this bunker is worth $3 million, it's because of dangerous weapons.",
        "That is a backpack flamethrower.",
        "Oh my gosh, this is crazy.",
    ], seconds=5.0))
    candidate = _story_candidate(units, units[0], "premise")
    assert candidate is not None
    assert candidate["payoff_sentence_id"] == units[-1].sentence_id
