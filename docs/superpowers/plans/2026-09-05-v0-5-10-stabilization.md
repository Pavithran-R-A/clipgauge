# ClipGauge v0.5.10 Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate known reproducible setup, lifecycle, process, and packaged-qualification defects before the immutable v0.5.10 release.

**Architecture:** Make the Rust bridge the sole owner of sidecar invocation, timeouts, process cleanup, and explicit pipeline initialization. Make initial inventory native and read-only, then let approved setup initialize the Python environment once. Give inventory and YouTube independent typed frontend state machines.

**Tech Stack:** React, TypeScript, Vitest, Tauri 2, Rust, Python 3.12, uv, pytest, PowerShell, GitHub Actions, NSIS.

**Spec:** `docs/superpowers/specs/2026-09-05-v0-5-10-stabilization-design.md`

## Global Constraints

- Preserve v0.5.9 and all older tags and release assets.
- Never download large runtime dependencies before explicit approval.
- Never let optional YouTube readiness block local-file creation.
- Every external process has bounded completion and cleanup.
- Preserve verified assets, resumable partial files, sessions, and credentials.
- Do not publish or merge until every required gate has evidence.

## File Map

- Create `app/src-tauri/src/sidecar.rs` for bounded child-process execution.
- Create `app/src-tauri/src/setup_inventory.rs` for native manifest inventory.
- Modify `app/src-tauri/src/main.rs` for bridge commands and coordination.
- Modify `app/src-tauri/src/process_manager.rs` for timeout cleanup state.
- Create `app/src/setupLifecycle.ts` for typed async setup states.
- Modify `app/src/components/SetupCenter.tsx` for terminal UI states.
- Modify `app/src/api.ts` for typed setup bridge calls.
- Add focused frontend and Rust regression tests.
- Add `.github/windows-fresh-first-launch.ps1` qualification coverage.
- Modify `.github/workflows/windows.yml` to run fresh qualification.
- Update README, INSTALL, TROUBLESHOOTING, and CHANGELOG truthfully.

### Task 1: Add failing Rust runner tests

**Files:**

- Create: `app/src-tauri/src/sidecar.rs`
- Test: `app/src-tauri/src/sidecar.rs`
- Modify: `app/src-tauri/src/main.rs`

**Interfaces:**

- `RunPolicy { hard_timeout, idle_timeout }` controls deadlines.
- `RunOutput { status, stdout, stderr_tail }` stores bounded output.
- `RunError::{Spawn, Timeout, IdleTimeout, Io, NonZero}` maps failures.
- `run_bounded(command, policy)` returns `Result<RunOutput, RunError>`.

- [ ] **Step 1: Write the timeout regression.**

~~~rust
#[test]
fn hanging_sidecar_returns_idle_timeout() {
    let command = test_sleep_command(Duration::from_secs(2));
    let result = run_bounded(command, RunPolicy::test_idle_timeout());
    assert!(matches!(result, Err(RunError::IdleTimeout)));
}
~~~

- [ ] **Step 2: Run the focused Rust test.**

Run: `cargo test --manifest-path app/src-tauri/Cargo.toml hanging_sidecar_returns_idle_timeout`

Expected: FAIL because `run_bounded` is absent.

- [ ] **Step 3: Write the stderr-drain regression.**

~~~rust
#[test]
fn noisy_sidecar_completes_without_pipe_deadlock() {
    let command = test_noisy_command(1_048_576);
    let output = run_bounded(command, RunPolicy::test()).unwrap();
    assert!(output.stderr_tail.len() <= MAX_DIAGNOSTIC_BYTES);
}
~~~

- [ ] **Step 4: Run the second focused test.**

Run: `cargo test --manifest-path app/src-tauri/Cargo.toml noisy_sidecar_completes_without_pipe_deadlock`

Expected: FAIL because the bounded runner is absent.

- [ ] **Step 5: Implement one bounded runner.**

Spawn the child with piped stdout and stderr. Drain both streams on reader threads. Poll `try_wait` with short intervals. Terminate the owned process tree on hard or idle timeout. Join readers before returning. Keep only the final diagnostic tail.

- [ ] **Step 6: Run both focused tests.**

Run: `cargo test --manifest-path app/src-tauri/Cargo.toml hanging_sidecar_returns_idle_timeout noisy_sidecar_completes_without_pipe_deadlock`

Expected: PASS with zero failures.

- [ ] **Step 7: Register the module.**

Add `mod sidecar;` to `main.rs`. Replace no callers yet. Commit with `test: cover bounded sidecar execution`.

### Task 2: Make invocation and initialization explicit

**Files:**

