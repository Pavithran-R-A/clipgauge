# v0.2.0 provider contract test matrix

Mandatory CI uses deterministic mocks and never sends source media or paid inference requests. Optional live-provider smoke is manual-only and must report `SKIPPED` when a repository secret is absent.

| Provider/path | Endpoint/auth contract | Model listing | Structured output | Vision | Error/security coverage |
|---|---|---|---|---|---|
| Gemini | Google endpoint; API-key header; key absent from URL | `/models` best effort | Native schema path | Curated image-capable path; model-dependent | Auth, quota/rate, malformed response, redaction |
| OpenRouter | `/v1`; bearer token | `/models` best effort | Native schema/JSON/text fallback based on profile | Conservative model-dependent behavior | Auth, model, quota/rate, redirects, no URL secret |
| Groq | `/openai/v1`; bearer token | `/models` | Conservative native/JSON fallback | Model-dependent | Auth, quota/rate, invalid JSON |
| Cloudflare Workers AI | Account-specific compatible endpoint; bearer token | Best effort | Model-dependent | Model-dependent | Account/token/model errors and URL policy |
| Hugging Face | Router compatible chat endpoint; bearer token | Best effort | Underlying provider/model dependent | Underlying provider/model dependent | Auth, model, capability degradation |
| Cerebras | Compatible `/v1`; bearer token | `/models` best effort | Conservative native/JSON fallback | Curated text-only default records limitation | Auth, quota/rate, schema failures |
| Ollama | Loopback `/api/tags`; no cloud credential | Installed model listing | Native structured output where supported | Model-dependent; images are not silently discarded | Service stopped, model missing, malformed response |
| LM Studio | Loopback `/v1/models`; no credential by default | `/models` | Compatible JSON levels | Model/server dependent | Server stopped, manual model entry, redirects |
| Custom compatible | User-validated HTTPS or loopback HTTP | Best effort; never required | Native schema, JSON mode, or explicit text compatibility | Capability override/detected behavior | Scheme, remote HTTP, auth modes, custom header, redirect, TLS |

## Executed deterministic provider coverage

The provider suite verifies profile construction, URL policy, cache identity and secret exclusion, native schema translation, text-only vision degradation, image translation, normalized auth/model/quota errors, Retry-After parsing, model-listing failure with manual entry, redirect disabling, legacy settings migration, LM Studio loopback defaults, and custom secret-header metadata. Real provider live tests remain separate from mandatory CI and are not represented as passing unless their manual workflow reports `PASS`.
