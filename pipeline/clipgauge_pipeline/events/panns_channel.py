"""PANNs Cnn14_DecisionLevelMax channel: framewise posteriors over the
AudioSet ontology, reduced to the event types the bus cares about.

Laughter-only decision (#2): crying classes are intentionally ABSENT from
the map — no battle-tested adult-crying model exists, and one false positive
would fire on three surfaces at once through the shared bus. PANNs' AudioSet
laughter classes stay in as the fusion partner for the jrgillick specialist.

Processes audio in 30 s chunks with 1 s overlap — Cnn14 on 2 h of audio at
once would need tens of GB of activations.
"""

from __future__ import annotations

import csv
from collections import deque
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import torch

from ..vendor.panns import models as panns_models
from . import post

# AudioSet display_name → bus event type. Laughter classes fuse with the
# jrgillick channel; the rest are solo PANNs detections.
CLASS_MAP: dict[str, str] = {
    "Laughter": "laugh",
    "Giggle": "laugh",
    "Belly laugh": "laugh",
    "Chuckle, chortle": "laugh",
    "Snicker": "laugh",
    "Gasp": "gasp",
    "Screaming": "scream",
    "Shout": "shout",
    "Yell": "shout",
    "Applause": "applause",
    "Cheering": "cheer",
    "Clapping": "applause",
}

CHUNK_SEC = 30.0
OVERLAP_SEC = 1.0

# Zero-shot PANNs posteriors on conversational audio run far below the
# dedicated-SED range the default DCASE thresholds assume: measured on a
# 2 h two-host comedy podcast, laughter tops out ~0.30 and gasps ~0.24
# while true negatives (applause/cheer in a studio) stay under 0.004.
# (enter, stay) per type; confidence is normalized by CONF_SCALE so a
# strong conversational laugh reads ~1.0 downstream.
THRESHOLDS: dict[str, tuple[float, float]] = {
    "laugh": (0.10, 0.05),
    "gasp": (0.10, 0.05),
    "scream": (0.15, 0.08),
    "shout": (0.15, 0.08),
    "applause": (0.15, 0.08),
    "cheer": (0.15, 0.08),
}
CONF_SCALE = 0.30


def load_class_indices() -> dict[int, str]:
    """AudioSet index → bus event type, for the classes we track."""
    csv_path = Path(__file__).parent.parent / "vendor" / "panns" / "class_labels_indices.csv"
    mapping: dict[int, str] = {}
    with open(csv_path) as fh:
        for row in csv.DictReader(fh):
            name = row["display_name"].strip('"')
            if name in CLASS_MAP:
                mapping[int(row["index"])] = CLASS_MAP[name]
    return mapping


class _StreamingPostprocessor:
    """Apply the full median/hysteresis chain without storing probabilities."""

    def __init__(self, fps: float, enter: float, stay: float):
        width = max(1, int(0.15 * fps))
        self.width = width + (width % 2 == 0)
        self.radius = self.width // 2
        self.buffer: deque[float] = deque([0.0] * self.radius)
        self.next_index = 0
        self.fps = fps
        self.enter = enter
        self.stay = stay
        self.inside = False
        self.start = 0
        self.peak = 0.0
        self.spans: list[tuple[float, float, float]] = []

    def _consume_ready(self) -> None:
        while len(self.buffer) >= self.width:
            window = np.fromiter(self.buffer, dtype=np.float32, count=self.width)
            probability = float(np.median(window))
            index = self.next_index
            self.buffer.popleft()
            self.next_index += 1
            if not self.inside and probability >= self.enter:
                self.inside = True
                self.start = index
                self.peak = probability
            elif self.inside:
                if probability >= self.stay:
                    self.peak = max(self.peak, probability)
                else:
                    self.spans.append((self.start / self.fps, index / self.fps, self.peak))
                    self.inside = False

    def append(self, probabilities: np.ndarray) -> None:
        self.buffer.extend(float(value) for value in probabilities)
        self._consume_ready()

    def finish(self) -> list[tuple[float, float, float]]:
        self.buffer.extend([0.0] * self.radius)
        self._consume_ready()
        if self.inside:
            self.spans.append((self.start / self.fps, self.next_index / self.fps, self.peak))
            self.inside = False
        return post.drop_short(post.merge_close(self.spans))


