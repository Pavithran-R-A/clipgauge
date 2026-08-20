"""Backward-compatible scoring facade for the v0.2 provider architecture."""

from __future__ import annotations

import os

from .providers import (
    CapabilitySet,
    GeminiAdapter,
    InferenceRequest,
    OllamaAdapter,
    ProviderError,
    ProviderProfile,
    cache_key,
    legacy_profile,
    make_adapter,
)

GEMINI_MODEL = "gemini-flash-latest"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OLLAMA_URL = "http://localhost:11434"
LLM_TIMEOUT = 120.0

LlmError = ProviderError


def gemini_api_key() -> str | None:
    key = os.environ.get("CLIPGAUGE_GEMINI_API_KEY")
    return key.strip() if key and key.strip() else None


def _cache_dir():
    from .providers import _cache_dir as provider_cache_dir

    return provider_cache_dir()


def _cache_key(backend: str, model: str, prompt: str, schema: dict, images: list[bytes]) -> str:
    profile = legacy_profile(backend, model)
    return cache_key(profile, InferenceRequest(prompt=prompt, schema=schema, images=images))


class GeminiClient(GeminiAdapter):
    def __init__(self, model: str = GEMINI_MODEL):
        super().__init__(legacy_profile("gemini", model))


class OllamaClient(OllamaAdapter):
    def __init__(self, model: str | None = None):
        super().__init__(legacy_profile("ollama", model or "auto"))


def make_client(llm_mode: str | ProviderProfile):
    return make_adapter(llm_mode)


__all__ = [
    "CapabilitySet",
    "GeminiClient",
    "InferenceRequest",
    "LlmError",
    "OllamaClient",
    "ProviderError",
    "ProviderProfile",
    "make_client",
]
