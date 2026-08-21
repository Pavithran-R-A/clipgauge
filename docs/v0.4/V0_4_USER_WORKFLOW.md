# ClipGauge v0.4 Creator Workflow and Managed Assets

ClipGauge v0.4 treats runtime, model, compatibility, and support data as one explicit managed-asset system. The desktop application remains a local application: it does not require a hosted ClipGauge service, does not start a persistent remote daemon, and does not use browser cookies unless the user explicitly selects an authenticated browser-session option.

## First launch

On first launch, the application performs read-only inventory and hardware checks. Setup Center then presents the exact managed groups available for the current platform. The user sees the byte estimate, asset purpose, license, provenance, destination, and one-time-download status before approving a group. No large asset is fetched merely because a job was started.

| Group | Contents | Typical use |
|---|---|---|
| Video engine | Pinned caption-capable FFmpeg archive | Decode, probe, caption, and render video |
| Speech recognition | faster-whisper large-v3-turbo snapshot, English alignment checkpoint, NLTK `punkt_tab` | Transcription and word timings |
| Clip analysis | Speaker, laughter, audio-event, and smart-camera model assets | Candidate signals and camera direction |
| YouTube compatibility | Pinned yt-dlp, portable Node.js, bgutil 1.3.2 source/plugin, locked provider dependencies | Public YouTube extraction and PO-token support |
| ClipGauge Local | llama.cpp b10545 and selected Qwen GGUF model | Local structured clip scoring |
| Optional provider | Ollama, LM Studio, cloud, or custom endpoint configuration | User-selected scoring alternative |

Approval is persisted by group and asset identity under `~/.clipgauge/download-consent.json`. A later version, revision, URL, digest, or destination does not silently inherit an earlier approval. Downloads are staged in `.part` files, resumed only when the server response is safe, bounded by expected size or a conservative cap, hashed, and atomically installed. A cancelled or failed operation leaves the last-known-good verified file untouched.

## Managed data layout

The default root is `~/.clipgauge`. The application creates the following subdirectories as needed:

```text
~/.clipgauge/
├── bin/                         # legacy migration source only
├── runtimes/
│   ├── ffmpeg/<revision>/<platform>/
│   ├── llama-server/<revision>/
│   ├── node/<revision>/
│   ├── yt-dlp/<revision>/
│   └── youtube/bgutil/<revision>/
├── models/
│   ├── asr/faster-whisper-large-v3-turbo/<revision>/
│   ├── clipgauge-local/
│   ├── hf/                     # library cache root, offline during compute
│   └── torch/checkpoints/
├── data/nltk/
├── jobs/
├── downloads.json
├── download-consent.json
└── db.sqlite3
```

The legacy `~/.publikclip` directory and pre-existing library caches are read-only migration sources. The migration copies only files whose complete SHA-256 matches the current catalog, never deletes the source, and records a reuse outcome. A corrupt or ambiguous legacy file is reported as `needs-repair` and is not executed or used for inference.

## Compute-time guarantees

The ASR stage sets Hugging Face, Torch, NLTK, and Transformers offline variables and loads the verified local faster-whisper directory directly. WhisperX alignment is limited to an installed managed language asset; an unsupported language produces an actionable setup error instead of a network fetch. Analysis stages use the registry adapter, which requires `core:analysis` consent before any registered model can be acquired. Render refuses to start a hidden FFmpeg download and directs the user to Setup Center.

## YouTube and authenticated access

The default YouTube path uses the managed yt-dlp and loopback bgutil provider when the YouTube compatibility group is installed. The provider server binds to `127.0.0.1:4416`, and its health endpoint is checked before yt-dlp is invoked. If the provider is absent or unhealthy, the job reports `YTDLP_PROVIDER_NOT_READY` with Setup Center recovery guidance.

Browser sessions are not inspected by default. For an explicitly authenticated run, the CLI accepts a constrained browser name:

```sh
uv run clipgauge run "https://www.youtube.com/watch?v=..." \
  --provider clipgauge-local \
  --cookies-from-browser chrome
```

The selected browser name is saved in the job settings snapshot for resume reproducibility. ClipGauge does not copy raw cookies into its data directory, support bundles, or job artifacts. If the source still requires login, age confirmation, membership, or region access, yt-dlp returns a stable creator-facing state rather than claiming that a generic 403 was solved.

## Local provider behavior

ClipGauge Local is loopback-only and uses an owned llama-server subprocess. Setup installs the pinned binary and model; inference starts the subprocess only after both are present and health-checked. Ollama and LM Studio are optional local alternatives: ClipGauge probes their documented loopback APIs, never downloads models for them, and reports `service-stopped`, `model-missing`, or `service-healthy` states. Cloud providers remain opt-in and credential-backed.

## Repair and cancellation

Setup Center exposes progress with bytes, speed, elapsed time, ETA when known, current asset, cache reuse, and one-time-download indicators. The cancel action terminates the owned setup subprocess and preserves any verified prior installation. A retry reuses a safe `.part` file when range semantics are valid; a mismatched or truncated response is discarded before retry. Repair actions re-check the complete file, archive traversal boundaries, expected member allow-lists, executable capability, and loopback health.

## Uninstall

Deleting `~/.clipgauge` removes managed jobs, runtime archives, models, NLTK data, provider source, logs, and persisted download state. Credential-store entries are platform-managed and must be removed through the operating system credential manager. Legacy `~/.publikclip` data is never deleted automatically by ClipGauge.