def framewise_spans(
    model: panns_models.Cnn14_DecisionLevelMax,
    y32k: np.ndarray | Iterable[np.ndarray],
    device: torch.device,
    progress=None,
    total_samples: int | None = None,
    on_memory_error=None,
) -> tuple[dict[str, list[tuple[float, float, float]]], float]:
    """Stream PANNs posteriors directly into bounded event post-processors."""
    class_idx = load_class_indices()
    types = sorted(set(class_idx.values()))
    columns_by_type = {
        etype: [cls for cls, mapped in class_idx.items() if mapped == etype]
        for etype in types
    }
    sr = panns_models.SAMPLE_RATE
    fps = panns_models.FRAMES_PER_SEC
    chunk = int(CHUNK_SEC * sr)
    overlap = int(OVERLAP_SEC * sr)
    if isinstance(y32k, np.ndarray):
        total_samples = len(y32k)
        chunks = (y32k[pos : pos + chunk] for pos in range(0, len(y32k), chunk))
    else:
        if total_samples is None:
            raise ValueError("total_samples is required for streamed PANNs input")
        chunks = iter(y32k)
    processors = {
        etype: _StreamingPostprocessor(fps, *THRESHOLDS.get(etype, (0.15, 0.08)))
        for etype in types
    }

    pos = 0
    previous_tail = np.zeros(0, dtype=np.float32)
    with torch.inference_mode():
        for incoming in chunks:
            incoming = np.ascontiguousarray(incoming, dtype=np.float32)
            if len(incoming) == 0:
                continue
            prefix = previous_tail if pos else np.zeros(0, dtype=np.float32)
            seg = np.concatenate((prefix, incoming)) if len(prefix) else incoming
            x = torch.from_numpy(seg.astype(np.float32)).unsqueeze(0).to(device)
            try:
                framewise = model(x)["framewise_output"][0].cpu().numpy()  # (frames, 527)
            except MemoryError as exc:
                from ..jobs.queue import StageError

                diagnostic_id = on_memory_error(
                    {
                        "code": "EVENT_PANNS_MEMORY_EXHAUSTED",
                        "sample_rate": sr,
                        "chunk_sec": CHUNK_SEC,
                        "error_type": type(exc).__name__,
                    }
                ) if on_memory_error else None
                raise StageError(
                    "Audio event detection ran out of memory. Close other applications and retry; completed earlier stages remain reusable.",
                    code="EVENT_PANNS_MEMORY_EXHAUSTED",
                    diagnostic_id=diagnostic_id,
                ) from exc
            lead_frames = int(round(len(prefix) / sr * fps))
            usable = framewise[lead_frames:]
            expected_frames = int(np.ceil((total_samples or pos + len(incoming)) / sr * fps))
            remaining_frames = max(0, expected_frames - int(round(pos / sr * fps)))
            usable = usable[:remaining_frames]
            if len(usable) == 0:
                pos += len(incoming)
                previous_tail = incoming[-overlap:].copy()
                del x, framewise, usable, seg
                continue
            for etype in types:
                columns = columns_by_type[etype]
                if columns:
                    processors[etype].append(np.max(usable[:, columns], axis=1))
            if progress:
                progress(min(1.0, (pos + len(incoming)) / max(1, total_samples or 1)))
            pos += len(incoming)
            previous_tail = incoming[-overlap:].copy()
            del x, framewise, usable, seg
    return {etype: processor.finish() for etype, processor in processors.items()}, fps


def framewise_probs(*args, **kwargs):
    """Compatibility alias for callers migrating to streamed spans."""
    return framewise_spans(*args, **kwargs)
