import json
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


def test_disk_warning_includes_local_source_estimate(monkeypatch):
    monkeypatch.setattr(cli.config, 'home_dir', lambda: cli.Path('C:/managed'))
    monkeypatch.setattr(cli.shutil, 'disk_usage', lambda _: SimpleNamespace(free=7 * 1024**3))
    monkeypatch.setattr(cli.Path, 'stat', lambda _: SimpleNamespace(st_size=4 * 1024**3))
    warning = cli._disk_warning('C:/source.mp4')
    assert warning is not None
    assert 'Source estimate' in warning


def test_disk_block_prevents_runs_before_job_creation(monkeypatch):
    monkeypatch.setattr(cli.config, 'home_dir', lambda: cli.Path('C:/managed'))
    monkeypatch.setattr(cli.shutil, 'disk_usage', lambda _: SimpleNamespace(free=512 * 1024**2))
    assert 'Free disk space' in cli._disk_block('https://www.youtube.com/watch?v=test')


def test_disk_block_allows_sufficient_space(monkeypatch):
    monkeypatch.setattr(cli.config, 'home_dir', lambda: cli.Path('C:/managed'))
    monkeypatch.setattr(cli.shutil, 'disk_usage', lambda _: SimpleNamespace(free=2 * 1024**3))
    assert cli._disk_block('https://www.youtube.com/watch?v=test') is None


def test_private_cli_default_uses_clipgauge_local():
    args = SimpleNamespace(
        provider=None,
        llm=None,
        model=None,
        endpoint=None,
        auth=None,
        secret_header=None,
    )

    profile = cli._profile_from_args(args, default_kind='clipgauge-local')

    assert profile.kind == 'clipgauge-local'
    assert profile.locality == 'local'


def test_private_cli_rejects_explicit_cloud_provider():
    args = SimpleNamespace(
        provider='gemini',
        llm=None,
        model=None,
        endpoint=None,
        auth=None,
        secret_header=None,
    )

    with pytest.raises(ValueError, match='private mode requires ClipGauge Local'):
        cli._profile_for_quality_mode(args, 'private')


def test_provider_models_command_builds_a_valid_namespace(monkeypatch, capsys):
    class FakeAdapter:
        def model_descriptors(self):
            return [{"id": "openrouter/free", "compatibility": "FULL"}]

    monkeypatch.setattr(cli, "_profile_from_args", lambda args: SimpleNamespace(kind="openrouter", model="openrouter/free"))
    monkeypatch.setattr(cli.providers_mod, "make_adapter", lambda profile: FakeAdapter())

    code = main(["provider-models", "--provider", "openrouter"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["state"] == "PASS"
    assert payload["models"][0]["id"] == "openrouter/free"


def test_managed_inventory_excludes_reused_system_ffmpeg(monkeypatch):
    def asset(asset_id):
        return cli.downloads.ManagedAsset(
            asset_id=asset_id,
            display_name=asset_id,
            purpose='test',
            destination=f'{asset_id}.bin',
            url='https://example.test',
            size_bytes=1,
            sha256='a' * 64,
            required=True,
            consent_group='core',
        )

    ffmpeg = asset('runtime:ffmpeg:win64-gpl')
    model = asset('model:test')
    seen = []

    class FakeManager:
        def inventory_cached(self, assets, **kwargs):
            seen.extend(assets)
            return []

    monkeypatch.setattr(cli, '_managed_asset_objects', lambda: [ffmpeg])
    monkeypatch.setattr(cli.downloads, 'DownloadManager', FakeManager)
    cli._managed_asset_inventory([model], exclude_asset_ids={ffmpeg.asset_id})
    assert [item.asset_id for item in seen] == [model.asset_id]


def test_core_inventory_reuses_cached_ytdlp_status(monkeypatch):
    from clipgauge_pipeline.ingest import ytdlp
    from clipgauge_pipeline.models import registry, specs  # noqa: F401
    from clipgauge_pipeline.render import ffmpeg_bin

    class FakeManager:
        manifest = {
            'runtimes': {
                'yt-dlp': {
                    'version': 'test',
                    'provenance': 'https://example.test/yt-dlp',
                    'license': 'test',
                    'assets': {'yt-dlp.exe': {'sha256': 'a' * 64, 'size': 1}},
                },
                'ffmpeg': {'assets': {}, 'version': 'test', 'license': 'test'},
            }
        }

    decision = SimpleNamespace(
        version='test',
        ready=True,
        source='system',
        executable='C:/ffmpeg.exe',
        capabilities={'starts': True},
        managed_download_needed=False,
        reason='ready',
    )
    monkeypatch.setattr(ytdlp, '_binary_name', lambda: 'yt-dlp.exe')
    monkeypatch.setattr(ytdlp, 'binary_path', lambda: cli.Path('C:/yt-dlp.exe'))
    monkeypatch.setattr(ffmpeg_bin, 'readiness', lambda: decision)
    monkeypatch.setattr(registry, 'REGISTRY', {})
    monkeypatch.setattr(cli.runtime, 'sha256_file', lambda _: pytest.fail('cached yt-dlp status must avoid rehashing'))

    rows = cli._core_setup_inventory(
        FakeManager(),
        [{'asset_id': 'core:yt-dlp', 'managed_path': 'C:/yt-dlp.exe', 'installed': True}],
    )

    assert rows[0]['asset_id'] == 'core:yt-dlp'
    assert rows[0]['integrity'] == 'verified'
