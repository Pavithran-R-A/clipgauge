# Changelog

All notable ClipGauge changes are recorded here. The v0.1.0 release is the first public ClipGauge release in this repository and is a modified derivative of publikclip; see [`ORIGIN.md`](ORIGIN.md) for the exact baseline.

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

[0.1.0]: https://github.com/Pavithran-R-A/clipgauge/releases/tag/v0.1.0 "ClipGauge v0.1.0"
