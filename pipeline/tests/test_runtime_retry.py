import hashlib

from clipgauge_pipeline import runtime


class FakeResponse:
    def __init__(self, chunks, *, status_code=200, headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_bytes(self):
        yield from self._chunks


def test_download_verified_retries_transient_http_504(tmp_path, monkeypatch):
    payload = b"verified-runtime"
    destination = tmp_path / "asset.bin"
    responses = iter(
        [
            FakeResponse([], status_code=504),
            FakeResponse(
                [payload],
                status_code=200,
                headers={"content-length": str(len(payload))},
            ),
        ]
    )
    calls = []

    def stream(*args, **kwargs):
        calls.append((args, kwargs))
        return next(responses)

    monkeypatch.setattr(runtime.httpx, "stream", stream)
    monkeypatch.setattr(runtime.time, "sleep", lambda _seconds: None)

    installed = runtime.download_verified(
        "https://example.invalid/asset.bin",
        destination,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_size=len(payload),
        max_bytes=1024,
    )

    assert installed == destination
    assert destination.read_bytes() == payload
    assert len(calls) == 2
