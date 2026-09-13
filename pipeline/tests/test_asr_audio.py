import wave

import numpy as np
import pytest

from clipgauge_pipeline.asr.audio import AnalysisAudioError, load_analysis_audio


def _write_wav(path, *, channels=1, sample_width=2, rate=16_000, frames=b"\x00\x00"):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sample_width)
        handle.setframerate(rate)
        handle.writeframes(frames)


def test_load_analysis_audio_decodes_valid_pcm_to_bounded_float32(tmp_path):
    path = tmp_path / "audio16k.wav"
    _write_wav(path, frames=np.array([-32768, 0, 32767], dtype="<i2").tobytes())

    samples = load_analysis_audio(path)

    assert samples.dtype == np.float32
    assert samples.flags.c_contiguous
    np.testing.assert_allclose(samples, [-1.0, 0.0, 32767 / 32768], rtol=0, atol=1e-7)
    assert np.all(samples >= -1.0)
    assert np.all(samples <= 1.0)


@pytest.mark.parametrize(
    ("name", "payload", "code"),
    [
        ("malformed.wav", b"not a wav", "WAV_MALFORMED"),
        ("empty.wav", b"", "WAV_MALFORMED"),
    ],
)
def test_load_analysis_audio_reports_typed_malformed_errors(tmp_path, name, payload, code):
    path = tmp_path / name
    path.write_bytes(payload)

    with pytest.raises(AnalysisAudioError) as caught:
        load_analysis_audio(path)

    assert caught.value.code == code


def test_load_analysis_audio_reports_truncated_declared_frames(tmp_path):
    path = tmp_path / "truncated.wav"
    _write_wav(path, frames=b"\x00\x00" * 32)
    path.write_bytes(path.read_bytes()[:-4])

    with pytest.raises(AnalysisAudioError) as caught:
        load_analysis_audio(path)

    assert caught.value.code == "WAV_TRUNCATED"


@pytest.mark.parametrize(
    ("kwargs", "frames"),
    [
        ({"channels": 2}, b"\x00\x00\x00\x00"),
        ({"sample_width": 1}, b"\x00"),
        ({"rate": 8_000}, b"\x00\x00"),
    ],
)
def test_load_analysis_audio_rejects_non_normalized_pcm_format(tmp_path, kwargs, frames):
    path = tmp_path / "wrong-format.wav"
    _write_wav(path, **kwargs, frames=frames)

    with pytest.raises(AnalysisAudioError) as caught:
        load_analysis_audio(path)

    assert caught.value.code == "WAV_FORMAT_UNSUPPORTED"


def test_load_analysis_audio_bounds_file_size_before_reading(tmp_path, monkeypatch):
    path = tmp_path / "large.wav"
    _write_wav(path)
    monkeypatch.setattr("clipgauge_pipeline.asr.audio.MAX_ANALYSIS_WAV_BYTES", 1)

    with pytest.raises(AnalysisAudioError) as caught:
        load_analysis_audio(path)

    assert caught.value.code == "WAV_TOO_LARGE"
