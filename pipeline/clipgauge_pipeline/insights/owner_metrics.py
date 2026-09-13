"""Build legally safe aggregate metrics for an owner benchmark replay."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .quality_benchmark import benchmark_metrics, false_bait_counts


def _data(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("data")
    return value if isinstance(value, dict) else payload


def candidate_set_fingerprint(candidate_payload: dict[str, Any]) -> str:
    """Hash candidate identity without transcript or model judgment fields."""
    candidates = _data(candidate_payload).get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidate identity payload is malformed")
    identity: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or not candidate.get("candidate_id"):
            raise ValueError("candidate identity is missing candidate_id")
        try:
            start = round(float(candidate["start"]), 6)
            end = round(float(candidate["end"]), 6)
        except (KeyError, TypeError, ValueError):
            raise ValueError("candidate identity has invalid interval") from None
        identity.append(
            {
                "candidate_id": str(candidate["candidate_id"]),
                "start": start,
                "end": end,
            }
        )
    canonical = json.dumps(
        sorted(identity, key=lambda item: (item["candidate_id"], item["start"], item["end"])),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


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
    scoring_failures = score.get("scoring_failures")
    if isinstance(scoring_failures, dict):
        provider_failure_count = int(scoring_failures.get("failed_count", 0) or 0)
    elif isinstance(scoring_failures, list):
        provider_failure_count = len(scoring_failures)
    else:
        provider_failure_count = 0
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
        "provider_failure_count": provider_failure_count,
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
    parser.add_argument("--score", type=Path)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--candidate-fingerprint", action="store_true")
    args = parser.parse_args()
    candidate_payload = json.loads(args.candidates.read_text(encoding="utf-8"))
    if args.candidate_fingerprint:
        print(candidate_set_fingerprint(candidate_payload))
        return 0
    if args.score is None or args.benchmark is None:
        parser.error("--score and --benchmark are required without --candidate-fingerprint")
    report = build_report(
        json.loads(args.score.read_text(encoding="utf-8")),
        candidate_payload,
        json.loads(args.benchmark.read_text(encoding="utf-8")),
    )
    print(json.dumps(report, separators=(",", ":")))
    return 0
