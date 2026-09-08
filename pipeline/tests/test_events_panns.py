from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from clipgauge_pipeline.events import panns_channel, post


class _FakePanns:
    def __init__(self, seen):
        self.seen = seen

    def __call__(self, values):
        self.seen.append(int(values.shape[1]))
        frames = max(1, int(round(values.shape[1] / 320)))
        output = torch.zeros((1, frames, 527), dtype=torch.float32)
        output[0, min(20, frames - 1) : min(60, frames), 0] = 0.9
        return {"framewise_output": output}


def test_framewise_spans_processes_bounded_audio_chunks(monkeypatch):
    monkeypatch.setattr(panns_channel, "load_class_indices", lambda: {0: "laugh"})
    seen: list[int] = []
    chunks = [np.zeros(32_000, dtype=np.float32) for _ in range(3)]
    spans, fps = panns_channel.framewise_spans(
        _FakePanns(seen), iter(chunks), "cpu", total_samples=96_000
    )
    assert fps == 100.0
    assert max(seen) <= int((panns_channel.CHUNK_SEC + panns_channel.OVERLAP_SEC) * 32_000)
    assert spans["laugh"]


def test_streaming_postprocessor_matches_small_postprocess():
    rng = np.random.default_rng(3)
    values = rng.random(1_237, dtype=np.float32)
    values[100:180] = 0.9
    expected = post.postprocess(values, 100.0, enter=0.1, stay=0.05)
    processor = panns_channel._StreamingPostprocessor(100.0, 0.1, 0.05)
    for chunk in np.array_split(values, 11):
        processor.append(chunk)
    assert processor.finish() == expected
