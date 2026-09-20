# ClipGauge v0.6.0 Capability Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add subtitle-aware ingest, platform captions, Bilibili, categories,
enrichment, collections, MCP, secure headless serving, and Docker while
preserving ClipGauge's multimodal pipeline and v0.5.22 compatibility.

**Architecture:** Extend the existing Python stage runner, SQLite metadata, and
atomic job artifacts. Add thin native interfaces for MCP and FastAPI. Extend
the existing React controls and protocol displays. Keep all provider, runtime,
resource, URL, and filesystem policies centralized.

**Tech Stack:** Python, SQLite, Pydantic-compatible validation already present,
FastAPI optional dependency, stdio MCP boundary, React/TypeScript, Tauri/Rust,
FFmpeg, Docker, pytest, Vitest, Cargo.

**Spec:** `docs/superpowers/specs/2026-09-20-v060-capability-suite.md`

## Execution status

- Tasks 1, 2, 4, 5, 7: implemented and locally verified.
- Task 3: implemented; live Bilibili remains unverified.
- Task 6: implemented; native collection rendering remains unverified.
- Task 8: implemented; optional FastAPI tests pass with the extra installed.
- Task 9: defined; Docker daemon blocked local runtime verification.
- Task 10: desktop tests, build, Rust tests, and Clippy pass. Native UX and
  production model E2E remain open. No tag or release exists.

## Global Constraints

- Never move, delete, recreate, retag, or force-update `v0.5.22`.
- Preserve v0.5.22 databases, jobs, settings schema version 4, and checkpoints.
- Keep ClipGauge multimodal candidate synthesis authoritative.
- Do not add Redis, Celery, hidden downloads, or arbitrary PATH dependencies.
- Never accept or persist secrets in job or server payloads.
- Keep optional enrichment and collections failures soft.
- Bind headless service to loopback by default.
- Use deterministic tests for external services.

## Review Focus

- Malformed and overlapping subtitles must fail safely and deterministically.
- Subtitle changes must invalidate transcript-dependent checkpoints.
- Secrets and raw subtitle text must stay out of diagnostics and protocols.
- Optional stage failures must preserve score finalists and renderability.
- Non-loopback servers must require authentication and deny wildcard CORS.

### Task 1: Baseline contracts and input manifest

**Files:**
- Create: `pipeline/clipgauge_pipeline/ingest/manifest.py`
- Modify: `pipeline/clipgauge_pipeline/jobs/queue.py`
- Modify: `pipeline/clipgauge_pipeline/ingest/stage.py`
- Test: `pipeline/tests/test_input_manifest.py`

**Interfaces:** `Job.input_json`, `create_job(..., input_manifest=None)`,
`load_input_manifest(job)`, and `write_input_manifest(job, manifest)`.

- [ ] Add failing migration tests for absent `jobs.input_json`.
- [ ] Add an idempotent `PRAGMA table_info` migration.
- [ ] Persist canonical `input.json` beside `settings.json`.
- [ ] Preserve legacy jobs with ASR fallback.
- [ ] Verify migration and old-job tests.

### Task 2: Subtitle parsing and ASR fast path

**Files:**
- Create: `pipeline/clipgauge_pipeline/transcripts/formats.py`
- Create: `pipeline/clipgauge_pipeline/transcripts/external.py`
- Create: `pipeline/clipgauge_pipeline/transcripts/timing.py`
- Modify: `pipeline/clipgauge_pipeline/asr/stage.py`
- Test: `pipeline/tests/test_external_subtitles.py`

**Interfaces:** `parse_srt(text, duration)`, `parse_vtt(text, duration)`,
`accept_external_subtitle(source, job, duration)`, and
`normalize_subtitle_transcript(cues, source) -> dict`.

- [ ] Write SRT, VTT, BOM, Unicode, malformed, overlap, and clamp tests.
- [ ] Implement bounded UTF-8 parsing and safe markup normalization.
- [ ] Copy accepted subtitles into the job directory.
- [ ] Add SHA-256 provenance and deterministic word interpolation.
- [ ] Skip only the transcription model when valid.
- [ ] Verify source deletion and ASR-loader bypass tests.

### Task 3: Platform classification, captions, and Bilibili

**Files:**
- Create: `pipeline/clipgauge_pipeline/ingest/platforms.py`
- Modify: `pipeline/clipgauge_pipeline/ingest/stage.py`
- Modify: `pipeline/clipgauge_pipeline/downloads.py`
- Test: `pipeline/tests/test_platform_ingest.py`

**Interfaces:** `classify_source(value)`, `select_platform_caption(tracks)`,
and `BilibiliError(code, message)`.

- [ ] Add classifier tests for YouTube, Bilibili, b23, local, unsupported.
- [ ] Use managed yt-dlp with single-video and no-playlist options.
- [ ] Normalize mocked platform caption responses.
- [ ] Preserve dependency readiness and public-transfer truthfulness.
- [ ] Verify live Bilibili remains separately unverified when unavailable.

### Task 4: Categories and dependency fingerprints

**Files:**
- Create: `pipeline/clipgauge_pipeline/scoring/categories.py`
- Modify: `pipeline/clipgauge_pipeline/config.py`
- Modify: `pipeline/clipgauge_pipeline/jobs/queue.py`
- Modify: `pipeline/clipgauge_pipeline/scoring/stage.py`
- Test: `pipeline/tests/test_categories_and_dependencies.py`

