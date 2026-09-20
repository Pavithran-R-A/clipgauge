"""Headless server boundary checks."""

from __future__ import annotations

import ipaddress
from typing import Any


def is_loopback(host: str) -> bool:
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def require_server_token(host: str, token: str | None) -> None:
    if not is_loopback(host) and not token:
        raise ValueError("a server token is required for non-loopback binding")


def authorize(provided: str | None, expected: str | None) -> bool:
    return expected is None or (provided is not None and provided == expected)


def reject_secret_payload(value: Any) -> None:
    from ..mcp_server import reject_secret_arguments

    reject_secret_arguments(value)
