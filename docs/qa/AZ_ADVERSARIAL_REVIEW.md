# ClipGauge A-to-Z Adversarial Review and Bug Reproductions

## Skeptical creator

**Question:** Why use ClipGauge instead of editing manually?  
**Observed answer:** The implementation provides local ingest, audio/speaker/laughter signals, scored clip candidates, active-speaker camera direction, caption rendering, an explainable ledger, provider-neutral scoring, checkpoints, resume, and bounded desktop integration. Those claims are supported by source and deterministic tests. The audit did not complete a real generated clip, so it does not claim observed output quality or time savings.

## Broke creator

**Question:** I cannot pay for any AI API.  
**Observed answer:** Ollama and LM Studio are implemented as local options, and the onboarding/provider documentation does not require a subscription. On this host neither local runtime was installed, so local inference was not live-proven. Cloud free-tier language is conservative and does not promise permanent or unlimited access. No automatic cloud failover was observed.

## Privacy-sensitive creator

**Question:** I do not want my video uploaded.  
**Observed answer:** The local-first path keeps source media and job data under `.clipgauge`; privacy summaries distinguish local loopback providers from external cloud endpoints and identify when transcript/context/frames may leave the device. URL downloads, model downloads, Pexels, Meta, and cloud inference are separate network activities. The audit verified source/static behavior and provider contracts, but did not perform a packet-capture or interactive Tauri privacy-flow session.

## Hostile tester

The fresh review exercised missing paths, zero-byte and corrupt media, audio-only and no-audio media, Unicode and spaced paths, unsupported provider URLs, remote HTTP approval requirements, embedded-credential rejection, redirect safety, cache isolation, malformed provider responses, authentication failure normalization, unsupported custom auth, provider model-listing failure, malformed editor payloads, impossible edit bounds, invalid overlay source/animation/timeline/size, checkpoint corruption, artifact mutation, path traversal, symlink boundaries, and no-secret serialization. Structured errors were emitted for the tested normal failures; no raw Python traceback or Rust panic was shown at the CLI boundary for those cases.

## Confirmed findings

| ID | Severity | Reproduction | Observed result | Recommended action |
|---|---|---|---|---|
| AZ-001 | MEDIUM | `cd app/src-tauri && cargo clippy --all-targets --all-features -- -D warnings` | Exit 101: `items_after_test_module`, unused exported `redact_with_secrets`, and widened provider-aware command argument-count warnings. | Refactor/helper annotation or targeted API design cleanup in v0.2.1; rerun full gates. Do not weaken unrelated lint coverage. |
| AZ-002 | LOW | `uv run clipgauge --version` | Argparse says the required `cmd` argument is missing; no documented version option exists. | Add a conventional `--version` flag or document the authoritative version command in v0.2.1. |
| AZ-003 | MEDIUM | `cargo audit` | Exit 0 with 17 warnings, including unmaintained GTK3 bindings and unsound `glib` RUSTSEC-2024-0429. | Review Tauri/GTK dependency path and upgrade or document risk in v0.2.1. |

The findings were not fixed on the immutable v0.2.0 tag. The QA branch contains evidence and recommendations only.

## Representative error quality

The missing-file CLI case produced a structured `INPUT_FILE_NOT_FOUND` terminal event with a clear absolute source path and no traceback. No-audio produced an actionable speech prerequisite message. Provider credential absence produced `AUTH_INVALID` or a no-configured-credential message. The redaction/protocol tests passed for unexpected exceptions and diagnostic IDs. Absolute paths remain visible in some local file errors because they help identify the selected input; secrets and authorization material are not included.
