# ClipGauge A-to-Z Repository Inventory

**Inventory basis:** Fresh `git ls-files` on the QA branch at baseline `69051be8d8cd6dc269608a30aaff3de4cfddc1b6`. The repository contains **234 tracked files**. The complete path list, topology, command searches, network search, secret/vault search, persistence search, and module lists are preserved under `/home/ubuntu/clipgauge-stage0/az-verification/evidence/` for the audit bundle.

## Repository structure

| Area | Fresh inventory evidence | Primary responsibility |
|---|---|---|
| React/TypeScript UI | `app/src`, `app/package.json`, `app/vite.config.ts`, `app/src/components` | Studio, onboarding, review, clip editing, provider setup, privacy activity, loop/Instagram views, key/about modals |
| Tauri/Rust bridge | `app/src-tauri/src` and `app/src-tauri/Cargo.toml` | Window commands, process control, vault boundaries, diagnostics, job lifecycle, artifact safety, exports, native packaging |
| Python pipeline | `pipeline/clipgauge_pipeline` | Ingest, ASR, alignment, diarization, audio events, scene/candidate generation, scoring, captions, rendering, jobs, integrations |
| Provider architecture | `pipeline/clipgauge_pipeline/scoring/providers.py`, `scoring/llm.py`, config/preflight/CLI, Rust provider vault | Normalized profiles, capability negotiation, adapters, model listing, auth, retries/errors, cache isolation, privacy and migration |
| Models/runtime | `models/`, `runtime.py`, `models/registry.py`, `models/specs.py`, `vendor/` | Model registry, runtime preparation, optional local weights and vendored model implementations |
| FFmpeg | `render/ffmpeg_bin.py`, `render/renderer.py`, `scripts/prepare-resources.mjs`, packaging workflows | Binary discovery, resource preparation, media rendering, qualification packaging |
| yt-dlp/ingest | `ingest/ytdlp.py`, `ingest/normalize.py`, `ingest/stage.py` | YouTube/URL acquisition, normalization, local media staging, privacy boundary |
| ASR/alignment | `asr/`, `align/` | Speech recognition and word/segment alignment |
| Diarization | `diarize/`, `vendor/campplus/` | Speaker segmentation and CAM++-based support |
| Audio events | `audio/`, `vendor/panns/`, `vendor/laughter/` | Audio event detection, laughter, PANNs labels, channel handling |
| Scene/candidate generation | `scenes/`, `candidates/` | Scene boundaries, highlight candidate generation and ranking inputs |
| Scoring | `scoring/frames.py`, `scoring/rubric.py`, `scoring/stage.py`, providers | Frame selection, rubric scoring, capability-aware LLM calls, degradation handling |
| Camera/reframing | `camera/`, `vendor/clippyme/` | Cut/pan/locked modes, reframing and crop operations |
| Captions | `captions/` | Caption presets, transcript styling, subtitle rendering inputs |
| Rendering/exports | `render/`, `jobs/artifacts.py`, `artifact.rs`, export commands | Clip render checkpoints, artifact allowlisting, final exports and validation |
| Editor | `edits/`, `edit_schema.rs`, `ClipEditor.tsx` | Per-clip context, visuals, edits, render requests and validation |
| Provider settings | `config.py`, `preflight.py`, `providers.py`, `Studio.tsx`, `Onboarding.tsx` | Provider-neutral setup, model/endpoint/auth selection, readiness, privacy display |
| Credential vault | `secrets.rs`, `diagnostics.rs`, save/get provider commands | OS-backed secrets, operation-scoped injection, redaction and support safety |
| Migrations | `config.py`, job/cache/config compatibility paths | v0.1.x Gemini/Ollama migration, non-destructive settings compatibility |
| Job scheduler | `jobs/queue.py`, `process_manager.rs`, `main.rs` | Job creation, leases, duplicate detection, cancellation, stale recovery, subprocesses |
| Cancellation/resume | `cancel_job`, `resume_job`, queue/process manager, checkpoint files | Safe cancellation, resume from checkpoints, stale lease reconciliation |
| Privacy | `privacy_summary`, provider profiles, activity view, docs | Local/cloud disclosure, destination/model/media visibility, no default telemetry |
| Diagnostics/support bundles | `diagnostics.rs`, `generate_support_bundle`, CLI support paths | Bounded logs, redaction, support export, secret and private-data exclusions |
| Pexels | `edits/visuals.py`, `KeyModal.tsx`, `providers`/visual sources | Optional visual search and asset suggestions; credential-gated |
| Instagram/Meta | `insights/instagram.py`, `IgModal.tsx`, `Loop.tsx`, CLI `ig` | OAuth against user’s own Meta app, media/link/metrics/calibration loop |
| CI | `.github/workflows/ci.yml`, `macos.yml`, `windows.yml`, `secret-scan.yml`, provider smoke | Deterministic checks, native qualification, secret scanning, optional live provider tests |
| Release workflows | `.github/workflows/release.yml`, metadata scripts | Exact-tag package builds, SBOM, checksums, provenance, draft-first release |
| Packaging | Tauri config, resource preparation, Linux/Windows/macOS workflow jobs | Debian, NSIS, unsigned macOS qualification artifacts |
| Documentation | README, INSTALL, TROUBLESHOOTING, CHANGELOG, docs/provider and v0.2 docs | User setup, limitations, architecture, research, QA, security, provenance |
| Licensing/notices | `LICENSE`, `NOTICE.md`, `ORIGIN.md`, `THIRD_PARTY_NOTICES.md`, vendored licenses | AGPL-3.0-or-later, derivative attribution, third-party inventory and exclusions |

