"""ASR transcription and forced word alignment."""

from __future__ import annotations

import gc
import os
import re
import sys
import time
from pathlib import Path

from .. import config, downloads, hardware, protocol, runtime
from ..jobs import queue
from ..jobs.queue import Stage, StageContext, StageError
from ..models import managed
from .alignment import EXACT, alignment_policy, fallback_word_alignment

ASR_MODEL = "large-v3-turbo"
COMPUTE_TYPE = "int8"
GPU_BATCH_SIZE = 8
LONG_ASR_APPROVAL_SECONDS = 60.0
DEGRADED_ACCELERATION_STATE = "GPU PRESENT — RUNTIME DEGRADED"
GPU_TRANSCRIPTION_CPU_ALIGNMENT_STATE = "GPU TRANSCRIPTION / CPU ALIGNMENT"
CPU_TRANSCRIPTION_GPU_ALIGNMENT_STATE = "CPU TRANSCRIPTION / GPU ALIGNMENT"
TRANSCRIPTION_CHECKPOINT_SCHEMA_VERSION = 1


def _resource_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(term in text for term in (
        "out of memory", "out-of-memory", "memory allocation", "cannot allocate",
        "bad alloc", "resource exhausted", "not enough memory",
    ))


def _batch_sequence(initial: int) -> list[int]:
    current = max(1, int(initial))
    values: list[int] = []
    while current not in values:
        values.append(current)
        current = max(1, current // 2)
    return values


def _safe_exception_message(exc: BaseException) -> str:
    message = protocol.safe_message(str(exc), limit=240)
    return re.sub(r"(?:[A-Za-z]:[\\/]|/)[^\s]+", "<path>", message)


def _asr_failure_code(exc: BaseException, substep: str) -> str:
    text = str(exc).lower()
    if any(term in text for term in ("dll", "shared object", "cannot import", "module named")):
        return "ASR_RUNTIME_MISSING"
    if "vad" in text:
        return "ASR_VAD_FAILED"
    if any(term in text for term in ("unsupported", "not supported", "compute type")):
        return "ASR_CPU_COMPUTE_UNSUPPORTED"
    if _resource_error(exc):
        return "ASR_MODEL_LOAD_RESOURCE_EXHAUSTED" if substep == "ASR_MODEL_LOAD" else "ASR_TRANSCRIPTION_RESOURCE_EXHAUSTED"
    return {
        "ASR_IMPORT_RUNTIME": "ASR_IMPORT_RUNTIME",
        "ASR_AUDIO_LOAD": "ASR_AUDIO_LOAD_FAILED",
        "ASR_MODEL_LOAD": "ASR_MODEL_LOAD_FAILED",
        "ASR_TRANSCRIBE": "ASR_TRANSCRIPTION_FAILED",
        "ASR_ALIGNMENT_MODEL_LOAD": "ASR_ALIGNMENT_FAILED",
        "ASR_ALIGNMENT": "ASR_ALIGNMENT_FAILED",
        "ASR_CHECKPOINT_WRITE": "ASR_CHECKPOINT_WRITE",
    }.get(substep, "ASR_TRANSCRIPTION_FAILED")


def _asr_details(
    capabilities: dict,
    *,
    selected_device: str,
    selected_compute_type: str,
    actual_device: str,
    actual_compute_type: str,
    batch_size: int,
    mode: str,
    substep: str,
    exc: BaseException,
    fallback_attempts: list[dict[str, object]],
    model_file_state: str,
    whisperx_version: str,
    started_at: float | None = None,
) -> dict[str, object]:
    cpu = capabilities.get("cpu_ctranslate2") or {}
    return {
        "os": capabilities.get("os", sys.platform),
        "architecture": capabilities.get("architecture", "unknown"),
        "cpu_logical_cores": capabilities.get("cpu_logical_cores"),
        "ram_bytes": capabilities.get("ram_bytes"),
        "available_ram_bytes": capabilities.get("available_ram_bytes"),
        "total_page_file_bytes": capabilities.get("total_page_file_bytes"),
        "available_page_file_bytes": capabilities.get("available_page_file_bytes"),
        "selected_asr_device": selected_device,
        "selected_compute_type": selected_compute_type,
        "actual_compute_type": actual_compute_type,
        "actual_asr_device": actual_device,
        "batch_size": batch_size,
        "transcription_mode": mode,
        "asr_model": ASR_MODEL,
        "asr_model_revision": managed.ASR_REVISION,
        "model_file_verification_state": model_file_state,
        "ctranslate2_version": cpu.get("version"),
        "whisperx_version": whisperx_version,
        "python_version": sys.version.split()[0],
        "cpu_supported_compute_types": list(cpu.get("compute_types") or []),
        "failing_asr_substep": substep,
        "exception_class": type(exc).__name__,
        "sanitized_exception_message": _safe_exception_message(exc),
        "elapsed_seconds": round(time.monotonic() - started_at, 3) if started_at is not None else 0.0,
        "fallback_attempts": list(fallback_attempts),
    }


def _transcribe_model(
    model,
    audio,
    *,
    initial_batch: int,
    emit,
    attempts: list[dict[str, object]],
):
    last_error: BaseException | None = None
    for batch_size in _batch_sequence(initial_batch):
        attempts.append({"operation": "transcribe", "batch_size": batch_size, "result": "started"})
        try:
            result = model.transcribe(audio, batch_size=batch_size)
            attempts[-1] = {**attempts[-1], "result": "success"}
            return result
        except Exception as exc:
            attempts[-1] = {**attempts[-1], "result": "failed", "error_class": type(exc).__name__}
            last_error = exc
            if not _resource_error(exc) or batch_size == 1:
                raise
            next_batch = max(1, batch_size // 2)
            emit(f"Speech recognition needs more memory; retrying with batch {next_batch}…")
    assert last_error is not None
    raise last_error


def _point_caches_at_home() -> None:
    managed.apply_local_env()


def _transcribe_with_fallback(
    model,
    *,
    audio,
    device: str,
    compute_type: str,
    load_cpu_model,
    emit,
    allow_cpu_fallback: bool = True,
    cpu_batch_size: int = GPU_BATCH_SIZE,
    cpu_compute_type: str = "int8",
    attempts: list[dict[str, object]] | None = None,
):
    attempts = attempts if attempts is not None else []
    try:
        result = _transcribe_model(
            model,
            audio,
            initial_batch=cpu_batch_size if device == "cpu" else GPU_BATCH_SIZE,
            emit=emit,
            attempts=attempts,
        )
        return result, model, device, compute_type
    except Exception as exc:
        if device == "cpu":
            code = _asr_failure_code(exc, "ASR_TRANSCRIBE")
            raise StageError(
                "Speech recognition needs more working memory. Close other applications and retry in Low-memory mode." if code == "ASR_TRANSCRIPTION_RESOURCE_EXHAUSTED" else "Speech transcription could not complete. Retry the job or repair the speech runtime.",
                code=code,
                retryable=True,
            ) from exc
        if not allow_cpu_fallback:
            raise StageError(
                "GPU speech acceleration failed. Repair GPU acceleration or explicitly continue in slower CPU mode.",
                code="ASR_GPU_FALLBACK_REQUIRES_APPROVAL",
                retryable=True,
            ) from exc
        emit(f"GPU speech execution was unavailable; using CPU fallback ({cpu_compute_type})…")
        del model
        gc.collect()
        try:
            cpu_model = load_cpu_model()
        except Exception as fallback_exc:
            code = _asr_failure_code(fallback_exc, "ASR_MODEL_LOAD")
            raise StageError(
                "Speech recognition needs more working memory. Close other applications and retry in Low-memory mode." if code == "ASR_MODEL_LOAD_RESOURCE_EXHAUSTED" else "Speech transcription could not load its model. Repair the speech runtime and retry.",
                code=code,
                retryable=True,
            ) from fallback_exc
        try:
            result = _transcribe_model(
                cpu_model,
                audio,
                initial_batch=cpu_batch_size,
                emit=emit,
                attempts=attempts,
            )
        except Exception as fallback_exc:
            code = _asr_failure_code(fallback_exc, "ASR_TRANSCRIBE")
            raise StageError(
                "Speech recognition needs more working memory. Close other applications and retry in Low-memory mode." if code == "ASR_TRANSCRIPTION_RESOURCE_EXHAUSTED" else "Speech transcription could not complete. Retry with CPU acceleration or repair the speech runtime.",
                code=code,
                retryable=True,
            ) from fallback_exc
        return result, cpu_model, "cpu", cpu_compute_type


def _transcription_identity(audio_path: Path) -> dict[str, object]:
    return {
        "source_size": audio_path.stat().st_size,
        "source_sha256": runtime.sha256_file(audio_path),
        "model": ASR_MODEL,
        "model_revision": managed.ASR_REVISION,
    }


def _cached_transcription(ctx: StageContext, audio_path: Path) -> dict | None:
    job = getattr(ctx, "job", None)
    if job is None:
        return None
    cached = queue.read_checkpoint(job, "asr-transcription", TRANSCRIPTION_CHECKPOINT_SCHEMA_VERSION)
    if not isinstance(cached, dict) or cached.get("identity") != _transcription_identity(audio_path):
        return None
    result = cached.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("segments"), list):
        return None
    return cached


def _save_transcription(ctx: StageContext, audio_path: Path, result: dict, device: str, compute_type: str) -> None:
    job = getattr(ctx, "job", None)
    if job is None:
        return
    queue.write_checkpoint(
        job,
        "asr-transcription",
        TRANSCRIPTION_CHECKPOINT_SCHEMA_VERSION,
        {
            "identity": _transcription_identity(audio_path),
            "result": result,
            "transcription_device": device,
            "transcription_compute_type": compute_type,
        },
    )


class AsrStage(Stage):
    name = "asr"
    schema_version = 2

    def run(self, ctx: StageContext) -> dict:
        ingest = ctx.prior.get("ingest") if ctx.prior else None
        if not ingest:
            raise StageError("ASR needs the ingest stage output.")
        audio_path = Path(ingest["audio_path"])
        if not audio_path.exists():
            raise StageError("Analysis audio missing — re-run ingest.")

        _point_caches_at_home()
        asset_manager = downloads.DownloadManager()
        if not managed.ready(asset_manager):
            raise StageError(
                "Speech recognition assets are not ready. Open Setup Center and approve the Speech recognition download group.",
                code="ASR_ASSETS_NOT_READY",
                retryable=True,
            )
        try:
            import torch  # deferred: heavy import
            import whisperx
        except Exception as exc:
            raise StageError(
                "Speech recognition runtime could not start. Open Setup Center and repair speech recognition.",
                code=_asr_failure_code(exc, "ASR_IMPORT_RUNTIME"),
                retryable=True,
                details={"failing_asr_substep": "ASR_IMPORT_RUNTIME", "exception_class": type(exc).__name__, "sanitized_exception_message": _safe_exception_message(exc)},
            ) from exc

        capabilities = hardware.snapshot(config.home_dir())
        devices = hardware.select_asr_devices(capabilities)
        selected_device = devices["transcription_device"]
        selected_compute_type = devices["transcription_compute_type"]
        cpu_policy = hardware.cpu_asr_policy(capabilities)
        cpu_batch_size = int(cpu_policy["batch_size"])
        cpu_compute_type = str(cpu_policy["compute_type"])
        transcription_batch_size = int(devices.get("transcription_batch_size", GPU_BATCH_SIZE if selected_device == "cuda" else cpu_batch_size))
        transcription_mode = str(devices.get("transcription_mode", "cuda" if selected_device == "cuda" else cpu_policy["mode"]))
        cpu_probe = capabilities.get("cpu_ctranslate2") or {}
        cpu_supported = list(cpu_probe.get("compute_types") or [])
        if selected_device == "cpu" and (not cpu_probe.get("verified") or not cpu_supported):
            raise StageError(
                "This computer does not expose a supported CPU speech mode. Repair the speech runtime and retry.",
                code="ASR_CPU_COMPUTE_UNSUPPORTED",
                retryable=True,
                details={"failing_asr_substep": "ASR_CAPABILITY_PROBE", "cpu_supported_compute_types": []},
            )
        transcription_device = selected_device
        transcription_compute_type = selected_compute_type
        alignment_device = devices["alignment_device"]
        acceleration = hardware.asr_readiness(capabilities)
        fallback_reason = None
        fallback_stages: list[str] = []
        allow_cpu_fallback = bool(getattr(ctx.settings, "allow_cpu_asr_fallback", False))
        duration = float(ingest.get("probe", {}).get("duration_sec", 0.0))
        long_job = duration >= LONG_ASR_APPROVAL_SECONDS
        model_load_device = transcription_device
        model_load_secs = 0.0
        transcribe_secs = 0.0
        fallback_attempts: list[dict[str, object]] = []
        model_file_state = "ready" if managed.ready(asset_manager) else "not-ready"
        whisperx_version = str(getattr(whisperx, "__version__", "unknown"))

        if transcription_device == "cuda" or alignment_device == "cuda":
            try:
                managed.activate_cuda_runtime()
            except Exception as exc:
                if transcription_device == "cuda":
                    raise StageError(
                        "The verified CUDA speech runtime is unavailable. Repair Speech recognition in Setup Center.",
                        code="ASR_CUDA_RUNTIME_NOT_READY",
                        retryable=True,
                    ) from exc
                alignment_device = "cpu"
                fallback_reason = "CUDA alignment runtime was unavailable; word alignment is using CPU."

        cached = _cached_transcription(ctx, audio_path)
        if cached is not None:
            result = cached["result"]
            transcription_device = str(cached.get("transcription_device") or "cpu")
            transcription_compute_type = str(cached.get("transcription_compute_type") or cpu_compute_type)
            transcription_batch_size = int(cached.get("transcription_batch_size") or transcription_batch_size)
            transcription_mode = str(cached.get("transcription_mode") or transcription_mode)
            try:
                audio = whisperx.load_audio(str(audio_path))
            except Exception as exc:
                raise StageError(
                    "Speech recognition could not read the analysis audio. Retry the job or repair the video.",
                    code="ASR_AUDIO_LOAD_FAILED", retryable=True,
                    details=_asr_details(capabilities, selected_device=selected_device, selected_compute_type=selected_compute_type, actual_device=transcription_device, actual_compute_type=transcription_compute_type, batch_size=transcription_batch_size, mode=transcription_mode, substep="ASR_AUDIO_LOAD", exc=exc, fallback_attempts=fallback_attempts, model_file_state=model_file_state, whisperx_version=whisperx_version),
                ) from exc
            duration = float(len(audio)) / 16000.0
            ctx.emit(-1, "Reusing completed transcription; aligning words…")
        else:
            ctx.emit(-1, "Loading verified speech model…")
            model_load_device = transcription_device
            os.environ["CLIPGAUGE_ACCELERATOR"] = f"{transcription_device}/{transcription_compute_type}"
            if transcription_device == "cpu":
                ctx.emit(-1, f"Using CPU speech recognition ({transcription_compute_type}, {transcription_mode}, batch {transcription_batch_size})…")
            else:
                ctx.emit(-1, f"Using {transcription_device.upper()} speech acceleration ({transcription_compute_type})…")
            model_started = time.monotonic()
            try:
                model = whisperx.load_model(
                    str(managed.asr_model_path()), transcription_device,
                    compute_type=transcription_compute_type, vad_method="silero", local_files_only=True,
                )
            except Exception as exc:
                if transcription_device != "cpu":
                    if long_job and not allow_cpu_fallback:
                        raise StageError(
                            "GPU speech acceleration failed. Repair GPU acceleration or explicitly continue in slower CPU mode.",
                            code="ASR_GPU_FALLBACK_REQUIRES_APPROVAL", retryable=True,
                            details=_asr_details(capabilities, selected_device=selected_device, selected_compute_type=selected_compute_type, actual_device=transcription_device, actual_compute_type=transcription_compute_type, batch_size=transcription_batch_size, mode=transcription_mode, substep="ASR_MODEL_LOAD", exc=exc, fallback_attempts=fallback_attempts, model_file_state=model_file_state, whisperx_version=whisperx_version, started_at=model_started),
                        ) from exc
                    fallback_reason = "CUDA speech model load failed."
                    fallback_stages.append("model_load")
                    transcription_device, transcription_compute_type = "cpu", cpu_compute_type
                    transcription_batch_size = cpu_batch_size
                    transcription_mode = cpu_policy["mode"]
                    acceleration = {**acceleration, "state": DEGRADED_ACCELERATION_STATE, "device": "cpu", "compute_type": cpu_compute_type, "reason": fallback_reason}
                    os.environ["CLIPGAUGE_ACCELERATOR"] = f"cpu/{cpu_compute_type}"
                    ctx.emit(-1, f"GPU speech acceleration was unavailable; using CPU fallback ({cpu_compute_type}, {transcription_mode}, batch {cpu_batch_size})…")
                    try:
                        model = whisperx.load_model(
                            str(managed.asr_model_path()), "cpu", compute_type=cpu_compute_type,
                            vad_method="silero", local_files_only=True,
                        )
                    except Exception as fallback_exc:
                        code = _asr_failure_code(fallback_exc, "ASR_MODEL_LOAD")
                        raise StageError(
                            "Speech recognition needs more working memory. Close other applications and retry in Low-memory mode." if code == "ASR_MODEL_LOAD_RESOURCE_EXHAUSTED" else "Speech transcription could not load its model. Repair the speech runtime in Setup Center and retry.",
                            code=code, retryable=True,
                            details=_asr_details(capabilities, selected_device=selected_device, selected_compute_type=selected_compute_type, actual_device=transcription_device, actual_compute_type=transcription_compute_type, batch_size=transcription_batch_size, mode=transcription_mode, substep="ASR_MODEL_LOAD", exc=fallback_exc, fallback_attempts=fallback_attempts, model_file_state=model_file_state, whisperx_version=whisperx_version, started_at=model_started),
                        ) from fallback_exc
                else:
                    code = _asr_failure_code(exc, "ASR_MODEL_LOAD")
                    raise StageError(
                        "Speech recognition needs more working memory. Close other applications and retry in Low-memory mode." if code == "ASR_MODEL_LOAD_RESOURCE_EXHAUSTED" else "Speech transcription could not load its model. Repair the speech runtime in Setup Center and retry.",
                        code=code, retryable=True,
                        details=_asr_details(capabilities, selected_device=selected_device, selected_compute_type=selected_compute_type, actual_device=transcription_device, actual_compute_type=transcription_compute_type, batch_size=transcription_batch_size, mode=transcription_mode, substep="ASR_MODEL_LOAD", exc=exc, fallback_attempts=fallback_attempts, model_file_state=model_file_state, whisperx_version=whisperx_version, started_at=model_started),
                    ) from exc
            try:
                audio = whisperx.load_audio(str(audio_path))
            except Exception as exc:
                raise StageError(
                    "Speech recognition could not read the analysis audio. Retry the job or repair the video.",
                    code="ASR_AUDIO_LOAD_FAILED", retryable=True,
                    details=_asr_details(capabilities, selected_device=selected_device, selected_compute_type=selected_compute_type, actual_device=transcription_device, actual_compute_type=transcription_compute_type, batch_size=transcription_batch_size, mode=transcription_mode, substep="ASR_AUDIO_LOAD", exc=exc, fallback_attempts=fallback_attempts, model_file_state=model_file_state, whisperx_version=whisperx_version, started_at=model_started),
                ) from exc
            duration = float(len(audio)) / 16000.0
            ctx.emit(-1, "Transcribing…")
            model_load_device = transcription_device
            model_load_secs = time.monotonic() - model_started
            transcription_started = time.monotonic()
            try:
                result, model, transcription_device, transcription_compute_type = _transcribe_with_fallback(
                    model, audio=audio, device=transcription_device, compute_type=transcription_compute_type,
                    cpu_batch_size=cpu_batch_size,
                    cpu_compute_type=cpu_compute_type,
                    attempts=fallback_attempts,
                    load_cpu_model=lambda: whisperx.load_model(
                        str(managed.asr_model_path()), "cpu", compute_type=cpu_compute_type,
                        vad_method="silero", local_files_only=True,
                    ),
                    emit=lambda message: ctx.emit(-1, message),
                    allow_cpu_fallback=allow_cpu_fallback or not long_job,
                )
            except StageError as exc:
                diagnostic_substep = "ASR_MODEL_LOAD" if exc.code in {
                    "ASR_MODEL_LOAD_RESOURCE_EXHAUSTED", "ASR_MODEL_LOAD_FAILED",
                } else "ASR_TRANSCRIBE"
                raise StageError(
                    str(exc), code=exc.code, retryable=exc.retryable,
                    details=exc.details or _asr_details(
                        capabilities, selected_device=selected_device, selected_compute_type=selected_compute_type,
                        actual_device=transcription_device, actual_compute_type=transcription_compute_type,
                        batch_size=cpu_batch_size if transcription_device == "cpu" else transcription_batch_size,
                        mode=transcription_mode, substep=diagnostic_substep, exc=exc.__cause__ or exc,
                        fallback_attempts=fallback_attempts, model_file_state=model_file_state,
                        whisperx_version=whisperx_version, started_at=transcription_started,
                    ),
                ) from (exc.__cause__ or exc)
            transcribe_secs = time.monotonic() - transcription_started
            if transcription_device == "cpu" and selected_device != "cpu":
                fallback_stages.append("transcription")
                fallback_reason = fallback_reason or "CUDA speech execution failed during transcription."
                acceleration = {**acceleration, "state": DEGRADED_ACCELERATION_STATE, "device": "cpu", "compute_type": cpu_compute_type, "reason": fallback_reason}
            if transcription_device == "cpu":
                transcription_batch_size = cpu_batch_size
                transcription_mode = cpu_policy["mode"]
            try:
                _save_transcription(ctx, audio_path, result, transcription_device, transcription_compute_type)
            except Exception as exc:
                raise StageError(
                    "Speech recognition completed but its checkpoint could not be saved. Retry the job.",
                    code="ASR_CHECKPOINT_WRITE", retryable=True,
                    details=_asr_details(capabilities, selected_device=selected_device, selected_compute_type=selected_compute_type, actual_device=transcription_device, actual_compute_type=transcription_compute_type, batch_size=transcription_batch_size, mode=transcription_mode, substep="ASR_CHECKPOINT_WRITE", exc=exc, fallback_attempts=fallback_attempts, model_file_state=model_file_state, whisperx_version=whisperx_version, started_at=transcription_started),
                ) from exc
            del model
            gc.collect()

        language = result.get("language", "en")
        ctx.emit(-1, "Aligning words…")
        started = time.monotonic()
        policy = alignment_policy(language)
        align_model = None
        if policy.status == EXACT:
            alignment_substep = "ASR_ALIGNMENT_MODEL_LOAD"
            try:
                align_model, align_meta = whisperx.load_align_model(
                    language_code=language, device=alignment_device, model_name=policy.model_name,
                    model_dir=str(managed.alignment_model_dir()), model_cache_only=True,
                )
                alignment_substep = "ASR_ALIGNMENT"
                aligned = whisperx.align(
                    result["segments"], align_model, align_meta, audio, alignment_device,
                    return_char_alignments=False,
                )
            except Exception as exc:
                if alignment_device != "cpu":
                    if long_job and not allow_cpu_fallback:
                        raise StageError(
                            "GPU speech acceleration failed during word alignment. Repair GPU acceleration or explicitly continue in slower CPU mode.",
                            code="ASR_GPU_FALLBACK_REQUIRES_APPROVAL", retryable=True,
                            details=_asr_details(capabilities, selected_device=selected_device, selected_compute_type=selected_compute_type, actual_device=transcription_device, actual_compute_type=transcription_compute_type, batch_size=transcription_batch_size, mode=transcription_mode, substep=alignment_substep, exc=exc, fallback_attempts=fallback_attempts, model_file_state=model_file_state, whisperx_version=whisperx_version, started_at=started),
                        ) from exc
                    fallback_reason = "CUDA word alignment failed."
                    fallback_stages.append("alignment")
                    alignment_device = "cpu"
                    acceleration = {**acceleration, "state": DEGRADED_ACCELERATION_STATE, "reason": fallback_reason}
                    ctx.emit(-1, "Word alignment fell back to CPU…")
                    try:
                        align_model, align_meta = whisperx.load_align_model(
                            language_code=language, device="cpu", model_name=policy.model_name,
                            model_dir=str(managed.alignment_model_dir()), model_cache_only=True,
                        )
                        alignment_substep = "ASR_ALIGNMENT"
                        aligned = whisperx.align(
                            result["segments"], align_model, align_meta, audio, "cpu",
                            return_char_alignments=False,
                        )
                    except Exception as fallback_exc:
                        raise StageError(
                            "Speech alignment could not complete. Retry with CPU acceleration or repair the speech runtime.",
                            code="ASR_ALIGNMENT_FAILED", retryable=True,
                            details=_asr_details(capabilities, selected_device=selected_device, selected_compute_type=selected_compute_type, actual_device=transcription_device, actual_compute_type=transcription_compute_type, batch_size=transcription_batch_size, mode=transcription_mode, substep=alignment_substep, exc=fallback_exc, fallback_attempts=fallback_attempts, model_file_state=model_file_state, whisperx_version=whisperx_version, started_at=started),
                        ) from fallback_exc
                else:
                    raise StageError(
                        "Speech alignment could not complete. Retry the job or repair the runtime.",
                        code="ASR_ALIGNMENT_FAILED", retryable=True,
                        details=_asr_details(capabilities, selected_device=selected_device, selected_compute_type=selected_compute_type, actual_device=transcription_device, actual_compute_type=transcription_compute_type, batch_size=transcription_batch_size, mode=transcription_mode, substep=alignment_substep, exc=exc, fallback_attempts=fallback_attempts, model_file_state=model_file_state, whisperx_version=whisperx_version, started_at=started),
                    ) from exc
        else:
            aligned = {"segments": fallback_word_alignment(result.get("segments", []), duration=duration)}
            ctx.emit(-1, f"{policy.language.upper()} word timings use a deterministic local fallback.")
        align_secs = time.monotonic() - started
        if align_model is not None:
            del align_model
        gc.collect()
        if hasattr(torch, "mps") and torch.backends.mps.is_available():
            torch.mps.empty_cache()

        segments = []
        for seg in aligned["segments"]:
            words = [
                {"word": w.get("word", "").strip(), "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3), "score": round(float(w.get("score", 0.0)), 3)}
                for w in seg.get("words", []) if "start" in w and "end" in w
            ]
            segments.append({"start": round(float(seg["start"]), 3), "end": round(float(seg["end"]), 3), "text": seg.get("text", "").strip(), "words": words})

        word_count = sum(len(segment["words"]) for segment in segments)
        if word_count == 0:
            raise StageError("No speech was found in this video. ClipGauge needs dialogue to find moments.")

        total = transcribe_secs + align_secs
        if selected_device == "cuda" and transcription_device == "cuda" and alignment_device == "cuda":
            acceleration = {**acceleration, "state": "GPU ACCELERATED", "device": "cuda", "compute_type": selected_compute_type, "reason": "Real transcription and alignment completed on CUDA."}
        elif selected_device == "cuda" and transcription_device == "cuda" and alignment_device == "cpu":
            acceleration = {**acceleration, "state": GPU_TRANSCRIPTION_CPU_ALIGNMENT_STATE, "device": "cuda", "compute_type": transcription_compute_type, "reason": "GPU transcription completed; word alignment is using CPU."}
        elif transcription_device == "cpu" and alignment_device == "cuda":
            acceleration = {**acceleration, "state": CPU_TRANSCRIPTION_GPU_ALIGNMENT_STATE, "device": "mixed", "compute_type": transcription_compute_type, "reason": "CPU transcription completed; word alignment used CUDA."}
        return {
            "language": language, "model": ASR_MODEL, "compute_type": transcription_compute_type,
            "device": transcription_device, "accelerator": f"{transcription_device}/{transcription_compute_type}",
            "acceleration_state": acceleration["state"], "acceleration_reason": fallback_reason or acceleration["reason"],
            "selected_device": selected_device, "selected_compute_type": selected_compute_type,
            "model_load_device": model_load_device,
            "transcription_device": transcription_device, "transcription_compute_type": transcription_compute_type,
            "alignment_device": alignment_device, "alignment_status": policy.status,
            "alignment_asset_id": policy.asset_id, "alignment_reason": policy.reason,
            "transcription_batch_size": transcription_batch_size, "transcription_mode": transcription_mode,
            "cpu_supported_compute_types": cpu_supported, "fallback_attempts": fallback_attempts,
            "fallback_stages": fallback_stages, "segments": segments, "word_count": word_count,
            "benchmark": {
                "audio_sec": round(duration, 1), "model_load_sec": round(model_load_secs, 1),
                "transcribe_sec": round(transcribe_secs, 1), "align_sec": round(align_secs, 1),
                "realtime_factor": round(duration / total, 2) if total > 0 else None,
            },
        }
