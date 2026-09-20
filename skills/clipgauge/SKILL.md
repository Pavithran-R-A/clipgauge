# ClipGauge Capability Suite

Use the native ClipGauge pipeline for all jobs. Do not replace candidate
synthesis with transcript-only LLM timestamps.

## Inputs

SRT and WebVTT files use the versioned job input manifest. Accepted subtitles
are copied into the job directory and hashed. Resume does not depend on the
original source path.

Supported platform classification includes local files, YouTube, and Bilibili.
Bilibili uses the managed yt-dlp runtime and no-playlist behavior.

## Privacy

Private mode keeps subtitle text and analysis local. Other modes follow the
existing bounded candidate-transcript provider contract. Never place secrets in
job settings, MCP arguments, API bodies, JSONL, logs, or support bundles.

## Headless interfaces

`clipgauge mcp` uses stdio. `clipgauge serve` is loopback-first. Non-loopback
binding requires `CLIPGAUGE_SERVER_TOKEN` or token stdin. CORS requires an
explicit allowlist; wildcard origins are forbidden.

## Qualification

Run deterministic subtitle, migration, MCP, server, Docker, and collection
tests. Report live Bilibili validation separately when unavailable.
