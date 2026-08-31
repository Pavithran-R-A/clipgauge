# Windows Performance and Export Rescue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make realistic long-form ClipGauge jobs fast and predictable on Windows, use available hardware acceleration safely, and let users save exported clips to an explicitly chosen location.

**Architecture:** Keep the Tauri + React + Python + FFmpeg product boundary, but remove waste inside the pipeline. Windows local inference becomes GPU-first with a verified Vulkan llama.cpp runtime and CPU fallback, local scoring gets a hard expensive-call budget, rendering gets hardware encoder selection, export gains a native Save As destination, and readiness/performance metadata tells the truth about degraded CPU execution.

**Tech Stack:** Tauri 2, React 19, TypeScript, Python 3.12, llama.cpp, WhisperX/faster-whisper/CTranslate2, FFmpeg, pytest, Vitest, Cargo tests, GitHub Actions.

**Spec:** User reproduction on a ~17 minute 1080p video: >1 hour total, CPU ASR fallback, ~35 sequential local scoring calls, 12 sequential renders, and export hard-coded to Downloads.

## Global Constraints

- Preserve source-artifact path validation and all existing security boundaries.
- Preserve local-first behavior and CPU fallbacks; degraded execution must be explicit rather than silently labelled fully ready.
- No unverified runtime/model downloads; all managed assets remain pinned by immutable upstream revision and SHA-256.
- Never require a cloud AI provider for the default ClipGauge Local path.
- Do not merge this branch without explicit user approval.
- Performance gates must be deterministic enough for shared CI; wall-clock observations may supplement but must not replace bounded-work assertions.

---

### Task 1: Lock the performance contract in failing tests

**Files:**
- Create: `pipeline/tests/test_performance_contract.py`
- Create: `app/src/exportDestination.test.ts`

**Interfaces:**
- Produces required policy helpers for runtime backend selection, local scoring work limits, video encoder selection, and export destination sanitization.

- [ ] Write failing tests proving Windows x64 with a verified GPU selects a GPU llama.cpp runtime, local scoring is capped at 10 expensive T1 calls and 6 finalists, local music does not add blocking LLM calls, and NVENC outranks software x264 when the probe succeeds.
- [ ] Write a failing frontend test proving export opens a native Save As dialog and cancellation performs no backend copy.
- [ ] Run CI and retain the expected RED evidence before implementation.

### Task 2: Make ClipGauge Local GPU-first on Windows

**Files:**
- Modify: `pipeline/runtime-manifest.json`
- Modify: `pipeline/clipgauge_pipeline/local_runtime.py`
- Modify: `pipeline/clipgauge_pipeline/cli.py`
- Test: `pipeline/tests/test_performance_contract.py`

**Interfaces:**
- `LocalRuntime.runtime_backend() -> str`
- `LocalRuntime.runtime_asset_key() -> str`
- `LocalRuntime.command(...)` adds GPU offload only for GPU runtimes.

- [ ] Pin the official llama.cpp b10545 Windows x64 Vulkan archive and SHA-256 while retaining the CPU archive as fallback.
- [ ] Install runtime variants into variant-specific directories so a stale CPU executable cannot masquerade as the selected GPU runtime.
- [ ] Select Vulkan for Windows x64 when a usable NVIDIA/Vulkan-capable device is detected; otherwise select the verified CPU runtime.
- [ ] Start Vulkan llama-server with full model offload and report the selected backend in setup inventory/diagnostics.
- [ ] Verify existing runtime integrity and security tests remain green.

### Task 3: Bound local scoring work

**Files:**
- Modify: `pipeline/clipgauge_pipeline/scoring/stage.py`
- Test: `pipeline/tests/test_performance_contract.py`

**Interfaces:**
- `LOCAL_T1_CANDIDATE_LIMIT = 10`
- `LOCAL_FINALIST_LIMIT = 6`
- Score output includes a `performance` object with candidate and model-call counts.

