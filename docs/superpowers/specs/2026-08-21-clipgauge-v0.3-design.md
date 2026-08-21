# ClipGauge v0.3.0 Design Specification

**Status:** Approved for implementation on `feature/v0.3-creator-experience`  
**Baseline:** `de8e8489b083f5cab00a6a9ab69425d810de1bb0`  
**Target:** `v0.3.0`  
**Product promise:** **Turn long videos into ready-to-post vertical clips.**

## 1. Product direction

ClipGauge v0.3 is a creator product, not a developer console with a new color palette. A new user should understand the primary workflow within five seconds: add a video, choose an AI path, and create clips. The normal interface must not require knowledge of GGUF, CUDA, model IDs, JSON Schema, diarization, yt-dlp, or internal pipeline stages. Advanced users retain those controls behind explicit progressive disclosure.

The product remains local-first and AGPL-preserving. ClipGauge Local is a built-in, managed on-device AI path. Ollama, LM Studio, cloud providers, and custom OpenAI-compatible APIs remain optional integrations that reuse the existing provider architecture rather than creating a second inference stack. Upstream attribution, `ORIGIN.md`, `NOTICE.md`, `THIRD_PARTY_NOTICES`, historical tags, and legal/provenance references remain intact.

## 2. Experience principles

| Principle | Product consequence | Acceptance signal |
|---|---|---|
| Creator-first | Normal mode exposes video, AI choice, caption style, and Create clips. | A nontechnical user can start without entering a model ID or endpoint. |
| Complexity managed, not hidden | Setup Center explains assets, sizes, licenses, integrity, and repair actions. | No substantial download starts before consent. |
| Honest progress | Determinate progress is used only when measurable; otherwise the UI shows activity, operation, elapsed time, and “Working normally.” | No fabricated percentage or ETA. |
| Recoverable work | Checkpoints, resumable downloads, and stage-scoped diagnostics preserve completed work. | Speaker failure resumes after completed transcription. |
| Privacy precision | Activity names local work, selected provider, URL retrieval, runtime/model downloads, and optional integrations separately. | ClipGauge Local explicitly says inference stays on this computer. |
| Progressive disclosure | Technical details, model IDs, endpoints, capabilities, runtime versions, and diagnostics are Advanced-only. | Normal mode contains no stale provider-console surfaces. |
| Original identity | Midnight/navy, electric indigo, cyan signal, emerald success, amber warning, warm-red error, proportional typography, and an original SVG-first ClipGauge mark. | No accidental legacy product branding in normal UX. |

## 3. Architecture

The implementation keeps the existing Tauri + React + Python pipeline split and adds explicit contracts rather than duplicating functionality.

```text
React product UI
  ├── onboarding / setup / studio / jobs / review / editor
  ├── downloads / providers / privacy / diagnostics / settings
  └── design tokens + accessible status components
        │ typed Tauri commands and progress events
Rust Tauri bridge
  ├── support-bundle collection and path scoping
  ├── hardware capability snapshot
  ├── managed local-server lifecycle
  ├── runtime/download command mediation
  └── sanitized job/progress metadata
        │ JSON Lines protocol v2
Python pipeline
  ├── stage runner, checkpoints, typed stage errors
  ├── progress v2 and diagnostic emission
  ├── managed runtimes/models/download verification
  ├── hardware-aware ASR selection
  └── shared provider abstraction including clipgauge-local
        │ loopback-only OpenAI-compatible requests
Owned llama-server child process
  └── selected GGUF model under managed storage
```

ClipGauge Local starts a pinned, verified `llama-server` binary on `127.0.0.1` and an available local port. The child process is started through an argument vector, never a shell string; its model path must be contained beneath the managed model directory; its logs are bounded and redacted; health checks are required before inference; and the process is terminated when ClipGauge shuts down if ClipGauge started it. The server is not exposed to LAN interfaces and server tools/agent features are disabled.

The provider abstraction gains a first-class `clipgauge-local` kind. It uses the existing normalized request, structured-output, capability, cache, and privacy pathways. Local inference must not require Ollama, LM Studio, cloud credentials, or a ClipGauge backend once the runtime and selected model are installed.

