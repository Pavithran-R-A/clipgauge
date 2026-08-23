from __future__ import annotations

from clipgauge_pipeline import memory


def test_release_cpu_memory_collects_unreachable_objects(monkeypatch):
    calls = []
    monkeypatch.setattr(memory.gc, "collect", lambda: calls.append("collect"))
    monkeypatch.setattr(memory.sys, "platform", "darwin")

    assert memory.release_cpu_memory() is None
    assert calls == ["collect"]


def test_non_linux_does_not_require_malloc_trim(monkeypatch):
    monkeypatch.setattr(memory.sys, "platform", "win32")

    def fail_if_loaded(_name):
        raise AssertionError("malloc_trim must not be required outside Linux")

    monkeypatch.setattr(memory.ctypes, "CDLL", fail_if_loaded)
    memory.release_cpu_memory()


def test_linux_attempts_malloc_trim(monkeypatch):
    calls = []

    class Libc:
        def malloc_trim(self, value):
            calls.append(value)
            return 1

    monkeypatch.setattr(memory.sys, "platform", "linux")
    monkeypatch.setattr(memory.ctypes, "CDLL", lambda _name: Libc())
    memory.release_cpu_memory()
    assert calls == [0]


def test_linux_swallows_missing_malloc_trim(monkeypatch):
    monkeypatch.setattr(memory.sys, "platform", "linux")
    monkeypatch.setattr(memory.ctypes, "CDLL", lambda _name: object())
    memory.release_cpu_memory()


def test_linux_swallows_libc_load_error(monkeypatch):
    monkeypatch.setattr(memory.sys, "platform", "linux")

    def fail_load(_name):
        raise OSError("libc unavailable")

    monkeypatch.setattr(memory.ctypes, "CDLL", fail_load)
    memory.release_cpu_memory()


def test_cleanup_never_turns_success_into_failure(monkeypatch):
    monkeypatch.setattr(memory.sys, "platform", "linux")
    monkeypatch.setattr(memory.gc, "collect", lambda: None)
    monkeypatch.setattr(memory.ctypes, "CDLL", lambda _name: object())

    try:
        memory.release_cpu_memory()
    except Exception as error:  # pragma: no cover - defensive contract assertion
        raise AssertionError("best-effort cleanup must not fail its caller") from error
