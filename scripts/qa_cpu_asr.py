"""Qualify the real CPU/int8 CTranslate2 ASR path."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path


def _safe_error(error: BaseException) -> str:
    message = str(error).replace("\r", " ").replace("\n", " ")[:240]
    return re.sub(r"(?:[A-Za-z]:[\\/]|/)\S+", "<path>", message)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--audio",
        type=Path,
        default=repo_root / "pipeline" / "tests" / "fixtures" / "v041-jfk.flac",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payload: dict[str, object] = {
        "qualification": "cpu-asr-core",
        "audio_fixture": args.audio.name,
        "device": "cpu",
        "compute_type": "int8",
        "batch_size": 1,
    }
    started = time.perf_counter()
    try:
        sys.path.insert(0, str(repo_root / "pipeline"))
        from clipgauge_pipeline import hardware
        from clipgauge_pipeline.models import managed

        managed.apply_local_env()
        import ctranslate2

        supported = sorted(str(value) for value in ctranslate2.get_supported_compute_types("cpu"))
        payload["ctranslate2_version"] = str(getattr(ctranslate2, "__version__", "unknown"))
        payload["cpu_supported_compute_types"] = supported
        if "int8" not in supported:
            raise RuntimeError("CTranslate2 CPU int8 is unsupported")
        if not args.audio.is_file():
            raise RuntimeError("speech fixture is missing")
        if not (managed.asr_model_path() / "model.bin").is_file():
            raise RuntimeError("verified speech model is missing")

        from faster_whisper import BatchedInferencePipeline, WhisperModel

        model = WhisperModel(str(managed.asr_model_path()), device="cpu", compute_type="int8")
        inference = BatchedInferencePipeline(model)
        segments, info = inference.transcribe(
            str(args.audio),
            batch_size=1,
            beam_size=1,
            vad_filter=False,
        )
        segment_count = sum(1 for _ in segments)
        if segment_count < 1:
            raise RuntimeError("CPU ASR returned no speech segments")
        payload.update({
            "ok": True,
            "segment_count": segment_count,
            "audio_seconds": round(float(getattr(info, "duration", 0.0)), 3),
            "model_revision": managed.ASR_REVISION,
            "hardware_policy": hardware.cpu_asr_policy({
                "ram_bytes": 8 * hardware.GIB,
                "cpu_ctranslate2": {"compute_types": supported},
            }),
        })
    except Exception as error:  # noqa: BLE001 - qualification must report a bounded result
        payload.update({
            "ok": False,
            "exception_class": type(error).__name__,
            "sanitized_exception_message": _safe_error(error),
        })
    payload["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
