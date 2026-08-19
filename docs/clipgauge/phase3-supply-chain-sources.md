# Phase 3 supply-chain source findings

The official yt-dlp GitHub releases page identifies stable release **2026.07.04**. Its release assets expose SHA-256 digests, including `yt-dlp_linux` digest `6bbb3d314cde4febe36e5fa1d55462e29c974f63444e707871834f6d8cc210ae`, `yt-dlp.exe` digest `52fe3c26dcf71fbdc85b528589020bb0b8e383155cfa81b64dd447bbe35e24b8`, and `yt-dlp_macos` must be verified from the same release asset list before being added to the manifest. Source: https://github.com/yt-dlp/yt-dlp/releases/tag/2026.07.04

The official FFmpeg download page states that FFmpeg publishes source code and points users to third-party distributors for compiled binaries. It also states that FFmpeg releases are cryptographically signed with the project public PGP key. ClipGauge therefore must not claim an official FFmpeg binary hash unless the chosen distributor’s immutable artifact and checksum/signature are independently retrieved and recorded. Source: https://ffmpeg.org/download.html

Initial trust assumption for ClipGauge: source downloads are staged, bounded, hash-verified against checked-in manifest values obtained from authoritative release metadata, archive members are validated before extraction, and the previous verified installation remains in place on failure. Mutable `latest` URLs are not acceptable for managed runtime installation.

The BtbN FFmpeg-Builds release page identifies `autobuild-2026-08-18-15-03`, commit `d5e1920`, and publishes `checksums.sha256`. The selected Windows GPL archive is `ffmpeg-N-126207-g21bbd98e7b-win64-gpl.zip` with SHA-256 `0dfc1c04a5b8c15e56e3e2245d3b0a1fb5f22242591e1b2c4a1cb6fa0cd0230b`, retrieved from the immutable release checksum asset. Source: https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2026-08-18-15-03

ClipGauge does not install an unpinned macOS FFmpeg archive. If no verified system or bundled binary is available, caption capability degrades explicitly rather than triggering a mutable download.
