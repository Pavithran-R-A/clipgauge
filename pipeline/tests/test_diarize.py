from __future__ import annotations

import numpy as np

from clipgauge_pipeline.diarize import stage


def test_embedding_cache_writes_are_atomic(tmp_path, monkeypatch):
    replaced = []
    original_replace = stage.os.replace

    def record_replace(source, destination):
        replaced.append((source, destination))
        return original_replace(source, destination)

    monkeypatch.setattr(stage.os, "replace", record_replace)
    destination = tmp_path / "diar_embeddings.npy"
    embeddings = np.arange(6, dtype=np.float32).reshape(2, 3)

    stage._atomic_save_npy(destination, embeddings)

    assert replaced
    assert all(str(source).endswith(".tmp") for source, _ in replaced)
    np.testing.assert_array_equal(np.load(destination, allow_pickle=False), embeddings)
    assert not list(tmp_path.glob("*.tmp"))
