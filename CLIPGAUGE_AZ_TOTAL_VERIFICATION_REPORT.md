# ClipGauge v0.2.0 — A-to-Z Total Verification Report

**Audit date:** 2026-08-21 UTC  
**Auditor:** Manus AI  
**Public repository:** [Pavithran-R-A/clipgauge][1]  
**Release:** [v0.2.0][2]  
**PR:** [#5][3]

> **Truth statement:** This report distinguishes deterministic verification, local mock verification, live external verification, and blocked tests. A successful build is not treated as a successful end-to-end video workflow, and a mocked provider is not treated as live.

## Executive verdict

# CONDITIONAL PASS

ClipGauge v0.2.0 is **conditionally acceptable for ordinary external evaluation** at the source, automated-test, security-contract, provider-architecture, and public-release-artifact levels. The public release is non-draft, its downloaded assets pass the published SHA-256 manifest, the SBOM is structurally valid, current main CI/Windows/macOS qualification/secret-scan runs are green, and no blocker or high-severity security defect was confirmed.

This is **not a clean full A-to-Z PASS**. The complete fresh Clippy command fails on three code-quality categories; no Windows host was available for installer/user-experience testing; no local Ollama or LM Studio runtime was installed; no cloud-provider credentials were present for live inference; and the available Linux host did not have the large ASR/model assets required to complete a real ClipGauge video job. The final status therefore does not claim a completed full-job export, live cloud success, Windows launch, Windows install/uninstall, or universal performance behavior. A v0.2.1 maintenance pass is recommended for the Clippy findings and a conventional CLI version flag.

## Scope

The audit inspected **234 tracked files**, classified **61 components**, ran **129 Python tests**, **12 frontend tests**, and **28 Rust tests**, executed one bounded Tauri launch, exercised the CLI and synthetic input matrix, ran one local custom-provider HTTP integration, dispatched the six-provider live-smoke matrix, re-downloaded and verified all six public release assets, and preserved the source, logs, evidence, and limitations in the companion bundle. One browser-only UI observation was made; it was classified as blocked because the browser session did not provide Tauri IPC.

The audit included source inventory, build and dependency checks, provider contract/adversarial testing, URL and redirect safety, secret-placement review, migration harnesses, filesystem and checkpoint tests, synthetic media probing, CLI error behavior, process cleanup, UI launch, release verification, rebrand forensics, documentation/licensing review, GitHub Actions review, and the required four-persona adversarial review.

| Verification class | Count/status |
|---|---:|
| Tracked files inspected | 234 |
| Classified components | 61 |
| Python tests | 129 passed |
| Frontend tests | 12 passed |
| Rust tests | 28 passed |
| Providers mock/contract-tested | 9 profiles through shared adapter contracts; custom endpoint exercised against a real loopback mock |
| Providers live-tested | 0 external providers; six workflow jobs explicitly BLOCKED/SKIPPED because secrets were absent |
| Public release assets verified | 6 |
| UI flows manually completed | 0 full Tauri flows; bounded launch succeeded, browser-only flow blocked |

## Source

| Field | Value |
|---|---|
| Repository | `Pavithran-R-A/clipgauge` |
| Protected release tag | `v0.2.0` |
| Protected tag object | `e1745a4114fc6b10211699783883a15979f45f78` |
| Protected tag peeled commit | `cf67df92e34c7ba0bec7b6ce3c69bc32deaa4ca5` |
| Current public main at audit start | `69051be8d8cd6dc269608a30aaff3de4cfddc1b6` |
| QA branch | `qa/a-z-total-verification` |
| QA branch HEAD | `f809c4a9954b5f27e37efb80b2b0748ccdb35e81` |
| Worktree at final-gate capture | Clean before the three final report files were added; report files are QA-only additions |
| Upstream remote | Preserved as `Blueturboguy07/publikclip` |
| Current version | `0.2.0` |
| Bundle ID | `io.github.pavithranra.clipgauge` |
| CLI/package/data root | `clipgauge` / `clipgauge_pipeline` / `.clipgauge` |

The immutable v0.2.0 tag and prior v0.1.0/v0.1.1 tags were not modified. The QA branch contains verification documents only; it does not rewrite the protected release source.

## Core pipeline

| Stage/component | Fresh result | Evidence and limitation |
|---|---|---|
| Ingest | VERIFIED for local staging/probing | Synthetic MP4, MOV, MKV, valid WebM, no-audio, audio-only, zero-byte, corrupt, missing, spaces, and Unicode-path fixtures were exercised. Valid media reached ASR; invalid media produced structured ingest errors. |
| ASR | BLOCKED end-to-end | The bounded real job reached ASR and attempted VAD/model work, but required downloaded speech assets were absent. No transcript quality claim is made. |
| Diarization | BLOCKED end-to-end | Source and tests were inspected; required model assets were not installed. |
| Events | BLOCKED end-to-end | Dependent on audio/model stages. |
| Candidates | BLOCKED end-to-end | Dependent on upstream audio and scoring stages. |
| Scoring | VERIFIED by deterministic contracts and local mock | Provider abstraction, schema translation, cache isolation, retry/error taxonomy, model listing, secret placement, and vision degradation passed. |
| Camera | VERIFIED by static/contract coverage; end-to-end BLOCKED | `cut`, `pan`, and `locked` modes are present; trajectory execution requiring models was not completed. |
| Captions | VERIFIED by source inspection | Actual source presets are `classic`, `beast`, `hormozi`, `minimal`, and `karaoke-pop`; all-preset render acceptance was blocked by the incomplete pipeline. |
| Render | VERIFIED for FFmpeg availability and fixture generation; ClipGauge render BLOCKED | `ffmpeg`/`ffprobe` are available and synthetic containers probe correctly; no ClipGauge finalist render was produced. |
| Editor | VERIFIED by Rust schema tests and migration harness; manual flow BLOCKED | Bounds, timeline, overlay limits, source/animation validation, and retired overlay migration are covered deterministically. |
| Export | VERIFIED by artifact/path tests; manual export BLOCKED | Output path and artifact boundary tests pass; no completed end-to-end clip was available for visual export review. |

The valid synthetic 5-second video run was deliberately bounded. It performed ingest and entered ASR but timed out while model/VAD assets were unavailable. This is a truthful dependency-readiness result, not a pipeline-success result.

## Job lifecycle

| Lifecycle feature | Result | Evidence |
|---|---|---|
| Start | VERIFIED by queue/protocol tests and CLI job creation | `test_queue.py`, protocol tests, and input matrix |
| Cancel | VERIFIED by process-manager tests; real UI cancellation BLOCKED | Rust process-manager tests; no full desktop interaction |
| Resume | VERIFIED by checkpoint/queue tests; restart UX BLOCKED | Queue focused suite |
| Stale recovery | VERIFIED by deterministic queue tests | Checkpoint/lease tests |
| Concurrency | VERIFIED by queue tests | Duplicate heavy-job protection and stage lease tests |
| Restart after interruption | PARTIAL | Controlled checkpoint tests pass; forced desktop close/reopen was not executed |
| Failure cleanup | VERIFIED for bounded test processes | No ClipGauge/FFmpeg/ASR/Vite process remained after cleanup; temporary UI processes were explicitly terminated |

## Providers

The shared provider contract suite covers URL policy, cache identity, schema translation, secret placement, vision degradation, image translation, normalized error taxonomy, redirect safety, model listing, migration, local presets, and custom authentication. A local OpenAI-compatible mock server was exercised through the real CLI for bearer, API-key-header, and custom-secret-header modes; text structured output and model listing passed, an unauthenticated request normalized to `AUTH_INVALID`, and unsafe URL forms were rejected. Vision adapter behavior passed under an explicitly vision-capable mock profile; text-only profiles correctly record degradation rather than claiming vision.

| Provider | Implementation inspection | Mock/contract | Live | Text | Structured JSON | Vision | Model discovery | Failure handling | Secret safety | Overall |
|---|---|---|---|---|---|---|---|---|---|---|
| Gemini | PASS | Shared adapter contracts PASS | BLOCKED: no credential | PASS by shared contract | PASS by shared contract | Capability-aware; not live-proven | PASS by shared contract | PASS | PASS | CONDITIONAL |
| OpenRouter | PASS | Shared adapter contracts PASS | BLOCKED: no credential | PASS by shared contract | PASS by shared contract | Capability-aware; not live-proven | PASS by shared contract | PASS | PASS | CONDITIONAL |
| Groq | PASS | Shared adapter contracts PASS | BLOCKED: no credential | PASS by shared contract | PASS by shared contract | Capability-aware; not live-proven | PASS by shared contract | PASS | PASS | CONDITIONAL |
| Cloudflare Workers AI | PASS | Shared compatible-adapter contracts PASS | BLOCKED: token/endpoint absent | PASS by shared contract | PASS by shared contract | Capability-aware; not live-proven | PASS by shared contract | PASS | PASS | CONDITIONAL |
| Hugging Face | PASS | Shared compatible-adapter contracts PASS | BLOCKED: no credential | PASS by shared contract | PASS by shared contract | Capability-aware; not live-proven | PASS by shared contract | PASS | PASS | CONDITIONAL |
| Cerebras | PASS | Shared compatible-adapter contracts PASS | BLOCKED: no credential | PASS by shared contract | PASS by shared contract | Curated preset is text-only by default | PASS by shared contract | PASS | PASS | CONDITIONAL |
| Ollama | PASS | Local loopback contract PASS | BLOCKED: executable/server absent | PASS | PASS where supported | Degrades when unsupported | PASS by contract | PASS | PASS | CONDITIONAL |
| LM Studio | PASS | Loopback compatible contract PASS | BLOCKED: runtime absent | PASS by shared contract | PASS by shared contract | Capability-aware | PASS by shared contract | PASS | PASS | CONDITIONAL |
| Custom OpenAI-compatible | PASS | Real loopback mock PASS | Not applicable to arbitrary remote endpoint | PASS | PASS | PASS in explicit vision-capable mock; default custom profile reports capability-dependent status | PASS | PASS | VERIFIED LOCALLY |

No automatic cross-provider failover was observed or claimed. Provider free-tier language remains conservative and is not interpreted as a promise of permanent or unlimited access.

## Windows desktop

| Acceptance item | Result |
|---|---|
| Installer | BLOCKED: Linux host cannot execute Windows NSIS |
| First run | BLOCKED |
| Provider setup | BLOCKED |
| Real job | BLOCKED |
| Edit | BLOCKED |
| Export | BLOCKED |
| Cancel | BLOCKED |
| Resume | BLOCKED |
| Uninstall and data preservation | BLOCKED |

The public Windows asset is a valid PE32 NSIS installer and its checksum passes. No SmartScreen, installation, launch, or uninstall claim is made. The installer is unsigned as documented by the release materials.

## Linux

Linux source gates passed: version consistency, Python tests, frontend tests/build, Rust check/tests/fmt, Python/npm advisory checks, and release asset verification. The Debian package is a valid Debian binary package and its checksum passes. A bounded Tauri development launch compiled and started the native app on Linux with a display; the launch was terminated by the audit timeout and left no application/build child process. GTK accessibility-bus and DRI3 warnings were observed in the sandbox and are environment warnings, not interpreted as product failures.

## macOS ARM

GitHub macOS ARM qualification was green in the public workflow history for the release/main sequence. No local macOS ARM host was available. The result is **native qualification evidence**, not local UX, signing, or notarization evidence.

## macOS Intel

GitHub macOS Intel qualification was green in the public workflow history for the release/main sequence. No local macOS Intel host was available. The result is **native qualification evidence**, not local UX, signing, or notarization evidence.

## Security

| Security surface | Result |
|---|---|
| Filesystem traversal, symlinks, absolute paths, job root | VERIFIED by Rust/queue tests and source review |
| IPC command boundary | VERIFIED by Rust compilation/tests and restrictive command signatures |
| Secret vault | VERIFIED by deterministic Rust tests/source review; actual Windows keyring BLOCKED |
| Provider URLs | VERIFIED; dangerous schemes, remote HTTP without explicit approval, embedded credentials, and unsafe query placement rejected |
| Redirects | VERIFIED; authenticated requests do not follow redirects |
| CSP | VERIFIED by frontend security tests |
| Asset protocol | VERIFIED by frontend security tests and source review |
| Support-bundle redaction | VERIFIED by source/tests; live Tauri support-bundle generation BLOCKED |
| Supply chain | Python/npm advisory gates clean; cargo-audit exits 0 with 17 transitive warnings including GTK3 maintenance warnings and glib RUSTSEC-2024-0429 |

No API key was placed in a URL, argv, normal provider snapshot, cache identity, or logged live-smoke output. GitHub secret scan is green on current main. The local scanner binary `gitleaks` was not installed; the public GitHub secret-scan workflow remains the authoritative repository scan evidence.

## Privacy

Local providers are described as loopback/local and cloud providers as external destinations. The Tauri privacy summary states that telemetry is disabled by default, source media remains in the managed local job directory, cloud providers receive transcript/scoring material and selected frames only when the selected model advertises vision, and URL/Pexels/Instagram/model downloads are separate network activities. These statements were verified by source inspection and frontend tests. Interactive UI disclosure was not completed because the Tauri IPC bridge was unavailable to the browser-only session.

Offline tests were partially verified statically and through local preflight. A local video with an installed local provider should be able to operate subject to installed models, but this host had neither Ollama nor LM Studio nor the required model assets. YouTube URL, cloud provider, and missing-model offline recovery were therefore not executed live.

## Migration: v0.1.x to v0.2.0

The fresh migration harness passed legacy Gemini and Ollama settings, provider snapshot reconstruction, secret exclusion from serialized settings, round-trip idempotence, and editor overlay migration. Rust source inspection verifies collision-safe copy, symlink refusal, source preservation, and a completion marker. Actual desktop startup migration from a real Windows keyring and a real `.publikclip` tree was not executed on this Linux host. The old data root is preserved rather than deleted automatically.

## Rebranding

The required report is `docs/qa/AZ_REBRAND_VERIFICATION.md`. Every remaining legacy occurrence was classified as legal/provenance, migration compatibility, or historical audit. No accidental current-product branding was found in the normal ClipGauge title, CLI/package identifiers, current data root, provider UI, or About identity. Windows installer UI was not locally inspected.

## Release

A fresh download of all six public v0.2.0 assets passed `SHA256SUMS`. The assets were:

| Asset class | Verification |
|---|---|
| Linux Debian package | `dpkg-deb --info` succeeded; checksum PASS |
| Windows NSIS installer | PE32/NSIS identified; checksum PASS; execution BLOCKED on Linux |
| SBOM | CycloneDX structure and component array PASS |
| Provenance | Downloaded and inspected; no signing claim inferred |
| Attestation status | Downloaded and inspected; no platform signing/notarization claim inferred |
| Checksums | All six downloaded assets `OK` |
| Tag | Annotated tag object and peeled commit recorded; protected tag unchanged |

The release is non-draft and non-prerelease. No credentials were found in release metadata. Release binaries are unsigned where documented; this is not represented as a signing or notarization success.

## Performance

The observed test machine was Ubuntu 24.04.4 LTS, x86_64, 3.8 GiB RAM, 40 GiB root filesystem with approximately 17 GiB free at observation, and no GPU claim. A synthetic 5-second 640×360 video with audio was used. The bounded job reached ingest and ASR startup but did not complete because required model/VAD assets were unavailable. GNU time recorded 45.00 seconds wall time, 2% CPU, and 55,732 kB maximum resident set size for that incomplete run. These are labeled **Observed on this machine** and are not universal minimum or performance claims.

## Bugs

| ID | Severity | Component | Reproduction | Status | Fix SHA |
|---|---|---|---|---|---|
| AZ-001 | MEDIUM | Full Rust Clippy quality gate | Run `cargo clippy --all-targets --all-features -- -D warnings` from `app/src-tauri`; it exits 101 on `items_after_test_module`, unused exported `redact_with_secrets`, and widened provider-aware command argument counts. | Confirmed code-quality finding; repository CI uses narrow documented allowances. Recommend smallest v0.2.1 cleanup and rerun all gates. | — |
| AZ-002 | LOW | CLI version surface | Run `uv run clipgauge --version`; argparse reports that the required `cmd` argument is missing. No `--version` flag was found in the current tracked documentation. | Confirmed interface omission/opportunity. Recommend `--version` in v0.2.1 or document an alternate version command. | — |
| AZ-003 | MEDIUM | Transitive Rust dependency health | Run `cargo audit`; it exits 0 but reports 17 warnings, including unmaintained GTK3 bindings and unsound `glib` RUSTSEC-2024-0429. | Open supply-chain maintenance risk; no direct application exploit was demonstrated. Review Tauri/GTK dependency path in v0.2.1. | — |

No blocker or high-severity defect was confirmed. The missing Windows/live-provider/full-job tests are **blocked scope**, not fabricated failures. No protected v0.2.0 source or release tag was modified.

## Blocked tests

| Test area | Exact reason |
|---|---|
| Windows install/launch/uninstall/reinstall | Only Linux x86_64 was available; Windows NSIS execution requires Windows. |
| Windows full UI job/edit/export/cancel/resume | Same host limitation plus no Windows desktop session. |
| Cloud live providers | GitHub Actions secrets were absent; workflow explicitly reported six `BLOCKED/SKIPPED` results and made no inference request. |
| Ollama | Executable and loopback server unavailable. |
| LM Studio | Runtime unavailable. |
| Full local ClipGauge video completion | Pinned ASR/VAD and pipeline model assets were not installed; bounded run stopped at ASR/model preparation. |
| Real render/preset visual review | Dependent on completed scoring/camera stages. |
| Pexels live lookup | No owner credential in a secure vault. |
| Instagram/Meta live OAuth/sync | No owner credential and no publishing authorization; deterministic tests only. |
| Actual Windows keyring/support-bundle secret sweep | Windows OS and keychain unavailable. |
| Local macOS UX | No macOS host; GitHub native qualification only. |
| Interactive Tauri accessibility/window-size review | Browser-only session lacked Tauri IPC; bounded native launch was not connected to an interaction harness. |

## Unknown and unproven areas

The audit does not prove absence of all bugs. It does not prove Windows user experience, Windows credential-vault behavior, macOS local behavior, cloud-provider live success, permanent free-tier availability, full transcript/diarization/camera quality, cancellation at every native stage, restart recovery after a real forced close, performance on other hardware, or signing/notarization. It also does not certify formal legal compliance; it records source-level AGPL and attribution evidence only.

The browser-only blank boot view is not classified as a frontend defect because `App.tsx` intentionally waits for Tauri `setupState()` and the browser cannot provide the Tauri invoke bridge. The native Tauri process did compile and start, but the audit did not have a native UI automation channel to complete the subsequent flow.

## Final verdict answers

1. **Does the normal Windows installer launch?** Not proven; BLOCKED on Linux.
2. **Can a new user complete a full video job?** Not proven in this environment; the automated source/runtime path is present, but model assets blocked completion.
3. **Can a clip be edited and exported?** Deterministic editor and artifact contracts pass; a real rendered clip edit/export was not completed.
4. **Can a job be cancelled safely?** Process-manager and queue tests pass; live UI cancellation is not proven.
5. **Can it resume after interruption?** Checkpoint/resume tests pass; forced desktop restart is not proven.
6. **Does OpenRouter Free work live?** BLOCKED; no credential and no live inference.
7. **Does Gemini work live?** BLOCKED; no credential and no live inference.
8. **Does Groq work live?** BLOCKED; no credential and no live inference.
9. **Does Cloudflare work live?** BLOCKED; token and account endpoint absent.
10. **Does Hugging Face work live?** BLOCKED; no credential and no live inference.
11. **Does Cerebras work live?** BLOCKED; no credential and no live inference.
12. **Does Ollama work live?** BLOCKED; executable/server unavailable.
13. **Does LM Studio work live?** BLOCKED; runtime unavailable.
14. **Does a custom OpenAI-compatible endpoint work?** YES against a local loopback mock through the real CLI for supported auth modes, model listing, structured output, and capability-aware vision; no remote custom endpoint was tested.
15. **Are secrets safe?** Contract and source evidence indicate yes for tested boundaries; Windows keyring and live support-bundle generation remain unproven.
16. **Are all old-brand references intentional?** Yes, based on fresh tracked-tree classification; Windows installer UI was not visually inspected.
17. **Are release artifacts valid?** Yes: all six assets downloaded, checksummed, and structurally inspected; unsigned/notarization limitations remain.
18. **Are there any blocker/high bugs?** No confirmed blocker or high bug. Medium findings AZ-001 and AZ-003 remain open; AZ-002 is low.
19. **What is still not proven?** Windows UX/install, live external providers, full local job completion, visual output quality, real cancellation/restart, and platform-local UX.
20. **Is ClipGauge ready for ordinary external users?** Conditionally, for users who can satisfy the documented runtime/model/provider requirements and accept unsigned artifacts; a v0.2.1 quality pass is recommended before calling the entire A-to-Z matrix complete.

## References

[1]: https://github.com/Pavithran-R-A/clipgauge "ClipGauge public repository"  
[2]: https://github.com/Pavithran-R-A/clipgauge/releases/tag/v0.2.0 "ClipGauge v0.2.0 release"  
[3]: https://github.com/Pavithran-R-A/clipgauge/pull/5 "ClipGauge v0.2.0 provider PR"

All execution details, raw logs, synthetic-media probe outputs, workflow records, release downloads, and supporting documents are included in `CLIPGAUGE_AZ_TOTAL_VERIFICATION_BUNDLE.zip`.
