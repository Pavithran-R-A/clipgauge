from types import SimpleNamespace

import pytest
import sys

from clipgauge_pipeline.asr import stage as asr_stage
from clipgauge_pipeline.asr import probe as asr_probe
from clipgauge_pipeline.asr.stage import _transcribe_with_fallback
from clipgauge_pipeline.jobs.queue import StageError


def test_cuda_probe_evidence_write_cleans_failed_temporary(monkeypatch, tmp_path):
    destination = tmp_path / "cuda-probe.json"
    destination.write_text("previous", encoding="utf-8")

    def fail_replace(*_args):
        raise OSError("replace failed")

    monkeypatch.setattr(asr_probe.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        asr_probe._atomic_write_text(destination, "new")

    assert destination.read_text(encoding="utf-8") == "previous"
    assert list(tmp_path.glob(".cuda-probe.json.*.part")) == []


class _Model:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def transcribe(self, _audio, batch_size):
        assert batch_size == 8
        if self.error:
            raise self.error
        return self.result


def test_transcription_retries_on_cpu_after_accelerator_failure():
    events = []
    gpu_model = _Model(error=RuntimeError("cublas64_12.dll is not found"))
    cpu_model = _Model(result={"language": "en", "segments": []})

    result, model, device, compute_type = _transcribe_with_fallback(
        gpu_model,
        audio=[0.0],
        device="cuda",
        compute_type="float16",
        load_cpu_model=lambda: cpu_model,
        emit=lambda message: events.append(message),
    )

    assert result == {"language": "en", "segments": []}
    assert model is cpu_model
    assert (device, compute_type) == ("cpu", "int8")
    assert any("CPU fallback" in event for event in events)


def test_long_accelerator_failure_requires_explicit_cpu_approval():
    gpu_model = _Model(error=RuntimeError("CUDA execution failed"))

    with pytest.raises(StageError) as caught:
        _transcribe_with_fallback(
            gpu_model,
            audio=[0.0],
            device="cuda",
            compute_type="float16",
            load_cpu_model=lambda: pytest.fail("CPU model must not load"),
            emit=lambda _message: None,
            allow_cpu_fallback=False,
        )

    assert caught.value.code == "ASR_GPU_FALLBACK_REQUIRES_APPROVAL"


def test_degraded_acceleration_state_uses_canonical_label():
    assert asr_stage.DEGRADED_ACCELERATION_STATE == "GPU PRESENT — RUNTIME DEGRADED"


def test_tamil_asr_uses_local_fallback_and_never_loads_english_alignment(monkeypatch, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"audio")
    events = []

    class Torch:
        class backends:
            class mps:
                @staticmethod
                def is_available():
                    return False

    class Model:
        @staticmethod
        def transcribe(_audio, batch_size):
            assert batch_size == 8
            return {"language": "ta", "segments": [{"start": 0.0, "end": 1.0, "text": "தமிழ் மொழி"}]}

    class WhisperX:
        @staticmethod
        def load_model(*_args, **_kwargs):
            return Model()

        @staticmethod
        def load_audio(_path):
            return [0.0] * 16_000

        @staticmethod
        def load_align_model(*_args, **_kwargs):
            pytest.fail("Tamil must not load the English alignment model")

    class Context:
        prior = {"ingest": {"audio_path": str(audio_path), "probe": {"duration_sec": 1.0}}}
        settings = SimpleNamespace(allow_cpu_asr_fallback=False)

        def emit(self, _fraction, message):
            events.append(message)

    monkeypatch.setitem(sys.modules, "torch", Torch)
    monkeypatch.setitem(sys.modules, "whisperx", WhisperX)
    monkeypatch.setattr(asr_stage.managed, "ready", lambda _manager: True)
    monkeypatch.setattr(asr_stage.managed, "asr_model_path", lambda: tmp_path / "model")
    monkeypatch.setattr(asr_stage.managed, "alignment_model_dir", lambda: tmp_path / "alignment")
    monkeypatch.setattr(asr_stage.hardware, "snapshot", lambda _root: {})
    monkeypatch.setattr(asr_stage.hardware, "select_asr_accelerator", lambda _capabilities: ("cpu", "int8"))
    monkeypatch.setattr(asr_stage.hardware, "asr_readiness", lambda _capabilities: {"state": "CPU FALLBACK", "device": "cpu", "compute_type": "int8", "reason": "cpu"})

    result = asr_stage.AsrStage().run(Context())

    assert result["language"] == "ta"
    assert result["alignment_status"] == "FALLBACK"
    assert result["alignment_asset_id"] is None
    assert result["word_count"] == 2
    assert any("deterministic" in message for message in events)


def test_gpu_transcription_uses_cpu_alignment_when_pytorch_cuda_is_unavailable(monkeypatch, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"audio")
    events = []

    class Torch:
        class backends:
            class mps:
                @staticmethod
                def is_available():
                    return False

    class Model:
        def transcribe(self, _audio, batch_size):
            assert batch_size == 8
            return {"language": "en", "segments": [{"start": 0.0, "end": 1.0, "text": "hello"}]}

    class WhisperX:
        @staticmethod
        def load_model(*args, **_kwargs):
            assert args[1] == "cuda"
            return Model()

        @staticmethod
        def load_audio(_path):
            return [0.0] * 16_000

        @staticmethod
        def load_align_model(*_args, **kwargs):
            assert kwargs["device"] == "cpu"
            return object(), object()

        @staticmethod
        def align(segments, *_args, **_kwargs):
            return {"segments": [{**segments[0], "words": [{"word": "hello", "start": 0.0, "end": 1.0, "score": 1.0}]}]}

    class Context:
        prior = {"ingest": {"audio_path": str(audio_path), "probe": {"duration_sec": 1.0}}}
        settings = SimpleNamespace(allow_cpu_asr_fallback=False)

        def emit(self, _fraction, message):
            events.append(message)

    monkeypatch.setitem(sys.modules, "torch", Torch)
    monkeypatch.setitem(sys.modules, "whisperx", WhisperX)
    monkeypatch.setattr(asr_stage.managed, "ready", lambda _manager: True)
    monkeypatch.setattr(asr_stage.managed, "asr_model_path", lambda: tmp_path / "model")
    monkeypatch.setattr(asr_stage.managed, "alignment_model_dir", lambda: tmp_path / "alignment")
    monkeypatch.setattr(asr_stage.managed, "activate_cuda_runtime", lambda: None)
    monkeypatch.setattr(asr_stage.hardware, "snapshot", lambda _root: {"cuda_ctranslate2": {"verified": True}})
    monkeypatch.setattr(asr_stage.hardware, "select_asr_devices", lambda _capabilities: {"transcription_device": "cuda", "transcription_compute_type": "float16", "alignment_device": "cpu"})
    monkeypatch.setattr(asr_stage.hardware, "asr_readiness", lambda _capabilities: {"state": "GPU ACCELERATED", "device": "cuda", "compute_type": "float16", "reason": "probe"})

    result = asr_stage.AsrStage().run(Context())

    assert result["transcription_device"] == "cuda"
    assert result["alignment_device"] == "cpu"
    assert result["acceleration_state"] == asr_stage.GPU_TRANSCRIPTION_CPU_ALIGNMENT_STATE
    assert result["acceleration_reason"] == "GPU transcription completed; word alignment is using CPU."
    assert any("GPU transcription" in message for message in events) or result["acceleration_reason"]


def test_transcription_checkpoint_reuse_skips_model_loading(monkeypatch, tmp_path):
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"audio")
    cached = {
        "identity": asr_stage._transcription_identity(audio_path),
        "result": {"language": "en", "segments": [{"start": 0.0, "end": 1.0, "text": "hello"}]},
        "transcription_device": "cuda",
        "transcription_compute_type": "float16",
    }

    class Context:
        job = object()
        prior = {"ingest": {"audio_path": str(audio_path), "probe": {"duration_sec": 1.0}}}
        settings = SimpleNamespace(allow_cpu_asr_fallback=False)

        def emit(self, _fraction, _message):
            pass

    monkeypatch.setattr(asr_stage.queue, "read_checkpoint", lambda *_args: cached)
    monkeypatch.setattr(asr_stage.managed, "ready", lambda _manager: True)
    monkeypatch.setattr(asr_stage.managed, "alignment_model_dir", lambda: tmp_path / "alignment")
    monkeypatch.setattr(asr_stage.managed, "activate_cuda_runtime", lambda: None)
    monkeypatch.setattr(asr_stage.hardware, "snapshot", lambda _root: {"cuda_ctranslate2": {"verified": True}})
    monkeypatch.setattr(asr_stage.hardware, "select_asr_devices", lambda _capabilities: {"transcription_device": "cuda", "transcription_compute_type": "float16", "alignment_device": "cpu"})
    monkeypatch.setattr(asr_stage.hardware, "asr_readiness", lambda _capabilities: {"state": "GPU ACCELERATED", "device": "cuda", "compute_type": "float16", "reason": "probe"})
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False))))
    monkeypatch.setitem(sys.modules, "whisperx", SimpleNamespace(
        load_audio=lambda _path: [0.0] * 16_000,
        load_model=lambda *_args, **_kwargs: pytest.fail("cached transcription must skip model loading"),
        load_align_model=lambda **_kwargs: (object(), object()),
        align=lambda segments, *_args, **_kwargs: {"segments": [{**segments[0], "words": [{"word": "hello", "start": 0.0, "end": 1.0}]}]},
    ))

    result = asr_stage.AsrStage().run(Context())

    assert result["word_count"] == 1
    assert result["benchmark"]["transcribe_sec"] == 0.0
