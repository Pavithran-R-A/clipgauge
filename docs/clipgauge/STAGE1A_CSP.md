# ClipGauge Stage 1A CSP

## Policy

The Tauri configuration now uses:

```text
default-src 'self' ipc: asset:;
connect-src 'self' ipc: http://localhost:1430 ws://localhost:1430;
script-src 'self';
style-src 'self' 'unsafe-inline';
img-src 'self' asset: blob: data:;
media-src 'self' asset: blob:;
font-src 'self' asset: data:;
object-src 'none';
base-uri 'none';
frame-ancestors 'none'
```

The policy is intentionally explicit. It contains no wildcard source and no `unsafe-eval`. `unsafe-inline` remains only for styles because the existing React frontend uses inline style props for visual values such as progress widths, animation delays, and platform bars; this should be removed in a future style-token cleanup if the WebView/toolchain permits it.

## Directive rationale

| Directive | Reason |
|---|---|
| `default-src 'self' ipc: asset:` | Bundled Vite code plus Tauri IPC and managed local assets are the baseline application sources |
| `connect-src 'self' ipc: http://localhost:1430 ws://localhost:1430` | Vite development server and local HMR are needed only in development; Python performs external provider calls outside the WebView and does not justify adding provider hosts here |
| `script-src 'self'` | Only bundled application scripts should execute |
| `style-src 'self' 'unsafe-inline'` | Existing React inline style props require the temporary allowance |
| `img-src 'self' asset: blob: data:` | Local thumbnails, generated asset URLs, blob previews, and data-backed images are used by current views |
| `media-src 'self' asset: blob:` | Review and editor video elements use Tauri asset URLs and local blob/media sources |
| `font-src 'self' asset: data:` | Bundled fonts and existing font loading behavior |
| `object-src 'none'` | No plugin/object embedding is required |
| `base-uri 'none'` | Prevent document-base manipulation |
| `frame-ancestors 'none'` | The desktop UI is not intended to be framed |

## Scope relationship

The CSP does not grant the WebView filesystem access. Tauri’s asset protocol remains separately scoped to the Rust-owned `$HOME/.publikclip/jobs/**` and `$HOME/.publikclip/ig_thumbs/**` directories. Credential, model, executable, database, and diagnostic paths are intentionally outside the asset scope. Network calls made by the Python sidecar are separate from WebView `connect-src` policy.

## Validation

Stage 1A validates the configuration statically through the frontend build and Rust configuration/build checks. Native packaged playback and a browser-console CSP audit remain required on Windows and macOS because this host cannot launch the full desktop application. A future test should load a valid clip, a missing clip, and an out-of-scope path and assert distinct states without broadening the policy.
