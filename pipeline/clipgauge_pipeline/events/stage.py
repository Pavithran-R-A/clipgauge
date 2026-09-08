"""Events stage — the shared audio-event timeline (the architectural spine).

Channels:
  - jrgillick laughter specialist (native ~43 fps, high precision)
  - PANNs Cnn14_DecisionLevelMax (laugh/gasp/scream/shout/applause/cheer,
    320 ms effective resolution)
  - transcript long pauses
  - DSP energy/flux/dynamics curves (not events — continuous signals)

Fusion: per-channel DCASE post-processing, then IOU-0.4 cross-model merge
where agreement boosts confidence. Laughter is the only event type with two
independent detectors — by design (decision #2): it is the type that drives
the most visible behavior, so it gets the redundancy.

Consumed by: virality scoring (M2), caption [laughs] tags (M4), camera
punch-ins (M3), music mood (M2). Computed exactly once.
"""

from __future__ import annotations

import subprocess
import time
import gc
from pathlib import Path

from .. import config
from ..jobs.queue import Stage, StageContext, StageError, _atomic_write_json
from ..memory import release_cpu_memory
from ..models import managed, registry, specs
from .. import protocol
from ..render import ffmpeg_bin


def _extract_wav(media: Path, dst: Path, sr: int) -> None:
    proc = subprocess.run(
        [
            ffmpeg_bin.ffmpeg(), "-y", "-i", str(media),
            "-vn", "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(dst),
        ],
        capture_output=True, text=True, timeout=3600,
    )
    if proc.returncode != 0:
        raise StageError(f"Audio extraction failed: {(proc.stderr or '')[-500:]}")


def select_inference_device(torch_module, *, force_cpu: bool = False):
    """Use CUDA only after managed runtime verification; otherwise use CPU."""
    if force_cpu:
        return torch_module.device("cpu")
    try:
        managed.activate_cuda_runtime()
    except Exception:
        pass
    return torch_module.device("cuda" if torch_module.cuda.is_available() else "cpu")


