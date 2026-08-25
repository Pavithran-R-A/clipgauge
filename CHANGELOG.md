# Changelog

All notable ClipGauge changes are recorded here. The v0.1.0 release is the first public ClipGauge release in this repository and is a modified derivative of publikclip; see [`ORIGIN.md`](ORIGIN.md) for the exact baseline.

## [0.5.3] — 2026-08-25

ClipGauge v0.5.3 is a real-device UX and readiness repair. It keeps the deep-ocean creator workflow while making responsive containment, optional local-AI state, YouTube support, provider copy, and terminal run status explicit and truthful.

### Fixed

- Contained long session titles and sidebar actions structurally so text cannot expand the sidebar into the Create region.
- Split creator processing and clip-editor timeline styles into independent namespaces and preserved reduced-motion behavior.
- Separated core setup readiness from optional ClipGauge Local and YouTube readiness, with scoped install, test, repair, and retry actions.
- Added model lifecycle states for Installed/Verified, Reused, Download required, and Needs repair, including persisted selection and no-download reuse for valid files.
- Made YouTube readiness authoritative at the backend/provider boundary and blocked public-link creation before session creation when support is not ready.
- Replaced inferred success messaging with explicit Running, Succeeded, Failed, and Cancelled creator states.
- Made Create helper text follow the selected provider and added safe local health and display diagnostics.

### Validation

- Added deterministic model lifecycle, YouTube readiness, creator-state, display-diagnostics, and rendered responsive containment regressions.
- Preserved the v0.5.2 security, provider credential, support-bundle, and release-quality controls.

### Known limitations

- Native platform qualification, real public-YouTube creator E2E, and publication remain gated on the exact PR head.
- Platform signing/notarization, provider quotas, model availability, and local hardware requirements continue to depend on the selected setup.

## [0.5.2] — 2026-08-23

ClipGauge v0.5.2 is a focused setup and provider-readiness correction. It keeps the v0.5.1 creator workflow intact while making component ownership, local-AI readiness, setup outcomes, and credential states truthful and recoverable.

### Fixed

- Reused a capable system FFmpeg installation when it starts successfully and exposes the subtitles filter, without presenting a managed download or charging its bytes to Setup & Storage.
- Added one selected-model-aware ClipGauge Local action that installs the verified runtime and downloads only the chosen model when needed.
- Aggregated setup operations across every queued component so an earlier or middle failure cannot be replaced by a later success; terminal progress clears on completion and failure remains retryable without a running timer.
- Standardized provider credential IDs at the native bridge boundary and added safe OS-vault removal for provider and Gemini credentials.
- Distinguished **Not configured**, **Credential saved**, **Connected**, and **Connection failed** in AI Providers; a saved key is never presented as a verified connection.

### Tests and qualification

- Added deterministic readiness and setup-queue regressions for system-FFmpeg reuse, managed fallback, first/middle queue failure, cancellation, canonical provider IDs, and credential removal.
- Preserved the v0.5.1 media/editor, path-security, privacy, and release-gate behavior without redesigning the creator pipeline.

### Known limitations

- Platform installers remain subject to the platform signing and notarization state documented on each release.
- Provider quotas, model availability, and local hardware requirements continue to depend on the selected setup.

## [0.5.1] — 2026-08-22

ClipGauge v0.5.1 is a small polish release that closes the remaining visual and public-project misses found after the creator-focused redesign.

### Fixed

- Replaced the remaining first-party yellow and purple app marks with the deep-ocean, teal, blue, and green ClipGauge identity across Tauri platform icons.
- Removed an unused duplicate mark asset that still carried retired visual-identity language.
- Reworded the retained clip editor so rendering, dead-space cleanup, and visual suggestions read like creator actions rather than developer commands.
- Removed the last legacy grain and amber styling from retained result and feedback surfaces.

### Changed

- Added a case-insensitive first-party visual-asset gate that checks SVG color text and raster icon pixels, including a regression self-test for uppercase hex values.
- Added the permanent branding, privacy, disclosure, evidence, and public-repository rules to the product principles and pull-request checklist.
- Kept the packaged visual QA evidence and release checks aligned with the current v0.5.1 build.

### Known limitations

- Platform installers remain unsigned unless a release explicitly says otherwise.
- Provider quotas, model availability, and local hardware requirements continue to depend on the selected setup.

## [0.5.0] — 2026-08-22

ClipGauge v0.5.0 brings the app back to the creator's workflow: add a video, choose how scoring runs, review the reason for each suggestion, and export the clip you want.

### Added

