# ClipGauge v0.4.1 Windows E2E Qualification

**Overall status:** BLOCKED in the current sandbox; exact-tag `windows-latest` GitHub Actions execution is the authoritative acceptance environment.

## Required Windows checks

| Check | Status | Evidence requirement |
|---|---|---|
| Fresh NSIS installer installs | BLOCKED | Native exact-tag Windows runner must perform the silent install. |
| Installed app launches | BLOCKED | Native installed-EXE launch must be captured by the workflow. |
| App data directory is writable | BLOCKED | Packaged-resource environment must write and inspect the managed home. |
| Setup inventory command works from packaged resources | BLOCKED | Windows workflow must invoke inventory through the packaged application resources. |
| Managed FFmpeg self-test | BLOCKED | Windows-managed FFmpeg acquisition and caption-capable self-test must pass natively. |
| Managed yt-dlp inventory | BLOCKED | Exact-tag packaged inventory must resolve the managed executable. |
| YouTube compatibility inventory | BLOCKED | Node/bgutil assets must install or be fully verified in the packaged environment. |
| Version and branding | BLOCKED | Installed application must report ClipGauge v0.4.1 and correct executable identity. |
| Clean shutdown and process cleanup | BLOCKED | Workflow must confirm no ClipGauge-owned leftover process. |

## Workflow design

The strengthened Windows workflow runs the full Python suite without the former runtime/stage exclusions, builds the exact-tag NSIS artifact, performs silent installation and launch checks, validates the managed-resource layout, and inspects process cleanup. This document does not turn the workflow definition into a native PASS; the result must come from an actual Windows runner URL and logs.

## Decision

Windows acceptance is a release-blocking external gate. It is intentionally marked BLOCKED until the exact-tag workflow completes, and it must not be replaced by Linux or macOS evidence.

## References

[1]: ../../.github/workflows/windows.yml "Windows qualification workflow"
[2]: V0_4_WINDOWS_E2E.md "Prior Windows acceptance requirements"
