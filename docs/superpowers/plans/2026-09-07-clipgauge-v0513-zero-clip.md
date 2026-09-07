# ClipGauge v0.5.13 Zero-Clip Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ClipGauge distinguish valid zero-recommendation analysis from pipeline failure, preserve finalist contracts through camera and render, and qualify v0.5.13 through real Windows acceptance.

**Architecture:** Keep v0.5.12 immutable. Add explicit domain outcomes, stage dependency fingerprints, and safe diagnostics around the existing Python pipeline. Preserve the current recommendation bar unless evidence proves a language-neutral scoring defect; add deterministic camera fallbacks and typed contract errors so valid clips cannot disappear silently.

**Tech Stack:** Python 3.12, pytest, React/Vite, TypeScript, Tauri/Rust, FFmpeg, SQLite, GitHub Actions, Windows installer.

**Spec:** `C:\Users\Pavithran R A\.codex\attachments\36bd41cc-0a4a-455d-aa1b-b764861f549d\pasted-text.txt`

## Global Constraints

- v0.5.12 commit `90b5b12d6554dc21b25b055aa87e98fc8594d658` and tag remain immutable.
- Never delete `C:\Users\Pavithran R A\.clipgauge`.
- No silent `continue` when finalist camera data is required.
- Zero recommendations are successful analysis, never `INTERNAL_ERROR`.
- Rendered clips require valid MP4, H.264 video, audio, duration, and 9:16 output.
- Diagnostics contain sanitized counts only, never transcripts or private media.
- Every production change follows a failing test first.

## Evidence Baseline

- Real job: `20260907-181848-1eea09`.
- Diagnostic: `diag-440e476c68084179`.
- Candidates: `5` generated and `5` scored.
- Score finalists: `0`; GOOD: `0`; STRONG: `0`.
- Borderline candidates: `5`, all marked `STRONG_RECOMMENDATION_REQUIRED`.
- Camera trajectories: `0`, because score clips were empty.
- Render attempts: `0`; outputs: `0`.
- CPU recovery completed ASR through score.
- Final failure was generic render failure.

## File Map

- Modify `pipeline/clipgauge_pipeline/scoring/short_quality.py`: language-neutral deterministic signals and explicit recommendation evidence.
- Modify `pipeline/clipgauge_pipeline/scoring/stage.py`: safe score counts, rejection reasons, and zero-finalist outcome data.
- Modify `pipeline/clipgauge_pipeline/camera/stage.py`: finalist coverage and static-center fallback provenance.
- Modify `pipeline/clipgauge_pipeline/render/stage.py`: typed camera contract errors and zero-finalist skip behavior.
- Modify `pipeline/clipgauge_pipeline/jobs/queue.py`: dependency fingerprints and terminal outcome handling.
- Modify `pipeline/clipgauge_pipeline/protocol.py`: typed success/failure protocol codes and sanitized diagnostics.
- Modify `pipeline/clipgauge_pipeline/cli.py`: terminal result mapping and result summaries.
- Modify `app/src/types.ts` and affected UI components: permanent outcome types and zero-recommendation copy.
- Add focused Python tests under `pipeline/tests/` for scoring, camera, render, recovery, diagnostics, and paths with spaces.
- Add frontend tests beside affected React components.
- Modify production model E2E and Windows qualification scripts to require clips for known-good media.
- Bump version files only after all gates pass.

### Task 1: Capture the real-job root cause

**Files:**
- Create: `docs/forensics/clipgauge-v0512-zero-clip.md`
- Test: no production test; read-only evidence capture.

- [ ] Record the stage ledger from the preserved job.
- [ ] Record checkpoint schemas, database statuses, counts, devices, and recovery order.
- [ ] Record that candidates were valid but all five remained borderline.
- [ ] Record that camera and render received zero finalists.
- [ ] Record the current generic error and required replacement behavior.

### Task 2: Add typed domain outcomes

**Files:**
- Modify: `pipeline/clipgauge_pipeline/protocol.py`
- Modify: `pipeline/clipgauge_pipeline/cli.py`
- Modify: `pipeline/clipgauge_pipeline/jobs/queue.py`
- Modify: `app/src/types.ts`
- Test: `pipeline/tests/test_terminal_outcomes.py`
- Test: affected frontend terminal/result tests.

- [ ] Write failing tests for `SUCCESS_WITH_CLIPS`, `SUCCESS_NO_RECOMMENDATIONS`, and `FAILED`.
- [ ] Add typed result fields: `outcome`, `code`, `message`, `counts`, and optional `best_candidate`.
- [ ] Return `NO_RECOMMENDED_CLIPS` after valid scoring with zero finalists.
- [ ] Skip camera and render for that terminal analytical outcome.
- [ ] Ensure zero recommendations never set the job to failed.
- [ ] Render the required user message and evaluated-count summary.

### Task 3: Preserve scoring evidence and audit language assumptions

**Files:**
- Modify: `pipeline/clipgauge_pipeline/scoring/short_quality.py`
- Modify: `pipeline/clipgauge_pipeline/scoring/stage.py`
- Test: `pipeline/tests/test_short_quality.py`
- Test: `pipeline/tests/test_non_english_scoring.py`

- [ ] Write failing Tamil and punctuation-neutral regression tests.
- [ ] Separate unsupported-language signals from English-only heuristics.
- [ ] Treat aligned segment boundaries and semantic closure as valid ending evidence.
- [ ] Prevent missing English keywords from automatic candidate rejection.
- [ ] Preserve strict recommendation thresholds unless a test proves false rejection.
- [ ] Store per-candidate rejection reason counts and best-candidate evidence.
- [ ] Verify malformed local-model judgments degrade safely and visibly.

