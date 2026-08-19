# ClipGauge

**Long video in. Auditable vertical clips out. Everything runs locally by default.**

ClipGauge is an AGPL-3.0-or-later desktop application for turning a YouTube URL or local horizontal video into scored 9:16 clips. It combines transcription, speaker and laughter signals, active-speaker camera direction, captions, rendering, and an explainable clip ledger. The project is a modified derivative of [Blueturboguy07/publikclip](https://github.com/Blueturboguy07/publikclip); the exact baseline and changes are documented in [`ORIGIN.md`](ORIGIN.md).

| Capability | What ClipGauge does |
|---|---|
| Smart camera | Uses speaker and scene signals to select and smooth vertical crop paths, with cut and punch-in decisions recorded in the clip ledger. |
| Word-level captions | Supports multiple caption presets, karaoke highlighting, prosodic emphasis, and detected laughter markers when the local pipeline provides those signals. |
| Explainable scoring | Shows subscores, adjustments, detector signals, and provenance instead of presenting an unauditable number. |
| Local-first processing | Keeps source media and managed job state local by default, with Ollama available for loopback-only scoring. |
| Optional integrations | Supports user-selected Gemini, Pexels, source URL download, and Instagram workflows. These are optional and can make network requests. |

## Current release

ClipGauge v0.1.1 is a public open-source release-engineering closure release. It does not rewrite the analytical pipeline. Linux amd64 and Windows x64 release artifacts are unsigned when the corresponding native release jobs succeed. Native macOS builds are qualification results from GitHub-hosted runners; macOS distribution is not claimed to be signed or notarized unless real Apple credentials were used and the release explicitly says so. The updater remains disabled because no real signing key is configured.

Unsigned Windows software may trigger SmartScreen or other reputation warnings. Unsigned and non-notarized macOS software may be blocked or warned about by Gatekeeper. These warnings are expected consequences of distributing without platform signing credentials; they are not evidence that ClipGauge is signed or notarized. Review the release notes and checksums before installing any artifact.

The earlier v0.1.0 release remains available as historical release metadata and packaging. v0.1.1 supersedes it for release-engineering documentation, version consistency, SBOM correctness, and current platform packaging. The v0.1.0 tag and release are not rewritten.

## Public artifacts

The v0.1.1 release workflow is the source of truth for downloadable artifacts. It publishes a Linux amd64 Debian package and a Windows x64 NSIS installer only after their native release jobs pass. macOS builds are retained as CI qualification artifacts unless the release notes explicitly identify an unsigned, non-notarized macOS asset.

Every public binary is accompanied by `SHA256SUMS`. The release also includes a CycloneDX SBOM and a human-readable provenance record. A checksum is not a cryptographic attestation, and neither is a substitute for Windows code signing or Apple signing/notarization.

## Requirements

Building from source requires Git, Node.js 22 or newer, Rust via [rustup](https://rustup.rs/), Python 3.12, and [uv](https://docs.astral.sh/uv/). Linux packaging additionally requires the Tauri system libraries listed in [`INSTALL.md`](INSTALL.md). Runtime model and binary downloads require network access the first time a selected feature is used; fully local scoring can use an installed Ollama model.

## Install from source

Clone the ClipGauge repository and build the desktop application:

```sh
git clone https://github.com/Pavithran-R-A/clipgauge.git
cd clipgauge/app
npm ci
npm run tauri build -- --bundles deb
```

The unsigned Debian artifact is written beneath `app/src-tauri/target/release/bundle/deb/`. Install it only if you understand that it is unsigned and review the package metadata before use. A source-development run is available with:

```sh
npm run tauri dev
```

On first run, ClipGauge performs local preflight checks and guides you through the selected scoring mode. Models and pinned runtime components are fetched into the managed local data directory only when required. The default data root is `~/.clipgauge`; older `~/.publikclip` data is treated as a migration source and is not deleted automatically.

## Python pipeline and CLI

The pipeline is a separately testable Python package named `clipgauge-pipeline`. Its executable is `clipgauge` and its import package is `clipgauge_pipeline`:

```sh
cd pipeline
uv sync
uv run pytest -q
uv run clipgauge --help
uv run clipgauge preflight --llm ollama
uv run clipgauge run "https://www.youtube.com/watch?v=..." --llm ollama
```

The desktop shell invokes the same CLI through `uv` in development and through the packaged resource environment in a bundle. The Rust bridge owns job lifecycle, cancellation, diagnostics, and filesystem boundaries; the Python sidecar emits structured JSONL events.

## Privacy and credentials

ClipGauge has no default telemetry and no mandatory subscription. Local processing includes source media, transcripts, model inference, scoring inputs, and rendered output. Network activity can occur when you provide a source URL, allow pinned runtime/model downloads, use Gemini or Pexels, or opt into Instagram. The in-app **Privacy Activity** view describes the selected mode.

Credentials are stored through the operating system credential store when available and are injected into child processes only for the operation that needs them. Do not place API keys in source files, issue reports, support bundles, or shell history. The support bundle is redacted and excludes raw source media, raw transcripts, and known credential material, but review it before sharing.

## Project layout

```text
pipeline/   Python package, CLI, model/runtime registry, and tests
app/        Tauri 2 desktop shell, React frontend, Rust bridge, and tests
docs/       Completion, release, and provenance planning material
scripts/    Deterministic version and release-metadata validators
```

## Development checks

Run the same checks used by continuous integration:

```sh
python3 scripts/check-version-consistency.py

cd app/src-tauri
cargo fmt -- --check
cargo test
cargo clippy -- -D warnings

cd ../../pipeline
uv run pytest -q

cd ../app
npm ci
npm run build
npm run test
```

The test suite includes Rust security and lifecycle tests, Python pipeline tests, and frontend tests. Hardware-dependent model execution, optional Instagram setup, platform signing, and notarization are not assumed by the deterministic source checks.

## Documentation and support

Read [`INSTALL.md`](INSTALL.md) for platform prerequisites, [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) for preflight and runtime failures, and [`CHANGELOG.md`](CHANGELOG.md) for the v0.1.1 release record. License and provenance information is available in [`NOTICE.md`](NOTICE.md), [`ORIGIN.md`](ORIGIN.md), and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Use the in-app support-bundle action when reporting a failure, and redact any remaining personal or source-specific information before sharing.

## License

ClipGauge is distributed under the [GNU Affero General Public License, version 3 or later](https://www.gnu.org/licenses/agpl-3.0.html). See [`LICENSE`](LICENSE) for the complete text and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for adapted and vendored components.
