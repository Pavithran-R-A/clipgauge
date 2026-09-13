import pytest

from clipgauge_pipeline.candidates.story_units import build_sentence_units, synthesize
from clipgauge_pipeline.insights.quality_benchmark import benchmark_metrics, recall_at_k


def test_quality_benchmark_metrics_are_deterministic_and_explainable():
    annotations = [
        {"start": 10, "end": 20},
        {"start": 70, "end": 80},
    ]
    candidates = [
        {"start": 9, "end": 21},
        {"start": 69, "end": 81},
        {"start": 40, "end": 45},
    ]
    recommendations = candidates[:2]

    result = benchmark_metrics(candidates, recommendations, annotations, duration=100, k=2)

    assert result["candidate_recall_at_k"] == 1.0
    assert result["recommendation_precision_at_k"] == 1.0
    assert result["ndcg_at_k"] == pytest.approx(5 / 6)
    assert result["boundary_start_error_seconds"] == 1.0
    assert result["boundary_end_error_seconds"] == 1.0
    assert result["temporal_diversity"] == 0.2


def test_candidate_recall_counts_each_annotation_once():
    annotations = [{"start": 10, "end": 20}]
    candidates = [
        {"start": 10, "end": 20},
        {"start": 10, "end": 20},
    ]

    result = benchmark_metrics(candidates, candidates, annotations, duration=100, k=2)

    assert result["candidate_recall_at_k"] == 1.0


def test_ndcg_ignores_subthreshold_interval_matches():
    annotations = [{"start": 10, "end": 20}]
    recommendations = [{"start": 10, "end": 12}]

    result = benchmark_metrics(recommendations, recommendations, annotations, duration=100, k=1)

    assert result["ndcg_at_k"] == 0.0


def test_boundary_error_ignores_unmatched_recommendations():
    annotations = [{"start": 10, "end": 20}]
    recommendations = [
        {"start": 10, "end": 20},
        {"start": 80, "end": 90},
    ]

    result = benchmark_metrics(recommendations, recommendations, annotations, duration=100, k=2)

    assert result["boundary_start_error_seconds"] == 0.0
    assert result["boundary_end_error_seconds"] == 0.0


def test_false_bait_rate_reads_scoring_adjustment_records():
    recommendations = [{
        "start": 10,
        "end": 20,
        "adjustments": [{
            "rule": "bait_verification",
            "model_reported_bait": ["subscribe", "we land here"],
            "verified_bait": ["subscribe"],
            "rejected_bait": [{"phrase": "we land here", "reason": "not_viewer_directed"}],
        }]
    }]

    assert benchmark_metrics(recommendations, recommendations, [], duration=100)["false_bait_rate"] == 0.5


def test_false_bait_rate_ignores_rejected_non_model_reports():
    recommendations = [{
        "start": 10,
        "end": 20,
        "bait_verification": {
            "model_reported_bait": [],
            "verified_bait": [],
            "rejected_bait": [{"phrase": "normal dialogue", "reason": "not_viewer_directed"}],
        },
    }]

    metrics = benchmark_metrics(recommendations, recommendations, [], duration=100)

    assert metrics["false_bait_rate"] == 0.0
    assert metrics["false_bait_reported_count"] == 0
    assert metrics["false_bait_false_positives"] == 0


def test_false_bait_rate_counts_legacy_bait_lists_by_phrase():
    recommendations = [{
        "start": 10,
        "end": 20,
        "bait_reported": ["subscribe", "we land here", "like this video"],
        "bait_verified": ["subscribe", "like this video"],
    }]

    assert benchmark_metrics(recommendations, recommendations, [], duration=100)["false_bait_rate"] == pytest.approx(1 / 3)


def test_candidate_generation_fixture_recovers_multiple_story_units():
    texts = [
        "Why is this room hidden?",
        "Because it sits under an ordinary house.",
        "The secret elevator opens below.",
        "The underground pool is worth millions.",
        "Next, hydroponics grows infinite food.",
        "That keeps seventy five people alive.",
    ]
    segments = [
        {"start": index * 5.0, "end": (index + 1) * 5.0 - 0.1, "speaker": 0, "text": text, "words": []}
        for index, text in enumerate(texts)
    ]
    units = build_sentence_units(segments)
    synthesis = synthesize(units, anchor_limit=8, shortlist_limit=24)
    annotations = [{"start": 0.0, "end": 14.9}, {"start": 15.0, "end": 29.9}]

    metrics = benchmark_metrics(
        synthesis["candidates"], synthesis["candidates"], annotations, duration=30.0, k=5
    )

    assert metrics["candidate_recall_at_k"] == 1.0
    assert metrics["recommendation_precision_at_k"] == 1.0
    assert metrics["false_bait_rate"] == 0.0


