"""ASR + forced alignment via whisperX (BSD-2-Clause, pinned 3.8.6).

Word-level timestamps are the substrate for everything downstream: captions,
[laughs] tag placement, prosodic emphasis, long-pause detection, ducking,
and sentence-snapped candidate boundaries.

Model choice: large-v3-turbo int8 by default — near-parity accuracy with
large-v3 at a fraction of the compute, which is what makes local-first
viable on Apple Silicon. Silero VAD (MIT) instead of whisperX's bundled
pyannote VAD checkpoint, whose license the research flagged as unresolved.

The stage records wall-clock + realtime factor into its checkpoint — the M1
gate's Apple Silicon benchmark comes from real runs, not synthetic tests.
"""

from __future__ import annotations

import gc
import os
import time
from pathlib import Path

from .. import config, hardware
from .. import downloads
from ..models import managed
from ..jobs.queue import Stage, StageContext, StageError

ASR_MODEL = "large-v3-turbo"
COMPUTE_TYPE = "int8"
BATCH_SIZE = 8


def _point_caches_at_home() -> None:
    """Keep all library caches below the managed ClipGauge data root."""
    managed.apply_local_env()


def _transcribe_with_fallback(
    model,
    *,
    audio,
    device: str,
    compute_type: str,
    load_cpu_model,
    emit,
):
    """Retry transcription on CPU when accelerator execution fails."""
    try:
        return model.transcribe(audio, batch_size=BATCH_SIZE), model, device, compute_type
    except Exception as exc:  # noqa: BLE001 - accelerator failures vary by runtime
        if device == "cpu":
            raise StageError(
                "Speech transcription could not complete. Retry the job or repair the speech runtime.",
                code="ASR_TRANSCRIPTION_FAILED",
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


class AsrStage(Stage):
    name = "asr"
    schema_version = 1

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
        ctx.emit(-1, "Loading verified speech model…")
        import torch  # deferred: heavy import

        capabilities = hardware.snapshot(config.home_dir())
        device, compute_type = hardware.select_asr_accelerator(capabilities)
        acceleration = hardware.asr_readiness(capabilities)
        fallback_reason = None
        if device == "cuda":
            try:
                managed.activate_cuda_runtime()
            except Exception as exc:  # noqa: BLE001 - readiness should have caught this
                raise StageError(
                    "The verified CUDA speech runtime is unavailable. Repair Speech recognition in Setup Center.",
                    code="ASR_CUDA_RUNTIME_NOT_READY",
                    retryable=True,
                ) from exc
        import whisperx

        os.environ["CLIPGAUGE_ACCELERATOR"] = f"{device}/{compute_type}"
        ctx.emit(-1, f"Using {device.upper()} speech acceleration ({compute_type})…")
        t0 = time.monotonic()
        try:
            model = whisperx.load_model(
                str(managed.asr_model_path()), device, compute_type=compute_type,
                vad_method="silero", local_files_only=True,
            )
        except Exception as exc:  # noqa: BLE001 - provide a reliable CPU fallback
            if device != "cpu":
                fallback_reason = "CUDA speech model load failed."
                device, compute_type = "cpu", "int8"
                acceleration = {
                    **acceleration,
                    "state": "GPU PRESENT — RUNTIME DEGRADED",
                    "device": device,
                    "compute_type": compute_type,
                    "reason": fallback_reason,
                }
                os.environ["CLIPGAUGE_ACCELERATOR"] = "cpu/int8"
                ctx.emit(-1, "GPU speech acceleration was unavailable; using CPU fallback (int8)…")
                try:
                    model = whisperx.load_model(
                        str(managed.asr_model_path()), device, compute_type=compute_type,
                        vad_method="silero", local_files_only=True,
                    )
                except Exception as fallback_exc:  # noqa: BLE001 - final typed boundary
                    raise StageError(
                        "Speech transcription could not load its model. Repair the speech runtime in Setup Center and retry.",
                        code="ASR_MODEL_LOAD_FAILED",
                        retryable=True,
                    ) from fallback_exc
            else:
                raise StageError(
                    "Speech transcription could not load its model. Repair the speech runtime in Setup Center and retry.",
                    code="ASR_MODEL_LOAD_FAILED",
                    retryable=True,
                ) from exc
        audio = whisperx.load_audio(str(audio_path))
        duration = float(len(audio)) / 16000.0

        ctx.emit(-1, "Transcribing…")
        result, model, device, compute_type = _transcribe_with_fallback(
            model,
            audio=audio,
            device=device,
            compute_type=compute_type,
            load_cpu_model=lambda: whisperx.load_model(
                str(managed.asr_model_path()),
                "cpu",
                compute_type="int8",
                vad_method="silero",
                local_files_only=True,
            ),
            emit=lambda message: ctx.emit(-1, message),
        )
        if device == "cpu" and acceleration["device"] != "cpu":
            fallback_reason = fallback_reason or "CUDA speech execution failed during transcription."
            acceleration = {
                **acceleration,
                "state": "GPU PRESENT — RUNTIME DEGRADED",
                "device": "cpu",
                "compute_type": compute_type,
                "reason": fallback_reason,
            }
        language = result.get("language", "en")
        transcribe_secs = time.monotonic() - t0

        # Free ASR weights before loading the alignment model — peak RSS on a
        # 24 GB machine matters more than reload cost.
        del model
        gc.collect()

        ctx.emit(-1, "Aligning words…")
        t1 = time.monotonic()
        if language != "en":
            raise StageError(
                f"Word alignment for language '{language}' is not installed. Open Setup Center to approve its one-time language model.",
                code="ASR_ALIGNMENT_ASSET_NOT_READY",
                retryable=True,
            )
        try:
            align_model, align_meta = whisperx.load_align_model(
                language_code=language, device=device,
                model_name="WAV2VEC2_ASR_BASE_960H",
                model_dir=str(managed.alignment_model_dir()), model_cache_only=True,
            )
            aligned = whisperx.align(
                result["segments"], align_model, align_meta, audio, device,
                return_char_alignments=False,
            )
        except Exception as exc:  # noqa: BLE001 - alignment can fall back to CPU
            if device != "cpu":
                fallback_reason = "CUDA word alignment failed."
                device, compute_type = "cpu", "int8"
                acceleration = {
                    **acceleration,
                    "state": "GPU PRESENT — RUNTIME DEGRADED",
                    "device": device,
                    "compute_type": compute_type,
                    "reason": fallback_reason,
                }
                os.environ["CLIPGAUGE_ACCELERATOR"] = "cpu/int8"
                ctx.emit(-1, "Word alignment fell back to CPU…")
                try:
                    align_model, align_meta = whisperx.load_align_model(
                        language_code=language, device=device,
                        model_name="WAV2VEC2_ASR_BASE_960H",
                        model_dir=str(managed.alignment_model_dir()), model_cache_only=True,
                    )
                    aligned = whisperx.align(
                        result["segments"], align_model, align_meta, audio, device,
                        return_char_alignments=False,
                    )
                except Exception as fallback_exc:  # noqa: BLE001 - final typed boundary
                    raise StageError(
                        "Speech alignment could not complete. Retry with CPU acceleration or repair the speech runtime.",
                        code="ASR_ALIGNMENT_FAILED",
                        retryable=True,
                    ) from fallback_exc
            else:
                raise StageError(
                    "Speech alignment could not complete. Retry the job or repair the speech runtime.",
                    code="ASR_ALIGNMENT_FAILED",
                    retryable=True,
                ) from exc
        align_secs = time.monotonic() - t1
        del align_model
        gc.collect()
        if hasattr(torch, "mps") and torch.backends.mps.is_available():
            torch.mps.empty_cache()

        segments = []
        for seg in aligned["segments"]:
            words = [
                {
                    "word": w.get("word", "").strip(),
                    "start": round(float(w["start"]), 3),
                    "end": round(float(w["end"]), 3),
                    "score": round(float(w.get("score", 0.0)), 3),
                }
                for w in seg.get("words", [])
                if "start" in w and "end" in w
            ]
            segments.append(
                {
                    "start": round(float(seg["start"]), 3),
                    "end": round(float(seg["end"]), 3),
                    "text": seg.get("text", "").strip(),
                    "words": words,
                }
            )

        word_count = sum(len(s["words"]) for s in segments)
        if word_count == 0:
            raise StageError(
                "No speech was found in this video. ClipGauge needs dialogue to find moments."
            )

        total = transcribe_secs + align_secs
        return {
            "language": language,
            "model": ASR_MODEL,
            "compute_type": compute_type,
            "device": device,
            "accelerator": f"{device}/{compute_type}",
            "acceleration_state": acceleration["state"],
            "acceleration_reason": fallback_reason or acceleration["reason"],
            "segments": segments,
            "word_count": word_count,
            "benchmark": {
                "audio_sec": round(duration, 1),
                "transcribe_sec": round(transcribe_secs, 1),
                "align_sec": round(align_secs, 1),
                "realtime_factor": round(duration / total, 2) if total > 0 else None,
            },
        }
