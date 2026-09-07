"""ASR transcription and forced word alignment."""

from __future__ import annotations

import gc
import os
import time
from pathlib import Path

from .. import config, downloads, hardware, runtime
from ..jobs import queue
from ..jobs.queue import Stage, StageContext, StageError
from ..models import managed
from .alignment import EXACT, alignment_policy, fallback_word_alignment

ASR_MODEL = "large-v3-turbo"
COMPUTE_TYPE = "int8"
BATCH_SIZE = 8
LONG_ASR_APPROVAL_SECONDS = 60.0
DEGRADED_ACCELERATION_STATE = "GPU PRESENT — RUNTIME DEGRADED"
GPU_TRANSCRIPTION_CPU_ALIGNMENT_STATE = "GPU TRANSCRIPTION / CPU ALIGNMENT"
CPU_TRANSCRIPTION_GPU_ALIGNMENT_STATE = "CPU TRANSCRIPTION / GPU ALIGNMENT"
TRANSCRIPTION_CHECKPOINT_SCHEMA_VERSION = 1


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
):
    try:
        return model.transcribe(audio, batch_size=BATCH_SIZE), model, device, compute_type
    except Exception as exc:  # noqa: BLE001 - accelerator failures vary by runtime
        if device == "cpu":
            raise StageError(
                "Speech transcription could not complete. Retry the job or repair the speech runtime.",
                code="ASR_TRANSCRIPTION_FAILED",
                retryable=True,
            ) from exc
        if not allow_cpu_fallback:
            raise StageError(
                "GPU speech acceleration failed. Repair GPU acceleration or explicitly continue in slower CPU mode.",
                code="ASR_GPU_FALLBACK_REQUIRES_APPROVAL",
                retryable=True,
            ) from exc
        emit("GPU speech execution was unavailable; using CPU fallback (int8)…")
        del model
        gc.collect()
        try:
            cpu_model = load_cpu_model()
            result = cpu_model.transcribe(audio, batch_size=BATCH_SIZE)
        except Exception as fallback_exc:  # noqa: BLE001 - final typed boundary
            raise StageError(
                "Speech transcription could not complete. Retry with CPU acceleration or repair the speech runtime.",
                code="ASR_TRANSCRIPTION_FAILED",
                retryable=True,
            ) from fallback_exc
        return result, cpu_model, "cpu", "int8"


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
        import torch  # deferred: heavy import
        import whisperx

        capabilities = hardware.snapshot(config.home_dir())
        devices = hardware.select_asr_devices(capabilities)
        selected_device = devices["transcription_device"]
        selected_compute_type = devices["transcription_compute_type"]
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

        if transcription_device == "cuda" or alignment_device == "cuda":
            try:
                managed.activate_cuda_runtime()
            except Exception as exc:  # noqa: BLE001 - readiness should have caught this
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
            transcription_compute_type = str(cached.get("transcription_compute_type") or "int8")
            audio = whisperx.load_audio(str(audio_path))
            duration = float(len(audio)) / 16000.0
            ctx.emit(-1, "Reusing completed transcription; aligning words…")
        else:
            ctx.emit(-1, "Loading verified speech model…")
            model_load_device = transcription_device
            os.environ["CLIPGAUGE_ACCELERATOR"] = f"{transcription_device}/{transcription_compute_type}"
            ctx.emit(-1, f"Using {transcription_device.upper()} speech acceleration ({transcription_compute_type})…")
            model_started = time.monotonic()
            try:
                model = whisperx.load_model(
                    str(managed.asr_model_path()), transcription_device,
                    compute_type=transcription_compute_type, vad_method="silero", local_files_only=True,
                )
            except Exception as exc:  # noqa: BLE001 - provide reliable fallback
                if transcription_device != "cpu":
                    if long_job and not allow_cpu_fallback:
                        raise StageError(
                            "GPU speech acceleration failed. Repair GPU acceleration or explicitly continue in slower CPU mode.",
                            code="ASR_GPU_FALLBACK_REQUIRES_APPROVAL", retryable=True,
                        ) from exc
                    fallback_reason = "CUDA speech model load failed."
                    fallback_stages.append("model_load")
                    transcription_device, transcription_compute_type = "cpu", "int8"
                    acceleration = {**acceleration, "state": DEGRADED_ACCELERATION_STATE, "device": "cpu", "compute_type": "int8", "reason": fallback_reason}
                    os.environ["CLIPGAUGE_ACCELERATOR"] = "cpu/int8"
                    ctx.emit(-1, "GPU speech acceleration was unavailable; using CPU fallback (int8)…")
                    try:
                        model = whisperx.load_model(
                            str(managed.asr_model_path()), "cpu", compute_type="int8",
                            vad_method="silero", local_files_only=True,
                        )
                    except Exception as fallback_exc:  # noqa: BLE001
                        raise StageError(
                            "Speech transcription could not load its model. Repair the speech runtime in Setup Center and retry.",
                            code="ASR_MODEL_LOAD_FAILED", retryable=True,
                        ) from fallback_exc
                else:
                    raise StageError(
                        "Speech transcription could not load its model. Repair the speech runtime in Setup Center and retry.",
                        code="ASR_MODEL_LOAD_FAILED", retryable=True,
                    ) from exc
            audio = whisperx.load_audio(str(audio_path))
            duration = float(len(audio)) / 16000.0
            ctx.emit(-1, "Transcribing…")
            model_load_device = transcription_device
            model_load_secs = time.monotonic() - model_started
            transcription_started = time.monotonic()
            result, model, transcription_device, transcription_compute_type = _transcribe_with_fallback(
                model, audio=audio, device=transcription_device, compute_type=transcription_compute_type,
                load_cpu_model=lambda: whisperx.load_model(
                    str(managed.asr_model_path()), "cpu", compute_type="int8",
                    vad_method="silero", local_files_only=True,
                ),
                emit=lambda message: ctx.emit(-1, message),
                allow_cpu_fallback=allow_cpu_fallback or not long_job,
            )
            transcribe_secs = time.monotonic() - transcription_started
            if transcription_device == "cpu" and selected_device != "cpu":
                fallback_stages.append("transcription")
                fallback_reason = fallback_reason or "CUDA speech execution failed during transcription."
                acceleration = {**acceleration, "state": DEGRADED_ACCELERATION_STATE, "device": "cpu", "compute_type": "int8", "reason": fallback_reason}
            _save_transcription(ctx, audio_path, result, transcription_device, transcription_compute_type)
            del model
            gc.collect()

        language = result.get("language", "en")
        ctx.emit(-1, "Aligning words…")
        started = time.monotonic()
        policy = alignment_policy(language)
        align_model = None
        if policy.status == EXACT:
            try:
                align_model, align_meta = whisperx.load_align_model(
                    language_code=language, device=alignment_device, model_name=policy.model_name,
                    model_dir=str(managed.alignment_model_dir()), model_cache_only=True,
                )
                aligned = whisperx.align(
                    result["segments"], align_model, align_meta, audio, alignment_device,
                    return_char_alignments=False,
                )
            except Exception as exc:  # noqa: BLE001 - alignment can fall back to CPU
                if alignment_device != "cpu":
                    if long_job and not allow_cpu_fallback:
                        raise StageError(
                            "GPU speech acceleration failed during word alignment. Repair GPU acceleration or explicitly continue in slower CPU mode.",
                            code="ASR_GPU_FALLBACK_REQUIRES_APPROVAL", retryable=True,
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
                        aligned = whisperx.align(
                            result["segments"], align_model, align_meta, audio, "cpu",
                            return_char_alignments=False,
                        )
                    except Exception as fallback_exc:  # noqa: BLE001
                        raise StageError(
                            "Speech alignment could not complete. Retry with CPU acceleration or repair the speech runtime.",
                            code="ASR_ALIGNMENT_FAILED", retryable=True,
                        ) from fallback_exc
                else:
                    raise StageError(
                        "Speech alignment could not complete. Retry the job or repair the runtime.",
                        code="ASR_ALIGNMENT_FAILED", retryable=True,
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
            "fallback_stages": fallback_stages, "segments": segments, "word_count": word_count,
            "benchmark": {
                "audio_sec": round(duration, 1), "model_load_sec": round(model_load_secs, 1),
                "transcribe_sec": round(transcribe_secs, 1), "align_sec": round(align_secs, 1),
                "realtime_factor": round(duration / total, 2) if total > 0 else None,
            },
        }
