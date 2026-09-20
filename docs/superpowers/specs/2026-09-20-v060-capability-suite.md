# ClipGauge v0.6.0 Capability Suite

## Baseline

- Repository: `Pavithran-R-A/clipgauge`.
- Immutable baseline: `v0.5.22` peeled commit `17197ee631db4a941786a3209e2d44fb51204635`.
- Feature branch: `feat/v060-capability-suite`.
- The `v0.5.22` tag remains immutable.

## Current architecture

ClipGauge uses a React and TypeScript desktop UI, a Tauri/Rust shell, and a
Python pipeline. The Python runner owns the SQLite job store and atomic JSON
stage checkpoints. Existing stages are ingest, ASR, diarization, audio
events, candidate synthesis, scoring, camera trajectories, and rendering.
Managed runtimes, model inventories, provider profiles, OS credential storage,
resource guards, URL policy, filesystem confinement, and redacted diagnostics
remain authoritative.

The existing multimodal candidate engine remains unchanged in purpose. It
continues to use transcript, speakers, scene changes, audio events, dynamics,
arousal, and heatmap evidence. No LLM-generated timestamps replace candidate
synthesis.

## Capability design

### Versioned input manifest

Each new job stores `input.json` in its job directory. The manifest has
`schema_version: 1`, media source identity, platform classification, and
subtitle selection state. Accepted external subtitles are copied into the job
directory and hashed. Resume never reads the original external path.

The subtitle contract records `mode`, `requested_path` only transiently,
`artifact_path`, format, language, source, SHA-256, and automatic status. It
never stores credentials, cookies, or provider secrets.

### Transcript fast path

SRT and WebVTT parsers accept bounded UTF-8 text, handle BOMs, reject binary
or unusable files, validate timestamps, clamp cues to media duration, and
normalize overlap deterministically. They preserve Unicode and safely remove
presentation markup. Cue-only word timings use explicit interpolation
provenance. Accepted subtitles produce the existing segment and word shape.

Source priority is explicit user subtitle, human platform subtitle, automatic
platform caption, then existing ASR. A valid subtitle skips only the
transcription model. Diarization, events, candidates, scoring, camera, and
rendering still run.

### Platform ingest

A single classifier recognizes local files, YouTube, Bilibili video URLs, and
unsupported URLs. Bilibili uses the already managed and verified yt-dlp
runtime, single-video and no-playlist behavior, and existing URL/download
security. Platform caption selection records language, human versus automatic
status, platform, and extractor identity. Live Bilibili qualification remains
manual and is never represented by mocked tests.

### Content categories

Settings gain `content_category`, defaulting to `auto`. Legacy settings map to
`auto` or `general` semantics without changing existing scoring behavior.
Bounded category guidance affects model interpretation only. It cannot invent
evidence, bypass thresholds, or alter measured signals. The CLI and UI expose
validated category choices.

### Enrichment

An `enrich` stage follows scoring. It receives only bounded finalist evidence
and creates title and short description metadata through the authorized
scoring provider. It is independently cacheable. Every finalist receives a
usable title through deterministic fallbacks. Enrichment errors are recorded
as warnings and never remove score finalists.

### Collections

An optional `collections` stage proposes zero or more validated collections
from scored finalists. Manual collection service operations use atomic writes
and preserve user edits. Collection compilation is on demand and consumes
verified rendered clips. It never replaces original clips or reruns analysis.

### MCP

`clipgauge mcp` exposes stdio tools over the real persistent job system. It
does not create a second registry or pipeline. Arguments select provider
profiles and never accept secrets. Logs go to stderr or protocol
notifications, keeping stdout valid MCP.

### Headless API

`clipgauge serve` starts a thin FastAPI layer over persistent jobs. It binds to
loopback by default, uses concurrency one, denies CORS by default, and requires
an explicit token for non-loopback binding. Job bodies select existing
provider profiles and cannot carry secrets or arbitrary host paths.

### Docker

`Dockerfile.headless` packages the Python pipeline, CLI, FastAPI service, and
FFmpeg without Tauri. The container uses `/data/.clipgauge`, a non-root user
where practical, explicit readiness, and no startup model download. The image
does not claim GPU support.

## Target pipeline and dependencies

The target order is:

`ingest -> asr -> diarize -> events -> candidates -> score -> enrich -> collections -> camera -> render`.

`enrich` and `collections` are soft-fail stages. Their failure preserves valid
score finalists and allows camera and render to continue. Camera consumes score
finalists, with enrichment and collections treated as metadata inputs only.
Collection rendering is an on-demand operation after individual clip output.

Dependency fingerprints include input manifest, subtitle hash, category, and
upstream outputs. Subtitle changes invalidate ASR through render where
semantics depend on transcript or finalist identity. Category changes start at
score. Title edits and collection ordering do not rerun analysis. Caption
preset changes retain existing rerender behavior.

## Database and migration plan

The `jobs` table receives an additive nullable `input_json` column after a
`PRAGMA table_info(jobs)` check. Existing databases remain open without
deleting `db.sqlite3`. Existing jobs without a manifest use the existing ASR
path. New collection data uses a versioned job-local JSON artifact initially,
with atomic writes, avoiding a replacement job store.

Settings move from schema version 4 to 5 by adding `content_category` with
default `auto`. Protocol version remains 2 unless an implementation requires
a strictly additive versioned field; native consumers remain tolerant. Old
checkpoints and result payloads remain readable through optional-stage
normalization.

## Privacy and security impact

External subtitle text is source-derived content. Private mode keeps it local.
Balanced and best modes may send only bounded candidate excerpts under the
existing provider contract. Raw subtitle contents, source paths, credentials,
cookies, and tokens are excluded from JSONL, diagnostics, support bundles,
MCP arguments, and ordinary server requests. Existing URL restrictions,
redirect policy, archive safety, hashes, resource guards, low-disk gates,
cancellation, resume, and locality guarantees remain enforced.

The headless API is loopback-first. Non-loopback use requires an explicit
token and configured import roots or uploads. CORS is explicit allowlist only.

## Migration and rollback

Migration is additive and idempotent. A failed feature stage leaves its
checkpoint absent or marked failed while score data remains usable. Rollback
means stopping at a prior branch commit; existing v0.5.22 jobs remain readable
because new fields are optional and new stages are optional. No rollback moves
or rewrites the published `v0.5.22` tag.

## Release-gate impact

Version consistency changes to v0.6.0 only after implementation acceptance.
Existing Python, frontend, Rust, audit, secret, visual, and model-backed E2E
gates remain mandatory. New gates cover subtitle E2E, mocked Bilibili
contracts, MCP stdio integration, FastAPI integration, Docker health, migration
fixtures, collection ffprobe verification, and privacy leakage inspection.
Real Bilibili qualification is reported separately when unavailable.

## AutoClip reference and rejected concepts

Reference concepts are subtitle fast paths, category-oriented editorial hints,
title enrichment, collections, MCP access, headless serving, and container
distribution. AutoClip's MIT license permits independent implementation; no
nontrivial source is copied in this design.

Explicitly rejected are AutoClip's transcript-to-outline pipeline, LLM-created
timestamps, duplicate task managers, Redis, Celery, browser-cookie harvesting,
playlist expansion, DRM bypass, arbitrary public server exposure, wildcard
CORS, hidden model downloads, hard-coded keyword collections, and threshold
weakening.

## Open environment-dependent validation

- Real public Bilibili ingest and caption qualification.
- Public YouTube caption availability across representative videos.
- Native desktop qualification for subtitle and collection UX.
- Docker runtime qualification on the supported CI host.
- Cloud provider behavior under each configured release profile.
