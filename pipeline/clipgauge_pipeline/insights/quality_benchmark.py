"""Legally shippable clip-selection benchmark metrics.

Fixtures contain timestamps and labels only. Media and transcripts stay outside
the repository.
"""

from __future__ import annotations

import math
from statistics import median
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


def _strong_annotations(annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use explicit human relevance when available.

    Older fixtures omit relevance and remain backward compatible.
    Frozen owner annotations always provide relevance.
    """
    if not any("relevance" in annotation for annotation in annotations):
        return list(annotations)
    return [annotation for annotation in annotations if float(annotation.get("relevance", 0.0)) == 3.0]


def _ranked_matches(
    recommendations: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
    threshold: float = 0.3,
) -> list[tuple[int, int, float]]:
    """Match recommendations once, in ranked order.

    Each recommendation receives its best still-unmatched annotation.
    """
    matches: list[tuple[int, int, float]] = []
    used_annotations: set[int] = set()
    for recommendation_index, recommendation in enumerate(recommendations):
        options = [
            (interval_iou(recommendation, annotation), annotation_index)
            for annotation_index, annotation in enumerate(annotations)
            if annotation_index not in used_annotations
            and interval_iou(recommendation, annotation) >= threshold
        ]
        if not options:
            continue
        overlap, annotation_index = max(options, key=lambda item: (item[0], -item[1]))
        used_annotations.add(annotation_index)
        matches.append((recommendation_index, annotation_index, overlap))
    return matches


def recall_at_k(candidates: list[dict[str, Any]], annotations: list[dict[str, Any]], k: int) -> float:
    if not annotations:
        return 0.0
    covered = _covered_annotation_indexes(candidates[: max(0, k)], annotations)
    return len(covered) / len(annotations)


def candidate_pool_recall(candidates: list[dict[str, Any]], annotations: list[dict[str, Any]]) -> float:
    """Return full-pool recall against human-Strong annotations."""
    strong = _strong_annotations(annotations)
    if not strong:
        return 0.0
    return len(_covered_annotation_indexes(candidates, strong)) / len(strong)


def recommendation_precision_at_k(recommendations: list[dict[str, Any]], annotations: list[dict[str, Any]], k: int) -> float:
    selected = recommendations[: max(0, k)]
    if not selected:
        return 0.0
    return sum(_covered(item, annotations) for item in selected) / len(selected)


def ndcg_at_k(recommendations: list[dict[str, Any]], annotations: list[dict[str, Any]], k: int) -> float:
    selected = recommendations[: max(0, k)]
    if not selected or not annotations:
        return 0.0
    selected_matches = {
        recommendation_index: (annotation_index, overlap)
        for recommendation_index, annotation_index, overlap in _ranked_matches(selected, annotations)
    }
    gains = [
        (
            selected_matches[index][1]
            * max(0.0, float(annotations[selected_matches[index][0]].get("relevance", 1.0)))
            if index in selected_matches
            else 0.0
        )
        for index in range(len(selected))
    ]
    dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal = sorted(
        [max(0.0, float(annotation.get("relevance", 1.0))) for annotation in annotations],
        reverse=True,
    )[:k]
    ideal_dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(ideal))
    return dcg / ideal_dcg if ideal_dcg else 0.0


def boundary_error(
    recommendations: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
    *,
    strong_only: bool | None = None,
) -> dict[str, float]:
    if strong_only is None:
        strong_only = any("relevance" in annotation for annotation in annotations)
    matched_annotations = _strong_annotations(annotations) if strong_only else annotations
    overlaps = [
        (interval_iou(recommendation, annotation), recommendation_index, annotation_index)
        for recommendation_index, recommendation in enumerate(recommendations)
        for annotation_index, annotation in enumerate(matched_annotations)
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
        matched.append((recommendations[recommendation_index], matched_annotations[annotation_index]))
    if not matched:
        return {"start_seconds": 0.0, "end_seconds": 0.0}
    return {
        "start_seconds": float(median(abs(float(item["start"]) - float(annotation["start"])) for item, annotation in matched)),
        "end_seconds": float(median(abs(float(item["end"]) - float(annotation["end"])) for item, annotation in matched)),
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
    points = [float(annotation[field]) for annotation in _strong_annotations(annotations) if field in annotation]
    if not points:
        return 0.0
    return sum(any(float(item["start"]) <= point < float(item["end"]) for item in recommendations) for point in points) / len(points)


def story_completeness(recommendations: list[dict[str, Any]], annotations: list[dict[str, Any]]) -> float:
    if not annotations:
        return 0.0
    return sum(max((interval_iou(item, annotation) for item in recommendations), default=0.0) for annotation in annotations) / len(annotations)


def strong_story_count_at_k(
    recommendations: list[dict[str, Any]], annotations: list[dict[str, Any]], k: int
) -> int:
    strong = _strong_annotations(annotations)
    return len(_ranked_matches(recommendations[: max(0, k)], strong))


def _temporal_story_diversity(
    recommendations: list[dict[str, Any]], annotations: list[dict[str, Any]], k: int
) -> tuple[int, float]:
    strong = _strong_annotations(annotations)
    if not strong:
        return 0, 0.0
    count = len(_ranked_matches(recommendations[: max(0, k)], strong))
    denominator = min(4, len(strong))
    return count, count / denominator if denominator else 0.0


def false_bait_rate(recommendations: list[dict[str, Any]]) -> float:
    total_reported, total_rejected = false_bait_counts(recommendations)
    return total_rejected / total_reported if total_reported else 0.0


def false_bait_counts(recommendations: list[dict[str, Any]]) -> tuple[int, int]:
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
    return total_reported, total_rejected


def benchmark_metrics(
    candidates: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
    *,
    duration: float,
    k: int = 5,
) -> dict[str, Any]:
    ranked = recommendations[: max(0, k)]
    explicit_relevance = any("relevance" in annotation for annotation in annotations)
    temporal_count, temporal_ratio = _temporal_story_diversity(recommendations, annotations, k)
    if not explicit_relevance:
        temporal_ratio = temporal_diversity(ranked, duration)
    bait_reported, bait_false_positives = false_bait_counts(recommendations)
    boundaries = boundary_error(ranked, annotations, strong_only=explicit_relevance)
    return {
        "candidate_recall_at_k": recall_at_k(candidates, annotations, k),
        "candidate_pool_recall": candidate_pool_recall(candidates, annotations),
        "recall_at_k": recall_at_k(ranked, annotations, k),
        "recommendation_precision_at_k": recommendation_precision_at_k(ranked, annotations, k),
        "ndcg_at_k": ndcg_at_k(recommendations, annotations, k),
        "boundary_start_error_seconds": boundaries["start_seconds"],
        "boundary_end_error_seconds": boundaries["end_seconds"],
        "duplicate_recommendation_rate": duplicate_rate(ranked),
        "temporal_diversity": temporal_ratio,
        "temporal_diversity_count": temporal_count,
        "hook_coverage": _point_coverage(ranked, annotations, "hook_start"),
        "payoff_coverage": _point_coverage(ranked, annotations, "payoff_start"),
        "story_completeness": story_completeness(recommendations, annotations),
        "false_bait_rate": bait_false_positives / bait_reported if bait_reported else 0.0,
        "false_bait_reported_count": bait_reported,
        "false_bait_false_positives": bait_false_positives,
        "strong_story_count_at_k": strong_story_count_at_k(recommendations, annotations, k),
        "annotation_count": len(annotations),
    }
