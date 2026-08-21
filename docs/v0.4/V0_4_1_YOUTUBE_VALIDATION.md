# ClipGauge v0.4.1 YouTube Validation

**Overall status:** PASS for the project-owned managed-provider architecture and deterministic validation path; BLOCKED for live public YouTube smoke from the GitHub/datacenter environment unless a permitted network result is recorded.

## Architecture preserved

The v0.4.1 release keeps the managed `core:youtube` path: pinned yt-dlp, portable Node.js, and the pinned bgutil PO-token provider supervised as a loopback-only service. The provider is health-checked before yt-dlp use, its lifecycle is owned by ClipGauge, and browser-session cookies remain an explicit opt-in rather than a default read.

| Requirement | Status | Evidence |
|---|---|---|
| Managed yt-dlp inventory | PASS | Existing managed catalog and setup inventory expose the pinned yt-dlp executable and revision. |
| Portable Node inventory | PASS | The `core:youtube` group includes the managed Node runtime rather than requiring a system Node installation. |
| bgutil revision pin and provenance | PASS | The managed provider revision and dependency provenance remain pinned and documented. |
| Loopback-only provider boundary | PASS | The compatibility provider binds to loopback and is supervised by the local pipeline. |
| Provider health check | PASS | The YouTube compatibility module performs readiness/health validation before invoking yt-dlp. |
| yt-dlp provider discoverability | PASS | The deterministic self-test path verifies provider discoverability and integration without claiming public-video success. |
| Browser-cookie default behavior | PASS | Browser cookies are not read by default; `--cookies-from-browser` is explicit and recorded in job settings. |
| Live public YouTube retrieval | BLOCKED | No live PASS is claimed from a datacenter environment whose YouTube egress, login, age, region, and provider policy may differ from the owner’s network. |

## Error classification

A live failure must be retained as a creator-facing classification such as provider-not-ready, login-required, age-restricted, private, region-blocked, unavailable, or network-blocked. A generic HTTP failure must not be converted into a claim that the provider solved access. The deterministic health/discovery checks and live public retrieval are separate gates.

## Decision

The v0.4.1 implementation preserves the correct managed yt-dlp + Node + bgutil direction and keeps explicit opt-in browser authentication. Live public YouTube remains BLOCKED by environment unless a real permitted-network run is captured; it is not relabeled as PASS.

## References

[1]: ../../pipeline/clipgauge_pipeline/ingest/ytdlp.py "Managed yt-dlp integration"
[2]: ../../pipeline/clipgauge_pipeline/ingest/youtube_compat.py "Managed YouTube compatibility provider"
[3]: V0_4_YOUTUBE_VALIDATION.md "Prior deterministic YouTube validation"
[4]: ../../pipeline/runtime-manifest.json "Pinned runtime and asset manifest"
