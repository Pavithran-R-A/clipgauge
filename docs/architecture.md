# ClipGauge architecture

ClipGauge is a local-first desktop application made of three cooperating parts: a Tauri desktop shell, a React interface, and a Python processing pipeline. The boundaries are intentionally visible so that a contributor can change one part without guessing where lifecycle, filesystem, or media work belongs.

## Runtime flow

```text
React interface
    │ typed commands and events
    ▼
Tauri Rust bridge
    │ job lifecycle, cancellation, paths, diagnostics
    ▼
Python pipeline CLI
    │ structured JSONL events and result files
    ▼
Managed local job directory
```

The React interface owns navigation, creator choices, progress presentation, review, and export controls. It does not decide where arbitrary files may be read or written. The Tauri bridge owns process startup, cancellation, job identity, managed filesystem boundaries, and native diagnostics. The Python sidecar owns media analysis, candidate scoring, caption preparation, rendering, and provider adapters.

## Creator workflow

A new session starts in **Create**. The user supplies a local video or supported link, chooses a provider and caption style, and starts a job. Progress is streamed into a human-readable timeline. The result keeps the source job identity, candidate scores, signal explanations, render status, and provider provenance together so the **Why this clip** view can explain a recommendation.

**Sessions** is the re-entry point for previous jobs. **Setup & Storage** handles managed runtime and model assets as one consented queue. **AI Providers** handles scoring destinations and credentials. **Integrations** handles optional Pexels and Instagram connections. **Privacy** summarizes data flow, while **Help & Diagnostics** provides a redacted support bundle path.

## Data and boundary rules

Job outputs live below the managed ClipGauge data root. A render is not presented as available merely because a path string exists; the bridge validates the artifact boundary and the interface shows a diagnostic when a render is missing, outside the managed root, or invalid.

Credentials are requested only for operations that need them and are stored through the operating-system credential store when available. They are not placed in job snapshots, normal project settings, support bundles, URLs, or command-line arguments. Browser-cookie retrieval remains opt-in and is recorded in the job settings snapshot.

Network behavior is explicit. A selected cloud scoring provider, a source URL, an approved setup download, Pexels, or Instagram can create network activity. Local providers use loopback endpoints and should not be described as cloud services.

## Testing boundary

Frontend tests cover navigation contracts, setup language, provider discoverability, and media trust states. Python tests cover pipeline behavior and output contracts. Rust tests cover bridge boundaries, lifecycle, path validation, credential handling, and security-sensitive behavior. Hardware-dependent model runs, real provider credentials, platform signing, and notarization are separate checks and must be reported as such.

For provider-specific behavior, see [`providers/README.md`](providers/README.md). For the visual system and disclosure rules, see [`design.md`](design.md).
