# ClipGauge v0.3.0 Dependency Security

## Scope

This record captures the dependency gates run for the v0.3.0 release candidate. The project does not hide audit findings, force an incompatible ML stack, or claim a zero-advisory result when the resolver and upstream compatibility constraints do not support one.

## Python audit

Project-scoped `pip-audit` exited `1` on the resolved `pipeline/uv.lock`. The findings are:

| Package | Resolved version | Dependency path | Findings | Fix status |
|---|---:|---|---|---|
| `lightning` | 2.6.5 | `clipgauge-pipeline → whisperx 3.8.6 → pyannote-audio 4.0.7 → lightning` | `PYSEC-2026-3624` / `CVE-2026-58659` | No released fix version reported by the audit; upstream patch reference is a commit. |
| `torch` | 2.8.0 | `clipgauge-pipeline → whisperx 3.8.6 → torch` | Multiple PYSEC/CVE/GHSA records, including findings with fixed versions at 2.9.0, 2.9.1, 2.10.0, and 2.13.0, plus records with no fixed version in the audit output. | The project’s current `whisperx==3.8.6` constraint requires `torch>=2.8.0,<2.9.dev0`. A trial `torch>=2.10,<2.11` security floor was rejected by `uv` as unsatisfiable. |
| `transformers` | 4.57.6 | `clipgauge-pipeline → whisperx 3.8.6 → transformers` | `PYSEC-2025-217` / `CVE-2025-14929`; additional 2026 records are reported by the audit database, with some fixed versions above the current major line and some without a fix version. | No safe upgrade was established without changing the WhisperX/pyannote inference stack. |

The audit also reports that the local editable package `clipgauge-pipeline 0.3.0` cannot be audited from PyPI because it is not published there. This is an audit-tool limitation, not a claim that the package is vulnerable.

### Decision

These findings are classified as **upstream-constrained dependency risk**, not silently converted into a pass. The vulnerable packages are runtime-critical for the current WhisperX/pyannote speech pipeline. The attempted Torch upgrade was reverted because the resolver proved it incompatible with WhisperX 3.8.6. Remediation requires a coordinated upstream-compatible WhisperX/pyannote/torch/transformers update, a separate inference backend, or an explicit pipeline migration; v0.3.0 does not invent one.

Model and runtime downloads remain SHA-256 verified, bounded, and pinned. Local GGUF models are loaded by the owned loopback llama-server runtime rather than by the Python Transformers loader. No untrusted repository is accepted through `trust_remote_code` or an arbitrary model URL in the ClipGauge Local path.

## Rust audit

`cargo audit` exits `0` with warnings only and reports the same GTK3 dependency graph known from v0.2.1. The affected stable graph includes `glib 0.18.5` through Tauri/Wry and unmaintained GTK3 crates such as `atk`, `gdk`, and `gtk`. The unsound `RUSTSEC-2024-0429` warning remains documented in [`RUST_DEPENDENCY_SECURITY.md`](RUST_DEPENDENCY_SECURITY.md) and is not hidden with an ignore entry. A forced Wry upgrade was not used because the current `tauri-runtime-wry` constraint rejects the incompatible version.

## Release classification

The v0.3.0 security gate is **CONDITIONAL**. Project-owned security regressions introduced by this release are not observed in the deterministic source checks. Upstream-constrained Python ML findings and the existing GTK3/glib warning set remain visible, documented, and release-blocking for any claim of “zero advisories.”

## Evidence

The raw machine-readable and terminal records are retained under `v030-evidence/` outside the source tree and are included in the final closure bundle. Relevant files are `phase9-pip-audit-project.json`, `phase9-pip-audit-project.log`, `phase9-torch-lock.log`, `phase9-cargo-audit.log`, and the inverse dependency traces for Lightning and Transformers.

## References

1. [WhisperX on PyPI](https://pypi.org/project/whisperx/)
2. [PyTorch Security Advisories](https://github.com/pytorch/pytorch/security/advisories)
3. [Hugging Face Transformers Security Advisories](https://github.com/huggingface/transformers/security/advisories)
4. [RustSec advisory database](https://rustsec.org/advisories/)
