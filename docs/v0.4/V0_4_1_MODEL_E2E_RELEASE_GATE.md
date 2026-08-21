# ClipGauge v0.4.1 Model-Backed E2E Release Gate

**Overall status:** PASS for the completed production-default controlled qualification; BLOCKED for exact-tag GitHub publication until the new release job executes and its uploaded summary is verified.

## Completed controlled qualification

The real local qualification reused job `20260821-132437-f2ef91` and completed the pipeline with managed assets, real local inference, captions enabled, the normal `classic` caption preset, and 1080×1920 output. The final clip is H.264/AAC, 21.1 seconds, vertically oriented, nonzero in size, and records `captions_burned: true`. The final SHA-256 is `0ea8d7f9700f960722f8016787506ccd761b9d262eaf09e5739d6f5e098e7a32`.

## Exact-tag job contract

| Requirement | Status | Workflow evidence |
|---|---|---|
| Checkout exact release tag | PASS | `model-e2e-release` checks out `${{ env.RELEASE_TAG }}` with full history. |
| Install managed ASR/analysis/runtime/model assets | PASS | The job invokes explicit setup commands for `core:asr`, `core:analysis`, runtime, and the pinned local model. |
| Use ClipGauge Local | PASS | The run specifies the managed `clipgauge-local` provider and pinned model. |
| Run genuine speech fixture | PASS | The committed `pipeline/tests/fixtures/v041-jfk.flac` is used to build the controlled input. |
| Validate terminal and all stages | PASS | `scripts/validate-model-e2e.py` is invoked against JSONL and the job directory. |
| Validate production-default media | PASS | The validator requires positive duration, audio/video, 1080×1920 geometry, vertical aspect, and burned captions. |
| Upload compact evidence | PASS | JSONL, summary, fixture input, setup logs, and job identifier are uploaded with a retention limit. |
| Release metadata depends on gate | PASS | `release-metadata` lists `model-e2e-release` in `needs`. |
| Publication depends on gate | PASS | `release-publish` lists `model-e2e-release` in `needs` and verifies `MODEL_E2E_SUMMARY.json`. |
| Actual exact-tag runner result | BLOCKED | Requires the GitHub Actions release workflow to execute on the eventual immutable v0.4.1 tag. |

## Decision

The release design now prevents a tag from publishing when real managed-model qualification fails. The local PASS is not substituted for the exact-tag GitHub result; the latter remains BLOCKED until the workflow runs and its compact evidence is preserved.

## References

[1]: ../../scripts/validate-model-e2e.py "Deterministic model-E2E validator"
[2]: ../../pipeline/tests/fixtures/README.md "Fixture provenance"
[3]: ../../.github/workflows/release.yml "Exact-tag release workflow"
[4]: ../../v041-production-default-e2e-validation.md "Completed production-default qualification"
