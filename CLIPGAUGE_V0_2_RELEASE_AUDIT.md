# ClipGauge v0.2.0 — Pre-Release Human-Readable Audit

**Audit date:** 2026-08-20 (user timezone, GMT+5:30)  
**Product:** ClipGauge v0.2.0 — Universal AI Providers  
**Audit status:** Conditional pass pending mandatory GitHub CI, merge, tag, packaging, and publication verification.  
**Policy:** This audit records only evidence available in the repository or from commands executed in this workspace. It does not claim live provider success, platform signing, notarization, benchmarks, or unobserved CI results.

## Source

| Field | Evidence |
|---|---|
| Starting main SHA | `bd36ea2` — merged v0.1.1 closure state |
| Current audited ending SHA | `c487b97` — feature branch, including workflow version-awareness fixes |
| Branch | `feature/v0.2-universal-providers` |
| Pull request | [PR #5](https://github.com/Pavithran-R-A/clipgauge/pull/5) |
| Origin remote | `https://github.com/Pavithran-R-A/clipgauge.git` |
| Upstream remote | `https://github.com/Blueturboguy07/publikclip.git`, preserved |
| Prior tags | `v0.1.0` and `v0.1.1` are not modified by this work |

The feature branch preserves real commit history and does not squash the prior provider architecture, core, adapter, desktop integration, and release-preparation commits. No API keys, tokens, keychain contents, user media, model weights, or diagnostic material containing private content are included in the audited source changes.

## Provider architecture

ClipGauge now uses a normalized provider domain rather than a Gemini/Ollama-only execution assumption. `ProviderProfile` is a versioned non-secret snapshot containing provider kind, endpoint, selected model, locality, capability declarations, authentication strategy, and non-secret metadata. `InferenceRequest` carries the prompt, optional schema, images, purpose, and capability requirements. `InferenceResult` returns normalized text or structured data, selected model, usage metadata where supplied, capabilities used, degradation signals, and provider-neutral error information.

The capability system distinguishes text, model listing, structured JSON, native JSON Schema, and vision. Structured output has explicit native-schema, JSON-mode/local-validation, and text-compatibility levels. Unknown capabilities are not silently converted into guarantees. Vision requests either use a supported image translation path or return an explicit unsupported/degraded result; automatic cross-provider failover is not enabled.

Provider adapters translate provider-specific request and response formats into the normalized contract. Gemini retains its native API path. Ollama retains its local API path and image handling. LM Studio, OpenRouter, Groq, Cloudflare Workers AI, Hugging Face, Cerebras, and custom OpenAI-compatible services use the compatible adapter with profile-specific endpoint, authentication, capability, model, and error behavior.

Secrets are kept outside provider snapshots. The Rust-owned credential vault has a provider-auth slot and injects credentials only at the narrowly scoped operation boundary. Diagnostics redact provider key names, token prefixes, exact secret values, and custom secret-header values. Secrets are not placed in URLs, query strings, ordinary configuration, shell arguments, cache keys, support bundles, or Git history.

Provider cache identity includes provider identity, endpoint, model, request purpose, schema identity, and relevant capability context. Secret values are excluded. This prevents results from one provider or model being reused for another provider or model.

## Built-in providers

The following table records implementation posture. “Mock contract” refers to deterministic local tests; it does not mean a remote provider was contacted.

| Provider | Preset/auth | Model discovery | Text and structured output | Vision | Mock/live status | Current access caveat |
|---|---|---|---|---|---|---|
| Gemini | Implemented; API-key header, vault-backed | `/models` best effort | Native schema path with local normalization | Model-dependent curated image path | Deterministic contract covered; **live SKIPPED** because no owner credential was supplied | Official free and paid tiers may be available; quotas and pricing can change |
| OpenRouter | Implemented; bearer token | `/models` best effort | Native schema, JSON, or text compatibility according to profile | `openrouter/free` and selected model are capability-dependent | Deterministic contract covered; **live SKIPPED** | Official free-model routing is dynamic; availability and routing can change |
| Groq | Implemented; bearer token | `/models` | Selected-model native/JSON support with local validation fallback | Selected-model dependent | Deterministic contract covered; **live SKIPPED** | Account and model rate limits are mutable; no permanent-free promise |
| Cloudflare Workers AI | Implemented; bearer token plus explicit account-scoped endpoint | Best effort | JSON-mode/schema-aware compatible path with local validation | Model-dependent | Deterministic contract covered; **live SKIPPED** | Account, token, model, and quota configuration are required; any free quota is mutable |
| Hugging Face | Implemented; bearer token | Best effort | Underlying provider/model-dependent structured output | Underlying provider/model-dependent | Deterministic contract covered; **live SKIPPED** | Provider routing, token access, limits, and model capabilities vary |
| Cerebras | Implemented; bearer token | `/models` best effort | Conservative native/JSON fallback | Default curated capability record is text-only; model-level checking remains required | Deterministic contract covered; **live SKIPPED** | Official material describes a trial/paid model, not a permanent free tier |
| Ollama | Implemented; no key for default loopback | Local installed-model listing and health | Native structured-output path where supported | Model-dependent; images are translated rather than discarded | Deterministic contract covered; local live run not claimed | Local and no mandatory cloud subscription; server, model, hardware, and download state are user-controlled |
| LM Studio | Implemented; no key by default for loopback | `/v1/models` | Compatible JSON levels, with model-dependent schema support | Server/model-dependent | Deterministic contract covered; local live run not claimed | Local and no mandatory cloud subscription; server must be started by the user |

The optional manual workflow covers the five original curated cloud paths plus Cerebras and reports `SKIPPED` when the required owner secret, or Cloudflare endpoint, is absent. No provider is described as permanently free or unlimited. Cloud providers transmit selected prompts, transcript excerpts, metadata, and possibly frames outside the device when explicitly selected; the privacy activity view exposes the selected destination and media behavior.

## Custom provider

Custom OpenAI-compatible configuration accepts a user-selected base URL, model, authentication strategy, optional custom secret-header name, and capability overrides or detected capabilities. The URL policy rejects dangerous schemes, credentials in URLs, query-string secrets, and unsafe remote plain HTTP. Loopback HTTP is allowed for local servers; remote HTTPS is the normal cloud requirement. Redirect handling does not forward authorization across an unsafe origin, and TLS verification remains enabled.

The custom path supports no-auth, bearer, API-key-header, and custom-secret-header modes. The model may be entered manually; model listing is best effort and is not required when the user supplies a model. Native schema, JSON-mode/local-validation, and explicit text compatibility are represented as different capability levels. Deterministic tests cover URL policy, custom authentication metadata, secret placement, redirect safety, model listing failure with manual entry, cache isolation, vision degradation, and normalized provider errors.

## Local inference

Ollama remains a first-class local path at the loopback API, with installed-model discovery and explicit stopped-service or missing-model states. LM Studio is a first-class local OpenAI-compatible path at the documented loopback default and exposes model discovery through `/v1/models`. Other local OpenAI-compatible servers can use the custom provider configuration. ClipGauge does not download models automatically and does not silently send local jobs to a cloud provider.

## Migration

The configuration model is versioned and migrates legacy v0.1.x Gemini and Ollama settings idempotently into provider snapshots. Existing job state and cache records are not destructively rewritten. Legacy `--llm` behavior remains available through the compatibility facade, while new provider selection uses explicit `--provider`, `--model`, `--endpoint`, `--auth`, and credential-bound operation arguments. Migration behavior is covered by deterministic tests, including repeatability and preservation of existing settings.

## Security

| Area | Finding |
|---|---|
| Remaining high severity | None identified in the audited changes |
| Remaining medium severity | Provider capabilities and cloud quota/retention policies can change; model-dependent vision and schema behavior must remain visible |
| Remaining low severity | Local model execution can be slow or unavailable; live smoke is optional and owner-secret dependent; unsigned platform artifacts may trigger operating-system warnings |
| Secret storage | Rust-owned OS credential vault; provider snapshots remain non-secret |
| Secret redaction | Provider key names, token prefixes, exact values, and custom headers are redacted in diagnostics/support boundaries |
| URL and transport | Dangerous schemes, URL credentials, query-string secrets, and unsafe remote HTTP are rejected; TLS verification remains enabled |
| Redirects | Authorization is not forwarded across unsafe redirect origins |
| Cache | Provider, endpoint, model, purpose, schema, and capability identity are separated; secret values are excluded |
| Failover | No automatic cross-provider failover; explicit user selection is required |

The security review at `docs/v0.2/SECURITY_REVIEW.md` records the detailed controls and residual non-blocking limitations. No API-key-in-URL, plaintext provider-key storage, shell-injection path, unsafe redirect forwarding, cache mixing, or credential leakage blocker was found in deterministic review.

## Rebrand

The rebrand classification at `docs/v0.2/REBRAND_CLASSIFICATION.md` records all remaining upstream identity occurrences. Legitimate legal/provenance, migration, and historical audit references remain where required. The accidental CAM++ branding occurrence was corrected. No accidental upstream branding remains in normal ClipGauge UI or executable identity according to the repository audit.

## QA

The deterministic QA gate covers the Python pipeline, provider failures, image translation and vision degradation, migration, local-provider readiness, Rust path and secret security, frontend provider configuration, and existing cancel/resume and rendering behavior. Test fixtures are synthetic or repository-owned; no user video or owner credential is required. Full QA planning and evidence expectations are recorded in `docs/v0.2/V0_2_FULL_QA_MATRIX.md`.

## Tests

| Gate | Result |
|---|---:|
| Python test suite | **129 passed**, 1 existing unknown-mark warning |
| Frontend Vitest suite | **12 passed** across 3 files |
| TypeScript build | **Passed** |
| Rust unit tests | **28 passed** |
| Rust formatting | **Passed** |
| Version consistency | **Passed**, all authoritative current-release sources report 0.2.0 |
| Provider contract tests | Included in the Python count; 13 deterministic provider-contract tests are documented, with the committed suite containing the expanded coverage |
| Live provider smoke | **SKIPPED / not claimed** in this audit; manual-only workflow is configured and no owner secrets were supplied |

## Platforms

Linux, Windows, macOS ARM, and macOS Intel qualification workflows are configured in the repository. At this pre-release audit point, their remote GitHub results are pending PR execution and are not fabricated. The release workflow now derives tag validation and release notes from the requested release tag, and the macOS bundle assertion derives its expected version from `app/package.json`.

Linux release artifacts are intended to be unsigned Debian packages. The Windows NSIS installer is unsigned and SmartScreen warnings are expected. macOS builds are qualification results only; no signing or notarization is claimed.

## Known limitations

Cloud provider quotas, pricing, model catalogs, routing, retention policies, and vision/schema support are mutable and must be checked at use time. Some providers and models support only best-effort JSON or text compatibility. Vision is model- and endpoint-dependent, and the Cerebras curated default is recorded as text-only. Local inference requires the user to install and run the local server and obtain models; performance depends on hardware. The optional live smoke workflow cannot report a live pass without owner-supplied secrets and does not count skipped providers as passing. There is no automatic cross-provider failover. Platform packages are unsigned, macOS is not notarized, and no Windows Authenticode claim is made.

## Verdict

**CONDITIONAL PASS — non-security, pre-release.** All local deterministic gates pass, the provider architecture and security controls are implemented, the version and documentation batch is committed, and PR #5 is open. Release remains blocked until mandatory PR CI is green, the pull request is merged without bypassing red checks, the exact `v0.2.0` tag is created from merged main, the release workflow completes, published artifacts are downloaded and verified, and the post-release bundle is generated. No live provider success is claimed in the interim.