### Task 4: Enforce score-to-camera contracts

**Files:**
- Modify: `pipeline/clipgauge_pipeline/camera/stage.py`
- Modify: `pipeline/clipgauge_pipeline/render/stage.py`
- Test: `pipeline/tests/test_camera_render_contract.py`

- [ ] Write failing tests for complete and incomplete trajectory maps.
- [ ] Require one trajectory or documented fallback per finalist.
- [ ] Raise `CAMERA_TRAJECTORY_MISSING` with expected, available, and missing indexes.
- [ ] Add deterministic `static_center` trajectories when tracking has no usable frames.
- [ ] Record `camera_mode` as tracking, `static_center`, or `safe_fit`.
- [ ] Render with a safe 9:16 center crop when smart tracking fails.
- [ ] Keep camera failures distinct from empty recommendation outcomes.

### Task 5: Add checkpoint dependency fingerprints

**Files:**
- Modify: `pipeline/clipgauge_pipeline/jobs/queue.py`
- Modify: `pipeline/clipgauge_pipeline/jobs/artifacts.py`
- Modify: stage modules that consume prior checkpoints.
- Test: `pipeline/tests/test_checkpoint_dependencies.py`

- [ ] Write failing tests for CPU-recovery reuse and stale downstream invalidation.
- [ ] Fingerprint source identity, settings identity, producer version, and upstream fingerprints.
- [ ] Include execution mode where output semantics depend on device or fallback.
- [ ] Reuse ASR only when its source and relevant settings match.
- [ ] Invalidate dependent events, candidates, score, camera, and render checkpoints when upstream identity changes.
- [ ] Preserve valid expensive checkpoints after GPU-to-CPU recovery.
- [ ] Keep paths and job IDs safe when profile directories contain spaces.

### Task 6: Improve sanitized zero-output diagnostics

**Files:**
- Modify: `pipeline/clipgauge_pipeline/protocol.py`
- Modify: `pipeline/clipgauge_pipeline/scoring/stage.py`
- Modify: `pipeline/clipgauge_pipeline/camera/stage.py`
- Modify: `pipeline/clipgauge_pipeline/render/stage.py`
- Test: `pipeline/tests/test_zero_output_diagnostics.py`

- [ ] Write failing diagnostic assertions for all required counts.
- [ ] Emit candidate, eligible, score, trajectory, attempt, and output counts.
- [ ] Emit bounded rejection reason counts.
- [ ] Exclude transcripts, media paths, and private source contents.
- [ ] Include the diagnostic ID in terminal events.
- [ ] Preserve typed camera contract context without leaking sensitive data.

### Task 7: Complete frontend review and export behavior

**Files:**
- Modify: `app/src/types.ts`
- Modify: affected files under `app/src/components/`.
- Test: frontend component tests for review, export, restart, and zero recommendations.

- [ ] Write failing tests for terminal outcome rendering.
- [ ] Show evaluated count and safe best-candidate details.
- [ ] Offer broader selection only when product policy allows it.
- [ ] Keep review and export available for real outputs.
- [ ] Reopen completed sessions after restart without stale empty state.

### Task 8: Add known-good model-backed and artifact tests

**Files:**
- Modify: production model E2E workflow and test fixtures.
- Modify: Windows qualification script.
- Test: `pipeline/tests/test_render_artifacts.py` and model-backed E2E.

- [ ] Write failing assertion requiring `render.outputs.length >= 1` for known-good media.
- [ ] Verify physical MP4 existence, H.264 stream, audio stream, duration, and 9:16 dimensions.
- [ ] Verify captions and Tamil Unicode when the fixture includes Tamil.
- [ ] Verify review playback and export paths.
- [ ] Verify restart and completed-session reopening.
- [ ] Verify preserved failed-job resume and fresh same-source run.

### Task 9: Run all local and platform gates

- [ ] Run Python full suite and coverage.
- [ ] Run frontend full suite and production build.
- [ ] Run Rust full suite, `cargo fmt`, and strict clippy.
- [ ] Run version consistency, secret scan, npm audit, Python dependency audit, and cargo audit.
- [ ] Run Linux, macOS arm64, macOS x86_64, and Windows qualification.
- [ ] Record every gate as passed, failed, blocked, or unverified.

### Task 10: Release only after real acceptance

- [ ] Bump all versions to `0.5.13`.
- [ ] Build candidate Windows installer.
- [ ] Install over v0.5.12 without deleting the real profile.
- [ ] Complete the real-device journey through review, export, close, reopen, and playback.
- [ ] Create the PR and wait for exact-SHA green checks.
- [ ] Merge only after all required gates pass.
- [ ] Create immutable annotated tag `v0.5.13`.
- [ ] Run release workflow and verify public assets and `SHA256SUMS`.
- [ ] Download the public installer and repeat real-device acceptance.
- [ ] Report COMPLETE only when a known-good video yields a playable/exportable clip.

## Completion Report Contract

The final report must include the original diagnostic, root cause, every required count, typed zero-recommendation result, Tamil scoring result, CPU recovery result, review/export/restart results, test counts, candidate/public installer results, merge SHA, tag, workflow, and public release. Any missing real-device or public-installer gate is BLOCKED.