## Public/user-facing feature surface

The desktop UI exposes first-run onboarding, local/cloud/custom provider setup, model and endpoint selection, credential save/test controls, preflight readiness, local video or YouTube source selection, provider-aware processing, progress stages, cancellation, resume, job history, review, per-clip editor, caption presets, camera modes, visual suggestions, clip rendering/export, privacy activity, support-bundle generation, About/license/provenance information, Pexels setup, and Instagram/Meta feedback-loop screens.

The command-line surface exposes the following commands and nested commands. The `preflight`, `provider-test`, and `run` commands support explicit provider/model/endpoint/auth arguments while preserving legacy Gemini/Ollama compatibility.

| Command | Public operations |
|---|---|
| `clipgauge preflight` | Runtime/provider readiness check |
| `clipgauge provider-test` | Provider connection/model test and optional hidden vision smoke |
| `clipgauge run SOURCE` | Process a YouTube URL or local video, with captions/camera/provider options |
| `clipgauge resume JOB_ID` | Resume a checkpointed job |
| `clipgauge jobs` | List jobs |
| `clipgauge edit context JOB CLIP` | Retrieve per-clip context |
| `clipgauge edit suggest-visuals JOB CLIP` | Suggest visuals with Pexels/Gemini preference |
| `clipgauge edit render-clip JOB CLIP` | Render a clip edit |
| `clipgauge ig connect` | OAuth against the user’s own Meta app |
| `clipgauge ig sync` | Sync media, thumbnails, insights, and auto-fit |
| `clipgauge ig overview` | Return Loop-screen data |
| `clipgauge ig media` | List recent Reels |
| `clipgauge ig link/unlink/reject` | Manage clip-to-Reel links and rejection pairs |
| `clipgauge ig pull` | Fetch metrics for linked clips |
| `clipgauge ig report` | Score-vs-outcome calibration report |

## Tauri command surface

The Rust bridge has **22 annotated command functions** in `main.rs`, including `privacy_summary`, `generate_support_bundle`, `preflight`, `test_connection`, `run_job`, `resume_job`, `cancel_job`, `job_results`, `list_job_dirs`, `save_gemini_key`, `save_provider_key`, `get_setup_state`, `mark_onboarded`, `check_ollama`, `edit_tool`, `run_edit_render`, `save_clip_edits`, `save_pexels_key`, `ig_status`, `ig_connect`, `ig_tool`, and `export_clip`. The command annotations and surrounding declarations are retained in the fresh evidence file.

## External network destinations

Static search identified provider API families and explicit integration endpoints including Google Gemini, OpenRouter, Groq, Cloudflare Workers AI account-scoped compatible endpoints, Hugging Face router endpoints, Cerebras, Ollama loopback, LM Studio loopback, arbitrary custom OpenAI-compatible endpoints, Pexels, YouTube/yt-dlp sources, and Meta/Instagram endpoints. Each destination is classified in the provider, ingest, Pexels, and Instagram code paths; no default telemetry destination was identified in the current product path. External network behavior remains subject to explicit user/provider selection and credential state.

## Secret types

The inventory identifies Gemini API keys, generic provider bearer/API-key/custom-header values, Ollama/LM Studio/custom endpoint credentials where configured, Pexels keys, Instagram/Meta app IDs and secrets, OAuth access/refresh tokens, and the Rust-managed internal operation secret used to constrain child-process behavior. Secret values are not included in this inventory or evidence bundle; only names and handling paths are recorded.

## Persistent formats and roots

Persistent state includes the `.clipgauge` data root, versioned configuration/provider snapshots, job directories and IDs, checkpoint files, render artifacts, job result JSON, cache entries, logs/diagnostics, support bundles, local model/runtime metadata, and provider/job compatibility fields. Rust path-security and artifact allowlisting protect job-root access; the audit will test malformed, missing, symlinked, Unicode, stale, and cross-job paths.

## Existing test inventory

Fresh tracked-file inventory identifies Python tests under `pipeline/tests`, frontend Vitest files under `app/src`, Rust unit tests under `app/src-tauri/src`, provider contract tests, and CI workflows covering Python, frontend, version consistency, Rust, secret scanning, native macOS, Windows, optional live provider smoke, and release packaging. Exact collected counts and fresh results will be recorded in the final test run and evidence index rather than inferred from prior reports.

## Inventory limitations to resolve in later phases

The inventory identifies all tracked code and declared surfaces. Runtime claims for installed Windows, macOS desktop interaction, local Ollama/LM Studio, live cloud credentials, Instagram OAuth, Pexels, YouTube network behavior, and resource limits remain execution questions. They will be classified explicitly as verified, blocked, failed, or not applicable after the relevant phase; no static inventory claim is treated as a runtime pass.
