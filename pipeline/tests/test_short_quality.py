from clipgauge_pipeline.scoring import short_quality


def test_known_positive_fixture_remains_recommendable():
    quality = short_quality.assess(
        "If you're wondering why this bunker is worth three million dollars, "
        "it's because of this YouTuber's collection of insane and dangerous "
        "weapons. That's a backpack flamethrower. This guy's like a real-life "
        "Tony Stark. I mean, look at this wrist-mounted rocket launcher. Fires "
        "knives and has a taser in it. And a machine gun with a chainsaw. Oh my "
        "gosh, this is crazy. Don't break into this bunker.",
        [],
        31.145,
    )
    assert quality["eligible_to_recommend"] is True
    assert quality["quality_tier"] in {"GOOD", "STRONG"}


def test_known_negative_fixture_remains_rejected():
    quality = short_quality.assess(
        "Whoa, this is huge. This is way bigger than I thought it would be. "
        "This is so fancy. It does not feel like you're in a bunker. No, I feel "
        "like I'm in a normal house. Surely, if you own a fifty million dollar "
        "bunker, you wouldn't care if I took a Diet Coke. Wait, how old is this? "
        "This expired two years ago. It tasted so bad. Hey, Google if I'm going "
        "to die. Yeah, it's because we're three stories underground. Wait, is "
        "this the video where we trapped Hugo and Rain in a bunker for 100 days?",
        [],
        43.413,
    )
    assert quality["eligible_to_recommend"] is False


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


def test_real_unfinished_endings_are_ineligible():
    for fragment in ("Can I hold your", "this one's bigger than"):
        quality = short_quality.assess(fragment, [], 3.0)
        assert quality["complete_ending"] is False
        assert quality["eligible_to_recommend"] is False
        assert "INCOMPLETE_ENDING" in quality["rejection_reasons"]


def test_hook_metrics_keep_structured_and_deterministic_signals_distinct():
    quality = short_quality.assess(
        "The answer is hidden in the final test.",
        [],
        4.0,
        llm={"hook_strength": 0, "hook_reason": "none"},
    )

    assert quality["rubric_hook_0_10"] is None
    assert quality["structured_hook_0_10"] == 0.0
    assert quality["deterministic_hook_0_100"] > 0.0
    assert quality["effective_hook_0_100"] > 0.0
    assert quality["hook_disagreement"] is True


def test_hook_fields_remain_distinct_and_explicit():
    quality = short_quality.assess(
        "The answer is hidden in the final test.",
        [],
        4.0,
        llm={"hook": 8, "hook_strength": 2},
    )

    assert quality["rubric_hook_0_10"] == 8.0
    assert quality["structured_hook_0_10"] == 2.0
    assert quality["deterministic_hook_0_100"] == 38.0
    assert quality["effective_hook_0_100"] != 20.0


def test_boundary_completeness_does_not_depend_on_fragment_tokens(monkeypatch):
    monkeypatch.setattr(short_quality, "_FRAGMENT_FUNCTION_WORDS", set())

    for fragment in ("Can I hold your", "this one's bigger than"):
        quality = short_quality.assess(
            fragment,
            [],
            3.0,
            ending_evidence={
                "punctuated": False,
                "segment_boundary": False,
                "silence": False,
                "speaker_turn_boundary": False,
                "semantic_complete": False,
            },
        )
        assert quality["complete_ending"] is False
        assert "INCOMPLETE_ENDING" in quality["rejection_reasons"]


def test_contradictory_story_shape_is_inconsistent_and_penalized():
    quality = short_quality.assess(
        "The argument ended without anyone reacting.",
        [],
        5.0,
        llm={"story_shape": "conflict_reaction", "payoff_strength": 0},
    )

    assert quality["payoff"] == 0.0
    assert quality["story_consistent"] is False
    assert quality["story_consistency_reason"]
    assert short_quality.recommendation_score(33.0, quality) < 10.0


