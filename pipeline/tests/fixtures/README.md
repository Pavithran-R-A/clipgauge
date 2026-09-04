# v0.4.1 model-backed E2E fixture

`v041-jfk.flac` is a small, genuine speech recording used only by the release qualification workflow. It was sourced from the MIT-licensed [collabora/WhisperLive](https://github.com/collabora/WhisperLive) project’s JFK speech fixture and is retained here to make the exact-tag acceptance gate reproducible without downloading user media.

The committed file is 1,152,693 bytes and has SHA-256 `63a4b1e4c1dc655ac70961ffbf518acd249df237e5a0152faae9a4a836949715`. The release workflow places this real speech over a generated solid-color video solely to satisfy ClipGauge’s candidate-window duration requirement; ASR, diarization, analysis, scoring, camera direction, caption burning, and rendering remain production code paths with real managed models and no mocks.

This fixture is not user data, does not contain credentials, and is not used by ordinary unit tests or application runtime code.

`clapping-esc50.wav` is a one-second excerpt from the ESC-50 `1-104089-A-22.wav` clapping recording. It is 441,044 bytes with SHA-256 `2b6ec14aafc6ed98c833c5c7e56780d283f3ceaea0d4c3c142b2f49fcc2fd215`. ESC-50 is released under CC BY 4.0; the source file is hosted at https://github.com/karolpiczak/ESC-50/blob/master/audio/1-104089-A-22.wav. The event cue gives the genuine speech fixture a deterministic editorial signal.
