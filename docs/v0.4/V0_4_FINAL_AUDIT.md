# ClipGauge v0.4.0 Final Audit

**Audit date:** 2026-08-21

**Current decision:** Implementation and Linux-controlled validation are complete. Publication remains conditional on the exact-tag PR/release workflow completing its required native jobs and secret/provenance gates.

## Executive conclusion

ClipGauge v0.4.0 closes the project-owned managed-runtime and creator-workflow gaps identified in the v0.3 audit. One consented Download Manager now represents runtime, speech, analysis, YouTube-compatibility, and local-model assets. FFmpeg is self-service; Silero VAD is explicitly managed and offline-ready; browser authentication is opt-in; YouTube compatibility owns portable Node.js and bgutil; Setup Center operations stream progress and support cancellation; and Simple mode hides implementation details without removing Advanced controls.

The first real model-backed E2E exposed an unrepresented WhisperX Silero VAD torch.hub download. That defect was fixed rather than waived. The next real run also exposed local Qwen runtime latency and startup-memory sensitivity; the managed runtime was bounded with reasoning disabled, one slot, and a 4096-token context. The corrected run completed every pipeline stage and produced a verified playable vertical MP4.

## Validation matrix

| Area | Result | Evidence |
|---|---|---|
| Python regression suite | PASS: 158 passed, one unknown-mark warning | `v040-python-tests.log` |
| Frontend tests | PASS: 12 tests | `v040-frontend-tests-npm.log` |
| Frontend production build | PASS | `v040-frontend-build-npm.log` |
| Rust tests | PASS: 33 passed | `v040-cargo-test.log` |
| Rust formatting | PASS | `v040-cargo-fmt.log` |
| Strict Clippy | PASS with `-D warnings` | `v040-cargo-clippy.log` |
| npm audit | PASS: 0 vulnerabilities | `v040-npm-audit.json` |
| pip-audit | Non-zero: 14 known findings in 3 ML-stack packages | `v040-pip-audit-nodeps.log`; documented in `V0_4_SECURITY_REVIEW.md` |
| cargo audit | Exit 0 with upstream GTK3/glib warnings/advisory | `v040-cargo-audit.log`; documented in `V0_4_SECURITY_REVIEW.md` |
| Version consistency | PASS for 0.4.0 | `scripts/check-version-consistency.py` |
| Real local model-backed E2E | PASS on isolated Linux home | `model-e2e-resume-static.jsonl`, job `20260821-132437-f2ef91` |
| Windows installer acceptance | Pending exact-tag native runner | `V0_4_WINDOWS_E2E.md` |
| YouTube live smoke | `ENVIRONMENT_BLOCKED`, not PASS | `V0_4_YOUTUBE_VALIDATION.md` |

## Model-backed E2E result

The final run reused verified managed assets in `/home/ubuntu/clipgauge-stage0/v040-e2e-home`, used the genuine `jfk-controlled-33s.mp4` speech fixture, and completed ingest, ASR, diarization, events, candidates, local Qwen scoring, camera, and render. The output is an H.264/AAC MP4 at 540×960, duration 21.1 seconds, with SHA-256 `667636a3b8c0744dfdcb161198426d9c2735c8ab9a0f7ffd0ce81cdb46f2f84b`. The 540×960 and ultrafast settings were explicit allow-listed validation overrides; production defaults remain captioned 1080×1920 and medium x264. The output’s FFprobe facts are preserved in `v040-e2e-media-facts.txt`.

## True-blocker review

| Specification blocker | Status |
|---|---|
| Manual FFmpeg installation required | RESOLVED by managed FFmpeg and fail-closed render setup |
| PO-token UI without implementation | RESOLVED by managed bgutil/Node supervisor and self-test |
| Large hidden model downloads | RESOLVED for inventoried ASR, Silero, alignment, NLTK, analysis, runtime, and GGUF assets |
| Future progress rows falsely complete | RESOLVED by streamed state/fraction/indeterminate rendering |
| Download UI lacks byte progress | RESOLVED by manager events and Setup Center display |
| Simple mode exposes raw internals | RESOLVED by Simple/Advanced provider mode |
| Existing v0.3 cache redownloaded | RESOLVED by migration and verified cache reuse |
| ClipGauge Local contract | RESOLVED by managed health/model/structured-completion checks and E2E scoring |
| Windows installer acceptance | PENDING exact-tag `windows-latest` workflow |
| Real vertical MP4 E2E | RESOLVED on Linux controlled fixture; Windows-specific acceptance remains separate |
| Deterministic tests | RESOLVED: Python/frontend/Rust gates pass |
| Secret scan/checksum/release metadata | Must be confirmed by CI and exact-tag release workflow before publication |

## Audit decision

The implementation candidate is suitable for PR and CI publication work. It is not yet permissible to describe v0.4.0 as published, Windows-accepted, checksum-verified, or advisory-free until the exact release workflow supplies those results. Historical tags v0.1.0 through v0.3.0 remain untouched.
