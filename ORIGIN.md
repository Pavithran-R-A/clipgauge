# ClipGauge Origin and Modification Record

## Project relationship

ClipGauge is a modified derivative of [Blueturboguy07/publikclip](https://github.com/Blueturboguy07/publikclip). It is not an independent clean-room implementation and should not be represented as the original upstream project. The upstream project’s AGPL licensing and attribution are preserved in this repository.

The forensic audit used the following exact upstream baseline:

| Item | Value |
|---|---|
| Upstream repository | `https://github.com/Blueturboguy07/publikclip` |
| Audited baseline commit | `a53a359b985b1d2d666266062936cc186f02340b` |
| Baseline tag preserved locally | `archive/stage1a1-verified` at `78cfaea78ab043723904ff8d3cd5b4b8a090ca64` |
| Upstream license | AGPL-3.0-or-later |
| ClipGauge maintainer | Pavithran R A (`Pavithran-R-A`) |

The `upstream` Git remote remains pointed at the original repository. The ClipGauge release branch and its commits are intentionally not squashed so that the audit, hardening, rebrand, and release work remain inspectable.

## What changed

ClipGauge v0.1.0 retains the upstream pipeline direction while adding or changing the following project-owned areas:

- A ClipGauge application identity, `clipgauge` CLI entry point, `clipgauge_pipeline` Python package, `clipgauge-app` Rust package, `io.github.pavithranra.clipgauge` bundle identifier, and `.clipgauge` managed data root.
- Explicit legacy migration from `.publikclip` and `PUBLIKCLIP_HOME`; those names remain only where compatibility or provenance requires them.
- Rust-owned job lifecycle, duplicate-run protection, cancellation, stale-job recovery, resumability metadata, and structured diagnostics.
- Path-containment, symlink, artifact, checkpoint, edit-schema, and support-bundle validation at the desktop boundary.
- Pinned and hash-verified runtime downloads, model/runtime registry checks, atomic writes, corruption recovery, and last-known-good preservation.
- OS credential-store integration, legacy credential migration, operation-scoped secret injection, Gemini header authentication, native Ollama loopback requests, and ephemeral Instagram OAuth handling.
- Resource preflight and first-run gating, local file picking and drag-and-drop, accessibility improvements, elapsed progress timing, explainable clip ledgers, privacy activity summaries, and redacted support bundles.
- Original ClipGauge icon assets and release documentation.

This list describes the release branch’s intended modifications; it is not a claim that every line of code originated with ClipGauge. Adapted and vendored material is inventoried in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and [`VENDORED-LICENSES.md`](VENDORED-LICENSES.md).

## Attribution policy

Upstream copyright and license notices are retained where present. New ClipGauge files and modifications identify ClipGauge as the derivative project. Third-party code, model, font, and binary notices are listed separately with source links and stated license identifiers. When an upstream component’s own terms are more specific than the summary here, the component’s license text and repository control.

## References

[1]: https://github.com/Blueturboguy07/publikclip "Upstream publikclip repository"
[2]: https://github.com/Blueturboguy07/publikclip/commit/a53a359b985b1d2d666266062936cc186f02340b "Audited upstream baseline commit"
[3]: https://www.gnu.org/licenses/agpl-3.0.html "GNU Affero General Public License v3"
