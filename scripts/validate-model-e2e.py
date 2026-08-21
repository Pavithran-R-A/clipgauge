#!/usr/bin/env python3
"""Validate the production-default model-backed release E2E evidence."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

REQUIRED_STAGES = {"ingest", "asr", "diarize", "events", "candidates", "score", "camera", "render"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("job_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    events = [json.loads(line) for line in args.log.read_text(encoding="utf-8").splitlines() if line.strip().startswith("{")]
    terminal = next((event for event in reversed(events) if event.get("event") == "terminal"), None)
    if not terminal or terminal.get("ok") is not True:
        raise SystemExit(f"model E2E did not finish successfully: {terminal!r}")
    observed = {str(event.get("stage")) for event in events if event.get("event") == "progress" and event.get("stage")}
    missing = REQUIRED_STAGES - observed
    if missing:
        raise SystemExit(f"model E2E is missing stages: {sorted(missing)}")
    if not args.output.is_file() or args.output.stat().st_size <= 0:
        raise SystemExit(f"model E2E output is missing or empty: {args.output}")

    probe = json.loads(
        subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration,size:stream=index,codec_name,codec_type,width,height", "-of", "json", str(args.output)
            ],
            text=True,
        )
    )
    streams = probe.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    duration = float(probe.get("format", {}).get("duration", 0) or 0)
    if not video or video.get("width") != 1080 or video.get("height") != 1920:
        raise SystemExit(f"model E2E output is not production-default 1080x1920: {video!r}")
    if not audio or duration <= 0:
        raise SystemExit("model E2E output lacks a positive-duration audio/video container")

    render_path = args.job_dir / "render.json"
    render = json.loads(render_path.read_text(encoding="utf-8"))
    render_data = render.get("data", render)
    if render_data.get("captions_burned") is not True:
        raise SystemExit(f"model E2E output did not burn captions: {render_data!r}")

    summary = {
        "terminal": terminal,
        "stages": sorted(observed),
        "output": str(args.output),
        "sha256": subprocess.check_output(["sha256sum", str(args.output)], text=True).split()[0],
        "probe": probe,
        "render": render_data,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
