"""Versioned sidecar protocol, safe diagnostics, and terminal-event helpers."""

from __future__ import annotations

import re
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

PROTOCOL_VERSION = 1

_SECRET_PATTERNS = (
    re.compile(r"(?i)\bAIza[0-9A-Za-z_\-]{12,}"),
    re.compile(
        r"(?i)(\b(?:api[_-]?key|access[_-]?token|app[_-]?secret|client[_-]?secret|token|secret)\s*[:=]\s*)([^\s,;]+)"
    ),
    re.compile(r"(?i)(\bBearer\s+)([^\s,;]+)"),
    re.compile(r"(?i)([?&](?:key|api_key|access_token|token|authorization|app_secret)=[^&#\s]+)"),
    re.compile(r"(?i)(\bAuthorization\s*:\s*)([^\s,;]+(?:\s+[^\s,;]+)?)"),
)


def redact_text(text: str) -> str:
    """Remove credential-shaped values while retaining useful context."""
    value = text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 2:
            value = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", value)
        else:
            value = pattern.sub("[REDACTED]", value)
    return value


def diagnostic_id() -> str:
    return f"diag-{uuid.uuid4().hex[:16]}"


def write_diagnostic(job_dir: Path, stage: str, exc: BaseException) -> str:
    """Persist a bounded, redacted traceback in the job's private diagnostics dir."""
    identifier = diagnostic_id()
    directory = job_dir / "diagnostics"
    directory.mkdir(parents=True, exist_ok=True)
    trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    payload = redact_text(trace)[-64_000:]
    path = directory / f"{identifier}.log"
    path.write_text(f"stage={stage}\n{payload}", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return identifier


def safe_message(message: str, limit: int = 800) -> str:
    return redact_text(str(message)).strip()[-limit:]


@dataclass
class TerminalEmitter:
    """Guarantee at most one terminal event for a streamed operation."""

    emit: Callable[[dict[str, Any]], None]
    job_id: str | None = None
    emitted: bool = False

    def terminal(
        self,
        *,
        ok: bool,
        code: str,
        message: str,
        retryable: bool,
        stage: str | None = None,
        diagnostic: str | None = None,
        exit_code: int | None = None,
    ) -> bool:
        if self.emitted:
            return False
        event: dict[str, Any] = {
            "event": "terminal",
            "protocol_version": PROTOCOL_VERSION,
            "ok": bool(ok),
            "job_id": self.job_id,
            "stage": stage,
            "code": code,
            "message": safe_message(message),
            "retryable": bool(retryable),
        }
        if diagnostic:
            event["diagnostic_id"] = diagnostic
        if exit_code is not None:
            event["exit_code"] = exit_code
        self.emit({k: v for k, v in event.items() if v is not None})
        self.emitted = True
        return True
