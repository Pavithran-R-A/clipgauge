# ClipGauge v0.5.18 Post-Release Defect Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the known v0.5.17 project-owned defects and prepare one green, narrowly scoped v0.5.18 stabilization PR without touching v0.5.17 history.

**Architecture:** Establish one typed provider execution/readiness contract shared by Creator, Provider Center, and Python preflight. Keep Provider Center inspection state separate from committed Creator state. Harden managed YouTube repair and loopback verification, bound owned-WAV ASR memory, and isolate asynchronous result/timing/notice state by job attempt.

**Tech Stack:** React/TypeScript, Vitest, Python 3.10+, pytest, FastAPI/Tauri command contracts, Rust/Tauri, uv, npm, cargo, GitHub Actions.

**Spec:** `C:/Users/Pavithran R A/.codex/attachments/c0038169-76ee-45ab-81b1-d5cf7e8e61c8/pasted-text.txt`

## Global Constraints

- Do not modify v0.5.17, historical tags, or historical releases.
- Do not weaken quality thresholds or remove security/VEX/advisory records.
- Keep bgutil at 2.0.0 or a later explicitly reviewed safe version.
- Bind managed provider services to loopback only: `127.0.0.1` and `::1`.
- Preserve the v0.5.17 owned normalized-WAV ASR path; do not restore PATH/system FFmpeg decoding.
- Preserve user data and existing `.clipgauge` content; use isolated temporary fixtures for repair tests.
- Do not merge, tag, or publish v0.5.18 in this task.

---

### Task 1: Establish executable baseline and regression map

**Files:**
- Create: `docs/qa/v0.5.18-post-release-defect-closure.md`
- Modify: none during baseline capture
- Test: existing `app/src/*.test.tsx`, `app/src/*.test.ts`, and `pipeline/tests/test_*.py`

**Interfaces:**
- Consumes: `origin/main` at `64d4224e7837ba2bbeb9d76c77c0db23c2c92915`.
- Produces: branch-local baseline record and a finding-to-test map.

- [ ] **Step 1: Verify the immutable baseline**

Run:

```powershell
git fetch origin --prune
git rev-parse origin/main
git show-ref --dereference refs/tags/v0.5.17
gh release view v0.5.17 --repo Pavithran-R-A/clipgauge --json tagName,isDraft,isPrerelease,assets
git status --short --branch
```

Expected: main remains `64d4224e7837ba2bbeb9d76c77c0db23c2c92915`, v0.5.17 remains annotated and public, and the worktree is clean before implementation.

- [ ] **Step 2: Inventory existing implementation and test seams**

Inspect these exact boundaries before editing:

```powershell
rg -n "qualityMode|selectedProvider|activeId|onSelectProvider|runJob|preflight|readiness" app/src pipeline/clipgauge_pipeline
rg -n "public_compatibility|youtube-status|youtube-test|bgutil|_source_install_ready" pipeline app/src
rg -n "jobResults|resultsLoadJobId|runStartedAt|runNotice|terminal|result" app/src/App.tsx app/src/*.test.tsx
```

- [ ] **Step 3: Record the current version and baseline evidence**

Record current `0.5.17` surfaces, the clean branch name, the baseline SHA, the untouched release URL, and the known Windows installer digest in the QA report.

---

### Task 2: Add the canonical provider execution and readiness contract

**Files:**
- Create or modify: `app/src/providerContract.ts`
- Modify: `app/src/types.ts`, `app/src/api.ts`, `app/src/components/Studio.tsx`, `app/src/components/ProviderCenter.tsx`, `app/src/App.tsx`
- Modify: `pipeline/clipgauge_pipeline/readiness.py`, `pipeline/clipgauge_pipeline/preflight.py`, `pipeline/clipgauge_pipeline/scoring/providers.py`
- Test: `app/src/providerContract.test.ts`, `app/src/App.test.tsx`, `app/src/components/ProviderCenter.test.tsx`, `app/src/v050InformationArchitecture.test.tsx`, `pipeline/tests/test_preflight.py`, `pipeline/tests/test_providers.py`

