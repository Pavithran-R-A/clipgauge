# ClipGauge v0.4.0 YouTube Validation

**Deterministic provider status:** PASS. **Live smoke status:** `ENVIRONMENT_BLOCKED`; not counted as PASS.

## Managed compatibility path

The v0.4.0 YouTube path uses the managed `core:youtube` group. It contains the pinned yt-dlp executable, portable Node.js v24.19.0, and the bgutil PO-token provider at revision 1.3.2. The supervisor binds the provider to loopback, owns its lifecycle, performs health checks, and stops the service when it is no longer required. The yt-dlp self-test verifies that the managed provider is discoverable rather than merely displaying an inventory row.

| Check | Result | Evidence |
|---|---|---|
| yt-dlp is represented in the managed inventory | PASS | `pipeline/clipgauge_pipeline/ingest/ytdlp.py`, setup inventory, runtime manifest |
| Portable Node.js is pinned and managed | PASS | `pipeline/runtime-manifest.json`, managed runtime setup path |
| bgutil provider revision is pinned | PASS | `pipeline/clipgauge_pipeline/ingest/youtube_compat.py`, v0.4 inventory |
| Provider binds only to loopback | PASS | Supervisor health and endpoint validation in `youtube_compat.py` |
| Provider health is checked | PASS | Managed supervisor health-check path |
| yt-dlp can discover the provider | PASS | Deterministic self-test path in the YouTube compatibility module |
| Browser cookies are read by default | PASS — they are not | Only an explicit allow-listed `--cookies-from-browser` option injects browser authentication |

## Live smoke classification

The live public-video smoke was classified **`ENVIRONMENT_BLOCKED`** because GitHub/datacenter egress to YouTube was subject to bot-check/rate-limit policy in the validation environment. This is an external environment classification, not a provider success. The smoke is therefore not counted as a release PASS and no claim is made that PO tokens guarantee every video will work.

The deterministic provider self-test remains the meaningful project-owned gate. It exercises provider installation, discoverability, loopback health, and yt-dlp integration without requiring a cloud credential or relying on a particular datacenter’s treatment of YouTube traffic.

## Authenticated flow

Authenticated retrieval is separate and opt-in. The CLI accepts only the supported browser-session allow-list and records the selected browser in the job snapshot. No browser cookies are read during ordinary local-file runs or public URL runs, and raw cookie material is not persisted as ordinary ClipGauge configuration or included in support bundles.

## Error classifications

The ingest path distinguishes attestation/PO-token requirement, sign-in required, private, age-restricted, regional restriction, unavailable/deleted, network failure, extractor failure, and rate-limit/bot-check outcomes. Each classification maps to a human-readable action rather than exposing an opaque raw extractor exception.

## Release interpretation

The managed YouTube component is implemented and deterministically self-tested. The remaining limitation is the external live-smoke environment, which is documented honestly and must not be relabeled as `LIVE_PASS`. A future run from a permitted network may produce `LIVE_PASS` or a real provider failure; neither outcome changes the requirement that deterministic provider health and discoverability remain release-blocking.
