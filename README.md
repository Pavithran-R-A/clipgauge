# ClipGauge

ClipGauge is a desktop app for finding strong moments in longer videos and turning them into vertical clips. It combines transcript and audio signals with optional AI scoring, then keeps the recommendation understandable so a creator can see *why* a moment was selected before exporting it.

[Download the latest release](https://github.com/Pavithran-R-A/clipgauge/releases/latest) · [Report an issue](https://github.com/Pavithran-R-A/clipgauge/issues)

> **Current release: ClipGauge v0.5.3** — a responsive setup and creator-flow refinement with truthful local-model reuse, source-aware YouTube readiness, and explicit terminal error states.

## What it does

A typical ClipGauge workflow looks like this:

1. Add a local video or supported link.
2. Choose a local or cloud scoring provider.
3. Let the pipeline find and score candidate moments.
4. Review the suggested clips and the signals behind each score.
5. Adjust the cut or caption style if needed and export the result.

The app is designed around the creator workflow rather than model configuration. Provider setup, diagnostics, and storage live in their own screens so they do not get in the way of the main job.

The packaged screenshots below show the creator workflow. Setup & Storage separates core components from optional ClipGauge Local, reports whether model files are verified or need repair, and exposes a real YouTube Test action. AI Providers distinguishes a saved credential from a verified connection.

![ClipGauge Create screen](docs/screenshots/v0.5.1-packaged-create.png)

![ClipGauge Sessions screen](docs/screenshots/v0.5.1-packaged-sessions.png)

## Main features

- candidate moment detection from video, audio, and transcript signals
- vertical clip rendering with captions
- explanation of the signals that contributed to a recommendation
- session history for previous jobs
- local and cloud AI-provider options
- provider connection checks and diagnostics
- local component and setup management
- support bundles that exclude provider credentials

## Get started

1. Download the installer for your operating system from the [latest release](https://github.com/Pavithran-R-A/clipgauge/releases/latest).
2. Open ClipGauge and approve the one-time core-component setup. Setup & Storage tells you what will be installed, what is already available, and when an existing verified file will be reused.
3. If you want local scoring, choose a model in Optional local AI. A verified existing model shows as installed and contributes zero additional download bytes; a failed integrity check shows Needs repair instead of silently redownloading.
4. For YouTube, open Setup & Storage and run Test YouTube support. The app checks the pinned runtime, provider build, plugin discovery, loopback startup, and health before Create allows a public-link job.
5. Add a video from your computer or paste a supported link. Choose the scoring provider and caption style that fit this clip.
6. Review the suggested clips, adjust a cut or caption style if needed, and export the MP4 you want to publish.

If a setup step needs attention, open **Setup & Storage**. Core readiness, optional local-AI readiness, and YouTube readiness are shown independently. Use Install, Test, Repair, or Retry as offered by the current state. If a connection or render needs investigation, open **Help & Diagnostics** for a local health summary and create a redacted support bundle. The bundle is designed for troubleshooting and does not include provider credentials.

## AI providers

ClipGauge can run with its built-in local path, local model servers such as Ollama or LM Studio, OpenRouter's free route, or supported bring-your-own-key cloud providers. There is also a custom OpenAI-compatible option for endpoints you control. Provider availability and free-tier limits can change, so the UI treats saved credentials and a verified connection as separate states.

| Option | Best for | What to know |
| --- | --- | --- |
| ClipGauge Local | Keeping source media on this computer | No provider account; requires the local setup components. |
| OpenRouter Free | Trying a cloud route with a free model path | Availability, limits, and the routed model can change. |
| Gemini, Groq, Cloudflare, Hugging Face, Cerebras | Using a provider you already use | Add your own key; model capabilities and provider terms vary. |
| Ollama or LM Studio | Using a local model you already run | Start the local server first, then test the connection. |
| Custom OpenAI-compatible | Connecting an endpoint you control | Enter the endpoint, model, and credential in Advanced settings. |

**Pexels** is separate from AI providers. It lives in **Integrations** as an optional source for stock visuals. Instagram feedback is also optional and separate from scoring.

## Privacy in plain language

When you use a local provider, source video stays on the machine. When you choose a cloud provider, ClipGauge explains what can be sent before you run the job; this can include transcript excerpts, prompts, and sampled frames when the selected model supports vision.

Provider credentials are stored through the operating-system credential store rather than project files. ClipGauge does not read browser cookies by default. Any browser-cookie behavior must be explicitly enabled for a supported workflow. Read the in-app **Privacy** panel and [`docs/providers/README.md`](docs/providers/README.md) before sending source-derived material to a third party.

## Build from source

ClipGauge uses a React/TypeScript frontend, Tauri for the desktop shell, and a Python media-processing pipeline. You will need Node.js, Rust, Python, `uv`, and the platform dependencies described in [`INSTALL.md`](INSTALL.md).

```bash
git clone https://github.com/Pavithran-R-A/clipgauge.git
cd clipgauge

cd app
npm ci
npm run dev
```

Run the checks before opening a pull request:

```bash
cd app && npm test -- --run && npm run build
cd ../pipeline && uv run pytest -q
cd ../app/src-tauri && cargo fmt -- --check && cargo test
```

The repository workflows build the release files. Do not commit generated installers, local credentials, job output, or downloaded models.

## Project layout

```text
app/            React/TypeScript UI and Tauri application
pipeline/       Python media-processing pipeline
docs/           architecture, providers, product notes and screenshots
.github/        CI and release workflows
```

## Contributing

Start with [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`docs/product-principles.md`](docs/product-principles.md). Changes to provider behavior, privacy disclosures, browser-cookie handling, setup downloads, or licensing need extra care; explain the user-visible effect and include tests where the behavior can be checked locally.

For security-sensitive reports, use [`SECURITY.md`](SECURITY.md) rather than a public issue.

## License and attribution

ClipGauge is distributed under the **GNU Affero General Public License v3.0 or later**. It began as a fork of [`Blueturboguy07/publikclip`](https://github.com/Blueturboguy07/publikclip); the upstream relationship and retained notices are documented in [`ORIGIN.md`](ORIGIN.md). Third-party licenses and notices remain in [`NOTICE.md`](NOTICE.md), [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md), and [`VENDORED-LICENSES.md`](VENDORED-LICENSES.md). The `bgutil` component is documented as **GPL-3.0-only** in the third-party notices.

## References

[1]: https://github.com/Pavithran-R-A/clipgauge/releases/latest "ClipGauge latest releases"
[2]: https://github.com/Pavithran-R-A/clipgauge/blob/main/LICENSE "ClipGauge license"
[3]: https://github.com/Blueturboguy07/publikclip "publikclip upstream repository"
