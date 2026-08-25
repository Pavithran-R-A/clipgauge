"""Pure local-model lifecycle and selection policy helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

RECOMMENDED_MODEL_ID = "clipgauge-local/qwen3-4b-q4_k_m"
SELECTION_FILENAME = "local-ai-settings.json"


def load_selected_model(root: Path) -> str | None:
    try:
        payload = json.loads((root / SELECTION_FILENAME).read_text(encoding="utf-8"))
        value = payload.get("selected_model_id") if isinstance(payload, dict) else None
        return str(value) if value else None
    except (OSError, ValueError, TypeError):
        return None


def save_selected_model(root: Path, model_id: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / SELECTION_FILENAME
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(json.dumps({"selected_model_id": model_id}, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _is_repair(row: Mapping[str, Any]) -> bool:
    value = f"{row.get('status', '')} {row.get('state', '')}".lower()
    return any(token in value for token in ("repair", "invalid", "failed", "unreadable"))


def _is_verified(row: Mapping[str, Any]) -> bool:
    return bool(row.get("installed")) and not _is_repair(row)


def select_model_id(rows: Iterable[Mapping[str, Any]], persisted_id: str | None = None, recommended_id: str = RECOMMENDED_MODEL_ID) -> str | None:
    rows = list(rows)
    valid_ids = [str(row.get("asset_id")) for row in rows if _is_verified(row) and row.get("asset_id")]
    if persisted_id and persisted_id in valid_ids:
        return persisted_id
    if valid_ids:
        return valid_ids[0]
    if any(str(row.get("asset_id")) == recommended_id for row in rows):
        return recommended_id
    return str(rows[0].get("asset_id")) if rows and rows[0].get("asset_id") else None


def enrich_model_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    size = int(result.get("size_bytes") or 0)
    installed = _is_verified(result)
    if _is_repair(result):
        lifecycle = "NEEDS_REPAIR"
        label = "Needs repair"
    elif installed:
        lifecycle = "VERIFIED"
        label = "Installed · reused for future videos"
    else:
        lifecycle = "DOWNLOAD_REQUIRED"
        label = "Download required"
    result.update(
        {
            "lifecycle_state": lifecycle,
            "lifecycle_label": label,
            "verified": installed,
            "required_download_bytes": 0 if installed else size,
            "installed_size_bytes": int(result.get("installed_size_bytes") or (size if installed else 0)),
        }
    )
    return result
