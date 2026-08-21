# ClipGauge v0.3.0 Implementation Plan

**Branch:** `feature/v0.3-creator-experience`  
**Baseline:** `de8e8489b083f5cab00a6a9ab69425d810de1bb0`  
**Design specification:** `docs/superpowers/specs/2026-08-21-clipgauge-v0.3-design.md`  
**Target release:** `v0.3.0`  
**Release title:** `ClipGauge v0.3.0 — Creator Experience & Local AI`

This plan is executable. Each workstream names the source files/interfaces, first failing tests, implementation, verification evidence, and planned commit boundary. A requirement is not considered complete because a component exists; it is complete only when its deterministic tests, security tests, and required native acceptance have evidence.

## 1. Delivery sequence and commit boundaries

| Commit | Workstream | Primary outcome | Required gate |
|---|---|---|---|
| `feat: define v0.3 design and implementation contracts` | W0 | Design/spec/plan, research manifest records, acceptance matrix | Docs lint and plan completeness. |
| `fix: make support diagnostics job-scoped and trustworthy` | W1 | Job diagnostics included by requested ID; manifest metadata and exclusions | Rust support-bundle tests and secret/path tests. |
| `fix: add typed speaker failures and resumable recovery` | W2 | Speaker error taxonomy, diagnostic IDs, resume-safe behavior | Python speaker regression and terminal protocol tests. |
| `feat: extend progress protocol for creator-readable status` | W3 | Progress v2, stage timing, ETA/bytes/accelerator fields | Python protocol tests, frontend progress tests, fixture event replay. |
| `feat: add hardware-aware ASR selection` | W4 | Conservative hardware capability service and CPU/GPU selection | Hardware matrix tests and controlled benchmark. |
| `feat: add Setup Center and resumable Download Manager` | W5 | Asset inventory, consent, storage estimate, progress, repair/remove | Download state/integrity tests and UI component tests. |
| `feat: manage FFmpeg yt-dlp and YouTube compatibility` | W6 | Managed FFmpeg/yt-dlp UX, PO-token plugin policy, error taxonomy | Manifest/provenance tests, URL classification tests, Windows test. |
| `feat: add ClipGauge Local provider and runtime lifecycle` | W7 | llama-server manager, local provider, model catalog, offline path | Loopback/process/security tests and real local inference. |
| `feat: redesign creator onboarding and Studio` | W8 | New normal/advanced UX, creator copy, progress surface, privacy | Frontend tests, accessibility checks, packaged screenshots. |
| `feat: establish original ClipGauge visual identity` | W9 | SVG-first mark, tokens, platform icons, brand docs | Asset lint, visual review, attribution scan. |
| `feat: add storage settings diagnostics and release UX` | W10 | Storage/settings/About/platform labels/release link | Frontend/Rust integration tests and packaged UI review. |
| `test: add v0.3 acceptance and security evidence` | W11 | Full deterministic/security/performance/native evidence | All local gates, native CI, Windows acceptance. |
| `release: prepare ClipGauge v0.3.0` | W12 | Version bump, changelog, artifacts, SBOM/provenance | Version consistency and release candidate gates. |
| `docs: publish v0.3 final report and evidence bundle` | W13 | Final report/bundle after post-release verification | ZIP integrity, checksums, no secrets. |

If a workstream uncovers a new project-owned defect, use `CGV3-007+`, add a failing regression test first, then continue the sequence. Do not modify historical tags.

## 2. Contract and test-first matrix

