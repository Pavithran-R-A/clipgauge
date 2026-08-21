# ClipGauge v0.3.0 — Creator Experience

ClipGauge v0.3.0 makes the desktop workflow easier to understand, safer to recover, and more useful for creators. It introduces **ClipGauge Local**, a managed loopback-only structured-scoring option powered by pinned llama.cpp assets and conservative Qwen3 GGUF tiers. The first-run flow now explains privacy, consent, storage, provenance, and optional cloud/custom alternatives before any download begins.

The Studio now uses creator-facing language, progressive Setup Center disclosure, richer progress timing and download metadata, named caption styles, plain-language recovery guidance, and accurate platform/runtime identity. Diagnostics are job-scoped and support bundles include the requested diagnostic without unrelated job records. Speaker-stage failures retain stable codes, retryability, redacted diagnostic IDs, and resume-safe checkpoints. YouTube access errors distinguish attestation, login, private, age, region, and unavailable states.

## Verification

The v0.3 branch passed the complete Python suite (`151 passed, 1 warning`), frontend tests (`12 passed`) and production build, Rust tests (`33 passed`), strict Clippy, formatting, manifest consistency, lockfile checks, and the existing cargo audit warning-only gate. A real GitHub Windows runner passed the pipeline suite, built the NSIS installer, silently installed it, launched the installed application, confirmed the process stayed alive for 15 seconds, and uploaded the installer artifact in run [32470539443](https://github.com/Pavithran-R-A/clipgauge/actions/runs/32470539443).

The release remains honest about environment-dependent checks. No full model-backed inference benchmark was claimed without a controlled Whisper fixture. Cloud-provider calls require credentials and are not represented as live by deterministic tests. Release artifacts are unsigned unless a release record proves otherwise; checksums, provenance, and attestations are distinct from platform signing and notarization.

## Security caveats

The project-scoped Python audit reports upstream-constrained findings in Lightning, Torch, and Transformers through the current WhisperX/pyannote stack. The stable Tauri/Wry graph continues to report GTK3/glib RustSec warnings, including `RUSTSEC-2024-0429`. These are documented in [`DEPENDENCY_SECURITY.md`](DEPENDENCY_SECURITY.md) and are not hidden with blanket ignores or incompatible forced upgrades.

ClipGauge remains distributed under **AGPL-3.0-or-later** with explicit attribution to the modified upstream `Blueturboguy07/publikclip` baseline. See [`ORIGIN.md`](../../ORIGIN.md), [`NOTICE.md`](../../NOTICE.md), and [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md).
