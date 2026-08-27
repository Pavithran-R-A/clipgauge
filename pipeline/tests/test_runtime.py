import hashlib
import io
import os
import tarfile
import zipfile
from pathlib import Path

import httpx
import pytest

from clipgauge_pipeline import local_runtime
from clipgauge_pipeline import runtime
from clipgauge_pipeline.models import registry
from clipgauge_pipeline.models import specs  # noqa: F401 - registers concrete specs


class FakeResponse:
    def __init__(self, chunks, status_code=200, headers=None, error=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks
        self._error = error

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_bytes(self):
        for chunk in self._chunks:
            if isinstance(chunk, BaseException):
                raise chunk
            yield chunk


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_hash_mismatch_rejects_and_preserves_last_known_good(tmp_path, monkeypatch):
    destination = tmp_path / "tool"
    destination.write_bytes(b"known-good")
    monkeypatch.setattr(
        runtime.httpx,
        "stream",
        lambda *args, **kwargs: FakeResponse([b"replacement"], headers={"content-length": "11"}),
    )
    with pytest.raises(runtime.RuntimeIntegrityError, match="SHA-256 mismatch"):
        runtime.download_verified(
            "https://example.invalid/tool",
            destination,
            expected_sha256=_sha(b"wrong"),
            max_bytes=100,
        )
    assert destination.read_bytes() == b"known-good"
    assert not list(tmp_path.glob("*.part"))


def test_interrupted_download_resumes_from_staging_file(tmp_path, monkeypatch):
    destination = tmp_path / "tool"
    part = destination.with_name(f".{destination.name}.part")
    part.write_bytes(b"abc")
    responses = iter(
        [
            FakeResponse([httpx.ReadError("interrupted")], status_code=206, headers={"content-length": "3"}),
            FakeResponse([b"def"], status_code=206, headers={"content-length": "3"}),
        ]
    )
    monkeypatch.setattr(runtime.httpx, "stream", lambda *args, **kwargs: next(responses))
    with pytest.raises(runtime.RuntimeIntegrityError, match="interrupted"):
        runtime.download_verified(
            "https://example.invalid/tool",
            destination,
            expected_sha256=_sha(b"abcdef"),
            max_bytes=100,
        )
    assert part.read_bytes() == b"abc"
    installed = runtime.download_verified(
        "https://example.invalid/tool",
        destination,
        expected_sha256=_sha(b"abcdef"),
        max_bytes=100,
    )
    assert installed == destination
    assert destination.read_bytes() == b"abcdef"
    assert not part.exists()


def _archive(path: Path, names: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, b"payload")


def test_archive_traversal_is_rejected(tmp_path):
    archive = tmp_path / "bad.zip"
    _archive(archive, ["../escape"])
    with pytest.raises(runtime.RuntimeIntegrityError, match="traversal"):
        runtime.extract_zip_verified(archive, tmp_path / "out", expected_members={"../escape"})


def test_unexpected_archive_entry_is_rejected(tmp_path):
    archive = tmp_path / "bad.zip"
    _archive(archive, ["bin/tool", "bin/unexpected"])
    with pytest.raises(runtime.RuntimeIntegrityError, match="unexpected"):
        runtime.extract_zip_verified(archive, tmp_path / "out", expected_members={"bin/tool"})


def test_manifest_and_registry_have_concrete_model_hashes():
    manifest = runtime.load_manifest(Path(__file__).parents[1] / "runtime-manifest.json")
    for key, spec in registry.REGISTRY.items():
        assert spec.sha256 and len(spec.sha256) == 64
        entry = manifest["models"][key]
        assert entry["sha256"] == spec.sha256
        assert entry["size"] > 0


def test_safe_tar_archive_installation(tmp_path):
    archive = tmp_path / "good.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        payload = tarfile.TarInfo("llama-b10545/llama-server")
        payload.size = len(b"server")
        handle.addfile(payload, io.BytesIO(b"server"))
    output = tmp_path / "installed"
    installed = runtime.extract_archive_verified(archive, output, archive_type="tar.gz")
    assert [path.relative_to(output).as_posix() for path in installed] == ["llama-b10545/llama-server"]
    assert (output / "llama-b10545/llama-server").read_bytes() == b"server"


def test_archive_extraction_preserves_nested_source_archive(tmp_path):
    destination = tmp_path / "node"
    destination.mkdir()
    archive = destination / "runtime.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        payload = tarfile.TarInfo("node/bin/node")
        payload.mode = 0o755
        payload.size = len(b"node")
        handle.addfile(payload, io.BytesIO(b"node"))
    runtime.extract_archive_verified(archive, destination, archive_type="tar.gz")
    assert archive.is_file()
    assert (destination / "node/bin/node").is_file()


def test_safe_archive_preserves_tar_executable_mode(tmp_path):
    archive = tmp_path / "executable.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        payload = tarfile.TarInfo("node/bin/node")
        payload.mode = 0o755
        payload.size = len(b"node")
        handle.addfile(payload, io.BytesIO(b"node"))
    output = tmp_path / "installed"
    runtime.extract_archive_verified(archive, output, archive_type="tar.gz")
    if os.name != "nt":
        assert (output / "node/bin/node").stat().st_mode & 0o111


def test_safe_archive_preserves_zip_executable_mode(tmp_path):
    archive = tmp_path / "executable.zip"
    info = zipfile.ZipInfo("node/bin/npm")
    info.external_attr = (0o100755 << 16)
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(info, b"npm")
    output = tmp_path / "installed"
    runtime.extract_archive_verified(archive, output, archive_type="zip")
    if os.name != "nt":
        assert (output / "node/bin/npm").stat().st_mode & 0o111


def test_safe_archive_preserves_internal_tar_aliases(tmp_path):
    archive = tmp_path / "aliases.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        target = tarfile.TarInfo("node/lib/cli.js")
        target.mode = 0o644
        target.size = len(b"module.exports = true")
        handle.addfile(target, io.BytesIO(b"module.exports = true"))
        alias = tarfile.TarInfo("node/bin/npm")
        alias.type = tarfile.SYMTYPE
        alias.linkname = "../lib/cli.js"
        handle.addfile(alias)
    output = tmp_path / "installed"
    runtime.extract_archive_verified(archive, output, archive_type="tar.gz")
    npm = output / "node/bin/npm"
    if os.name != "nt":
        assert npm.is_symlink()
        assert npm.resolve() == (output / "node/lib/cli.js").resolve()
    assert npm.read_bytes() == b"module.exports = true"


def test_safe_archive_rejects_tar_traversal(tmp_path):
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        payload = tarfile.TarInfo("../escape")
        payload.size = len(b"blocked")
        handle.addfile(payload, io.BytesIO(b"blocked"))
    with pytest.raises(runtime.RuntimeIntegrityError, match="traversal"):
        runtime.extract_archive_verified(archive, tmp_path / "installed", archive_type="tar.gz")


def test_local_runtime_allows_slow_verified_model_startup(monkeypatch, tmp_path):
    model = tmp_path / "models" / "clipgauge-local" / "Qwen3-1.7B-Q8_0.gguf"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"verified-model")
    manifest = {"runtimes": {"llama-server": {"version": "test-runtime"}}}
    instance = local_runtime.LocalRuntime(root=tmp_path, manifest=manifest)
    monkeypatch.setattr(instance, "command", lambda _model_id, _port: ["llama-server"])
    monkeypatch.setattr(instance, "_port", lambda _endpoint=None: 18089)

    class DummyProcess:
        pid = 1234
        returncode = None

        @staticmethod
        def poll():
            return None

    monkeypatch.setattr(local_runtime.subprocess, "Popen", lambda *args, **kwargs: DummyProcess())
    health_calls = []
    monkeypatch.setattr(
        local_runtime.httpx,
        "get",
        lambda *args, **kwargs: health_calls.append(args[0]) or type("Response", (), {"status_code": 503})(),
    )
    ticks = iter((0.0, 31.0, 121.0))
    monkeypatch.setattr(local_runtime.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(local_runtime.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(instance, "stop_process", lambda _process: None)

    with pytest.raises(local_runtime.LocalRuntimeError, match="120 seconds"):
        instance.start("clipgauge-local/qwen3-1.7b-q8_0")
    assert len(health_calls) == 1


def test_valid_staged_archive_installation(tmp_path):
    archive = tmp_path / "good.zip"
    _archive(archive, ["bin/tool"])
    output = tmp_path / "installed"
    installed = runtime.extract_zip_verified(
        archive,
        output,
        expected_members={"bin/tool"},
        member_modes={"bin/tool": 0o755},
    )
    assert [path.relative_to(output).as_posix() for path in installed] == ["bin/tool"]
    assert (output / "bin/tool").read_bytes() == b"payload"
    if os.name == "nt":
        # Windows does not expose POSIX execute bits through st_mode; the
        # packaged-resource contract is successful materialization instead.
        assert (output / "bin/tool").is_file()
    else:
        assert (output / "bin/tool").stat().st_mode & 0o111
