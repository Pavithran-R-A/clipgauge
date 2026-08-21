# ClipGauge v0.4.0 Windows E2E Evidence

**Status:** PENDING NATIVE CI ACCEPTANCE; no local Linux result is presented as Windows acceptance.

## Required gate

The v0.4.0 specification requires a fresh `windows-latest` runner with no preinstalled project state. The release workflow must build the unsigned Windows x64 NSIS installer, install it silently, launch the installed executable, confirm the expected version and executable identity, and inspect the clean managed-runtime layout. The required checks include a writable data directory, setup inventory, managed FFmpeg path, managed yt-dlp, YouTube compatibility inventory, absence of historical `publikclip` runtime identity leakage, clean shutdown, and no zombie ClipGauge-owned subprocess.

## Workflow evidence

The repository contains two native Windows workflows: `.github/workflows/windows.yml` for the regular Windows gate and `.github/workflows/release.yml` for the exact-tag Windows release job. Both target `windows-latest`; the release workflow names the job **Build unsigned Windows x64 NSIS installer** and includes Python tests, frontend gates, Rust checks, fresh NSIS packaging, silent installation, inspection, and launch.

| Acceptance item | Current status | Evidence path |
|---|---|---|
| Fresh Windows runner | PENDING until GitHub Actions run | `.github/workflows/windows.yml`, `.github/workflows/release.yml` |
| NSIS build | PENDING native run | Windows workflow build steps |
| Silent installation | PENDING native run | Windows workflow installation step |
| Installed EXE launch and version | PENDING native run | Windows workflow launch/inspection step |
| Writable managed home | PENDING native run | Windows acceptance script and runtime layout checks |
| Managed FFmpeg/yt-dlp/YouTube inventory | PENDING native run | Setup inventory inspection |
| Clean shutdown and no zombies | PENDING native run | Windows acceptance process check |

## Linux controlled substitute

A real model-backed E2E completed on Linux using the isolated managed home and the same managed asset catalog. It reached render and produced an H.264/AAC MP4 with 540×960 geometry and 21.1 seconds of duration. This validates the Python pipeline contract and local asset lifecycle, but it does not validate Windows installer behavior, Windows path semantics, NSIS registration, or Windows process shutdown.

## Release decision

Windows acceptance remains a release-blocking CI responsibility under the v0.4.0 specification. The release checklist must be updated only from the actual exact-tag GitHub Actions result. No claim of Windows PASS is made in this document before that result exists.
