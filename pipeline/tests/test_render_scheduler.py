from clipgauge_pipeline.render.scheduler import concurrency_limit


def test_hardware_rendering_is_always_serial():
    assert concurrency_limit("h264_nvenc", ram_bytes=64 * 1024**3, vram_mb=8192) == 1
    assert concurrency_limit("h264_videotoolbox", ram_bytes=64 * 1024**3) == 1


def test_software_rendering_respects_memory_floor():
    assert concurrency_limit("libx264", ram_bytes=8 * 1024**3) == 1
    assert concurrency_limit("libx264", ram_bytes=32 * 1024**3) == 2