- [ ] Deterministically pre-rank candidate windows before invoking a local LLM.
- [ ] Score at most 10 viable local candidates instead of every generated candidate.
- [ ] Keep at most 6 local finalists.
- [ ] Do not make a second local LLM call per finalist merely to produce music guidance; use no blocking music LLM on the local path.
- [ ] Keep the richer cloud-provider path intact.

### Task 4: Use hardware video encoding when it actually works

**Files:**
- Modify: `pipeline/clipgauge_pipeline/render/renderer.py`
- Test: `pipeline/tests/test_performance_contract.py`

**Interfaces:**
- `select_video_encoder(...)` / runtime encoder probe returns `h264_nvenc`, `h264_videotoolbox`, or `libx264`.

- [ ] Add a cached functional NVENC smoke probe rather than trusting encoder-list presence.
- [ ] Prefer NVENC on compatible Windows/NVIDIA systems, VideoToolbox on compatible macOS systems, then x264 fallback.
- [ ] Keep output dimensions, subtitle burn-in, audio normalization, verification, and metadata stripping unchanged.

### Task 5: Make ASR degradation explicit and actionable

**Files:**
- Modify: `pipeline/clipgauge_pipeline/hardware.py`
- Modify: `pipeline/clipgauge_pipeline/asr/stage.py`
- Modify: `pipeline/clipgauge_pipeline/cli.py`
- Modify: `app/src/components/SetupCenter.tsx`
- Test: `pipeline/tests/test_asr_fallback.py`
- Test: `app/src/v050InformationArchitecture.test.tsx`

**Interfaces:**
- Hardware/setup inventory exposes speech acceleration state and an actionable reason when NVIDIA exists but CTranslate2 CUDA is unavailable.

- [ ] Preserve CPU int8 fallback so jobs still work.
- [ ] Distinguish `gpu`, `cpu`, and `gpu-unavailable` readiness instead of displaying all installed assets as equivalent performance readiness.
- [ ] Surface the CUDA 12/cuDNN requirement when that is why an NVIDIA GPU cannot be used.
- [ ] Include ASR real-time factor and accelerator in job result provenance.

### Task 6: Replace hard-coded Downloads export with Save As

**Files:**
- Modify: `app/src/components/Review.tsx`
- Modify: `app/src/api.ts`
- Modify: `app/src-tauri/src/artifact.rs`
- Modify: `app/src-tauri/src/main.rs`
- Test: `app/src/exportDestination.test.ts`
- Test: Rust artifact tests in `app/src-tauri/src/artifact.rs`

**Interfaces:**
- Frontend opens `@tauri-apps/plugin-dialog.save()` with an MP4 filter.
- Backend export command accepts an optional explicit destination.
- Explicit destination must be absolute, end in `.mp4`, have an existing parent directory, and may not be a symlink.

- [ ] Native Save As dialog chooses the exact output path.
- [ ] Cancellation leaves the source render untouched and performs no copy.
- [ ] Backend re-validates the managed source artifact before every copy.
- [ ] Preserve old Downloads fallback only for compatibility callers that omit a destination.

### Task 7: Add deterministic long-form performance gates

**Files:**
- Create or modify a CI performance-contract test/workflow under `.github/` and `pipeline/tests/`.
- Modify docs/changelog/version only after implementation is green.

**Interfaces:**
- CI asserts bounded expensive calls/renders and records stage benchmark metadata; it does not depend on flaky absolute timing alone.

- [ ] Assert a 35-candidate local job can never cause more than 10 T1 LLM calls, 0 local music LLM calls, and 6 finalist renders.
- [ ] Assert GPU-capable Windows selects a GPU local-runtime variant and hardware encoding when probes succeed.
- [ ] Run Python, frontend, Rust, and existing release/security suites.
- [ ] Inspect the complete PR diff for security, lifecycle, and regression risks.
- [ ] Keep the PR draft until all required checks are green and evidence is attached.
