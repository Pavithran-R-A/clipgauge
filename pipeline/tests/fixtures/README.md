# v0.4.1 model-backed E2E fixture

`v041-jfk.flac` is a small, genuine speech recording used only by the release qualification workflow. It was sourced from the MIT-licensed [collabora/WhisperLive](https://github.com/collabora/WhisperLive) project’s JFK speech fixture and is retained here to make the exact-tag acceptance gate reproducible without downloading user media.

The committed file is 1,152,693 bytes and has SHA-256 `63a4b1e4c1dc655ac70961ffbf518acd249df237e5a0152faae9a4a836949715`. The release workflow places this real speech over a generated solid-color video solely to satisfy ClipGauge’s candidate-window duration requirement; ASR, diarization, analysis, scoring, camera direction, caption burning, and rendering remain production code paths with real managed models and no mocks.

This fixture is not user data, does not contain credentials, and is not used by ordinary unit tests or application runtime code.
