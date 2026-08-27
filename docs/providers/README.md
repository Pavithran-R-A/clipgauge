# ClipGauge provider guide

ClipGauge keeps media processing local-first and does not require a ClipGauge account, subscription, cloud backend, or telemetry. The scoring provider is selected explicitly for each run. A local provider keeps inference on the device; a cloud provider may receive transcript excerpts, prompts, and—only when the selected model advertises vision—sampled frames. Review **Privacy Activity** before sending source-derived material to a third party.

## Local options

**Ollama** uses the loopback API at `http://127.0.0.1:11434` and discovers installed models through `/api/tags`. Start Ollama and load a compatible chat model yourself; ClipGauge does not download large models automatically. Structured output and vision are model-dependent and are reported conservatively.

**LM Studio** uses the loopback OpenAI-compatible API at `http://127.0.0.1:1234/v1` and discovers models through `/models` when the server exposes that endpoint. Choose a loaded chat model or leave the model as `auto`. Authentication is disabled by default for the local preset.

A custom local OpenAI-compatible endpoint can be configured with a loopback HTTP base URL, a model, and no authentication. Remote plain HTTP is rejected by default; use HTTPS for remote providers.

## Curated cloud / bring-your-own-key options

The current presets use the normalized provider adapter and allow manual model selection. **Free access, quotas, model availability, card requirements, retention, and terms are controlled by the provider and can change.** ClipGauge does not promise that any provider is permanently free or unlimited.

| Preset | Default endpoint family | Authentication | Capability posture |
|---|---|---|---|
| Gemini | Google Gemini Developer API | API-key header in the child operation | Structured JSON and vision are supported by the curated path; model availability is tested at runtime. |
| OpenRouter | OpenAI-compatible `/v1` | Bearer token | `openrouter/free` is available as a manual model choice; routed model capabilities must be treated as variable. |
| Groq | OpenAI-compatible `/openai/v1` | Bearer token | Structured output and vision are model-dependent; use Test Connection. |
| Cloudflare Workers AI | Account-specific OpenAI-compatible inference endpoint | Bearer token | Enter the account-specific endpoint and model; capabilities vary by model. |
| Hugging Face | Router OpenAI-compatible chat endpoint | Bearer token | Chat-style inference only; underlying provider/model capabilities vary. |
| Cerebras | OpenAI-compatible `/v1` | Bearer token | Curated as an additional compatible provider; current availability and limits must be checked. |

To configure a cloud preset, choose it in Studio, set the model, enter a credential in the password field, and select **SAVE CREDENTIAL**. The credential is stored by the operating-system vault. It is not written to normal settings, job snapshots, cache keys, support bundles, URLs, command-line arguments, or Git.

## Custom OpenAI-compatible endpoint

Choose **custom** and provide a profile endpoint, model, and one of the supported authentication modes: no authentication, bearer token, API-key header, or a custom secret header. Custom header names are validated; arbitrary request scripting, shell hooks, and executable templates are not supported. Model-list discovery is best effort and manual model entry always remains available.

Remote HTTPS requests disable redirects so an authorization header cannot be forwarded to another host. TLS verification remains enabled. Dangerous URI schemes and remote plain HTTP are rejected. Loopback HTTP is reserved for local services.

## Test Connection and capability states

**TEST CONNECTION** makes a small request using the selected endpoint and model. It reports `PASS`, `WARNING`, or `FAIL` with an actionable reason. A saved credential alone is never presented as proof of connectivity. The result may identify model availability, authentication failure, rate/quota limits, structured-output level, and vision degradation.

ClipGauge uses three structured-output levels: native JSON Schema, JSON mode with local validation, and explicit text compatibility mode with bounded corrective retries. A model that cannot accept images is not silently treated as vision-capable; missing vision is recorded in score provenance and the UI.

## Privacy and terms

For current endpoint details, quotas, terms, and retention practices, consult the official provider documentation linked in [`PROVIDER_RESEARCH_2026.md`](./PROVIDER_RESEARCH_2026.md). Do not paste credentials into issues, chat, screenshots, or documentation. Optional Pexels and Instagram features have separate credentials and network disclosures.

## YouTube public-link compatibility

YouTube URL import is a **best-effort compatibility feature** whose availability depends on YouTube’s current playback rules. Local-file import is the supported fallback and does not depend on YouTube.

Setup reports two distinct states. **YouTube tools ready** means the pinned yt-dlp runtime, Node runtime, released bgutil provider source, provider plugin, and loopback health check are verified. **YouTube download tested** means a real unauthenticated public transfer completed and its media was probed successfully. A loopback `/ping` check never implies that YouTube will accept a media request. The most recent successful public check stores only a timestamp, yt-dlp version, provider version, and compatibility method; it never stores tokens, cookies, visitor IDs, or browser-profile data. A later attestation failure invalidates that public-verification claim.

The managed provider is the official `Brainicism/bgutil-ytdlp-pot-provider` source archive from tag `1.3.2`, with the archive URL and SHA-256 pinned in the runtime manifest. ClipGauge builds the server and copies the plugin from that same archive, so the server and plugin remain on one compatible released revision. The integration uses yt-dlp’s normal provider path first and may try its documented `mweb` guest-client alternative after an attestation-specific failure. It does not enable `formats=missing_pot`.

ClipGauge does not read browser cookies or profiles by default. The optional WPC browser-assisted provider is not part of the normal creator path. If it is separately installed and a local Chrome or Chromium executable is detected, a future explicit user action may launch it only after explaining that it is optional, uses a local browser to obtain public playback attestation, requires no account, and can be cancelled. ClipGauge never installs a browser automatically and never uses logged-in browser state for normal operation.
