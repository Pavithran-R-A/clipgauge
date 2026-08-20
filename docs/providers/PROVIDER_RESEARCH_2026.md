# ClipGauge Provider Research — 2026

**Research date:** 2026-08-20  
**Scope:** Official first-party documentation only, with mutable quota/pricing facts treated as time-sensitive.  
**Product policy:** Provider metadata informs capability-aware UX; it does not become a permanent promise of free, unlimited, or fixed-price usage.

## Research conclusions

The provider ecosystem is sufficiently convergent around chat-style JSON APIs to support one normalized ClipGauge adapter architecture. OpenAI-compatible endpoints are especially useful for OpenRouter, Groq, Cloudflare Workers AI, LM Studio, Cerebras, and arbitrary compatible services, but capability support is model- and endpoint-dependent. ClipGauge must validate selected capabilities rather than infer them from provider family names.

The safest v0.2.0 product position is explicit provider selection, local-first defaults, OS-vault secrets, local schema validation, bounded retries, and provider-aware privacy disclosure. Cloud options should be presented as free-tier/BYO-key or free-router options only where current official material justifies that label; no provider should be described as permanently free or unlimited.

## Provider matrix

| Provider | Official API / endpoint family | Authentication | Model discovery | Structured output | Vision | Locality and current access caveat |
|---|---|---|---|---|---|---|
| Gemini Developer API | Google Gemini API / Interactions and generation APIs | API key; official structured-output example uses `x-goog-api-key` [1] | Official Gemini API model documentation should be queried and cached; selected model remains explicit | Native JSON Schema response format is documented [1] | Model-dependent; capability must be read from selected model metadata/documentation | Cloud. Official pricing documents free and paid usage tiers with quotas that can change [2]. Do not hard-code exact limits or a permanent free promise. |
| OpenRouter | OpenAI-compatible API; `openrouter/free` router | API key | Models page and provider metadata; structured-output support is endpoint-specific [3] | `response_format.type=json_schema`; use `require_parameters=true` and strict mode where supported [3] | `openrouter/free` documentation says the router filters for image understanding when needed [4]; verify selected endpoint/model | Cloud router. Official page describes a free-model router and says it accepts text/images, but routing and model availability are dynamic [4]. |
| Groq | OpenAI-compatible `https://api.groq.com/openai/v1/chat/completions` family [5] | Bearer API key | API/model documentation and model list | Strict structured outputs are available only on selected models; best-effort mode is broader [6] | Selected-model only; must not be assumed from provider support | Cloud. Free-plan/rate limits are account/model dependent and must be surfaced generically. |
| Cloudflare Workers AI | OpenAI-compatible account-scoped `/ai/v1/chat/completions` endpoint [7] | Bearer API token plus account identifier [7] | Cloudflare model catalog; model capabilities are model-specific | JSON mode and JSON Schema-style response formats are documented, but Cloudflare warns schema compliance is not guaranteed in every situation [8] | Model-specific; official JSON-mode list includes a vision model, but selected model must be checked [8] | Cloud. Account/token/model configuration is required. Treat free quota as mutable and avoid billing promises. |
| Hugging Face Inference Providers | Hugging Face Hub `InferenceClient` or compatible chat endpoints [9] | HF token | Provider/model selection and model/provider catalog | Structured-output guide documents JSON Schema and strict mode; it recommends selecting a specific provider/model for compatibility [9] | Underlying provider/model dependent; chat-style scope only | Cloud/provider router. Token and provider availability/limits vary; no blanket “all HF tasks” claim. |
| Ollama | Local Ollama API; OpenAI-compatible path is also available | No API key for default local loopback; optional configured auth must be handled as secret | Local model listing and health endpoints | `format` schema and OpenAI-compatible structured output are documented [10] | Model-dependent; official structured-output docs include a vision example [10] | Local by default. Service may be stopped, model may be missing, and model downloads must never occur automatically without user confirmation. |
| LM Studio | Local OpenAI-compatible `/v1/models`, `/v1/chat/completions`, `/v1/responses` [11] | No key required for normal local server; user-configured auth must remain secret | `/v1/models` [11] | JSON Schema through `/v1/chat/completions`; not all models support it, especially smaller models [12] | Chat completions support text and images at endpoint level, but model support must be checked [11] | Local by default. Server must be started by the user; show a clear not-running state. |
| Cerebras (additional candidate) | OpenAI-compatible `https://api.cerebras.ai/v1` [13] | API key | Public model endpoint exists without an API key and exposes capabilities/pricing [14] | Strict and best-effort structured output are documented [15] | Public model metadata indicates selected models can be text-only; vision must be checked per model [14] | Cloud. Official pricing advertises a `$5` free trial after account creation, not a permanent free tier [16]. Investigated as a possible future preset, not a permanent free promise. |

