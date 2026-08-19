# ClipGauge Notice

**ClipGauge v0.1.0** is a modified, local-first desktop AI video clipper distributed under the **GNU Affero General Public License, version 3 or any later version (AGPL-3.0-or-later)**. The complete license text is in [`LICENSE`](LICENSE).

Copyright © 2026 Pavithran R A and contributors.

ClipGauge is not the original upstream project. It is a modified derivative of [Blueturboguy07/publikclip](https://github.com/Blueturboguy07/publikclip), based on upstream commit [`a53a359b985b1d2d666266062936cc186f02340b`](https://github.com/Blueturboguy07/publikclip/commit/a53a359b985b1d2d666266062936cc186f02340b). The source tree preserves upstream attribution and Git history where available. See [`ORIGIN.md`](ORIGIN.md) for the modification record and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for dependency, model, font, and binary notices.

ClipGauge modifications include the Rust-owned job lifecycle and cancellation model, path and artifact security boundaries, runtime supply-chain verification, credential handling, edit-schema validation, resource preflight, explainability and privacy tooling, the ClipGauge application identity, and the `.clipgauge` data root. These changes are maintained as a derivative work; they do not remove or weaken the AGPL obligations applying to the covered source.

## Distribution notes

ClipGauge is intended to operate locally and has no default telemetry or mandatory cloud backend. Optional provider integrations, source URL downloads, runtime/model downloads, and user-selected LLM or social integrations can make network requests; those behaviors are documented in the application’s privacy activity view and release documentation.

The v0.1.0 Linux artifact is unsigned. No signing certificate, notarization, trademark clearance, or Windows/macOS release result is claimed by this notice.

## License text and source offer

For the rights, conditions, and corresponding-source requirements that apply to this work, read [`LICENSE`](LICENSE) and the source in this repository. Questions about a specific third-party component should be checked against the component’s own license and source link listed in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## References

[1]: https://www.gnu.org/licenses/agpl-3.0.html "GNU Affero General Public License v3"
[2]: https://github.com/Blueturboguy07/publikclip "Upstream publikclip repository"
[3]: https://github.com/Blueturboguy07/publikclip/commit/a53a359b985b1d2d666266062936cc186f02340b "Audited upstream baseline commit"
