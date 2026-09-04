# Installing ClipGauge v0.5.9

ClipGauge v0.5.9 is distributed from source and, when the native release gates succeed, as unsigned Linux Debian, Windows NSIS, and macOS qualification artifacts. No signing or notarization is implied unless the release evidence explicitly proves it.

## Source-build prerequisites

Install the following before building:

| Requirement | Purpose | Reference |
|---|---|---|
| Git | Clone the repository and preserve project history | [git-scm.com](https://git-scm.com/) |
| Node.js 22 or newer | Build the React/Vite frontend and run the Tauri CLI | [nodejs.org](https://nodejs.org/) |
| Rust stable and Cargo | Compile the Tauri desktop shell | [rustup.rs](https://rustup.rs/) |
| Python 3.12 | Run the pinned Python pipeline environment | [python.org](https://www.python.org/) |
| uv | Resolve the Python environment and invoke the pipeline | [docs.astral.sh/uv](https://docs.astral.sh/uv/) |

The pipeline declares Python `>=3.12,<3.13`. GPU acceleration is not required by the release contract, but model execution time and memory use depend on the machine and the selected stages.

## Linux prerequisites

Install the Tauri/WebKit development packages appropriate to your distribution. On Debian or Ubuntu, the usual starting point is:

```sh
sudo apt update
sudo apt install -y \
  libwebkit2gtk-4.1-dev \
  build-essential \
  curl \
  wget \
  file \
  libxdo-dev \
  libssl-dev \
  libayatana-appindicator3-dev \
  librsvg2-dev
```

Package names can differ by distribution and desktop release. If the Tauri build reports a missing system library, follow the corresponding [Tauri prerequisites documentation](https://v2.tauri.app/start/prerequisites/).

## Build from source

```sh
git clone https://github.com/Pavithran-R-A/clipgauge.git
cd clipgauge/app
npm ci
npm run build
npm run tauri build -- --bundles deb
```

The Debian package is generated under `src-tauri/target/release/bundle/deb/`. It is unsigned. Verify the package metadata and inspect the artifact before installation:

```sh
dpkg-deb --info src-tauri/target/release/bundle/deb/*.deb
dpkg-deb --contents src-tauri/target/release/bundle/deb/*.deb
```

Do not treat an unsigned artifact as proof of publisher identity. Verify `SHA256SUMS`, review package metadata, and understand that Windows may show SmartScreen warnings. macOS builds that are not signed and notarized may be blocked or warned about by Gatekeeper. Distribution, signing, notarization, and trust decisions remain explicit release limitations for v0.5.9.

## Windows and macOS release artifacts

The v0.5.9 release workflow builds a fresh Windows x64 NSIS installer from the v0.5.9 tag only after native tests, resource staging, silent installation, and installed-process smoke checks pass. The installer is unsigned. Do not describe it as Authenticode-signed.

The release workflow also attempts native Apple Silicon and Intel macOS qualification. These jobs inspect `.app` metadata and packaged resources and may build unsigned DMG files for engineering validation. A successful macOS compilation is not a signed or notarized distribution claim; use the release notes to determine whether any macOS artifact is attached publicly.

## First launch and data directories

ClipGauge stores managed jobs, checkpoints, consented runtime/model components, credentials metadata, diagnostics, and support bundles under `~/.clipgauge`. Setup Center presents exact managed groups and byte estimates before downloading. Each download is resumable, cancellable, SHA-256 verified, and atomically installed; compute stages do not silently fetch large files. First-run preflight reports missing assets, disk-space concerns, hardware, and selected-provider configuration before a job starts. Older data under `~/.publikclip` and verified library caches are considered for one-way migration; the source is preserved and only complete hash matches are reused.

The application shows measured asset sizes where upstream metadata is available and identifies any bounded estimate. Model availability, source length, selected LLM, and local hardware affect processing time. Setup reports download progress, speed, elapsed time, ETA when known, cache reuse, and cancellation state; the pipeline reports an actionable setup error instead of beginning a hidden download.

## Choosing a scoring mode

Gemini requires a user-provided API key and sends the documented transcript slices, scoring context, and sampled finalist frames to the provider. Ollama uses a loopback service and keeps scoring requests on the local machine. Both modes are optional; the app cannot promise identical scores across providers.

For local scoring, either approve the ClipGauge Local group in Setup Center or install [Ollama](https://ollama.com/) / LM Studio separately and point ClipGauge at the documented loopback endpoint. ClipGauge probes local services and does not silently start or download models for Ollama or LM Studio. For Gemini, enter the key through onboarding or the in-app credential modal; do not put the key in `.env` files or commit it.

## YouTube compatibility and browser authentication

YouTube workflows use the explicit `core:youtube` Setup Center group, which contains the pinned yt-dlp binary, a portable Node.js runtime, and the GPL-3.0-only bgutil PO-token provider. The provider binds to `127.0.0.1` only. Browser cookies are never read by default. If you intentionally need an authenticated browser session, select a supported browser through the explicit `--cookies-from-browser` option; the choice is recorded in the job snapshot and raw cookies are not copied into ClipGauge data.

See [`docs/v0.4/V0_4_USER_WORKFLOW.md`](docs/v0.4/V0_4_USER_WORKFLOW.md) for the complete asset layout and recovery contract.

## Optional Instagram integration

Instagram is not required for clipping. If enabled, use your own Meta application, configure the loopback redirect URI shown by the app, and keep the app in the provider’s permitted development mode unless you separately complete the provider’s requirements. ClipGauge uses ephemeral OAuth callback handling and stores the resulting connection through the credential abstraction.

## Uninstall and reset

To remove application data, first export any clips you want to keep, close ClipGauge, and remove `~/.clipgauge` using your operating system’s file manager or a deliberate shell command. Credential-store entries may be separate from this directory and should be removed through the platform credential manager. The legacy `~/.publikclip` directory is not deleted by migration.

## References

[1]: https://v2.tauri.app/start/prerequisites/ "Tauri 2 prerequisites"
[2]: https://docs.astral.sh/uv/ "uv documentation"
[3]: https://ollama.com/ "Ollama"