- A creator-first **Create** screen with video drop zone, link input, provider choice, caption style, and a readable processing timeline.
- **Sessions**, **AI Providers**, **Integrations**, **Privacy**, and **Help & Diagnostics** screens with clear routes back to Create.
- A provider center that keeps ClipGauge Local, OpenRouter Free, Gemini, Groq, Cloudflare Workers AI, Hugging Face, Cerebras, Ollama, LM Studio, and Custom OpenAI-compatible endpoints discoverable.
- A grouped Setup & Storage flow with one consented install action, resumable downloads, and honest size states when an estimate is not yet available.
- Separate Pexels stock visuals and Instagram performance feedback integrations.
- A calmer first-run onboarding flow and a human-readable **Why this clip** review screen.

### Changed

- Replaced the previous purple and amber visual identity with a deep-ocean palette using teal, blue, green, coral, and neutral surfaces.
- Moved provider credentials into the provider center and kept technical model and endpoint details behind an Advanced disclosure.
- Rewrote public documentation around the creator workflow and added product principles, contributor guidance, and a pull-request checklist.
- Removed internal agent-phase reports and planning folders from the current public tree while preserving historical Git history and release provenance.

### Fixed

- Removed the misleading zero-byte setup placeholder for sizes that have not been calculated.
- Preserved explicit missing-render and media-decode diagnostics in the review flow.
- Kept browser-cookie retrieval opt-in and separate from ordinary source-link processing.

### Known limitations

- Packaged installers remain subject to the platform signing and notarization state documented on each release.
- Cloud provider quotas, free-route availability, model capabilities, retention, and terms are controlled by those providers and can change.
- Local model setup and hardware-dependent scoring still require the supported runtime, enough disk space, and suitable hardware.

## [0.4.1] — 2026-08-21

ClipGauge v0.4.1 is the qualification-and-release-gates patch release. It closes the verified v0.4.0 gaps around setup observability, production-default model-backed output, exact-tag publication, and platform quality enforcement.

### Setup Center and onboarding

- Completes streamed setup progress for every substantial setup action in Studio and Onboarding, including bytes completed/total, determinate percentage, speed, meaningful ETA, elapsed time, and one-time versus reused lifecycle labels.
- Adds required/optional/installed/available storage summaries, richer asset provenance rows, cancellable operations, and functional retry of the last validated setup action.
- Routes runtime, FFmpeg, ASR, analysis, YouTube compatibility, and local-model setup through the cancellable streaming boundary; compute stages do not gain hidden large-download bypasses.

### Qualification and release gates

- Adds a production-default model-backed E2E gate using a genuine MIT-licensed speech fixture, real managed assets, 1080×1920 vertical output, and captions burned into the final playable MP4.
- Adds an exact-tag `model-e2e-release` job whose validated `MODEL_E2E_SUMMARY.json` is required by release metadata and publication, then checksummed and attached.
- Strengthens CI, Windows, macOS, and release quality gates by removing blanket Clippy allowances and test exclusions; native Windows acceptance remains a GitHub-hosted Windows responsibility.

### Evidence and provenance

- Commits the genuine speech fixture and provenance documentation used by the release gate.
- Updates README download navigation, accessibility evidence, YouTube validation classification, security review, and the v0.4.1 final audit while preserving AGPL-3.0-or-later licensing, publikclip attribution, and the GPL-3.0-only bgutil notice.

## [0.4.0] — 2026-08-21

ClipGauge v0.4.0 is the managed-runtime and creator-workflow release. It makes runtime, speech, analysis, YouTube compatibility, and local-provider setup explicit, consented, repairable, and observable.

### Managed runtime and downloads

- Adds one verified Download Manager for runtime and analysis assets, grouped consent, disk-space checks, cancellation, progress/ETA events, repair, cache reuse, and v0.3 cache migration.
- Adds self-service managed FFmpeg and fails closed with an actionable Setup Center message instead of downloading during rendering.
- Adds explicit faster-whisper, Silero VAD, English alignment, NLTK `punkt_tab`, analysis-model, local-runtime, and local-GGUF setup paths. Silero VAD is pinned, SHA-256 verified, atomically materialized into the managed torch.hub cache, and loaded offline.
- Adds bounded local ClipGauge Local runtime startup with one llama-server slot, a 4096-token context, and Qwen3 reasoning disabled for predictable structured scoring requests.

### YouTube and provider workflow

- Adds managed portable Node.js and bgutil PO-token compatibility with loopback-only supervision and health checks.
- Adds explicit browser-auth opt-in through an allow-listed `--cookies-from-browser` option; browser cookies are never read by default and the choice is recorded in the job snapshot.
- Adds Simple/Advanced provider mode. Simple mode presents creator-facing ClipGauge Local, Ollama, LM Studio, and Gemini choices without raw model IDs or endpoints; Advanced mode exposes the full provider configuration.
- Adds streamed, cancellable Setup Center operations and explicit download-consent confirmation before managed downloads.