**Interfaces:**
- Produces `ProviderExecution = { provider, model, locality, qualityMode }`.
- Produces `ProviderReadiness = { provider, locality, configured, credential_ready, endpoint_ready, model_ready, model_available, model_compatible, can_private, can_hybrid, can_best, blocking_reasons, warnings }`.
- `resolveProviderExecution(provider, qualityMode, model)` returns the actual provider/model sent to preflight and run.
- `evaluateProviderReadiness(config)` is the shared decision source for Creator, Provider Center, and preflight.

- [ ] **Step 1: Write failing routing tests**

Assert actual `api.preflight` and `api.runJob` arguments for ClipGauge Local/Ollama/LM Studio private, Groq private/balanced/best, OpenRouter balanced, and Custom best. Assert that cloud/private is blocked or explicitly switched with visible copy, never silently substituted for another local provider.

- [ ] **Step 2: Run the routing tests and confirm the existing failure**

```powershell
Set-Location app
npm test -- --run src/providerContract.test.ts src/App.test.tsx
```

Expected: Ollama and LM Studio private cases currently resolve to `clipgauge-local`, and the test fails on actual arguments.

- [ ] **Step 3: Implement one provider execution resolver**

Keep local provider identity intact for private mode. Require a capable configured cloud provider for balanced/best. Preserve OpenRouter Auto Free. Represent locality from the provider definition, not from quality mode.

- [ ] **Step 4: Implement typed readiness in Python and TypeScript**

Require runtime/model readiness for ClipGauge Local, endpoint/service/model readiness for Ollama and LM Studio, credential/model/capability readiness for cloud providers, and endpoint/model/auth readiness for Custom and Cloudflare. Return blocking reasons such as `Choose a model`, `Enter endpoint`, and `Test/start Ollama`.

- [ ] **Step 5: Verify the routing and readiness tests**

```powershell
Set-Location app
npm test -- --run src/providerContract.test.ts src/App.test.tsx src/components/ProviderCenter.test.tsx
Set-Location ..\pipeline
uv run pytest tests/test_preflight.py tests/test_providers.py -q
```

---

### Task 3: Separate Provider Center browsing from committed selection

**Files:**
- Modify: `app/src/components/ProviderCenter.tsx`, `app/src/App.tsx`, `app/src/setupState.ts`
- Test: `app/src/components/ProviderCenter.test.tsx`, `app/src/v050InformationArchitecture.test.tsx`, `app/src/App.test.tsx`

**Interfaces:**
- `activeId` is inspection-only.
- `selectedProvider` is the committed Creator provider.
- `commitProviderSelection()` is the only Provider Center path that calls `onSelectProvider`.

- [ ] **Step 1: Add failing browse/commit tests**

Cover browse-then-back, browse-then-test-then-back, browse-then-save-then-back, browse-then-use, several cards then commit-last, selectedProvider prop updates, and independent local model persistence.

- [ ] **Step 2: Remove selection callback from card browsing**

Card click changes only `activeId`. Credential saves, model refreshes, endpoint edits, and connection tests must not call `onSelectProvider`.

- [ ] **Step 3: Keep committed selection visibly distinct**

Show `selectedProvider === provider.id` as the committed marker. Keep the detail heading as the inspected provider. Commit active provider only from `Use for next clip`.

- [ ] **Step 4: Verify Provider Center regressions**

```powershell
Set-Location app
npm test -- --run src/components/ProviderCenter.test.tsx src/v050InformationArchitecture.test.tsx src/App.test.tsx
```

---

### Task 4: Make YouTube status truthful and repair integrity complete

**Files:**
- Modify: `pipeline/clipgauge_pipeline/ingest/youtube_compat.py`, `pipeline/clipgauge_pipeline/setup_models.py`, `pipeline/clipgauge_pipeline/cli.py`, `app/src/types.ts`, `app/src/components/SetupCenter.tsx`, `app/src/setupInventoryCache.ts`
- Test: `pipeline/tests/test_v053_provider_lifecycle.py`, `pipeline/tests/test_v053_setup_readiness.py`, new focused YouTube repair tests, `app/src/components/SetupCenter.test.tsx`, `app/src/setupInventoryCache.test.ts`

**Interfaces:**
- Readiness records independent `dependency_checked_at`, `provider_self_tested_at`, and `public_transfer_verified_at` values.
- `_source_install_ready()` validates the pinned archive’s complete required input manifest.
- Repair returns typed state and does not touch unmanaged user files.

- [ ] **Step 1: Add failing timestamp and cache tests**

