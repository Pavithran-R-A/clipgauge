# ClipGauge Troubleshooting

ClipGauge fails closed when a path, artifact, credential, runtime, or job state cannot be validated. Start with the exact error text and diagnostic ID shown by the app; do not bypass a blocked check by copying files into arbitrary directories.

## Preflight reports a blocked check

Open the preflight details and follow the remediation text. Common causes include missing `uv`, missing Python 3.12, insufficient free disk space for models, an unavailable FFmpeg runtime, a missing Ollama model, or an invalid Gemini configuration. Re-run preflight after correcting the local condition. A warning is not the same as a block, but it may indicate that a provider or optional feature will not work reliably.

## The pipeline does not start

From the repository root, confirm that the development path works independently:

```sh
cd pipeline
uv sync
uv run clipgauge --help
uv run clipgauge preflight --llm ollama
```

The desktop shell invokes `clipgauge`, not the legacy `publikclip` command. If the Python package was renamed in a partially updated checkout, remove and recreate only the project environment with `uv sync`; do not delete the managed job root while a migration or resumable job is in progress.

## A runtime or model download fails

ClipGauge verifies bounded downloads against the pinned manifest and preserves the last-known-good runtime where possible. Check network access, available disk space, and the diagnostic ID. Do not replace a failed artifact with an unverified download or edit the recorded SHA-256. Retry after the network condition is stable. A provider may also restrict a model by geography, authentication, or updated terms; in that case, use an available local alternative or wait for a project update.

## Gemini authentication fails

Re-enter the key through onboarding or the Gemini key modal. The key must be active and permitted for the selected API. ClipGauge sends the credential through an operation-scoped secret path and does not require it in a URL query parameter. Do not paste the key into an issue, log, screenshot, support bundle, or source file. If the key may have leaked, revoke it with the provider before continuing.

## Ollama is not detected

Confirm that Ollama is running on its local loopback endpoint and that at least one compatible chat model is installed. The app’s Ollama mode is intentionally loopback-only; it is not a generic remote-host configuration. Restart Ollama, pull the model again if its local manifest is incomplete, and rerun preflight. A small local model may produce less reliable humor or virality judgments; the UI labels these scores as local estimates.

## A job is stuck, cancelled, or only partly complete

A cancelled job is not automatically corrupt. Reopen it from the Sessions rail and use resume when the checkpoint is marked safe. If the app was terminated unexpectedly, the Rust lifecycle manager reconciles stale leases before allowing a new run. Duplicate active runs for the same job are rejected to avoid competing writers. If a checkpoint is invalid or corrupt, the app will require an earlier stage rather than trusting unverified output.

## A migration collision is reported

The legacy migration refuses to overwrite a destination file whose bytes differ from the legacy source. This is deliberate. Close the app, back up both directories, compare the conflicting file, and decide which copy to retain. The source under `~/.publikclip` is preserved, and no completed migration marker is written after a collision. Do not force-copy the directories over one another.

## Clips, captions, or camera framing look wrong

Confirm that the source file has a supported readable stream and that the selected runtime is complete. Inspect the Review screen’s clip ledger for detected signals, score adjustments, and stage provenance. Try a short local sample to separate source-specific behavior from a global runtime issue. Audio quality, speaker overlap, cuts, language, and model availability can materially affect transcription, diarization, laughter detection, and camera selection; ClipGauge does not guarantee identical results for every recording.

## Asset or export errors appear

The desktop bridge only exports a render artifact that is present in the managed job directory, contained within the expected job path, and recorded in the validated checkpoint. A path outside the managed root or a symlink escape is rejected. Keep source and output files in the app-managed paths and use the file picker or drag-and-drop rather than attempting to pass arbitrary filesystem paths to internal commands.

## Support bundles and privacy

Use **support bundle** from the Studio rail. The bundle contains sanitized metadata and redacted diagnostic tails; it excludes source media, raw transcripts, and known credential material. Review the archive before sharing because local filenames, operating-system details, job IDs, and provider names may still be present. Never attach the original job directory or credential-store export.

## Unsigned artifact warnings

The v0.1.0 Linux Debian artifact is unsigned. An unsigned package cannot establish publisher identity and should be obtained from a trusted source, inspected with `dpkg-deb`, and installed only at the user’s discretion. The updater is disabled because no signing key is configured. This release makes no claim about Windows/macOS artifacts, code signing, notarization, or hardware benchmarks.

## Reporting a reproducible issue

Include the ClipGauge version, operating system and architecture, selected scoring mode, stage name, diagnostic ID, and a redacted support bundle. Describe whether the source was a local file or URL and whether the issue is reproducible on a short sample. Remove personal URLs, usernames, tokens, raw transcripts, and private media before submitting.
