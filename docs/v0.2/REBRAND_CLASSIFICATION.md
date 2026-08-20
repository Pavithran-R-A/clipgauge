# ClipGauge v0.2.0 rebrand classification

The current user-facing product identity is **ClipGauge**. The CLI is `clipgauge`, the Python package is `clipgauge_pipeline`, the managed data root is `~/.clipgauge`, and the Tauri product identity is ClipGauge. A repository-wide search was performed for `publikclip`, `PublikClip`, `PUBLIKCLIP`, `publik`, `Publik`, `publikhq`, `.publikclip`, and `PUBLIKCLIP_`.

## Required legal and provenance occurrences — keep

The following current-tree occurrences identify the modified derivative, preserve AGPL attribution, or link to the upstream project and therefore must remain: `ORIGIN.md`, `NOTICE.md`, `README.md`, `CHANGELOG.md`, `THIRD_PARTY_NOTICES.md`, `VENDORED-LICENSES.md`, the About view’s upstream attribution link, release provenance text, and the v0.2 implementation/provider research documents’ source references. These are not product claims that ClipGauge is the upstream project.

## Required legacy migration occurrences — keep and document

`pipeline/clipgauge_pipeline/config.py` accepts `PUBLIKCLIP_HOME` as a legacy development/test migration source and recognizes the historical `~/.publikclip` root. The Rust bridge discovers `PUBLIKCLIP_HOME`, copies legacy data collision-safely, and writes a `legacy-publikclip-v1.done` marker only after a successful migration. `.gitignore` preserves `.publikclip/` as a migration source. `INSTALL.md`, `TROUBLESHOOTING.md`, `ORIGIN.md`, and `docs/clipgauge/STAGE1A_APP_PATHS.md` explain that the legacy source is preserved and not deleted automatically. These names are required for v0.1.x user migration and must not be mass-renamed.

## Historical audit occurrences — keep

The Stage 1A and v0.1 closure reports and plans contain old package paths, upstream branch names, historical build names, and statements describing work that was intentionally out of scope at that time. They are historical evidence, not current product branding. The v0.1.1 closure plan and reports also preserve the upstream remote identity and immutable release history.

## Accidental product branding — fixed

The only current code comment identified as accidental product-facing upstream wording was the CAM++ diarization module docstring. It now says that ClipGauge ships the vendored diarization path. No current Studio label, CLI name, package name, data root, environment variable, window title, installer name, or bundle identifier uses upstream branding.

## Review conclusion

The remaining occurrences are justified legal/provenance, legacy migration, or historical audit references. They are deliberately retained rather than hidden because deleting them would damage attribution or break migration. No accidental upstream branding remains in normal ClipGauge UX or executable identity.