class EventsStage(Stage):
    name = "events"
    schema_version = 5  # v5: bounded long-form channels and typed resource failures

    def artifacts_ok(self, ctx: StageContext, data: dict) -> bool:
        return (ctx.job_dir / "curves.json").exists()

    def run(self, ctx: StageContext) -> dict:
        prior = ctx.prior or {}
        ingest, asr = prior.get("ingest"), prior.get("asr")
        if not ingest or not asr:
            raise StageError("Events need ingest + asr outputs.")
        media = Path(ingest["media_path"])
        audio16 = Path(ingest["audio_path"])

        import json

        import numpy as np
        import torch

        from ..audio.io import iter_mono, resample, sample_count
        from ..vendor.laughter import model as laugh_model
        from ..vendor.laughter import segmenter as laugh_seg
        from ..vendor.panns import models as panns_models
        from . import dsp, panns_channel, post

        device = select_inference_device(
            torch,
            force_cpu=bool(getattr(ctx.settings, "allow_cpu_asr_fallback", False)),
        )
        bench: dict[str, float | str | int] = {"device": str(device)}
        events: list[dict] = []

        audio16_samples = sample_count(audio16)
        duration = audio16_samples / 16000.0

        # --- Channel 1 (optional): jrgillick laughter specialist ----------
        # OFF by default — PANNs' laughter classes cover the bus at a
        # fraction of the compute; this adds 10 ms precision + the
        # two-detector agreement boost when enabled.
        if getattr(ctx.settings, "laughter_specialist", False):
            ctx.emit(-1, "Detecting laughter (specialist)…")
            t0 = time.monotonic()
            ckpt = registry.ensure(specs.LAUGHTER, lambda f, m: ctx.emit(f * 0.05, m))
            lmodel = laugh_model.load_model(str(ckpt), device)
            laughs = laugh_seg.segment_stream(
                lmodel,
                (
                    resample(chunk, 16000, 8000)
                    for chunk in iter_mono(audio16, 16000, chunk_samples=480_000)
                ),
                int(audio16_samples * 8000 / 16000),
                duration,
                device,
                progress=lambda f: ctx.emit(0.05 + f * 0.3, "Detecting laughter (specialist)…"),
            )
            for item in laughs:
                events.append(
                    {
                        "type": "laugh",
                        "start": item["start"],
                        "end": item["end"],
                        "confidence": item["confidence"],
                        "sources": ["jrgillick"],
                    }
                )
            del lmodel
            gc.collect()
            if device.type == "cuda":
                torch.cuda.empty_cache()
            bench["laughter_sec"] = round(time.monotonic() - t0, 1)
            ctx.emit(0.35, f"{len(laughs)} laughter spans")

        # --- Channel 2: PANNs AudioSet tagger (32 kHz) --------------------
        ctx.emit(0.35, "Detecting audio events (PANNs)…")
        t0 = time.monotonic()
        ckpt = registry.ensure(specs.PANNS_CNN14_MAX, lambda f, m: ctx.emit(0.35 + f * 0.1, m))
        wav32 = ctx.job_dir / "audio32k.wav"
        if not wav32.exists():
            _extract_wav(media, wav32, panns_models.SAMPLE_RATE)
        audio32_samples = sample_count(wav32)
        pmodel = panns_models.load_model(str(ckpt), device)
        spans_by_type, fps = panns_channel.framewise_spans(
            pmodel,
            iter_mono(wav32, panns_models.SAMPLE_RATE, chunk_samples=int(panns_channel.CHUNK_SEC * panns_models.SAMPLE_RATE)),
            device,
            progress=lambda f: ctx.emit(0.45 + f * 0.35, "Detecting audio events…"),
            total_samples=audio32_samples,
            on_memory_error=lambda payload: protocol.write_json_diagnostic(
                ctx.job_dir,
                "events",
                {**payload, "duration_sec": round(duration, 3), "stage": "events"},
            ),
        )
        del pmodel
        gc.collect()
        if device.type == "cuda":
            torch.cuda.empty_cache()
        for etype, spans in spans_by_type.items():
            for start, end, peak in spans:
                events.append(
                    {
                        "type": etype,
                        "start": round(start, 3),
                        "end": round(end, 3),
                        "confidence": round(min(1.0, float(peak) / panns_channel.CONF_SCALE), 3),
                        "sources": ["panns"],
                    }
                )
        bench["panns_sec"] = round(time.monotonic() - t0, 1)
        bench["panns_chunks"] = int(max(1, audio32_samples // (panns_models.SAMPLE_RATE * 30) + 1))
        wav32.unlink(missing_ok=True)  # 32k wav is only needed here

        # --- Channel 3: transcript long pauses ----------------------------
        ctx.emit(0.81, "Finding pauses…")
        events.extend(dsp.long_pauses(asr["segments"]))

        # --- Fusion --------------------------------------------------------
        ctx.emit(0.84, "Fusing event timeline…")
        timeline = post.fuse(events)

        # --- Continuous curves (side file: big arrays stay out of the
        #     checkpoint JSON that other stages read constantly) ------------
        t0 = time.monotonic()
        ctx.emit(0.86, "Analyzing energy and dynamics…")
        try:
            curves = dsp.energy_curves(
                iter_mono(audio16, 16000, chunk_samples=160_000),
                total_samples=audio16_samples,
                progress=lambda fraction, message: ctx.emit(
                    0.86 + (max(0.0, fraction) * 0.07 if fraction >= 0 else 0.0),
                    message,
                ),
            )
        except MemoryError as exc:
            diagnostic_id = protocol.write_json_diagnostic(
                ctx.job_dir,
                "events",
                {
                    "code": "EVENT_DSP_MEMORY_EXHAUSTED",
                    "duration_sec": round(duration, 3),
                    "sample_rate": 16000,
                    "frame_count": audio16_samples // int(16000 * dsp.GRID_SEC) + 1,
                    "chunk_frames": dsp.ENERGY_CHUNK_FRAMES,
                    "stage": "events",
                    "error_type": type(exc).__name__,
                },
            )
            raise StageError(
                "Audio event analysis ran out of memory. Close other applications and retry; completed earlier stages remain reusable.",
                code="EVENT_DSP_MEMORY_EXHAUSTED",
                diagnostic_id=diagnostic_id,
            ) from exc
        bench["curves_sec"] = round(time.monotonic() - t0, 1)

        # --- Arousal (DSP fallback; remote SER disabled) ------------------
        ctx.emit(0.9, "Estimating arousal…")
        t0 = time.monotonic()
        from . import ser

        arousal = ser.arousal_curve_ser(
            None, asr["segments"], str(config.models_dir() / "ser"),
            progress=lambda f: ctx.emit(0.9 + f * 0.08, "Estimating arousal…"),
        )
        arousal_source = "ser"
        if arousal is None:
            arousal = ser.arousal_curve_dsp(curves["dynamics"], curves["grid_sec"])
            arousal_source = "dsp-proxy"
        bench["arousal_sec"] = round(time.monotonic() - t0, 1)
        curves["arousal"] = [round(float(v), 4) for v in arousal]
        curves["arousal_grid_sec"] = ser.GRID_SEC
        curves["arousal_source"] = arousal_source
        ctx.emit(0.99, "Finalizing audio analysis…")

        curves_path = ctx.job_dir / "curves.json"
        _atomic_write_json(curves_path, curves)

        by_type: dict[str, int] = {}
        for event in timeline:
            by_type[event["type"]] = by_type.get(event["type"], 0) + 1

        del curves, spans_by_type, events
        release_cpu_memory()
        return {
            "timeline": timeline,
            "counts": by_type,
            "curves_path": str(curves_path),
            "arousal_source": arousal_source,
            "duration_sec": round(duration, 1),
            "benchmark": bench,
            # Measured constant, recorded once for M3's punch-in math:
            "panns_effective_resolution_sec": 0.32,
        }
