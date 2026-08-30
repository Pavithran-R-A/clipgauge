# v0.5.4 Python dependency VEX

Audit basis: the project `pipeline/uv.lock` audit record captured on
2026-08-30. It contains 14 records. A coordinated disposable upgrade of
WhisperX, Torch, torchaudio, torchvision, Transformers, and Lightning kept
WhisperX 3.8.6 with Torch 2.8.x, Transformers 4.57.6, and Lightning 2.6.5.
No advisory is marked fixed by reachability alone.

The Python runtime is shipped in the Windows package and is used by the
Linux/macOS qualification environments. `torch` is transitive through
WhisperX. `lightning` is transitive through the pyannote stack. Transformers
is transitive through WhisperX. User media is the only untrusted data entering
the local pipeline. Managed model acquisition is networked, but loading is
offline after staged size and SHA-256 verification. No service exposes these
model-loading paths to remote callers.

The table's runtime field is `shipped / imported`: `direct` means ClipGauge
imports the package, and `transitive` means an exercised dependency imports it.

| Canonical ID and aliases | Package/version | Fixed versions | Dependency and runtime path | Shipped runtime / imported | Affected API; executed? | Attacker input; network; privilege | Compatible fix | Final disposition and VEX justification |
|---|---|---|---|---|---|---|---|---|
| PYSEC-2026-3624; CVE-2026-58659 | lightning 2.6.5 | none reported | `clipgauge-pipeline -> whisperx -> pyannote-audio -> lightning`; no ClipGauge Lightning checkpoint loader | yes / transitive import | Lightning affected loader: no; source search and runtime path review found no matching call | Local model files only; acquisition is pinned; local-user prerequisite; no remote service | None compatible without retesting WhisperX | NOT_AFFECTED — the vulnerable Lightning operation is absent from the shipped ClipGauge path. Upstream remains open. |
| PYSEC-2025-206; CVE-2025-55554 | torch 2.8.0 | 2.9.0 | `clipgauge-pipeline -> whisperx -> torch`; no `torch.nan_to_num().long()` path | yes / direct import | `torch.nan_to_num().long()`: no; source search found no call | Local media and verified local weights; no network execution; ordinary local-user process | 2.9.0 requires coordinated WhisperX validation | NOT_AFFECTED — the affected operation is not executed. Upstream remains open. |
| PYSEC-2025-204; CVE-2025-55552 | torch 2.8.0 | 2.9.0 | Same transitive Torch path; no `torch.rot90` plus `torch.randn_like` path | yes / direct import | Affected tensor sequence: no; source search found no call | Local media only; no remote service; local user required | 2.9.0 requires coordinated WhisperX validation | NOT_AFFECTED — the affected operation is not executed. Upstream remains open. |
| PYSEC-2026-139; CVE-2026-4538 | torch 2.8.0 | none reported | Managed checkpoint callers use `models.registry.require_verified_model` before Torch loading | Yes / yes | PT2 loading handler: no; managed Torch loads use exact registry path, size, SHA-256, and `weights_only=True` | Download is staged and pinned; no arbitrary repository/config reference; local user required | No compatible fix reported | MITIGATED — the managed loading boundary rejects unexpected identity and bytes before load. Upstream remains open. |
| PYSEC-2025-203; CVE-2025-55551 | torch 2.8.0 | 2.9.0 | Same transitive Torch path; no `torch.linalg.lu` slice path | Yes / yes | Affected LU slice operation: no; source search found no call | Local media only; no remote service; local user required | 2.9.0 requires coordinated WhisperX validation | NOT_AFFECTED — the affected operation is not executed. Upstream remains open. |
| PYSEC-2025-194; GHSA-rrmf-rvhw-rf47; CVE-2025-3000; BIT-pytorch-2025-3000 | torch 2.8.0 | 2.13.0 | Same transitive Torch path; no `torch.jit.script` path | Yes / yes | `torch.jit.script`: no; source search found no call | Local media and managed weights; no remote service; local user required | 2.13.0 requires coordinated WhisperX validation | NOT_AFFECTED — the affected operation is not executed. Upstream remains open. |
| PYSEC-2026-2286; GHSA-63cw-57p8-fm3p; CVE-2026-24747 | torch 2.8.0 | 2.10.0 | Managed Torch checkpoint callers use the verified registry boundary | Yes / yes | Untrusted weights-only load: no; all managed callers verify identity, size, SHA-256, then use `weights_only=True` | Network is limited to pinned acquisition; no arbitrary remote repository/config; local user required | 2.10.0 requires coordinated WhisperX validation | MITIGATED — untrusted managed checkpoints cannot reach the load call. Upstream remains open. |
| CVE-2025-2999; GHSA-vgrw-7cvw-pwgx | torch 2.8.0 | 2.9.1 | Same transitive Torch path; no `torch.nn.utils.rnn.unpack_sequence` path | Yes / yes | `unpack_sequence`: no; source search found no call | Local media only; no remote service; local user required | 2.9.1 requires coordinated WhisperX validation | NOT_AFFECTED — the affected operation is not executed. Upstream remains open. |
| CVE-2025-3001; GHSA-qfhq-4f3w-5fph | torch 2.8.0 | 2.10.0 | Same transitive Torch path; no `torch.lstm_cell` path | Yes / yes | `torch.lstm_cell`: no; source search found no call | Local media only; no remote service; local user required | 2.10.0 requires coordinated WhisperX validation | NOT_AFFECTED — the affected operation is not executed. Upstream remains open. |
| PYSEC-2025-217; CVE-2025-14929 | Transformers 4.57.6 | none reported | `clipgauge-pipeline -> whisperx -> transformers`; no X-CLIP conversion | Yes / yes | X-CLIP conversion: no; no matching loader or call | Local model metadata is validated; network is pinned acquisition only; local user required | None reported | NOT_AFFECTED — the affected conversion path is absent. Upstream remains open. |
| PYSEC-2026-2290; CVE-2026-5241; GHSA-fgcw-684q-jj6r | Transformers 4.57.6 | none reported; one duplicate record lists 5.5.0 | Same transitive Transformers path; no LightGlue loader or arbitrary repository reference | Yes / yes | LightGlue path: no; source search found no call | Managed metadata rejects remote-code and repository redirects; no remote service; local user required | 5.5.0 is not compatible without WhisperX validation | NOT_AFFECTED — the affected LightGlue path is absent. Upstream remains open. |
| PYSEC-2026-2288; CVE-2026-1839; GHSA-69w3-r845-3855 | Transformers 4.57.6 | 5.0.0 | Same transitive Transformers path; no Trainer or RNG-state loader | Yes / yes | Trainer/RNG-state path: no; source search found no call | Local media and verified assets; no remote service; local user required | 5.0.0 requires coordinated WhisperX validation | NOT_AFFECTED — the affected Trainer path is absent. Upstream remains open. |
| PYSEC-2026-2289; GHSA-29pf-2h5f-8g72; CVE-2026-4372 | Transformers 4.57.6 | 5.3.0 | WhisperX English alignment uses the fixed local torchaudio asset; model cache is local-only | Yes / yes | Affected alignment loader: constrained; source uses `model_cache_only=True`, managed asset hash verification, and offline env | Acquisition is pinned; local metadata cannot redirect loading; local user required | 5.3.0 requires coordinated WhisperX validation | MITIGATED — alignment cannot fetch or load an unverified repository asset. Upstream remains open. |
| PYSEC-2026-2290; CVE-2026-5241; GHSA-fgcw-684q-jj6r duplicate record | Transformers 4.57.6 | 5.5.0 in duplicate record | Duplicate of the LightGlue record above; no additional ClipGauge path | Yes / yes | No additional execution; duplicate audit record confirmed | Same as parent record | Same as parent record | NOT_AFFECTED — duplicate record, not a second advisory or code path. |

## Boundary evidence

- Managed ONNX, Torch, and checkpoint callers require exact registry identity,
  expected size, and SHA-256 before loading.
- Managed Torch callers use `weights_only=True`.
- Local model metadata rejects repository, URL, remote-code, and trust flags.
- WhisperX ASR uses local-only model and VAD loading.
- English alignment uses the pinned local asset and cache-only loading.
- SpeechBrain remote custom loading is disabled; SER uses the deterministic DSP
  fallback until a verified local bundle exists.
- `pipeline/tests/test_security_boundaries.py` proves rejection of path,
  hash, metadata, and remote-loader boundary violations.

These records do not claim an advisory-free dependency set. The remaining
upstream-open advisories require a coordinated WhisperX compatibility upgrade.
No current record is classified `ACCEPTED_RISK` or `BLOCKING`; a future audit
must reopen the release gate if an affected operation becomes reachable.
