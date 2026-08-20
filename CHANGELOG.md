# Changelog

All notable ClipGauge changes are recorded here. The v0.1.0 release is the first public ClipGauge release in this repository and is a modified derivative of publikclip; see [`ORIGIN.md`](ORIGIN.md) for the exact baseline.

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
