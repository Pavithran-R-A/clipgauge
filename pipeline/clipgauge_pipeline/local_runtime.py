"""Owned llama-server lifecycle for the ClipGauge Local provider."""

from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

QA_TRACE_ENV = "CLIPGAUGE_QA_RUNTIME_TRACE"
QA_TRACE_MAX_BYTES = 24_000
STARTUP_TIMEOUT_SECONDS = 120.0


def _qa_trace_enabled() -> bool:
    return os.environ.get(QA_TRACE_ENV) == "1"


def _qa_trace(root: Path, event: str, **fields: Any) -> None:
    """Write bounded runtime facts only when QA tracing is explicitly enabled."""
    if not _qa_trace_enabled():
        return
    try:
        directory = root / "diagnostics"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "local-runtime.jsonl"
        record = {"event": event, "time": round(time.time(), 3), **fields}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        if path.stat().st_size > QA_TRACE_MAX_BYTES:
            data = path.read_bytes()[-QA_TRACE_MAX_BYTES:]
            path.write_bytes(data[data.find(b"\n") + 1:] if b"\n" in data else data)
        path.chmod(0o600)
    except OSError:
        # Diagnostics must never break a model run.
        return


def _stderr_tail(root: Path, path: Path | None, limit: int = 3_000) -> str | None:
    if path is None or not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return text.replace(str(root), "<clipgauge-home>")[-limit:]
    except OSError:
        return None

from . import config, runtime


class LocalRuntimeError(RuntimeError):
    """The managed local runtime cannot be started or verified."""


@dataclass(frozen=True)
class LocalModel:
    model_id: str
    display_name: str
    filename: str
    url: str
    sha256: str
    size_bytes: int
    license: str
    context_window: int
    capabilities: tuple[str, ...]
    provenance: str
    revision: str


MODEL_CATALOG: dict[str, LocalModel] = {
    "clipgauge-local/qwen3-1.7b-q8_0": LocalModel(
        model_id="clipgauge-local/qwen3-1.7b-q8_0",
        display_name="Qwen3 1.7B · Lightweight",
        filename="Qwen3-1.7B-Q8_0.gguf",
        url="https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/resolve/90862c4b9d2787eaed51d12237eafdfe7c5f6077/Qwen3-1.7B-Q8_0.gguf",
        sha256="061b54daade076b5d3362dac252678d17da8c68f07560be70818cace6590cb1a",
        size_bytes=1_834_426_016,
        license="Apache-2.0",
        context_window=32_768,
        capabilities=("text", "structured_json"),
        provenance="https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/tree/90862c4b9d2787eaed51d12237eafdfe7c5f6077",
        revision="90862c4b9d2787eaed51d12237eafdfe7c5f6077",
    ),
    "clipgauge-local/qwen3-4b-q4_k_m": LocalModel(
        model_id="clipgauge-local/qwen3-4b-q4_k_m",
        display_name="Qwen3 4B · Balanced",
        filename="Qwen3-4B-Q4_K_M.gguf",
        url="https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q4_K_M.gguf",
        sha256="7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5",
        size_bytes=2_497_280_256,
        license="Apache-2.0",
        context_window=131_072,
        capabilities=("text", "structured_json"),
        provenance="https://huggingface.co/Qwen/Qwen3-4B-GGUF/tree/bc640142c66e1fdd12af0bd68f40445458f3869b",
        revision="bc640142c66e1fdd12af0bd68f40445458f3869b",
    ),
}


@dataclass
class LocalServerHandle:
    process: subprocess.Popen[Any]
    endpoint: str
    model_id: str


