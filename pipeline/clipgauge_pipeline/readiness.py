"""Versioned readiness facts shared by setup and preflight surfaces."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

READINESS_SCHEMA_VERSION = 1
PROVIDER_READINESS_SCHEMA_VERSION = 1


class ProviderReadinessResult(TypedDict):
    readiness_schema_version: int
    provider: str
    locality: Literal["local", "cloud"]
    configured: bool
    credential_ready: bool
    endpoint_ready: bool
    model_ready: bool
    model_available: bool
    model_compatible: bool
    can_private: bool
    can_hybrid: bool
    can_best: bool
    blocking_reasons: list[str]
    warnings: list[str]


def provider_readiness(
    profile: Any,
    *,
    credential_ready: bool | None = None,
    endpoint_ready: bool | None = None,
    model_available: bool | None = None,
    model_compatible: bool | None = None,
    runtime_ready: bool = True,
    local_model_ready: bool = True,
    service_ready: bool = True,
) -> ProviderReadinessResult:
    """Evaluate provider configuration and capability readiness once."""
    provider = str(profile.kind)
    locality = "local" if str(profile.locality).lower() == "local" else "cloud"
    model = str(getattr(profile, "model", "")).strip()
    auth_strategy = str(getattr(profile, "auth_strategy", "none"))
    endpoint = str(getattr(profile, "endpoint_identity", "")).strip()
    credential = auth_strategy == "none" if credential_ready is None else bool(credential_ready)
    endpoint_required = provider in {"cloudflare", "custom"}
    endpoint_ok = bool(endpoint) if endpoint_ready is None and endpoint_required else True if endpoint_ready is None else bool(endpoint_ready)
    model_ok = bool(model) and model.casefold() != "model required"
    available = model_ok if model_available is None else bool(model_available)
    compatible = True if model_compatible is None else bool(model_compatible)
    blocking: list[str] = []
    if not credential:
        blocking.append("Save credential")
    if not endpoint_ok:
        blocking.append("Enter endpoint")
    if not model_ok:
        blocking.append("Choose a model")
    elif not available or not compatible:
        blocking.append("Choose a compatible model")
    if locality == "local" and not local_model_ready:
        blocking.append("Choose a ready local model")
    if locality == "local" and not runtime_ready:
        blocking.append("Install or repair the local runtime")
    if locality == "local" and not service_ready:
        action = {
            "ollama": "Test/start Ollama",
            "lmstudio": "Test/start LM Studio",
        }.get(provider, "Repair ClipGauge Local")
        blocking.append(action)
    configured = not blocking
    return {
        "readiness_schema_version": PROVIDER_READINESS_SCHEMA_VERSION,
        "provider": provider,
        "locality": locality,
        "configured": configured,
        "credential_ready": credential,
        "endpoint_ready": endpoint_ok,
        "model_ready": model_ok,
        "model_available": available,
        "model_compatible": compatible,
        "can_private": locality == "local" and configured,
        "can_hybrid": locality == "cloud" and configured,
        "can_best": locality == "cloud" and configured,
        "blocking_reasons": blocking,
        "warnings": [],
    }


def contract(
    *,
    asset_id: str,
    installed: bool,
    verified: bool,
    usable: bool,
    repair: bool,
    selected_runtime: str | None = None,
    selected_model: str | None = None,
    actual_additional_bytes: int = 0,
    repair_reason: str | None = None,
) -> dict[str, Any]:
    """Return the stable fields every readiness producer must expose."""
    result: dict[str, Any] = {
        "readiness_schema_version": READINESS_SCHEMA_VERSION,
        "asset_id": asset_id,
        "installed": bool(installed),
        "verified": bool(verified),
        "usable": bool(usable),
        "repair": bool(repair),
        "selected_runtime": selected_runtime,
        "selected_model": selected_model,
        "actual_additional_bytes": max(0, int(actual_additional_bytes)),
    }
    if repair_reason:
        result["repair_reason"] = repair_reason
    return result
