# ClipGauge v0.6.0 (development)

ClipGauge is a local-first desktop application for finding, ranking, reviewing, and exporting short-form clips from long-form video.

It combines speech transcription, speaker information, audio events, replay signals, story structure, and optional model-based scoring. The output is intentionally reviewable: ClipGauge keeps the recommendation score, supporting signals, and edit controls visible before export instead of treating clip selection as a black box.

**Current stable release: [v0.5.21](https://github.com/Pavithran-R-A/clipgauge/releases/tag/v0.5.21)**

[Download for Windows](https://github.com/Pavithran-R-A/clipgauge/releases/download/v0.5.21/ClipGauge_0.5.21_Windows_x64_NSIS.exe) · [Download for Linux](https://github.com/Pavithran-R-A/clipgauge/releases/download/v0.5.21/ClipGauge_0.5.21_amd64.deb) · [Release notes](https://github.com/Pavithran-R-A/clipgauge/releases/tag/v0.5.21) · [Report an issue](https://github.com/Pavithran-R-A/clipgauge/issues)

## Release status

v0.5.21 is the current qualified release and the recommended version for normal use.

| Item | v0.5.21 |
| --- | --- |
| Windows | x64 NSIS installer |
| Linux | amd64 Debian package |
| macOS | ARM64 and x86_64 build qualification in CI; no signed/notarized public package |
| Production model E2E | Passed |
| CycloneDX SBOM | Published |
| SHA-256 manifest | Published |
| Artifact attestation | Windows binary, Linux package, and SBOM |
| Release provenance | Published |
| Public YouTube import | Best effort; local-file import is the reliable fallback |

The Windows and Linux release artifacts are currently unsigned. See the release page for checksums, SBOM, provenance, attestation status, and the model-E2E summary.

## What ClipGauge does

A ClipGauge job moves through a deterministic media pipeline:

1. **Ingest** a local video or a supported public link.
2. **Prepare media** and normalize the source for downstream processing.
3. **Transcribe speech** and align spoken content.
4. **Identify speakers** and derive audio-level signals.
5. **Build candidate story units** from transcript, timing, replay, and media evidence.
6. **Score candidates** with ClipGauge Local or a configured provider.
7. **Review recommendations** with score breakdowns and supporting signals.
8. **Reframe, caption, edit, and render** vertical clips.
9. **Export** the final MP4 and keep the session available for later review.

ClipGauge is designed for human-in-the-loop editing. A recommendation is a ranking signal, not an instruction to publish a clip unchanged.

## Core capabilities

- local video import and best-effort public YouTube import
- automatic speech transcription and timing alignment
- speaker-aware processing
- audio-event, vocal-arousal, replay, and story-structure signals
- candidate discovery and ranked short-form recommendations
- local scoring with ClipGauge Local
- optional OpenAI-compatible and provider-specific cloud scoring
- recommendation ledger with per-signal explanations
- vertical smart reframing
- multiple caption styles
- per-clip editing and rerendering
- session persistence and reopen support
- resumable, verified component downloads
- setup, storage, GPU, and provider diagnostics
- redacted support bundles
- release SBOM, checksums, provenance, and artifact attestations

## Local-first by default

ClipGauge Local runs scoring on the machine and does not require an AI-provider account.

The application separates local execution from external providers deliberately:

- **Local mode** keeps scoring on the computer.
- **Hybrid mode** combines local discovery with a configured provider.
- **Best Quality mode** uses the configured provider for scoring where selected.
- Provider credentials are stored through the operating-system credential store.
- Browser cookies are not read by default.
- No mandatory account is required to use the local workflow.

When a cloud provider is selected, source-derived material may leave the machine. The Privacy screen describes the relevant boundary before the job runs.

## Installation

### Windows

Download the current x64 installer:

[**ClipGauge_0.5.21_Windows_x64_NSIS.exe**](https://github.com/Pavithran-R-A/clipgauge/releases/download/v0.5.21/ClipGauge_0.5.21_Windows_x64_NSIS.exe)

SHA-256:

```text
B6A486F75C5F8204CD72A396E04D41343A1E8D35CAAE8C43E2F59C6CC015FF64
```

### Linux

Download the current amd64 Debian package:

[**ClipGauge_0.5.21_amd64.deb**](https://github.com/Pavithran-R-A/clipgauge/releases/download/v0.5.21/ClipGauge_0.5.21_amd64.deb)

SHA-256:

```text
8F55474283CA5F9A2C1037AF18815025C3D60D08860FF8A2931C4CDB6AB4422C
```

For the complete checksum manifest and release metadata, use the [v0.5.21 release page](https://github.com/Pavithran-R-A/clipgauge/releases/tag/v0.5.21).

## First run

1. Launch ClipGauge.
2. Open **Setup & Storage** and install the required core components.
3. Optionally configure GPU speech acceleration.
4. If you want local scoring, install one ClipGauge Local model.
5. If you want public YouTube import, install and test the optional YouTube support components.
6. Return to **Create**, add a local file or supported link, choose the scoring mode and caption style, then run the job.
7. Review the candidates, adjust the cut or style if required, and export.

Setup state is explicit. Verified files are reused; failed integrity checks are reported as repair states rather than silently accepted.

## YouTube support

YouTube integration is intentionally treated as **best effort**.

ClipGauge pins and verifies the local downloader/runtime/provider components it manages, and it can test the local provider lifecycle independently from a real public transfer. That distinction matters: a healthy local setup does not guarantee that every public YouTube URL will remain downloadable.

YouTube can change access behavior, bot checks, formats, or transfer requirements without notice. ClipGauge does not claim to bypass login, DRM, anti-bot, or account restrictions.

For reliable processing, use a local media file.

## AI providers

ClipGauge supports multiple scoring paths without coupling the media pipeline to a single vendor.

| Provider path | Typical use |
| --- | --- |
| ClipGauge Local | Local scoring with no provider account |
| Ollama / LM Studio | Existing local OpenAI-compatible model servers |
| OpenRouter | Routed cloud models, including available free routes |
| Gemini / Groq / Cloudflare / Hugging Face / Cerebras | Bring-your-own-key cloud scoring |
| Custom OpenAI-compatible | Self-hosted or third-party compatible endpoints |

Provider availability, model capability, pricing, and free-tier limits are external to ClipGauge and can change independently.

Pexels and Instagram are integrations, not scoring providers.

## Architecture

```text
app/
  React + TypeScript UI
  Tauri desktop shell
  native lifecycle, installer and platform integration

pipeline/
  Python media pipeline
  ingest, ASR, diarization, audio analysis
  candidate synthesis, scoring, rendering and diagnostics

docs/
  architecture, provider notes, QA evidence and product documentation

.github/
  CI, platform qualification, security checks and release automation
```

At runtime, the desktop application owns process lifecycle and local setup state while the Python pipeline performs media analysis and rendering. Managed runtimes and models are installed outside the source tree and verified before use.

## Release engineering

ClipGauge releases are built from immutable version tags.

The v0.5.21 release pipeline includes:

- version/tag consistency checks
- Windows qualification
- Linux qualification
- macOS ARM64 qualification
- macOS x86_64 qualification
- production-default managed-model E2E
- checksum generation
- CycloneDX SBOM generation
- release provenance
- GitHub artifact attestations for stable release subjects
- publication only after mandatory release gates pass

The published release includes `SHA256SUMS`, `SBOM.cyclonedx.json`, `MODEL_E2E_SUMMARY.json`, `RELEASE_PROVENANCE.md`, and `ATTESTATION_STATUS.md`.

## Development

The frontend is React/TypeScript, the desktop shell is Tauri/Rust, and the media pipeline is Python.

Read [INSTALL.md](INSTALL.md) for platform prerequisites.

### Frontend

```bash
cd app
npm ci
npm test -- --run
npm run build
```

### Pipeline

```bash
cd pipeline
uv run pytest -q
```

### Tauri / Rust

```bash
cd app/src-tauri
cargo fmt -- --check
cargo test
cargo clippy -- -D warnings
```

Do not commit generated installers, local model files, downloaded runtime assets, credentials, user sessions, or rendered media.

## Repository layout

| Path | Purpose |
| --- | --- |
| `app/` | React UI and Tauri desktop application |
| `pipeline/` | Python analysis, scoring, setup, and render pipeline |
| `docs/` | Architecture, providers, QA records, and product documentation |
| `scripts/` | Release and qualification utilities |
| `.github/` | CI, platform qualification, security, and release workflows |

## Security and privacy

ClipGauge is intended to make execution boundaries visible rather than implicit.

- Credentials are stored outside the repository through the OS credential store.
- Support bundles are redacted and exclude provider credentials.
- Managed downloads are versioned and integrity-checked.
- Local scoring does not require source-derived content to be sent to a cloud AI provider.
- Cloud/provider workflows disclose their external boundary in the application.
- Release artifacts include checksums and an SBOM.

Security-sensitive reports should follow [SECURITY.md](SECURITY.md) instead of being opened as public issues.

## Contributing

Start with [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/product-principles.md](docs/product-principles.md).

Changes that affect provider behavior, privacy boundaries, setup downloads, process lifecycle, release integrity, or browser-assisted workflows should include focused regression coverage and a clear description of the user-visible change.

Main may contain work intended for a future release. The latest tagged release is the supported reference point for packaged behavior.

## License and attribution

ClipGauge is distributed under the **GNU Affero General Public License v3.0 or later**.

The project began as a fork of [Blueturboguy07/publikclip](https://github.com/Blueturboguy07/publikclip). Upstream history and retained attribution are documented in [ORIGIN.md](ORIGIN.md).

Third-party licensing is documented in [NOTICE.md](NOTICE.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and [VENDORED-LICENSES.md](VENDORED-LICENSES.md).
