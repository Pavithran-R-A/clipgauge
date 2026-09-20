import json

import pytest

from clipgauge_pipeline.mcp_server import McpService, reject_secret_arguments
from clipgauge_pipeline.server.auth import authorize, is_loopback, require_server_token


def test_mcp_rejects_secret_shaped_arguments():
    with pytest.raises(ValueError):
        reject_secret_arguments({"source": "video.mp4", "api_key": "do-not-accept"})


def test_mcp_tools_are_protocol_safe_without_running_jobs(capsys):
    service = McpService()
    assert service.call("preflight", {})["ok"] is True
    assert service.call("list_providers", {})
    service._executor.shutdown(wait=False, cancel_futures=True)
    assert capsys.readouterr().out == ""


def test_server_auth_defaults_to_loopback():
    assert is_loopback("127.0.0.1")
    assert is_loopback("::1")
    require_server_token("127.0.0.1", None)
    with pytest.raises(ValueError):
        require_server_token("0.0.0.0", None)
    assert authorize("secret", "secret")
    assert not authorize("wrong", "secret")
