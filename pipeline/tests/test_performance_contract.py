from clipgauge_pipeline import local_runtime
from clipgauge_pipeline.render import renderer
from clipgauge_pipeline.scoring import stage as scoring_stage


def test_windows_nvidia_prefers_verified_vulkan_local_runtime():
    key = local_runtime.select_runtime_asset_key(
        platform_key="windows-x86_64",
        nvidia_available=True,
        vulkan_available=False,
        available_keys={"windows-x86_64", "windows-x86_64-vulkan"},
    )
    assert key == "windows-x86_64-vulkan"


def test_windows_without_verified_gpu_keeps_cpu_runtime_fallback():
    key = local_runtime.select_runtime_asset_key(
        platform_key="windows-x86_64",
        nvidia_available=False,
        vulkan_available=False,
        available_keys={"windows-x86_64", "windows-x86_64-vulkan"},
    )
    assert key == "windows-x86_64"


def test_local_scoring_has_a_hard_expensive_work_budget():
    budget = scoring_stage.scoring_budget(local=True, candidate_count=35)
    assert budget["candidate_count"] == 35
    assert budget["t1_limit"] == 10
    assert budget["finalist_limit"] == 6
    assert budget["music_llm"] is False


def test_cloud_scoring_keeps_the_existing_richer_budget():
    budget = scoring_stage.scoring_budget(local=False, candidate_count=35)
    assert budget["candidate_count"] == 35
    assert budget["t1_limit"] == 35
    assert budget["finalist_limit"] == 12
    assert budget["music_llm"] is True


def test_nvenc_is_preferred_over_software_encoding_when_functional():
    args = renderer.select_video_encoder(nvenc_available=True, videotoolbox_available=False)
    assert args[:2] == ["-c:v", "h264_nvenc"]
    assert "libx264" not in args


def test_software_encoder_remains_the_safe_last_resort():
    args = renderer.select_video_encoder(nvenc_available=False, videotoolbox_available=False)
    assert args[:2] == ["-c:v", "libx264"]