## Detailed provider notes

### Gemini Developer API

Google’s current structured-output documentation shows JSON Schema response formats, SDK support through Pydantic/Zod, REST usage, and streamed structured output [1]. The implementation should preserve Gemini’s existing native schema path while routing it through the normalized ClipGauge request/result contract. Model selection and vision support must be model-specific. The official pricing page describes free and paid usage modes with mutable quotas and pricing [2]; UI copy should therefore say that free and paid tiers may be available and that current account/model limits must be checked.

### OpenRouter

OpenRouter’s structured-output documentation states that support is determined per endpoint, not merely per model, and recommends checking supported parameters, using `require_parameters=true`, and setting `response_format` to JSON Schema when structured output is required [3]. The official free-router page says `openrouter/free` dynamically selects free models and filters for needed features such as image understanding and structured outputs [4]. ClipGauge must still record the selected provider/model capability result and must not silently accept a routed endpoint that cannot satisfy scoring requirements.

### Groq

Groq documents an OpenAI-compatible API and structured outputs. Its current structured-output documentation distinguishes strict constrained decoding from best-effort mode: strict mode is limited to selected models, while best-effort mode is broader and may produce schema-invalid results [5] [6]. The adapter should therefore implement Level A for strict models, Level B for JSON/best-effort models with local validation and bounded corrective retry, and a clear unsupported/degraded state when neither is reliable. Vision must be selected-model aware.

### Cloudflare Workers AI

Cloudflare documents an account-scoped OpenAI-compatible endpoint using an account identifier and bearer token [7]. JSON mode accepts JSON object or JSON Schema-style response formats, but the official page explicitly warns that model responses may still fail to satisfy complex schemas and that JSON mode does not support streaming [8]. This maps directly to capability negotiation and Level B local validation. The account identifier is ordinary configuration unless Cloudflare’s current documentation says otherwise; the API token is always a vault secret.

### Hugging Face Inference Providers

Hugging Face documents `InferenceClient` with provider selection and HF token authentication, and its structured-output guide recommends choosing a specific provider/model because compatibility can differ [9]. ClipGauge should implement chat-style inference only, keep provider routing visible in the profile, and avoid claiming arbitrary Hugging Face task support. Structured output and vision are underlying provider/model capabilities rather than guarantees of the HF brand.

### Ollama

Ollama’s official API documentation describes a local API expected to remain backward-compatible even though it is not strictly versioned [17]. Its structured-output documentation supports JSON Schema through the `format` field and documents vision with structured outputs [10]. The v0.2 adapter must stop discarding images, discover installed models, test the selected model, identify vision and structured-output support conservatively, and report stopped-service, missing-model, context, malformed-response, and unsupported-capability states.

### LM Studio

LM Studio documents local OpenAI-compatible `/v1/models`, `/v1/chat/completions`, `/v1/responses`, and other endpoints, with a default example at `http://localhost:1234/v1` [11]. Its structured-output documentation says JSON Schema is supported through chat completions but warns that not all models support it, particularly smaller models [12]. The adapter can reuse the generic local OpenAI-compatible implementation, adding a convenient preset, local health/model discovery, and explicit server-not-running UX.

### Cerebras additional investigation

