# ClipGauge v0.4.0 Security Review

**Status:** Project-owned v0.4 controls PASS; dependency audit findings remain transparently documented.

## Download and execution boundary

Every managed executable or model has an explicit identity, immutable source/revision, expected size, SHA-256, controlled destination, provenance, license, and consent group. Downloads stage into partial files, verify before promotion, and use bounded destinations. Archive extraction rejects traversal and unsafe links; the llama.cpp archive path additionally materializes safe symlinks/hardlinks as regular files with cycle and escape checks. No unverified executable is launched.

FFmpeg, yt-dlp, Node.js, bgutil, llama-server, faster-whisper, Silero VAD, alignment, NLTK, and analysis assets are represented by the manager or an explicit adapter. Compute stages use local/offline environment settings for HF, Transformers, Torch, NLTK, and the managed torch hub. The Silero VAD hidden torch.hub fetch discovered by the failed first E2E is now closed through a pinned managed archive and readiness gate.

## Network and local-service controls

Local inference and bgutil services bind to loopback only. User-controlled source URLs are validated through the existing ingest boundary rather than interpolated into shell strings. Browser cookies are never read by default; only the explicit supported-browser allow-list can request `cookies-from-browser`, and the selection is recorded in the job snapshot. Raw cookies, provider secrets, source media, raw transcripts, and private prompts are excluded from support bundles.

## Path and process controls

Managed roots and job directories are contained, partial files are not marked verified, and cancellation preserves completed checkpoints while terminating owned child processes. The local runtime supervisor owns its process handle and endpoint, uses bounded startup/readiness checks, and does not rely on arbitrary user `PATH` state for the managed runtime. Diagnostic messages are sanitized and support bundles are scoped to the requested job/diagnostic.

## Dependency audit results

| Ecosystem | Observed result | Classification and action |
|---|---|---|
| npm | `npm audit` exit 0; 0 vulnerabilities across 222 resolved packages | PASS; no project-owned npm advisory was reported. |
| Python | Locked `pip-audit --no-deps --disable-pip` found 14 known vulnerabilities in `lightning 2.6.5`, `torch 2.8.0`, and `transformers 4.57.6` | Upstream/stack-constrained. WhisperX 3.8.6 and the verified ML stack constrain coordinated upgrades; no incompatible force-upgrade was applied. The exact IDs and available fixes are preserved in `v040-pip-audit-nodeps.log`. |
| Rust | `cargo audit` exit 0 but reports unmaintained GTK3/glib-family crates and `RUSTSEC-2024-0429` for glib 0.18.5 | Upstream Tauri/Wry graph constraint. No blanket warning suppression or incompatible GUI-stack migration was applied. Exact advisory IDs are preserved in `v040-cargo-audit.log`. |

The non-zero Python advisory result is not called “zero advisories” and is not hidden. The remaining exposure is reduced by local-only default processing, verified asset provenance, no arbitrary remote execution, and the project’s existing input/process boundaries. A future compatible WhisperX/Torch/Transformers migration is required for full remediation.

## License and provenance

ClipGauge remains AGPL-3.0-or-later and explicitly attributes the modified derivative to `Blueturboguy07/publikclip`. The managed bgutil provider is GPL-3.0-only and is called out in the inventory and notices. FFmpeg and other adapted/vendored components retain their respective notices. No license or provenance file was removed to satisfy an audit.

## Conclusion

The v0.4 project-owned security controls are implemented and covered by Python, Rust, and frontend tests. The release must retain the documented Python and Rust advisory limitations and must not claim an advisory-free dependency graph.
