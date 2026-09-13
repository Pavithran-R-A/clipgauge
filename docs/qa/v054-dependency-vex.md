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

On 2026-09-12, a fresh project-environment audit reported 17 raw records
across Torch 2.8.0, NLTK 3.10.3, and Transformers 4.57.6. This includes
three duplicate Transformers records and eight Torch records that are
reported by the current PyPI advisory feed. The raw audit remains non-zero.
The reachability review below covers the newly emitted NLTK and Torch IDs;
the Transformers records retain their existing review. No dependency upgrade
is claimed without coordinated WhisperX and CUDA-stack qualification.

On 2026-09-13, the current project virtual environment was audited again.
The raw result reported nine advisory records across NLTK 3.10.3 and
Transformers 4.57.6. Torch 2.8.0+cu126, torchaudio 2.8.0+cu126,
torchvision 0.23.0+cu126, and the local ClipGauge package were skipped because
they are not published as directly auditable PyPI distributions. The current
raw audit remains non-zero; the reachability conclusions below remain the
security-owner review boundary.

ClipGauge imports these packages through WhisperX and its analysis stack. Its
managed loading path verifies asset identity, size, and SHA-256 first. Model
metadata rejects repository redirects, URLs, remote code, and trust flags.
WhisperX uses local-only managed assets. No vulnerable loader below receives
attacker-controlled repository or checkpoint metadata.

A current source reachability check found no direct use of the reported Torch
tensor, JIT, or recurrent-cell operations. The only direct Torch checkpoint
loads use `weights_only=True` and verified local paths in the diarization,
PANNs, and laughter model loaders. No direct Transformers import or model
repository loader exists in first-party ClipGauge code.

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
`PYSEC-2025-203`, `PYSEC-2025-193`, `PYSEC-2025-194`,
`PYSEC-2025-195`, `PYSEC-2026-2286`, `CVE-2025-2999`,
`CVE-2025-3000`, and `CVE-2025-3001`. They cover absent tensor and
checkpoint operations, plus verified weights-only managed loading. No Torch
version upgrade was claimed here.

The remaining package advisories require coordinated WhisperX validation before
upgrading. No record is marked fixed by reachability alone. A future audit must
reopen this gate if a listed loader becomes reachable.

## v0.5.16 exact outstanding-finding table

This table reflects the current locked project environment on 2026-09-13.
`pip-audit -l --format=json` returned nine raw records. Duplicate rows remain
visible because they are separate audit records. Advisory severity comes from
the reviewed GitHub or OSV record where available. All Python findings are
transitive runtime dependencies; none was introduced by v0.5.16. The current
application uses WhisperX local-only managed assets and does not expose the
affected arbitrary model-loading APIs.

| Ecosystem | Package | Installed | Advisory / CVE / GHSA | Severity | Direct or transitive | Introduced by v0.5.16? | Runtime, dev, or build-only | Reachable from shipped product? Evidence | Fixed version | Upgrade possible? | Why not upgraded | Current mitigation | Recommended disposition |
|---|---|---:|---|---|---|---|---|---|---|---|---|---|---|
| pip | nltk | 3.10.3 | PYSEC-2026-3740 / CVE-2026-81726 / GHSA-8mgp-746c-j5xp | High, CVSS 8.3 v4 | Transitive via WhisperX | No | Runtime | No. ClipGauge uses fixed local tokenizer resources; affected model-artifact APIs are absent. | None | No | Upstream lists no patched version. | Fixed resource names; managed assets verify before loading. | Retain VEX; owner review only if raw runtime advisories require acceptance. |
| pip | transformers | 4.57.6 | PYSEC-2025-217 / CVE-2025-14929 | High, CVSS 7.8 | Transitive via WhisperX | No | Runtime | No. X-CLIP conversion is not imported or called. | None | No | No fix listed; coordinated stack migration required. | Local-only managed assets; no X-CLIP loader. | Retain VEX; no blanket waiver. |
| pip | transformers | 4.57.6 | PYSEC-2026-2288 / CVE-2026-1839 / GHSA-69w3-r845-3855 | Moderate, CVSS 6.5 | Transitive via WhisperX | No | Runtime | No. Trainer RNG-state loading is not used. | 5.0.0rc3 | Not safely | WhisperX 3.8.6 constrains the current compatible line. | No Trainer checkpoint path; verified local assets. | Retain VEX; coordinated upgrade review. |
| pip | transformers | 4.57.6 | PYSEC-2026-2289 / CVE-2026-4372 / GHSA-29pf-2h5f-8g72 | High, CVSS 7.8 | Transitive via WhisperX | No | Runtime | No. AutoModelForCausalLM remote loading is absent. | 5.3.0 | Not safely | A major stack change needs WhisperX and CUDA qualification. | Cache-only pinned alignment assets; remote code disabled. | Retain VEX; coordinated upgrade review. |
| pip | transformers | 4.57.6 | PYSEC-2026-2290 / CVE-2026-5241 / GHSA-fgcw-684q-jj6r | High, CVSS 8.0 | Transitive via WhisperX | No | Runtime | No. LightGlue loading is absent from ClipGauge. | 5.5.0 | Not safely | Current WhisperX stack does not establish a safe 5.5 migration. | Local-only verified assets; no LightGlue path. | Retain VEX; specific owner review if policy requires. |
| pip | transformers | 4.57.6 | Duplicate PYSEC-2026-2288 / CVE-2026-1839 / GHSA-69w3-r845-3855 | Moderate, CVSS 6.5 | Transitive via WhisperX | No | Runtime | Same as primary 2288 record. | 5.0.0rc3 | Not safely | Duplicate audit record; same stack constraint. | Same as primary 2288 record. | Track as duplicate; no separate waiver. |
| pip | transformers | 4.57.6 | Duplicate PYSEC-2026-2289 / CVE-2026-4372 / GHSA-29pf-2h5f-8g72 | High, CVSS 7.8 | Transitive via WhisperX | No | Runtime | Same as primary 2289 record. | 5.3.0 | Not safely | Duplicate audit record; same stack constraint. | Same as primary 2289 record. | Track as duplicate; no separate waiver. |
| pip | transformers | 4.57.6 | Duplicate PYSEC-2026-2290 / CVE-2026-5241 / GHSA-fgcw-684q-jj6r | High, CVSS 8.0 | Transitive via WhisperX | No | Runtime | Same as primary 2290 record. | 5.5.0 | Not safely | Duplicate audit record; same stack constraint. | Same as primary 2290 record. | Track as duplicate; no separate waiver. |
| pip | transformers | 4.57.6 | PYSEC-2026-3929 / CVE-2026-9856 / GHSA-xrqw-3rrv-vx5w | High, CVSS 7.1 | Transitive via WhisperX | No | Runtime | No. Vulnerable save_pretrained path is not called. | 5.10.0 | Not safely | Major stack migration needs coordinated qualification. | No remote model save path; managed local assets. | Retain VEX; coordinated upgrade review. |

