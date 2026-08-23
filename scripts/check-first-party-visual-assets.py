#!/usr/bin/env python3
"""Reject retired ClipGauge brand colors in first-party visual assets.

The old grep gate was case-sensitive, so uppercase SVG values such as #8066FF
were missed. This gate normalizes textual colors and inspects raster pixels.
Run directly with Python when Pillow is installed, or through the pipeline
environment with: uv run --project pipeline python scripts/check-first-party-visual-assets.py
"""
from __future__ import annotations

import argparse
import colorsys
import re
import sys
import tempfile
from pathlib import Path
from typing import Iterable

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - exercised by an environment, not logic
    raise SystemExit(
        "Pillow is required for raster asset validation; run through `uv run --project pipeline`."
    ) from exc

ROOT = Path(__file__).resolve().parents[1]
TEXT_ROOTS = (ROOT / "app/src", ROOT / "app/src-tauri/icons", ROOT / "docs")
RASTER_ROOTS = (ROOT / "app/src-tauri/icons", ROOT / "docs/screenshots", ROOT / "docs/qa")
TEXT_EXTENSIONS = {".svg"}
RASTER_EXTENSIONS = {".png", ".ico", ".icns", ".jpg", ".jpeg", ".webp"}
RETIRED_HEX = {"#7357ff", "#8066ff", "#f2b84b", "#a97b22"}
RETIRED_WORDS = re.compile(r"\b(?:purple|violet|indigo|magenta|yellow|gold|amber)\b", re.IGNORECASE)
HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


def iter_files(roots: Iterable[Path], extensions: set[str]) -> Iterable[Path]:
    for root in roots:
        if not root.exists():
            continue
        yield from sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in extensions)


def scan_text(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    findings: list[str] = []
    for match in HEX.finditer(text):
        if match.group(0).lower() in RETIRED_HEX:
            findings.append(f"{path.relative_to(ROOT)}: retired color {match.group(0)}")
    for match in RETIRED_WORDS.finditer(text):
        findings.append(f"{path.relative_to(ROOT)}: retired brand word {match.group(0)}")
    return findings


def scan_raster(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        image = Image.open(path).convert("RGBA")
    except Exception as exc:
        return [f"{path.relative_to(ROOT)}: could not decode raster ({exc})"]
    exact = {tuple(bytes.fromhex(color[1:])): color for color in RETIRED_HEX}
    exact_hits = 0
    saturated_yellow = 0
    saturated_purple = 0
    for r, g, b, alpha in image.get_flattened_data():
        if alpha <= 8:
            continue
        if (r, g, b) in exact:
            exact_hits += 1
        hue, saturation, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        degrees = hue * 360
        if saturation >= 0.45 and value >= 0.35:
            if 35 <= degrees <= 75:
                saturated_yellow += 1
            elif 245 <= degrees <= 330:
                saturated_purple += 1
    if exact_hits:
        findings.append(f"{path.relative_to(ROOT)}: {exact_hits} pixels match retired exact colors")
    # The app icon family is ClipGauge-owned branding. Its accent pixels must
    # not be saturated yellow or purple; screenshots are evidence, not icons.
    if path.is_relative_to(ROOT / "app/src-tauri/icons") and saturated_yellow:
        findings.append(f"{path.relative_to(ROOT)}: {saturated_yellow} saturated yellow branding pixels")
    if path.is_relative_to(ROOT / "app/src-tauri/icons") and saturated_purple:
        findings.append(f"{path.relative_to(ROOT)}: {saturated_purple} saturated purple branding pixels")
    return findings


def run_gate() -> list[str]:
    findings: list[str] = []
    for path in iter_files(TEXT_ROOTS, TEXT_EXTENSIONS):
        findings.extend(scan_text(path))
    for path in iter_files(RASTER_ROOTS, RASTER_EXTENSIONS):
        findings.extend(scan_raster(path))
    return findings


def self_test() -> None:
    with tempfile.TemporaryDirectory() as temp:
        sample = Path(temp) / "sample.svg"
        sample.write_text('<svg><stop stop-color="#8066FF"/><desc>indigo</desc></svg>', encoding="utf-8")
        old_root = globals()["ROOT"]
        try:
            globals()["ROOT"] = Path(temp)
            findings = scan_text(sample)
        finally:
            globals()["ROOT"] = old_root
        if len(findings) != 2 or "#8066FF" not in findings[0] or "indigo" not in findings[1]:
            raise AssertionError(f"case-insensitive visual gate self-test failed: {findings}")
    print("visual-asset gate self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    findings = run_gate()
    if findings:
        print("first-party visual-asset gate failed:")
        print("\n".join(findings))
        return 1
    print("first-party visual-asset gate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
