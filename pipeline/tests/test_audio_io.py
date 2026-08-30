import numpy as np
import soundfile as sf

from clipgauge_pipeline.audio.io import load_mono, resample


def test_load_mono_and_resample_avoid_librosa_decoder(tmp_path):
    source = tmp_path / "source.wav"
    samples = np.column_stack(
        [np.linspace(-1.0, 1.0, 1600), np.linspace(1.0, -1.0, 1600)]
    ).astype(np.float32)
    sf.write(source, samples, 16000)

    mono, sample_rate = load_mono(source, 8000)

    assert sample_rate == 8000
    assert mono.dtype == np.float32
    assert len(mono) == 800
    assert np.allclose(mono[[0, -1]], 0.0, atol=0.02)
    assert len(resample(mono, 8000, 16000)) == 1600


def test_event_curves_do_not_import_librosa_decoder_chain():
    from pathlib import Path

    source = (Path(__file__).parents[1] / "clipgauge_pipeline" / "events" / "dsp.py").read_text()

    assert "import librosa" not in source
