# Contributing to ClipGauge

Thank you for helping make ClipGauge easier for creators to use and easier for contributors to understand. Start by reading [`docs/product-principles.md`](docs/product-principles.md); those principles guide product, interface, and documentation changes.

## Before you begin

Search existing issues and pull requests before starting a large change. For a new feature, open an issue first when the behavior, privacy impact, or provider contract is not obvious. Small fixes, documentation improvements, and test additions can usually be proposed directly.

## Local setup

Install Git, Node.js 22 or newer, Rust through [rustup](https://rustup.rs/), Python 3.12, and [uv](https://docs.astral.sh/uv/). Platform-specific Tauri dependencies are listed in [`INSTALL.md`](INSTALL.md).

```bash
git clone https://github.com/Pavithran-R-A/clipgauge.git
cd clipgauge

cd app
npm ci
npm run tauri dev
```

The first run may offer local component setup. Do not commit downloaded models, rendered clips, job folders, credentials, or generated installers.

## Checks to run

Run the checks that match your change. A pull request that changes the app should run the frontend tests and build; a pipeline change should run the Python suite; Rust bridge changes should run the Rust checks.

```bash
python3 scripts/check-version-consistency.py

cd app
npm test -- --run
npm run build

cd ../pipeline
uv run pytest -q

cd ../app/src-tauri
cargo fmt -- --check
cargo test
cargo clippy --all-targets --all-features -- -D warnings
```

Tests that require a downloaded model, a real provider credential, Instagram access, a platform signing identity, or a specific operating-system runner should say so clearly. Never report a hardware-dependent or model-backed check as passing when it was not run.

## Pull requests

Keep each pull request focused on one user-visible change. Describe the problem, the behavior you changed, the privacy or data-flow effect, and the checks you ran. Include screenshots only from the current build when a visual change is central to the review. Use the checklist in [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md).

A good pull request uses creator language in the visible interface, keeps advanced technical detail behind an explicit disclosure, and preserves a clear path back to **Create**. Avoid release-process jargon in UI copy and do not remove a provider, setup path, or diagnostic without explaining the replacement.

## Provider changes

Provider changes must preserve explicit provider choice, accurate local-versus-cloud disclosure, and a useful failure state. Keep Pexels and Instagram in **Integrations**, not in **AI Providers**. Add or update tests for provider listing, credential handling, connection testing, model capability reporting, and privacy text where applicable. Do not hard-code credentials, copy provider secrets into logs, or claim that a free route is permanent.

For new endpoints, document the authentication mode, endpoint behavior, model selection, structured-output behavior, vision behavior, and retention questions in the provider documentation. Remote requests must use HTTPS; loopback HTTP is reserved for local services.

## Security-sensitive changes

Treat credential storage, browser-cookie handling, filesystem boundaries, download verification, subprocess invocation, support bundles, and network redirects as security-sensitive. Explain the threat model and include a regression test or a precise reason a test cannot be automated. Browser cookies must remain opt-in, and support bundles must not include raw source media, transcripts, or credentials.

Report a suspected vulnerability using the private process in [`SECURITY.md`](SECURITY.md). Do not put secrets or sensitive media in issues, pull requests, screenshots, or test fixtures.

## Documentation and licensing

Keep the AGPL notice, [`ORIGIN.md`](ORIGIN.md), and third-party notices accurate. The project is derived from [`Blueturboguy07/publikclip`](https://github.com/Blueturboguy07/publikclip), and `bgutil` remains GPL-3.0-only. If your change adds a dependency, update the relevant lockfile and licensing record.

## Code style

Prefer small, readable components and explicit state transitions. Use visible focus states, semantic controls, keyboard-reachable navigation, and reduced-motion behavior. Keep creator-facing copy concise and explain what will happen before an action sends data, downloads components, or changes a saved session.
