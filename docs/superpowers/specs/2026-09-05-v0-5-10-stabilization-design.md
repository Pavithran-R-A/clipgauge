# ClipGauge v0.5.10 Stabilization Design

## Goal

Make first launch, setup, local processing, provider failures, packaged Windows use, and release qualification terminate honestly and recoverably. Preserve the immutable v0.5.9 release and retain truthful v0.5.3 local-import fallback guidance.

## Evidence

The fetched main commit is `4830b11e46c8de681cc721cac258771e1190b457`. `SetupCenter` starts `setup_tool inventory` and `setup_tool youtube-status` together. Packaged `pipeline_invocation` calls `uv run`, allowing implicit environment synchronization. Native `setup_tool_blocking` waits with unbounded `Command::output`. Streaming setup pipes stderr without consuming it. The current Windows workflow synchronizes the pipeline and seeds creator assets before packaged UI qualification, so fresh first launch is not tested.

These boundaries explain the observed placeholder: two status requests can race the same first-run `uv` environment bootstrap, while either native wait can remain pending. A full stderr pipe can also prevent streamed setup from exiting. The release gate hides the defect by warming the environment first.

## Design

### 1. Explicit sidecar lifecycle

Add one Rust sidecar runner with explicit invocation modes:

- `ReadOnly`: use `uv run --no-sync` only after the user environment is initialized.
- `Initialize`: run bundled `uv sync --locked` only from an approved setup action.
- `ManagedOperation`: run asset installation with `--no-sync` after initialization.

Read-only status calls never synchronize, download, or mutate. When the environment is absent, they return a structured `PIPELINE_NOT_INITIALIZED` result. The native bridge emits a diagnostic ID and actionable retry/setup state.

The runner owns command creation, environment propagation, process groups, bounded stdout/stderr collection, cancellation, inactivity deadlines, hard deadlines, and terminal result mapping. All native pipeline callers use this runner. No caller invokes `Command::output`, `wait_with_output`, or raw `uv run` directly.

### 2. Native fresh inventory

Add a native inventory path for the initial Setup screen. It reads the packaged manifest and user-owned asset paths, checks file existence and pinned hashes where safe, evaluates available disk space, and reports known download sizes. It does not require Python, `uv`, network access, YouTube, model loading, or provider credentials.

The existing Python inventory remains available after initialization for parity checks. The UI receives one typed inventory contract with explicit lifecycle states and a manifest version.

### 3. Serialized initialization

Store a process-wide coordinator in `AppState`. Initialization has one owner and one result. Concurrent callers wait on the same result. A failed, cancelled, or timed-out initialization clears ownership and leaves verified files reusable. The coordinator never treats an existing directory as a valid environment without a successful locked sync and probe.

Setup asset commands acquire the same coordinator. YouTube readiness never acquires the initialization lock during read-only status checks. Core setup readiness therefore remains independent from optional YouTube readiness.

### 4. Bounded operations

Status operations use short hard deadlines. Setup initialization and downloads use a hard deadline plus an inactivity deadline. Every timeout terminates the owned process tree, drains and joins output readers, releases coordinator state, preserves verified files and resumable partial files, emits one terminal event, and exposes Retry.

Setup streaming consumes both stdout and stderr continuously. Output is retained only as a bounded diagnostic tail. Child processes use a process group or Windows process tree termination. No loading state depends on an external process without a terminal timeout or error.

### 5. Frontend state machines

Create typed setup state helpers for `LOADING`, `READY`, `SETUP_REQUIRED`, `REPAIR_REQUIRED`, `OFFLINE`, `ERROR`, and `TIMED_OUT`. Inventory and YouTube state are independent. Each request has a generation token and mounted guard. Older responses cannot overwrite newer selections. Retry starts a new generation.

The Setup screen renders explicit loading, error, timeout, and retry copy. It never uses `Size calculated during setup`, `Available disk —`, or `Checking YouTube tools...` as permanent initial states. Optional YouTube failures remain visible only inside the YouTube card and cannot block local-file creation.

### 6. Fresh qualification

Keep the existing warm qualification. Add a separate Windows fresh-first-launch gate that builds NSIS, installs into a clean user home, starts from an unrelated working directory, launches before `uv sync`, and proves that no large download starts before consent. It then approves setup, observes initialization progress, checks ready state, relaunches, measures warm inventory latency, and verifies no child process leaks.

Add deterministic contract tests for concurrent inventory and YouTube status, missing environments, hanging sidecars, timeout cleanup, path names with spaces, Unicode-capable paths, cancellation, retry, partial files, and truthful fresh-state copy.

### 7. Documentation and release truth

Update public setup, fallback, troubleshooting, and changelog wording only after behavior is verified. Preserve the visible v0.5.3 fallback: YouTube-link import may fail, so users should obtain media separately and use local media import. Bump authoritative current version surfaces to 0.5.10 only after all gates pass.

## Non-goals

- Moving, deleting, or replacing v0.5.9 or older release tags.
- Claiming third-party provider success without real evidence.
- Automatically deleting user sessions, settings, credentials, models, or verified assets.
- Replacing pinned dependency integrity checks with unverified downloads.

## Verification

Run focused red-green regressions first. Then run Python, frontend, Rust, release-contract, visual-asset, security, packaged Windows, macOS, Linux, upgrade, and model-backed gates. Re-read every modified file and perform an adversarial second-pass search before any merge, tag, or publication action.
