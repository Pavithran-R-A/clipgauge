# ClipGauge

ClipGauge is a desktop app for finding strong moments in longer videos and turning them into vertical clips. It combines transcript/audio signals with optional AI scoring, then keeps the recommendation understandable so a creator can see *why* a moment was selected before exporting it.

[Download the latest release](https://github.com/Pavithran-R-A/clipgauge/releases/latest) · [Report an issue](https://github.com/Pavithran-R-A/clipgauge/issues)

## What it does

A typical ClipGauge workflow looks like this:

1. Add a local video or supported link.
2. Choose a local or cloud scoring provider.
3. Let the pipeline find and score candidate moments.
4. Review the suggested clips and the signals behind each score.
5. Adjust the cut/caption style if needed and export the result.

The app is designed around the creator workflow rather than model configuration. Provider setup, diagnostics and storage live in their own screens so they do not get in the way of the main job.

![ClipGauge Create screen](docs/screenshots/v0.5.1-packaged-create.png)

![ClipGauge Sessions screen](docs/screenshots/v0.5.1-packaged-sessions.png)

## Main features

- candidate moment detection from video/audio/transcript signals
- vertical clip rendering with captions
- explanation of the signals that contributed to a recommendation
- session history for previous jobs
- local and cloud AI-provider options
- provider connection checks and diagnostics
- local component/setup management
- support bundles that exclude provider credentials

## AI providers

ClipGauge can run with its built-in local path, local model servers such as Ollama or LM Studio, OpenRouter's free route, or supported bring-your-own-key cloud providers. There is also a custom OpenAI-compatible option for endpoints you control.

Provider availability and free-tier limits can change, so the UI treats saved credentials and a verified connection as separate states.

## Privacy

When you use a local provider, source video stays on the machine. Cloud providers may receive source-derived data such as transcript excerpts, prompts or sampled frames depending on the selected model and feature.

Provider credentials are stored through the operating-system credential store rather than project files. Browser-cookie access is not enabled by default. See [`docs/providers/README.md`](docs/providers/README.md) and the in-app Privacy screen for the current provider-specific behaviour.

## Build from source

ClipGauge uses a React/TypeScript frontend, Tauri for the desktop shell, and a Python media-processing pipeline.

Prerequisites and platform-specific setup are documented in [`INSTALL.md`](INSTALL.md). The short development path is:

```bash
git clone https://github.com/Pavithran-R-A/clipgauge.git
cd clipgauge

cd app
npm ci
npm run dev
```

Run the main checks with:

```bash
cd app && npm test -- --run && npm run build
cd ../pipeline && uv run pytest -q
cd ../app/src-tauri && cargo fmt -- --check && cargo test
```

The repository workflows build release artifacts. Generated installers, local credentials, job output and downloaded models should not be committed.

## Project layout

```text
app/            React/TypeScript UI and Tauri application
pipeline/       Python media-processing pipeline
docs/           architecture, providers, product notes and screenshots
.github/        CI/release workflows
```

For contribution guidance, start with [`CONTRIBUTING.md`](CONTRIBUTING.md). Security-sensitive reports should follow [`SECURITY.md`](SECURITY.md).

## Origin and license

ClipGauge is licensed under the **GNU Affero General Public License v3.0 or later**.

The project began as a fork of [`Blueturboguy07/publikclip`](https://github.com/Blueturboguy07/publikclip). The upstream relationship and retained notices are documented in [`ORIGIN.md`](ORIGIN.md), [`NOTICE.md`](NOTICE.md), [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and [`VENDORED-LICENSES.md`](VENDORED-LICENSES.md).