Prove readiness refresh and local self-test do not update public transfer time. Prove successful real transfer records it. Prove provider-version mismatch invalidates old verification while failures retain a clearly stale historical timestamp.

- [ ] **Step 2: Add failing partial-install integrity tests**

Cover missing `tsconfig`, missing source entrypoint, malformed package manifest, partial plugin, zero-byte plugin, missing node/npm, missing/zero-byte build, missing node_modules, stale 1.3.2 tree, interrupted staging/backup, archive missing/hash mismatch, build timeout/npm/compiler failures, wrong listener, occupied unrelated port, healthy v2.0.0 listener, repair twice.

- [ ] **Step 3: Implement schema-versioned status fields**

Migrate old cache records safely. Never map local checks or self-tests into public transfer verification.

- [ ] **Step 4: Implement complete managed-tree readiness and atomic repair**

Validate every pinned build input, reacquire bad archives through the verified downloader, repair dependencies, build in staging, validate outputs, atomically swap managed trees, remove only ClipGauge-owned interrupted staging/backup paths, and run loopback/plugin discovery before returning ready.

- [ ] **Step 5: Update Setup copy and verify all repair tests**

Display Tools installed, Provider self-test, and Public YouTube transfer separately. Keep wording best-effort.

---

### Task 5: Verify bgutil loopback behavior against the real 2.0.0 process

**Files:**
- Modify if required: `pipeline/clipgauge_pipeline/ingest/youtube_compat.py`, provider launch helpers, and focused tests
- Test: `pipeline/tests/test_v053_provider_lifecycle.py`, a temporary real-process qualification script under `scripts/`

**Interfaces:**
- Launch arguments must match bgutil 2.0.0’s actual CLI contract.
- Qualification records IPv4, IPv6 behavior, returned version, listener addresses, clean stop, and repeated restart.

- [ ] **Step 1: Inspect pinned bgutil package/source and current launcher**

Verify the host argument syntax and current process health endpoint from the pinned 2.0.0 source or package.

- [ ] **Step 2: Add failing command-contract assertions if syntax is wrong**

Assert no `0.0.0.0` or LAN bind appears and that both loopback forms are handled deliberately.

- [ ] **Step 3: Run the real isolated process qualification**

Use a temporary ClipGauge runtime directory, check IPv4 and IPv6 separately, inspect listeners, stop cleanly, and start/stop/start again. Record unavailable IPv6 behavior without treating it as an IPv4 failure.

- [ ] **Step 4: Verify Windows dual-stack CI coverage**

Keep the platform-specific listener assertions in the repository’s Windows workflow and record the job ID in the QA report.

---

### Task 6: Bound owned-WAV ASR memory and preserve CPU/CUDA semantics

**Files:**
- Modify: `pipeline/clipgauge_pipeline/asr/audio.py`, `pipeline/clipgauge_pipeline/asr/stage.py`, `pipeline/clipgauge_pipeline/asr/probe.py`, `app/src/App.tsx`
- Test: `pipeline/tests/test_asr_audio.py`, `pipeline/tests/test_asr_fallback.py`, new long-form memory contract tests

**Interfaces:**
- Owned-WAV loader returns the existing transcription-compatible array or a typed `ASR_RESOURCE_LIMIT`/`WAV_TOO_LARGE` failure.
- No path invokes `whisperx.load_audio()` for production owned-WAV input.

- [ ] **Step 1: Add failing loader edge-case tests**

Cover tiny/normal/malformed/truncated/wrong-channel/wrong-rate/wrong-bit-depth/zero-frame/oversized-declared-frame/long synthetic WAV and CPU fallback behavior.

- [ ] **Step 2: Measure current duplicate allocations**

Use a bounded synthetic WAV and allocation instrumentation to document the byte buffer plus float array behavior before changing it.

- [ ] **Step 3: Implement bounded loading**

Choose the compatible architecture after tracing Faster-Whisper/WhisperX input requirements. Avoid uncontrolled duplicate full-audio allocations. Preserve int8, low-memory, batch1, CUDA, and alignment fallback behavior.

- [ ] **Step 4: Add typed user-facing resource mapping**

Map typed resource failures to an explicit memory/audio-size message, never `could not read audio`.

- [ ] **Step 5: Verify ASR tests and CPU qualification**

