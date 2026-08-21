# ClipGauge v0.2.1 Rust Dependency Security Review

## Scope and source

This review was performed on `fix/v0.2.1-total-closure` from `origin/main` at the v0.2.0 public source baseline. The exact commands and outputs are preserved under `/home/ubuntu/clipgauge-stage0/v021-evidence/dependencies/`: `cargo tree -i` outputs, `cargo-audit-before.log`, `cargo-update.log`, resolved versions, and the direct-use search.

## Exact resolved stack

| Package | Resolved version | Role |
|---|---:|---|
| Tauri | 2.11.5 | Application framework |
| tauri-runtime | 2.11.3 | Tauri runtime abstraction |
| tauri-runtime-wry | 2.11.4 | Tauri Wry runtime |
| Wry | 0.55.1 | Cross-platform webview backend |
| tao | 0.35.3 | Windowing backend |
| GTK | 0.18.2 | GTK3 Rust bindings in the Linux graph |
| WebKitGTK Rust binding | 2.0.2 | WebKitGTK 4.1-era Rust binding |
| glib | 0.18.5 | GTK/WebKit transitive GLib binding |

The current public Tauri release metadata observed during this review was Tauri `v2.11.5`, while the current public Wry release metadata was `v0.56.1`. Normal `cargo update` completed successfully but retained Wry `0.55.1`, GTK3 bindings, and glib `0.18.5` because the current stable Tauri graph does not adopt the newer Wry GTK4/WebKit6 line. No arbitrary git dependency or forced glib override was introduced.

## Exact dependency path

The primary path is:

> `clipgauge-app → tauri 2.11.5 → tauri-runtime-wry 2.11.4 → wry 0.55.1 → gtk 0.18.2 / webkit2gtk 2.0.2 → glib 0.18.5`

Additional Linux graph paths enter through `tao 0.35.3`, `muda 0.19.3`, Tauri plugins, and the GTK/WebKit support crates. The inverse trees show that the same glib 0.18.5 is reachable through GTK, WebKitGTK, Wry, `tauri-runtime-wry`, Tauri, and the app. Unicode warnings enter through `tauri-utils → urlpattern → unic-*`; the proc-macro warning enters through GTK/glib macros.

## RUSTSEC-2024-0429 decision

RustSec reports that `glib` versions `>=0.15.0,<0.20.0` are affected and `>=0.20.0` is patched. It names `glib::VariantStrIter::{last,next,next_back,nth,nth_back}` and explains that an unsound mutable out-argument was passed through an immutable reference, potentially causing invalid pointers and crashes.[1]

ClipGauge source search found no direct use of `VariantStrIter`, `glib::Variant`, or Variant string iteration. That is evidence of **TRANSITIVE ONLY** use in ClipGauge source, not proof that the dependency is harmless. The affected Linux GTK3/WebKit graph is owned by the current Tauri/Wry stack.

A direct glib 0.20 override is unsafe because GTK4 is a major API/ABI migration from GTK3, not a compatible point update.[4] The official Wry migration issue describes GTK3/WebKitGTK 4.1 to GTK4/WebKit6 as a broad migration with breaking WebViewHandle and Linux embedding changes, and the linked tao migration work remains upstream migration work rather than a released stable Tauri-compatible update.[2] [3]

**Final state: UPSTREAM DEPENDENCY BLOCKER / KNOWN RISK.** The current supported stable Tauri/Wry graph still resolves glib 0.18.5; the patched GTK4/WebKit6 path is not a compatible drop-in for ClipGauge; no safe supported upgrade path was available during this review. Re-evaluate when a stable Tauri release adopts the GTK4/WebKit6 Wry/Tao stack or another supported graph resolves glib `>=0.20` without forced incompatibility. ClipGauge does not claim “zero advisories.”

## Complete cargo-audit warning table

