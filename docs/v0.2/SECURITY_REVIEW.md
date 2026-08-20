# ClipGauge v0.2.0 security re-audit

## Provider URL boundary

Provider endpoints are normalized before use. `https` is required for remote endpoints; loopback HTTP is permitted for local services. Dangerous URI schemes such as `file:`, `data:`, and `javascript:` are rejected. Remote plain HTTP is rejected by default. TLS verification remains enabled and the normal UI exposes no TLS-disable control.

## Redirect and request handling

Authenticated provider requests use `follow_redirects=False`. API keys and bearer tokens are placed in headers, never query parameters or model URLs. Custom request scripting, shell hooks, executable provider plugins, and arbitrary request templates are not supported.

## Secret storage and process scope

Rust owns provider credentials through the operating-system credential vault. Normal settings and job snapshots contain profile IDs, endpoint identity, model, capability metadata, auth strategy, locality, and non-secret custom header names only. Selected credentials are injected into the short-lived child process environment for the active operation. No provider credential is passed as a command-line argument.

## Diagnostics and support bundles

Known provider key names and common token prefixes are redacted. A `redact_with_secrets` helper supports exact custom-secret value removal before persistence. Support bundles include sanitized metadata and redacted diagnostic tails; they exclude keys, tokens, authorization values, transcripts, source media, and transmitted image bytes.

## Cache correctness

Cache identity includes provider profile ID, provider kind, model, normalized endpoint identity, capability mode, prompt, JSON schema, image bytes, and relevant request settings. Secret material is excluded. Cache hits reconstruct degraded vision provenance so repeated runs do not hide text-only limitations.

## Migration and path controls

Legacy Gemini/Ollama settings are converted idempotently into provider snapshots. Legacy job settings remain resumable and no raw secret is copied into the snapshot. Existing path traversal, symlink, asset-scope, archive, edit-schema, runtime-integrity, cancellation, and lifecycle controls remain in place and are re-run in the v0.2 QA gate.

## Residual limitations

Provider-specific remote service behavior cannot be proven without the owner’s live credentials and is therefore covered by deterministic mocks plus optional manual smoke. Unsigned installers and lack of notarization are release limitations, not mitigations for provider security. No automatic cross-cloud failover is implemented, preventing an unexpected destination change when one provider fails.