Run genuine CPU/int8/low-memory/batch1 ASR with the normalized owned WAV and record transcript/alignment results.

---

### Task 7: Generalize result normalization and isolate Review-load races

**Files:**
- Modify: `app/src/jobResultsValidation.ts`, `app/src/App.tsx`, `app/src/types.ts`
- Test: `app/src/jobResultsValidation.test.ts`, `app/src/App.test.tsx`, `app/src/components/Review.test.tsx`

**Interfaces:**
- `normalizeJobResults(value)` returns a new normalized object or `null`; it never mutates input.
- `loadResults(jobId, diagnosticId)` uses a request identity and applies results only to the active job/request.

- [ ] **Step 1: Build the historical result fixture matrix**

Include v0.5.16 results, current results, factor/bonus adjustments, missing bait reason, numeric/string story values, `SUCCESS_NO_RECOMMENDATIONS`, and successful rendered output.

- [ ] **Step 2: Add failing normalization and race tests**

Cover terminal job A versus job B, late Sessions responses, multiple Review retries, unmounted App, preserved job/diagnostic IDs, retry-only `jobResults`, and no `runJob`/`resumeJob` calls.

- [ ] **Step 3: Implement immutable normalization and request cancellation/identity**

Keep unknown safe metadata, reject malformed unsafe shapes, and gate every async result application by request ID, active job ID, and mounted state.

- [ ] **Step 4: Verify Review recovery tests**

```powershell
Set-Location app
npm test -- --run src/jobResultsValidation.test.ts src/App.test.tsx src/components/Review.test.tsx
```

---

### Task 8: Correct elapsed state and notice lifecycles

**Files:**
- Modify: `app/src/App.tsx`, `app/src/creatorState.ts`, `app/src/components/Studio.tsx`
- Test: `app/src/App.test.tsx`, `app/src/creatorState.test.ts`, `app/src/components/Studio.test.tsx`

**Interfaces:**
- Attempt lifecycle has one start timestamp and one terminal frozen elapsed value.
- Notice state is scoped to setup operation, job attempt, and provider qualification.

- [ ] **Step 1: Add state-transition tests**

Cover IDLE, preflight-blocked, RUNNING, success, failure, cancellation, resume, Review retry, new job, and job switch.

- [ ] **Step 2: Remove the duplicate post-preflight timer reset**

Decide and document whether preflight time counts. Apply the policy consistently. Keep terminal elapsed frozen during result loading and Review retry.

- [ ] **Step 3: Add notice scope tokens**

Clear stale notices at new job boundaries and provider switches. Preserve useful current warnings. Ensure successful repair refreshes readiness and removes obsolete repair warnings.

- [ ] **Step 4: Verify timing and notice regressions**

```powershell
Set-Location app
npm test -- --run src/App.test.tsx src/creatorState.test.ts src/components/Studio.test.tsx
```

---

### Task 9: Improve focused Creator/Setup UI semantics and cache efficiency

**Files:**
- Modify: `app/src/components/Studio.tsx`, `app/src/components/ProviderCenter.tsx`, `app/src/components/SetupCenter.tsx`, `app/src/setupInventoryCache.ts`, `app/src/setupLifecycle.ts`, `app/src/types.ts`
- Test: `app/src/components/Studio.test.tsx`, `app/src/components/ProviderCenter.test.tsx`, `app/src/components/SetupCenter.test.tsx`, `app/src/setupInventoryCache.test.ts`, `app/src/setupLifecycle.test.ts`, `app/src/accessibility.test.tsx`

**Interfaces:**
- Creator summary derives from `ProviderExecution`, showing mode, actual provider, exact model, locality, and data-disclosure copy.
- Cache identity separates core inventory, GPU diagnostics, YouTube dependencies, and public transfer verification.

- [ ] **Step 1: Add failing UI and invocation-count tests**

Cover friendly labels, exact model IDs, no duplicate current dropdown option, blocked models, keyboard/focus/aria states, Cloudflare endpoint requirement, provider/model persistence, and repeated Setup open behavior.

- [ ] **Step 2: Render actual execution summary**

Use the same resolver arguments sent to preflight/run. Do not display ClipGauge Local when Ollama or LM Studio is selected.

- [ ] **Step 3: Implement separate cache TTL and identity rules**

