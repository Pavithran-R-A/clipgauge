# ClipGauge Security Policy

## Reporting

Please report security issues privately through the repository’s supported security-reporting channel rather than publishing credentials, private media, or exploit details in an issue. Do not include API keys, bearer tokens, cookies, OS keychain contents, or raw user videos in a report or support bundle.

## Rust dependency advisory status

ClipGauge v0.2.1 does not claim a zero-advisory Rust dependency graph. The current stable Tauri/Wry Linux stack resolves GTK3-era crates and `glib 0.18.5` through `tauri 2.11.5 → tauri-runtime-wry 2.11.4 → wry 0.55.1 → gtk/webkit2gtk`. `cargo audit` reports the GTK3 binding maintenance advisories and RUSTSEC-2024-0429.

RUSTSEC-2024-0429 affects `glib >=0.15.0,<0.20.0` and is patched in `glib >=0.20.0`. The advisory names `glib::VariantStrIter::{last,next,next_back,nth,nth_back}` and describes unsound pointer mutation that can lead to invalid pointers and crashes. ClipGauge source search found no direct use of those APIs: the advisory is **transitive only in ClipGauge source**, not proven harmless.

A direct glib-only upgrade is not safe under the current GTK3 graph. GTK4 is a major API/ABI migration, and current official Wry/Tao migration work changes the Linux webview/window API and system requirements. Normal Cargo resolution retains Wry 0.55.1 because `tauri-runtime-wry 2.11.4` requires `wry ^0.55.0`; forcing Wry 0.56.1 or glib 0.20 would create an unsupported dependency graph.

**Status:** **UPSTREAM DEPENDENCY BLOCKER / KNOWN RISK**, not fixed. The practical exposure is limited to the Linux GTK3/WebKitGTK transitive path, with no direct ClipGauge call site identified. This status must be re-evaluated when a stable supported Tauri release adopts the GTK4/WebKit6 migration or otherwise resolves glib `>=0.20` without incompatible overrides. The dependency report in `docs/v0.2.1/RUST_DEPENDENCY_SECURITY.md` lists every current cargo-audit warning and its path/status.

## Application security controls

ClipGauge keeps credentials in the operating-system credential store where available, injects secrets only into the operation that needs them, rejects dangerous provider URL forms, never follows authenticated redirects, isolates provider cache identity, validates job/edit paths, confines export artifacts, and redacts diagnostics/support bundles. These controls are covered by the Rust, Python, frontend, and provider contract suites. Live provider and Windows keyring behavior must be verified in their actual environments when available.