- Modify: `app/src-tauri/src/sidecar.rs`
- Modify: `app/src-tauri/src/main.rs`
- Modify: `app/src-tauri/src/process_manager.rs`
- Test: `app/src-tauri/src/sidecar.rs`
- Test: `app/src-tauri/src/main.rs`

**Interfaces:**

- `PipelineMode::{ReadOnly, Initialize, ManagedOperation}` selects arguments.
- `pipeline_command(mode)` builds one command without cwd assumptions.
- `InitializationCoordinator::ensure_initialized()` single-flights locked sync.

- [ ] **Step 1: Write argument-shape tests.**

~~~rust
#[test]
fn read_only_pipeline_never_requests_uv_sync() {
    let args = pipeline_args(PipelineMode::ReadOnly);
    assert!(args.contains(&"--no-sync".to_string()));
    assert!(!args.contains(&"sync".to_string()));
}

#[test]
fn initialize_pipeline_requests_locked_sync() {
    let args = pipeline_args(PipelineMode::Initialize);
    assert_eq!(args, vec!["--directory", "pipeline", "sync", "--locked"]);
}
~~~

- [ ] **Step 2: Run tests and observe failure.**

Run: `cargo test --manifest-path app/src-tauri/Cargo.toml read_only_pipeline_never_requests_uv_sync initialize_pipeline_requests_locked_sync`

Expected: FAIL because mode-specific argument construction is absent.

- [ ] **Step 3: Implement mode-specific command construction.**

Packaged read-only commands use `uv --directory <pipeline> run --no-sync clipgauge`. Initialization uses `uv --directory <pipeline> sync --locked`. Managed operations use `run --no-sync`. Dev commands retain repository paths but use the same mode contract.

- [ ] **Step 4: Write coordinator concurrency tests.**

~~~rust
#[test]
fn concurrent_initializers_share_one_result() {
    let coordinator = InitializationCoordinator::test_double();
    let results = run_two_threads(|| coordinator.ensure_initialized());
    assert_eq!(coordinator.sync_count(), 1);
    assert!(results.iter().all(Result::is_ok));
}

#[test]
fn failed_initialization_can_retry() {
    let coordinator = InitializationCoordinator::test_double_failing_once();
    assert!(coordinator.ensure_initialized().is_err());
    assert!(coordinator.ensure_initialized().is_ok());
    assert_eq!(coordinator.sync_count(), 2);
}
~~~

- [ ] **Step 5: Run coordinator tests and observe failure.**

Run: `cargo test --manifest-path app/src-tauri/Cargo.toml concurrent_initializers_share_one_result failed_initialization_can_retry`

Expected: FAIL because the coordinator is absent.

- [ ] **Step 6: Implement single-flight initialization.**

Store the coordinator in `AppState`. Use a mutex and condition variable. Clear the owner on every error, timeout, and cancellation. Require a successful locked sync and probe before marking initialized.

- [ ] **Step 7: Run all Task 2 tests.**

Run: `cargo test --manifest-path app/src-tauri/Cargo.toml sidecar::tests`

Expected: PASS with zero failures.

### Task 3: Add native, read-only initial inventory

**Files:**

- Create: `app/src-tauri/src/setup_inventory.rs`
- Modify: `app/src-tauri/src/main.rs`
- Test: `app/src-tauri/src/setup_inventory.rs`
- Test: `app/src-tauri/src/main.rs`

**Interfaces:**

- `native_inventory(resources, home)` returns `SetupInventory` JSON.
- `SetupInventory.state` is `SETUP_REQUIRED`, `READY`, or `REPAIR_REQUIRED`.
- `SetupInventory.youtube` is informational and non-blocking.

- [ ] **Step 1: Write fresh-home inventory tests.**

~~~rust
#[test]
fn fresh_inventory_reports_sizes_without_running_python() {
    let result = native_inventory(&fixtures::resources(), &fixtures::empty_home()).unwrap();
    assert_eq!(result.state, "SETUP_REQUIRED");
    assert!(result.storage.required_bytes > 0);
    assert!(result.models.iter().any(|row| row.size_bytes > 0));
}

#[test]
fn inventory_does_not_require_youtube_or_provider_credentials() {
    let result = native_inventory(&fixtures::resources(), &fixtures::empty_home()).unwrap();
    assert_eq!(result.youtube.state, "NOT_CHECKED");
    assert!(result.provider_credentials.is_empty());
}
~~~

- [ ] **Step 2: Run tests and observe failure.**

Run: `cargo test --manifest-path app/src-tauri/Cargo.toml fresh_inventory_reports_sizes_without_running_python inventory_does_not_require_youtube_or_provider_credentials`

Expected: FAIL because native inventory is absent.