## 4. Design tokens and visual identity

The primary theme is deep midnight/navy rather than pure black. Initial tokens are `#070B14`, `#0B1020`, and `#11182B` for surfaces; `#7357FF`/`#8066FF` for primary actions; `#22D3EE`/`#38BDF8` for analysis signals; emerald for success; amber only for warnings; and warm rose/red for errors. Exact values are finalized through contrast tests. Tokens cover color, spacing, radius, typography, shadows, motion, z-index, and state semantics in one design layer.

Normal text uses a proportional UI typeface. Monospace is limited to diagnostic IDs, model IDs, endpoints, technical metrics, and code-like values. Motion uses CSS transitions in the 140–240 ms range, supports `prefers-reduced-motion`, and avoids particles, parallax, giant blur layers, and heavy WebGL backgrounds.

The new ClipGauge mark is SVG-first and conceptually combines a clip boundary, signal, measurement, and ranking/gauge without becoming a literal car speedometer. SVG source is authoritative; platform icon exports are generated from it and recorded in brand documentation. The old icon is not modified into the new mark.

## 5. User flows

### 5.1 Onboarding

Page one states “ClipGauge — Turn long videos into ready-to-post clips,” explains that ClipGauge finds strong moments, reframes speakers, adds captions, and exports vertical clips, then offers **Get started** and **How ClipGauge works**.

The AI choice step begins with outcomes rather than provider names:

| Choice | Normal explanation | Advanced details |
|---|---|---|
| ClipGauge Local | Recommended for privacy; runs AI on this computer; no API key required. | llama.cpp release, model revision, quantization, context, backend, paths. |
| Free / BYO cloud | Use a free tier or your own provider account. | Provider, model, auth, endpoint, quota and capability details. |
| Already use local AI? | Connect Ollama or LM Studio. | Loopback endpoint, discovery, model capabilities. |
| Advanced | Custom compatible API. | Endpoint, auth strategy, secret header, schema and vision settings. |

### 5.2 Setup Center

Setup Center inventories core video tools, speech, speaker analysis, audio understanding, camera/reframing, and ClipGauge Local. Every row provides a friendly purpose, exact version/revision, known and installed size, required/optional status, integrity, source, license summary, managed location, and safe Verify/Repair/Remove actions where supported.

Before the first substantial job or download, the selected workflow produces a real storage estimate from the manifest, cache inspection, and free-disk measurement. The user sees required core, speech, speaker/audio/camera, and optional local-AI totals, plus available disk and a clear one-time reuse statement. Actions are **Download & continue**, **Review downloads**, and **Cancel**. A future automatic-download preference is opt-in and does not silently install a multi-GB local model, Ollama, LM Studio, or unrelated integrations.

### 5.3 Studio

Studio is titled **Create clips** and explains that ClipGauge finds the strongest moments in a long video. The input card supports file selection, drag/drop, and a video link. The primary sequence is **Add a video**, **AI**, **Caption style**, and **Create clips**. Caption preset labels describe style: Clean, Bold Pop, Punch, Minimal, and Karaoke, while internal IDs remain compatible.

Normal provider cards use understandable states: Not configured, Credential saved, Testing…, Ready, Ready with limitations, Rate limited, Quota reached, Invalid credential, and Provider unavailable. A saved secret is not itself Ready. Stale pricing copy is removed; provider-specific quotas and pricing are described as provider-dependent.

### 5.4 Processing

The normal stage labels are: Preparing video, Transcribing speech, Identifying speakers, Understanding audio, Finding strong moments, Scoring clips, Smart reframing, and Creating clips. Completed stages show a check and duration; the active stage shows operation, determinate percentage/ETA when reliable or indeterminate activity with elapsed time; future stages remain quiet and are not amber bars. Total elapsed and current-stage elapsed are always visible, and completed jobs retain per-stage durations. The selected accelerator and one-time-download state appear in the technical details and job checkpoint.

### 5.5 Errors and recovery

