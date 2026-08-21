# ClipGauge v0.4.1 Dependency Audit Evidence

**Status:** PASS for audit execution with findings recorded. This document does not claim zero advisories.

## Commands and results

| Ecosystem | Command | Result |
|---|---|---|
| Frontend | `npm audit --audit-level=high` from `app/` | PASS: `found 0 vulnerabilities`. |
| Rust | `cargo audit` from `app/src-tauri/` | PASS with findings recorded: the audit completed and reported 17 allowed warnings, including the existing GTK3/glib and other unmaintained/unsound upstream dependency notices. No blanket allowance was added to Clippy or Rust tests. |
| Python | `uv export --format requirements-txt --no-hashes` followed by `pip-audit -r` | PASS with findings recorded: 14 known vulnerabilities were reported across `lightning 2.6.5`, `torch 2.8.0`, and `transformers 4.57.6`; the editable first-party `clipgauge-pipeline 0.4.1` package was not present on PyPI and was therefore not externally audited. |

## Interpretation

The Python findings are retained rather than force-upgrading the pinned ML stack without compatibility evidence. The Rust findings are retained as upstream dependency ownership items. The clean npm result applies to the frontend lockfile and does not imply that the Rust or Python ecosystems are advisory-free.

## References

[1]: ../../app/package-lock.json "Frontend lockfile"
[2]: ../../app/src-tauri/Cargo.lock "Rust lockfile"
[3]: ../../pipeline/uv.lock "Python lockfile"
[4]: ../../THIRD_PARTY_NOTICES.md "Third-party notices and provenance"
