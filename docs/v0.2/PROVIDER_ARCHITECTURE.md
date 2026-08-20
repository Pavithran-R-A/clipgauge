# ClipGauge v0.2 Provider Architecture

## Design objective

ClipGauge v0.2 replaces the two-value `llm_mode` switch with a versioned provider domain that lets scoring depend on normalized capabilities and results rather than provider names. Provider-specific details remain inside adapters. Existing Gemini and Ollama behavior remains available through migrated profiles and regression tests.

## Versioned domain model

The persisted non-secret profile is represented conceptually as:

```json
{
  "schema_version": 1,
  "id": "profile-local-ollama",
  "kind": "ollama",
  "display_name": "Ollama",
  "base_url": "http://127.0.0.1:11434",
  "model": "llama3.1:8b",
  "auth_strategy": "none",
  "capabilities": {
    "text": true,
    "structured_json": true,
    "json_schema": "unknown",
    "vision": "unknown",
    "model_listing": true,
    "local": true,
    "cloud": false,
    "streaming": "unknown",
    "context_window": null,
    "max_images": null
  },
  "locality": "local",
  "enabled": true,
  "timeout_seconds": 120,
  "metadata": {}
}
```

Secrets are referenced by a stable secret slot but never embedded in this object. A cloud profile may contain `secret_ref="provider:<profile-id>:primary"` in an internal vault mapping, while normal config and job snapshots contain only profile identity and endpoint/model metadata.

### Capability semantics

Each capability is tri-state where detection is model- or endpoint-dependent: `true`, `false`, or `unknown`. A provider-family default is not sufficient to claim a selected model capability. Required flags are `text`, `structured_json`, `json_schema`, `vision`, `model_listing`, `local`, `cloud`, and optional `streaming`, context window, and image limits.

`true` means the selected endpoint/model was documented or tested as supporting the capability. `false` means it is known not to support it. `unknown` means ClipGauge must not rely on it and must either test, degrade, or ask the user to configure an override.

## Normalized inference contract

```text
InferenceRequest
- prompt: string
- schema: JSON object
- images: ordered list of ImageInput
- temperature: optional float
- purpose: stage/purpose identifier
- job_id: optional job identity
- provider_profile_id: immutable profile reference
- capability_requirements: required flags
- timeout_seconds: bounded timeout

ImageInput
- bytes: binary payload held only for the request
- mime_type: validated image MIME
- width/height: optional source metadata
- prepared_size: bounded encoded dimensions/bytes

InferenceResult
- data: schema-validated JSON object
- provider_profile_id
- provider_kind
- model
- capabilities_used
- degraded_signals: explicit list such as `vision_unavailable`
- structured_level: `native_schema`, `json_mode`, or `text_compatibility`
- latency_ms
- cache_hit
- provider_request_id: optional safely redacted identifier
```

Provider adapters translate only at the boundary:

```text
ClipGauge InferenceRequest
  -> adapter-specific HTTP/local request
  -> normalized response extraction
  -> local JSON/schema validation
  -> InferenceResult or normalized ProviderError
```

No scoring stage may inspect raw provider response fields or catch provider-specific HTTP errors.

## Structured-output levels

**Level A — native schema** uses a selected model/endpoint’s explicit JSON Schema enforcement. The adapter must still parse and validate locally because provider documentation can change and endpoint support can differ.

**Level B — JSON mode** requests valid JSON without reliable schema enforcement, then performs local schema validation. A single bounded corrective retry is allowed for schema-invalid output when the provider error is retryable.

**Level C — text compatibility** is an explicit degraded mode. The prompt requests JSON, the adapter extracts a bounded JSON object, validates locally, and performs one bounded corrective retry. The result records `structured_level=text_compatibility` and the UI lowers reliability expectations.

## Provider error taxonomy

Adapters map failures to stable codes:

```text
AUTH_INVALID
PROVIDER_UNAVAILABLE
MODEL_NOT_FOUND
MODEL_UNSUPPORTED
RATE_LIMITED
QUOTA_EXHAUSTED
BILLING_REQUIRED
TIMEOUT
NETWORK_FAILED
STRUCTURED_OUTPUT_INVALID
CONTEXT_TOO_LARGE
VISION_UNSUPPORTED
PROVIDER_RESPONSE_INVALID
INTERNAL_PROVIDER_ERROR
```

