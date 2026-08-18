# ClipGauge Stage 1A Report

## STAGE 1A STATUS

**CONDITIONAL PASS.** The scoped Stage 1A correctness and trust-boundary fixes are implemented, tested, committed on `clipgauge/stage1a-foundation`, and not pushed publicly. The conditional qualifier is limited to native platform validation: the Linux Tauri debug `.deb` smoke passed, while Windows and macOS native installers were not executed on this Linux host.

## BASELINE

| Field | Value |
|---|---|
| Upstream | `Blueturboguy07/publikclip` |
| Starting branch | `main` |
| Starting SHA | `a53a359b985b1d2d666266062936cc186f02340b` |
| Local implementation branch | `clipgauge/stage1a-foundation` |
| Ending source implementation SHA | `93495fc27d64684ff64726d3941a0e9dcae2985e` |
| Broad rename | **Untouched**; `publikclip`, `.publikclip`, package IDs, and historical provenance remain in place |
| Production-source status at implementation end | Clean |

The ending SHA above is the final implementation commit before this report artifact is added. The report-only commit, if present in the delivery branch, does not change the implementation source described by that SHA.

## COMMIT LIST

| Commit | Purpose |
|---|---|
| `90bd87f` | `test: add Stage 1A regression harness` |
| `f831087` | `fix: add structured pipeline terminal errors` |
| `7ffe80f` | `security: harden desktop bridge boundaries` |
| `d318508` | `fix: add safe media diagnostics and CSP checks` |
| `d51c87f` | `docs: record Stage 1A contracts and evidence` |
| `93495fc` | `test: strengthen Stage 1A security regressions` |

## FILES CHANGED

The implementation changes are limited to the pipeline protocol/ingest/queue boundary, focused Rust bridge modules and configuration, targeted React state/API changes, minimal frontend test infrastructure, tests, and Stage 1A documentation. The complete exact file list is captured in the delivery bundle’s `git diff` and checksum manifest. No unrelated creator feature, broad rename, license rewrite, or production asset replacement was performed.

## ARCHITECTURE CHANGES

The desktop now has explicit trust boundaries. Rust owns the packaged application root at the upstream-compatible `$HOME/.publikclip` location and passes that selected root to Python sidecars. Streamed sidecar stdout remains JSONL and progress remains incremental, but a run or resume operation must end in one versioned `terminal` event. Rust drains stderr concurrently into a bounded tail, redacts it before local persistence, observes the child exit, and synthesizes a structured failure if Python exits without a terminal event.

The privileged filesystem operations now use `path_security.rs` for exact generated job-ID validation, canonical containment under the jobs root, regular-file checks, and symlink escape rejection. `artifact.rs` owns render-checkpoint parsing, artifact status normalization, and export-by-`job_id` plus clip index. `job_results` no longer returns the absolute job directory and no longer implies that a render path is healthy merely because a checkpoint contains a string.

## TERMINAL PROTOCOL

The final contract is documented in [`docs/clipgauge/STAGE1A_PROTOCOL.md`](docs/clipgauge/STAGE1A_PROTOCOL.md). It uses `protocol_version: 1`, one `event: "terminal"`, a machine-readable `code`, safe human message, stage, job ID where known, retryability, and diagnostic ID where applicable. Expected ingest failures are typed as `INPUT_FILE_NOT_FOUND`, `INPUT_FILE_INVALID`, `YTDLP_AUTH_REQUIRED`, `YTDLP_DOWNLOAD_FAILED`, or `YTDLP_METADATA_FAILED`. Unexpected failures become `INTERNAL_ERROR`, retain a redacted bounded local traceback, and show only a safe diagnostic ID to the creator. Rust synthesizes `PIPELINE_START_FAILED` or `PIPELINE_EXIT_WITHOUT_TERMINAL` when the child boundary fails.

The protocol tests assert exactly one terminal event and reject duplicate legacy terminal behavior. The desktop consumes the terminal event as authoritative and retains `result` handling only for one-shot edit/Instagram commands.

## PUBLIC PIPELINE-EXIT BUG REMEDIATION

