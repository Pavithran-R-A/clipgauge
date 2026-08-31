from clipgauge_pipeline.scoring import short_quality


def test_short_quality_prefers_hook_setup_reveal_and_reaction():
    strong = short_quality.assess(
        "Why did the quiet engineer hide the result? Because the test failed, then everyone shouted wow!",
        [{"type": "gasp"}, {"type": "laugh"}],
        12.0,
    )
    weak = short_quality.assess(
        "Um like you know this is basically a long introduction without payoff.",
        [],
        12.0,
    )

    assert strong["score"] > weak["score"]
    assert strong["story_shape"] > weak["story_shape"]
    assert strong["payoff"] > weak["payoff"]


def test_smart_boundaries_complete_nearby_sentence():
    words = [
        {"word": "Why", "start": 0.0, "end": 0.2},
        {"word": "did", "start": 0.2, "end": 0.4},
        {"word": "it", "start": 0.4, "end": 0.6},
        {"word": "matter?", "start": 0.6, "end": 0.9},
        {"word": "Because", "start": 1.1, "end": 1.4},
        {"word": "we", "start": 1.4, "end": 1.6},
        {"word": "won!", "start": 1.6, "end": 1.9},
    ]

    start, end = short_quality.smart_boundaries(words, 0.45, 1.5)

    assert (start, end) == (0.0, 1.9)


def test_quality_ranking_is_deterministic():
    items = [
        {"start": 4.0, "end": 8.0, "short_quality": {"score": 80}},
        {"start": 1.0, "end": 5.0, "short_quality": {"score": 80}},
    ]

    ranked = short_quality.rank(items)

    assert [item["start"] for item in ranked] == [1.0, 4.0]


def test_generic_opening_is_not_a_hook():
    generic = short_quality.assess("The team went into the room and started talking.", [], 5.0)
    specific = short_quality.assess("Why did the alarm start after midnight?", [], 5.0)

    assert generic["hook"] < specific["hook"]


def test_structured_t1_fields_are_combined_with_source_evidence():
    quality = short_quality.assess(
        "Why did the test fail? Because the battery exploded, and everyone gasped!",
        [{"type": "gasp"}],
        8.0,
        llm={
            "hook_strength": 9,
            "hook_reason": "question",
            "standalone_comprehension": 8,
            "setup_strength": 7,
            "escalation_strength": 8,
            "payoff_strength": 9,
            "payoff_location": "late",
            "ending_completeness": 8,
            "story_shape": "hook_setup_payoff",
            "information_density": 8,
            "reaction_strength": 8,
        },
    )

    assert quality["llm_structured"] is True
    assert quality["story_shape"] == 92.0
    assert quality["payoff"] > 70.0
