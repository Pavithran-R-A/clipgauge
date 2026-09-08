# ClipGauge v0.5.14 long-form DSP qualification

## Root cause

The failed Windows job `20260908-110138-5cabf7` reached Events and attempted
the old full-recording FFT operand. The diagnostic recorded a NumPy allocation
of 2.39 GiB for `(100157, 3200)` float64 samples. The UI stayed on
“Fusing event timeline…” while that allocation failed.

v0.5.14 processes bounded frame blocks. RMS, spectral flux, progress, and
short-input handling keep the event semantics while avoiding duration-sized
FFT operands. PANNs and the optional laughter specialist also process bounded
audio chunks. Diarization reads each speech window directly from the WAV.

## Reproducible matrix

Run from `pipeline`:

```text
python benchmark_long_form.py
```

The benchmark uses zero-filled streamed chunks. It measures the old operand
formula and wraps the real FFT only to record the largest input operand.

| Source duration | Old FFT operand | Bounded FFT operand | Curve points | Elapsed |
| ---: | ---: | ---: | ---: | ---: |
| 5 minutes | 0.072 GiB | 12.5 MiB | 3,001 | 0.19 s |
| 30 minutes | 0.429 GiB | 12.5 MiB | 18,001 | 1.05 s |
| 1 hour | 0.858 GiB | 12.5 MiB | 36,001 | 2.38 s |
| 3 hours | 2.575 GiB | 12.5 MiB | 108,001 | 12.61 s |
| 6 hours | 5.150 GiB | 12.5 MiB | 216,001 | 24.50 s |

The benchmark completed without duration-sized allocations. The real failed
Windows diagnostic remains the production incident evidence.

## Resume and storage behavior

Resume keeps valid ingest, ASR, and diarization checkpoints. Events uses a new
schema and recomputes only the failed stage. Each run emits a disk-space
warning below 4 GiB free; the warning points to Setup & Storage and does not
delete sessions or source media.
