import json
from types import SimpleNamespace

import pytest

from clipgauge_pipeline import local_runtime
from clipgauge_pipeline import cli
from clipgauge_pipeline.edits import render_clip as edit_render
from clipgauge_pipeline.render import renderer
from clipgauge_pipeline.scoring import stage as scoring_stage
from clipgauge_pipeline.scoring import providers


def test_windows_nvidia_prefers_verified_vulkan_local_runtime():
    key = local_runtime.select_runtime_asset_key(
        platform_key="windows-x86_64",
        nvidia_available=True,
        vulkan_available=False,
        available_keys={"windows-x86_64", "windows-x86_64-vulkan"},
    )
    assert key == "windows-x86_64-vulkan"


def test_windows_verified_cuda_runtime_wins_over_vulkan():
    key = local_runtime.select_runtime_asset_key(
        platform_key="windows-x86_64",
        nvidia_available=True,
        vulkan_available=True,
        cuda_available=True,
        available_keys={
            "windows-x86_64",
            "windows-x86_64-vulkan",
            "windows-x86_64-cuda",
        },
    )
    assert key == "windows-x86_64-cuda"


def test_windows_vulkan_remains_fallback_without_cuda_runtime():
    key = local_runtime.select_runtime_asset_key(
        platform_key="windows-x86_64",
        nvidia_available=True,
        vulkan_available=True,
        cuda_available=False,
        available_keys={
            "windows-x86_64",
            "windows-x86_64-vulkan",
            "windows-x86_64-cuda",
        },
    )
    assert key == "windows-x86_64-vulkan"


def test_runtime_download_identity_includes_selected_backend(tmp_path, monkeypatch):
    manifest = {
        "runtimes": {
            "llama-server": {
                "version": "b10545",
                "license": "MIT",
                "provenance": "https://example.invalid/llama",
            }
        }
    }
    manager = local_runtime.LocalRuntime(root=tmp_path, manifest=manifest)
    monkeypatch.setattr(manager, "runtime_asset_key", lambda: "windows-x86_64-cuda")
    monkeypatch.setattr(
        manager,
        "runtime_asset",
        lambda: {
            "archive_type": "zip",
            "url": "https://example.invalid/cuda.zip",
            "size": 12,
            "sha256": "a" * 64,
        },
    )

    asset = cli._setup_runtime_asset(manager)

    assert asset.asset_id == "runtime:llama-server:windows-x86_64-cuda"
    assert asset.destination.endswith("llama-server-b10545-windows-x86_64-cuda.zip")


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


def test_finalist_selection_spreads_candidates_across_long_source():
    entries = [
        {"start": start, "end": start + 42.0, "recommendation_score": score}
        for start, score in [
            (0.0, 99.0), (35.0, 98.0), (70.0, 97.0), (105.0, 96.0),
            (140.0, 95.0), (175.0, 94.0), (360.0, 91.0), (620.0, 89.0),
            (890.0, 87.0), (1010.0, 86.0),
        ]
    ]

    finalists = scoring_stage.select_diverse_finalists(entries, limit=6)
    starts = [entry["start"] for entry in finalists]

    assert len(finalists) == 6
    assert max(starts) - min(starts) >= 800.0
    assert sum(1 for start in starts if start < 200.0) <= 3


def test_nvenc_is_preferred_over_software_encoding_when_functional():
    args = renderer.select_video_encoder(nvenc_available=True, videotoolbox_available=False)
    assert args[:2] == ["-c:v", "h264_nvenc"]
    assert "libx264" not in args


def test_software_encoder_remains_the_safe_last_resort():
    args = renderer.select_video_encoder(nvenc_available=False, videotoolbox_available=False)
    assert args[:2] == ["-c:v", "libx264"]


def test_edited_render_uses_verified_encoder_selection(monkeypatch):
    monkeypatch.setattr(edit_render.renderer, "nvenc_available", lambda: True)
    monkeypatch.setattr(edit_render.renderer, "videotoolbox_available", lambda: False)

    args = edit_render.video_encoder_args()

    assert args[:2] == ["-c:v", "h264_nvenc"]
    assert "libx264" not in args


@pytest.mark.parametrize("candidate_count", [35, 100, 500])
def test_local_scoring_actual_model_calls_stay_bounded(monkeypatch, tmp_path, candidate_count):
    profile = providers.preset_profile("clipgauge-local", metadata={"managed": False})

    class Client:
        def __init__(self):
            self.profile = profile
            self.model = profile.model
            self.last_result = None
            self.calls = 0

        def structured_level(self):
            return "json_mode"

        def generate_json(self, _prompt, _schema, **_kwargs):
            self.calls += 1
            return {
                "hook": 7, "hook_type": "bold_claim", "funniness": 5,
                "punchline_index": -1, "shock": 2, "curiosity_gap": 6,
                "value": 7, "self_contained": True, "bait_phrases": [],
                "summary": "A complete local scoring fixture.",
                "hook_strength": 7, "hook_reason": "claim",
                "standalone_comprehension": 7, "setup_strength": 7,
                "escalation_strength": 7, "payoff_strength": 7,
                "payoff_location": "middle", "ending_completeness": 7,
                "story_shape": "hook_setup_payoff", "information_density": 7,
                "reaction_strength": 7, "recommended_start_offset": 0.4,
                "recommended_end_offset": 5.0,
            }

    client = Client()
    selection_inputs = []
    original_selector = scoring_stage.select_diverse_finalists

    def capture_selection(entries, limit):
        selection_inputs.append([dict(entry) for entry in entries])
        return original_selector(entries, limit)

    monkeypatch.setattr(scoring_stage, "select_diverse_finalists", capture_selection)
    monkeypatch.setattr(scoring_stage.providers_mod, "profile_from_snapshot", lambda _snapshot: profile)
    monkeypatch.setattr(scoring_stage.providers_mod, "make_adapter", lambda _profile: client)
    words = [{"word": f"word{i}", "start": i * 0.4, "end": i * 0.4 + 0.2} for i in range(25)]
    curves_path = tmp_path / "curves.json"
    curves_path.write_text(json.dumps({"arousal": [], "arousal_grid_sec": 0.5}), encoding="utf-8")
    candidates = [
        {"start": 0.0, "end": 10.0, "curve_score": (i % 10) / 10, "channel_scores": {"energy": i % 3}}
        for i in range(candidate_count)
    ]
    ctx = SimpleNamespace(
        prior={
            "ingest": {"probe": {"duration_sec": 10.0}, "media_path": "fixture.mp4"},
            "diarize": {"segments": [{"start": 0.0, "end": 10.0, "speaker": 0, "words": words}]},
            "events": {"timeline": [], "curves_path": str(curves_path)},
            "candidates": {"candidates": candidates},
        },
        settings=SimpleNamespace(provider_snapshot=lambda: {}),
        job_dir=tmp_path,
        emit=lambda *_args: None,
    )

    result = scoring_stage.ScoreStage().run(ctx)

    assert client.calls == result["performance"]["t1_calls"]
    assert client.calls <= scoring_stage.LOCAL_T1_CANDIDATE_LIMIT
    assert result["performance"]["finalist_limit"] == scoring_stage.LOCAL_FINALIST_LIMIT
    assert result["performance"]["music_llm_calls"] == 0
    assert selection_inputs
    assert all("recommendation_score" in item for item in selection_inputs[0])
    assert all("boundary_refinement" in item for item in result["clips"])
    assert any(
        item["boundary_refinement"]["head_adjustment"] != 0
        or item["boundary_refinement"]["tail_adjustment"] != 0
        for item in result["clips"]
    )