Recent valid cache avoids expensive checks; version/runtime manifest mismatch invalidates relevant sections; explicit Refresh bypasses cache; repair invalidates affected sections; public transfer remains independent.

- [ ] **Step 4: Run focused accessibility and cache tests**

```powershell
Set-Location app
npm test -- --run src/components/Studio.test.tsx src/components/ProviderCenter.test.tsx src/components/SetupCenter.test.tsx src/setupInventoryCache.test.ts src/setupLifecycle.test.ts src/accessibility.test.tsx
```

---

### Task 10: Update active documentation and version surfaces

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `app/package.json`, `app/package-lock.json`, `app/src-tauri/Cargo.toml`, `app/src-tauri/Cargo.lock`, `app/src-tauri/tauri.conf.json`, `pipeline/pyproject.toml`, active QA/version fixtures
- Create: `docs/qa/v0.5.18-post-release-defect-closure.md`
- Leave unchanged: historical v0.4 documents and v0.5.17 release records

**Interfaces:**
- Every active version surface reads `0.5.18`.
- README fallback says “Fallback if the current release has issues” and retains v0.5.3/local-media guidance.

- [ ] **Step 1: Add the stabilization changelog entry**

Describe defect closure, not feature expansion. Preserve historical entries.

- [ ] **Step 2: Update active version surfaces consistently**

Run the existing version consistency script and update About UI/current release metadata.

- [ ] **Step 3: Record every R01-R15 disposition**

For each finding include symptom, root cause, files, fix, regression, qualification evidence, and final disposition. Add R16+ only for reproducible adjacent defects.

- [ ] **Step 4: Document release immutability support status**

Record whether project policy makes tags immutable and whether GitHub immutable-release settings are enabled, disabled, or unavailable. Do not change repository settings.

---

### Task 11: Run full qualification, review, and prepare the PR

**Files:**
- Modify: all tracked implementation/tests/docs from Tasks 2-10
- Test: repository-defined Python, frontend, Rust, accessibility, build, packaging, audit, and secret-scan commands

**Interfaces:**
- Produces: one commit and one pushed branch/PR only after all local gates pass.

- [ ] **Step 1: Run full local gates**

Run repository commands for full pytest, frontend tests/typecheck/lint/build/accessibility, cargo test/fmt/strict Clippy, npm audit, cargo audit, Python VEX audit, gitleaks, version consistency, and packaging.

- [ ] **Step 2: Run real qualification**

Run CPU ASR, stable public YouTube transfer without cookies, and genuine Ollama/LM Studio qualification only when installed. Build packaged Windows, verify upgrade from v0.5.17, data/model reuse, local pipeline Review, playback/export, restart/session reopen, and cache behavior.

- [ ] **Step 3: Perform bounded touched-subsystem review**

Search for duplicated state, stale promises, provider substitution, cache timestamp misuse, partial-tree checks, non-atomic swaps, whole-file allocations, terminal mutation, and retry recomputation.

- [ ] **Step 4: Update QA evidence and inspect staged files**

Confirm no generated runtime/model/download artifacts are staged. Record exact test totals, skips, workflow IDs, and unavailable physical-device checks.

- [ ] **Step 5: Commit and push the stabilization branch**

```powershell
git add app pipeline scripts README.md CHANGELOG.md docs/qa docs/superpowers/plans
git diff --cached --check
git commit -m "fix: close ClipGauge v0.5.18 post-release defects"
git push -u origin fix/v0.5.18-post-release-defect-closure
```

- [ ] **Step 6: Open one narrow PR and stop after checks are green**

Use title `fix: close ClipGauge v0.5.18 post-release defects`. Include all Rxx findings, totals, real qualification, VEX status, deferred physical i5 qualification, and explicit v0.5.17 immutability. Do not merge, tag, or publish.

---

## Self-review coverage

- Provider routing, browse/commit state, readiness, UI truth, and preflight are covered by Tasks 2, 3, and 9.
- YouTube timestamps, cache identity, partial repair, atomicity, bgutil loopback, and public transfer are covered by Tasks 4 and 5.
- ASR bounded memory and typed failures are covered by Task 6.
- Result compatibility, Review races, timing, and notices are covered by Tasks 7 and 8.
- Documentation, immutability notes, QA evidence, full gates, and PR boundaries are covered by Tasks 10 and 11.
- No historical release or advisory record is modified.
