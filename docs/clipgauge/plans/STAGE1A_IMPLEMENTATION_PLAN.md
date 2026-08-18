# ClipGauge Stage 1A Implementation Plan

## Scope and baseline

Stage 1A starts from `Blueturboguy07/publikclip` `main` at `a53a359b985b1d2d666266062936cc186f02340b`. Work is on branch `clipgauge/stage1a-foundation`. The implementation repairs trust-boundary and failure-contract defects only. The broad `publikclip` to ClipGauge rename, UI redesign, unrelated creator features, licensing rewrites, public repository creation, and Stage 1B work are explicitly out of scope.

## Workstream map

| Workstream | Production files | Tests/evidence | Acceptance |
|---|---|---|---|
| Versioned terminal protocol | `pipeline/publikclip_pipeline/cli.py`, `jobs/queue.py`, `ingest/stage.py`, `ingest/ytdlp.py`, `app/src-tauri/src/main.rs`, `app/src/types.ts`, `app/src/App.tsx` | Python protocol tests; Rust protocol/redaction tests; frontend state tests; `docs/clipgauge/STAGE1A_PROTOCOL.md` | Every streamed run/resume emits exactly one terminal event with version, safe code/message, job/stage, retryability, diagnostic ID where applicable, and exit code where known |
| Sidecar diagnostics and redaction | `app/src-tauri/src/main.rs` or focused Rust module; shared redaction helper | Rust unit tests for bounded tail and secrets; protocol tests | Bounded stderr capture, redaction of keys/tokens/headers/query secrets, persisted diagnostic ID, synthesized terminal if child exits without one |
| Secure job IDs and paths | `app/src-tauri/src/main.rs` or focused `path_security` module; `app/src-tauri/Cargo.toml` only if needed | Rust traversal, absolute path, malformed ID, symlink escape, missing job, Unicode/space tests | All job operations resolve through trusted jobs root; traversal/symlink escapes fail closed |
| Safe export | Rust export command and `app/src/api.ts`, `app/src/types.ts`, export call sites | Rust arbitrary-file export regression; frontend API/type tests | Export accepts trusted job/clip identity, validates checkpoint/artifact/containment/type, never frontend source pathname |
| Job-results artifact validation | Rust `job_results`, shared resolver/status types, `Review.tsx` | Rust malformed/missing/outside-root tests; frontend state tests | Each rendered clip has safe available/missing/invalid/outside/unreadable status; malformed state is structured, not silent null |
| Managed application paths and asset scope | `pipeline/publikclip_pipeline/config.py`, `app/src-tauri/src/main.rs`, `app/src-tauri/tauri.conf.json` or generated config path | Rust/Python path contract tests; `docs/clipgauge/STAGE1A_APP_PATHS.md` | Rust owns a narrow managed root; Python receives it consistently; asset-readable media dirs exclude secrets; legacy `.publikclip` compatibility remains explicit and unrenamed |
| Restrictive CSP | `app/src-tauri/tauri.conf.json` | Frontend build plus CSP/config tests; `docs/clipgauge/STAGE1A_CSP.md` | CSP is non-null, least privilege, no wildcard, no unsafe-eval, and justified from actual asset/IPC behavior |
| Video diagnostics | `app/src/components/Review.tsx`, `app/src/api.ts`, `app/src/types.ts`, possibly `App.tsx` | Frontend tests for loading, ready, missing, scope/permission, decode error, stale artifact, and success | Blank monitor becomes explicit creator-facing state with safe job/clip identity, retry/repair direction, and no raw absolute path by default |
| Meta secret transport | `app/src-tauri/src/main.rs`, `pipeline/publikclip_pipeline/insights/instagram.py` or CLI contract | Rust child-argument/process-wrapper tests; OAuth behavior regression | Meta secret absent from argv, logs, terminal events, diagnostics; OAuth behavior preserved |
| Frontend test stack | `app/package.json`, test setup/config, targeted `app/src/**/*.test.*` | `npm test` | Minimal deterministic React/Vite-compatible stack; no heavyweight model dependency |
| Rust testability | `app/src-tauri/src/**/*.rs` | `cargo fmt --check`, `cargo check`, `cargo test`, `cargo clippy --all-targets --all-features -- -D warnings` | Native checks pass if toolchain can be installed; otherwise exact blocker recorded |

## TDD sequence

1. Add failing tests for the fake yt-dlp failure, missing local source, injected unexpected exception, lightweight fake-stage success, exactly-one-terminal invariant, redaction, path containment, arbitrary export rejection, artifact status, CSP non-null/scope, Meta-secret argv exclusion, and frontend terminal/video states.
2. Run each focused test and preserve the expected failure output in Stage 1A evidence.
3. Implement the smallest correction for the affected boundary.
4. Re-run the focused test, then the affected existing suite.
5. Commit logically by protocol, diagnostics/redaction, path security, export, artifact/video, CSP/paths, secret transport, tests/docs.
6. Run the full verification matrix and review the final diff against the audited SHA.

## Protocol design target

The streamed contract will use a stable `protocol_version` and one `event: "terminal"` event. Terminal failures will carry `ok: false`, `job_id` where known, stage where known, typed `code`, safe `message`, `retryable`, `diagnostic_id` where generated, and `exit_code` where known. The implementation may retain compatibility fields for existing frontend behavior, but must not preserve the defect of bare `exited` without a terminal event.

## Acceptance gates

Gate A requires exactly one terminal event for expected and unexpected injected failures. Gate B requires the fake yt-dlp reproduction to yield an actionable structured ingest failure. Gate C requires traversal and symlink escapes to fail closed. Gate D requires no frontend-controlled arbitrary source path to reach file copy. Gate E requires non-null justified CSP. Gate F requires explicit artifact/video states. Gate G requires no Meta secret in argv/logs/events. Gate H requires all existing Python tests plus new regressions. Gate I requires frontend tests/build. Gate J requires Rust format/check/test/clippy when the toolchain is available.

## Deferred items

Full credential-vault migration, broad product/package/data-root rebrand, public ClipGauge repository creation, cancellation-ready execution, signed releases, SBOM, native Windows/macOS end-to-end validation, and unrelated creator features are deferred to later stages unless a narrowly safe prerequisite is needed for Stage 1A.