| Requirement cluster | Source files | Interface/data contract | First failing tests | Implementation | Verification/evidence | Commit |
|---|---|---|---|---|---|---|
| Design/history/rebrand | `docs/superpowers/*`, `ORIGIN.md`, `NOTICE.md`, `THIRD_PARTY_NOTICES.md`, `README.md` | Design and plan are authoritative; historical tags immutable; normal UX uses ClipGauge identity | `test_design_plan_covers_all_spec_sections`, legacy-UX inventory test | Add docs, acceptance matrix, and release identity policy | Plan audit, tag SHA checks, legacy search | W0 |
| Support-bundle job diagnostics | `app/src-tauri/src/main.rs`, `path_security.rs`, `diagnostics.rs`; `pipeline/clipgauge_pipeline/protocol.py` | `generate_support_bundle_at(root, job_id)` includes root diagnostics plus only validated `jobs/<job_id>/diagnostics/*.log`; report fields include requested/included IDs | `support_bundle_includes_requested_job_diagnostic`, `support_bundle_excludes_unrelated_job`, `support_bundle_reports_missing_diagnostic` | Add safe job-scoped collector, redaction/tail helper, metadata and explicit missing message | Rust ZIP inspection, traversal, secrets, transcript exclusion | W1 |
| Speaker typed failures | `pipeline/clipgauge_pipeline/diarize/stage.py`, `diarize/campplus.py`, `jobs/queue.py`, `protocol.py` | `StageError.code` uses `SPEAKER_*`; `retryable`, `stage`, and `diagnostic_id` flow into terminal event | Invalid checkpoint/load/download/audio/cluster fixtures; generic exception must fail old assertion | Catch and classify known model/runtime boundaries; preserve checkpoint and resume after ASR | Python tests, controlled corrupt checkpoint, Windows diagnostic | W2 |
| Progress v2 | `protocol.py`, `jobs/queue.py`, Rust JSON-line bridge, `app/src/types.ts`, `App.tsx`, progress components | Event fields: `stage_id`, `display_stage`, `operation`, `fraction`, `indeterminate`, elapsed/ETA/items/bytes/accelerator/one_time_download | JSON-schema/event-shape tests; replay fixture with determinate and indeterminate phases | Extend without breaking legacy fields; stage timers and download events | Protocol replay, frontend event rendering, screenshots | W3 |
| Human stage labels | `Studio.tsx`, progress components, pipeline stage emitters | Internal IDs remain stable; normal labels map to Preparing video, Transcribing speech, Identifying speakers, Understanding audio, Finding strong moments, Scoring clips, Smart reframing, Creating clips | UI text tests reject old normal labels and accept new labels | Central label map and stage-aware status cards | Component tests and packaged screenshot review | W3/W8 |
| Hardware service | New `pipeline/clipgauge_pipeline/hardware.py`; Rust `hardware.rs` or typed bridge; `types.ts` | Snapshot contains OS, CPU, logical cores, RAM, GPU, VRAM, Apple Silicon, Vulkan, CUDA/CTranslate2, disk; unknown remains unknown | Mocked platform/GPU/CUDA/Vulkan matrix and conservative fallback tests | Detect with safe subprocess/OS APIs, bounded output, no name-only inference | Matrix logs, support metadata, Windows observation | W4 |
| ASR accelerator | `asr/stage.py`, `hardware.py`, `jobs/queue.py` | `device`, `compute_type`, `accelerator` recorded in checkpoint; CPU path remains reliable | Existing CPU fixture plus mocked CUDA available/unavailable and unsupported MPS tests | Select supported CTranslate2 backend and compute type; record benchmark | Same-fixture CPU/GPU benchmark, no fabricated universal claim | W4 |
| Runtime manifest | `pipeline/runtime-manifest.json`, `runtime.py`, `preflight.py` | Version/revision/URL/SHA/size/platform/license/provenance for every managed asset | Manifest schema, hash/size mismatch, platform-selection tests | Add llama.cpp release, local model records, PO plugin metadata; validate schema | Manifest audit and SHA verification | W5/W6/W7 |
| Download Manager | `runtime.py`, new `downloads.py`, `preflight.py`, Rust bridge, `types.ts`, setup components | Download event fields: asset ID/name, bytes, fraction, speed, elapsed, ETA, one-time, status, retryable | Resume `.part`, network drop, cancellation, size limit, hash mismatch, atomic replacement, restart-state tests | Reuse verified downloader; add event/state persistence, pause where supported, retry/repair | Python suite, Rust command tests, UI tests, logs | W5 |
| Setup Center | `preflight.py`, new setup UI, `App.tsx`, Rust bridge | Asset inventory with friendly purpose, exact metadata, installed size, required/optional, integrity, source/license/location, actions | Missing FFmpeg/model/yt-dlp/LLM and insufficient disk component tests | Replace coarse warning-only preflight surface with inventory and workflow estimate | UI tests, storage estimate fixture, packaged screenshot | W5 |
| Consent/storage estimate | `preflight.py`, `downloads.py`, setup UI | Estimate derives from selected workflow/manifest/cache/free disk; consent required before substantial download | Cache combinations, free disk boundary, cancel/review/download interaction tests | Calculate real totals, show available disk and one-time reuse, persist opt-in preference only | Deterministic totals and UI evidence | W5 |
| Managed FFmpeg | `render/ffmpeg_bin.py`, `runtime-manifest.json`, setup UI | Install verified Windows archive or use existing; no unexplained manual browser install | Missing managed binary, invalid archive, existing capable binary, caption filter tests | Surface current pinned manifest size/provenance, repair action, safe extraction | Windows installed acceptance and manifest evidence | W6 |
| Managed yt-dlp | `ingest/ytdlp.py`, `runtime-manifest.json`, `downloads.py` | Managed binary preferred over PATH; version/hash displayed; repair action | PATH-vs-managed precedence, hash mismatch, resume/cancel tests | Route all operations through verified managed path and explicit repair | Python tests, Windows Setup Center | W6 |
| YouTube PO-token compatibility | `ingest/ytdlp.py`, new `youtube_policy.py`, manifest, privacy UI | Distinguish public attestation, login-required, private/member/age/region/unavailable; optional plugin consent and provenance | 403 classification fixtures, plugin absent/present, browser-session consent/cookie exclusion tests | Use pinned plugin only after license review; no token minting code; explicit browser session | Official docs citation, public URL Windows test, security scan | W6 |
| Browser cookie safety | `youtube_policy.py`, `protocol.py`, support bundle | Explicit browser/profile consent; cookies scoped to yt-dlp; never stored/logged/bundled | Consent denial, diagnostic redaction, support ZIP exclusion tests | Use short-lived subprocess scope and redact traces | Security regression and Windows privacy evidence | W6 |
| ClipGauge Local provider | `scoring/providers.py`, provider types/tests, `api.ts`, `main.rs` | Provider kind `clipgauge-local`; normalized text/structured/vision capability and offline/privacy metadata | Provider contract, structured output, model missing, runtime unavailable, cache isolation tests | Reuse provider adapter path, add local endpoint identity and capabilities | Mock server plus real local inference | W7 |
| llama-server lifecycle | New `local_runtime.py`, Rust process manager, path security | Start pinned binary with argv, `127.0.0.1`, available port; health check; owned child; shutdown cleanup; no shell | Bind address, random port, path containment, startup timeout, shutdown/orphan tests | Process supervisor with bounded logs and deterministic cleanup | Process-tree evidence, loopback scan, Windows test | W7 |
| Local model catalog | New `local_models.json` or manifest section, Setup Center | Exact display name, underlying model, revision, GGUF source/file, quantization, SHA, sizes, license, capability, RAM/VRAM, context, limitations | Catalog schema, one-model selection, no bulk download, terms gating tests | Add Qwen lightweight/balanced and Gemma vision with exact source metadata; avoid unapproved redistribution | API evidence, manifest checks, UI catalog tests | W7 |
| Local offline path | provider/runtime, privacy, job runner | After runtime+model install, inference needs no cloud/Ollama/LM Studio; URL retrieval remains network-required | Network-disabled local fixture, health/inference, cloud failure isolation | Route all local scoring through loopback server and report precise network activity | Real Windows small model inference, offline evidence | W7 |
| Ollama/LM Studio optional | `preflight.py`, `providers.py`, Settings/Provider components | States Not installed, server stopped, Ready, No compatible model, Error; official install links; never auto-install | Mock discovery/status/model lists and absent-runtime UX tests | Refactor existing checks into provider status cards | Component tests and Windows state observation | W7/W8 |
| Normal/advanced split | `Studio.tsx`, provider/setup components, design tokens | Normal exposes source, AI, captions, Create; Advanced reveals provider/model/endpoint/auth/capabilities/diagnostics | UI query tests reject advanced controls in normal view; reveal/hide tests | Component decomposition and disclosure state | Frontend tests/accessibility review | W8 |
| New onboarding/Studio | `App.tsx`, `Onboarding.tsx`, `Studio.tsx`, features/components, CSS | Copy, actions, drag/drop, caption labels, privacy, progress, errors | User-visible text and keyboard tests | Implement focused feature components, preserve API compatibility | Screenshot set from packaged app | W8 |
| Review/editor/copy | `Review.tsx`, `ClipEditor.tsx`, `Loop.tsx`, styles | Human labels, performance feedback, Advanced scoring details, edit/rerender/export clarity | Legacy-copy search and component text tests | Rewrite normal copy, retain IDs/config compatibility | UI test and installed flow | W8 |
| Design tokens/motion/accessibility | `app/src/design/tokens.css`, `motion.css`, UI components | Contrast, focus, reduced motion, labels, semantic progress, responsive breakpoints | axe-equivalent/static checks, keyboard tests, viewport snapshots | Central tokens and accessible primitives | 1280×720/1366×768/1920×1080 screenshots | W8/W9 |
| Original brand assets | `app/src/assets/brand/*`, icon config, `BRAND.md`, notices | SVG-first mark, platform icons, social assets, originality/provenance record | SVG lint, icon size render, legacy asset search | Generate original SVG and deterministic raster/icon exports | Asset hashes and packaged visual review | W9 |
| About/platform/release UX | `About.tsx`, build metadata, release links | Actual platform and signing state; attribution retained; latest release/download link | Platform label tests and build-target matrix | Replace hard-coded Linux label; build-time platform helper | Native screenshots and CI artifact metadata | W10 |
| Storage settings | New `StorageSettings.tsx`, config/runtime APIs | Sizes and Open folder/Remove unused/Repair with active-job protection | Active job deletion prevention, size computation, repair tests | Add managed-storage inventory and safe actions | Rust/Python/frontend tests | W10 |
| Diagnostics UI | `Diagnostics.tsx`, `main.rs`, protocol | Diagnostic ID and technical details behind disclosure; accurate bundle contents | Support-bundle request/status tests | Surface manifest and missing-diagnostic message | ZIP inspection and screenshot | W1/W10 |
| Release/version/README | all authoritative manifests, `CHANGELOG.md`, `README.md`, `About.tsx` | All sources `0.3.0`; creator-first README with Windows download and screenshots | Version consistency and README link tests | Bump only after RC; rewrite release-facing copy | `--version`, CI, release metadata | W12 |
| Security/regression | existing security tests plus new tests above | No secrets/cookies/transcripts; no shell injection; no traversal; no unsafe binds | Full security suite and secret scan | Keep AGPL/upstream notices, transparent glib risk | cargo audit visible, SBOM, provenance | W11/W12 |
| Native acceptance | Windows My Computer, CI workflows | Actual installer, OpenRouter path, ClipGauge Local path, full job, edit/export, cancel/resume, YouTube, downloads, accessibility | All mandatory Windows scenarios | Repair defects until gates pass or release is blocked honestly | Screenshots, logs, ffprobe, process trees | W11 |
| Release artifacts | workflows, release scripts, SBOM/provenance | Exact tag build, Windows/Linux/macOS artifacts, checksums, SBOM, provenance, attestation | Tag/source equality and artifact checks | Build/publish only after gates; never modify old tags | Release verification bundle | W12/W13 |

