# ClipGauge v0.4.0 Release Checklist

**Release target:** `v0.4.0`
**Repository:** `Pavithran-R-A/clipgauge`
**Historical tags:** `v0.1.0`, `v0.1.1`, `v0.2.0`, `v0.2.1`, and `v0.3.0` remain immutable.

This checklist answers the 18 mandatory questions from specification section 36. A PASS below means the item is supported by current source and deterministic evidence. PENDING means an exact-tag CI/release result is still required. `ENVIRONMENT_BLOCKED` is never treated as PASS.

| # | Required question | Answer | Evidence / qualification |
|---:|---|---|---|
| 1 | Can a clean Windows user install ClipGauge without manually installing FFmpeg? | **PENDING native Windows acceptance** | Managed FFmpeg is implemented and the release workflow includes Windows installation checks; the exact-tag `windows-latest` run must confirm the clean-machine path. |
| 2 | Can ClipGauge install every mandatory core component itself with consent? | **PASS in isolated Linux setup** | `core:asr`, `core:analysis`, `core:youtube`, FFmpeg, runtime, and model setup are represented by the Download Manager and explicit consent flow. |
| 3 | Does every large download show size/progress/speed/ETA? | **PASS by manager/UI contract** | Managed progress events expose bytes, total, rate, fraction, ETA, elapsed time, cache state, and one-time state; the Setup Center renders streamed events. |
| 4 | Are one-time downloads clearly identified? | **PASS** | Asset rows and progress events include `one_time_download`; the workflow and onboarding copy label one-time setup. |
| 5 | Does it reuse already downloaded assets? | **PASS** | Verified cache reuse and v0.3 migration are covered by tests and observed `Verified asset reused.` events. |
| 6 | Is the PO-token provider actually installed and detected? | **PASS deterministically** | Managed bgutil/Node installation, loopback health, and yt-dlp provider discoverability self-test are implemented. |
| 7 | What happened in the live YouTube smoke? | **ENVIRONMENT_BLOCKED** | GitHub/datacenter YouTube access was classified as a bot-check/rate-limit environment block. It is documented in `V0_4_YOUTUBE_VALIDATION.md` and is not counted as PASS. |
| 8 | Does local-file ingest work? | **PASS** | The real `jfk-controlled-33s.mp4` fixture completed ingest and audio extraction. |
| 9 | Did a real model-backed E2E create a playable vertical clip? | **PASS on Linux controlled fixture** | Job `20260821-132437-f2ef91` completed through render. Output: H.264/AAC, 540×960, 21.1 seconds, SHA-256 `667636a3b8c0744dfdcb161198426d9c2735c8ab9a0f7ffd0ce81cdb46f2f84b`. |
| 10 | Does ClipGauge Local work without a cloud key? | **PASS** | Loopback health, model listing, structured completion, and the real local-Qwen scoring stage passed with no cloud credential. |
| 11 | Are Ollama and LM Studio correctly detected when present? | **PASS by implemented contract; live presence not available** | The provider adapters use the documented loopback endpoints and capability-aware states. No claim is made that either external runner was live on this host. |
| 12 | Can ordinary users avoid seeing model IDs/endpoints? | **PASS** | Simple mode presents creator-facing provider choices; raw model IDs/endpoints are under Advanced. |
| 13 | Can power users still configure every provider? | **PASS by source/UI contract** | Advanced mode preserves Gemini, OpenRouter, Groq, Cloudflare, Hugging Face, Cerebras, Ollama, LM Studio, and custom OpenAI-compatible configuration. |
| 14 | Does Cancel leave recoverable state? | **PASS by deterministic tests** | Download cancellation preserves verified assets and safe state; the manager and job queue tests cover cancellation/resume semantics. |
| 15 | Are support bundles secret-safe? | **PASS by Rust tests and source review** | Credential redaction, job scoping, diagnostic containment, and exclusion of cookies/source media/raw private content are covered by the Rust suite and support-bundle design. |
| 16 | Are all required CI jobs green? | **PENDING** | Local Python, frontend, Rust, format, Clippy, npm-audit, and version checks are recorded. PR and exact-tag native CI still must run and pass. |
| 17 | Are published binaries tied to the exact tag and checksums? | **PENDING publication workflow** | The release workflow is designed to build from the exact tag, generate SHA256SUMS, SBOM, provenance, and attestation status. No published artifact claim is made before that workflow completes. |
| 18 | What limitations genuinely remain? | **Documented** | Native Windows acceptance, live YouTube smoke in a permitted network, upstream Python ML-stack advisories, upstream GTK3/glib RustSec findings, and unsigned/non-notarized artifacts remain external or release-workflow qualifications. |

## Mandatory pre-publication gates

Before merging or publishing, run the exact PR and release workflows and preserve their URLs and job results. Confirm the Windows NSIS installer is built and silently installed on a fresh `windows-latest` runner; confirm Linux and macOS qualification; run secret scan; validate the release tag/version equality; generate and inspect SBOM, checksums, provenance, and attestation status; and verify every draft release asset before publication.

The project must not be described as published v0.4.0, Windows-accepted, checksum-verified, or advisory-free until those exact gates are complete. The final owner handoff must include the release URL, Windows direct-download URL, Windows SHA-256, genuine external limitations, and one short human acceptance session.