Cerebras documents OpenAI compatibility at `https://api.cerebras.ai/v1`, structured outputs, and a public model catalog that exposes model capabilities and pricing without an API key [13] [14] [15]. Its official pricing page describes a `$5` free trial after account creation and paid developer access, not an always-free tier [16]. It is therefore a credible future candidate and a valuable test of the generic architecture, but it should not be presented as a permanent free preset. Its current public model example reports structured outputs but no vision, reinforcing the requirement for model-level capability checks.

## Security and privacy implications

All cloud providers transmit some combination of prompts, transcript excerpts, selected frames, metadata, or request diagnostics outside the device. The UI must show the selected provider, destination host, model, whether images are included, and whether the path is local or cloud. Provider policies and retention terms can change; provider documentation links must be available from configuration and privacy help rather than being summarized as permanent guarantees.

Secrets must be stored through ClipGauge’s Rust-owned operating-system credential vault. API keys, bearer tokens, custom secret-header values, and provider request credentials must not appear in URLs, query strings, normal configuration, job snapshots, logs, diagnostics, support bundles, cache keys, shell arguments, Git, or CI output. Custom endpoint redirects must be disabled or proven same-origin and safe before credentials are forwarded. HTTPS verification remains enabled, and remote plain HTTP requires an explicit warning/confirmation path.

## Implementation decisions derived from research

| Decision | Rationale |
|---|---|
| Use one normalized adapter contract | OpenAI-compatible APIs reduce duplicated transport code, while provider-specific capability and error translation remains necessary. |
| Treat capabilities as model- and endpoint-level | Official OpenRouter, Groq, Cloudflare, HF, Ollama, LM Studio, and Cerebras documentation all show support varies by model or endpoint. |
| Make structured output levels explicit | Native strict schema, JSON/best-effort with local validation, and text compatibility have materially different guarantees. |
| Keep local presets first-class | Ollama and LM Studio provide local paths with no mandatory cloud API key and are the strongest privacy/no-cost options. |
| Make cloud free claims mutable | Official free access is tiered, quota-limited, trial-based, or dynamically routed; the UI must say to check current provider limits. |
| Keep explicit provider selection | Automatic cloud failover could transmit user data to an unselected provider and is disallowed by the v0.2.0 privacy requirement. |
| Support generic custom OpenAI-compatible endpoints | LM Studio, Cloudflare, Groq, Cerebras, and OpenRouter demonstrate the usefulness of a common endpoint family, while custom configuration future-proofs unknown services. |

## References

[1]: https://ai.google.dev/gemini-api/docs/structured-output "Google Gemini API structured outputs"
[2]: https://ai.google.dev/gemini-api/docs/pricing "Google Gemini Developer API pricing"
[3]: https://openrouter.ai/docs/guides/features/structured-outputs "OpenRouter structured outputs"
[4]: https://openrouter.ai/openrouter/free "OpenRouter Free Models Router"
[5]: https://console.groq.com/docs/openai "Groq OpenAI compatibility"
[6]: https://console.groq.com/docs/structured-outputs "Groq structured outputs"
[7]: https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/ "Cloudflare Workers AI OpenAI compatibility"
[8]: https://developers.cloudflare.com/workers-ai/features/json-mode/ "Cloudflare Workers AI JSON mode"
[9]: https://huggingface.co/docs/inference-providers/en/guides/structured-output "Hugging Face Inference Providers structured outputs"
[10]: https://docs.ollama.com/capabilities/structured-outputs "Ollama structured outputs"
[11]: https://lmstudio.ai/docs/developer/openai-compat "LM Studio OpenAI compatibility endpoints"
[12]: https://lmstudio.ai/docs/developer/openai-compat/structured-output "LM Studio structured output"
[13]: https://inference-docs.cerebras.ai/resources/openai "Cerebras OpenAI compatibility"
[14]: https://inference-docs.cerebras.ai/api-reference/models/public-models "Cerebras public models and capabilities"
[15]: https://inference-docs.cerebras.ai/capabilities/structured-outputs "Cerebras structured outputs"
[16]: https://www.cerebras.ai/pricing "Cerebras pricing"
[17]: https://docs.ollama.com/api "Ollama API overview"