## 3. Requirement-to-workstream coverage

| Specification sections | Covered by | Completion proof |
|---|---|---|
| 0–3 safety, baseline, design | W0 | Protected tag/remote checks, design and plan committed. |
| 4–7 real findings and speaker/support diagnosis | W1/W2/W11 | Controlled reproduction, exact typed errors, job-scoped support ZIP, Windows evidence. |
| 8–10 Setup Center, estimate, consent | W5 | Manifest-driven inventory, estimate, consent tests and screenshots. |
| 11–12 Download Manager/integrity | W5 | Resume/hash/atomic/repair test logs. |
| 13–17 FFmpeg, yt-dlp, PO tokens, browser cookies | W6 | Managed assets, plugin provenance, consent and public URL evidence. |
| 18–22 progress and human stages | W3/W8 | Protocol replay, frontend tests, progress screenshots, stage timings. |
| 23–25 hardware/ASR/performance | W4/W11 | Hardware matrix and same-fixture benchmark. |
| 26–35 ClipGauge Local, model catalog, optional engines, offline status | W7 | Manifest/model cards, lifecycle tests, local inference and offline evidence. |
| 36–41 normal/advanced UX, visual system, motion | W8/W9 | Component tests, accessibility, screenshots, asset tests. |
| 42–51 onboarding/Studio/providers/privacy/Instagram/About | W8/W10 | User-visible text tests, provider/privacy states, platform screenshots. |
| 52–57 brand/independence/copy/errors/checkpoints/repair | W1/W2/W8/W9 | Legacy scan, error/recovery tests, brand docs. |
| 58–65 model/download/storage/network/process/privacy/error UX | W5/W7/W8/W10 | Download restart/integrity/process/privacy tests. |
| 66–78 local/remote jobs, output, cancel/resume, YouTube, performance, reuse | W6/W7/W11 | Real Windows jobs and ffprobe/process/download evidence. |
| 79–87 accessibility/responsive/frontend/screenshots/README/download links | W8/W9/W10 | Viewport/accessibility tests, packaged screenshots, README audit. |
| 88–92 version/security/tests/native CI | W11/W12 | Full gates, advisory scan, CI records, version consistency. |
| 93–98 Windows/PR/release gate/release notes/release | W11/W12 | Windows acceptance, PR, exact annotated tag, release artifacts. |
| 99–100 final report/bundle | W13 | Final report, ZIP integrity, SHA-256, exclusion scan. |