The Stage 0 disposable fake-yt-dlp reproduction is now a permanent regression. The test creates a failing executable that prints `ERROR: video unavailable after extractor failure` and exits nonzero, injects it into the real `IngestStage` through `ensure_ytdlp`, and runs the JSONL CLI path. The resulting terminal is `stage: ingest`, `code: YTDLP_METADATA_FAILED`, `retryable: true`, and an actionable yt-dlp message. It does not collapse into a bare traceback or generic `exited` event.

The queue now annotates unexpected exceptions with their stage, persists only redacted error text, and the CLI writes redacted diagnostic traces below the job’s private diagnostics directory. Representative Gemini-shaped, Pexels-shaped, Meta bearer-token, authorization-header, and URL-query secrets are covered by redaction tests.

## EDITOR/VIDEO REMEDIATION

`job_results` validates every render output against the canonical job `clips` directory and reports `available`, `missing`, `invalid`, or `outside_managed_root` states while nulling unsafe paths. Malformed render checkpoints return structured errors rather than silently becoming a healthy-looking result. Export verifies that the requested clip belongs to the job, the checkpoint supplies its artifact, the file is a regular MP4 inside the managed clips directory, and the destination filename is sanitized with duplicate-name handling preserved.

The Review screen now distinguishes loading, ready, missing/invalid/out-of-scope artifacts, and media decode/playback failure. The creator sees a safe job/clip-oriented explanation and a retry action; raw absolute paths are not shown. Frontend tests cover missing artifact, successful `loadedmetadata`, decode error/retry, and export calls by job and clip identity.

The exact root cause of the public editor screenshot remains unproven at machine level because the original screenshot environment is unavailable. Stage 1A nevertheless removes the unsafe path assumption and makes the likely path/scope/artifact mismatch observable and actionable.

## SECURITY FIXES MAPPED TO STAGE 0 IDs

| Stage 0 ID | Stage 1A result |
|---|---|
| **SEC-01** | **Resolved for desktop job operations.** Exact generated job-ID grammar and canonical jobs-root containment are centralized in `path_security.rs`; invalid, missing, absolute, traversal, and symlink-escaped jobs fail closed. |
| **SEC-02** | **Resolved.** The Tauri export command no longer accepts a frontend source pathname. It accepts job ID, clip index, and optional title, then resolves the server-side render artifact. Arbitrary readable-file export is a Rust regression test. |
| **SEC-03** | **Resolved in configuration.** `csp` is no longer null; the policy has no wildcard and no `unsafe-eval`, and its directives are justified in `STAGE1A_CSP.md`. |
| **SEC-04** | **Resolved for child argv.** Meta app secrets are written to the Python child’s stdin and never appear in the child argument vector. The argv contract has a Rust unit test. Full OS credential-vault migration remains deferred. |
| **SEC-05** | **Resolved for packaged desktop root selection.** Rust owns `$HOME/.publikclip`, passes it to sidecars, and the asset scope is narrowed to job media/overlays/thumbnails rather than the whole application tree. The root is intentionally not renamed in Stage 1A. |
| **SEC-11** | **Resolved.** Rust captures bounded stderr, redacts it, writes a local diagnostic record, observes exit status, and synthesizes a structured terminal event when Python omits one. |

SEC-06 is **partially touched**: Pexels secret files now receive the same Unix `0600` treatment as Gemini files, but cross-platform ACL hardening and credential-vault migration are deferred. SEC-07, SEC-08, SEC-09, SEC-10, SEC-12, SEC-13, SEC-14, and SEC-15 are intentionally outside this focused stage except where diagnostics or path containment provide a prerequisite.

## TESTS ADDED

| Area | Coverage |
|---|---|
| Python protocol | Missing local source; end-to-end fake yt-dlp failure; direct fake executable cleanup; injected unexpected exception; success; exactly-one-terminal invariant; protocol version; redaction; retryability; diagnostic ID |
| Rust diagnostics | Bounded stderr tail; Gemini/Pexels/Meta/query redaction |
| Rust path boundary | Valid/malformed IDs; traversal; absolute/separator rejection; missing job; symlink escape; Unicode filename |
| Rust artifacts/export | Available/missing/out-of-scope artifacts; arbitrary readable-file export rejection; clip ownership; regular MP4 requirement |
| Rust secret transport | Meta secret absent from child argv; stdin flag present |
| Frontend | Structured terminal error; synthesized missing-terminal fallback; loading/ready/error media states; retry; trusted export API; CSP non-null/scope and no arbitrary path primitive |

