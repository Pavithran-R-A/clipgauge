# ClipGauge v0.5.12 Zero-Clip Forensics

Diagnostic: `diag-440e476c68084179`

Job: `20260907-181848-1eea09`

Profile root: `C:\Users\Pavithran R A\.clipgauge`

The preserved job used local scoring. Its source identity remains private.

## Stage ledger

| Stage | Checkpoint | Schema | Database | Outputs | Device or backend | Result |
|---|---:|---:|---|---:|---|---|
| ingest | yes | 1 | done | media and probe | unknown | cached on recovery |
| ASR | yes | 2 | done | 196 words | CUDA transcription, CPU alignment | recovery completed |
| diarize | yes | 3 | done | turns and speakers | unknown | recomputed |
| events | yes | 4 | done | timeline and curves | CPU | recomputed |
| candidates | yes | 15 | done | 5 candidates | unknown | recomputed |
| score | yes | 24 | done | 0 clips | local provider | recomputed |
| camera | yes | 7 | done | 0 trajectories | unknown | empty input accepted |
| render | no | 7 | failed | 0 outputs | unknown | generic empty-render failure |

## Counts

- Candidate count: `5`.
- Scored candidate count: `5`.
- GOOD count: `0`.
- STRONG count: `0`.
- `score.data.clips` count: `0`.
- Camera trajectory count: `0`.
- Render attempted count: `0`.
- Render output count: `0`.
- Borderline candidate count: `5`.
- Borderline reason: `STRONG_RECOMMENDATION_REQUIRED`.

## Root cause

Candidate generation worked. Scoring worked. The five candidates were all
structurally valid but below the recommendation bar. The score checkpoint
therefore contained no finalists. Camera accepted that empty collection and
produced no trajectories. Render silently skipped missing trajectory entries,
then raised `No clips were rendered.`. The final error hid the successful
analytical zero-recommendation result.

The real job did not prove a scoring-language regression. Its transcript
language was English. Tamil and unsupported-language behavior now has separate
regression coverage.

## Recovery evidence

The first ASR attempt failed with CUDA out-of-memory during alignment. The
recovered run completed transcription, CPU alignment, diarization, events,
candidate generation, and scoring. The prior ingest checkpoint was reused.

## Required v0.5.13 behavior

- Zero finalists return `SUCCESS_NO_RECOMMENDATIONS`.
- Terminal code is `NO_RECOMMENDED_CLIPS`.
- Camera and render do not run on an empty finalist set.
- Non-empty finalist sets require complete trajectory coverage.
- Missing coverage raises `CAMERA_TRAJECTORY_MISSING`.
- Diagnostics retain sanitized counts and rejection reasons.
