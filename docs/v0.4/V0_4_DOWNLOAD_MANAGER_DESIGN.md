# ClipGauge v0.4 Managed Download Manager Design

## Goal

The manager is the only project-owned path for downloading or installing a runtime/model asset. Subsystems declare asset records and installation adapters; they do not implement their own progress, consent, retry, or verification logic.

## Asset record

A managed asset record contains `asset_id`, `group_id`, `display_name`, `purpose`, `required`, `one_time_download`, `source_url` or immutable snapshot source, `source_revision`, `license`, `provenance_url`, `download_bytes`, `installed_bytes`, `sha256` or a per-file snapshot manifest, `archive_type`, `destination_relpath`, `install_layout`, `platform`, `architecture`, `cache_key`, and `dependencies`. Destinations are resolved below the ClipGauge managed root and are rejected if absolute, traversing, symlinked, or outside the declared group root.

## State machine

`NOT_INSTALLED → NEEDS_CONSENT → QUEUED → DOWNLOADING → VERIFYING → INSTALLING → READY`. A verified existing artifact may enter `REUSED` after its hash and capability self-test pass. A hash, layout, or capability failure enters `NEEDS_REPAIR`. Network and non-integrity failures enter `FAILED` with retryability. User cancellation enters `CANCELLED`; a safe `.partial` may remain resumable but is never treated as installed. A running job holds an asset lease so optional removal is refused until the lease is released.

## Download protocol

Before starting, the manager checks free space for the download plus temporary staging and installed expansion. It uses HTTP Range only when the server returns a compatible `206` response and a known content identity; a `200` response after a Range request discards the partial and restarts cleanly. A changed `ETag`/revision or invalid partial restarts cleanly. Every write is bounded by expected bytes plus a small protocol allowance, hashed during verification, flushed, and atomically renamed. A content-length mismatch, overflow, checksum mismatch, archive traversal, duplicate executable, symlink, or failed self-test never replaces a last-known-good copy.

The manager owns a cancellation event and closes the active response/process when set. The caller receives terminal `CANCELLED` state, and completed assets remain ready. Retry creates a new attempt ID but preserves the asset identity. Partial cleanup is policy-driven: safe resumable HTTP partials may be retained, while malformed/over-limit/corrupt partials are removed.

## Consent groups

A grouped consent record stores the exact asset IDs, required and optional byte totals, installed total, free-space snapshot, managed location, timestamp, application version, and user choice. It is invalidated when the asset revision, checksum, download size, or required group changes. A consent record never authorizes a different URL, revision, category, or asset without a new prompt. The UI exposes `DOWNLOAD REQUIRED`, `DOWNLOAD OPTIONAL`, `CANCEL`, and `REVIEW DETAILS` before work begins.

## Progress event

Every emitted event includes:

```json
{
  "event": "asset-progress",
  "protocol_version": 3,
  "asset_id": "model:asr:faster-whisper-large-v3-turbo",
  "display_name": "Speech recognition",
  "operation": "Downloading model files",
  "bytes_done": 1120000000,
  "bytes_total": 1617884929,
  "bytes_per_second": 8400000,
  "fraction": 0.6924,
  "eta_seconds": 59.1,
  "elapsed_seconds": 133.8,
  "one_time_download": true,
  "cached": false,
  "state": "DOWNLOADING"
}
```

Unknown progress uses `bytes_total: null`, `fraction: null`, `eta_seconds: null`, and a heartbeat timestamp. The UI must not synthesize a percentage.

## Installation adapters

File assets install by verified atomic replacement. Archive assets download to a sibling partial archive, verify the archive, extract into a new staging directory with safe member validation, run capability/version tests, then swap the completed version directory. Snapshot assets install every declared file into a staging directory, verify the per-file manifest and complete file set, then swap the snapshot directory. Existing verified versions are not deleted automatically; migration only writes a marker after successful non-destructive reuse/copy.

## Test obligations

The manager must have deterministic tests for success, progress, speed/ETA, disk preflight, grouped consent, cancellation, retry, Range resume, no-Range restart, wrong length, bad hash, archive traversal/symlink, atomic swap, cache reuse, repair, and migration. Each subsystem must add only adapter-level tests for its own source/layout/capability behavior.
