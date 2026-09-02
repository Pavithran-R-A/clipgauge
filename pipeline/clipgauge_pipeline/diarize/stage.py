"""Diarization stage: CAM++ embeddings over ASR speech windows → speaker
turns → word-level speaker labels merged back into the transcript."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..jobs.queue import Stage, StageContext, StageError
from ..memory import release_cpu_memory
from ..models import registry, specs


class DiarizeStage(Stage):
    name = "diarize"
    schema_version = 3  # v3: consume CUDA-qualified ASR checkpoints

    def run(self, ctx: StageContext) -> dict:
        prior = ctx.prior or {}
        ingest, asr = prior.get("ingest"), prior.get("asr")
        if not ingest or not asr:
            raise StageError("Diarization needs ingest + asr outputs.")
        audio_path = Path(ingest["audio_path"])
        if not audio_path.exists():
            raise StageError("Analysis audio missing — re-run ingest.")

        import torch

        from . import campplus, cluster

        ctx.emit(-1, "Loading speaker model…")
        try:
            ckpt = registry.ensure(specs.CAMPPLUS, lambda f, m: ctx.emit(f * 0.2, m))
        except Exception as exc:  # noqa: BLE001 - convert into an actionable stage contract
            detail = str(exc).lower()
            code = (
                "SPEAKER_MODEL_VERIFY_FAILED"
                if "verif" in detail or "sha" in detail or "hash" in detail
                else "SPEAKER_MODEL_DOWNLOAD_FAILED"
            )
            raise StageError(
                "Speaker analysis couldn’t start. The speaker model could not be downloaded or verified. Retry the download or repair the speaker model in Setup Center.",
                code=code,
                retryable=True,
            ) from exc
        device = torch.device("cpu")
        try:
            model = campplus.load_model(str(ckpt), device)
        except Exception as exc:  # noqa: BLE001 - model boundary is intentionally typed
            raise StageError(
                "Speaker analysis couldn’t start. The speaker model could not be loaded. Retry the model download or continue without speaker-aware reframing.",
                code="SPEAKER_MODEL_LOAD_FAILED",
                retryable=True,
            ) from exc

        from ..audio.io import load_mono

        try:
            y16k, _ = load_mono(audio_path, 16000)
            duration = len(y16k) / 16000.0
        except Exception as exc:  # noqa: BLE001 - audio boundary is intentionally typed
            raise StageError(
                "Speaker analysis couldn’t read the analysis audio. Re-run ingest or choose another video.",
                code="SPEAKER_AUDIO_LOAD_FAILED",
                retryable=True,
            ) from exc

        segments = asr["segments"]
        try:
            windows = campplus.speech_windows(segments, duration)
        except Exception as exc:  # noqa: BLE001 - malformed ASR data is actionable
            raise StageError(
                "Speaker analysis couldn’t prepare speech windows from the transcript. Retry transcription, then resume speaker analysis.",
                code="SPEAKER_ANALYSIS_FAILED",
                retryable=True,
            ) from exc
        if not windows:
            del model, y16k
            release_cpu_memory()
            return {"speakers": 0, "turns": [], "segments": segments}

        # Mid-stage cache: embedding an hour of speech costs real minutes and
        # the stage checkpoint only lands at the end — a crash after embedding
        # shouldn't re-pay it.
        cache_path = ctx.job_dir / "diar_embeddings.npy"
        embeddings = None
        if cache_path.exists():
            try:
                cached = np.load(cache_path)
            except Exception as exc:  # noqa: BLE001 - stale cache is recoverable
                raise StageError(
                    "Speaker analysis found a damaged embedding cache. Repair this job and resume speaker analysis.",
                    code="SPEAKER_CHECKPOINT_CORRUPT",
                    retryable=True,
                ) from exc
            if len(cached) == len(windows):
                embeddings = cached
                ctx.emit(0.8, "Embeddings cached")
        if embeddings is None:
            ctx.emit(0.25, f"Embedding {len(windows)} speech windows…")
            try:
                embeddings = campplus.embed_windows(
                    model, y16k, windows, device,
                    progress=lambda f: ctx.emit(0.25 + f * 0.55, "Embedding speech…"),
                )
                np.save(cache_path, embeddings)
            except Exception as exc:  # noqa: BLE001 - embedding boundary is intentionally typed
                raise StageError(
                    "Speaker analysis couldn’t analyze the speech windows. Retry speaker analysis or continue without speaker-aware reframing.",
                    code="SPEAKER_ANALYSIS_FAILED",
                    retryable=True,
                ) from exc

        ctx.emit(0.85, "Clustering speakers…")
        try:
            labels = cluster.cluster_windows(embeddings)
            turns = cluster.build_turns(windows, labels)
            cluster.assign_words(segments, turns)
        except Exception as exc:  # noqa: BLE001 - clustering boundary is intentionally typed
            raise StageError(
                "Speaker analysis couldn’t group the speakers. Retry speaker analysis or continue without speaker-aware reframing.",
                code="SPEAKER_CLUSTER_FAILED",
                retryable=True,
            ) from exc

        speakers = int(len(np.unique(labels))) if len(labels) else 0
        del model, y16k, embeddings
        release_cpu_memory()
        return {
            "speakers": speakers,
            "turns": turns,
            "segments": segments,  # transcript enriched with word/segment speakers
        }
