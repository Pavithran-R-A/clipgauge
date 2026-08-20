# ClipGauge v0.2.0 final review

## Maintainer

The scoring stage consumes a normalized `InferenceRequest` and `InferenceResult`; adding another OpenAI-compatible service requires profile configuration rather than a scoring-code branch. Curated providers use the same adapter family, while Gemini and Ollama retain compatibility paths. Job snapshots are immutable with respect to provider identity and model.

## No-cost user

ClipGauge remains usable without a paid ClipGauge subscription, ClipGauge-owned backend, or mandatory cloud API. Ollama, LM Studio, and compatible local servers are the completely local paths when the user has suitable hardware. Curated cloud free access, quotas, and terms vary by provider and are described conservatively rather than promised permanently.

## Privacy-sensitive user

The selected provider is explicit. Privacy Activity identifies local data, network operations, provider endpoint identity, model, and whether frames may be transmitted. Cloud inference is never silently substituted when a provider fails. URL retrieval, Pexels, Instagram, runtime downloads, and provider calls remain separately disclosed.

## Hostile tester

Custom endpoint validation rejects dangerous schemes and remote plain HTTP by default. Authenticated redirects are disabled, credentials remain in the OS vault, query-string secrets are rejected by construction, child arguments do not contain keys, cache identity excludes secrets, and support bundles redact provider values. Invalid provider responses become bounded normalized errors rather than raw tracebacks.

## Acceptance verdict before release

The review is **conditionally ready for release engineering** only after the version bump, mandatory CI, native packaging matrix, rebrand search, dependency/security audits, release audit, and exact-tag publication gates pass. Optional live provider smoke is reported separately as `PASS`, `SKIPPED`, or `FAIL`; skipped live smoke is not counted as a pass.