| ID | Crate/version | Dependency path | Type/severity | Platform | Fix availability | Action | Final status |
|---|---|---|---|---|---|---|---|
| RUSTSEC-2024-0413 | atk 0.18.2 | `tauri → muda → gtk` | Unmaintained GTK3 binding | Linux | GTK4 port upstream; not stable-compatible here | Track Tauri/Wry GTK4 migration | Upstream-blocked transitive |
| RUSTSEC-2024-0416 | atk-sys 0.18.2 | `tauri → muda → gtk` | Unmaintained GTK3 binding | Linux | Same | Track upstream | Upstream-blocked transitive |
| RUSTSEC-2024-0412 | gdk 0.18.2 | `wry → gtk` | Unmaintained GTK3 binding | Linux | Same | Track upstream | Upstream-blocked transitive |
| RUSTSEC-2024-0418 | gdk-sys 0.18.2 | `wry → gtk` | Unmaintained GTK3 binding | Linux | Same | Track upstream | Upstream-blocked transitive |
| RUSTSEC-2024-0411 | gdkwayland-sys 0.18.2 | `wry → gtk` | Unmaintained GTK3 binding | Linux/Wayland | Same | Track upstream | Upstream-blocked transitive |
| RUSTSEC-2024-0417 | gdkx11 0.18.2 | `wry → gtk` | Unmaintained GTK3 binding | Linux/X11 | Same | Track upstream | Upstream-blocked transitive |
| RUSTSEC-2024-0414 | gdkx11-sys 0.18.2 | `wry → gtk` | Unmaintained GTK3 binding | Linux/X11 | Same | Track upstream | Upstream-blocked transitive |
| RUSTSEC-2024-0415 | gtk 0.18.2 | `tauri → muda → gtk` and `wry` | Unmaintained GTK3 binding | Linux | GTK4 migration required | Track upstream | Upstream-blocked transitive |
| RUSTSEC-2024-0420 | gtk-sys 0.18.2 | GTK3 binding graph | Unmaintained GTK3 binding | Linux | Same | Track upstream | Upstream-blocked transitive |
| RUSTSEC-2024-0419 | gtk3-macros 0.18.2 | `gtk → gtk3-macros` | Unmaintained GTK3 proc macro | Linux build graph | GTK4 migration required | Track upstream | Upstream-blocked transitive |
| RUSTSEC-2024-0370 | proc-macro-error 1.0.4 | `gtk3-macros → glib-macros` | Unmaintained proc-macro helper | Linux build graph | Transitive replacement depends on GTK4 migration | Do not force independently | Upstream-blocked transitive |
| RUSTSEC-2025-0081 | unic-char-property 0.9.0 | `tauri-utils → urlpattern → unic-ucd-ident` | Unmaintained Unicode helper | All builds using Tauri utils | Requires upstream urlpattern/Tauri update | Track upstream; no direct use | Upstream-blocked transitive |
| RUSTSEC-2025-0075 | unic-char-range 0.9.0 | `tauri-utils → urlpattern` | Unmaintained Unicode helper | All builds using Tauri utils | Same | Track upstream | Upstream-blocked transitive |
| RUSTSEC-2025-0080 | unic-common 0.9.0 | `tauri-utils → urlpattern` | Unmaintained Unicode helper | All builds using Tauri utils | Same | Track upstream | Upstream-blocked transitive |
| RUSTSEC-2025-0100 | unic-ucd-ident 0.9.0 | `tauri-utils → urlpattern` | Unmaintained Unicode helper | All builds using Tauri utils | Same | Track upstream | Upstream-blocked transitive |
| RUSTSEC-2025-0098 | unic-ucd-version 0.9.0 | `tauri-utils → urlpattern` | Unmaintained Unicode helper | All builds using Tauri utils | Same | Track upstream | Upstream-blocked transitive |
| RUSTSEC-2024-0429 | glib 0.18.5 | `tauri → tauri-runtime-wry → wry → GTK/WebKitGTK` plus plugin paths | Unsoundness in VariantStrIter | Linux GTK3/WebKitGTK path | Patched in glib `>=0.20`; safe adoption requires GTK4/WebKit6 stack | Track Tauri/Wry GTK4 migration; no ignore entry hiding the advisory | Upstream-blocked known risk |

No cargo-audit ignore entry was added. `cargo audit` continues to report the warnings transparently and exits 0 under its current default warning policy; the report does not call that “clean.”

## References

[1]: https://rustsec.org/advisories/RUSTSEC-2024-0429.html "RustSec RUSTSEC-2024-0429"  
[2]: https://github.com/tauri-apps/wry/issues/1474 "Wry GTK4/WebKit6 migration tracking"  
[3]: https://github.com/tauri-apps/tao/pull/1104 "Tao GTK4-rs migration work"  
[4]: https://docs.gtk.org/gtk4/migrating-3to4.html "Official GTK3 to GTK4 migration guide"
