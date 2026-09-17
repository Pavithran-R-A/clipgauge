from clipgauge_pipeline import hardware


def test_linux_memory_values_prefer_memavailable_over_free_pages():
    values = hardware._linux_memory_values(
        {"MemTotal": 16 * hardware.GIB, "MemAvailable": 14 * hardware.GIB, "MemFree": 1 * hardware.GIB},
        physical_total=16 * hardware.GIB,
        sysconf_available=1 * hardware.GIB,
        cgroup_limit=None,
        cgroup_current=None,
    )

    assert values == {
        "total_bytes": 16 * hardware.GIB,
        "available_bytes": 14 * hardware.GIB,
        "available_source": "proc_meminfo",
        "cgroup_memory_limit_bytes": None,
        "cgroup_memory_current_bytes": None,
    }


def test_linux_memory_values_cap_available_at_cgroup_headroom():
    values = hardware._linux_memory_values(
        {"MemTotal": 16 * hardware.GIB, "MemAvailable": 10 * hardware.GIB},
        physical_total=16 * hardware.GIB,
        sysconf_available=1 * hardware.GIB,
        cgroup_limit=8 * hardware.GIB,
        cgroup_current=7 * hardware.GIB,
    )

    assert values["total_bytes"] == 8 * hardware.GIB
    assert values["available_bytes"] == 1 * hardware.GIB
    assert values["available_source"] == "proc_meminfo+cgroup"
    assert values["cgroup_memory_limit_bytes"] == 8 * hardware.GIB
    assert values["cgroup_memory_current_bytes"] == 7 * hardware.GIB


def test_linux_memory_values_marks_sysconf_fallback_when_memavailable_is_missing():
    values = hardware._linux_memory_values(
        {"MemTotal": 16 * hardware.GIB},
        physical_total=16 * hardware.GIB,
        sysconf_available=4 * hardware.GIB,
        cgroup_limit=None,
        cgroup_current=None,
    )

    assert values["available_bytes"] == 4 * hardware.GIB
    assert values["available_source"] == "sysconf_avphys_pages"


def test_linux_meminfo_parser_rejects_malformed_values():
    values = hardware._parse_meminfo("MemAvailable: malformed kB\nMemFree: 128 kB\nBroken line")

    assert values == {"MemFree": 128 * 1024}


def test_linux_memory_snapshot_uses_memavailable_for_asr_headroom(monkeypatch):
    monkeypatch.setattr(hardware.sys, "platform", "linux")
    monkeypatch.setattr(hardware, "_memory_bytes", lambda: 16 * hardware.GIB)
    monkeypatch.setattr(hardware, "_sysconf_available_bytes", lambda: 1 * hardware.GIB)
    monkeypatch.setattr(hardware, "_linux_cgroup_memory", lambda: (None, None))
    monkeypatch.setattr(
        hardware,
        "_read_text",
        lambda path: "MemTotal: 16777216 kB\nMemAvailable: 14680064 kB\n" if path.name == "meminfo" else None,
    )

    result = hardware._memory_snapshot()

    assert result["available_bytes"] == 14 * hardware.GIB
    assert result["available_source"] == "proc_meminfo"


def test_linux_cgroup_memory_reads_v2_limit_and_current_usage(monkeypatch):
    monkeypatch.setattr(
        hardware,
        "_read_text",
        lambda path: {
            "cgroup": "0::/github-runner\n",
            "memory.max": str(8 * hardware.GIB),
            "memory.current": str(3 * hardware.GIB),
        }.get(path.name),
    )

    assert hardware._linux_cgroup_memory() == (8 * hardware.GIB, 3 * hardware.GIB)


def test_linux_cgroup_memory_reads_v1_limit_and_current_usage(monkeypatch):
    monkeypatch.setattr(
        hardware,
        "_read_text",
        lambda path: {
            "cgroup": "7:cpu,memory:/runner\n",
            "memory.limit_in_bytes": str(6 * hardware.GIB),
            "memory.usage_in_bytes": str(2 * hardware.GIB),
        }.get(path.name),
    )

    assert hardware._linux_cgroup_memory() == (6 * hardware.GIB, 2 * hardware.GIB)


def test_linux_cgroup_memory_treats_unlimited_and_malformed_values_as_unknown():
    assert hardware._parse_cgroup_memory_value("max") is None
    assert hardware._parse_cgroup_memory_value("not-a-number") is None
    assert hardware._parse_cgroup_memory_value("-1") is None


def test_snapshot_exposes_linux_memory_measurement_sources(monkeypatch):
    monkeypatch.setattr(hardware.platform, "system", lambda: "Linux")
    monkeypatch.setattr(hardware.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(hardware, "_nvidia", lambda: {})
    monkeypatch.setattr(hardware, "_cuda", lambda: {})
    monkeypatch.setattr(hardware, "_pytorch_cuda", lambda: {})
    monkeypatch.setattr(hardware, "_whisperx_alignment", lambda: {})
    monkeypatch.setattr(hardware, "_vulkan", lambda: {})
    monkeypatch.setattr(hardware, "_cpu", lambda: {})
    monkeypatch.setattr(hardware, "_memory_snapshot", lambda: {
        "total_bytes": 8 * hardware.GIB,
        "available_bytes": 4 * hardware.GIB,
        "available_source": "proc_meminfo+cgroup",
        "total_page_file_bytes": None,
        "available_page_file_bytes": None,
        "cgroup_memory_limit_bytes": 6 * hardware.GIB,
        "cgroup_memory_current_bytes": 2 * hardware.GIB,
    })

    result = hardware.snapshot()

    assert result["available_ram_source"] == "proc_meminfo+cgroup"
    assert result["cgroup_memory_limit_bytes"] == 6 * hardware.GIB
    assert result["cgroup_memory_current_bytes"] == 2 * hardware.GIB


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
