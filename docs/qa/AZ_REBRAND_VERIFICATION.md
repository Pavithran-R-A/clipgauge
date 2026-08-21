# ClipGauge A-to-Z Rebrand Verification

**Audit basis:** Fresh case-insensitive whole-tree searches on the current QA branch, plus source inspection of app title, executable/package identifiers, CLI name, Python package, data-root migration, About/provenance copy, support paths, and logs.

## Verdict

No accidental legacy branding was identified in the normal ClipGauge product identity. Remaining occurrences are intentional and fall into **LEGAL / PROVENANCE**, **MIGRATION**, or **HISTORICAL AUDIT** classes. The current product-facing name is ClipGauge; the Python package/CLI is `clipgauge_pipeline`/`clipgauge`; the bundle identifier is `io.github.pavithranra.clipgauge`; and the normal data root is `~/.clipgauge`.

## Occurrence classification

| Occurrence family | Classification | Locations and rationale |
|---|---|---|
| `Blueturboguy07/publikclip` repository URLs and upstream commit references | LEGAL / PROVENANCE | `NOTICE.md`, `ORIGIN.md`, `README.md`, `THIRD_PARTY_NOTICES.md`, and `VENDORED-LICENSES.md` identify the derivative relationship and upstream attribution. |
| `.publikclip` data root and `PUBLIKCLIP_HOME` | MIGRATION | `app/src-tauri/src/main.rs`, `pipeline/clipgauge_pipeline/config.py`, `README.md`, `INSTALL.md`, `TROUBLESHOOTING.md`, and `ORIGIN.md` preserve explicit compatibility behavior and explain that migration does not delete the source automatically. |
| `legacy-publikclip-v1.done` migration marker | MIGRATION | Rust startup migration marker records the completed legacy data-tree migration without changing the current product identity. |
| Legacy `publikclip` command wording | HISTORICAL AUDIT / MIGRATION | `TROUBLESHOOTING.md` explains the distinction between current `clipgauge` and historical legacy command names. |
| Upstream attribution in About/license/provenance copy | LEGAL / PROVENANCE | Required AGPL derivative attribution; not a current UI brand substitution. |
| Historical audit and Stage 1 reports | HISTORICAL AUDIT | Retained to document earlier verification stages and source provenance. |
| Normal app title, product copy, CLI, package, bundle ID, and provider UI | No accidental occurrence | Fresh search and source inspection found ClipGauge identity in these paths; no user-facing accidental upstream name was found. |

## Checks performed

The current tracked tree was searched for `publikclip`, `PublikClip`, `PUBLIKCLIP`, `publik`, `Publik`, `publikhq`, `.publikclip`, and `PUBLIKCLIP_`. The complete raw occurrence list is preserved in `az-verification/evidence/rebrand/all-rebrand-occurrences.txt`. Occurrences in generated dependency caches were not treated as repository branding; the tracked-tree search was the authoritative classification set.

The current product identity was also checked statically in `app/tauri.conf.json`, `app/package.json`, `app/src-tauri/Cargo.toml`, `pipeline/pyproject.toml`, `pipeline/clipgauge_pipeline/__init__.py`, `README.md`, `About.tsx`, Rust service/bundle identifiers, and environment/data-root names. The public release remains ClipGauge v0.2.0.

## Limitation

The Windows installer and its installed UI could not be launched on the available Linux host. GitHub Windows packaging passed and the asset type/name were verified, but no local Windows visual observation is claimed.
