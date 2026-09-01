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


def test_recommendation_score_penalizes_weak_story_over_platform_lead():
    weak = {"score": 88.0, "hook": 0.0, "story_shape": 24.0, "ending_completeness": 20.0}
    strong = {"score": 68.0, "hook": 75.0, "story_shape": 84.0, "ending_completeness": 92.0}

    weak_score = short_quality.recommendation_score(40.0, weak)
    strong_score = short_quality.recommendation_score(35.0, strong)

    assert strong_score > weak_score


def test_recommendation_score_is_distinct_from_platform_score():
    quality = {"score": 80.0, "hook": 70.0, "story_shape": 86.0, "ending_completeness": 90.0}

    assert short_quality.recommendation_score(40.0, quality) != 40.0


def test_fragment_endings_are_penalized_but_cliffhangers_remain_valid():
    for fragment in ("These.", "So.", "Here."):
        assert short_quality.assess(fragment, [], 1.0)["complete_ending"] is False
    assert short_quality.assess("Wait.", [], 1.0)["complete_ending"] is True
