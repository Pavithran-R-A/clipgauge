import hashlib
import io
import zipfile
from pathlib import Path

import httpx
import pytest

from publikclip_pipeline import runtime
from publikclip_pipeline.models import registry
from publikclip_pipeline.models import specs  # noqa: F401 - registers concrete specs


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
    assert (output / "bin/tool").stat().st_mode & 0o111
