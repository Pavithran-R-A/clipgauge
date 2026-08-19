# ClipGauge v0.1.1 Release-Engineering Closure Plan

## Purpose and invariants

This plan closes the independently reviewed release-engineering defects without redesigning ClipGauge, rewriting the analytical pipeline, rewriting Git history, moving or replacing the existing `v0.1.0` tag/release, or removing AGPL/upstream attribution. Work is performed on `release/v0.1.1-closure`, branched from the verified `origin/main` SHA `e589baf7c3c71c35e9e55e619cf7bdc54b780eb4`.

The existing upstream remote remains `https://github.com/Blueturboguy07/publikclip.git`. The audited upstream baseline remains `a53a359b985b1d2d666266062936cc186f02340b`. The v0.1.0 tag and release are historical and must remain unchanged.

## Requirement map

| Requirement | Files and implementation | Tests and CI jobs | Acceptance criterion |
|---|---|---|---|
| Version consistency | `app/package.json`, `app/package-lock.json`, `app/src-tauri/Cargo.toml`, `app/src-tauri/Cargo.lock`, `app/src-tauri/tauri.conf.json`, `pipeline/pyproject.toml`, `pipeline/clipgauge_pipeline/__init__.py`, `CHANGELOG.md`, `README.md`, About UI, `scripts/check-version-consistency.py` | Local script; dedicated `Version consistency` CI job; normal CI | Every authoritative source reports `0.1.1`; historical v0.1.0 references remain historical; mismatch fails deterministically |
| README and release language | `README.md`, `CHANGELOG.md`, `INSTALL.md`, `TROUBLESHOOTING.md`, `app/src/components/About.tsx` | Frontend typecheck/build/tests; documentation grep checks | Public release wording distinguishes Linux/Windows unsigned artifacts, macOS qualification, and signing/notarization limitations |
| Correct SBOM | `scripts/generate-release-metadata.py`, `scripts/validate-sbom.py`, `SBOM.cyclonedx.json` release output | SBOM validator CI job and release metadata job | Valid CycloneDX; dynamic peeled tag commit; v0.1.1; repository identity; no stale `c4f4a1f5cae4cdfc7b98c719387946896062e7fb`; first-party refs unique and versioned |
| Windows release artifact | `.github/workflows/release.yml` Windows job; existing `.github/workflows/windows.yml` remains normal CI | Windows pipeline tests, frontend build, Rust checks where practical, resource staging, NSIS build, silent install, launch/process smoke | Fresh `ClipGauge_0.1.1_Windows_x64_NSIS.exe` is built from the v0.1.1 tag, validated, uploaded as an immutable workflow artifact, and attached only after all mandatory gates pass |
| Native macOS CI | `.github/workflows/macos.yml` or gated release workflow matrix | Apple Silicon `aarch64-apple-darwin` and Intel `x86_64-apple-darwin` native jobs; Python/frontend/Rust checks; `.app` and optional DMG packaging | Both architectures are attempted on currently supported runners; success/failure and runner availability are reported accurately; no signing/notarization claim |
| Release workflow architecture | `.github/workflows/release.yml` | Linux, Windows, macOS ARM, macOS Intel, metadata/publish jobs | Build jobs upload immutable artifacts; publication depends on mandatory gates; tag/version mismatch hard-fails; no competing release publisher |
| Checksums | Release metadata job and `SHA256SUMS` | Download-back verification | Manifest is generated from exact final assets and every referenced file is attached; public downloads reproduce hashes |
| Provenance and attestation | `RELEASE_PROVENANCE.md`, optional GitHub artifact-attestation step | Attestation verification where supported; explicit unavailable limitation otherwise | Human-readable provenance is not confused with SHA-256, code signing, or cryptographic attestation; no fabricated success |
| Release immutability | Repository setting inspection and release publication strategy | `gh api`/release inspection | If immutable releases are enabled, draft-first publication is used; if owner-only, limitation and exact Settings path are documented |
| Workflow security | All `.github/workflows/*.yml` | Permissions and action review; secret scan | Normal CI is read-only; release write permissions are scoped to publishing; third-party actions are reviewed and pinned where practical |
| PR validation and merge | GitHub PR from `release/v0.1.1-closure` to `main` | All mandatory PR workflows | PR title exactly `release: close ClipGauge v0.1.1 packaging and provenance`; red jobs are repaired before merge |
| Tag and public release | Annotated `v0.1.1` tag after verified merge; release notes and assets | Post-merge main CI, tag release CI, post-release public verification | Tag points to exact verified main commit; release is `ClipGauge v0.1.1`; v0.1.0 remains untouched |
| Closure report and bundle | `CLIPGAUGE_V0_1_1_RELEASE_CLOSURE_REPORT.md`, `CLIPGAUGE_V0_1_1_RELEASE_CLOSURE_BUNDLE.zip` | ZIP integrity and SHA-256 | Report contains required source/version/platform/SBOM/checksum/attestation/immutability/CI/licensing/limitations sections; bundle excludes credentials, caches, and private material |

## Version sources

The deterministic checker will inspect the frontend manifest and lockfile, Rust manifest and lockfile package entry, Tauri configuration, Python manifest, Python package constant, and required current-release documentation. It will compare only authoritative current-release values and will not fail on historical changelog entries or references to the preserved v0.1.0 release.

## Release acceptance gates

The v0.1.1 release may be tagged only when the closure branch has a clean tree, all version sources agree, local tests pass, PR CI is green, Linux and Windows release builds are fresh from the release source, both macOS architecture jobs are successful or their precise availability limitation is documented, secret scanning is green, the SBOM validator is green, and the release workflow has no unverified artifact path assumptions.

The release publication job must download the immutable Linux, Windows, and any explicitly selected macOS artifacts from workflow transfer, generate checksums from those exact files, generate and validate SBOM/provenance, and attach only the final validated assets. Post-publication verification must download assets from the public release and independently recheck hashes, metadata, tag/source identity, and signing-status labels.

## Execution commands

The local verification baseline is:

```text
python3 scripts/check-version-consistency.py
python3 scripts/validate-sbom.py <generated-sbom> --tag v0.1.1
cd pipeline && uv run pytest -q
cd ../app && npm ci && npm run build && npm test
cd src-tauri && cargo fmt -- --check && cargo test && cargo clippy -- -D warnings
```

Release workflow runs are monitored with the GitHub CLI. No credential values are printed or stored in the repository. Any owner-only limitation, such as enabling release immutability or providing Apple/Windows signing credentials, is documented rather than represented as success.
