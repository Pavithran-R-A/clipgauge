"""Supported source classification and platform-caption policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit
from typing import Any


class SourcePlatform(str, Enum):
    LOCAL = "local"
    YOUTUBE = "youtube"
    BILIBILI = "bilibili"
    UNSUPPORTED_URL = "unsupported_url"


@dataclass(frozen=True)
class PlatformCaption:
    language: str
    url: str
    automatic: bool
    ext: str | None = None
    extractor: str | None = None


def caption_tracks(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize yt-dlp human and automatic caption entries."""
    tracks: list[dict[str, Any]] = []
    for field, automatic in (("subtitles", False), ("automatic_captions", True)):
        values = metadata.get(field)
        if not isinstance(values, dict):
            continue
        extractor = metadata.get("extractor_key") or metadata.get("extractor")
        extractor = str(extractor)[:80] if extractor else None
        for language, entries in sorted(values.items(), key=lambda item: str(item[0]).lower()):
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                url = entry.get("url") or entry.get("manifest_url")
                if not isinstance(url, str) or not url.strip():
                    continue
                ext = entry.get("ext") if isinstance(entry.get("ext"), str) else None
                if ext and ext.lower() not in {"srt", "vtt"}:
                    continue
                tracks.append({
                    "language": str(language),
                    "url": url,
                    "automatic": automatic,
                    "ext": ext,
                    "source": "platform_automatic" if automatic else "platform_human",
                    "extractor": extractor,
                })
    return tracks


def classify_source(value: str) -> SourcePlatform:
    parsed = urlsplit(str(value).strip())
    if parsed.scheme not in {"http", "https"}:
        return SourcePlatform.LOCAL
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host == "youtu.be" or host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
        return SourcePlatform.YOUTUBE
    if host == "b23.tv" or host.endswith("bilibili.com"):
        path = parsed.path.lower()
        if host == "b23.tv" or "/video/bv" in path or "/video/av" in path:
            return SourcePlatform.BILIBILI
    return SourcePlatform.UNSUPPORTED_URL


def select_platform_caption(tracks: list[dict], *, requested_language: str | None = None) -> PlatformCaption | None:
    usable: list[PlatformCaption] = []
    for track in tracks:
        if not isinstance(track, dict):
            continue
        url = track.get("url") or track.get("manifest_url")
        language = track.get("language") or track.get("lang")
        if not isinstance(url, str) or not url or not isinstance(language, str) or not language:
            continue
        usable.append(PlatformCaption(language, url, bool(track.get("automatic")), track.get("ext"), track.get("extractor")))
    if not usable:
        return None
    requested = (requested_language or "").lower()
    return sorted(
        usable,
        key=lambda item: (
            0 if requested and item.language.lower().startswith(requested) else 1,
            0 if not item.automatic else 1,
            item.language.lower(),
            item.url,
        ),
    )[0]


def map_bilibili_error(message: str) -> str:
    lowered = message.lower()
    if "login" in lowered or "sign in" in lowered or "cookie" in lowered:
        return "BILIBILI_LOGIN_REQUIRED"
    if "private" in lowered or "members" in lowered or "restricted" in lowered:
        return "BILIBILI_ACCESS_RESTRICTED"
    if "not found" in lowered or "unavailable" in lowered or "removed" in lowered:
        return "BILIBILI_MEDIA_UNAVAILABLE"
    if "metadata" in lowered:
        return "BILIBILI_METADATA_FAILED"
    return "BILIBILI_DOWNLOAD_FAILED"
