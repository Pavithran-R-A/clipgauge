"""Strict, bounded SRT and WebVTT parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_SUBTITLE_BYTES = 10 * 1024 * 1024
_SRT_TIMESTAMP = re.compile(r"^(?P<h>\d{2,}):(?P<m>[0-5]\d):(?P<s>[0-5]\d)[,.](?P<ms>\d{3})$")
_VTT_TIMESTAMP = re.compile(r"^(?:(?P<h>\d{2,}):)?(?P<m>[0-5]\d):(?P<s>[0-5]\d)\.(?P<ms>\d{3})$")
_ARROW = re.compile(r"^\s*(?P<start>[^ ]+)\s+-->\s+(?P<end>[^ ]+)(?:\s+.*)?$")
_TAGS = re.compile(r"<[^>]{1,80}>")


@dataclass(frozen=True)
class SubtitleCue:
    start: float
    end: float
    text: str
    ordinal: int


class SubtitleParseError(ValueError):
    def __init__(self, message: str, *, malformed_cues: int = 0) -> None:
        super().__init__(message)
        self.malformed_cues = malformed_cues


def parse_timestamp(value: str, *, vtt: bool) -> float:
    match = (_VTT_TIMESTAMP if vtt else _SRT_TIMESTAMP).match(value.strip())
    if not match:
        raise SubtitleParseError(f"invalid subtitle timestamp: {value!r}")
    groups = match.groupdict()
    return (int(groups.get("h") or 0) * 3600) + int(groups["m"]) * 60 + int(groups["s"]) + int(groups["ms"]) / 1000


def _clean_text(lines: list[str]) -> str:
    text = " ".join(line.strip() for line in lines if line.strip())
    return re.sub(r"\s+", " ", _TAGS.sub("", text)).strip()


def _normalize(cues: list[SubtitleCue], duration: float | None) -> list[SubtitleCue]:
    ordered = sorted(cues, key=lambda cue: (cue.start, cue.end, cue.ordinal))
    output: list[SubtitleCue] = []
    bounded_duration = max(0.0, float(duration or 0.0))
    for cue in ordered:
        start = max(0.0, cue.start)
        end = min(cue.end, bounded_duration) if bounded_duration > 0 else cue.end
        if end <= start or not cue.text:
            continue
        if output and output[-1].end > start:
            previous = output[-1]
            output[-1] = SubtitleCue(previous.start, start, previous.text, previous.ordinal)
            if output[-1].end <= output[-1].start:
                output.pop()
        output.append(SubtitleCue(start, end, cue.text, cue.ordinal))
    return output


def parse_srt(text: str, duration: float | None = None) -> tuple[list[SubtitleCue], int]:
    blocks = re.split(r"\r?\n\s*\r?\n", text.strip())
    cues: list[SubtitleCue] = []
    malformed = 0
    for ordinal, block in enumerate(blocks):
        lines = [line.rstrip("\r") for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        arrow_index = next((index for index, line in enumerate(lines) if "-->" in line), None)
        if arrow_index is None or arrow_index + 1 >= len(lines):
            malformed += 1
            continue
        match = _ARROW.match(lines[arrow_index])
        if not match:
            malformed += 1
            continue
        try:
            start = parse_timestamp(match.group("start"), vtt=False)
            end = parse_timestamp(match.group("end"), vtt=False)
        except SubtitleParseError:
            malformed += 1
            continue
        if end <= start:
            malformed += 1
            continue
        text_value = _clean_text(lines[arrow_index + 1 :])
        if not text_value:
            malformed += 1
            continue
        cues.append(SubtitleCue(start, end, text_value, ordinal))
    normalized = _normalize(cues, duration)
    if not normalized:
        raise SubtitleParseError("subtitle file contains no usable cues", malformed_cues=malformed)
    return normalized, malformed


def parse_vtt(text: str, duration: float | None = None) -> tuple[list[SubtitleCue], int]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines or lines[0].strip().upper() != "WEBVTT":
        raise SubtitleParseError("WebVTT must begin with WEBVTT")
    cues: list[SubtitleCue] = []
    malformed = 0
    index = 1
    ordinal = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith(("NOTE", "STYLE", "REGION")):
            index += 1
            while index < len(lines) and lines[index].strip():
                index += 1
            continue
        if "-->" not in line:
            index += 1
            continue
        match = _ARROW.match(line)
        body_start = index + 1
        while body_start < len(lines) and not lines[body_start].strip():
            body_start += 1
        body_end = body_start
        while body_end < len(lines) and lines[body_end].strip():
            body_end += 1
        if not match:
            malformed += 1
        else:
            try:
                start = parse_timestamp(match.group("start"), vtt=True)
                end = parse_timestamp(match.group("end"), vtt=True)
                text_value = _clean_text(lines[body_start:body_end])
                if end <= start or not text_value:
                    raise SubtitleParseError("empty or reversed cue")
                cues.append(SubtitleCue(start, end, text_value, ordinal))
            except SubtitleParseError:
                malformed += 1
        ordinal += 1
        index = body_end
    normalized = _normalize(cues, duration)
    if not normalized:
        raise SubtitleParseError("subtitle file contains no usable cues", malformed_cues=malformed)
    return normalized, malformed
