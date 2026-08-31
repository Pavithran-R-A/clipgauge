from clipgauge_pipeline import hardware


def test_cuda_probe_requires_a_real_device(monkeypatch):
    class CTranslate2:
        @staticmethod
        def get_supported_compute_types(_device):
            return {"float16", "int8_float16"}

        @staticmethod
        def get_cuda_device_count():
            return 1

    monkeypatch.setitem(__import__("sys").modules, "ctranslate2", CTranslate2)
    result = hardware._cuda()

    assert result["verified"] is True
    assert result["device_count"] == 1


def test_cuda_probe_rejects_runtime_without_devices(monkeypatch):
    class CTranslate2:
        @staticmethod
        def get_supported_compute_types(_device):
            return {"float16"}

        @staticmethod
        def get_cuda_device_count():
            return 0

    monkeypatch.setitem(__import__("sys").modules, "ctranslate2", CTranslate2)
    result = hardware._cuda()

    assert result["available"] is True
    assert result["verified"] is False
    assert result["device_count"] == 0


def test_asr_readiness_distinguishes_acceleration_and_fallback():
    accelerated = hardware.asr_readiness(
        {"nvidia": {"available": True, "verified": True}, "cuda_ctranslate2": {
            "available": True, "verified": True, "device_count": 1, "compute_types": ["float16"]
        }}
    )
    degraded = hardware.asr_readiness(
        {"nvidia": {"available": True, "verified": True}, "cuda_ctranslate2": {
            "available": True, "verified": False, "device_count": 0, "compute_types": []
        }}
    )
    failed = hardware.asr_readiness(
        {"nvidia": {"available": False, "verified": False}, "cuda_ctranslate2": {
            "available": False, "verified": False, "device_count": 0, "compute_types": []
        }}
    )

    assert accelerated["state"] == "GPU ACCELERATED"
    assert accelerated["device"] == "cuda"
    assert degraded["state"] == "GPU PRESENT — RUNTIME DEGRADED"
    assert failed["state"] == "CPU FALLBACK"
