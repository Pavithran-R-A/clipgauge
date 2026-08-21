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
        model = self.model_path(model_id)
        if not binary.is_file():
            raise LocalRuntimeError("ClipGauge Local runtime is not installed. Open Setup Center to install it.")
        if not model.is_file():
            raise LocalRuntimeError("The selected ClipGauge Local model is not installed. Open Setup Center to download it.")
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
            return self.handle.endpoint
        port = self._port(endpoint)
        command = self.command(model_id, port)
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        popen_kwargs: dict[str, Any] = {
            "cwd": str(self.root),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "creationflags": creationflags,
        }
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True
        try:
            process = subprocess.Popen(command, **popen_kwargs)
        except OSError as exc:
            raise LocalRuntimeError("ClipGauge Local could not start its managed runtime.") from exc
        api = self._loopback_endpoint(port)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise LocalRuntimeError("ClipGauge Local runtime exited before becoming ready.")
            try:
                response = httpx.get(api.rsplit("/v1", 1)[0] + "/health", timeout=0.5, follow_redirects=False)
                if response.status_code in {200, 204}:
                    self.handle = LocalServerHandle(process=process, endpoint=api, model_id=model_id)
                    return api
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        self.stop_process(process)
        raise LocalRuntimeError("ClipGauge Local runtime did not become ready within 30 seconds.")

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
            self.stop_process(self.handle.process)
            self.handle = None

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass
