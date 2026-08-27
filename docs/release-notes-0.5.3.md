# ClipGauge v0.5.3 release notes

## YouTube compatibility contract

YouTube URL import is a best-effort compatibility feature. **YouTube tools ready** means the pinned yt-dlp runtime, Node runtime, released bgutil provider source, plugin, and loopback health check are verified. **YouTube download tested** is a separate state that is recorded only after an unauthenticated public transfer completes and the resulting media passes probing. A provider `/ping` response is not treated as proof that YouTube will accept a media request.

The managed provider is the official `Brainicism/bgutil-ytdlp-pot-provider` source archive from tag `1.3.2`, pinned by source URL, archive SHA-256, and upstream provenance. The server and plugin are built or copied from that same archive. ClipGauge uses the managed bgutil route first, then a documented yt-dlp `mweb` guest-client alternative after an attestation-specific failure. It never enables `formats=missing_pot`.

If YouTube rejects media transfer during playback verification, the app explains that ClipGauge itself is ready and offers the safe alternatives: retry later or import the video file directly. Optional WPC browser-assisted compatibility is described separately and is never silently installed or launched. If a separately installed compatible WPC provider and local Chrome/Chromium are detected, any browser launch requires explicit user approval; normal ClipGauge operation never reads browser profiles, cookies, accounts, or credentials.

The latest successful public compatibility check stores only its timestamp, yt-dlp version, provider version, and method. A subsequent attestation-specific failure invalidates the public-verification claim without deleting the verified local dependencies.

## Core workflow

The local-file creator workflow remains the supported core path, including local scoring, Review playback, edit persistence, rerender, export, reopen, and cancellation. These workflows do not depend on YouTube availability.
