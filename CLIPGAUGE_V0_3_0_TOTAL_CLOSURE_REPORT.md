# ClipGauge v0.3.0 Total Closure Report

**Project:** [Pavithran-R-A/clipgauge](https://github.com/Pavithran-R-A/clipgauge)  
**Release:** `v0.3.0`  
**Release URL:** [github.com/Pavithran-R-A/clipgauge/releases/tag/v0.3.0](https://github.com/Pavithran-R-A/clipgauge/releases/tag/v0.3.0)  
**Pull request:** [#7](https://github.com/Pavithran-R-A/clipgauge/pull/7)  
**Release workflow:** [run 32474838692](https://github.com/Pavithran-R-A/clipgauge/actions/runs/32474838692)  
**Peeled release commit:** `102356fa86770b90f08b6110cf310f23b8548487`  
**Report date:** 2026-08-21

## 1. Final verdict

> **CONDITIONAL PASS** — ClipGauge v0.3.0 was implemented, verified, merged, tagged, published, and independently checked against the published checksum manifest. The release is not represented as “zero advisories” or “100% bug-free.” Upstream-constrained Python ML dependency findings and the existing GTK3/glib RustSec warning set remain documented and visible. Environment-dependent cloud-provider smoke tests and a full model-backed inference benchmark remain blocked because the required credentials and controlled model fixture were not available.

The feature branch `feature/v0.3-creator-experience` was pushed at commit `bfc0917`, reviewed through PR #7, and merged into `main` with merge commit `102356fa86770b90f08b6110cf310f23b8548487`. The annotated tag `v0.3.0` points to that merge commit. Historical tags `v0.1.0`, `v0.1.1`, `v0.2.0`, and `v0.2.1` were preserved and were not rewritten.

The first tag-triggered release attempt exposed a real Windows release-job failure in the caption-capable FFmpeg acquisition step. The URL and SHA-256 pin were independently verified, and the release workflow was repaired with bounded retry and partial-file cleanup plus exact-tag checkout for manual dispatches. The repaired workflow run `32474838692` completed all seven jobs successfully and published the release.

## 2. Feature and defect closure

| Defect | Resolution | Status | Evidence |
|---|---|---|---|
| **CGV3-001 — support-bundle diagnostic scope** | Support bundles are job-scoped, filter by the requested diagnostic ID, redact secrets generically, and report when a requested diagnostic is missing instead of returning unrelated job records. | **RESOLVED** | Rust diagnostics implementation and Rust test suite; `app/src-tauri/src/diagnostics.rs`; `app/src-tauri/src/main.rs`. |
| **CGV3-002 — generic speaker-stage failures** | Speaker stages now emit six stable typed codes: `SPEAKER_MODEL_DOWNLOAD_FAILED`, `SPEAKER_MODEL_VERIFY_FAILED`, `SPEAKER_MODEL_LOAD_FAILED`, `SPEAKER_AUDIO_LOAD_FAILED`, `SPEAKER_ANALYSIS_FAILED`, and `SPEAKER_CLUSTER_FAILED`, with retryability and diagnostic IDs. | **RESOLVED** | `pipeline/clipgauge_pipeline/diarize/stage.py`; Python tests; frontend `FRIENDLY_FAILURES` recovery mapping. |
| **CGV3-003 — Windows platform mislabeling** | About and runtime identity use detected platform information rather than a Linux v0.2.1 label. | **RESOLVED** | `app/src/components/About.tsx`; real Windows acceptance run `32470539443`. |
| **CGV3-004 — generic YouTube 403 errors** | yt-dlp failures are classified into six stable access states: `ATTESTATION_REQUIRED`, `LOGIN_REQUIRED`, `PRIVATE`, `AGE_RESTRICTED`, `REGION_RESTRICTED`, and `UNAVAILABLE`. | **RESOLVED** | `pipeline/clipgauge_pipeline/ingest/ytdlp.py`; ingest-stage propagation; deterministic classification tests. |
| **CGV3-005 — opaque progress protocol** | Protocol v2 carries creator-facing display stage, elapsed and stage timing, ETA, byte progress and rate, accelerator, one-time-download, and indeterminate metadata. | **RESOLVED** | `pipeline/clipgauge_pipeline/protocol.py`; CLI JSONL progress; `app/src/App.tsx`; Python and frontend tests. |
| **CGV3-006 — Ollama-centric onboarding** | Progressive onboarding now presents ClipGauge Local as the privacy-first default, obtains privacy/storage consent, explains downloads, and exposes Setup Center inventory and recovery paths. | **RESOLVED** | `Onboarding.tsx`, `Studio.tsx`, `local_runtime.py`, `downloads.py`, setup commands, and inventory tests. |

The release also includes the managed loopback-only llama.cpp runtime, pinned b10545 runtime assets, Qwen3 GGUF tiers, conservative hardware detection, ASR CPU fallback, manifest-driven download state, named caption styles, creator-first visual language, an original ClipGauge mark, and explicit AGPL/upstream attribution.

## 3. Verification results

| Area | Result | Notes |
|---|---:|---|
| Python pipeline | **151 passed, 1 warning** | `uv.lock` and `pip check` passed. |
| Frontend | **12 passed** | Typecheck and production build passed; npm audit passed. |
| Rust | **33 passed** | Formatting passed; strict Clippy exited 0. |
| Version consistency | **PASS** | All authoritative current-release sources report `0.3.0`. |
| Windows acceptance | **PASS** | Real GitHub Windows runner, run [32470539443](https://github.com/Pavithran-R-A/clipgauge/actions/runs/32470539443): pipeline tests, NSIS build, silent install, installed-app launch alive for 15 seconds, and artifact upload. |
| Pull-request CI | **PASS** | PR #7 CI, secret scan, and macOS arm64/x86_64 qualification all passed. |
| Release workflow | **PASS** | Run `32474838692`; seven jobs succeeded: validation, Linux, Windows, macOS arm64, macOS x86_64, metadata, and publication. |
| YouTube classification | **PASS** | Six distinct stable access codes verified. |
| Setup inventory | **PASS** | Eight core assets and two local models returned correctly. |
| CPU/int8 performance probe | **PASS** | Conservative CPU/int8 selection verified; no CUDA device was present. |
| Full Whisper model-backed inference benchmark | **BLOCKED** | No controlled model fixture was available; no benchmark result is claimed. |
| Live cloud-provider smoke | **BLOCKED** | No provider credentials were configured; no live-provider success is claimed. |

## 4. Security and reliability classification

The project-scoped Python `pip-audit` run remains non-zero because the resolved WhisperX/pyannote stack carries upstream-constrained findings in `lightning 2.6.5`, `torch 2.8.0`, and `transformers 4.57.6`. The exact paths are `clipgauge-pipeline → whisperx 3.8.6 → pyannote-audio 4.0.7 → lightning` and `clipgauge-pipeline → whisperx 3.8.6 → transformers`, with Torch required by WhisperX. A trial Torch floor of `2.10` was rejected by the resolver because WhisperX 3.8.6 requires `torch>=2.8.0,<2.9.dev0`. These findings are not suppressed or relabeled as zero advisories; remediation requires a coordinated upstream-compatible ML-stack migration.

`cargo audit` exited 0 with warnings only for the existing Tauri/Wry GTK3/glib graph, including the documented unsound advisory `RUSTSEC-2024-0429` and unmaintained GTK3 crates. The warning set is materially the same as v0.2.1 and is documented rather than hidden with blanket ignores. See [`docs/v0.3.0/DEPENDENCY_SECURITY.md`](docs/v0.3.0/DEPENDENCY_SECURITY.md) and the retained Rust dependency record.

Runtime downloads use bounded, staged, SHA-256-verified acquisition. ClipGauge Local uses a managed loopback llama-server supervisor with pinned runtime and model manifest entries; downloaded runtimes and GGUF models are not treated as trusted merely because a URL is reachable. No credentials, API keys, model weights, or user data are included in the closure bundle.

## 5. Published assets and independent checksum verification

The following assets were downloaded from the public v0.3.0 release and checked with `sha256sum -c SHA256SUMS`. Every entry returned `OK`.

| Asset | SHA-256 |
|---|---|
| `ClipGauge_0.3.0_amd64.deb` | `d88a2b6df6ebe63a4f2bc9aa20079725f0aad7dbcbc4d38e2eb025865d1a3207` |
| `ClipGauge_0.3.0_Windows_x64_NSIS.exe` | `7349dee77a971b7839f55f25df04c77de9e5a457c71cb7d0e61b49c16d720d44` |
| `SBOM.cyclonedx.json` | `fdad1c508dfe026a6a0d30be8f5d9137c6116435677dcb7942273bb79bb1dfbd` |
| `RELEASE_PROVENANCE.md` | `d1c54e1c76590dbe2e6f29e282dfe3be3d1e7639186f9d221303098b4e38c42a` |
| `ATTESTATION_STATUS.md` | `8dcb210be367ce44af95c9a282302b99c7e62026474e8ea8ee8f5b6d4962d89d` |

The published SBOM is valid JSON with CycloneDX format version 1.5 and 668 components. The provenance record identifies tag `v0.3.0`, peeled commit `102356fa86770b90f08b6110cf310f23b8548487`, and workflow run `32474838692`. It explicitly distinguishes generated GitHub build provenance from platform signing, notarization, cryptographic signatures, and artifact attestations. The release is published, not a draft or prerelease.

## 6. Closure bundle contents and integrity protocol

`CLIPGAUGE_V0_3_0_TOTAL_CLOSURE_BUNDLE.zip` contains this report, the complete retained `v030-evidence/` logs, the downloaded and checksum-verified release assets, the `v0.3.0` source archive, pull-request and release-run evidence, the real Windows acceptance JSON, and a bundle-level SHA-256 manifest. The archive excludes credentials, API keys, model weights, downloaded runtime binaries, and user data.

The bundle integrity test is deterministic: extract the archive into a clean directory, run `sha256sum -c BUNDLE_SHA256SUMS`, and confirm every entry returns `OK`. The extracted bundle integrity test returned `OK` for every listed file. The final ZIP byte count and SHA-256 are supplied in the accompanying `CLIPGAUGE_V0_3_0_TOTAL_CLOSURE_BUNDLE.zip.sha256` file so the report does not self-reference its container digest. The public bundle excludes credentials, API keys, model weights, downloaded runtime archives, and user data.

## 7. Provenance and licensing

ClipGauge remains under **AGPL-3.0-or-later**. The release preserves explicit attribution to the modified upstream baseline [`Blueturboguy07/publikclip`](https://github.com/Blueturboguy07/publikclip). No historical release tags were modified. The release source commit is the PR merge commit named in the published provenance record; post-tag CI reliability commits on `main` are not silently presented as part of the immutable v0.3.0 source tag.

## 8. Evidence index

The supporting evidence is retained in `v030-evidence/` and includes Python, frontend, Rust, Clippy, audit, version, setup inventory, performance-probe, Windows acceptance, PR-check, release-run, release-asset, checksum, and provenance records. The most important external records are:

- [PR #7 — ClipGauge v0.3.0](https://github.com/Pavithran-R-A/clipgauge/pull/7)
- [Windows acceptance run 32470539443](https://github.com/Pavithran-R-A/clipgauge/actions/runs/32470539443)
- [Release workflow run 32474838692](https://github.com/Pavithran-R-A/clipgauge/actions/runs/32474838692)
- [Published v0.3.0 release](https://github.com/Pavithran-R-A/clipgauge/releases/tag/v0.3.0)