class LocalRuntime:
    def __init__(self, root: Path | None = None, manifest: dict[str, Any] | None = None) -> None:
        self.root = (root or config.home_dir()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = manifest or self._load_manifest()
        self.handle: LocalServerHandle | None = None

    def _load_manifest(self) -> dict[str, Any]:
        path = Path(__file__).parents[1] / "runtime-manifest.json"
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _platform_key() -> str:
        system = platform.system().lower()
        machine = platform.machine().lower()
        if system == "windows":
            return "windows-x86_64" if machine in {"amd64", "x86_64"} else "windows-arm64"
        if system == "darwin":
            return "macos-arm64" if machine in {"arm64", "aarch64"} else "macos-x86_64"
        return "linux-x86_64" if machine in {"x86_64", "amd64"} else "linux-arm64"

    def runtime_asset(self) -> dict[str, Any]:
        try:
            return self.manifest["runtimes"]["llama-server"]["assets"][self._platform_key()]
        except KeyError as exc:
            raise LocalRuntimeError("ClipGauge Local is not available for this platform yet.") from exc

    def binary_path(self) -> Path:
        asset = self.runtime_asset()
        destination = self.root / "runtimes" / "llama-server" / self.manifest["runtimes"]["llama-server"]["version"]
        binary = Path(asset["binary"])
        path = (destination / binary).resolve()
        if path != self.root and self.root not in path.parents:
            raise LocalRuntimeError("managed llama-server path escapes the ClipGauge data root")
        return path

    def model_path(self, model_id: str) -> Path:
        try:
            model = MODEL_CATALOG[model_id]
        except KeyError as exc:
            raise LocalRuntimeError("The selected ClipGauge Local model is not in the verified catalog.") from exc
        path = (self.root / "models" / "clipgauge-local" / model.filename).resolve()
        models_root = (self.root / "models").resolve()
        if models_root not in path.parents:
            raise LocalRuntimeError("managed model path escapes the ClipGauge model root")
        return path

    def verified_model_path(self, model_id: str) -> Path:
        """Return a catalog model only after size and hash verification."""
        try:
            model = MODEL_CATALOG[model_id]
        except KeyError as exc:
            raise LocalRuntimeError("The selected ClipGauge Local model is not in the verified catalog.") from exc
        path = self.model_path(model_id)
        if not path.is_file():
            raise runtime.RuntimeIntegrityError("managed local model is missing")
        if path.stat().st_size != model.size_bytes:
            raise runtime.RuntimeIntegrityError("managed local model size mismatch")
        if runtime.sha256_file(path).lower() != model.sha256.lower():
            raise runtime.RuntimeIntegrityError("managed local model hash mismatch")
        return path

    def install_runtime(self, archive: Path) -> Path:
        asset = self.runtime_asset()
        if runtime.sha256_file(archive).lower() != str(asset["sha256"]).lower():
            raise LocalRuntimeError("The llama.cpp runtime archive failed SHA-256 verification.")
        destination = self.root / "runtimes" / "llama-server" / self.manifest["runtimes"]["llama-server"]["version"]
        runtime.extract_archive_verified(archive, destination, archive_type=str(asset["archive_type"]))
        binary = self.binary_path()
        if not binary.is_file():
            raise LocalRuntimeError("The verified llama.cpp archive did not contain llama-server.")
        if os.name != "nt":
            binary.chmod(binary.stat().st_mode | 0o111)
        return binary

    def _port(self, endpoint: str | None = None) -> int:
        if endpoint:
            port = urlsplit(endpoint).port
            if port:
                return port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _loopback_endpoint(port: int) -> str:
        return f"http://127.0.0.1:{port}/v1"

    def command(self, model_id: str, port: int) -> list[str]:
        binary = self.binary_path()
        if not binary.is_file():
            raise LocalRuntimeError("ClipGauge Local runtime is not installed. Open Setup Center to install it.")
        try:
            model = self.verified_model_path(model_id)
        except runtime.RuntimeIntegrityError as exc:
            raise LocalRuntimeError(
                "The selected ClipGauge Local model failed verification. Delete it and retry the verified download."
            ) from exc
        return [
            str(binary),
            "--model",
            str(model),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-webui",
            "--parallel",
            "1",
            "--ctx-size",
            "4096",
            "--reasoning",
            "off",
        ]

    def start(self, model_id: str, endpoint: str | None = None) -> str:
        if self.handle and self.handle.process.poll() is None:
            _qa_trace(self.root, "runtime_reused", model_id=model_id, endpoint_kind="loopback")
            return self.handle.endpoint
        port = self._port(endpoint)
        command = self.command(model_id, port)
        model = self.model_path(model_id)
        started_at = time.monotonic()
        stderr_path = self.root / "diagnostics" / "local-runtime.stderr.log" if _qa_trace_enabled() else None
        if stderr_path:
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_handle = stderr_path.open("w", encoding="utf-8") if stderr_path else None
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name != "nt" else 0
        _qa_trace(
            self.root,
            "runtime_start",
            runtime_version=self.manifest["runtimes"]["llama-server"]["version"],
            model_id=model_id,
            model_size_bytes=model.stat().st_size,
            context_size=4096,
            parallel=1,
            reasoning="off",
            cpu_threads_configured=None,
            endpoint_kind="loopback",
        )
        popen_kwargs: dict[str, Any] = {
            "cwd": str(self.root),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": stderr_handle or subprocess.DEVNULL,
            "creationflags": creationflags,
        }
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True
        try:
            process = subprocess.Popen(command, **popen_kwargs)
        except OSError as exc:
            if stderr_handle:
                stderr_handle.close()
            raise LocalRuntimeError("ClipGauge Local could not start its managed runtime.") from exc
        if stderr_handle:
            stderr_handle.close()
        api = self._loopback_endpoint(port)
        base_url = api.rsplit("/v1", 1)[0]
        deadline = started_at + STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                _qa_trace(self.root, "runtime_exit_before_ready", exit_code=process.returncode, stderr_tail=_stderr_tail(self.root, stderr_path))
                raise LocalRuntimeError("ClipGauge Local runtime exited before becoming ready.")
            try:
                response = httpx.get(base_url + "/health", timeout=0.5, follow_redirects=False)
                _qa_trace(self.root, "health", status_code=response.status_code)
                if response.status_code in {200, 204}:
                    try:
                        slots = httpx.get(base_url + "/slots", timeout=1.0, follow_redirects=False)
                        slots_payload = slots.json()
                        slots_keys = sorted(slots_payload[0]) if isinstance(slots_payload, list) and slots_payload and isinstance(slots_payload[0], dict) else []
                        slots_status = slots.status_code
                    except (httpx.HTTPError, ValueError, TypeError, KeyError):
                        slots_keys = []
                        slots_status = None
                    _qa_trace(
                        self.root,
                        "ready",
                        health_status=response.status_code,
                        ready_seconds=round(time.monotonic() - started_at, 3),
                        process_pid=process.pid,
                        slots_status=slots_status,
                        slots_keys=slots_keys,
                    )
                    self.handle = LocalServerHandle(process=process, endpoint=api, model_id=model_id)
                    return api
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        self.stop_process(process)
        _qa_trace(self.root, "runtime_timeout_before_ready", stderr_tail=_stderr_tail(self.root, stderr_path))
        raise LocalRuntimeError(f"ClipGauge Local runtime did not become ready within {STARTUP_TIMEOUT_SECONDS:g} seconds.")

    @staticmethod
    def stop_process(process: subprocess.Popen[Any]) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def stop(self) -> None:
        if self.handle:
            process = self.handle.process
            self.stop_process(process)
            stderr_path = self.root / "diagnostics" / "local-runtime.stderr.log"
            _qa_trace(self.root, "runtime_exit", exit_code=process.returncode, stderr_tail=_stderr_tail(self.root, stderr_path))
            self.handle = None

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass
