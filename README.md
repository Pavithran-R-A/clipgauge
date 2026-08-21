# ClipGauge

**Long video in. Auditable vertical clips out. Everything runs locally by default.**

ClipGauge is an AGPL-3.0-or-later desktop application for turning a YouTube URL or local horizontal video into scored 9:16 clips. It combines transcription, speaker and laughter signals, active-speaker camera direction, captions, rendering, and an explainable clip ledger. The project is a modified derivative of [Blueturboguy07/publikclip](https://github.com/Blueturboguy07/publikclip); the exact baseline and changes are documented in [`ORIGIN.md`](ORIGIN.md).

| Capability | What ClipGauge does |
|---|---|
| Smart camera | Uses speaker and scene signals to select and smooth vertical crop paths, with cut and punch-in decisions recorded in the clip ledger. |
| Word-level captions | Supports multiple caption presets, karaoke highlighting, prosodic emphasis, and detected laughter markers when the local pipeline provides those signals. |
| Explainable scoring | Shows subscores, adjustments, detector signals, and provenance instead of presenting an unauditable number. |
| Local-first processing | Keeps source media and managed job state local by default, with Ollama, LM Studio, and compatible local endpoints available for loopback inference. |
| Universal providers | Uses one capability-aware scoring contract for Gemini, OpenRouter, Groq, Cloudflare Workers AI, Hugging Face, Cerebras, Ollama, LM Studio, and custom OpenAI-compatible endpoints. |
| Privacy-aware inference | Shows provider, model, endpoint identity, local/cloud state, structured-output level, and vision degradation in provenance and Privacy Activity. |

## Current release

ClipGauge v0.3.0 is the creator-experience release. It adds ClipGauge Local as a managed, loopback-only structured-scoring option; a progressive Setup Center with consent-aware downloads and verification; typed diagnostics; resumable progress; creator-first onboarding; and the Studio, Review, Settings, and Diagnostics surfaces. v0.1.0, v0.1.1, v0.2.0, and v0.2.1 remain immutable historical releases.

The v0.3.0 release artifacts are unsigned unless the release notes explicitly prove otherwise. Windows SmartScreen warnings and non-notarized macOS Gatekeeper warnings are expected. The updater remains disabled because no real signing key is configured. ClipGauge Local remains optional until its pinned runtime and selected model are installed and verified.

## Provider options

Completely local options include Ollama, LM Studio, and compatible local endpoints. Curated cloud/BYO-key options include Gemini, OpenRouter, Groq, Cloudflare Workers AI, Hugging Face, and Cerebras. Free access, quotas, model support, retention, and payment requirements vary and can change; ClipGauge does not promise permanent free or unlimited usage. Any OpenAI-compatible endpoint can be configured manually with a model and validated authentication mode.

See [`docs/providers/README.md`](docs/providers/README.md) and [`docs/providers/PROVIDER_RESEARCH_2026.md`](docs/providers/PROVIDER_RESEARCH_2026.md) for setup, capability, privacy, and terms guidance.

## Public artifacts

The v0.3.0 release workflow is the source of truth for downloadable artifacts. It publishes platform artifacts only after native build, metadata, checksum, SBOM, provenance, attestation, and secret-scan gates pass. Review release notes and checksums before installing any unsigned artifact.

Every public binary is accompanied by `SHA256SUMS`. The release also includes a CycloneDX SBOM and a human-readable provenance record. A checksum is not a cryptographic attestation, and neither is a substitute for Windows code signing or Apple signing/notarization.

## Requirements

Building from source requires Git, Node.js 22 or newer, Rust via [rustup](https://rustup.rs/), Python 3.12, and [uv](https://docs.astral.sh/uv/). Linux packaging additionally requires the Tauri system libraries listed in [`INSTALL.md`](INSTALL.md). Runtime, analysis-model, and ClipGauge Local downloads require network access the first time a selected feature is used. Once verified assets are installed, ClipGauge Local scoring runs against the loopback-owned runtime without a cloud credential.

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
uv run clipgauge preflight --provider ollama
uv run clipgauge provider-test --provider openrouter --model openrouter/free
uv run clipgauge run "https://www.youtube.com/watch?v=..." --provider ollama
```

The desktop shell invokes the same CLI through `uv` in development and through the packaged resource environment in a bundle. The Rust bridge owns job lifecycle, cancellation, diagnostics, and filesystem boundaries; the Python sidecar emits structured JSONL events.

## Privacy and credentials

ClipGauge has no default telemetry and no mandatory subscription. Local processing includes source media, transcripts, model inference, scoring inputs, and rendered output. Network activity can occur when you provide a source URL, allow pinned runtime/model downloads, use a selected cloud provider, use Pexels, or opt into Instagram. The in-app **Privacy Activity** view describes the selected provider, model, endpoint, and whether frames may leave the device.

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

Read [`INSTALL.md`](INSTALL.md) for platform prerequisites, [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) for preflight and runtime failures, [`docs/providers/README.md`](docs/providers/README.md) for provider setup, and [`CHANGELOG.md`](CHANGELOG.md) for the v0.3.0 release record. License and provenance information is available in [`NOTICE.md`](NOTICE.md), [`ORIGIN.md`](ORIGIN.md), and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Use the in-app support-bundle action when reporting a failure, and redact any remaining personal or source-specific information before sharing.

## License

ClipGauge is distributed under the [GNU Affero General Public License, version 3 or later](https://www.gnu.org/licenses/agpl-3.0.html). See [`LICENSE`](LICENSE) for the complete text and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for adapted and vendored components.
