from types import SimpleNamespace

import pytest

from clipgauge_pipeline import __version__
from clipgauge_pipeline import cli
from clipgauge_pipeline.cli import main


def run_exit(*args, capsys):
    with pytest.raises(SystemExit) as error:
        main(list(args))
    captured = capsys.readouterr()
    return error.value.code, captured.out, captured.err


def test_version_flag_uses_authoritative_package_version(capsys):
    code, stdout, stderr = run_exit('--version', capsys=capsys)
    assert code == 0
    assert stdout.strip() == f'ClipGauge {__version__}'
    assert stderr == ''


def test_short_version_flag_matches_long_version(capsys):
    code, stdout, stderr = run_exit('-V', capsys=capsys)
    assert code == 0
    assert stdout.strip() == f'ClipGauge {__version__}'
    assert stderr == ''


def test_help_flag_remains_successful(capsys):
    code, stdout, stderr = run_exit('--help', capsys=capsys)
    assert code == 0
    assert 'usage: clipgauge' in stdout
    assert 'process a YouTube URL or local video file' in stdout
    assert stderr == ''


def test_disk_warning_is_actionable_when_free_space_is_low(monkeypatch):
    monkeypatch.setattr(cli.config, 'home_dir', lambda: cli.Path('C:/managed'))
    monkeypatch.setattr(cli.shutil, 'disk_usage', lambda _: SimpleNamespace(free=2 * 1024**3))
    warning = cli._disk_warning()
    assert warning is not None
    assert 'free' in warning
    assert 'Setup & Storage' in warning
