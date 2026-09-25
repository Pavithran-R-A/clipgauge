# ClipGauge Post-v0.6.2 Audit Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the confirmed lifecycle, resume, cancellation, import-root, collection, schema, disk-space, and URL-policy defects without changing product version or release history.

**Architecture:** Keep `runtime.json` as the native lifecycle authority, with read-only legacy fallback. Keep managed job artifacts authoritative after ingest, and centralize source-policy validation at shared Python boundaries. Preserve existing checkpoint, resource, path, and atomic-write guards.

**Tech Stack:** Python 3.12, pytest, FastAPI, Rust/Tauri, Cargo tests, Node contract tests, GitHub Actions.

**Spec:** Attached post-v0.6.2 full audit repair request.

## Global Constraints

- Keep product version `0.6.2`.
- Do not modify or recreate `v0.6.2`.
- Do not modify historical tags.
- Do not merge, tag, or release.
- Do not weaken path, resource, or validation guards.
- Push only `fix/v063-repository-audit-closure`.

## Review Focus

- Conflicting native lifecycle files: `runtime.json` wins; test in `main.rs`.
- Deleted original media after ingest: downstream resume uses managed media; test in queue dependencies.
- Cancelled job resumption: marker removal is explicit and active workers reject duplicate resumes; test MCP and FastAPI.
- External subtitle confinement: missing, traversal, symlink escape, and URL-plus-subtitle cases fail before job creation; test server boundaries.
- Schema numeric edge cases: booleans, non-finite numbers, unions, and nested paths remain strict; test providers.

### Task 1: Lifecycle authority and fixture contract

**Files:**
- Modify: `app/src-tauri/src/main.rs`
- Modify: `.github/windows-ui-qualification.ps1`
- Modify: `.github/windows-ui-qualification-capture.test.mjs`
- Test: `app/src-tauri/src/main.rs` unit tests

- [ ] Add a helper that reads `runtime.json` first, then legacy `lifecycle.json` only when runtime is absent or invalidly absent.
- [ ] Make Sessions use that helper and add tests for terminal states, conflict precedence, legacy fallback, and corrupt runtime safety.
- [ ] Seed qualification fixtures with serialized `LeaseRecord` payloads in `runtime.json`.
- [ ] Update fixture contract tests to require runtime state.
- [ ] Run `cargo test` and the related Windows contract tests.

### Task 2: Managed local-source resume

**Files:**
- Modify: `pipeline/clipgauge_pipeline/jobs/queue.py`
- Test: `pipeline/tests/test_checkpoint_dependencies.py`
- Test: `pipeline/tests/test_queue.py`

- [ ] Add a failing downstream-fingerprint test with a valid managed ingest checkpoint and deleted picker source.
- [ ] Keep ingest dependency checks tied to the original source before ingest succeeds.
- [ ] For later stages, fingerprint validated managed media and persisted `source_hash`, never the picker path.
- [ ] Add missing/corrupt managed-media invalidation tests.
- [ ] Run focused queue tests, then the complete Python suite.

### Task 3: Explicit headless resume and cancellation

**Files:**
- Modify: `pipeline/clipgauge_pipeline/jobs/queue.py`
- Modify: `pipeline/clipgauge_pipeline/mcp_server.py`
- Modify: `pipeline/clipgauge_pipeline/server/app.py`
- Modify: `pipeline/clipgauge_pipeline/cli.py`
- Test: `pipeline/tests/test_mcp_server.py`
- Test: `pipeline/tests/test_server.py`
- Test: `pipeline/tests/test_cli.py`

- [ ] Add strict job-ID validation and an atomic marker-removal resume preparation helper.
- [ ] Add MCP `resume_job`, same-job checkpoint reuse, active-worker rejection, invalid-ID rejection, and marker lifecycle tests.
- [ ] Add `POST /v1/jobs/{job_id}/resume` with the same service operation.
- [ ] Keep cancellation stage-boundary based, but store `cancelled` separately from `failed`.
- [ ] Run focused headless tests and CLI resume tests.

