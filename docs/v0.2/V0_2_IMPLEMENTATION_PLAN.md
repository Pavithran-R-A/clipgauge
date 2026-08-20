# ClipGauge v0.2.0 Implementation Plan

## Goal

Deliver ClipGauge v0.2.0 as a local-first, AGPL-3.0-or-later desktop AI video clipper with a secure, capability-aware, extensible provider architecture. Users must be able to use local inference, curated cloud providers, free-tier/BYO-key options, or an arbitrary compatible OpenAI-style endpoint without ClipGauge source changes for every new provider.

The release must preserve the v0.1.0 and v0.1.1 tags and releases, upstream attribution, existing security foundations, no mandatory account or subscription, no ClipGauge cloud backend, no default telemetry, and honest provider/privacy limitations.

## Baseline and source control

The implementation starts from `bd36ea2d6f957c66f4e162e947fa3beb54720967`, the clean `origin/main` tip after v0.1.1 release closure. The immutable historical tags are `v0.1.0` at `8f1bb7751bd3bef455bd9e005d708c46c8d3a1ea` and `v0.1.1` at `c24b5ee59dd6ef9a55b36cbf3310aa0b8062a694`. Work is performed on `feature/v0.2-universal-providers`, preserving `origin=https://github.com/Pavithran-R-A/clipgauge.git` and `upstream=https://github.com/Blueturboguy07/publikclip.git`.

## Phase 1 — Current provider research gate

Research current first-party documentation for Gemini Developer API, OpenRouter, Groq, Cloudflare Workers AI, Hugging Face Inference Providers, Ollama, and LM Studio. Investigate at least one additional credible provider only if official documentation supports a meaningful developer/free path. Record research date, official URLs, endpoint family, authentication, model discovery, structured-output and vision capabilities, current free-tier status, rate/usage caveats, payment requirements where documented, privacy/terms notes, and uncertainty. Never encode mutable pricing or quota promises as permanent product facts.

Deliverable: `docs/providers/PROVIDER_RESEARCH_2026.md`.

## Phase 2 — Provider domain and normalized contracts

Introduce versioned `ProviderProfile`, capability metadata, normalized `InferenceRequest`, normalized `InferenceResult`, normalized provider error taxonomy, and explicit structured-output levels. Separate secrets from normal configuration. Persist immutable job provider snapshots containing profile identity, provider kind, model, endpoint identity, and capability snapshot, never raw credentials. Preserve and migrate v0.1.x `llm_mode=gemini` and `llm_mode=ollama` settings and jobs safely.

Cache identity must include provider profile identity, provider kind, model, prompt, schema, image content, and relevant capability/mode settings without secret material. Provider adapters must be the only layer translating provider-specific requests and responses.

## Phase 3 — Secure provider core

Extend the existing Rust-owned credential-vault architecture for every cloud and custom secret. Add redaction for new secret types and ensure secrets never appear in config, job snapshots, diagnostics, support bundles, URLs, command-line arguments, logs, Git, or CI output. Validate custom endpoint URLs, reject dangerous schemes, allow loopback HTTP with explicit policy, warn or require confirmation for remote plain HTTP, keep TLS verification enabled, prevent credential-leaking redirects, and disallow arbitrary scripts, shell hooks, executable templates, or raw request scripting.

Implement bounded exponential retry behavior with trustworthy `Retry-After` handling and normalized errors including authentication, availability, model, rate, quota, billing, timeout, network, structured output, context, vision, and provider-response failures. Do not retry invalid credentials, hard quota depletion, billing-required errors, or unsupported models.

## Phase 4 — Provider adapters

Use one reusable adapter architecture for:

- Gemini, preserving current reliability while adding model selection, structured output, vision, and actionable auth/quota/rate/model errors.
- OpenRouter, including `openrouter/free`, model selection/listing where practical, capability filtering, structured-output and vision negotiation.
- Groq through its current compatible API with model discovery and model-dependent capability detection.
- Cloudflare Workers AI with account identifier, token, model, current compatible inference path, and account/token/model failure handling.
- Hugging Face chat-style Inference Providers with token, model, routing suffixes where applicable, and honest task limitations.
- Ollama with loopback health checks, installed-model discovery, model-dependent vision and structured output, malformed response handling, context limits, and no automatic large model download.
- LM Studio through its local compatible API, model listing, model-dependent vision/structured output, and clear server-not-running state.
- Generic OpenAI-compatible custom providers with no-auth, bearer, API-key header, and custom-secret-header modes; manual model entry; optional listing; safe non-secret headers; timeout; and capability overrides.

All adapters must preserve graceful degradation and record missing visual signals rather than silently discarding images. Selected vision-capable models must receive resized/compressed frames with enforced limits and stripped unnecessary metadata.

## Phase 5 — Desktop UX and privacy

Replace the two-mode Gemini/Ollama UI with provider grouping for local, cloud/BYO-key, and custom endpoints. Show provider, model, connection state, text/vision/structured capability, locality, configuration, and a meaningful `Test Connection` action returning PASS, WARNING, or FAIL with actionable reasons. Do not force Gemini or any cloud provider on first run; offer local, cloud free-tier/BYO-key, and custom endpoint paths.

Make Privacy Activity provider-aware. Disclose what remains local and what may leave the device, including source URLs, transcript/prompt excerpts, selected frames for vision-enabled cloud inference, provider endpoints, Pexels/Instagram/network calls, and runtime/model downloads. Never claim 100% offline for URL workflows. Update support bundles to include only privacy-safe provider metadata and normalized errors.