- [ ] **Step 3: Implement manifest-backed inventory.**

Read `runtime-manifest.json` from the executable resource directory. Check user-owned files and hashes. Detect available disk space. Report exact pinned sizes. Do not spawn a process or contact a network.

- [ ] **Step 4: Add the Tauri command.**

Expose `setup_inventory` through `invoke`. Return structured errors with a diagnostic ID when resource lookup or manifest parsing fails.

- [ ] **Step 5: Run native inventory tests.**

Run: `cargo test --manifest-path app/src-tauri/Cargo.toml setup_inventory`

Expected: PASS with zero failures.

### Task 4: Bound setup bridge operations

**Files:**

- Modify: `app/src-tauri/src/main.rs`
- Modify: `app/src-tauri/src/process_manager.rs`
- Test: `app/src-tauri/src/main.rs`

- [ ] **Step 1: Write timeout and cleanup tests.**

~~~rust
#[test]
fn setup_status_timeout_returns_actionable_terminal_error() {
    let result = run_setup_status_with_test_command(TestCommand::Hang);
    assert_eq!(result.code, "SETUP_STATUS_TIMED_OUT");
    assert!(result.retryable);
    assert!(!result.diagnostic_id.is_empty());
}

#[test]
fn streamed_setup_drains_stderr_and_releases_reservation() {
    let result = run_stream_setup_with_test_command(TestCommand::NoisySuccess);
    assert!(result.ok);
    assert_eq!(test_process_manager().active_count(), 0);
}
~~~

- [ ] **Step 2: Run tests and observe failure.**

Run: `cargo test --manifest-path app/src-tauri/Cargo.toml setup_status_timeout_returns_actionable_terminal_error streamed_setup_drains_stderr_and_releases_reservation`

Expected: FAIL because current setup waits are unbounded.

- [ ] **Step 3: Route setup status through `run_bounded`.**

Use short status deadlines. Map missing environment, timeout, non-zero exit, malformed JSON, and spawn errors into distinct structured results. Never return an unresolved promise.

- [ ] **Step 4: Fix streamed setup output ownership.**

Drain stderr continuously. Apply process-group configuration. Enforce hard and idle deadlines. Emit exactly one terminal event. Join all output reader threads before releasing the reservation.

- [ ] **Step 5: Verify cancellation and retry.**

Run: `cargo test --manifest-path app/src-tauri/Cargo.toml setup_status_timeout_actionable streamed_setup_drains_stderr`

Expected: PASS with zero failures.

### Task 5: Add frontend lifecycle state machine

**Files:**

- Create: `app/src/setupLifecycle.ts`
- Test: `app/src/setupLifecycle.test.ts`
- Modify: `app/src/api.ts`

**Interfaces:**

- `SetupLoadState` covers loading, ready, setup-required, repair-required, offline, error, timeout.
- `beginSetupRequest()` returns a generation token.
- `settleSetupRequest(token, result)` rejects stale generations.
- `withTimeout(operation, timeoutMs)` returns a terminal timeout result.

- [ ] **Step 1: Write failing lifecycle tests.**

~~~typescript
it('settles a hanging inventory request as timed out', async () => {
  await expect(withTimeout(new Promise(() => undefined), 5)).resolves.toMatchObject({ state: 'TIMED_OUT' })
})

it('ignores an older inventory response', () => {
  const first = beginSetupRequest()
  const second = beginSetupRequest()
  expect(settleSetupRequest(first, readyResult())).toBeNull()
  expect(settleSetupRequest(second, readyResult())).toMatchObject({ state: 'READY' })
})
~~~

- [ ] **Step 2: Run focused tests and observe failure.**

Run: `npm --prefix app test -- setupLifecycle.test.ts`

Expected: FAIL because the lifecycle helper is absent.

- [ ] **Step 3: Implement typed terminal transitions.**

Use a generation counter and mounted guard. Preserve actionable error codes and diagnostic IDs. Return timeout after the fixed deadline. Do not use a swallowed catch to represent a state.

- [ ] **Step 4: Run lifecycle tests.**

Run: `npm --prefix app test -- setupLifecycle.test.ts`

Expected: PASS with zero failures.

### Task 6: Integrate Setup Center without YouTube coupling

**Files:**

- Modify: `app/src/components/SetupCenter.tsx`
- Test: `app/src/components/SetupCenter.test.tsx`
- Modify: `app/src/api.ts`

- [ ] **Step 1: Write failing interaction tests.**

~~~tsx
it('shows setup required after fast native inventory', async () => {
  render(<SetupCenter onBack={() => undefined} />)
  expect(await screen.findByText('Core setup needed')).toBeVisible()
  expect(screen.getByText(/approve these one-time downloads/i)).toBeVisible()
})

