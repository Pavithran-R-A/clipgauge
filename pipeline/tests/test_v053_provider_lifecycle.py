from __future__ import annotations

import threading
from pathlib import Path

import httpx
import pytest

from clipgauge_pipeline import runtime
from clipgauge_pipeline.ingest import youtube_compat


class FakeProcess:
    _next_pid = 41000

    def __init__(self, *, returncode: int | None = None):
        self.pid = FakeProcess._next_pid
        FakeProcess._next_pid += 1
        self.returncode = returncode
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminate_calls += 1
        self.returncode = -15

    def kill(self):
        self.kill_calls += 1
        self.returncode = -9

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


@pytest.fixture
def provider_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_compat, "_server_ready", lambda: True)
    monkeypatch.setattr(youtube_compat, "_root", lambda: tmp_path)
    monkeypatch.setattr(youtube_compat, "node_path", lambda: tmp_path / "node")
    monkeypatch.setattr(youtube_compat, "server_home", lambda: tmp_path)
    (tmp_path / "node").touch()


@pytest.fixture
def fake_popen(monkeypatch):
    processes = []

    def popen(*args, **kwargs):
        process = FakeProcess()
        processes.append(process)
        return process

    monkeypatch.setattr(youtube_compat.subprocess, "Popen", popen)
    return processes


def test_successful_startup_records_ownership_before_return(provider_ready, fake_popen, monkeypatch):
    supervisor = youtube_compat.ProviderSupervisor()
    responses = iter([
        {"running": False, "healthy": False, "version": None},
        {"running": False, "healthy": False, "version": None},
        {"running": True, "healthy": True, "version": "1.3.2"},
    ])
    monkeypatch.setattr(supervisor, "health", lambda: next(responses))

    endpoint = supervisor.start()

    assert endpoint == "http://127.0.0.1:4416"
    assert supervisor.handle is not None
    assert supervisor.handle.process is fake_popen[0]


def test_provider_exits_before_health_is_classified(provider_ready, fake_popen, monkeypatch):
    process = FakeProcess(returncode=1)
    fake_popen.append(process)
    monkeypatch.setattr(youtube_compat.subprocess, "Popen", lambda *args, **kwargs: process)
    supervisor = youtube_compat.ProviderSupervisor()
    monkeypatch.setattr(supervisor, "health", lambda: {"running": False, "healthy": False, "version": None})

    with pytest.raises(runtime.RuntimeIntegrityError, match="PROCESS_EXITED"):
        supervisor.start()

    assert supervisor.handle is None
    assert process.poll() is not None


def test_health_timeout_terminates_spawned_child(provider_ready, fake_popen, monkeypatch):
    supervisor = youtube_compat.ProviderSupervisor()
    monkeypatch.setattr(supervisor, "health", lambda: {"running": False, "healthy": False, "version": None})
    clock = iter([0.0, 31.0])
    monkeypatch.setattr(youtube_compat.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(youtube_compat.time, "sleep", lambda _: None)

    with pytest.raises(runtime.RuntimeIntegrityError, match="HEALTH_TIMEOUT"):
        supervisor.start()

    process = fake_popen[0]
    assert process.poll() is not None
    assert process.terminate_calls or process.kill_calls
    assert supervisor.handle is None


def test_stop_is_idempotent(provider_ready, fake_popen):
    supervisor = youtube_compat.ProviderSupervisor()
    process = FakeProcess()
    supervisor.handle = youtube_compat.ProviderHandle(process=process, endpoint="http://127.0.0.1:4416")

    supervisor.stop()
    supervisor.stop()

    assert process.poll() is not None
    assert supervisor.handle is None
    assert process.terminate_calls == 1


def test_failed_health_test_leaves_zero_spawned_children(provider_ready, fake_popen, monkeypatch):
    status = {
        "state": "DEPENDENCIES_READY",
        "ready": True,
        "dependency_state": "DEPENDENCIES_READY",
        "public_download_verified": False,
        "checks": [],
    }
    monkeypatch.setattr(youtube_compat, "readiness", lambda: status)
    supervisor_health = {"running": False, "healthy": False, "version": None}
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, "health", lambda self: supervisor_health)
    clock = iter([0.0, 31.0])
    monkeypatch.setattr(youtube_compat.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(youtube_compat.time, "sleep", lambda _: None)

    result = youtube_compat.test()

    assert result["state"] == "UNHEALTHY"
    assert result["startup_error_code"] == "HEALTH_TIMEOUT"
    assert fake_popen[0].poll() is not None


def test_repeated_start_stop_start_succeeds(provider_ready, fake_popen, monkeypatch):
    supervisor = youtube_compat.ProviderSupervisor()
    responses = iter([
        {"running": False, "healthy": False, "version": None},
        {"running": True, "healthy": True, "version": "1.3.2"},
        {"running": False, "healthy": False, "version": None},
        {"running": True, "healthy": True, "version": "1.3.2"},
    ])
    monkeypatch.setattr(supervisor, "health", lambda: next(responses))

    supervisor.start()
    first = supervisor.handle.process
    supervisor.stop()
    supervisor.start()
    second = supervisor.handle.process

    assert first is not second
    assert first.poll() is not None
    assert second.poll() is None


def test_healthy_listener_with_expected_version_is_reused(provider_ready, fake_popen, monkeypatch):
    supervisor = youtube_compat.ProviderSupervisor()
    monkeypatch.setattr(supervisor, "health", lambda: {"running": True, "healthy": True, "version": "1.3.2", "address_family": "ipv4"})

    assert supervisor.start() == "http://127.0.0.1:4416"
    assert fake_popen == []


def test_wrong_version_listener_is_rejected_before_spawn(provider_ready, fake_popen, monkeypatch):
    supervisor = youtube_compat.ProviderSupervisor()
    monkeypatch.setattr(supervisor, "health", lambda: {"running": True, "healthy": False, "version": "9.9.9"})

    with pytest.raises(runtime.RuntimeIntegrityError, match="VERSION_MISMATCH"):
        supervisor.start()

    assert fake_popen == []


def test_unrelated_listener_is_rejected_explicitly(provider_ready, fake_popen, monkeypatch):
    supervisor = youtube_compat.ProviderSupervisor()
    monkeypatch.setattr(supervisor, "health", lambda: {"running": True, "healthy": False, "version": None})

    with pytest.raises(runtime.RuntimeIntegrityError, match="PORT_IN_USE"):
        supervisor.start()

    assert fake_popen == []


def test_health_accepts_ipv6_when_ipv4_is_unreachable(monkeypatch):
    calls = []

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"version": "1.3.2", "server_uptime": 1.0}

    def get(url, **kwargs):
        calls.append(url)
        if "127.0.0.1" in url:
            raise httpx.ConnectError("ipv4 unavailable")
        return Response()

    monkeypatch.setattr(youtube_compat.httpx, "get", get)
    result = youtube_compat.ProviderSupervisor().health()

    assert result["healthy"] is True
    assert result["address_family"] == "ipv6"
    assert calls == ["http://127.0.0.1:4416/ping", "http://[::1]:4416/ping"]