def test_clear_complete_payoff_beats_platform_only_candidate():
    weak = short_quality.assess("The discussion continued without an answer.", [], 5.0, llm={"hook_strength": 0, "payoff_strength": 0})
    strong = short_quality.assess("Why did it fail? Because we fixed it!", [{"type": "reaction"}], 5.0, llm={"hook_strength": 8, "payoff_strength": 8})

    assert short_quality.recommendation_score(33.0, weak) < short_quality.recommendation_score(27.0, strong)


def test_rank_and_selection_drop_ineligible_candidates():
    entries = [
        {"start": 0, "end": 10, "recommendation_score": 90, "eligible_to_recommend": False, "rejection_reasons": ["INCOMPLETE_ENDING"]},
        {"start": 20, "end": 30, "recommendation_score": 60, "eligible_to_recommend": True, "rejection_reasons": []},
    ]

    selected = short_quality.select_eligible_finalists(entries, 6)

    assert len(selected) == 1
    assert selected[0]["start"] == 20


def test_generic_reaction_without_context_is_not_strong():
    quality = short_quality.assess(
        "Whoa, this is huge. People walk through the bunker and look around.",
        [],
        8.0,
    )

    assert quality["quality_tier"] != "STRONG"
    assert "WEAK_COLD_HOOK" in quality["quality_flags"]


def test_complete_question_can_lack_semantic_closure():
    quality = short_quality.assess(
        "The bunker has rooms and a refrigerator. Did they enter the 100-day challenge?",
        [],
        8.0,
    )

    assert quality["syntactic_complete"] is True
    assert quality["open_loop_at_end"] is True
    assert quality["semantic_closure_0_100"] < 60.0
    assert "WEAK_SEMANTIC_CLOSURE" in quality["quality_flags"]


def test_late_topic_is_not_a_relevant_payoff():
    quality = short_quality.assess(
        "The bunker has rooms and a refrigerator. The 100-day challenge asks contestants to win money?",
        [],
        10.0,
        llm={
            "hook": 2,
            "hook_strength": 2,
            "payoff_strength": 8,
            "payoff_location": "late",
            "ending_completeness": 8,
            "story_shape": "hook_setup_payoff",
        },
    )

    assert quality["late_new_topic"] is True
    assert quality["payoff_relevance_to_premise"] < 50.0
    assert "PAYOFF_NOT_RELEVANT" in quality["quality_flags"]


def test_structurally_valid_is_not_strong_when_topic_drifts():
    quality = short_quality.assess(
        "The bunker is underground and comfortable. The refrigerator is full. A separate challenge asks for 100 days.",
        [],
        10.0,
        llm={
            "hook": 7,
            "hook_strength": 7,
            "payoff_strength": 7,
            "ending_completeness": 8,
            "story_shape": "hook_setup_payoff",
        },
    )

    assert quality["structurally_valid"] is True
    assert quality["quality_tier"] == "STRUCTURALLY_VALID"
    assert quality["strong_recommendation"] is False
    assert quality["topic_shift_count"] >= 1


def test_repeated_premise_anchor_does_not_count_as_topic_drift():
    quality = short_quality.assess(
        "The bunker is underground. The door is massive. The bunker protects families.",
        [],
        8.0,
    )

    assert quality["topic_shift_count"] == 0
    assert quality["late_new_topic"] is False


def test_coherent_story_with_narrative_beats_can_be_strong():
    quality = short_quality.assess(
        "Why did the test fail? Because the battery exploded, and everyone gasped!",
        [{"type": "gasp"}],
        8.0,
        llm={
            "hook": 9,
            "hook_strength": 9,
            "standalone_comprehension": 9,
            "setup_strength": 8,
            "escalation_strength": 8,
            "payoff_strength": 9,
            "ending_completeness": 9,
            "story_shape": "hook_setup_payoff",
            "reaction_strength": 9,
        },
    )

    assert quality["quality_tier"] == "STRONG"
    assert quality["quality_flags"] == []
