# ClipGauge v0.2.1 Total Defect Closure and Native Acceptance Plan

## Objective

Close the project-owned findings from the independent v0.2.0 A-to-Z verification without modifying v0.1.0, v0.1.1, or v0.2.0. The target is zero unresolved ClipGauge-owned blocker/high/medium defects, zero strict-Clippy failures, a conventional authoritative `clipgauge --version` command, a transparent decision on the transitive RustSec advisory, green deterministic/native CI, and honest classification of any remaining Windows, local-provider, or live-cloud limitations.

## Source and safety controls

The fix branch is created directly from `origin/main`. Existing release tags remain immutable and their original history is preserved. The upstream remote remains `Blueturboguy07/publikclip`. No credentials will be requested in chat, printed, committed, or included in evidence. No blanket warning suppression or incompatible forced Rust dependency will be used.

## Execution sequence

| Phase | Work | Required evidence | Exit condition |
|---|---|---|---|
| Baseline | Verify remotes, tags, source SHA, clean tree, and branch origin | Baseline log and tag verification | Fix branch is based on current origin/main; v0.2.0 peels to the preserved commit |
| AZ-001 | Reproduce exact strict Clippy failures; inspect Tauri command boundary; replace widened argument lists with validated typed request objects where appropriate; move definitions before tests; remove or use dead exported API | Complete pre-fix log, focused regression tests, API/security review | Full `cargo clippy --all-targets --all-features -- -D warnings` exits 0 |
| AZ-002 | Add `clipgauge --version` and `-V` from authoritative package metadata; retain help/subcommands | CLI output logs and tests | Both version flags exit 0 and equal current release version |
| AZ-003 | Map glib/GTK/Wry/Tauri dependency chains; run cargo audit; research official upstream migration status; search direct VariantStrIter use; classify all warnings | Dependency-security report and advisory table | Advisory is fixed by supported update or explicitly classified upstream-blocked with tracking and no false clean claim |
| Regression security | Re-run provider URL/redirect/cache/secret tests, vault/redaction, filesystem, editor, protocol, migration, support-bundle, CSP, and asset tests | Focused logs and updated matrix | No regression and no new project-owned medium/high/blocker defect |
| Native/provider | Use actual Windows/My Computer if available; otherwise classify Windows rows BLOCKED; test installed app, vault, mock custom provider, synthetic video, lifecycle, local providers, live providers only with existing secure credentials | Screenshots, package/installer/process/ffprobe/provider evidence | Every attempted row has VERIFIED, deterministic/static, BLOCKED, N/A, or FAILED status |
| Release decision | Bump to 0.2.1 only after actual fixes and gates; update docs/changelog/manifests; run complete fresh suite and CI | Version evidence, CI records, release candidate audit | Release only if all mandatory conditions are satisfied; otherwise stop with a closure report and no tag |
| Delivery | Update 61+ coverage rows, write closure report, assemble exclusion-safe bundle, ZIP-test and hash | Report, bundle, SHA-256 | All components classified and final verdict delivered honestly |

## Release gate

v0.2.1 may be tagged only after AZ-001 and AZ-002 are fixed, all ClipGauge-owned blocker/high/medium findings are resolved, strict Clippy is green without broad suppression, deterministic and native CI pass, Windows installed-app acceptance passes when available, and no secret/security regression exists. AZ-003 may remain only as an explicitly documented **UPSTREAM DEPENDENCY BLOCKER / KNOWN RISK** if current supported Tauri/Wry still requires the affected glib and authoritative upstream evidence shows no safe compatible path.

## Non-claims

The audit will not call the result 100% bug-free. Mock provider success will not be called live success. Missing credentials, absent local runtimes, unavailable Windows/macOS hosts, unsigned artifacts, changed quotas, and upstream dependency constraints will remain visible in the final report.