### Validation and caveats

- A real model-backed local-file E2E completed through ingest, faster-whisper transcription, Silero VAD, alignment, diarization, analysis, candidate selection, local Qwen scoring, camera direction, and verified vertical MP4 rendering. The controlled validation render used the documented caption-free mode and allow-listed low-resolution/fast-encode overrides; the production default remains captioned 1080×1920 output.
- Windows acceptance remains a native `windows-latest` CI responsibility; Linux local validation is not presented as Windows acceptance. Live YouTube retrieval remains environment-dependent and is documented separately when datacenter policy blocks it.
- Release artifacts remain unsigned unless release evidence explicitly proves otherwise. AGPL-3.0-or-later licensing, upstream attribution to `Blueturboguy07/publikclip`, and the GPL-3.0-only bgutil notice are preserved.

## [0.3.0] — 2026-08-21

ClipGauge v0.3.0 is the creator-experience release: a calmer, privacy-first desktop workflow with ClipGauge Local, managed runtime setup, typed diagnostics, resumable progress, and native Windows installer acceptance.

### Creator workflow

- Adds progressive onboarding and an in-studio Setup Center with consent-aware storage estimates, pinned provenance, SHA-256 verification state, and repairable runtime/model actions.
- Adds ClipGauge Local as a first-class loopback-only OpenAI-compatible provider using pinned llama.cpp `llama-server` assets and conservative Qwen3 GGUF tiers.
- Adds human-readable Studio labels, named caption styles, plain-language failure recovery, richer stage timing/ETA/download metadata, and accurate runtime-detected About platform copy.
- Adds an original SVG-first ClipGauge mark and a navy/indigo/cyan/emerald creator-console visual system while preserving the AGPL license and upstream attribution.

### Reliability and security

- Adds job-scoped diagnostic support bundles, typed speaker-stage errors, resumable checkpoint semantics, and explicit YouTube access classifications for attestation, login, private, age, region, and unavailable states.
- Adds safe full-archive extraction for managed runtime bundles, loopback-only local-runtime lifecycle ownership, manifest-driven inventory, and deterministic setup/provider regression coverage.
- Full local Python and frontend gates pass; Rust tests, strict Clippy, and native Windows install/launch acceptance pass. Full model-backed inference benchmarking remains environment-dependent and is not claimed without a controlled fixture.
- The existing GTK3/glib RustSec warning set remains upstream-blocked in the stable Tauri/Wry graph; pip-audit findings constrained by WhisperX are documented rather than hidden or force-upgraded.

### Caveats

- Cloud providers, local inference engines, and model-backed end-to-end video jobs are reported only when credentials, installed assets, and controlled fixtures are available; blocked tests are not marked PASS.
- Release artifacts remain unsigned unless release evidence explicitly proves otherwise. Platform qualification is not signing or notarization.

## [0.2.1] — 2026-08-21

ClipGauge v0.2.1 is a maintenance and verification release. It preserves the v0.2.0 provider architecture and closes the project-owned findings from the independent A-to-Z audit.

### Defect closure

- Resolves strict Rust Clippy findings through production-definition ordering, removal of dead exported diagnostics API, generic custom-secret redaction coverage, and typed `RunJobRequest`/`ResumeJobRequest` Tauri boundaries with unknown-field rejection.
- Adds `clipgauge --version` and `clipgauge -V` from authoritative Python package metadata while preserving `--help` and all existing subcommands.
- Runs normal Cargo dependency resolution and documents the remaining GTK3/glib RustSec warnings transparently. RUSTSEC-2024-0429 remains an upstream dependency blocker/known risk because the supported stable Tauri/Wry graph still resolves glib 0.18.x and the GTK4/WebKit6 migration is not a compatible drop-in update.
- Adds fresh typed-command, diagnostics, CLI, dependency, and native/provider acceptance evidence for the v0.2.1 release decision.

### Caveats

- Windows installed-app acceptance, live provider calls, local Ollama/LM Studio inference, and full model-backed video completion are reported only when their real environments and credentials are available; blocked tests are not marked PASS.
- Release artifacts remain unsigned unless release evidence explicitly proves otherwise. Platform qualification is not signing or notarization.

## [0.2.0] — 2026-08-20

### Universal AI provider architecture

