# ClipGauge Stage 1A Protocol

## Scope

The Python sidecar uses JSON Lines for streamed `run` and `resume` operations. Progress events remain incremental. Each streamed operation emits **exactly one** `event: "terminal"` event after the job event and any progress events. The legacy `event: "result"` shape remains only for one-shot edit/Instagram commands; it is not the terminal contract for run/resume.

## Terminal shape

```json
{
  "event": "terminal",
  "protocol_version": 1,
  "ok": false,
  "job_id": "20260818-155237-c6b118",
  "stage": "ingest",
  "code": "YTDLP_DOWNLOAD_FAILED",
  "message": "yt-dlp could not process this video: ...",
  "retryable": true,
  "diagnostic_id": "diag-...",
  "exit_code": 1
}
```

`protocol_version`, `ok`, `code`, `message`, and `retryable` are always present. `job_id` is present after job creation. `stage` is present when the stage is known; the success stage is `pipeline`. `diagnostic_id` is present for unexpected failures and bridge-synthesized failures. `exit_code` is present when the Rust bridge observes a child exit code. Messages are safe, bounded, and redacted; tracebacks and credentials are retained only in redacted local diagnostic records.

## Codes

| Code family | Meaning | Retryability |
|---|---|---|
| `OK` | Full streamed pipeline completed | No |
| `INPUT_FILE_NOT_FOUND` | The requested local file does not exist | No |
| `INPUT_FILE_INVALID` | The local input is not a regular file | No |
| `INPUT_COPY_FAILED` | The source could not be copied into the managed job folder | Usually yes |
| `YTDLP_AUTH_REQUIRED` | The remote source requires authentication or access | User action required; retry after correction |
| `YTDLP_DOWNLOAD_FAILED` | Remote download/network/tool download failure | Yes |
| `YTDLP_METADATA_FAILED` | Metadata/extractor failure or invalid video URL | Usually yes after URL/tool correction |
| `STAGE_FAILED` | Typed stage failure without a more specific code | Usually yes |
| `INTERNAL_ERROR` | Unexpected Python exception captured at the protocol boundary | No automatic retry; use diagnostic ID |
| `PIPELINE_START_FAILED` | Rust could not start the sidecar | Yes after installation/environment correction |
| `PIPELINE_EXIT_WITHOUT_TERMINAL` | Rust observed child exit without the required terminal event | Yes; inspect diagnostic ID |

## Security rules

The protocol never contains Gemini or Pexels API keys, Meta app secrets, access tokens, full authorization headers, or secret-bearing URL query values. Python diagnostics are written below the job’s private `diagnostics/` directory with a bounded, redacted traceback and restrictive Unix permissions. Rust bridge diagnostics are bounded to the final stderr tail, redacted, and written below the managed application diagnostics directory.

## Consumer behavior

The React app treats `terminal` as authoritative for streamed runs. On success it loads job results. On failure it displays the safe message, typed code, and diagnostic ID when present. A legacy bare `exited` event is treated as an unsafe fallback message and is not emitted by the Stage 1A Rust bridge. The Rust bridge also synthesizes `PIPELINE_EXIT_WITHOUT_TERMINAL` if a child exits without producing the required terminal event.

## Compatibility boundary

The CLI retains human-readable non-JSON output and one-shot command JSON for existing edit/Instagram operations. The Stage 1A change intentionally does not make a broad CLI/package rename and does not claim cancellation support; cancellation is a later stage. The protocol is versioned so future terminal fields can be added without silently changing the meaning of existing codes.
