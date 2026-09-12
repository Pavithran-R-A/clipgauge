"""Build legally safe aggregate metrics for an owner benchmark replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .quality_benchmark import benchmark_metrics, false_bait_counts


def _data(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("data")
    return value if isinstance(value, dict) else payload


def build_report(
    score_payload: dict[str, Any],
    candidate_payload: dict[str, Any],
    benchmark_payload: dict[str, Any],
) -> dict[str, Any]:
    score = _data(score_payload)
    candidates_data = _data(candidate_payload)
    annotations = benchmark_payload.get("annotations")
    if not isinstance(annotations, list):
        raise ValueError("owner benchmark annotations are malformed")
    candidates = candidates_data.get("candidates")
    clips = score.get("clips")
    if not isinstance(candidates, list) or not isinstance(clips, list):
        raise ValueError("score or candidate payload is malformed")
    metrics = benchmark_metrics(
        candidates,
        clips,
        annotations,
        duration=float(benchmark_payload["duration_seconds"]),
    )
    reported, false_positives = false_bait_counts(clips)
    return {
        "provider": score.get("provider_kind"),
        "model": score.get("model"),
        "candidate_count": len(candidates),
        "scored_count": score.get("scored_count"),
        "recommendation_count": len(clips),
        "other_moment_count": len(score.get("borderline_candidates") or []),
        "schema_success_rate": (float(score.get("scored_count", 0)) / len(candidates)) if candidates else 0.0,
        "provider_failure_count": len(score.get("scoring_failures") or []),
        "false_bait_reported_count": reported,
        "false_bait_false_positives": false_positives,
        "final_boundaries": [
            {"start": clip.get("start"), "end": clip.get("end")}
            for clip in clips
            if isinstance(clip, dict) and "start" in clip and "end" in clip
        ],
        "metrics": metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score", required=True, type=Path)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--benchmark", required=True, type=Path)
    args = parser.parse_args()
    report = build_report(
        json.loads(args.score.read_text(encoding="utf-8")),
        json.loads(args.candidates.read_text(encoding="utf-8")),
        json.loads(args.benchmark.read_text(encoding="utf-8")),
    )
    print(json.dumps(report, separators=(",", ":")))
    return 0
