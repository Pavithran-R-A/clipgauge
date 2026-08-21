# ClipGauge v0.4.1 Setup Center Validation

**Overall status:** PASS for the implemented frontend contract and deterministic frontend regression suite. Native packaged-resource acceptance remains a separate exact-tag Windows/macOS/Linux CI gate.

## Scope

This document records the v0.4.1 qualification of the Setup Center and onboarding download-manager presentation. The change was limited to the existing `start_setup` / `setup-event` architecture; no synchronous large-download path remains in the reviewed Studio or Onboarding setup actions.

## Qualification matrix

| Requirement | Status | Evidence |
|---|---|---|
| Determinate bytes completed and total | PASS | `Studio.tsx` renders `formatBytes(setupDone)` and `formatBytes(setupTotal)` from streamed setup events. |
| Determinate percentage | PASS | The progress bar exposes `role="progressbar"`, `aria-valuemin`, `aria-valuemax`, and `aria-valuenow`; the visible facts panel renders the percentage. |
| Transfer speed | PASS | `formatRate` renders automatic `KB/s` / `MB/s` units from `bytes_per_second`. |
| Meaningful ETA | PASS | `formatEta` suppresses early ETA values until sufficient bytes and elapsed time are available, avoiding first-kilobyte nonsense. |
| Elapsed time | PASS | `formatDuration` is rendered for active setup operations and onboarding progress. |
| Indeterminate downloads | PASS | The indeterminate branch displays a download-in-progress state without a fabricated percentage. |
| One-time and reuse labels | PASS | Asset rows and progress facts distinguish one-time download, installed/reused, and migration reuse states. |
| Storage summary | PASS | Required now, optional local AI, already installed, and available disk values are rendered above the managed asset list. |
| Per-asset detail | PASS | Rows expose download size, installed size where known, status, revision, purpose, and lifecycle state. |
| Cancellation | PASS | All six substantial Studio actions and the runtime/model onboarding actions use operation IDs and the shared cancellation path. |
| Retry | PASS | The last validated setup arguments are retained and reused by the visible retry action. |
| Frontend regression coverage | PASS | The v0.4.1 frontend suite contains 16 passing tests, including four `setupFormatting` regression tests. |
| Windows packaged interface | BLOCKED | Requires the exact-tag GitHub-hosted Windows runner; Linux cannot claim Windows acceptance. |

## Covered operations

The reviewed streaming path covers runtime installation, managed FFmpeg, ASR assets, analysis assets, YouTube compatibility assets, and the ClipGauge Local model download. Studio and Onboarding now invoke the same cancellable setup operation rather than bypassing the manager with a synchronous large-download helper.

## Evidence locations

The implementation evidence is in [`app/src/setupFormatting.ts`](../../app/src/setupFormatting.ts), [`app/src/setupFormatting.test.ts`](../../app/src/setupFormatting.test.ts), [`app/src/components/Studio.tsx`](../../app/src/components/Studio.tsx), [`app/src/components/Onboarding.tsx`](../../app/src/components/Onboarding.tsx), [`app/src/types.ts`](../../app/src/types.ts), and [`app/src/styles.css`](../../app/src/styles.css). The authoritative backend event fields remain `bytes_done`, `bytes_total`, `bytes_per_second`, `fraction`, `eta_seconds`, `elapsed_seconds`, `one_time_download`, `cached`, and `state`.

## Limitations

This document does not claim that a human visually inspected every native desktop viewport. The exact-tag platform workflows remain the source of truth for packaged installation, writable application-data checks, managed-resource resolution, and clean shutdown on their respective runners.

## Decision

The v0.4.1 Setup Center implementation satisfies the project-owned streamed-progress, lifecycle-label, storage-summary, cancellation, and retry requirements. The remaining native-runner item is an external qualification gate rather than a hidden or skipped frontend requirement.

## References

[1]: ../../app/src/setupFormatting.ts "Setup formatting helpers"
[2]: ../../app/src/components/Studio.tsx "Studio Setup Center"
[3]: ../../app/src/components/Onboarding.tsx "Onboarding setup flow"
[4]: ../../app/src/setupFormatting.test.ts "Setup formatting regression tests"

<!-- Evidence paths are repository-relative so this document remains portable. -->