def test_health_accepts_ipv4_when_ipv6_is_unreachable(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"version": "1.3.2", "server_uptime": 1.0}

    def get(url, **kwargs):
        if "[::1]" in url:
            raise httpx.ConnectError("ipv6 unavailable")
        return Response()

    monkeypatch.setattr(youtube_compat.httpx, "get", get)
    result = youtube_compat.ProviderSupervisor().health()

    assert result["healthy"] is True
    assert result["address_family"] == "ipv4"


def test_reentrant_start_is_serialized(provider_ready, fake_popen, monkeypatch):
    supervisor = youtube_compat.ProviderSupervisor()
    entered = threading.Event()
    release = threading.Event()
    calls = 0

    def health():
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            release.wait(timeout=2)
            return {"running": False, "healthy": False, "version": None}
        return {"running": True, "healthy": True, "version": "1.3.2"}

    monkeypatch.setattr(supervisor, "health", health)
    errors = []

    def invoke():
        try:
            supervisor.start()
        except Exception as error:  # pragma: no cover - failure is asserted below
            errors.append(error)

    first = threading.Thread(target=invoke)
    second = threading.Thread(target=invoke)
    first.start()
    assert entered.wait(timeout=2)
    second.start()
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert errors == []
    assert len(fake_popen) == 1


def test_cancellation_cleanup_uses_owned_handle(provider_ready, fake_popen, monkeypatch):
    supervisor = youtube_compat.ProviderSupervisor()
    responses = iter([
        {"running": False, "healthy": False, "version": None},
        {"running": True, "healthy": True, "version": "1.3.2"},
    ])
    monkeypatch.setattr(supervisor, "health", lambda: next(responses))

    supervisor.start()
    process = supervisor.handle.process
    supervisor.stop()

    assert process.poll() is not None
    assert supervisor.handle is None


def test_parent_log_descriptor_is_closed_after_spawn(provider_ready, monkeypatch, tmp_path):
    captured = {}
    process = FakeProcess()
    responses = iter([
        {"running": False, "healthy": False, "version": None},
        {"running": True, "healthy": True, "version": "1.3.2", "address_family": "ipv4"},
    ])

    def popen(*args, **kwargs):
        captured.update(kwargs)
        return process

    monkeypatch.setattr(youtube_compat.subprocess, "Popen", popen)
    supervisor = youtube_compat.ProviderSupervisor()
    monkeypatch.setattr(supervisor, "health", lambda: next(responses))

    supervisor.start()

    assert captured["stdout"].closed is True
    assert captured["stderr"].closed is True
    supervisor.stop()


def test_ytdlp_uses_supervisor_endpoint_for_both_methods(monkeypatch):
    from clipgauge_pipeline.ingest import ytdlp

    class StubSupervisor:
        def start(self):
            return "http://[::1]:4416"

        def self_test(self):
            return {"ok": True}

    monkeypatch.setattr(ytdlp, "_provider_supervisor", StubSupervisor())
    for method in ("bgutil", "mweb"):
        args = ytdlp._youtube_provider_args("https://www.youtube.com/watch?v=aqz-KE-bpKQ", compatibility_method=method)
        assert "youtubepot-bgutilhttp:base_url=http://[::1]:4416" in " ".join(args)


def test_spawn_exception_is_classified_and_leaves_no_handle(provider_ready, monkeypatch):
    def failing_popen(*args, **kwargs):
        raise OSError("executable unavailable")

    monkeypatch.setattr(youtube_compat.subprocess, "Popen", failing_popen)
    supervisor = youtube_compat.ProviderSupervisor()

    with pytest.raises(runtime.RuntimeIntegrityError, match="NODE_FAILURE"):
        supervisor.start()

    assert supervisor.handle is None


def test_unresponsive_occupied_port_is_rejected(provider_ready, fake_popen, monkeypatch):
    supervisor = youtube_compat.ProviderSupervisor()
    monkeypatch.setattr(supervisor, "health", lambda: {"running": False, "healthy": False, "version": None})
    monkeypatch.setattr(supervisor, "_port_occupied", lambda: True)

    with pytest.raises(runtime.RuntimeIntegrityError, match="PORT_IN_USE"):
        supervisor.start()

    assert fake_popen == []
