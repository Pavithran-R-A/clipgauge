# ClipGauge Third-Party Notices

This notice records the third-party code, model weights, fonts, and optional binaries used or adapted by ClipGauge v0.1.0. It is a concise inventory, not a replacement for each component’s complete license text. The repository’s [`VENDORED-LICENSES.md`](VENDORED-LICENSES.md) contains the underlying project inventory and the source tree retains applicable attribution headers.

## Adapted and vendored code

| Component | Stated license | ClipGauge use | Source |
|---|---|---|---|
| `clip-forge` | MIT | Adapted managed yt-dlp, camera detection/tracking, and LR-ASD processing patterns | [JeremySNR/clip-forge](https://github.com/JeremySNR/clip-forge) |
| `clippyme` | MIT | Vendored crop-path smoothing and AutoFlip-inspired reframe operations | [fralapo/clippyme](https://github.com/fralapo/clippyme) |
| `openshorts` | MIT for the used project material; its excluded cloud material is proprietary | Adapted render command architecture, crop rounding, punch-in envelope, encoder tiering, and metadata scrubbing | [mutonby/openshorts](https://github.com/mutonby/openshorts) |
| `whisperX` 3.8.6 | BSD-2-Clause | Pinned dependency for transcription/diarization and adapted word-speaker assignment | [m-bain/whisperX](https://github.com/m-bain/whisperX) |
| `opensource-clipping` | MIT | Adapted two-pass canonical-position diarization fusion | [NaufalRizqullah/opensource-clipping](https://github.com/NaufalRizqullah/opensource-clipping) |
| `supoclip` | AGPL-3.0 | Adapted caption Dialogue-redraw and style-preset approach | [FujiwaraChoki/supoclip](https://github.com/FujiwaraChoki/supoclip) |
| `ViralMint` | AGPL-3.0 | Adapted punctuation, pause, and budget chunking rule | [openclaw-easy/ViralMint](https://github.com/openclaw-easy/ViralMint) |
| `laughter-detection` | MIT | Vendored laughter model and segmentation inference recipe | [jrgillick/laughter-detection](https://github.com/jrgillick/laughter-detection) |
| `audioset_tagging_cnn` / PANNs | MIT | Vendored Cnn14 inference subset and AudioSet labels | [qiuqiangkong/audioset_tagging_cnn](https://github.com/qiuqiangkong/audioset_tagging_cnn) |
| `3D-Speaker` CAM++ | Apache-2.0 | Vendored CAM++ model definition and layers | [modelscope/3D-Speaker](https://github.com/modelscope/3D-Speaker) |
| `autoclip` | MIT | Adapted intersection-over-union span deduplication pattern | [artbyjazi/autoclip](https://github.com/artbyjazi/autoclip) |

## Runtime-fetched model weights

The following weights are downloaded at runtime when required by local processing. ClipGauge does **not** redistribute these weight files in the source repository or the unsigned v0.1.0 Linux artifact. Users must review the provider’s current terms for their use case.

| Weight or checkpoint | Stated license | Runtime source |
|---|---|---|
| Whisper large-v3-turbo (CTranslate2) | MIT | Hugging Face via faster-whisper |
| wav2vec2 alignment (English) | Apache-2.0 | torchaudio / Hugging Face via whisperX |
| Silero VAD | MIT | Via whisperX `vad_method="silero"` |
| CAM++ `campplus_cn_common.bin` | Apache-2.0 | [FunASR CAM++ on Hugging Face](https://huggingface.co/funasr/campplus) |
| PANNs Cnn14_DecisionLevelMax | MIT (checkpoint per the upstream repository) | [Zenodo record 3987831](https://zenodo.org/record/3987831) |
| jrgillick laughter checkpoint | MIT | [laughter-detection repository](https://github.com/jrgillick/laughter-detection) |
| LR-ASD frontend/backend ONNX | MIT | Parity-preserving exports associated with [Junhua-Liao/LR-ASD](https://github.com/Junhua-Liao/LR-ASD) and clip-forge |
| UltraFace RFB-320 ONNX | MIT | [Ultra-Light-Fast-Generic-Face-Detector-1MB](https://github.com/Linzaer/Ultra-Light-Fast-Generic-Face-Detector-1MB) via clip-forge |
| speechbrain SER wav2vec2-IEMOCAP | Apache-2.0 for the stated code/weights | [SpeechBrain](https://huggingface.co/speechbrain) |

## Fonts

The repository bundles fonts under the SIL Open Font License 1.1 as recorded in [`VENDORED-LICENSES.md`](VENDORED-LICENSES.md): **Anton, Archivo Black, Inter, Public Sans, and Martian Mono**. The applicable OFL text is distributed alongside the font files under the captions-fonts directory. The font names and notices remain subject to their respective upstream font projects.

## Optional runtime binaries and services

The managed runtime can fetch pinned yt-dlp and FFmpeg artifacts according to `pipeline/runtime-manifest.json`. yt-dlp is distributed under its upstream license; FFmpeg builds may be GPL-licensed depending on the selected build, as noted in the repository inventory. ClipGauge does not claim to redistribute or relicense third-party binaries beyond the terms that apply to each selected artifact.

Optional Gemini, Ollama, Pexels, Instagram, and source-URL integrations are user-selected services rather than bundled third-party code. Their credentials, provider terms, and network behavior are outside the ClipGauge license and are described in the application privacy activity view.

## Deliberately excluded material

ClipGauge deliberately does not use the unresolved `supoclip` `THEBOLDFONT.ttf`, source trees without a license file, Remotion company-license material, the research-only NRC-VAD lexicon, research-only laughter weights, non-commercial emotion/audio checkpoints, or the proprietary `openshorts/cloud/` material. These exclusions are recorded to make the release boundary explicit.

## References

[1]: https://www.gnu.org/licenses/agpl-3.0.html "GNU Affero General Public License v3"
[2]: https://scripts.sil.org/OFL "SIL Open Font License"
[3]: https://github.com/Blueturboguy07/publikclip "Upstream project and inventory context"
