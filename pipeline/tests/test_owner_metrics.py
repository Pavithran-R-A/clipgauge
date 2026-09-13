import pytest

from clipgauge_pipeline.insights.owner_metrics import build_report, candidate_set_fingerprint


def test_candidate_set_fingerprint_is_order_independent_and_transcript_free():
    first = {
        "data": {
            "candidates": [
                {"candidate_id": "b", "start": 3.0, "end": 8.0},
                {"candidate_id": "a", "start": 0.0, "end": 4.0},
            ]
        }
    }
    second = {
        "data": {
            "candidates": [
                {"candidate_id": "a", "start": 0.0, "end": 4.0, "transcript": "secret"},
                {"candidate_id": "b", "start": 3.0, "end": 8.0, "transcript": "secret"},
            ]
        }
    }

    assert candidate_set_fingerprint(first) == candidate_set_fingerprint(second)


def test_candidate_set_fingerprint_rejects_missing_identity():
    with pytest.raises(ValueError, match="candidate identity"):
        candidate_set_fingerprint({"data": {"candidates": [{"start": 0.0, "end": 1.0}]}})


def test_owner_metrics_report_is_aggregate_only():
    report = build_report(
        {
            "data": {
                "provider_kind": "clipgauge-local",
                "model": "local-test",
                "scored_count": 1,
                "clips": [
                    {
                        "start": 1.0,
                        "end": 7.0,
                        "bait_verification": {
                            "model_reported_bait": ["look at that"],
                            "verified_bait": [],
                            "rejected_bait": ["not engagement bait"],
                        },
                    }
                ],
                "borderline_candidates": [],
                "scoring_failures": [],
            }
        },
        {"data": {"candidates": [{"start": 0.0, "end": 8.0}]}},
        {
            "duration_seconds": 10.0,
            "annotations": [{"start": 0.0, "end": 8.0, "relevance": 3}],
        },
    )

    assert report["candidate_count"] == 1
    assert report["false_bait_false_positives"] == 1
    assert report["metrics"]["candidate_pool_recall"] == 1.0
    assert "transcript" not in report


def test_owner_metrics_counts_typed_provider_failures():
    report = build_report(
        {
            "data": {
                "provider_kind": "cloud",
                "model": "cloud-test",
                "scored_count": 3,
                "clips": [],
                "borderline_candidates": [],
                "scoring_failures": {
                    "attempted_count": 5,
                    "successful_count": 3,
                    "failed_count": 2,
                    "failure_reason_counts": {"TIMEOUT": 2},
                },
            }
        },
        {"data": {"candidates": [{"start": 0.0, "end": 8.0}] * 4}},
        {
            "duration_seconds": 10.0,
            "annotations": [{"start": 0.0, "end": 8.0, "relevance": 3}],
        },
    )

    assert report["provider_failure_count"] == 2
