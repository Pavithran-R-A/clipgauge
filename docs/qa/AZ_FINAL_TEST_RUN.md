# ClipGauge A-to-Z Final Fresh Test Run

**Fresh run timestamp:** Recorded in `az-verification/evidence/final-gates/timestamp.txt`  
**Branch:** `qa/a-z-total-verification`  
**Source base:** `f809c4a9954b5f27e37efb80b2b0748ccdb35e81` plus QA documents only  
**Protected release source:** `v0.2.0` peeled commit `cf67df92e34c7ba0bec7b6ce3c69bc32deaa4ca5`.

## Result summary

| Gate | Exit/status | Evidence | Classification |
|---|---:|---|---|
| Version consistency | 0 | `final-gates/version.log` | VERIFIED |
| `git diff --check` | 0 | `final-gates/diff_check.log` | VERIFIED |
| Python full pytest | 0 | `final-gates/python_pytest.log` | VERIFIED: 129 passed, 1 warning |
| Python dependency check | 0 | `final-gates/python_pip_check.log` | VERIFIED |
| Python advisory scan | 0 | `final-gates/python_pip_audit.log` | VERIFIED: no known vulnerabilities |
| Frontend Vitest | 0 | `final-gates/frontend_test.log` | VERIFIED: 12 passed |
| Frontend production build | 0 | `final-gates/frontend_build.log` | VERIFIED |
| npm audit | 0 | `final-gates/frontend_npm_audit.log` | VERIFIED: 0 total vulnerabilities reported |
| Rust fmt | 0 | `final-gates/rust_fmt.log` | VERIFIED |
| Rust check | 0 | `final-gates/rust_check.log` | VERIFIED |
| Rust tests | 0 | `final-gates/rust_test.log` | VERIFIED: 28 passed |
| Full Rust Clippy | 101 | `final-gates/rust_clippy.log` | FAILED: `items_after_test_module`, unused `redact_with_secrets`, and two widened Tauri functions over the default argument-count threshold |
| Rust cargo-audit | 0 | `final-gates/rust_audit.log` | VERIFIED with 17 allowed warnings: transitive GTK3/unmaintained crates and `glib` RUSTSEC-2024-0429 unsoundness warning |
| Release checksums | 0 | `final-gates/release_checksum.log` | VERIFIED: all downloaded release assets `OK` |
| Release SBOM | 0 | `final-gates/release_sbom.log` | VERIFIED: CycloneDX with component array |
| Fresh cloud smoke | success run | `live-smoke-final.json`, `live-provider-status.tsv` | BLOCKED per provider: no live inference because secrets were absent |
| GitHub current main | success | `workflows/main-runs-summary.txt` | VERIFIED: current CI, Windows, macOS qualification, and secret scan green |

## Test and advisory notes

The Python suite collected 129 tests and passed all 129, with one warning. The frontend suite passed 12 tests across three files and the production build passed. Rust unit tests passed all 28 tests. The full mandated Clippy command is stricter than the repository workflow’s narrow lint allowances and failed on three categories: production functions after the test module, an exported but unused redaction helper, and widened provider-aware Tauri command argument lists. This is recorded as a code-quality defect, not silently converted to a pass.

Python `pip-audit --local` reported no known vulnerabilities. `npm audit --json` reported zero total vulnerabilities. `cargo audit` completed with 17 allowed warnings, including unmaintained GTK3 bindings/transitives and the unsound `glib` advisory RUSTSEC-2024-0429. These transitive supply-chain findings require maintenance review but did not produce a nonzero cargo-audit exit code.

## Fresh provider status

The manual all-provider run was `32448768889` on the QA branch. Gemini, OpenRouter, Groq, Cloudflare Workers AI, Hugging Face, and Cerebras each completed the workflow step successfully by reporting that credentials were not fully configured; no live external inference was attempted. Their status is **BLOCKED**, not LIVE PASS. The custom OpenAI-compatible provider was tested locally against a real loopback mock server with bearer, API-key-header, and custom-secret-header authentication; model listing and structured output passed, no-auth failure was classified as `AUTH_INVALID`, URL policy rejected unsafe endpoints, and the adapter vision path passed under an explicitly vision-capable mock profile.

## Release artifact verification

A fresh download of all six public v0.2.0 assets passed `sha256sum -c SHA256SUMS`. The Linux asset was recognized as a Debian binary package and the Windows asset as a PE32 NSIS installer. The SBOM parsed as CycloneDX with an array of components. The release record was non-draft and non-prerelease. The tag comparison preserved the annotated tag object and peeled source commit. No Windows installation, macOS local launch, or signing/notarization claim was made.