Every failure card answers what happened, what can be done, whether Retry helps, and where technical details are available. Speaker failures use typed codes such as `SPEAKER_MODEL_DOWNLOAD_FAILED`, `SPEAKER_MODEL_VERIFY_FAILED`, `SPEAKER_MODEL_LOAD_FAILED`, `SPEAKER_AUDIO_LOAD_FAILED`, `SPEAKER_ANALYSIS_FAILED`, and `SPEAKER_CLUSTER_FAILED`. The normal message is plain language, for example: “Speaker analysis couldn’t start. The speaker model could not be loaded. Retry the model download or continue without speaker-aware reframing.” Technical details expose only a diagnostic ID and sanitized details.

Completed work is preserved. A speaker failure explicitly says “Transcription already completed” and offers “Resume from speaker analysis.” Repair operates on the affected asset only and never wipes all model caches.

### 5.6 Review, editor, settings, privacy, and About

Review and Editor retain the existing functional surface but adopt the new tokens, proportional typography, readable copy, keyboard focus, accessible labels, and clear Review → edit → rerender → export actions. Performance feedback replaces “SCORE VS REALITY” in the normal Instagram view; raw constants remain under Advanced scoring details.

Settings includes Storage with sizes for core runtimes, speech models, speaker/audio models, ClipGauge Local models, job files, and render cache, plus Open folder, Remove unused, and Repair. Active job files are never deleted unexpectedly. Privacy Activity has three explicit sections: Stays on this computer, Sent to selected AI provider, and Other network activity. ClipGauge Local says inference stays on this computer while still naming URL retrieval and optional downloads/integrations.

About identifies the actual platform (`Windows x64`, `macOS arm64`, `Linux x64`) and honest signing state, rather than embedding a Linux artifact label in every build. AGPL and upstream/legal attribution remain on the page.

## 6. Runtime and download contracts

### 6.1 Download Manager

The existing verified runtime substrate remains authoritative: `.part` staging, Range resume, maximum size, SHA-256, safe archive extraction, atomic replacement, and last-known-good preservation. The new manager adds an event contract:

```text
asset_id, display_name, bytes_done, bytes_total, fraction,
bytes_per_second, elapsed_seconds, eta_seconds, one_time,
status, retryable
```

Statuses include queued, downloading, paused, verifying, installed, failed, cancelled, and retryable. Pause is exposed only where technically supported. A network drop preserves a safe partial file and resumes when possible; restart reloads download state and requires user choice before continuing. No downloaded executable or model is run or loaded before integrity verification.

### 6.2 Runtime manifest

`runtime-manifest.json` remains the source of truth for pinned versions, revisions, URLs, sizes, hashes, platform assets, licenses, and provenance. The first catalog research records llama.cpp release `b10545` and exact Qwen revisions/files, but implementation must refresh and pin them in the project manifest at release-candidate time.

### 6.3 FFmpeg and yt-dlp

On Windows, FFmpeg/ffprobe use the managed pinned archive and expose Install automatically or Use an existing installation. yt-dlp is installed into the managed runtime directory after consent and never replaced by a random PATH version when a verified managed copy exists. YouTube support uses an optional, pinned, integrity-verified PO-token provider only after license/provenance review. The UI distinguishes public attestation failure, login-required, private/member/age/region/unavailable, and ordinary network failures. Browser-session support is explicit and scoped to yt-dlp, with no cookie persistence or diagnostic inclusion.

## 7. Hardware and ASR

A conservative hardware service records OS, CPU, logical cores, RAM, NVIDIA GPU/VRAM where reliably discoverable, Apple Silicon, Vulkan, CUDA/CTranslate2 availability, and disk capacity. It never infers support from a GPU name alone. ASR chooses a supported accelerator based on detected evidence, retains a reliable optimized CPU path, avoids pretending CTranslate2 supports MPS, and records the selected accelerator in checkpoints and support bundles. Performance evidence compares the previous CPU path with the new supported path on the same controlled fixture, recording audio duration, transcribe duration, alignment duration, realtime factor, and practical peak memory.

## 8. ClipGauge Local model catalog

The first catalog is conservative and consent-based:

