"""Versioned readiness facts shared by setup and preflight surfaces."""

from __future__ import annotations

from typing import Any

READINESS_SCHEMA_VERSION = 1


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
