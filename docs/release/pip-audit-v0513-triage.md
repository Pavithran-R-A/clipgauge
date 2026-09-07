# ClipGauge v0.5.13 Python advisory triage

Audit command: `uv run --with pip-audit pip-audit . --format=json`

Audit result: exit `1`; 16 findings in four packages.

Machine-readable output is preserved outside the repository at
`C:\Users\Pavithran R A\Documents\ClipGauge-v0.5.13-candidate\pip-audit-v0513.json`.

## Runtime evidence

- `torch==2.8.0` is direct. Model checkpoints enter through the verified-model registry. The three application checkpoint loaders use `torch.load(..., weights_only=True)` only after manifest and SHA-256 verification.
- `whisperx==3.8.6` is direct. `nltk==3.10.3` and `transformers==4.57.6` arrive through WhisperX.
- `lightning==2.6.5` arrives through `whisperx -> pyannote-audio -> lightning`. ClipGauge uses its vendored CAM++ diarization path, not the pyannote Lightning checkpoint loader.
- English alignment selects the verified torchaudio `WAV2VEC2_ASR_BASE_960H` asset. The WhisperX Hugging Face alignment branch is not selected. Offline flags are set for Hugging Face Hub and Transformers.
- The only NLTK call is WhisperX sentence splitting with an internal, allowlisted `punkt_tab` resource name. ClipGauge does not expose NLTK model-artifact paths.
- No application code calls `torch.jit.script`, `torch.linalg.lu`, `torch.rot90`, `torch.randn_like`, `torch.nn.utils.rnn.unpack_sequence`, `torch.lstm_cell`, Transformers Trainer checkpoint loading, X-CLIP conversion, LightGlue loading, or `save_pretrained`.

## Finding-level disposition

| Advisory | Package | Installed | Fix | Path | Reachability and affected path | Class | Action |
|---|---|---:|---|---|---|---|---|
| PYSEC-2025-206 / CVE-2025-55554 | torch | 2.8.0 | 2.9.0 | direct | `torch.nan_to_num(...).long()` is not called | B | retain lock; revisit with a compatible Torch stack |
| PYSEC-2025-204 / CVE-2025-55552 | torch | 2.8.0 | 2.9.0 | direct | `torch.rot90` plus `torch.randn_like` is not called | B | retain lock; revisit with a compatible Torch stack |
| PYSEC-2026-139 / CVE-2026-4538 | torch | 2.8.0 | none listed | direct | advisory text describes the 2.10.0 pt2 loader; that loader is not used | B | retain lock; monitor upstream clarification |
| PYSEC-2025-203 / CVE-2025-55551 | torch | 2.8.0 | 2.9.0 | direct | `torch.linalg.lu` is not called | B | retain lock; revisit with a compatible Torch stack |
| PYSEC-2025-194 / CVE-2025-3000 | torch | 2.8.0 | 2.13.0 | direct | `torch.jit.script` is not called | B | retain lock; revisit with a compatible Torch stack |
| PYSEC-2026-2286 / CVE-2026-24747 | torch | 2.8.0 | 2.10.0 | direct | `weights_only` loads are limited to hash-verified managed checkpoints | B | retain verified-model boundary; do not accept user checkpoints |
| CVE-2025-2999 / GHSA-vgrw-7cvw-pwgx | torch | 2.8.0 | 2.9.1 | direct | `torch.nn.utils.rnn.unpack_sequence` is not called | B | retain lock; revisit with a compatible Torch stack |
| CVE-2025-3001 / GHSA-qfhq-4f3w-5fph | torch | 2.8.0 | 2.10.0 | direct | `torch.lstm_cell` is not called | B | retain lock; revisit with a compatible Torch stack |
| PYSEC-2026-3740 / CVE-2026-81726 / GHSA-8mgp-746c-j5xp | nltk | 3.10.3 | none listed | `whisperx -> nltk` | only fixed `tokenizers/punkt_tab/<allowlisted-language>.pickle` loading is exercised | B | retain fixed resource names; monitor upstream patch |
| PYSEC-2026-3624 / CVE-2026-58659 / GHSA-qqmf-gpg7-g8gw | lightning | 2.6.5 | none listed | `whisperx -> pyannote-audio -> lightning` | no `LightningModule.load_from_checkpoint` path is used | B | retain vendored CAM++ path; monitor upstream patch |
| PYSEC-2025-217 / CVE-2025-14929 | transformers | 4.57.6 | none listed | `whisperx -> transformers` | X-CLIP checkpoint conversion is not used | B | retain offline, torchaudio alignment path |
| PYSEC-2026-2290 / CVE-2026-5241 / GHSA-fgcw-684q-jj6r | transformers | 4.57.6 | none listed | `whisperx -> transformers` | LightGlue loading is not used | B | retain offline, torchaudio alignment path |
| PYSEC-2026-2288 / CVE-2026-1839 / GHSA-69w3-r845-3855 | transformers | 4.57.6 | 5.0.0 | `whisperx -> transformers` | Transformers Trainer RNG-state loading is not used | B | retain lock; revisit with a compatible WhisperX stack |
| PYSEC-2026-2289 / CVE-2026-4372 / GHSA-29pf-2h5f-8g72 | transformers | 4.57.6 | 5.3.0 | `whisperx -> transformers` | `AutoModelForCausalLM.from_pretrained` is not used | B | retain offline, torchaudio alignment path |
| PYSEC-2026-2290 / CVE-2026-5241 / GHSA-fgcw-684q-jj6r | transformers | 4.57.6 | 5.5.0 | `whisperx -> transformers` | duplicate advisory record; LightGlue loading is not used | B | retain offline, torchaudio alignment path |
| CVE-2026-9856 / GHSA-xrqw-3rrv-vx5w | transformers | 4.57.6 | 5.10.0 | `whisperx -> transformers` | `save_pretrained` is not used | B | retain offline, torchaudio alignment path |

## Decision

No finding was ignored. No ML dependency was upgraded blindly. The findings are classified B because the affected APIs are unreachable through ClipGauge's current input and model trust boundaries. The raw audit remains non-zero and requires reassessment whenever the managed model-loading surface changes.