**Interfaces:** `ContentCategory`, `category_profile(category)`, and
`Settings.content_category`.

- [ ] Add invalid-choice and schema-4 migration tests.
- [ ] Implement bounded profiles with `auto` legacy semantics.
- [ ] Inject guidance into existing strict scoring input.
- [ ] Add category and subtitle dependency fingerprints.
- [ ] Verify title and collection changes avoid analysis reruns.

### Task 5: Enrichment and resilient metadata

**Files:**
- Create: `pipeline/clipgauge_pipeline/enrich/stage.py`
- Create: `pipeline/clipgauge_pipeline/enrich/fallbacks.py`
- Modify: `pipeline/clipgauge_pipeline/cli.py`
- Test: `pipeline/tests/test_enrichment.py`

**Interfaces:** `EnrichStage`, `build_fallback_title(clip, index)`, and
`enrich_finalists(finalists, provider) -> dict`.

- [ ] Add malformed, timeout, missing-clip, Unicode, and fallback tests.
- [ ] Call the authorized existing provider with bounded finalist evidence.
- [ ] Enforce title and description limits.
- [ ] Record `title_source` and provider provenance.
- [ ] Mark failures soft and preserve score finalists.

### Task 6: Collections and on-demand compilation

**Files:**
- Create: `pipeline/clipgauge_pipeline/collections/model.py`
- Create: `pipeline/clipgauge_pipeline/collections/service.py`
- Create: `pipeline/clipgauge_pipeline/collections/render.py`
- Modify: `pipeline/clipgauge_pipeline/cli.py`
- Test: `pipeline/tests/test_collections.py`

**Interfaces:** `list_collections`, `create_collection`, `update_collection`,
`reorder_collection`, `delete_collection`, `regenerate_ai_collections`, and
`render_collection`.

- [ ] Test proposal validation and stable clip identity.
- [ ] Add atomic manual operations and edit preservation.
- [ ] Add safe concat lists and ffprobe verification.
- [ ] Keep compilation out of mandatory stage success.
- [ ] Verify historical jobs without collection artifacts.

### Task 7: MCP server boundary

**Files:**
- Create: `pipeline/clipgauge_pipeline/mcp_server.py`
- Modify: `pipeline/clipgauge_pipeline/cli.py`
- Create: `docs/MCP.md`
- Create: `skills/clipgauge/SKILL.md`
- Test: `pipeline/tests/test_mcp_server.py`

**Interfaces:** stdio tools for preflight, providers, jobs, status, results,
cancel, clip render, rerender, and collection operations.

- [ ] Add tool registration and argument-schema tests.
- [ ] Delegate starts and status to persistent job APIs.
- [ ] Reject secret-shaped arguments and unsafe paths.
- [ ] Route logs away from stdout.
- [ ] Verify restart persistence and cancellation.

### Task 8: Secure FastAPI service

**Files:**
- Create: `pipeline/clipgauge_pipeline/server/app.py`
- Create: `pipeline/clipgauge_pipeline/server/auth.py`
- Create: `pipeline/clipgauge_pipeline/server/schemas.py`
- Create: `pipeline/clipgauge_pipeline/server/jobs.py`
- Test: `pipeline/tests/test_server.py`

**Interfaces:** `/v1/health`, `/v1/readiness`, job CRUD/status/results/cancel,
clip render, collection CRUD/render, providers, preflight, and SSE events.

- [ ] Test loopback defaults and health/readiness.
- [ ] Require explicit token for non-loopback binding.
- [ ] Deny wildcard CORS and arbitrary local paths.
- [ ] Add persistent worker and terminal event tests.
- [ ] Verify no secret serialization.

### Task 9: Headless Docker distribution

**Files:**
- Create: `Dockerfile.headless`
- Create: `docker-compose.headless.yml`
- Create: `docs/headless.md`
- Test: `scripts/test-headless-container.ps1`

- [ ] Build the non-root image without secret layers.
- [ ] Mount `/data/.clipgauge` as persistent home.
- [ ] Expose truthful readiness and `/v1/health` healthcheck.
- [ ] Run controlled subtitle-fixture smoke when dependencies permit.
- [ ] Verify clean shutdown and no startup model download.

### Task 10: Desktop integration and release qualification

**Files:**
- Modify: `app/src/components/Studio.tsx`
- Modify: `app/src/components/Review.tsx`
- Modify: `app/src/types.ts`
- Modify: `app/src/api.ts`
- Modify: `pipeline/clipgauge_pipeline/protocol.py`
- Modify: `scripts/validate-model-e2e.py`
- Create: `pipeline/tests/test_v060_e2e.py`
- Create: `docs/qa/v0.6.0-capability-suite-ledger.md`

- [ ] Add subtitle, platform, category, title, and collection controls.
- [ ] Display provenance and soft-failure warnings truthfully.
- [ ] Add external-subtitle synthetic end-to-end qualification.
- [ ] Run Python, frontend, Rust, audits, secret scan, and E2E gates.
- [ ] Record live Bilibili and environment limits explicitly.
- [ ] Change version and tag only after all gates pass.