def test_dense_fixture_preserves_recall_across_repeated_story_terms():
    segments = []
    for index in range(8):
        base = index * 40.0
        texts = [
            f"Why did the challenge in chapter {index} begin?",
            f"Because the team entered challenge {index}.",
            f"The result changed the record for chapter {index}.",
            f"Finally, chapter {index} succeeded.",
        ]
        segments.extend(
            {
                "start": base + offset * 7.0,
                "end": base + offset * 7.0 + 6.8,
                "speaker": 0,
                "text": text,
                "words": [],
            }
            for offset, text in enumerate(texts)
        )

    synthesis = synthesize(build_sentence_units(segments), anchor_limit=20, shortlist_limit=24)
    annotations = [
        {"start": index * 40.0, "end": index * 40.0 + 27.8}
        for index in range(8)
    ]

    assert recall_at_k(synthesis["candidates"], annotations, 24) == 1.0


def test_frozen_contract_uses_strong_pool_and_top_five_story_denominators():
    annotations = [
        {"id": "strong-a", "start": 0, "end": 10, "relevance": 3, "hook_start": 1, "payoff_start": 9},
        {"id": "strong-b", "start": 20, "end": 30, "relevance": 3, "hook_start": 21, "payoff_start": 29},
        {"id": "borderline", "start": 40, "end": 50, "relevance": 2, "hook_start": 41, "payoff_start": 49},
    ]
    candidates = [
        {"start": 0, "end": 10},
        {"start": 20, "end": 30},
    ]

    result = benchmark_metrics(candidates, candidates, annotations, duration=60, k=5)

    assert result["candidate_pool_recall"] == pytest.approx(2 / 2)
    assert result["recall_at_k"] == pytest.approx(2 / 3)
    assert result["strong_story_count_at_k"] == 2
    assert result["hook_coverage"] == pytest.approx(2 / 2)
    assert result["payoff_coverage"] == pytest.approx(2 / 2)


def test_ndcg_does_not_credit_duplicate_predictions_twice():
    annotations = [
        {"start": 0, "end": 10, "relevance": 3},
        {"start": 20, "end": 30, "relevance": 3},
    ]
    recommendations = [
        {"start": 0, "end": 10},
        {"start": 0, "end": 10},
    ]

    result = benchmark_metrics(recommendations, recommendations, annotations, duration=60, k=2)

    assert result["ndcg_at_k"] == pytest.approx(1 / (1 + 1 / 1.5849625007))


def test_boundary_contract_reports_median_strong_errors():
    annotations = [
        {"start": 0, "end": 10, "relevance": 3},
        {"start": 20, "end": 30, "relevance": 3},
        {"start": 40, "end": 50, "relevance": 2},
    ]
    recommendations = [
        {"start": 1, "end": 12},
        {"start": 22, "end": 34},
        {"start": 40, "end": 50},
    ]

    result = benchmark_metrics(recommendations, recommendations, annotations, duration=60, k=5)

    assert result["boundary_start_error_seconds"] == 1.5
    assert result["boundary_end_error_seconds"] == 3.0


def test_boundary_contract_uses_filtered_strong_annotation_indexes():
    annotations = [
        {"id": "borderline", "start": 0, "end": 10, "relevance": 2},
        {"id": "strong", "start": 20, "end": 30, "relevance": 3},
    ]
    recommendations = [{"start": 21, "end": 31}]

    result = benchmark_metrics(recommendations, recommendations, annotations, duration=40, k=1)

    assert result["boundary_start_error_seconds"] == 1.0
    assert result["boundary_end_error_seconds"] == 1.0


def test_point_coverage_uses_half_open_intervals():
    annotations = [{"start": 0, "end": 10, "relevance": 3, "hook_start": 10}]
    recommendations = [{"start": 0, "end": 10}]

    result = benchmark_metrics(recommendations, recommendations, annotations, duration=20, k=1)

    assert result["hook_coverage"] == 0.0


def test_temporal_diversity_counts_distinct_strong_story_regions():
    annotations = [
        {"id": "a", "start": 0, "end": 10, "relevance": 3},
        {"id": "b", "start": 20, "end": 30, "relevance": 3},
        {"id": "c", "start": 40, "end": 50, "relevance": 3},
        {"id": "d", "start": 60, "end": 70, "relevance": 3},
    ]
    recommendations = [
        {"start": 0, "end": 10},
        {"start": 20, "end": 30},
        {"start": 40, "end": 50},
        {"start": 0, "end": 10},
        {"start": 0, "end": 10},
    ]

    result = benchmark_metrics(recommendations, recommendations, annotations, duration=80, k=5)

    assert result["temporal_diversity_count"] == 3
    assert result["temporal_diversity"] == pytest.approx(3 / 4)
