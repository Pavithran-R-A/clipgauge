# ClipGauge v0.5.17 Real-Device Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize ClipGauge on real Windows laptops, repair YouTube partial installs, restore completed-result loading, and remove UX contradictions without changing v0.5.16.

**Architecture:** Keep managed runtime ownership in Python. Keep cross-language result validation strict and backward-compatible. Keep lifecycle state explicit across Python, Rust, and React. Keep release metadata changes last.

**Tech Stack:** Python, pytest, TypeScript, React, Vitest, Rust, Cargo, Tauri, managed FFmpeg, WhisperX, Node, bgutil, yt-dlp.

**Spec:** User-provided ClipGauge v0.5.17 real-device stabilization brief.

## Global Constraints

- [ ] Work only on `feat/v0.5.17-real-device-stabilization`.
- [ ] Preserve v0.5.16 tag, release, and commit.
- [ ] Investigate each failure before editing.
- [ ] Add failing regressions before implementation fixes.
- [ ] Keep secrets, cookies, and private paths out.
- [ ] Do not bump release version early.
- [ ] Do not merge, tag, or release.

## Tasks

### 1. Establish failure fixtures and evidence

- [ ] Inspect current ASR, YouTube, results, and lifecycle paths.
- [ ] Capture current test commands and baseline failures.
- [ ] Add production-shaped fixtures where missing.
- [ ] Record exact failure codes and substeps.

### 2. Repair ClipGauge-owned ASR audio loading

**Files:** `pipeline/clipgauge_pipeline/asr/stage.py`, new focused ASR loader module if needed, `pipeline/tests/test_asr_fallback.py`, new ASR qualification tests.

- [ ] Add a failing clean-PATH regression first.
- [ ] Prove current WhisperX path decode failure.
- [ ] Implement bounded stdlib WAV validation and decoding.
- [ ] Require PCM, mono, 16 kHz, 16-bit, nonempty audio.
- [ ] Return float32 samples within `[-1, 1]`.
- [ ] Raise typed malformed or truncated errors.
- [ ] Remove normalized-WAV `whisperx.load_audio` calls.
- [ ] Keep absolute managed FFmpeg fallback only.
- [ ] Preserve CPU policy and resource retry behavior.
- [ ] Qualify full packaged CPU AsrStage execution.
- [ ] Keep CUDA transcription and alignment coverage.

### 3. Repair partial YouTube installations

**Files:** `pipeline/clipgauge_pipeline/ingest/youtube_compat.py`, `pipeline/tests/test_v053_setup_readiness.py`, related runtime-manifest and inventory surfaces.

- [ ] Add failing partial-directory regressions first.
- [ ] Define complete node, source, plugin, and build checks.
- [ ] Rebuild incomplete managed components only.
- [ ] Preserve valid verified archives.
- [ ] Use atomic extraction and copying.
- [ ] Install locked dependencies with sanitized diagnostics.
- [ ] Verify server build and plugin discovery.
- [ ] Start provider and verify loopback health.
- [ ] Make false-success states impossible.
- [ ] Map required typed YouTube error codes.
- [ ] Run repair twice for idempotence.

### 4. Pin and qualify bgutil provider 2.0.0

**Files:** YouTube compatibility module, runtime manifest or inventory surfaces, provider tests, focused provenance documentation.

- [ ] Update provider version to `2.0.0`.
- [ ] Pin source URL, SHA, layout, and plugin.
- [ ] Adapt server command behavior if required.
- [ ] Verify version through loopback health.
- [ ] Verify IPv4 and IPv6 loopback behavior.
- [ ] Reject LAN binding and hidden cookie access.
- [ ] Preserve explicit browser-cookie opt-in boundaries.

### 5. Restore result-loading contract compatibility

**Files:** `pipeline/clipgauge_pipeline/scoring`, `pipeline/clipgauge_pipeline` result writers, `app/src/jobResultsValidation.ts`, `app/src/jobResultsValidation.test.ts`, `app/src-tauri/src/artifact.rs` tests, cross-language fixtures.

- [ ] Add failing `bait_verification` contract test first.
- [ ] Include human-readable reasons in new adjustments.
- [ ] Normalize known v0.5.16 records safely.
- [ ] Keep strict validation for unknown malformed records.
- [ ] Exercise real Python score checkpoints.
- [ ] Exercise actual Rust artifact serialization.
- [ ] Exercise TypeScript validation and Review mount.
- [ ] Cover all requested adjustment variants.
- [ ] Cover clips and no-recommendation outcomes.

### 6. Restrict Review retry behavior

**Files:** `app/src/App.tsx`, Review components, API tests.

- [ ] Add failing completed-result load recovery test.
- [ ] Show created-clips recovery copy.
- [ ] Retry only `job_results`.
- [ ] Preserve the existing session.
- [ ] Never rerun ASR, scoring, or rendering.

### 7. Fix terminal elapsed-time lifecycle

**Files:** `app/src/components/Studio.tsx`, App state, relevant tests.

- [ ] Add failing terminal elapsed regression first.
- [ ] Freeze final elapsed on success.
- [ ] Freeze final elapsed on failure.
- [ ] Freeze final elapsed on cancellation.
- [ ] Keep live elapsed while processing.

### 8. Fix stale runtime-update messaging

**Files:** `app/src/App.tsx`, `app/src/components/Studio.tsx`, runtime state helpers, tests.

- [ ] Add failing stale-warning regression first.
- [ ] Clear warning after runtime initialization.
- [ ] Keep lifecycle ownership explicit.
- [ ] Optionally show v0.5.17 update confirmation.

### 9. Clarify AI and scoring modes

**Files:** `app/src/components/Studio.tsx`, provider state/types, provenance path, component tests.

- [ ] Add failing contradiction tests first.
- [ ] Describe Private/Local as ClipGauge Local.
- [ ] Offer Lightweight and Balanced local choices.
- [ ] Require configured cloud provider for Hybrid.
- [ ] Require configured provider and model for Best Quality.
- [ ] Disable unavailable cloud modes with guidance.
- [ ] Show provider and model before creation.
- [ ] Persist exact provider/model provenance.

### 10. Complete qualification and documentation

- [ ] Run requested R01–R07 regression matrix.
- [ ] Add explicit R08 QA records without private paths.
- [ ] Run security gates for R09 boundaries.
- [ ] Verify Python, frontend, Rust, and full builds.
- [ ] Bump every release surface only now.
- [ ] Update CHANGELOG, README, and focused notes.
- [ ] Keep physical laptop testing deferred.
- [ ] Record remaining real-device gates honestly.
- [ ] Verify v0.5.16 immutability again.
- [ ] Report candidate commit SHA only.

## Verification Commands

- `uv run pytest pipeline/tests -q`
- `npm test -- --run`
- `cargo test --manifest-path app/src-tauri/Cargo.toml`
- Frontend build and typecheck commands from `app/package.json`.
- Full release-adjacent checks without publishing.

## Completion Criteria

- [ ] All acceptance items pass or remain explicitly deferred.
- [ ] No v0.5.16 object changes.
- [ ] No v0.5.17 tag or release exists.
- [ ] Candidate SHA and residual device gates are reported.
