# ClipGauge

ClipGauge helps creators find the moments worth sharing, turn them into vertical clips, and understand why each clip scored well.

[Download the latest release](https://github.com/Pavithran-R-A/clipgauge/releases/latest) · [View the source](https://github.com/Pavithran-R-A/clipgauge) · [Report a problem](https://github.com/Pavithran-R-A/clipgauge/issues)

> **Current release: ClipGauge v0.5.1** — a creator-focused redesign with a calmer workflow, clearer provider choices, and stronger privacy explanations.

## See the workflow

The v0.5.1 screenshots below are captured from the packaged application and show the verified creator workflow: choose a workspace, keep previous sessions close at hand, and understand the setup and scoring choices before you run a video.

![ClipGauge Create screen](docs/screenshots/v0.5.1-packaged-create.png)

![ClipGauge Sessions screen](docs/screenshots/v0.5.1-packaged-sessions.png)

## What ClipGauge does

ClipGauge works from a video file or a supported link. It detects candidate moments, scores them against signals such as speech, laughter, pacing, and replay data when available, then renders vertical clips with captions and optional music direction. You can inspect the reasoning, edit a clip, and export an MP4 without leaving the app.

The main flow is designed for creators rather than model configuration. Start on **Create**, pick a local or cloud scoring option, choose a caption style, and let the processing timeline show what is happening. **Sessions** keeps previous jobs close at hand, while **Why this clip** explains the recommendation instead of leaving you with a bare number.

## Get started

1. Download the installer for your operating system from the [latest release](https://github.com/Pavithran-R-A/clipgauge/releases/latest).
2. Open ClipGauge and approve the one-time local component setup. The app tells you what will be installed, what is already available, and when a size still needs to be calculated.
3. Add a video from your computer or paste a supported link. Choose the scoring provider and caption style that fit this clip.
4. Review the suggested clips, adjust a cut or caption style if needed, and export the MP4 you want to publish.

If a setup step needs attention, open **Setup & Storage**. If a connection or render needs investigation, open **Help & Diagnostics** and create a support bundle. The bundle is designed for troubleshooting and does not include provider credentials.

## Choose how scoring runs

ClipGauge keeps all supported choices visible in **AI Providers**. You can use the built-in local route, a free-friendly cloud route, a curated cloud provider with your own key, or a local app already running on your computer.

| Option | Best for | What to know |
| --- | --- | --- |
| ClipGauge Local | Keeping source media on this computer | No provider account; requires the local setup components. |
| OpenRouter Free | Trying a cloud route with a free model path | Availability, limits, and the routed model can change. |
| Gemini, Groq, Cloudflare, Hugging Face, Cerebras | Using a provider you already use | Add your own key; model capabilities and provider terms vary. |
| Ollama or LM Studio | Using a local model you already run | Start the local server first, then test the connection. |
| Custom OpenAI-compatible | Connecting an endpoint you control | Enter the endpoint, model, and credential in Advanced settings. |

**Pexels** is separate from AI providers. It lives in **Integrations** as an optional source for stock visuals. Instagram feedback is also optional and separate from scoring.

## Privacy in plain language

Your video stays on this computer when you use a local provider. When you choose a cloud provider, ClipGauge explains what can be sent before you run the job; this can include transcript excerpts, prompts, and sampled frames when the selected model supports vision. Provider keys are stored in the operating-system vault rather than project files.

ClipGauge does not read browser cookies by default. Any browser-cookie behavior must be explicitly enabled for a supported workflow. Read the in-app **Privacy** panel and [`docs/providers/README.md`](docs/providers/README.md) before sending source-derived material to a third party.

## Build from source

ClipGauge is a Tauri desktop app with a React and TypeScript interface and a Python processing pipeline. You will need Node.js, Rust, Python, `uv`, and the platform dependencies described in [`INSTALL.md`](INSTALL.md).

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

The release files are built by the repository workflows. Do not commit generated installers, local credentials, job outputs, or model downloads.

## Contributing

Start with [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`docs/product-principles.md`](docs/product-principles.md). Changes to provider behavior, privacy disclosures, browser-cookie handling, setup downloads, or licensing need extra care; explain the user-visible effect and include tests where the behavior can be checked locally.

## License and attribution

ClipGauge is distributed under the **GNU Affero General Public License v3.0 or later**. It began as a fork of [`Blueturboguy07/publikclip`](https://github.com/Blueturboguy07/publikclip); the upstream relationship and retained notices are documented in [`ORIGIN.md`](ORIGIN.md). Third-party licenses and notices remain in [`NOTICE.md`](NOTICE.md), [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md), and [`VENDORED-LICENSES.md`](VENDORED-LICENSES.md). The `bgutil` component is documented as **GPL-3.0-only** in the third-party notices.

For security-sensitive reports, use [`SECURITY.md`](SECURITY.md) rather than a public issue.

## References

[1]: https://github.com/Pavithran-R-A/clipgauge/releases/latest "ClipGauge latest releases"
[2]: https://github.com/Pavithran-R-A/clipgauge/blob/main/LICENSE "ClipGauge license"
[3]: https://github.com/Blueturboguy07/publikclip "publikclip upstream repository"
