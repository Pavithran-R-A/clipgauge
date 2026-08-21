# ClipGauge v0.4.1 Security Review

**Overall status:** PASS for the v0.4.1 project-owned design review and fresh dependency-audit execution, with non-zero Rust/Python findings recorded. No claim of zero advisories is made.

## Security boundary changes

The v0.4.1 frontend now routes substantial setup actions through the existing cancellable `start_setup` / `setup-event` boundary. This adds observable progress and retry state but does not add a new network service, credential store, remote control surface, or compute-time download path. Operation IDs remain job-scoped, and cancellation is issued through the existing Rust/Python bridge.

| Area | Status | Review result |
|---|---|---|
| Setup download consent | PASS | Managed downloads remain explicit and grouped; the UI does not silently fetch large assets during compute. |
| Download verification | PASS | Existing length/hash verification, partial-file staging, and verified-cache reuse remain the acceptance boundary. |
| Archive extraction | PASS | Existing safe extraction and filesystem-boundary tests remain in the full Rust/Python gate; no bypass was added. |
| Operation cancellation | PASS | The streaming operation ID is retained and the cancel path is available to Studio and Onboarding. |
| Retry behavior | PASS | Retry reuses validated setup arguments rather than accepting arbitrary unvalidated paths from the UI. |
| Local runtime exposure | PASS | ClipGauge Local remains loopback-owned; no public bind or new endpoint was introduced. |
| YouTube provider exposure | PASS | bgutil remains loopback-only and supervisor-owned. |
| Browser cookies | PASS | Cookies are never read by default; browser selection is explicit and recorded in the job snapshot. |
| Secrets/support bundles | PASS | Existing credential-store injection and redacted support-bundle behavior are preserved. |
| License/provenance | PASS | AGPL-3.0-or-later and publikclip attribution remain explicit; bgutil’s GPL-3.0-only status remains documented. |
| Dependency advisories | PASS | Fresh npm, Rust, and exported-lock Python audits are recorded in `V0_4_1_DEPENDENCY_AUDIT.md`; the known Rust/Python findings remain visible and are not force-upgraded or suppressed. |

## Network-surface assessment

The v0.4.1 changes do not introduce browser-side API keys, remote telemetry, inbound listeners, or background sync. Network access remains limited to explicit source retrieval, approved managed asset setup, selected provider calls, and other already-documented opt-in integrations. The new progress UI consumes structured local events; it does not make direct network requests.

## Threat and regression review

The principal v0.4.1 regression risk is an inconsistent UI/backend lifecycle state during cancellation or retry. The implementation retains the operation ID, records the last validated arguments, and updates terminal state through streamed events. The principal release risk remains environmental dependency acquisition and platform execution, not an intentionally weakened security gate.

## Decision

No new project-owned high-severity security surface was identified in the v0.4.1 changes. The release must retain the existing advisory findings, archive traversal coverage, secret scan, manifest validation, and redaction checks in the final qualification record; this document does not convert unavailable audit output into a zero-advisory claim.

## References

[1]: ../../app/src/components/Studio.tsx "Studio setup operation and privacy behavior"
[2]: ../../app/src/components/Onboarding.tsx "Onboarding setup operation behavior"
[3]: ../../pipeline/clipgauge_pipeline/local_runtime.py "Loopback local runtime"
[4]: ../../pipeline/clipgauge_pipeline/ingest/youtube_compat.py "Loopback YouTube compatibility provider"
[5]: ../../THIRD_PARTY_NOTICES.md "Third-party license and provenance notices"
