# ClipGauge v0.4.0 Setup Validation

**Status:** PASS for the Linux-controlled validation environment; Windows installer acceptance remains a native GitHub Actions gate.

## Scope

This document records the v0.4.0 Setup Center and managed-runtime validation performed against the isolated home `/home/ubuntu/clipgauge-stage0/v040-e2e-home`. The test home was separate from the developer’s normal configuration and contained only verified assets installed through the ClipGauge-managed paths. The authoritative design is [`V0_4_DOWNLOAD_MANAGER_DESIGN.md`](V0_4_DOWNLOAD_MANAGER_DESIGN.md), and the creator-facing workflow is [`V0_4_USER_WORKFLOW.md`](V0_4_USER_WORKFLOW.md).

## Managed groups

| Group | Validation result | Observed behavior |
|---|---|---|
| `core:asr` | PASS | faster-whisper, alignment, NLTK data, and the pinned Silero VAD repository were installed or reused through one consented manager. |
| `core:analysis` | PASS | Six analysis-model rows were represented in the managed inventory and installed or reused with exact size/hash metadata. |
| `core:youtube` | PASS for deterministic setup/self-test | Managed yt-dlp, portable Node.js, and bgutil provider assets were represented; loopback health and yt-dlp discoverability checks were implemented. Live YouTube retrieval is documented separately. |
| `install-ffmpeg` | PASS | FFmpeg resolution routes through the manager and rendering fails closed instead of initiating an implicit download. |
| `install-runtime` | PASS | The pinned llama.cpp runtime installed with archive traversal checks and safe symlink/hardlink materialization. |
| `download-model` | PASS | The lightweight Qwen3 GGUF model installed through the managed local-runtime path and passed the provider contract check. |

## Consent and progress

The Download Manager requires explicit grouped consent before new assets are downloaded. Its progress contract includes asset identity, bytes completed, total bytes where known, speed, fraction, ETA, elapsed time, cached state, one-time-download state, and terminal state. The frontend Setup Center receives streamed setup events and exposes cancellation. The onboarding flow blocks a managed download action until the consent checkbox is selected.

Regression coverage in `pipeline/tests/test_v040_download_manager.py` covers grouped consent, cache reuse, migration, cancellation, progress, repair, and insufficient-disk-space behavior. The complete Python suite finished with **158 passed** and one pre-existing unknown-mark warning for `pytest.mark.slow`.

## Cache reuse and repair

The isolated validation home reused already-verified assets on subsequent setup and resume operations. The logs contain `Verified asset reused.` events for analysis assets and the managed runtime. The manager keeps verified content in place, stages new downloads under `.partial`, validates the expected length and SHA-256, and marks corruption for repair rather than treating an incomplete file as ready.

## Silero VAD closure

The failed first model-backed run exposed a hidden WhisperX `torch.hub` fetch for Silero VAD. v0.4.0 closes that gap by adding a pinned Silero repository archive to the `core:asr` catalog, verifying its immutable archive metadata, extracting it atomically into the managed torch hub cache, and checking the required entrypoint files before ASR. A direct Silero load succeeded with network-disabled environment variables. The later real E2E therefore did not need a compute-time GitHub fetch.

## Local runtime readiness

The managed ClipGauge Local runtime passed health, model-listing, and structured-completion checks. The runtime is loopback-only, uses the verified llama-server binary and Qwen3 GGUF, and starts with one parallel slot, a 4096-token context, and Qwen3 reasoning disabled. These settings bound structured rubric latency after the earlier diagnostic showed unrestricted reasoning could exceed the provider deadline.

## Evidence files

The durable E2E evidence is recorded in `/home/ubuntu/clipgauge-stage0/v040-e2e-validation.txt`, `/home/ubuntu/clipgauge-stage0/v040-e2e-media-facts.txt`, the JSONL run log under `v040-e2e-home/model-e2e-resume-static.jsonl`, and the isolated job directory named `20260821-132437-f2ef91`. The exact final clip hash is recorded in the model-backed E2E document.

## Limitations

This document does not claim Windows acceptance. Clean Windows installation, silent NSIS installation, installed-EXE launch, and Windows managed-layout checks remain responsibilities of the `windows-latest` workflow and are reported in [`V0_4_WINDOWS_E2E.md`](V0_4_WINDOWS_E2E.md).
