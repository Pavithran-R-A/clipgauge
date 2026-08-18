# ClipGauge Stage 1A Application Paths

## Source of truth

The desktop Rust layer owns the application root as `dirs_home()/.publikclip`. The desktop bridge no longer accepts an arbitrary `PUBLIKCLIP_HOME` override. Direct Python CLI runs may still set `PUBLIKCLIP_HOME` for isolated development/tests; the Tauri process explicitly passes its Rust-owned root to the sidecar so desktop state and asset scope remain aligned. The upstream `.publikclip` name is intentionally preserved in Stage 1A; data-root migration belongs to the later rebrand/migration stage.

| Environment | Resolved desktop root | Notes |
|---|---|---|
| Windows | `%USERPROFILE%\\.publikclip` | Rust falls back to `USERPROFILE` when `HOME` is absent |
| macOS | `$HOME/.publikclip` | Same app-root contract; native app-data migration is deferred |
| Linux/dev | `$HOME/.publikclip` | Direct Python tests may use `PUBLIKCLIP_HOME`; Rust desktop commands do not |
| Legacy upstream | `.publikclip` | Preserved for compatibility; no `.clipgauge` rename in Stage 1A |

## Directory policy

| Directory | Contains | WebView-readable? |
|---|---|---|
| `jobs/<generated-job-id>/` | Job checkpoints and bookkeeping | No; only child media directories are scoped |
| `jobs/<generated-job-id>/clips/` | Final MP4 outputs and generated hook thumbnails | Yes, for validated media outputs |
| `jobs/<generated-job-id>/media*.mp4` | Managed source/CFR video used by ClipEditor | Yes, for media playback only |
| `jobs/<generated-job-id>/overlays/` | User-approved overlay images | Yes, because they are job-owned render inputs |
| `jobs/<generated-job-id>/t2frames/` | Scoring evidence frames | No |
| `jobs/<generated-job-id>/diagnostics/` | Redacted traces and sidecar diagnostics | No |
| `models/`, `bin/` | Model weights and managed executables | No |
| `secrets.json`, `instagram.json` | API keys, OAuth tokens, connection state | Never |
| `ig_thumbs/` | Cached Instagram thumbnails used by Loop | Yes, through the explicit narrow thumbnail scope |
| `db.sqlite3` | Job bookkeeping | Never |

The Tauri asset protocol allows only `$HOME/.publikclip/jobs/*/clips/**`, `$HOME/.publikclip/jobs/*/media*.mp4`, `$HOME/.publikclip/jobs/*/overlays/**`, and `$HOME/.publikclip/ig_thumbs/**`. The frontend receives sanitized artifact status and managed media paths; it does not receive the application root from `job_results`. Checkpoints, secrets, models, executables, the database, scoring frames, and diagnostics are outside the explicit asset scope.

## Compatibility and migration boundary

Stage 1A intentionally does not rename `.publikclip` or migrate data. A later migration must define discovery, copy/rollback, permissions, schema versions, legacy environment behavior, and asset-scope updates before any `.clipgauge` path is introduced.
