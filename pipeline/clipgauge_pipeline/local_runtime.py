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


from . import config, hardware, runtime


class LocalRuntimeError(RuntimeError):
    """The managed local runtime cannot be started or verified."""


def select_runtime_asset_key(
    *,
    platform_key: str,
    nvidia_available: bool,
    vulkan_available: bool,
    cuda_available: bool = False,
    available_keys: set[str],
) -> str:
    """Choose CUDA first, then Vulkan, with CPU fallback.

    CUDA requires both verified CTranslate2 CUDA support and the managed CUDA
    runtime. Vulkan remains the Windows GPU fallback. A verified NVIDIA device
    is sufficient to prefer either GPU backend; llama-server health checks remain
    the final runtime verification boundary.
    """
    cuda_key = f"{platform_key}-cuda"
    if platform_key == "windows-x86_64" and cuda_key in available_keys and cuda_available and nvidia_available:
        return cuda_key
    gpu_key = f"{platform_key}-vulkan"
    if (
        platform_key == "windows-x86_64"
        and gpu_key in available_keys
        and (nvidia_available or vulkan_available)
    ):
        return gpu_key
    return platform_key


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
        self._runtime_asset_key_cache: str | None = None

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

    def runtime_asset_key(self) -> str:
        if self._runtime_asset_key_cache is not None:
            return self._runtime_asset_key_cache
        platform_key = self._platform_key()
        assets = self.manifest.get("runtimes", {}).get("llama-server", {}).get("assets", {})
        if platform_key not in assets:
            raise LocalRuntimeError("ClipGauge Local is not available for this platform yet.")
        nvidia_available = False
        vulkan_available = False
        cuda_available = False
        if platform_key == "windows-x86_64":
            try:
                capabilities = hardware.snapshot(self.root)
                nvidia_available = bool((capabilities.get("nvidia") or {}).get("verified"))
                vulkan_available = bool((capabilities.get("vulkan") or {}).get("verified"))
                if self.root == config.home_dir().resolve():
                    from .models import managed

                    cuda_available = managed.cuda_runtime_ready() and bool(
                        (capabilities.get("cuda_ctranslate2") or {}).get("verified")
                    )
            except Exception:  # noqa: BLE001 - capability probing must never remove CPU fallback
                pass
        selected = select_runtime_asset_key(
            platform_key=platform_key,
            nvidia_available=nvidia_available,
            vulkan_available=vulkan_available,
            cuda_available=cuda_available,
            available_keys=set(assets),
        )
        self._runtime_asset_key_cache = selected
        return selected

    def runtime_asset(self) -> dict[str, Any]:
        try:
            return self.manifest["runtimes"]["llama-server"]["assets"][self.runtime_asset_key()]
        except KeyError as exc:
            raise LocalRuntimeError("ClipGauge Local is not available for this platform yet.") from exc

    def runtime_backend(self) -> str:
        return str(self.runtime_asset().get("backend", "cpu"))

    def runtime_library_dir(self) -> Path | None:
        """Return verified local CUDA libraries for the child runtime."""
        if self.runtime_backend() != "cuda":
            return None
        if self.root != config.home_dir().resolve():
            return None
        from .models import managed

        return managed.CUDA_RUNTIME_DIR if managed.cuda_runtime_ready() else None

    def _runtime_destination(self) -> Path:
        version = str(self.manifest["runtimes"]["llama-server"]["version"])
        base = self.root / "runtimes" / "llama-server" / version
        key = self.runtime_asset_key()
        # Preserve the existing CPU path for compatibility. GPU variants live in
        # their own directory so an old CPU executable can never masquerade as
        # an accelerated installation.
        if key == self._platform_key():
            return base
        return base / key

    def binary_path(self) -> Path:
        asset = self.runtime_asset()
        destination = self._runtime_destination()
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
        destination = self._runtime_destination()
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
        command = [
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
        if self.runtime_backend() in {"vulkan", "cuda", "metal"}:
            command.extend(["--n-gpu-layers", "999"])
        return command

    def probe_inference(self, endpoint: str, model_id: str, *, backend: str) -> dict[str, Any]:
        """Verify one bounded local inference without recording its content."""
        started_at = time.monotonic()
        try:
            response = httpx.post(
                endpoint.rstrip("/") + "/chat/completions",
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": "Reply with exactly OK."}],
                    "max_tokens": 1,
                    "temperature": 0,
                    "stream": False,
                },
                timeout=15.0,
                follow_redirects=False,
            )
            payload = response.json()
            choices = payload.get("choices") if isinstance(payload, dict) else None
            message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
            reply = message.get("content") if isinstance(message, dict) else None
            usage = payload.get("usage") if isinstance(payload, dict) else None
            generated_tokens = usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0
            ok = response.status_code == 200 and reply.strip() == "OK" if isinstance(reply, str) else False
            result = {
                "ok": ok,
                "backend": backend,
                "generated_tokens": int(generated_tokens or 0),
                "duration_sec": round(time.monotonic() - started_at, 3),
            }
            if not ok:
                result["reason"] = "Local inference returned an invalid response."
            return result
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return {
                "ok": False,
                "backend": backend,
                "generated_tokens": 0,
                "duration_sec": round(time.monotonic() - started_at, 3),
                "reason": "Local inference verification failed.",
            }

    def start(self, model_id: str, endpoint: str | None = None) -> str:
        if self.handle and self.handle.process.poll() is None:
            _qa_trace(self.root, "runtime_reused", model_id=model_id, endpoint_kind="loopback")
            return self.handle.endpoint
        port = self._port(endpoint)
        command = self.command(model_id, port)
        model = self.model_path(model_id)
        backend = self.runtime_backend()
        started_at = time.monotonic()
        stderr_path = self.root / "diagnostics" / "local-runtime.stderr.log" if _qa_trace_enabled() else None
        if stderr_path:
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_handle = stderr_path.open("w", encoding="utf-8") if stderr_path else None
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        _qa_trace(
            self.root,
            "runtime_start",
            runtime_version=self.manifest["runtimes"]["llama-server"]["version"],
            runtime_asset_key=self.runtime_asset_key(),
            backend=backend,
            model_id=model_id,
            model_size_bytes=model.stat().st_size,
            context_size=4096,
            parallel=1,
            gpu_layers=999 if backend in {"vulkan", "cuda", "metal"} else 0,
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
        library_dir = self.runtime_library_dir()
        if library_dir is not None:
            child_env = os.environ.copy()
            child_env["PATH"] = str(library_dir) + os.pathsep + child_env.get("PATH", "")
            popen_kwargs["env"] = child_env
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
                    inference = self.probe_inference(api, model_id, backend=backend)
                    _qa_trace(
                        self.root,
                        "inference_probe",
                        ok=inference["ok"],
                        backend=backend,
                        generated_tokens=inference["generated_tokens"],
                        duration_sec=inference["duration_sec"],
                    )
                    if not inference["ok"]:
                        self.stop_process(process)
                        raise LocalRuntimeError(
                            "ClipGauge Local runtime started, but its bounded inference check failed."
                        )
                    _qa_trace(
                        self.root,
                        "ready",
                        health_status=response.status_code,
                        ready_seconds=round(time.monotonic() - started_at, 3),
                        process_pid=process.pid,
                        backend=backend,
                        slots_status=slots_status,
                        slots_keys=slots_keys,
                        inference_verified=True,
                        inference_duration_sec=inference["duration_sec"],
                        generated_tokens=inference["generated_tokens"],
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