The Rust audit separately returned seven allowed warnings. Npm production
audit returned zero vulnerabilities. These Rust findings are not introduced by
v0.5.16.

| Ecosystem | Package/version | Advisory | Severity | Direct or transitive | Introduced by v0.5.16? | Runtime, dev, or build-only | Reachable from shipped product? Evidence | Fixed version | Upgrade possible? | Why not upgraded | Current mitigation | Recommended disposition |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cargo | proc-macro-error 1.0.4 | RUSTSEC-2024-0370 | Unmaintained | Transitive | No | Build-only proc macro | No runtime code; through glib-macros. | None | No safe direct replacement | Tauri GTK graph supplies it. | No runtime loading. | Accept as upstream build warning; monitor Tauri graph. |
| cargo | unic-char-property 0.9.0 | RUSTSEC-2025-0081 | Unmaintained | Transitive | No | Build/runtime dependency graph | No direct first-party use; through urlpattern/Tauri. | None | No safe direct replacement | Tauri dependency graph pins the line. | No first-party parser input. | Accept as upstream warning; monitor. |
| cargo | unic-char-range 0.9.0 | RUSTSEC-2025-0075 | Unmaintained | Transitive | No | Build/runtime dependency graph | No direct first-party use; through urlpattern/Tauri. | None | No safe direct replacement | Tauri dependency graph pins the line. | No first-party parser input. | Accept as upstream warning; monitor. |
| cargo | unic-common 0.9.0 | RUSTSEC-2025-0080 | Unmaintained | Transitive | No | Build/runtime dependency graph | No direct first-party use; through urlpattern/Tauri. | None | No safe direct replacement | Tauri dependency graph pins the line. | No first-party parser input. | Accept as upstream warning; monitor. |
| cargo | unic-ucd-ident 0.9.0 | RUSTSEC-2025-0100 | Unmaintained | Transitive | No | Build/runtime dependency graph | No direct first-party use; through urlpattern/Tauri. | None | No safe direct replacement | Tauri dependency graph pins the line. | No first-party parser input. | Accept as upstream warning; monitor. |
| cargo | unic-ucd-version 0.9.0 | RUSTSEC-2025-0098 | Unmaintained | Transitive | No | Build/runtime dependency graph | No direct first-party use; through urlpattern/Tauri. | None | No safe direct replacement | Tauri dependency graph pins the line. | No first-party parser input. | Accept as upstream warning; monitor. |
| cargo | glib 0.18.5 | RUSTSEC-2024-0429 | Unsound | Transitive | No | Runtime on Linux GTK path | Linux Tauri GTK/webkit2gtk graph; not Windows runtime. | None established | No safe compatible update established | Tauri GTK compatibility currently pins glib 0.18.x. | Windows release does not ship this Linux path; Linux qualification remains required. | Specific owner risk review; do not silently suppress. |