### Task 4: Import-root authorization and source policy

**Files:**
- Modify: `pipeline/clipgauge_pipeline/server/app.py`
- Modify: `pipeline/clipgauge_pipeline/ingest/platforms.py`
- Modify: `pipeline/clipgauge_pipeline/ingest/stage.py`
- Modify: `pipeline/clipgauge_pipeline/cli.py`
- Modify: `pipeline/clipgauge_pipeline/mcp_server.py`
- Test: `pipeline/tests/test_server.py`
- Test: `pipeline/tests/test_platform_ingest.py`
- Test: `pipeline/tests/test_external_subtitles.py`

- [ ] Add failing tests for outside subtitle, traversal, symlink escape, malformed URL, and attacker-host URLs.
- [ ] Canonicalize regular local files against configured roots before FastAPI job creation.
- [ ] Reject unsupported URL classes before yt-dlp at CLI, MCP, API, and ingest boundaries.
- [ ] Preserve managed internal subtitle artifacts on resume.
- [ ] Run focused source and subtitle tests.

### Task 5: Collection invalidation and collision-resistant output

**Files:**
- Modify: `pipeline/clipgauge_pipeline/collections/service.py`
- Modify: `pipeline/clipgauge_pipeline/collections/model.py`
- Modify: `pipeline/clipgauge_pipeline/collections/render.py`
- Test: `pipeline/tests/test_collections.py`

- [ ] Add failing tests proving edits clear `render_path` and duplicate/Unicode titles produce different output paths.
- [ ] Clear render state on membership, order, and title mutations.
- [ ] Name new collection outputs with readable slug plus sanitized collection identity.
- [ ] Avoid destructive cleanup of persisted old paths.
- [ ] Run collection tests and verify restart persistence.

### Task 6: Complete JSON-schema validation

**Files:**
- Modify: `pipeline/clipgauge_pipeline/scoring/providers.py`
- Test: `pipeline/tests/test_providers.py`

- [ ] Add failing tests for all requested type, bound, union, enum, array, string, object, boolean, and non-finite cases.
- [ ] Implement path-aware recursive validation without mutating schemas.
- [ ] Reject booleans as integers or numbers.
- [ ] Run provider tests and the Python suite.

### Task 7: Peak additional download-space accounting

**Files:**
- Modify: `pipeline/clipgauge_pipeline/downloads.py`
- Test: `pipeline/tests/test_v040_download_manager.py`

- [ ] Add failing tests showing ready installed bytes must not be counted as free-space demand.
- [ ] Calculate required additional bytes from pending downloads plus explicit operation peak bytes.
- [ ] Preserve installed-byte reporting and archive extraction callers.
- [ ] Run download tests and resource-guard tests.

### Task 8: Cross-file audit and documentation

**Files:**
- Create: `docs/qa/v0.6.3-repository-audit-closure.md`
- Modify: touched files from Tasks 1-7 as required by occurrence audit

- [ ] Re-scan every requested symbol and classify each occurrence.
- [ ] Repair only additional confirmed occurrences caused by the same root issues.
- [ ] Record reproduction, exact repair, focused regression, and remaining risks.
- [ ] Verify no product-version bump or release metadata mutation.

### Task 9: Full verification and PR preparation

**Files:**
- No additional product files.

- [ ] Run Python, frontend, frontend build, Rust test/fmt/clippy, version, and release contracts.
- [ ] Run npm, Python/VEX, Cargo/VEX, and gitleaks audits under existing policy.
- [ ] Review diff and status.
- [ ] Commit with a conventional repair message.
- [ ] Push the same branch and open one PR against main.
- [ ] Wait for exact-head CI, Secret Scan, Windows, macOS, and Docker checks.
- [ ] Report readiness for independent review without merging, tagging, or releasing.
