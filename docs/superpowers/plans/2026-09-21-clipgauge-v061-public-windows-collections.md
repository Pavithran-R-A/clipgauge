# ClipGauge v0.6.1 Public Windows Collections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair legacy collection identity, real collection rendering, creator-sidecar errors, and Windows upgrade metadata for v0.6.1.

**Architecture:** Python assembles one canonical creator-clip list from score, enrich, and render checkpoints. Rust normalizes UI-facing score identities with the same deterministic algorithm. React consumes enriched clips first and reports typed render failures. NSIS postinstall uses its generated uninstall context.

**Tech Stack:** Python, pytest, React, Vitest, Rust, Cargo, Tauri, NSIS, GitHub Actions.

**Spec:** The attached v0.6.1 post-release patch request.

## Global Constraints

- Do not modify, replace, or retag v0.6.0.
- Do not replace v0.6.0 release assets.
- Do not broaden scope beyond collection, registry, docs, and version fixes.
- Preserve current v0.6 clip IDs exactly.
- Keep all managed paths inside job-owned directories.
- Do not expose secrets, transcripts, cookies, or source media.
- Do not merge, tag, or publish v0.6.1.

## Review Focus

- Legacy score-only jobs: deterministic IDs must survive reload.
- Enriched jobs with custom IDs: existing IDs must remain unchanged.
- Render outputs with duplicate or unsafe paths: reject ambiguous data.
- Sidecar success without a path: show a visible failure.
- In-place NSIS upgrades: one active entry must report 0.6.1.

### Task 1: Capture defect forensics

**Files:**
- Create: `docs/forensics/clipgauge-v060-public-windows-collections.md`

- [ ] **Step 1: Record the public installer evidence.**

  Record the v0.6.0 URL, size, SHA256, upgrade path, app version, preserved counts, and the single stale HKCU uninstall entry. Exclude private data.

- [ ] **Step 2: Record affected checkpoint evidence.**

  Record job `20260918-170408-e53b27`, `score.json` present with six clips and no IDs, `enrich.json` absent, `render.json` present with six indexed `clips/clip_00.mp4` through `clip_05.mp4` outputs, and `collections.json` with two persisted IDs and null render path.

- [ ] **Step 3: Record the root-cause boundary.**

  State that the job is pre-v0.6.0 lineage: artifact manifests identify producer version 0.5.21, while no exact app-version field exists. State that no data loss occurred and the original collection name/order were restored.

### Task 2: Canonical creator-clip assembly

**Files:**
- Modify: `pipeline/clipgauge_pipeline/creator_state.py`
- Modify: `pipeline/clipgauge_pipeline/cli.py`
- Modify: `pipeline/clipgauge_pipeline/collections/render.py`
- Test: `pipeline/tests/test_creator_state.py`
- Test: `pipeline/tests/test_collections.py`

**Interfaces:**
- Produces: `creator_clips_for_job(job) -> list[dict[str, Any]]`.
- Consumes: `clip_id_for(clip, index)` and render checkpoint `outputs[].clip/path`.

- [ ] **Step 1: Add failing score-only identity tests.**

  Add a production-shaped fixture with score clips, render outputs, and no enrich checkpoint. Assert `creator_clips_for_job` returns stable IDs, managed render paths, and the same IDs after repeated loads.

- [ ] **Step 2: Run the focused tests.**

  Run `pytest pipeline/tests/test_creator_state.py -q`. Expect failure because the canonical helper does not exist.

- [ ] **Step 3: Implement canonical assembly.**

  Merge score and enrich by stable finalist order, preserve existing IDs, assign `clip_id_for` only when missing, merge render outputs by exact `clip_id` first, otherwise by the explicit persisted `clip` index, and accept only existing files under `job.dir/clips`.

- [ ] **Step 4: Route all creator operations through it.**

  Replace `_creator_clips` with `creator_clips_for_job`. Make collection rendering map IDs through `clip_id_for`, not a second identity algorithm.

- [ ] **Step 5: Add realistic CLI render integration coverage.**

  Use score-only and enriched checkpoint fixtures without manually injecting `render_path`. Invoke `main(["collections", "render", job.id, collection_id])`; assert a non-empty output, persisted collection path, source preservation, and temporary-list cleanup. Stub FFmpeg only at the process boundary.

- [ ] **Step 6: Run Python focused tests.**

  Run `pytest pipeline/tests/test_creator_state.py pipeline/tests/test_collections.py -q`. Expect all focused tests to pass.

### Task 3: Rust job-results identity normalization

**Files:**
- Modify: `app/src-tauri/src/artifact.rs`

- [ ] **Step 1: Add failing Rust fixture tests.**

  Add score-only and enriched fixtures. Assert score clips receive canonical IDs, enriched IDs are preserved exactly, and render outputs remain available.

- [ ] **Step 2: Run the Rust artifact tests.**

  Run `cargo test --manifest-path app/src-tauri/Cargo.toml artifact::tests`. Expect failure for score-only identity assertions.

- [ ] **Step 3: Implement the canonical Rust mirror.**

  Use SHA-256 over `index:start:.3:end:.3`, matching Python `stable_clip_id`, while preserving any existing `clip_id`. Normalize score clips before title overrides and merge enriched metadata by finalist order.