## 4. Verification commands

The final local gate set is:

```bash
cd pipeline
uv lock --check
uv sync
uv run pytest -q
uv pip check

cd ../app
npm ci
npm test
npm run build
npm audit

cd src-tauri
cargo fmt --check
cargo check
cargo test
cargo clippy --all-targets --all-features -- -D warnings
cargo audit
```

Additional checks include protocol fixture replay, model/runtime manifest validation, download resume/hash/cancellation tests, local-server loopback/process tests, support-bundle ZIP tests, secret/cookie/transcript scans, accessibility/static UI checks, same-fixture performance benchmarks, and final version consistency.

## 5. Native acceptance checklist

The Windows checklist is executable and evidence-backed: install the RC NSIS package; confirm platform/signing/About identity; complete onboarding and Setup Center consent; test managed FFmpeg/yt-dlp; save/restart OpenRouter credentials and complete one OpenRouter Free job; install one practical ClipGauge Local model and complete a local job; run a controlled local MP4 through all stages; inspect 9:16/audio/captions/framing/cuts with ffprobe; review/edit/rerender/export; cancel during download/transcription/rendering and inspect the process tree; force-close/restart/resume; test public YouTube URL classification after PO-token support; test Ollama/LM Studio states if absent/present; run keyboard/focus/reduced-motion/viewport checks; capture real packaged screenshots. A missing Windows environment is a release blocker for the creator-ready claim, not a pass.

## 6. Release and stop rules

Do not publish if any release gate from the design specification fails. If a platform or optional provider is unavailable, record it as blocked only where the specification permits an honest documented limitation. ClipGauge Local, full local MP4, OpenRouter full job, support-bundle correctness, speaker actionable errors, strict Clippy, security tests, and native CI are mandatory release gates. Build all artifacts from the exact annotated `v0.3.0` tag and leave `v0.1.0`, `v0.1.1`, `v0.2.0`, and `v0.2.1` immutable.

## 7. Planned final evidence

The final bundle will contain the exact tagged source archive, this plan, the design specification, final report, real packaged screenshots, Windows logs/screenshots, progress/download evidence, runtime manifest, model catalog, download tests, speaker regression, support-bundle ZIP tests, YouTube evidence, hardware benchmark, CI records, SBOM, checksums, provenance, and a diff from the v0.2.1 source tag. It will exclude keys, credentials, browser cookies, private transcripts/videos, unapproved model weights, caches, and signing keys.