it('shows YouTube timeout without blocking core setup', async () => {
  render(<SetupCenter onBack={() => undefined} />)
  expect(await screen.findByText(/Core setup needed|Ready to create clips/)).toBeVisible()
  expect(await screen.findByText(/timed out|unavailable/i)).toBeVisible()
})
~~~

- [ ] **Step 2: Run focused tests and observe failure.**

Run: `npm --prefix app test -- SetupCenter.test.tsx`

Expected: FAIL because Setup Center still uses permanent placeholders.

- [ ] **Step 3: Use native inventory and independent YouTube state.**

Start native inventory first. Start YouTube readiness separately through bounded API calls. Render explicit loading, ready, setup-required, repair, offline, error, and timeout copy. Add Retry controls. Keep local creation available after YouTube failure.

- [ ] **Step 4: Remove permanent placeholder copy.**

Use `Loading setup information…` only during loading. Show known sizes from native inventory. Replace `Checking YouTube tools…` with terminal failure copy after timeout or error.

- [ ] **Step 5: Run frontend regressions.**

Run: `npm --prefix app test -- SetupCenter.test.tsx setupLifecycle.test.ts`

Expected: PASS with zero failures.

### Task 7: Add fresh Windows qualification

**Files:**

- Create: `.github/windows-fresh-first-launch.ps1`
- Create: `.github/windows-fresh-first-launch.test.mjs`
- Modify: `.github/workflows/windows.yml`

- [ ] **Step 1: Write contract tests.**

~~~javascript
test('fresh qualification launches before environment seeding', () => {
  const text = readFileSync(scriptPath, 'utf8')
  assert.match(text, /Remove-Item.*\.clipgauge/)
  assert.doesNotMatch(text, /uv.*sync.*before.*launch/i)
  assert.match(text, /PIPELINE_NOT_INITIALIZED|SETUP_REQUIRED/)
})
~~~

- [ ] **Step 2: Run the contract test and observe failure.**

Run: `node --test .github/windows-fresh-first-launch.test.mjs`

Expected: FAIL because the fresh gate is absent.

- [ ] **Step 3: Implement clean install orchestration.**

Install NSIS into a temporary profile with spaces. Launch from a separate working directory. Assert native inventory reaches a terminal state. Track child processes. Approve setup through UI. Record bootstrap timing, warm inventory timing, and child-process cleanup.

- [ ] **Step 4: Add the workflow job.**

Keep warm qualification. Add a separate fresh job that never calls `uv sync` or creates creator assets before first launch. Upload sanitized JSON evidence and screenshots.

- [ ] **Step 5: Run contract tests.**

Run: `node --test .github/windows-fresh-first-launch.test.mjs .github/release-notes-contract.test.mjs`

Expected: PASS with zero failures.

### Task 8: Complete audit, documentation, and release qualification

**Files:**

- Modify: `README.md`
- Modify: `INSTALL.md`
- Modify: `TROUBLESHOOTING.md`
- Modify: `CHANGELOG.md`
- Create: `docs/qa/v0.5.10-stabilization-ledger.md`

- [ ] **Step 1: Write the audit ledger.**

Record every tracked file, category, inspection result, finding, action, and verification. Include all 349 tracked paths, 256 first-party text files, 53 tests, 29 workflow/build files, 72 binary/media files, and 12 vendored files.

- [ ] **Step 2: Update truthful fallback guidance.**

State that v0.5.3 remains the fallback. State that YouTube-link import may fail there. Tell users to obtain media separately and use local media import.

- [ ] **Step 3: Run the complete local gates.**

Run `uv sync --dev` and `uv run pytest -q` in `pipeline`. Run `npm ci`, `npm run build`, and `npm test` in `app`. Run Cargo format, tests, and clippy. Run version, visual-asset, release-contract, SBOM, and available security scans.

- [ ] **Step 4: Re-read modified files and adversarially search.**

Search for raw `uv run`, unbounded waits, swallowed setup catches, duplicated process launchers, stale placeholder copy, and version mismatches. Re-run focused regressions after every correction.

- [ ] **Step 5: Run remote CI and packaged gates.**

Push the stabilization branch. Open one PR. Wait for all required workflows. Fix failures from their root causes. Run upgrade and public-installer qualification only after merge authorization is satisfied.

- [ ] **Step 6: Version and release last.**

Bump all authoritative surfaces to 0.5.10. Run version consistency. Merge normally. Create an annotated immutable tag only after post-merge qualification. Verify public assets, checksums, SBOM, provenance, attestation, and fresh public installer behavior.

