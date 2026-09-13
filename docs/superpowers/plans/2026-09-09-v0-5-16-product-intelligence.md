# ClipGauge v0.5.16 Product Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve ClipGauge quality, provider model control, setup performance, and user-facing reliability without changing v0.5.15.

**Architecture:** Keep broad candidate discovery deterministic and provider-independent. Add typed benchmark evidence, verified bait classification, advisory boundary refinement, capability-aware provider snapshots, and cached setup/GPU state. Keep cloud use explicit.

**Tech Stack:** Python pipeline, React/TypeScript UI, Rust/Tauri bridge, Vitest, pytest, Rust tests, Playwright/axe, GitHub Actions.

**Spec:** `docs/qa/v0.5.16-audit-ledger.md` and the referenced v0.5.16 product-quality request.

## Global Constraints

- `v0.5.15` remains immutable.
- Do not commit copyrighted benchmark media.
- Preserve local-first behavior.
- Never apply model bait without transcript verification.
- Never silently send media to cloud providers.
- Never silently switch requested models on resumed jobs.
- Do not lower recommendation quality thresholds to force output.
- Every production change requires a failing regression test first.

### Task 1: Candidate-quality benchmark and instrumentation

**Files:** `pipeline/clipgauge_pipeline/candidates/*`, `pipeline/tests/test_story_units.py`, new deterministic benchmark fixtures and `docs/qa/v0.5.16-benchmark.md`.

- [x] Add human-annotation metadata schema.
- [x] Add deterministic recall, precision, NDCG, boundary, diversity, and bait metrics.
- [x] Add broad proposal instrumentation with rejection reasons.
- [x] Add fixture tests for dense multi-story sources.
- [x] Add story-boundary recovery tests.

Owner annotations remain an external qualification gate.

### Task 2: Verified engagement-bait scoring

**Files:** `pipeline/clipgauge_pipeline/scoring/rubric.py`, `pipeline/clipgauge_pipeline/scoring/stage.py`, `pipeline/tests/test_rubric.py`, `pipeline/tests/test_scoring_resilience.py`.

- [x] Add transcript occurrence and viewer-directed phrase verification.
- [x] Preserve model, verified, and rejected bait records.
- [x] Apply penalties only to verified bait.
- [x] Add false-positive regression fixtures.

### Task 3: Provider models and reproducible snapshots

**Files:** `pipeline/clipgauge_pipeline/scoring/providers.py`, `config.py`, `jobs/*`, Rust command bridge, `app/src/components/ProviderCenter.tsx`, `app/src/types.ts`, tests.

- [x] Return typed model capabilities and provider errors.
- [x] Add bounded model-list cache and manual refresh.
- [x] Expose model selection in normal provider panels.
- [x] Persist provider, requested model, actual model, and capability snapshot.
- [x] Add PRIVATE, BALANCED, and BEST QUALITY modes.
- [x] Surface provider-model and endpoint persistence failures.
- [x] Surface provider-setting read failures.
- [x] Normalize malformed provider model-list entries safely.
- [x] Validate malformed provider model-list payloads across adapters.
- [x] Write inference caches atomically.
- [x] Write diarization embedding caches atomically.
- [x] Write Instagram connection output atomically.
- [x] Write downloaded overlay images atomically.
- [x] Write Instagram thumbnail images atomically.
- [x] Validate malformed overlay-provider responses safely.
- [x] Validate malformed clip-edit sidecars safely.
- [x] Validate malformed job settings snapshots safely.
- [x] Validate malformed native review results safely.
- [x] Validate malformed Instagram overview data safely.
- [x] Validate malformed editor context data safely.
- [x] Ignore stale overlapping Loop overview refreshes.
- [x] Clean failed temporary persistence writes.
- [x] Ignore stale overlapping onboarding inventory refreshes.
- [x] Validate native setup and health response shapes.

### Task 4: Setup, GPU, YouTube, and storage state

**Files:** `app/src-tauri/src/setup_inventory.rs`, Rust diagnostics, `SetupCenter.tsx`, `setupState.ts`, `displayDiagnostics.ts`, `api.ts`, and tests.

- [x] Add versioned inventory cache with metadata-based reuse.
- [x] Return cached state immediately, then refresh in background.
- [x] Cache optional GPU and YouTube diagnostics.
- [x] Keep event extraction on CPU after managed CUDA activation failure.
- [x] Add prominent healthy/low/critical disk states.
- [x] Make cleanup explicit and session-picker based.
- [x] Validate cached Setup inventory and diagnostics shapes.
- [x] Validate nested cached diagnostic arrays and readiness actions.
- [x] Validate nested cached inventory rows before rendering.

### Task 5: UI, async, accessibility, and regression states

**Files:** all React screens/styles, tests, packaged screenshot helpers, CI workflows.

- [x] Audit async effects for cancellation and stale writes.
- [x] Rebuild provider and setup hierarchy.
- [x] Add axe coverage for onboarding, provider, navigation, about, support, privacy, review, create, Instagram dialog, and Integrations surfaces.
- [x] Add keyboard-accessible mobile navigation coverage.
- [x] Add programmatic-label regressions for Pexels and Instagram credentials.
- [x] Surface local model persistence failures with bounded recovery guidance.
- [x] Consume best-effort runtime telemetry failures safely.
- [x] Keep Other-moment preview failures inside Review.
- [x] Validate cached application setup-state flags.
- [ ] Complete remaining focus, screen-reader, and packaged visual-state coverage.
- [ ] Capture required packaged visual states.
- [x] Run available local functional and security gates.

Viewport, packaged visual, and full packaged Rust gates remain unverified.

### Task 6: Qualification and release

- [ ] Run owner benchmark source without committing media.
- [ ] Run complete local and configured cloud comparison; Groq attempts are quota-limited.
- [ ] Build and retest public Windows installer over v0.5.15 state.
- [x] Update version surfaces and changelog.
- [ ] Open one exact-head PR.
- [ ] Merge, tag, publish, and verify v0.5.16.
