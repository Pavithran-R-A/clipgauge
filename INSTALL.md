# Installing ClipGauge v0.1.0

ClipGauge v0.1.0 is distributed as source and as an unsigned Linux Debian artifact. This document describes the reproducible source path first because platform signing and notarization are not configured for this release.

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

Do not treat an unsigned artifact as proof of publisher identity. Distribution, checksums, signing, and trust decisions remain the user’s responsibility for v0.1.0.

## First launch and data directories

ClipGauge stores managed jobs, checkpoints, downloaded runtime components, credentials metadata, diagnostics, and support bundles under `~/.clipgauge`. First-run preflight reports missing tools, model/runtime readiness, disk-space concerns, and selected-provider configuration before a job starts. Older data under `~/.publikclip` is considered for one-way migration into the new root; the legacy source is preserved and a migration marker is written only after a collision-free copy.

The application does not silently promise a fixed download size or runtime duration. Model availability, source length, selected LLM, and local hardware affect first-run cost and processing time. The UI reports stage progress and preserves safe checkpoints for resumable jobs.

## Choosing a scoring mode

Gemini requires a user-provided API key and sends the documented transcript slices, scoring context, and sampled finalist frames to the provider. Ollama uses a loopback service and keeps scoring requests on the local machine. Both modes are optional; the app cannot promise identical scores across providers.

For local scoring, install [Ollama](https://ollama.com/), start it, and pull a compatible chat model. ClipGauge’s preflight screen reports whether a local model is available. For Gemini, enter the key through onboarding or the in-app credential modal; do not put the key in `.env` files or commit it.

## Optional Instagram integration

Instagram is not required for clipping. If enabled, use your own Meta application, configure the loopback redirect URI shown by the app, and keep the app in the provider’s permitted development mode unless you separately complete the provider’s requirements. ClipGauge uses ephemeral OAuth callback handling and stores the resulting connection through the credential abstraction.

## Uninstall and reset

To remove application data, first export any clips you want to keep, close ClipGauge, and remove `~/.clipgauge` using your operating system’s file manager or a deliberate shell command. Credential-store entries may be separate from this directory and should be removed through the platform credential manager. The legacy `~/.publikclip` directory is not deleted by migration.

## References

[1]: https://v2.tauri.app/start/prerequisites/ "Tauri 2 prerequisites"
[2]: https://docs.astral.sh/uv/ "uv documentation"
[3]: https://ollama.com/ "Ollama"
