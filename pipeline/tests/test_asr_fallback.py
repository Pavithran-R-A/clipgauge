from types import SimpleNamespace

from clipgauge_pipeline.asr.stage import _transcribe_with_fallback


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