- [ ] **Step 4: Run the Rust artifact tests again.**

  Run `cargo test --manifest-path app/src-tauri/Cargo.toml artifact::tests`. Expect all artifact tests to pass.

### Task 4: Typed creator-sidecar render failures

**Files:**
- Modify: `app/src-tauri/src/main.rs`
- Test: `app/src-tauri/src/main.rs`

- [ ] **Step 1: Add failing response-contract tests.**

  Test `{ok:false}` rejection, bounded error text, `{ok:true}` missing-path rejection for collection rendering, and valid managed path acceptance.

- [ ] **Step 2: Run the focused Rust tests.**

  Run `cargo test --manifest-path app/src-tauri/Cargo.toml main::tests`. Expect failure because current JSON handling returns `{ok:false}` as success.

- [ ] **Step 3: Harden the sidecar boundary.**

  Reject typed failures, redact and bound safe errors, require a non-empty render path, and validate returned collection paths under the managed job collections directory.

- [ ] **Step 4: Run the focused Rust tests again.**

  Run `cargo test --manifest-path app/src-tauri/Cargo.toml main::tests`. Expect all response-contract tests to pass.

### Task 5: Frontend creator fallback and error surface

**Files:**
- Modify: `app/src/components/Review.tsx`
- Modify: `app/src/components/Review.test.tsx`

- [ ] **Step 1: Add failing legacy fallback tests.**

  Render a score-only result with stable IDs and no enrich data. Assert create and add dialogs show every finalist. Add render-response tests for missing paths and typed failures.

- [ ] **Step 2: Run the focused frontend tests.**

  Run `pnpm --dir app exec vitest run src/components/Review.test.tsx`. Expect failure for the legacy chooser and missing-path error assertions.

- [ ] **Step 3: Implement frontend behavior.**

  Prefer non-empty enrich clips, otherwise normalized score clips. Require a returned render path before updating local state. Surface safe visible errors and clear busy state on all outcomes.

- [ ] **Step 4: Run the focused frontend tests again.**

  Run `pnpm --dir app exec vitest run src/components/Review.test.tsx`. Expect all focused tests to pass.

### Task 6: Windows registry correction and release preparation

**Files:**
- Modify: `app/src-tauri/windows/hooks.nsh`
- Modify: `app/src-tauri/Cargo.toml`
- Modify: `app/src-tauri/tauri.conf.json`
- Modify: `app/package.json`
- Modify: `app/package-lock.json`
- Modify: `pipeline/pyproject.toml`
- Modify: `pipeline/uv.lock`
- Modify: `pipeline/clipgauge_pipeline/__init__.py`
- Modify: `app/src/components/About.tsx`
- Modify: `app/src/components/SetupCenter.tsx`
- Modify: `app/src/setupInventoryCache.ts`
- Modify: `scripts/check-version-consistency.py`
- Modify: `CHANGELOG.md`
- Modify: `INSTALL.md`
- Test: version and installer checks

- [ ] **Step 1: Add the NSIS upgrade regression.**

  Add a controlled Windows qualification path that installs v0.5.22, upgrades a locally built v0.6.1, and checks executable metadata, the active NSIS uninstall key, install location, uninstall string, and duplicate count.

- [ ] **Step 2: Implement the smallest registry correction.**

  Add a postinstall hook using `${UNINSTKEY}` and `SHCTX`, never a hard-coded hive, to rewrite the active ClipGauge `DisplayVersion` from `${VERSION}` and preserve generated install metadata.

- [ ] **Step 3: Bump authoritative current-version sources.**

  Update current version files to 0.6.1. Preserve historical v0.6.0 references in release evidence and historical notes. Update the version consistency script and About copy.

- [ ] **Step 4: Correct installation documentation.**

  Make INSTALL.md describe v0.6.0 as current public stable and v0.6.1 as the patch under preparation. Add the v0.6.1 changelog entry and retain historical references.

- [ ] **Step 5: Run version checks.**

  Run `python scripts/check-version-consistency.py`. Expect PASS for 0.6.1.

### Task 7: Full verification, candidate qualification, and PR

**Files:**
- Modify: `.github/workflows/windows-qualification.yml` if required by the controlled regression.
- Create: patch evidence under `docs/qa/` only if existing workflow requires it.

- [ ] **Step 1: Run Python full gates.**

  Run the repository Python suite and dependency audit under current policy.

- [ ] **Step 2: Run frontend full gates.**

  Run frontend tests, typecheck, lint, and production build.

- [ ] **Step 3: Run Rust full gates.**

  Run `cargo fmt -- --check`, `cargo test`, and `cargo clippy -- -D warnings`.

- [ ] **Step 4: Run security gates.**

  Run npm audit, Python/environment audit, cargo audit under VEX policy, and secret scan.

- [ ] **Step 5: Build a local v0.6.1 Windows candidate.**

  Do not publish. Upgrade the current public v0.6.0 installation in place, preserve all existing data, and exercise chooser, manual collection lifecycle, collection render playback, title rerender, reset, and registry behavior.

- [ ] **Step 6: Review the complete diff.**

  Confirm no v0.6.0 tags, assets, release files, or unrelated product areas changed.

- [ ] **Step 7: Open the focused PR.**

  Push `fix/v061-public-windows-collections` and open `fix: repair v0.6 public Windows collections`. Require exact-head CI, Secret Scan, Windows, and macOS checks. Do not merge.
