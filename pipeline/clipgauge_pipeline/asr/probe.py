"""Small real CUDA speech qualification probe.

The probe records timings and runtime identity only. It never writes transcript
text or model responses to the evidence file.
"""

from __future__ import annotations

import gc
import importlib.metadata
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from .. import config, hardware
from ..models import managed
from .alignment import EXACT, alignment_policy, fallback_word_alignment


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _atomic_write_text(path: Path, content: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".part",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def run_cuda_probe(audio_path: Path, evidence_path: Path, *, align: bool) -> dict[str, Any]:
    """Run verified local CUDA speech, optionally including alignment."""
    path = audio_path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    managed.activate_cuda_runtime()
    capabilities = hardware.snapshot(config.home_dir())
    if not (capabilities.get("nvidia") or {}).get("verified"):
        raise RuntimeError("NVIDIA device verification failed")
    if not (capabilities.get("cuda_ctranslate2") or {}).get("verified"):
        raise RuntimeError("CTranslate2 CUDA device verification failed")

    import ctranslate2
    import whisperx

    audio = whisperx.load_audio(str(path))
    audio_seconds = float(len(audio)) / 16000.0
    started = time.monotonic()
    model = whisperx.load_model(
        managed.asr_model_path().as_posix(),
        "cuda",
        compute_type="float16",
        vad_method="silero",
        local_files_only=True,
    )
    model_load_seconds = time.monotonic() - started
    started = time.monotonic()
    result = model.transcribe(audio, batch_size=8)
    transcription_seconds = time.monotonic() - started
    if not result.get("segments"):
        raise RuntimeError("CUDA transcription returned no segments")
    del model
    gc.collect()

    alignment_seconds = None
    alignment_policy_result = alignment_policy(result.get("language", "en"))
    if align and alignment_policy_result.status == EXACT:
        started = time.monotonic()
        align_model, align_meta = whisperx.load_align_model(
            language_code=result.get("language", "en"),
            device="cuda",
            model_name="WAV2VEC2_ASR_BASE_960H",
            model_dir=managed.alignment_model_dir().as_posix(),
            model_cache_only=True,
        )
        aligned = whisperx.align(
            result["segments"],
            align_model,
            align_meta,
            audio,
            "cuda",
            return_char_alignments=False,
        )
        alignment_seconds = time.monotonic() - started
        if not aligned.get("segments"):
            raise RuntimeError("CUDA alignment returned no segments")
        del align_model
        gc.collect()
    elif align:
        started = time.monotonic()
        aligned = fallback_word_alignment(result.get("segments", []), duration=audio_seconds)
        if not aligned:
            raise RuntimeError("deterministic alignment returned no segments")
        alignment_seconds = time.monotonic() - started

    gpu = (capabilities.get("nvidia") or {}).get("gpus") or []
    evidence: dict[str, Any] = {
        "status": "PASS",
        "gpu": gpu[0] if gpu else None,
        "ctranslate2_version": getattr(ctranslate2, "__version__", "unknown"),
        "faster_whisper_version": _package_version("faster-whisper"),
        "whisperx_version": _package_version("whisperx"),
        "device": "cuda",
        "compute_type": "float16",
        "audio_seconds": round(audio_seconds, 3),
        "model_load_seconds": round(model_load_seconds, 3),
        "transcription_seconds": round(transcription_seconds, 3),
        "alignment_seconds": round(alignment_seconds, 3) if alignment_seconds is not None else None,
        "realtime_factor": round(audio_seconds / max(0.001, transcription_seconds + (alignment_seconds or 0.0)), 3),
        "cuda_runtime_version": "12.4",
        "cudnn_version": "9.11.0.98",
        "managed_runtime": True,
        "alignment": align,
        "alignment_status": alignment_policy_result.status,
        "alignment_asset_id": alignment_policy_result.asset_id,
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(evidence_path, json.dumps(evidence, indent=2, sort_keys=True))
    return evidence
