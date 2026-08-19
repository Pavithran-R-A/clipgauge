# ClipGauge Stage 1A CSP

## Policy boundary

ClipGauge uses separate production and development CSP policies. The production policy contains only bundled application sources, Tauri IPC origins, and the asset protocol origins required by `convertFileSrc`. Vite’s development server and HMR WebSocket are present only in `devCsp`; they are not permitted by the production policy.

Tauri’s current security guidance states that CSP protection is enabled only when configured and recommends tailoring the policy to the application’s trusted sources [1]. Current Tauri 2 examples use both `ipc:` and `http://ipc.localhost` for IPC and both `asset:` and `http://asset.localhost` for local assets where required [1]. The application therefore includes those exact forms rather than relying only on the legacy-looking custom schemes.

## Production policy

```text
default-src 'self';
connect-src 'self' ipc: http://ipc.localhost;
script-src 'self';
style-src 'self' 'unsafe-inline';
img-src 'self' asset: http://asset.localhost blob: data:;
media-src 'self' asset: http://asset.localhost blob:;
font-src 'self' asset: http://asset.localhost data:;
object-src 'none';
base-uri 'none';
frame-ancestors 'none'
```

The production policy contains no wildcard source, no `unsafe-eval`, and neither `http://localhost:1430` nor `ws://localhost:1430`. `ipc:` and `http://ipc.localhost` support the Tauri IPC forms required by the current Tauri 2 guidance. `asset:` and `http://asset.localhost` are present in `img-src`, `media-src`, and `font-src` where local thumbnails, video, overlays, and bundled font behavior require them. `style-src 'unsafe-inline'` remains a narrowly documented compatibility allowance because the existing React UI uses inline style props for progress widths and animation delays.

## Development policy

```text
default-src 'self';
connect-src 'self' ipc: http://ipc.localhost http://localhost:1430 ws://localhost:1430;
script-src 'self';
style-src 'self' 'unsafe-inline';
img-src 'self' asset: http://asset.localhost blob: data:;
media-src 'self' asset: http://asset.localhost blob:;
font-src 'self' asset: http://asset.localhost data:;
object-src 'none';
base-uri 'none';
frame-ancestors 'none'
```

`devCsp` adds only the Vite development origin and HMR WebSocket needed by the configured development server. It does not weaken the production CSP and still excludes wildcard sources and `unsafe-eval`.

## Directive rationale

| Directive | Production rationale | Development addition |
|---|---|---|
| `default-src` | Bundled application baseline only | None |
| `connect-src` | Tauri IPC forms only; Python provider calls occur outside the WebView | `http://localhost:1430` and `ws://localhost:1430` for Vite/HMR |
| `script-src` | Bundled scripts only | None |
| `style-src` | Existing React inline style props; temporary and documented | Same |
| `img-src` | Bundled images, Tauri asset URLs, blob previews, and data-backed images | Same |
| `media-src` | Review and ClipEditor video through Tauri asset URLs and blob/media sources | Same |
| `font-src` | Bundled fonts and current font-loading behavior | Same |
| `object-src`, `base-uri`, `frame-ancestors` | Explicitly disable unneeded embedding and document-base/frame behavior | Same |

The CSP does not grant filesystem access. Tauri’s asset protocol remains separately scoped to the Rust-owned managed media directories. Credential, model, executable, database, checkpoint, and diagnostic paths are outside that asset scope. Network calls made by the Python sidecar do not justify adding provider hosts to the WebView CSP.

## Validation

`app/src/securityConfig.test.ts` asserts the production IPC and asset origins, confirms that production omits Vite/HMR origins, confirms that `devCsp` contains them, and rejects wildcard and `unsafe-eval` sources. The frontend test suite, TypeScript/Vite build, Rust configuration/build checks, and Linux Tauri package smoke are rerun for Stage 1A.1. Native Windows and macOS runtime validation remains a platform-specific follow-up.

## References

[1]: https://v2.tauri.app/security/csp/ "Tauri 2 Content Security Policy guidance"
[2]: https://v2.tauri.app/reference/javascript/api/namespacepath/#convertfilesrc "Tauri 2 convertFileSrc API reference"
[3]: https://v2.tauri.app/reference/config/#security-csp "Tauri 2 configuration reference"