| Tier | Candidate | Source revision/file | License/terms | Capability | Initial user-facing role |
|---|---|---|---|---|---|
| Lightweight | Qwen3-1.7B | Qwen revision `90862c4b9d2787eaed51d12237eafdfe7c5f6077`; `Qwen3-1.7B-Q8_0.gguf`; LFS SHA `061b54daade076b5d3362dac252678d17da8c68f07560be70818cace6590cb1a`; 1,834,426,016 bytes | Apache-2.0 | Text, structured output; 32K context | Older/low-memory systems. |
| Balanced — recommended | Qwen3-4B | Qwen revision `bc640142c66e1fdd12af0bd68f40445458f3869b`; `Qwen3-4B-Q4_K_M.gguf`; LFS SHA `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`; 2,497,280,256 bytes | Apache-2.0 | Text, structured output; 131K context with YaRN | Default creator recommendation when detected hardware supports it. |
| Vision | Gemma 3 4B IT | Google revision `093f9f388b31de276ce2de164bdc2081324b9767`; authoritative source `google/gemma-3-4b-it`; exact GGUF mirror/file must be pinned only after terms/provenance review | Google Gemma Terms of Use | Text + image input; 128K context; 8,192 output context | Selected-frame analysis where terms and hardware are accepted. |

The model catalog must not claim a model is Vision-capable without authoritative evidence. It must show exact revision, selected file, size from the exact file metadata, hash, license/terms, context, recommended RAM/VRAM, minimum practical hardware, and limitations. It downloads only one user-selected model, never all tiers.

## 9. Security and privacy

The security contract adds downloaded binary/model integrity, loopback-only local-server binding, child-process ownership and cleanup, no shell strings, model-path containment, bounded logs, provider URL policy, PO-token plugin provenance, explicit browser-cookie consent, diagnostics redaction, support-bundle job scoping, secret vault behavior, redirects, CSP, asset protocol, and safe export checks.

Support bundles include root bridge diagnostics and only the requested validated job’s diagnostics. Manifest metadata includes `support_bundle_version`, `app_version`, OS, architecture, job ID, requested and included diagnostic IDs, and diagnostic count. Exclusions remain API keys, OAuth tokens, source media, transcripts, arbitrary files, and unrelated jobs. If a requested diagnostic is absent, the bundle states: “No diagnostic log was available for this failure.”

## 10. Acceptance and release gates

A v0.3.0 release is blocked if the support bundle omits a requested diagnostic, speaker failures remain generic, local MP4 full jobs fail, ClipGauge Local cannot complete an inference request, OpenRouter full jobs fail, FFmpeg still requires unexplained manual Windows setup, first-run downloads lack disclosure/consent, downloads cannot recover safely, the public YouTube test fails solely for missing PO-token support, ASR acceleration crashes, cancellation leaves known children, legacy branding remains in normal UI, native CI is red, security tests fail, or strict Clippy fails.

The mandatory Windows acceptance uses the actual packaged v0.3.0 release candidate and tests installer, onboarding, Setup Center, OpenRouter Free, ClipGauge Local, a local MP4 through full pipeline, Review/Edit/Rerender/Export, cancellation during download/transcription/rendering, restart/resume, output quality, YouTube public URL handling, progress/download reuse, accessibility, and responsive desktop sizes. Linux CI is not a substitute.

## References

[1]: https://github.com/ggml-org/llama.cpp "ggml-org/llama.cpp official repository"

[2]: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md "llama.cpp official HTTP server documentation"

[3]: https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide "yt-dlp official PO Token Guide"

[4]: https://huggingface.co/Qwen/Qwen3-1.7B-GGUF "Qwen3-1.7B-GGUF official model card"

[5]: https://huggingface.co/Qwen/Qwen3-4B-GGUF "Qwen3-4B-GGUF official model card"

[6]: https://huggingface.co/google/gemma-3-4b-it "Google Gemma 3 4B official model card"

[7]: https://github.com/Brainicism/bgutil-ytdlp-pot-provider "BgUtils PO-token provider repository"

[8]: https://github.com/coletdjnz/yt-dlp-getpot-wpc "WebPoClient PO-token provider repository"
