# macOS Runner Research for ClipGauge v0.1.1

This note records the external sources used to choose native qualification labels and bundle commands. It is release provenance support, not a claim that a macOS build has completed successfully.

| Source | Finding used |
|---|---|
| [GitHub-hosted runners reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) | Public repositories have standard GitHub-hosted macOS runners including Apple Silicon arm64 and Intel x86_64 classes; the official reference documents arm64 limitations and distinguishes Intel static UDID behavior. |
| [GitHub Actions macOS 15 Intel runner announcement](https://github.com/actions/runner-images/issues/13045) | GitHub introduced `macos-15-intel` for Intel x86_64 qualification and identified it as the last available Intel image family, with availability stated through August 2027 in the source issue. |
| [Tauri 2 macOS application bundle documentation](https://v2.tauri.app/distribute/macos-application-bundle/) | Tauri documents `tauri build --bundles app` for a native `.app` bundle and explains that bundle identity/version/resources are represented in `Info.plist` and the `.app` contents. |

The workflow therefore attempts `macos-latest` with `aarch64-apple-darwin` and `macos-15-intel` with `x86_64-apple-darwin`. Native qualification checks inspect the `.app` bundle identifier, version, executable, and packaged `clipgauge_pipeline` resources. The workflow does not claim signing, notarization, or consumer-ready macOS distribution.
