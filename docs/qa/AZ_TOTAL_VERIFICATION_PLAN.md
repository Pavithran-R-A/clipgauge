# ClipGauge A-to-Z Total Verification Plan

**Repository:** `Pavithran-R-A/clipgauge`  
**Target:** public `v0.2.0` release, with protected tags `v0.1.0`, `v0.1.1`, and `v0.2.0` left unchanged  
**QA branch:** `qa/a-z-total-verification`  
**Baseline:** `origin/main` at `69051be8d8cd6dc269608a30aaff3de4cfddc1b6`  
**Classification vocabulary:** `VERIFIED`, `VERIFIED BY DETERMINISTIC TEST`, `VERIFIED BY STATIC INSPECTION`, `BLOCKED`, `FAILED`, and `NOT APPLICABLE`.

## Verification principles

This is a fresh independent verification pass. Previous reports are inputs only and do not substitute for new execution. Every claim will be tied to a command, controlled fixture, source inspection, public release artifact, or explicit external limitation. No claim of perfection, bug-free behavior, or universal provider support will be made. Secrets will be read only from already configured secure environments; no credentials will be requested in chat, printed, committed, or placed in URLs.

## Execution matrix

| Area | Required coverage | Fresh evidence | Classification rule |
|---|---|---|---|
| Source safety | Remotes, branch, clean state, commit graph, protected tags | Baseline command transcript and tag peels | Verified if exact expected remotes/tags are preserved |
| Repository inventory | Every tracked file grouped by UI, Tauri, pipeline, providers, runtimes, media, lifecycle, privacy, integrations, CI, packaging, docs, licensing | Tracked-file inventory plus subsystem map | Verified by static inspection when executable testing is unavailable |
| Clean Python build | `uv lock --check`, clean sync, pip check, full pytest, warnings and timing, maintained advisory scanner | Command logs and test summary | Failed on dependency/test failure; advisory findings recorded, never hidden |
| Clean frontend build | `npm ci`, Vitest, TypeScript/Vite build, `npm audit` | Command logs and audit output | Failed on build/test failure; audit findings classified separately |
| Clean Rust/Tauri build | fmt, check, test, all-target/all-feature Clippy, maintained advisory audit | Command logs and advisory output | Failed on compilation/test failure; lint exceptions recorded explicitly |
| Static code audit | TODO/FIXME/unsafe/shell/eval/secret/network/filesystem/error-handling searches and review of all hits | Search output plus reviewed findings | Static-inspection classification unless executed |
| Provider architecture | Nine provider paths, endpoints, auth, secret transport, discovery, manual models, text, JSON/schema, vision, timeout, rate/quota, errors, cache, diagnostics, privacy | Provider source review and contract tests | Capability-dependent claims are never generalized |
| Provider contracts | Success/failure, malformed output, schema violation, retries, redirects, cache separation, manual model, secret redaction | Fresh deterministic test log | Verified by deterministic test only |
| Live cloud providers | Gemini, OpenRouter, Groq, Cloudflare, Hugging Face, Cerebras; auth/text/schema/vision/failure | Existing manual smoke with secure secrets only | `PASS` only after actual live request; absent secret is `BLOCKED — credential not configured`, never pass |
| OpenRouter workflow | Real `openrouter/free` tiny workflow if credential exists | Isolated synthetic request evidence | Blocked without credential; no paid purchase or source media |
| Ollama | Local server health, model listing, text/schema/vision/error behavior | Local server evidence or explicit absence | Blocked if service/model unavailable |
| LM Studio | Local server health, model listing, text/schema/vision/error behavior | Local server evidence or explicit absence | Blocked if service/model unavailable |
| Custom provider | URL/auth/header/redirect/TLS/model/manual listing/text/schema/vision/failure | Local mock-server evidence | Verified only for exercised capability paths |
| Windows release | Download, hash, install, launch, first-run, use, uninstall | Public release asset and local Windows access | Blocked if OS unavailable; never imply Windows execution from CI alone |
| First-run UI | Local/cloud/custom onboarding, provider setup, vault state, privacy disclosure | Desktop/UI test or static evidence | Blocked if desktop display unavailable |
| End-to-end video | Synthetic fixture ingest through scoring, captions, rendering, export, quality review | Local fixture outputs and media metadata | Failed on reproducible functional defect; blocked on missing runtime/hardware |
| Input matrix | MP4/MOV/WebM, portrait/landscape, short/long, audio/no-audio, variable frame rate, Unicode paths, malformed files | Fixture matrix and results | Each unsupported or blocked case explicitly recorded |
| URL ingest | YouTube/URL validation, yt-dlp, failure states, privacy boundary | Safe public/test URL or blocked status | No private upload; network-dependent cases can be blocked |
| Lifecycle | Cancel, resume, duplicate/concurrent jobs, stale recovery, checkpoint corruption | Controlled job fixtures and process inspection | Reproducible bad state is failed/high severity according to impact |
| Editor/captions/camera | Edit schema, caption presets, camera modes, safe export | UI/unit/output evidence | Blocked if desktop/media runtime unavailable |
| Integrations | Pexels and Instagram/Meta loop, credential gates, failure/telemetry/privacy | Static review and safe mock/credentialless behavior | Live external action is not performed without owner authorization |
| Vault/support/privacy | Secret storage, redaction, support bundle exclusions, activity view, offline mode | Rust tests, redaction inspection, UI/static review | Any leaked secret is a blocker |
| Resource behavior | Low-memory/CPU/disk/network-disconnect observations, process/temp/cache cleanup | Safe bounded observations | No destructive stress; limitations documented |
| Accessibility/windowing | Keyboard/focus/labels/contrast, display sizing, launch/close behavior | Desktop execution or static review | Blocked if no display/session |
| Rebrand/licensing/docs | Search and classify upstream identity, AGPL, notices, provider docs, release docs | Fresh searches and file review | Accidental user-facing branding or unsupported claims fail |
| Release/artifacts | Release record, six assets, checksums, SBOM, provenance, attestation status, README/docs/version | Fresh download and parse evidence | Hash/SBOM/tag mismatch fails |
| GitHub Actions | PR, push, platform, secret scan, release workflows and logs | Public run JSON/logs | Red mandatory gate fails; skipped optional live tests remain skipped |
| Final requirements | One matrix row for every identifiable subsystem and every mandated phase | Coverage crosswalk and final report | Any silent gap is not acceptable; unknowns become explicit |

## Planned execution order

First, inventory the repository and create the subsystem crosswalk. Second, execute clean dependency/build/test gates and advisory scans. Third, perform source, provider, security, privacy, migration, lifecycle, and adversarial reviews, adding local mock servers and synthetic fixtures where safe. Fourth, exercise live/local providers only when secure credentials and services already exist. Fifth, validate public release artifacts and available installation paths. Sixth, run the final consolidated tests, classify every row, and write the final report and evidence bundle.

## Safety boundaries

The audit will not modify protected tags, rewrite history, expose or request credentials, upload private media, purchase services, disable TLS, weaken OS security, destroy existing jobs/settings, or perform irreversible external actions. Any unavailable operating system, display session, provider credential, local server, model, certificate, or permission will be recorded as `BLOCKED`, not represented as a pass.

## Required deliverables

The branch will contain this plan and the final QA reports/evidence index only. The final deliverables will include a complete repository inventory, fresh test and audit matrix, provider status report, blocked/failed/unknown register, release-artifact verification, requirements crosswalk, and a ZIP evidence bundle that excludes secrets, credentials, user media, model weights, dependency caches, build directories, and private diagnostics.
