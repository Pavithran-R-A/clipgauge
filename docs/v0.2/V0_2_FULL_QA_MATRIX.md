# ClipGauge v0.2.0 full QA matrix

This matrix is the execution record for v0.2.0. A case is counted as passing only when its command or native workflow evidence is recorded; a skipped case is not counted as a pass.

| Perspective | Area | Verification | Evidence / status |
|---|---|---|---|
| Creator | Run local file | Ingest, checkpoints, scoring, camera, captions, render, review, export | Execute with synthetic Fixture A; record job ID and artifact checksums. |
| Creator | URL workflow | Validate URL and disclose video-host/network activity | Use invalid and supported URL fixtures; no claim of offline URL processing. |
| Creator | Edit loop | Suggest visuals, edit overlays, rerender, export | Run mocked provider visual plan plus Pexels-disabled path. |
| Creator | Recovery | Cancel, close, restart, resume, stale recovery | Exercise queue lifecycle and preserve provider snapshot. |
| New Windows user | Install | Install unsigned NSIS artifact and launch | Release workflow silent-install and launch smoke; SmartScreen warning documented. |
| New Windows user | Provider setup | Provider presets, custom endpoint, password field, Test Connection | Native UI smoke with mock/local endpoint where feasible. |
| Developer | Contracts | ProviderProfile, InferenceRequest/Result, capability levels, errors | `pipeline/tests/test_providers.py`; no live inference in mandatory CI. |
| Developer | Migration | Legacy Gemini/Ollama settings and jobs | `test_settings_migrates_legacy_modes_without_secrets` plus queue regression tests. |
| Privacy reviewer | Data flow | Dynamic Privacy Activity for local/cloud/text/vision paths | Review Tauri privacy payload and provider docs. |
| Privacy reviewer | Secrets | Vault-only credentials, no job/config/cache/support leakage | Rust secret tests, Python credential tests, secret scan. |
| Security reviewer | URL | Scheme, remote HTTP, query secret, redirects, TLS | Provider URL policy and redirect tests. |
| Security reviewer | Input | Traversal, symlinks, archive, edit schema, malformed provider config | Existing security suite plus provider contract tests. |
| Hostile tester | Provider failures | 401, 403, 404, 429, quota, 5xx, timeout, invalid JSON, invalid schema | Normalized error tests and bounded retry tests. |
| Hostile tester | Vision | Text-only model with frames, mandatory vision, image limit | Degraded signal and explicit `VISION_UNSUPPORTED` tests. |
| Offline/local user | Ollama | Loopback health, model listing, structured response, model unavailable | Mock API tests; no large model download in CI. |
| Offline/local user | LM Studio | Loopback `/models`, manual model entry, server stopped | Mock API tests; no large model download in CI. |
| Free-tier API user | Curated providers | Preset config, manual model, generic quota language | Official research document and mock contract tests. |
| Free-tier API user | Custom provider | Unknown OpenAI-compatible endpoint without source update | Custom profile tests and manual endpoint field. |
| Maintainer | Rebrand | Current UI/CLI/package/data names and classified legacy occurrences | `REBRAND_CLASSIFICATION.md`. |
| Maintainer | Dependencies | Python lock, frontend audit, Rust audit, secret scan | CI artifacts and audit log. |
| Release engineer | Native matrix | Linux, Windows x64, macOS arm64, macOS x86_64 | Required CI workflow evidence before merge/tag. |
| Release engineer | Publication | Tag identity, assets, checksum, SBOM, provenance, attestation | Release workflow and post-release verification evidence. |

## Synthetic fixtures

Fixture A is a generated, legally redistributable landscape conversational clip with speech, two visual areas, and a scene change. Fixture B uses a Unicode filename and parent path. Fixture C is a truncated copy of Fixture A. Fixture D is a generated no-audio or unusual-audio sample where the relevant stage can produce an actionable result. Random copyrighted downloads are not committed.

## Evidence rules

Mocked provider tests prove protocol and security behavior, not model quality. Native platform qualification proves packaging and launch behavior, not notarization or signing. Live provider smoke is optional and must report `SKIPPED` when owner-configured secrets are absent. Any failure remains a release blocker unless the specification explicitly classifies it as a documented non-blocker.
