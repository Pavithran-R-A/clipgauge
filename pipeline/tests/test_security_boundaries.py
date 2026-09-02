import hashlib
import sys
import types
from dataclasses import replace

import numpy as np
import pytest

# macOS Intel qualification intentionally omits the locked Torch stack because
# compatible wheels are unavailable. Linux and Windows run this full suite.
pytest.importorskip("torch", reason="Torch-backed security boundary tests require the managed ML stack")

from clipgauge_pipeline.camera.asd import AsdModel
from clipgauge_pipeline.camera.detect import FaceDetector
from clipgauge_pipeline.diarize import campplus
from clipgauge_pipeline.events import ser
from clipgauge_pipeline import local_runtime
from clipgauge_pipeline.models import registry, specs
from clipgauge_pipeline.models import managed
from clipgauge_pipeline.models.managed import validate_local_model_metadata
from clipgauge_pipeline.runtime import RuntimeIntegrityError
from clipgauge_pipeline.vendor.laughter import model as laughter_model
from clipgauge_pipeline.vendor.panns import models as panns_models


def test_managed_checkpoint_requires_registry_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPGAUGE_HOME", str(tmp_path / "home"))
    payload = b"approved checkpoint"
    spec = replace(
        specs.CAMPPLUS,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    approved = registry.model_path(spec)
    approved.parent.mkdir(parents=True)
    approved.write_bytes(payload)

    assert registry.require_verified_model(spec, approved) == approved.resolve()
    with pytest.raises(RuntimeIntegrityError, match="approved registry path"):
        registry.require_verified_model(spec, tmp_path / "unapproved.bin")


def test_model_metadata_rejects_remote_code_references(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"model_type":"whisper","remote_code":"https://example.test"}', encoding="utf-8")

    with pytest.raises(RuntimeIntegrityError, match="remote loading metadata"):
        validate_local_model_metadata(config_path)


def test_model_metadata_allows_tokenizer_vocab_tokens(tmp_path):
    config_path = tmp_path / "tokenizer.json"
    config_path.write_text('{"model":{"vocab":{"code":42}}}', encoding="utf-8")

    validate_local_model_metadata(config_path)


def test_managed_cudnn_catalog_is_pinned_and_minimal():
    asset = managed.cudnn_runtime_asset()

    assert asset is not None
    assert asset.asset_id == "runtime:cudnn:windows-x86_64:9.11.0.98-cuda12"
    assert asset.url.endswith("cudnn-windows-x86_64-9.11.0.98_cuda12-archive.zip")
    assert asset.size_bytes == 550_483_500
    assert len(asset.sha256) == 64
    assert set(managed.CUDNN_RUNTIME_FILES) == {
        "cudnn64_9.dll",
        "cudnn_adv64_9.dll",
        "cudnn_cnn64_9.dll",
        "cudnn_engines_precompiled64_9.dll",
        "cudnn_engines_runtime_compiled64_9.dll",
        "cudnn_graph64_9.dll",
        "cudnn_heuristic64_9.dll",
        "cudnn_ops64_9.dll",
    }
    assert all(len(digest) == 64 for digest in managed.CUDNN_RUNTIME_FILES.values())


def test_local_model_requires_hash_verification_before_runtime_start(tmp_path, monkeypatch):
    expected = b"approved!"
    tampered = b"tampered!"
    model = replace(
        local_runtime.MODEL_CATALOG["clipgauge-local/qwen3-1.7b-q8_0"],
        size_bytes=len(expected),
        sha256=hashlib.sha256(expected).hexdigest(),
    )
    monkeypatch.setitem(local_runtime.MODEL_CATALOG, model.model_id, model)
    manager = local_runtime.LocalRuntime(root=tmp_path / "home", manifest={})
    path = manager.model_path(model.model_id)
    path.parent.mkdir(parents=True)
    path.write_bytes(tampered)

    with pytest.raises(RuntimeIntegrityError, match="hash mismatch"):
        manager.verified_model_path(model.model_id)


def test_ser_falls_back_without_remote_code_loader(monkeypatch, tmp_path):
    called = False

    def remote_loader(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("remote code loader must not run")

    speechbrain = types.ModuleType("speechbrain")
    inference = types.ModuleType("speechbrain.inference")
    interfaces = types.ModuleType("speechbrain.inference.interfaces")
    interfaces.foreign_class = remote_loader
    monkeypatch.setitem(sys.modules, "speechbrain", speechbrain)
    monkeypatch.setitem(sys.modules, "speechbrain.inference", inference)
    monkeypatch.setitem(sys.modules, "speechbrain.inference.interfaces", interfaces)

    result = ser.arousal_curve_ser(np.zeros(16_000, dtype=np.float32), [], str(tmp_path))

    assert result is None
    assert called is False


@pytest.mark.parametrize(
    "loader",
    [
        lambda path: campplus.load_model(str(path), __import__("torch").device("cpu")),
        lambda path: laughter_model.load_model(str(path), __import__("torch").device("cpu")),
        lambda path: panns_models.load_model(str(path), __import__("torch").device("cpu")),
        lambda path: FaceDetector(str(path)),
        lambda path: AsdModel(str(path), str(path)),
    ],
)
def test_model_loaders_reject_unapproved_paths(loader, tmp_path):
    with pytest.raises(RuntimeIntegrityError, match="approved registry path"):
        loader(tmp_path / "unapproved-model.bin")
