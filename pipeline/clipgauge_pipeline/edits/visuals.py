"""Visual-overlay planning + fetching.

Planner: one LLM call over the clip's transcript proposes overlays — the
explicit things being talked about (objects, places, amounts, situations).
Deliberately generous (the user wants overdone-and-removable); every item
lands on the timeline where it can be deleted, moved, resized.

Fetchers: Pexels (free BYO key, real photos, license-clean) and Gemini
image generation (the funded key's image models — on-topic for absurd or
specific scenes stock can't match). Images cache into
<job_dir>/overlays/ and are referenced by path in the edit state.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from base64 import b64decode
from binascii import Error as Base64DecodeError
from pathlib import Path
from typing import Any

import httpx

from .. import config
from ..scoring import llm as llm_mod
from ..scoring import providers as providers_mod
from .timeline import Overlay

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "visuals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "phrase": {"type": "string", "description": "the exact spoken words this illustrates"},
                    "query": {"type": "string", "description": "short image search / generation prompt"},
                    "start_word_index": {"type": "integer"},
                    "duration_sec": {"type": "number", "description": "1.5-3.0 typical"},
                    "kind": {"type": "string", "enum": ["object", "place", "person", "number", "situation"]},
                },
                "required": ["phrase", "query", "start_word_index", "duration_sec", "kind"],
            },
        }
    },
    "required": ["visuals"],
}


def plan_prompt(numbered_words: str) -> str:
    return (
        "You are planning illustrative pop-over images for a short vertical "
        "clip. Below is the transcript with word indices. Propose a visual "
        "for EVERY explicit thing mentioned — objects, animals, places, "
        "amounts of money, named people, concrete situations. Be generous; "
        "the editor deletes what they don't want. Do not propose visuals "
        "for abstract talk with nothing depictable.\n\n"
        f"{numbered_words}\n\n"
        "query: a concrete image description, e.g. 'possum close up', "
        "'stack of hundred dollar bills', 'las vegas strip at night'. "
        "start_word_index: where the phrase begins. duration_sec: 1.5-3."
    )


def plan_overlays(words: list[dict], provider: providers_mod.ProviderProfile | str) -> list[dict]:
    """Words carry OUTPUT-timeline times; provider identity is explicit."""
    numbered = " ".join(f"[{i}]{w['word']}" for i, w in enumerate(words))
    profile = providers_mod.legacy_profile(provider) if isinstance(provider, str) else provider
    result = providers_mod.make_adapter(profile).infer(
        providers_mod.InferenceRequest(prompt=plan_prompt(numbered), schema=PLAN_SCHEMA)
    ).data
    plans = []
    for v in result.get("visuals", []):
        idx = max(0, min(int(v["start_word_index"]), len(words) - 1))
        start = words[idx]["start"]
        plans.append(
            {
                "phrase": v["phrase"],
                "query": v["query"],
                "start": round(start, 2),
                "end": round(start + max(1.0, min(4.0, float(v["duration_sec"]))), 2),
                "kind": v["kind"],
            }
        )
    return plans


def _overlay_dir(job_dir: Path) -> Path:
    d = job_dir / "overlays"
    d.mkdir(exist_ok=True)
    return d


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass
        raise


def pexels_key() -> str | None:
    key = os.environ.get("CLIPGAUGE_PEXELS_API_KEY")
    return key.strip() if key and key.strip() else None


def fetch_pexels(query: str, job_dir: Path) -> str | None:
    key = pexels_key()
    if not key:
        return None
    dest = _overlay_dir(job_dir) / f"px_{hashlib.sha256(query.encode()).hexdigest()[:12]}.jpg"
    if dest.exists():
        return str(dest)
    try:
        res = httpx.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            headers={"Authorization": key},
            timeout=20.0,
        )
        res.raise_for_status()
        payload = res.json()
        photos = payload.get("photos", []) if isinstance(payload, dict) else []
        if not isinstance(photos, list) or not photos or not isinstance(photos[0], dict):
            return None
        source = photos[0].get("src")
        image_url = source.get("large") if isinstance(source, dict) else None
        if not isinstance(image_url, str) or not image_url:
            return None
        img = httpx.get(image_url, timeout=30.0)
        img.raise_for_status()
        if not img.content:
            return None
        _atomic_write_bytes(dest, img.content)
        return str(dest)
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return None


GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"


def fetch_gemini(query: str, job_dir: Path) -> str | None:
    key = providers_mod.secret_from_environment(providers_mod.legacy_profile("gemini"))
    if not key:
        return None
    dest = _overlay_dir(job_dir) / f"gm_{hashlib.sha256(query.encode()).hexdigest()[:12]}.png"
    if dest.exists():
        return str(dest)
    try:
        res = httpx.post(
            llm_mod.GEMINI_URL.format(model=GEMINI_IMAGE_MODEL),
            headers={"x-goog-api-key": key},
            json={
                "contents": [{"parts": [{"text": f"A clean, punchy illustrative photo for a video overlay: {query}. No text in the image."}]}],
                "generationConfig": {"responseModalities": ["IMAGE"]},
            },
            timeout=60.0,
        )
        res.raise_for_status()
        payload = res.json()
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        first = candidates[0] if isinstance(candidates, list) and candidates else None
        content = first.get("content") if isinstance(first, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            return None
        for part in parts:
            if not isinstance(part, dict):
                continue
            data = part.get("inlineData") or part.get("inline_data")
            encoded = data.get("data") if isinstance(data, dict) else None
            if isinstance(encoded, str) and encoded:
                image = b64decode(encoded, validate=True)
                if not image:
                    continue
                _atomic_write_bytes(dest, image)
                return str(dest)
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError, Base64DecodeError):
        return None
    return None


def fetch_image(query: str, job_dir: Path, prefer: str = "pexels") -> tuple[str | None, str]:
    """(path, source). Tries the preferred source, falls back to the other."""
    order = ["pexels", "gemini"] if prefer == "pexels" else ["gemini", "pexels"]
    for source in order:
        path = fetch_pexels(query, job_dir) if source == "pexels" else fetch_gemini(query, job_dir)
        if path:
            return path, source
    return None, "none"


def suggest(job_dir: Path, words: list[dict], provider: providers_mod.ProviderProfile | str, prefer: str = "pexels") -> list[Overlay]:
    """Plan + fetch, returning ready Overlay items (static by default —
    animation strictly opt-in per the design decision)."""
    plans = plan_overlays(words, provider)
    out: list[Overlay] = []
    for i, plan in enumerate(plans):
        path, source = fetch_image(plan["query"], job_dir, prefer)
        if not path:
            continue
        out.append(
            Overlay(
                id=f"ov{i}_{hashlib.sha256(plan['query'].encode()).hexdigest()[:6]}",
                query=plan["query"],
                source=source,
                image_path=path,
                start=plan["start"],
                end=plan["end"],
                animation="none",
                phrase=plan["phrase"],
            )
        )
    return out
