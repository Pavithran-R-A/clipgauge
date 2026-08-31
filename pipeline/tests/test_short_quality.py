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