The error carries a safe user-facing message, optional retry-after seconds, provider/profile identity, and a redacted diagnostic identifier. Raw response bodies and authorization material never cross the scoring or UI boundary.

## Job snapshot and migration

`Settings` gains `provider_profile_id`, `provider_kind`, `provider_model`, `provider_endpoint_identity`, `provider_capabilities`, and `provider_schema_version`, while retaining `llm_mode` only as a legacy migration field. `Settings.to_json()` writes the immutable provider snapshot into the job database and job directory. `Settings.from_json()` performs a fail-safe migration:

| Existing persisted state | Migrated profile | Behavior |
|---|---|---|
| `llm_mode="gemini"` | Stable Gemini profile with current model/default endpoint | Existing Gemini vault secret remains usable; no raw key enters the snapshot. |
| `llm_mode="ollama"` | Loopback Ollama profile | Existing jobs remain resumable; selected model is preserved when present, otherwise health/model discovery is explicit. |
| New provider snapshot | Same provider/profile/model/capability snapshot | Resume cannot silently switch provider or model. |
| Unknown/malformed provider fields | Legacy-compatible safe profile or actionable migration failure | Never guess a cloud destination or expose a secret. |

Migration is idempotent. A job directory receives a migrated settings envelope only after atomic validation. The original v0.1.x fields remain readable for rollback and audit until a later schema migration explicitly retires them.

## Cache identity

The deterministic inference-cache key is a canonical hash over:

```text
cache_schema_version
provider_profile_id
provider_kind
model
normalized endpoint identity
prompt
canonical JSON schema
ordered image content digests
structured-output level/capability requirements
relevant temperature and mode settings
```

Secret values and secret names are excluded. Changing a credential for the same provider/profile/model does not invalidate deterministic identity by itself. Profile identity changes deliberately isolate results even when two endpoints happen to share a model name.

## URL and transport security

Base URLs are parsed and normalized before persistence. Accepted schemes are HTTPS, plus loopback HTTP for local providers. Remote HTTP requires explicit warning/confirmation. `file:`, `data:`, `javascript:`, shell-like schemes, malformed authority, embedded credentials, query-string secrets, and unsafe Unix-socket URL forms are rejected. Authenticated requests disable redirects unless same-origin redirect behavior is proven safe. HTTPS certificate verification remains enabled, and no normal UI control disables it.

## Secret-vault mapping

The Rust vault owns provider secrets. Secret slots are typed by profile ID and purpose, for example `provider:<profile-id>:auth`. The Python process receives an operation-scoped environment or IPC secret only for the active provider call. Diagnostics redact generic authorization headers, known provider key prefixes, custom secret header values, and any configured secret value. Settings, job snapshots, cache keys, support bundles, exported profiles, and URLs remain secret-free.

## Model discovery and test connection

Model discovery is optional and short-lived. Providers with a reliable model endpoint expose a refresh action; generic providers always permit manual model entry when `/models` is absent. `Test Connection` performs bounded endpoint reachability, auth acceptance, selected-model existence, tiny text inference, structured-output verification when selected, and optional synthetic-image verification. It returns `PASS`, `WARNING`, or `FAIL` with capability evidence and normalized error codes.

## Privacy and scoring integration

The scoring stage receives the normalized result and capability state. If vision is required but unavailable, the adapter does not silently discard frames: it returns a result with `degraded_signals=["vision_unavailable"]` or a clear `VISION_UNSUPPORTED` error when visual input is mandatory. Clip ledger provenance records provider profile ID, kind, model, structured level, capabilities used, and degradation signals. Privacy Activity uses the same snapshot to describe local versus network destinations and whether frames/transcript excerpts may leave the device.

## Extension rule

Adding a new compatible provider should normally require a profile preset or metadata entry, not changes to scoring code. Provider-specific behavior belongs in an adapter implementing the normalized contract. Curated presets may add discovery and capability probes, while the generic adapter remains the fallback for unknown OpenAI-compatible services.
