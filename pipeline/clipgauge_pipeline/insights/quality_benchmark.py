"""Legally shippable clip-selection benchmark metrics.

Fixtures contain timestamps and labels only. Media and transcripts stay outside
the repository.
"""

from __future__ import annotations

import math
from typing import Any, Iterable


def _interval(item: dict[str, Any]) -> tuple[float, float]:
    return float(item["start"]), float(item["end"])


def interval_iou(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_start, left_end = _interval(left)
    right_start, right_end = _interval(right)
    intersection = max(0.0, min(left_end, right_end) - max(left_start, right_start))
    union = max(left_end, right_end) - min(left_start, right_start)
    return intersection / union if union > 0 else 0.0


def _covered(item: dict[str, Any], annotations: Iterable[dict[str, Any]], threshold: float = 0.3) -> bool:
    return any(interval_iou(item, annotation) >= threshold for annotation in annotations)


def _covered_annotation_indexes(
    items: Iterable[dict[str, Any]],
    annotations: list[dict[str, Any]],
    threshold: float = 0.3,
) -> set[int]:
    return {
        annotation_index
        for annotation_index, annotation in enumerate(annotations)
        if any(interval_iou(item, annotation) >= threshold for item in items)
    }


def recall_at_k(candidates: list[dict[str, Any]], annotations: list[dict[str, Any]], k: int) -> float:
    if not annotations:
        return 0.0
    covered = _covered_annotation_indexes(candidates[: max(0, k)], annotations)
    return len(covered) / len(annotations)


def recommendation_precision_at_k(recommendations: list[dict[str, Any]], annotations: list[dict[str, Any]], k: int) -> float:
    selected = recommendations[: max(0, k)]
    if not selected:
        return 0.0
    return sum(_covered(item, annotations) for item in selected) / len(selected)


def ndcg_at_k(recommendations: list[dict[str, Any]], annotations: list[dict[str, Any]], k: int) -> float:
    selected = recommendations[: max(0, k)]
    if not selected or not annotations:
        return 0.0
    gains = [
        max(
            (interval_iou(item, annotation) * max(0.0, float(annotation.get("relevance", 1.0))) for annotation in annotations),
            default=0.0,
        )
        for item in selected
    ]
    dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal = sorted(
        [max(0.0, float(annotation.get("relevance", 1.0))) for annotation in annotations],
        reverse=True,
    )[:k]
    ideal_dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(ideal))
    return dcg / ideal_dcg if ideal_dcg else 0.0


def boundary_error(recommendations: list[dict[str, Any]], annotations: list[dict[str, Any]]) -> dict[str, float]:
    overlaps = [
        (interval_iou(recommendation, annotation), recommendation_index, annotation_index)
        for recommendation_index, recommendation in enumerate(recommendations)
        for annotation_index, annotation in enumerate(annotations)
        if interval_iou(recommendation, annotation) >= 0.3
    ]
    matched = []
    used_recommendations: set[int] = set()
    used_annotations: set[int] = set()
    for _, recommendation_index, annotation_index in sorted(overlaps, key=lambda item: (-item[0], item[1], item[2])):
        if recommendation_index in used_recommendations or annotation_index in used_annotations:
            continue
        used_recommendations.add(recommendation_index)
        used_annotations.add(annotation_index)
        matched.append((recommendations[recommendation_index], annotations[annotation_index]))
    if not matched:
        return {"start_seconds": 0.0, "end_seconds": 0.0}
    return {
        "start_seconds": sum(abs(float(item["start"]) - float(annotation["start"])) for item, annotation in matched) / len(matched),
        "end_seconds": sum(abs(float(item["end"]) - float(annotation["end"])) for item, annotation in matched) / len(matched),
    }


def duplicate_rate(recommendations: list[dict[str, Any]], threshold: float = 0.7) -> float:
    if len(recommendations) < 2:
        return 0.0
    duplicates = sum(
        interval_iou(left, right) >= threshold
        for index, left in enumerate(recommendations)
        for right in recommendations[index + 1 :]
    )
    pairs = len(recommendations) * (len(recommendations) - 1) / 2
    return duplicates / pairs


def temporal_diversity(recommendations: list[dict[str, Any]], duration: float) -> float:
    if not recommendations or duration <= 0:
        return 0.0
    buckets = {min(9, max(0, int((float(item["start"]) / duration) * 10))) for item in recommendations}
    return len(buckets) / 10.0


def _point_coverage(recommendations: list[dict[str, Any]], annotations: list[dict[str, Any]], field: str) -> float:
    points = [float(annotation[field]) for annotation in annotations if field in annotation]
    if not points:
        return 0.0
    return sum(any(float(item["start"]) <= point <= float(item["end"]) for item in recommendations) for point in points) / len(points)


def story_completeness(recommendations: list[dict[str, Any]], annotations: list[dict[str, Any]]) -> float:
    if not annotations:
        return 0.0
    return sum(max((interval_iou(item, annotation) for item in recommendations), default=0.0) for annotation in annotations) / len(annotations)


def false_bait_rate(recommendations: list[dict[str, Any]]) -> float:
    total_reported = 0
    total_rejected = 0
    for item in recommendations:
        record = item.get("bait_verification") if isinstance(item.get("bait_verification"), dict) else None
        if record is None:
            record = next(
                (
                    adjustment for adjustment in item.get("adjustments", [])
                    if isinstance(adjustment, dict) and "model_reported_bait" in adjustment
                ),
                None,
            )
        if isinstance(record, dict) and isinstance(record.get("model_reported_bait"), list):
            reported = record["model_reported_bait"]
            verified = record.get("verified_bait") if isinstance(record.get("verified_bait"), list) else []
            rejected = record.get("rejected_bait") if isinstance(record.get("rejected_bait"), list) else []
            total_reported += len(reported)
            total_rejected += len(rejected) if rejected else max(0, len(reported) - len(verified))
        elif isinstance(item.get("bait_reported"), list):
            reported = item["bait_reported"]
            verified = item.get("bait_verified")
            total_reported += len(reported)
            if isinstance(verified, list):
                total_rejected += max(0, len(reported) - len(verified))
            else:
                total_rejected += 0 if bool(verified) else len(reported)
        elif item.get("bait_reported"):
            total_reported += 1
            total_rejected += int(not bool(item.get("bait_verified")))
    return total_rejected / total_reported if total_reported else 0.0


def benchmark_metrics(
    candidates: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
    *,
    duration: float,
    k: int = 5,
) -> dict[str, Any]:
    boundaries = boundary_error(recommendations, annotations)
    return {
        "candidate_recall_at_k": recall_at_k(candidates, annotations, k),
        "recommendation_precision_at_k": recommendation_precision_at_k(recommendations, annotations, k),
        "ndcg_at_k": ndcg_at_k(recommendations, annotations, k),
        "boundary_start_error_seconds": boundaries["start_seconds"],
        "boundary_end_error_seconds": boundaries["end_seconds"],
        "duplicate_recommendation_rate": duplicate_rate(recommendations),
        "temporal_diversity": temporal_diversity(recommendations, duration),
        "hook_coverage": _point_coverage(recommendations, annotations, "hook_start"),
        "payoff_coverage": _point_coverage(recommendations, annotations, "payoff_start"),
        "story_completeness": story_completeness(recommendations, annotations),
        "false_bait_rate": false_bait_rate(recommendations),
        "annotation_count": len(annotations),
    }
