# v0.5.4 Python dependency VEX

Audit basis: `pip-audit` against the Windows 3.12 environment on
2026-09-02. It reported 27 raw records, 22 unique advisory IDs, and three
packages: Lightning 2.6.5, NLTK 3.10.2, and Transformers 4.57.6.

The older record count was 14. It is stale. Duplicate records remain listed
below where the audit emitted them. Two Transformers 2290 records are aliases
of one advisory with different reported fix versions. The CUDA Torch
wheel is `2.8.0+cu126`; the Windows audit did not emit Torch records for that
local-version build. The lock still retains the reviewed Torch 2.8.0 advisory
coverage from the earlier platform-neutral audit.

A project-environment audit on 2026-09-10 reported 12 records across four packages:
Lightning 2.6.5, NLTK 3.10.3, PyTorch Lightning 2.6.5, and Transformers
4.57.6. The records below remain reachability-reviewed. The audit is clean
only when these documented advisory IDs are explicitly ignored; the raw
audit must remain visible and non-zero.

The current host-global audit is separate. On 2026-09-11, the installed
Python 3.13 `pip-audit --local` reported 40 records across Pillow 11.3.0,
pip 26.1.1, and uv 0.11.14. That executable is outside the project’s locked
Python 3.12 environment. The project lock pins Pillow 12.3.0 and does not
declare pip or uv as runtime dependencies. `pip-audit --locked` does not
recognize `pipeline/uv.lock`, so this audit does not claim a locked result.

ClipGauge imports these packages through WhisperX and its analysis stack. Its
managed loading path verifies asset identity, size, and SHA-256 first. Model
metadata rejects repository redirects, URLs, remote code, and trust flags.
WhisperX uses local-only managed assets. No vulnerable loader below receives
attacker-controlled repository or checkpoint metadata.

| Advisory ID | Package/version | Alias or duplicate relationship | Previous VEX | Reachability in ClipGauge | Status |
|---|---|---|---|---|---|
| `PYSEC-2026-3624` | lightning 2.6.5 | `CVE-2026-58659` | existing | No Lightning checkpoint loader is called. | NOT_AFFECTED |
| `PYSEC-2026-3736` | nltk 3.10.2 | `CVE-2026-79674`, `GHSA-3gq4-3j92-5w49` | new | No LinThesaurus corpus reader is used. | NOT_AFFECTED |
| `PYSEC-2026-3739` | nltk 3.10.2 | `CVE-2026-81724`, `GHSA-cw6x-m8jw-qmrh` | new | No FeatStruct reader handles user input. | NOT_AFFECTED |
| `PYSEC-2026-3738` | nltk 3.10.2 | `CVE-2026-81722`, `GHSA-ww6m-cw3f-q94g` | new | PorterStemmer is not used on user tokens. | NOT_AFFECTED |
| `PYSEC-2026-3735` | nltk 3.10.2 | `CVE-2026-79657`, `GHSA-x99w-6fgc-pmfw` | new | No NLTK pickle loader is used. | NOT_AFFECTED |
| `PYSEC-2026-3737` | nltk 3.10.2 | `CVE-2026-79676`, `GHSA-p4rw-rvv2-7xwr` | new | No affected corpus reader is used. | NOT_AFFECTED |
| `PYSEC-2026-3741` | nltk 3.10.2 | `CVE-2026-81727`, `GHSA-f794-5jv7-7672` | new | NLTK Downloader is not called at runtime. | NOT_AFFECTED |
| `PYSEC-2026-3740` | nltk 3.10.2 | `CVE-2026-81726`, `GHSA-8mgp-746c-j5xp` | new | No affected model-artifact API is used. | NOT_AFFECTED |
| `PYSEC-2026-3733` | nltk 3.10.2 | `CVE-2026-78682`, `GHSA-6ww7-3frv-cqxh` | new | Runtime data is local and preverified. | NOT_AFFECTED |
| `PYSEC-2026-3748` | nltk 3.10.2 | `CVE-2026-78681`, `GHSA-97qj-x29f-37w7` | new | No affected XML parser path is used. | NOT_AFFECTED |
| `PYSEC-2026-3751` | nltk 3.10.2 | `CVE-2026-80206`, `GHSA-w3v8-gmh9-3wv7` | new | No user-controlled tgrep pattern exists. | NOT_AFFECTED |
| `PYSEC-2026-3749` | nltk 3.10.2 | `CVE-2026-79675`, `GHSA-m4rf-3fr8-xwx3` | new | No affected JVM option path exists. | NOT_AFFECTED |
| `PYSEC-2026-3752` | nltk 3.10.2 | `CVE-2026-81725`, `GHSA-8mpw-7fpc-4gqj` | new | No affected NLTK parser path exists. | NOT_AFFECTED |
| `CVE-2026-78680` | nltk 3.10.2 | `GHSA-6hwm-xvph-95vm` | new | No affected NLTK runtime path exists. | NOT_AFFECTED |
| `CVE-2026-12876` | nltk 3.10.2 | `GHSA-ff5c-cp5c-9wjf` | new | No affected NLTK parser path exists. | NOT_AFFECTED |
| `CVE-2026-81723` | nltk 3.10.2 | `GHSA-vp2x-qp44-57v7` | new | No affected NLTK parser path exists. | NOT_AFFECTED |
| `CVE-2026-71513` | nltk 3.10.2 | `GHSA-5gh2-94qg-qppq` | new | No affected NLTK runtime path exists. | NOT_AFFECTED |
| `PYSEC-2025-217` | transformers 4.57.6 | `CVE-2025-14929` | existing | X-CLIP conversion is absent. | NOT_AFFECTED |
| `PYSEC-2026-2290` | transformers 4.57.6 | `CVE-2026-5241`, `GHSA-fgcw-684q-jj6r` | existing | LightGlue and arbitrary repository loading are absent. | NOT_AFFECTED |
| `PYSEC-2026-2288` | transformers 4.57.6 | `CVE-2026-1839`, `GHSA-69w3-r845-3855` | existing | Trainer and RNG-state loading are absent. | NOT_AFFECTED |
| `PYSEC-2026-2289` | transformers 4.57.6 | `CVE-2026-4372`, `GHSA-29pf-2h5f-8g72` | existing | Alignment uses a pinned local asset and cache-only loading. | MITIGATED |
| `PYSEC-2026-2290` | transformers 4.57.6 | duplicate of the row above; audit reported fix 5.5.0 | existing | No additional execution path. | DUPLICATE |
| `PYSEC-2026-3929` | transformers 4.57.6 | `CVE-2026-9856`, `GHSA-xrqw-3rrv-vx5w` | new | Affected loader path is absent. | NOT_AFFECTED |
| `PYSEC-2026-3967` | pytorch-lightning 2.6.5 | `CVE-2026-58659` | new | ClipGauge does not call Lightning checkpoint loaders. | NOT_AFFECTED |

## Lock-only Torch coverage

The platform-neutral lock review retains the earlier Torch records for
`2.8.0`: `PYSEC-2025-206`, `PYSEC-2025-204`, `PYSEC-2026-139`,
`PYSEC-2025-203`, `PYSEC-2025-194`, `PYSEC-2026-2286`, `CVE-2025-2999`,
and `CVE-2025-3001`. They cover absent tensor operations and verified
weights-only managed loading. No Torch version upgrade was claimed here.

The remaining package advisories require coordinated WhisperX validation before
upgrading. No record is marked fixed by reachability alone. A future audit must
reopen this gate if a listed loader becomes reachable.
