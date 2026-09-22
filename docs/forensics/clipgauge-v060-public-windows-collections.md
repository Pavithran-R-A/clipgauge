# ClipGauge v0.6.0 Public Windows Collections Forensics

Date: 2026-09-21

## Scope

This record covers the public v0.6.0 Windows qualification, the affected
legacy score-only job, creator collection rendering, and uninstall metadata.
It excludes secrets, cookies, and media contents.

## Release and upgrade evidence

- Public installer: `ClipGauge_0.6.0_Windows_x64_NSIS.exe`
- Installer size: `15,940,504` bytes
- Installer SHA256: `ec95efda2f43b0fc06089b958a93ef63d96a21cebd231b90b2ba565faedf08e2`
- Upgrade path: public v0.5.22 installation upgraded in place to v0.6.0
- App/About version after upgrade: `0.6.0`
- Installed executable version after upgrade: `0.6.0`
- v0.6.0 tag object: `e63b4fd2baedf86a7f5a408050b34ac0c9203380`
- v0.6.0 peeled commit: `5043f2a5eaac1f90814267250c564a9ac85b9f46`

The v0.6.0 tag and assets remain immutable.

## Affected job

Job: `20260918-170408-e53b27`

The job contains `score.json`, `render.json`, and `collections.json`.
It has no `enrich.json`. The score checkpoint contains six finalist clips.
None of those score clips contains `clip_id`. Render outputs contain six
outputs with explicit indexes `0` through `5`, paths under `clips/`, and no
output `clip_id`. The collection references two deterministic clip IDs but
has `render_path: null`.

The artifact manifest identifies the stage producer as `0.5.21`.
The exact originating application version is unavailable. The evidence shows
pre-v0.6.0 artifact lineage carried through later qualification.

## Root-cause findings

### Legacy collection identity

Creator UI selection depends on clip identity. Legacy score-only checkpoints
do not carry identity, while the creator state resolver only selected the
first usable checkpoint. This left legacy clips without selectable IDs.

### Collection render assembly

The persisted render checkpoint explicitly maps each output through its
`clip` index. Creator collection loading did not merge these outputs into the
canonical creator clips. Collection render therefore lacked reliable source
paths for real collection clips.

### Sidecar failure visibility

The Rust sidecar wrapper accepted a final JSON response even when it reported
`ok: false`. The React render handler also treated a response without `path`
as a non-error. A failed or incomplete render could therefore look successful.

The v0.6.0 qualification surfaced no sanitized sidecar error. The collection
checkpoint remained at `render_path: null`, and no new collection artifact
was produced by the attempted render.

### Uninstall registry metadata

The active entry was:

- Hive/key: `HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\ClipGauge`
- `DisplayVersion`: `0.5.22`
- `InstallLocation`: current v0.6.0 installation directory
- `UninstallString`: current v0.6.0 `uninstall.exe`
- `DisplayIcon`: current v0.6.0 executable
- `Publisher`: `github`

No duplicate ClipGauge entries were found in HKCU, HKLM 64-bit, or HKLM
WOW6432Node 32-bit locations. The installed executable reported `0.6.0`,
so the defect is stale active uninstall metadata after in-place upgrade.

The generated NSIS script already writes `DisplayVersion` through the
generated `${UNINSTKEY}` and `SHCTX` values. The exact installer internals
were not instrumented. The repair therefore adds a post-install correction
using those generated values, then requires controlled upgrade regression.

## Data preservation

The `.clipgauge` root remained intact. The observed byte count changed only
from `30,539,699,014` to `30,539,699,103` during qualification. It retained
42 jobs, 143 model files, and 59,726 runtime files.

The provider/model selection remained
`clipgauge-local/qwen3-4b-q4_k_m`. Collection title and order changes used
for qualification were restored. No data loss was observed.

## Repair boundaries

The v0.6.1 patch must preserve existing clip IDs, assign deterministic IDs
only when absent, merge explicit render indexes, reject unsafe or missing
render outputs, surface sidecar failures, and refresh active uninstall
metadata. It must not alter v0.6.0 tags, assets, or unrelated features.