The first protocol run intentionally failed all four initial protocol tests before implementation; the saved evidence log is included in the final bundle.

## FULL VERIFICATION MATRIX

| Area | Command | Result |
|---|---|---|
| Python lock | `cd pipeline && uv lock --check` | **PASS** — resolved 149 packages |
| Python sync | `cd pipeline && uv sync` | **PASS** |
| Python tests | `cd pipeline && uv run pytest -q` | **PASS** — 97 passed, 1 pre-existing unknown-`slow`-mark warning |
| Python dependencies | `cd pipeline && uv pip check` | **PASS** — 147 packages compatible |
| Frontend clean install | `cd app && npm ci` | **PASS** — 0 vulnerabilities reported during install |
| Frontend tests | `cd app && npm test` | **PASS** — 3 files, 9 tests |
| Frontend build | `cd app && npm run build` | **PASS** — TypeScript and Vite production build |
| Frontend audit | `cd app && npm audit` | **PASS** — 0 vulnerabilities |
| Rust format | `cd app/src-tauri && cargo fmt --check` | **PASS** |
| Rust check | `cd app/src-tauri && cargo check` | **PASS** |
| Rust tests | `cd app/src-tauri && cargo test` | **PASS** — 12 passed |
| Rust clippy | `cd app/src-tauri && cargo clippy --all-targets --all-features -- -D warnings` | **PASS** |
| Tauri environment | `npm run tauri -- info` | **PASS** — Rust 1.97.1, WebKitGTK 4.1, rsvg2 present |
| Linux packaging smoke | `npm run tauri -- build --debug --bundles deb` | **PASS** — produced `publikclip_0.1.0_amd64.deb` |
| Windows/macOS native packaging | Native commands | **NOT RUN** — no Windows/macOS host; no fake cross-platform result claimed |

## REMAINING KNOWN RISKS

The Rust bridge still uses the existing localhost OAuth callback design and existing provider URL/query behavior. Cross-platform secret-file ACLs, signed/pinned yt-dlp/FFmpeg/model artifacts, archive extraction hardening, schema validation for all edit JSON, cancellation, and release/SBOM/provenance gates remain risks from Stage 0. The CSP retains `style-src 'unsafe-inline'` because current React style props require it; `unsafe-eval` and wildcard sources are absent. Native Windows and macOS playback, asset-scope, installer, and credential behavior require their respective hosts.

The public editor-video screenshot’s exact original machine cause is not claimed as confirmed. Stage 1A converts the failure from silent/blank behavior to explicit artifact and media diagnostics and closes the arbitrary-path boundary.

## DEFERRED TO STAGE 1B OR LATER

The following were intentionally not started: broad `publikclip` to ClipGauge rename; `.publikclip` to `.clipgauge` data-root migration; public ClipGauge repository creation; complete OS credential-vault migration; cancellation and cancellation-ready execution semantics; model/download signatures and immutable manifests; FFmpeg archive policy; full edit-schema validation; ephemeral OAuth callback hardening; signed releases/SBOM/license automation; Windows/macOS native test matrix; and unrelated creator features.

## REBRAND BOUNDARY

Broad ClipGauge rebranding remains untouched. The implementation uses the product direction in documentation and branch naming only. Upstream package names, application identifiers, `.publikclip` runtime root, visible existing product copy, license text, vendor notices, and historical references were not mass-renamed.

## REFERENCES

[1]: https://github.com/Blueturboguy07/publikclip/tree/a53a359b985b1d2d666266062936cc186f02340b "Audited upstream baseline"
[2]: https://v2.tauri.app/security/csp/ "Tauri CSP security documentation"
[3]: https://v2.tauri.app/security/asset-protocol/ "Tauri asset-protocol scope documentation"
[4]: https://github.com/Blueturboguy07/publikclip/issues/2 "Upstream pipeline-exit issue"
[5]: https://github.com/Blueturboguy07/publikclip/issues/3 "Upstream editor-video issue"
