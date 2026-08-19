# ClipGauge v0.1 Completion Plan

## Baseline and non-negotiable constraints

The protected baseline is `78cfaea78ab043723904ff8d3cd5b4b8a090ca64`, descended from the audited upstream commit `a53a359b985b1d2d666266062936cc186f02340b`. The baseline is preserved by the annotated tag `archive/stage1a1-verified`. Work proceeds on `clipgauge/finalize-v0.1`; the original `origin` remote remains the Publikclip repository until the public destination is created safely.

ClipGauge remains a local-first desktop application. No cloud backend, mandatory subscription, default telemetry, or ClipGauge-owned media upload is permitted. AGPL licensing, upstream attribution, third-party notices, and historical authorship must remain explicit.

## Requirement map

| Specification area | Primary implementation areas | Required tests/evidence | Acceptance gate |
|---|---|---|---|
| Job lifecycle, process ownership, cancellation, duplicate-run protection | `app/src-tauri/src/process_manager.rs`, `app/src-tauri/src/main.rs`, lifecycle protocol/types, Python queue metadata | Rust state-machine tests; duplicate active-job test; owned-process cancellation fixture; native-CI process-tree notes | Cancellation is distinct from failure; exactly one terminal event; no duplicate active run; safe resume remains available |
| Stale recovery and app exit | Rust runtime/lease manager; queue status reconciliation; startup command/event path | Deterministic stale lease tests; PID-reuse mismatch test; interrupted/resumable UI test | Abandoned runs become `INTERRUPTED`; unrelated PIDs are never killed; completed checkpoints remain usable |
| Conservative concurrency | Rust scheduler/process manager | Two-job busy/queue test | At most one heavy job by default; state is visible and actionable |
| Versioned artifact descriptors | Python artifact manifest module, queue/checkpoint writers, Rust artifact resolver | Descriptor schema tests; relative-path/type/role validation | No untrusted absolute path as logical identity |
| Artifact reuse and corruption recovery | All stage checkpoint writers/readers under `pipeline/publikclip_pipeline/**`; render/export bridge | Missing, malformed, outside-root, wrong-type, stale, and corrupted-checkpoint fixtures | Fail closed with structured recovery, never traceback/silent reuse |
| Atomic writes | Shared Python atomic JSON/manifest writer | Interrupted-write and replacement tests | Critical JSON/checkpoints are never partially valid |
| Runtime dependency manifest | `pipeline/publikclip_pipeline/runtime_manifest.py`, `pipeline/runtime-manifest.json`, docs | Manifest schema and hash/provenance validation | Exact version/revision/source/hash/size/license fields; no invented hashes |
| yt-dlp and FFmpeg | `pipeline/publikclip_pipeline/ingest/ytdlp.py`, `render/ffmpeg_bin.py`, download/archive helpers | Hash mismatch, interrupted download, traversal, unexpected entry, last-known-good, valid install tests | Staged verified installation; failed update preserves known-good; new binary never executes before verification |
| Model registry | `pipeline/publikclip_pipeline/models/**`, explicit registry manifest | Registry hash/revision tests; mismatch rejection; internal-fetch boundary documentation | Release-managed artifacts do not use `sha256=None`; opaque library downloads are documented accurately |
| Secret storage and migration | Rust secret-store abstraction; settings/key bridge; Python credential transport; migration module | Mock store tests; legacy migration success/failure/partial/retry tests; redaction tests | No normal plaintext secret storage; no deletion before verified migration; session-only fallback is explicit |
| Provider request security | Python Gemini/Pexels/Meta/Ollama modules; centralized redaction | URL/header/log/error secret tests; loopback Ollama state tests | Gemini secrets use headers, not query strings; Ollama is loopback/timeout/size bounded; provider errors are useful and safe |
| Instagram OAuth | Rust/Python OAuth bridge and callback server | Ephemeral-port, loopback, CSRF/state, timeout, one-valid-callback, clean-shutdown tests | No fixed-port requirement; no secret logging |
| Edit/overlay IPC schemas | Rust Tauri command inputs, `artifact.rs`, Python edit validation, frontend types | Unknown-field, range, identity, bounds, extension, ownership, overlay-count/size, malicious payload tests | Frontend types are not trusted; Rust/Python reject malformed or arbitrary paths |
| Resource preflight | Rust preflight command/module; frontend Studio/settings | Ready/warning/blocked fixture tests; no-fake-ETA test | Disk/runtime/model/provider state is actionable; displayed sizes have one source of truth; local file picker/drop path works |
| UX and accessibility | `app/src/**`, styles, dialogs, settings, review/editor | Vitest state/accessibility tests; keyboard/focus/label/contrast/reduced-motion audit | Creator-facing copy is clear; impossible actions disabled; progress semantics are honest and accessible |
| Product differentiators | Review ledger/provenance components; privacy summary; support bundle; resumability UI | Score-ledger provenance tests; privacy-mode tests; support-bundle secret-exclusion tests; resume-health tests | Explainability uses actual scoring data; no unsupported certainty claims; no raw secrets/media in support bundle |
| Rebrand and migration | Repository-wide identifiers; package names; env/data-root migration; Tauri identifier; UI copy/assets | Search/classification report; `.publikclip` migration partial/retry/collision tests; build/import tests | Normal product surface says ClipGauge; historical/legal/migration references remain justified; failed migration preserves old data |
| Identity assets | Original SVG/icon source and platform derivatives under `app/src-tauri/icons/` | Asset existence/size/build checks; provenance note | Original ClipGauge icon, recognizable at 16–32 px; no modified upstream P icon |
| Licensing/provenance | `LICENSE`, `VENDORED-LICENSES.md`, `NOTICE.md`, `ORIGIN.md`, `THIRD_PARTY_NOTICES.md`, About/Licenses UI | License/source inventory and UI reachability checks | AGPL and upstream derivative status remain explicit |
| Documentation | `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, `docs/**`, templates | Link/path/config checks; no fabricated screenshots/benchmarks | Install, privacy, architecture, troubleshooting, release, development, contribution, and provenance docs are complete |
| Test and security infrastructure | Python/frontend/Rust test configs; advisory/secret/license scans; CI workflows | Full local matrix plus security regressions and dependency scans | No failing required suite, known critical/high unmitigated vulnerability, or secret scan hit |
| Native CI and release | `.github/workflows/**`, release manifest/SBOM/provenance steps | Actual Windows/macOS/Linux workflow runs; artifact/checksum/SBOM/attestation evidence | Each platform claim reflects real execution; ordinary tests do not receive release write permissions |
| Final release and publication | Version files, tag, release notes, GitHub repository/remotes | Final audit, clean tree, public repo/release verification | Only after GO report; unsigned status is explicit; updater remains disabled without signing key |

## Commit and verification discipline

Each coherent workstream is developed with a focused regression first where practical, followed by the smallest implementation, affected tests, the complete local matrix, and a focused commit. Generated environments, model caches, raw media, credentials, signing keys, and temporary files never enter the final repository or bundle.

The release candidate must record the exact final commit, complete test counts, platform matrix, dependency/runtime provenance, security and license scan results, artifact names and SHA-256 values, signing/updater status, migration behavior, and the final GO/NO-GO decision in `CLIPGAUGE_V0_1_RELEASE_AUDIT.md`.

## Release stop conditions

Release is blocked by arbitrary filesystem read/export, path traversal, secret exposure, CSP broadening, unstructured terminal failure, known orphan processes, destructive migration, unverified runtime downloads, critical/high unmitigated vulnerabilities, failing required suites or native CI, invalid AGPL/provenance handling, an uncommitted tree, or a repository secret-scan failure. Missing paid signing certificates, disabled updater, unavailable hardware benchmarks, and optional user-owned Instagram setup are not blockers when documented accurately.
