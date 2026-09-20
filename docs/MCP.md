# ClipGauge MCP

ClipGauge exposes an optional stdio MCP server:

```text
uv run clipgauge mcp
```

The server wraps the existing SQLite job store and filesystem checkpoints. It
does not create a second pipeline or registry. Progress is written to stderr;
stdout contains JSON-RPC responses only.

Available tools include preflight, provider listing, job start/status/results,
cancellation, clip rendering, rerendering, and collection operations.

`start_job` accepts a source, optional subtitle path, category, provider profile,
model, quality mode, output preference, caption preset, and browser-session
selection. It never accepts API keys, tokens, cookies, or authorization
headers. Provider credentials resolve through existing secure ClipGauge
configuration.

Local source paths are canonicalized. Outputs remain inside managed job
directories. Existing cancellation and resume semantics remain authoritative.