- Adds a versioned `ProviderProfile`, capability model, normalized inference request/result contract, explicit structured-output levels, provider-aware cache identity, immutable job snapshots, and legacy Gemini/Ollama migration.
- Adds curated Gemini, OpenRouter, Groq, Cloudflare Workers AI, Hugging Face, and Cerebras profiles through one OpenAI-compatible adapter family.
- Adds local Ollama and LM Studio loopback presets, model discovery, manual model entry, and capability-aware degradation reporting.
- Adds a generic OpenAI-compatible custom endpoint with validated HTTPS/loopback URL policy, no-auth/bearer/API-key/custom-header modes, disabled authenticated redirects, and OS-vault credentials.
- Adds provider-aware Studio controls, Test Connection, neutral onboarding, Privacy Activity details, provider provenance, and redacted support-bundle behavior.
- Adds deterministic provider contract tests, migration tests, normalized error/retry handling, URL/redirect security tests, and the v0.2 full QA/rebrand/security documentation set.

### Caveats

- Provider free tiers, quotas, model support, retention, payment requirements, and terms change over time; ClipGauge makes no permanent free or unlimited-use promise.
- Local and cloud model capabilities are model-dependent. Text-only providers record missing vision instead of silently claiming image support.
- Release signing, notarization, and live-provider smoke depend on owner credentials and are reported separately from deterministic CI.

## [0.1.1] — 2026-08-19

ClipGauge v0.1.1 is a release-engineering closure release. It does not rewrite the analytical pipeline or replace the historical v0.1.0 tag and release.

### Release engineering

- Adds deterministic version-consistency checks across the Tauri, Rust, frontend, Python, runtime, and current-release documentation metadata.
- Corrects release-language so Linux and Windows artifacts are explicitly unsigned, while native macOS builds are described as qualification results rather than signed or notarized consumer distribution.
- Replaces the earlier ad-hoc SBOM path with a tag-driven CycloneDX generator and validator whose first-party source identity is obtained from the actual peeled v0.1.1 tag commit.
- Adds fresh Windows x64 NSIS release packaging with native tests, silent install, application launch/process smoke, and immutable workflow-artifact transfer.
- Adds native Apple Silicon and Intel macOS qualification jobs, including `.app` inspection and optional DMG packaging where the hosted runners support it.
- Refactors release publication behind Linux, Windows, macOS, metadata, checksum, SBOM, provenance, and secret-scan gates.
- Generates SHA-256 manifests from the exact public release assets and records the distinction between checksums, human-readable provenance, GitHub attestations, and platform signing.

### Security and release notes

- AGPL-3.0-or-later, upstream attribution, and the audited publikclip baseline remain preserved.
- No default telemetry, mandatory subscription, signing certificate, Apple Developer credential, or notarization claim is introduced.
- The updater remains disabled because no real signing key is configured.

## [0.1.0] — 2026-08-19

### Added

- Rust-owned job lifecycle state, duplicate-run protection, cancellation, stale-lease recovery, checkpoint resumability metadata, and structured diagnostics.
- Versioned artifact descriptors, managed-root containment, checkpoint validation, atomic writes, corruption recovery, and redacted support-bundle generation.
- Pinned runtime and model registry handling with bounded downloads, verified SHA-256 checks, traversal rejection, and last-known-good preservation.
- OS credential-store abstraction, legacy credential migration, operation-scoped secret injection, Gemini header authentication, native Ollama loopback HTTP, and ephemeral Instagram OAuth handling.
- Strict Tauri edit-schema validation, resource preflight, first-run gating, local file picker and drag-and-drop, accessible progress timing, reduced-motion support, and visible focus styles.
- Explainable clip ledger data, privacy activity summaries, safe resumability metadata, licensing/provenance notices, and an in-app About/Licenses route.
- Original ClipGauge identity assets, package names, `clipgauge` CLI, `clipgauge_pipeline` Python package, `.clipgauge` data root, and `io.github.pavithranra.clipgauge` bundle identifier.
- CI workflows for Python, frontend, Rust, release artifact assembly, and repository secret scanning.

### Changed

- The desktop bridge now invokes the renamed `clipgauge` entry point in both development and packaged-resource paths.
- Legacy `.publikclip` and `PUBLIKCLIP_HOME` identifiers remain only for migration compatibility and upstream provenance.
- Documentation now distinguishes local processing from optional network activity and documents the unsigned Linux release boundary.

### Security and release notes

- AGPL-3.0-or-later is preserved. Adapted and vendored dependencies, runtime-fetched weights, fonts, and optional binaries are inventoried in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
- No default telemetry or mandatory subscription is introduced.
- The updater is disabled because no real signing key is configured.
- The release is unsigned. This changelog does not claim signing, notarization, Windows/macOS test results, performance benchmarks, screenshots, or trademark clearance.

[0.1.1]: https://github.com/Pavithran-R-A/clipgauge/releases/tag/v0.1.1 "ClipGauge v0.1.1"
[0.1.0]: https://github.com/Pavithran-R-A/clipgauge/releases/tag/v0.1.0 "ClipGauge v0.1.0"
