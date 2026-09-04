from types import SimpleNamespace

import pytest

from clipgauge_pipeline.asr import stage as asr_stage
from clipgauge_pipeline.asr.stage import _transcribe_with_fallback
from clipgauge_pipeline.jobs.queue import StageError


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
