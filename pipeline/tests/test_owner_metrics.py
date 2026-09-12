from clipgauge_pipeline.insights.owner_metrics import build_report


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
