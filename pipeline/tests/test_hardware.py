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


def test_transcription_and_alignment_devices_are_selected_independently():
    devices = hardware.select_asr_devices(
        {
            "cuda_ctranslate2": {
                "verified": True,
                "device_count": 1,
                "compute_types": ["int8_float16"],
            },
            "pytorch_cuda": {
                "verified": False,
                "reason": "Torch not compiled with CUDA enabled",
            },
        }
    )

    assert devices == {
        "transcription_device": "cuda",
        "transcription_compute_type": "int8_float16",
        "alignment_device": "cpu",
    }


def test_cpu_probe_records_supported_compute_types(monkeypatch):
    class CTranslate2:
        __version__ = "4.6.0"

        @staticmethod
        def get_supported_compute_types(_device):
            return {"float32", "int8"}

    monkeypatch.setitem(__import__("sys").modules, "ctranslate2", CTranslate2)

    result = hardware._cpu()

    assert result == {
        "available": True,
        "verified": True,
        "compute_types": ["float32", "int8"],
        "version": "4.6.0",
    }


def test_cpu_asr_policy_uses_conservative_batches_by_ram():
    assert hardware.cpu_asr_policy({"ram_bytes": 8 * 1024**3, "cpu_ctranslate2": {"compute_types": ["int8"]}}) == {
        "device": "cpu",
        "compute_type": "int8",
        "batch_size": 1,
        "mode": "low-memory",
    }
    assert hardware.cpu_asr_policy({"ram_bytes": 16 * 1024**3, "cpu_ctranslate2": {"compute_types": ["int8"]}})["batch_size"] == 2
    assert hardware.cpu_asr_policy({"ram_bytes": 32 * 1024**3, "cpu_ctranslate2": {"compute_types": ["int8"]}})["batch_size"] == 4
    assert hardware.cpu_asr_policy({"ram_bytes": 64 * 1024**3, "cpu_ctranslate2": {"compute_types": ["int8"]}})["batch_size"] == 8


def test_cpu_asr_policy_downgrades_when_available_memory_is_low():
    policy = hardware.cpu_asr_policy({
        "ram_bytes": 16 * 1024**3,
        "available_ram_bytes": 1 * 1024**3,
        "cpu_ctranslate2": {"compute_types": ["int8"]},
    })

    assert policy["batch_size"] == 1
    assert policy["mode"] == "low-memory"


def test_cpu_selection_does_not_attempt_unsupported_int8():
    devices = hardware.select_asr_devices({
        "ram_bytes": 8 * 1024**3,
        "cpu_ctranslate2": {"verified": True, "compute_types": ["float32"]},
    })

    assert devices["transcription_device"] == "cpu"
    assert devices["transcription_compute_type"] == "float32"
    assert devices["transcription_batch_size"] == 1