## Phase 6 — Tests and deterministic contracts

Build deterministic mock HTTP providers covering valid compatible APIs, auth failures, 401/403/404, rate limits and `Retry-After`, quota, 500, timeout, invalid JSON, schema mismatch, context-too-large, same-host and cross-host redirects, vision-capable and text-only behavior, model listing, and unavailable listing. Test every adapter and prove endpoint/auth construction, no secret in URLs, structured translation, image translation, and redaction. Add migration, cache isolation, URL security, redirect, credential, support-bundle, and provider-status tests. Do not use paid live inference in normal CI.

Add an optional manual `provider-live-smoke.yml` workflow for tiny synthetic requests only. It must skip providers without configured secrets, never print secrets, never upload source media, and label each provider PASS, SKIPPED, or FAIL accurately.

## Phase 7 — Whole-product QA and security re-audit

Create `docs/v0.2/V0_2_FULL_QA_MATRIX.md` and legally redistributable synthetic fixtures for landscape speech/video, Unicode paths, corrupt media, and unusual/no-audio input. Exercise ingest, URL validation, yt-dlp failures, ASR, diarization, events, candidates, scoring, camera, captions, render, review, edit, rerender, export, cancellation, resume, and stale recovery. Exercise broken inputs, provider failures, quota, model availability, malformed structured data, and missing vision.

Repeat traversal, symlink, export, CSP, asset protocol, secret redaction, archive extraction, runtime checksum, and edit-schema tests. Run actual Python lock/dependency checks, npm audit, maintained Rust advisory audit, and secret scanning over current tree, history, generated bundle, and release metadata. Do not suppress high/critical vulnerabilities without written justification.

## Phase 8 — Rebrand, documentation, and final review

Classify every surviving old-brand occurrence in `docs/v0.2/REBRAND_CLASSIFICATION.md` as legal/provenance, legacy migration, historical audit, or accidental product branding. Remove accidental visible upstream branding from UI, installers, executable/package names, data paths, environment variables, icons, titles, and CLI while preserving required provenance and migration compatibility.

Update README, `docs/providers/README.md`, provider pages, CHANGELOG, privacy documentation, support-bundle documentation, and troubleshooting. Create `docs/v0.2/FINAL_REVIEW.md` with maintainer, no-cost user, privacy-sensitive user, and hostile-tester reviews.

## Phase 9 — Version and native release readiness

Bump all authoritative user-facing and package versions to `0.2.0`, extend the version-consistency checker, and preserve historical v0.1.x reports. Preserve Linux, Windows x64, macOS arm64, and macOS x86_64 qualification gates. Add meaningful packaged Windows customer smoke coverage for installation, launch, Studio, provider UI, Settings, Test Connection, branding, and clean exit. Update release metadata and workflow logic to build from the exact immutable v0.2.0 tag.

## Phase 10 — Audit, PR, and merge

Create `CLIPGAUGE_V0_2_RELEASE_AUDIT.md` with source SHAs, provider architecture, every built-in preset, custom provider security, local inference, migration, security findings, rebrand classification, QA, exact test counts, platform evidence, limitations, and PASS/CONDITIONAL PASS/FAIL verdict. Open PR title `feat: ClipGauge v0.2 universal AI providers`. Repair only actual root causes, never bypass red CI, and merge only after required checks are green.

## Phase 11 — Tag and release

After a PASS or justified non-security CONDITIONAL PASS, merge to `main`, verify main CI, create annotated immutable tag `v0.2.0`, and run the gated release pipeline. Do not modify v0.1.0 or v0.1.1. Publish as `ClipGauge v0.2.0 — Universal AI Providers` only when all mandatory release gates, metadata validation, checksum generation, and publication checks pass.

## Phase 12 — Post-release verification and final bundle

Download release assets and verify checksums, SBOM, provenance, tag commit, Linux package, Windows installer, release metadata, README, provider documentation, source identity, public secret searches, asset names, and version consistency. Create `CLIPGAUGE_V0_2_FINAL_BUNDLE.zip` containing the exact source snapshot, audit, research, architecture docs, test matrix, QA matrix, rebrand classification, security review, CI/release evidence, SBOM, checksums, provenance, commit list, final diff from v0.1.1, and secret-scan evidence. Exclude credentials, keychain data, virtual environments, dependency caches, model weights, user media, and private diagnostics. Test ZIP integrity and generate its SHA-256.

## Release blockers

Do not release if secrets are plaintext or leak into URLs/logs, custom endpoints allow dangerous schemes, redirects leak credentials, cache mixes providers/models, Gemini/Ollama regress, migration destroys settings/jobs/cache, high/critical vulnerabilities lack justification, Python/frontend/Rust/mandatory platform/secret/package gates fail, accidental visible upstream branding remains, README overclaims support, or UI makes unsupported free/unlimited promises.

Unsigned artifacts, absent notarization or Authenticode, changing free-tier quotas, model-dependent vision/schema gaps, skipped optional live-provider secrets, small Hugging Face credits, and slow local inference are non-blockers only when clearly documented.

## Final acceptance

The final response must report exact source and tag SHAs, PR, every provider’s implemented capabilities and live-test status, local/free access, security posture, rebrand classification, exact test counts, platform gates, release assets/checksums/SBOM/attestation, known limitations, final bundle hash/integrity, and explicit answers to whether ClipGauge is usable without paid AI APIs, which local/cloud options work, whether unknown compatible providers are configurable, where vision is verified, which live tests were skipped, whether accidental branding remains, whether all gates are green, and whether v0.2.0 is ready for external creator testing.
