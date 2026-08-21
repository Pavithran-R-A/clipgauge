# ClipGauge v0.4.1 Release Checklist

**Release target:** `v0.4.1`

**Repository:** `Pavithran-R-A/clipgauge`

**Historical tags:** `v0.1.0`, `v0.1.1`, `v0.2.0`, `v0.2.1`, `v0.3.0`, and `v0.4.0` are immutable and must not be modified.

This checklist answers the mandatory release questions from the v0.4.1 specification. `PASS` means the item is supported by implementation and recorded evidence. `BLOCKED` identifies an external runner, network, or publication result that is not honestly claimable from the current environment. No item is labelled `PENDING`.

| # | Required question | Status | Evidence / qualification |
|---:|---|---|---|
| 1 | Can a clean Windows user install ClipGauge without manually installing FFmpeg? | **BLOCKED** | Managed FFmpeg and the Windows workflow are implemented; fresh `windows-latest` installer acceptance must be verified by the exact-tag GitHub run. |
| 2 | Can ClipGauge install every mandatory core component itself with consent? | **PASS** | The managed groups and explicit setup actions cover ASR, analysis, YouTube compatibility, FFmpeg, runtime, and local model setup. |
| 3 | Does every large download show size/progress/speed/ETA? | **PASS** | Studio and Onboarding render streamed bytes, percentage, speed, meaningful ETA, elapsed time, and indeterminate state without a fabricated percentage. |
| 4 | Are one-time downloads clearly identified? | **PASS** | One-time, installed/reused, and migration-reuse lifecycle labels are rendered in the Setup Center. |
| 5 | Does it reuse already downloaded assets? | **PASS** | Verified-cache reuse and migration fields remain part of the managed inventory and setup event contract. |
| 6 | Is the PO-token provider actually installed and detected? | **PASS** | Managed Node/bgutil assets, loopback health, and yt-dlp provider discoverability are covered by the deterministic compatibility path. |
| 7 | What happened in the live YouTube smoke? | **BLOCKED** | Live public retrieval is environment-dependent and is not counted as PASS from a GitHub/datacenter network. See `V0_4_1_YOUTUBE_VALIDATION.md`. |
| 8 | Does local-file ingest work? | **PASS** | The controlled genuine-speech fixture was converted to a local MP4 and used in the real model-backed qualification run. |
| 9 | Did a production-default model-backed E2E create a playable vertical clip? | **PASS** | Job `20260821-132437-f2ef91` completed with real managed inference; output is H.264/AAC, 1080×1920, 21.1 seconds, captions burned, SHA-256 `0ea8d7f9700f960722f8016787506ccd761b9d262eaf09e5739d6f5e098e7a32`. |
| 10 | Does ClipGauge Local work without a cloud key? | **PASS** | The qualified run used the managed local runtime/model and no cloud credential for local scoring. |
| 11 | Are Ollama and LM Studio correctly detected when present? | **PASS** | Provider capability and loopback contracts remain implemented; no claim is made that either optional external runner was live in this environment. |
| 12 | Can ordinary users avoid seeing model IDs/endpoints? | **PASS** | Simple mode retains creator-facing labels and keeps raw model IDs/endpoints in Advanced configuration. |
| 13 | Can power users still configure every provider? | **PASS** | Advanced provider configuration remains available for the documented local, cloud, and OpenAI-compatible paths. |
| 14 | Does Cancel leave recoverable state? | **PASS** | The shared setup cancellation path preserves operation state and retry arguments; existing manager cancellation/resume tests remain mandatory. |
| 15 | Are support bundles secret-safe? | **PASS** | Existing credential redaction and support-bundle containment behavior is preserved; v0.4.1 adds no credential-bearing network surface. |
| 16 | Are all required CI jobs green? | **BLOCKED** | Local gates are being rerun; PR, exact-tag native platform jobs, and the model-backed release job must supply the final GitHub results. |
| 17 | Are published binaries tied to the exact tag and checksums? | **BLOCKED** | The workflow now enforces exact-tag checkout, model-E2E dependency, SBOM, provenance, checksums, and draft-first publication; no public asset claim is made before completion. |
| 18 | What limitations genuinely remain? | **PASS** | Native runner results, live YouTube from a permitted network, upstream dependency advisories, and unsigned/non-notarized artifacts are explicitly documented rather than hidden. |

## Release-gate design

The exact-tag `model-e2e-release` job checks out the release tag, installs managed assets with explicit setup commands, uses ClipGauge Local, runs the committed genuine-speech fixture through the production-default pipeline, validates terminal success and all required stages, verifies a real captioned 1080×1920 MP4, and uploads compact evidence. `release-metadata` and `release-publish` depend on this job, so a failed model-backed gate cannot publish the tag.

The Windows job remains the authority for native installer installation, packaged-resource setup inventory, writable application data, managed FFmpeg/YouTube assets, branding/version, clean shutdown, and process cleanup. Linux and macOS jobs retain their native build and qualification responsibilities. No blanket Clippy allowance or test exclusion is used in the strengthened workflows.

## Decision before publication

The candidate is suitable for PR and exact-tag qualification because all project-owned v0.4.1 changes are implemented and the production-default local E2E evidence exists. Publication remains BLOCKED until the exact GitHub PR/release results, native runner evidence, checksums, and published asset verification are captured. This is an external gate, not a reason to weaken or relabel any check.

## References

[1]: ../../v041-production-default-e2e-validation.md "Production-default model-backed E2E evidence"
[2]: ../../v041-production-default-media-probe.json "Production-default media probe"
[3]: V0_4_1_SETUP_CENTER_VALIDATION.md "v0.4.1 Setup Center validation"
[4]: V0_4_1_YOUTUBE_VALIDATION.md "v0.4.1 YouTube validation"
[5]: V0_4_1_SECURITY_REVIEW.md "v0.4.1 security review"
[6]: ../../.github/workflows/release.yml "Exact-tag release workflow"
