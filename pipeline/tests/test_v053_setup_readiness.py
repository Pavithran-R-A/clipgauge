import json

from clipgauge_pipeline import setup_models
from clipgauge_pipeline.ingest import youtube_compat


def _row(asset_id, *, installed=False, status='not-installed'):
    return {
        'asset_id': asset_id,
        'display_name': 'Lightweight' if '1.7' in asset_id else 'Balanced',
        'installed': installed,
        'status': status,
        'size_bytes': 12,
        'installed_size_bytes': 12 if installed else 0,
    }


def test_selection_prefers_persisted_valid_installed_model():
    rows = [_row('clipgauge-local/qwen3-1.7b-q8_0', installed=True), _row('clipgauge-local/qwen3-4b-q4_k_m', installed=False)]
    assert setup_models.select_model_id(rows, persisted_id='clipgauge-local/qwen3-1.7b-q8_0') == 'clipgauge-local/qwen3-1.7b-q8_0'


def test_selection_falls_back_to_valid_installed_then_recommended():
    rows = [_row('clipgauge-local/qwen3-1.7b-q8_0', installed=True), _row('clipgauge-local/qwen3-4b-q4_k_m', installed=False)]
    assert setup_models.select_model_id(rows, persisted_id='missing') == 'clipgauge-local/qwen3-1.7b-q8_0'
    assert setup_models.select_model_id([_row('clipgauge-local/qwen3-4b-q4_k_m')], persisted_id='missing') == 'clipgauge-local/qwen3-4b-q4_k_m'


def test_persisted_selection_round_trips_without_credentials(tmp_path):
    setup_models.save_selected_model(tmp_path, 'clipgauge-local/qwen3-1.7b-q8_0')
    assert setup_models.load_selected_model(tmp_path) == 'clipgauge-local/qwen3-1.7b-q8_0'
    assert 'secret' not in (tmp_path / setup_models.SELECTION_FILENAME).read_text(encoding='utf-8').lower()


def test_model_lifecycle_never_schedules_download_for_verified_asset():
    verified = setup_models.enrich_model_row(_row('clipgauge-local/qwen3-1.7b-q8_0', installed=True))
    repair = setup_models.enrich_model_row(_row('clipgauge-local/qwen3-1.7b-q8_0', status='needs-repair'))
    assert verified['lifecycle_state'] == 'VERIFIED'
    assert verified['required_download_bytes'] == 0
    assert repair['lifecycle_state'] == 'NEEDS_REPAIR'


def test_runtime_and_model_state_is_independent():
    installed = setup_models.enrich_model_row(_row('clipgauge-local/qwen3-1.7b-q8_0', installed=True))
    missing = setup_models.enrich_model_row(_row('clipgauge-local/qwen3-4b-q4_k_m'))
    assert installed['required_download_bytes'] == 0
    assert missing['required_download_bytes'] == 12


def test_youtube_readiness_reports_install_and_build_boundaries(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_compat.config, 'home_dir', lambda: tmp_path)
    monkeypatch.setattr(youtube_compat, '_yt_dlp_ready', lambda: False)
    assert youtube_compat.readiness()['state'] == 'NOT_INSTALLED'

    monkeypatch.setattr(youtube_compat, '_yt_dlp_ready', lambda: True)
    monkeypatch.setattr(youtube_compat.DownloadManager, 'inventory', lambda self, assets: [
        {'asset_id': asset.asset_id, 'installed': True, 'status': 'ready'} for asset in assets
    ])
    monkeypatch.setattr(youtube_compat, '_server_ready', lambda: False)
    result = youtube_compat.readiness()
    assert result['state'] == 'BUILD_REQUIRED'
    assert result['ready'] is False


def test_youtube_readiness_requires_healthy_loopback_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_compat.config, 'home_dir', lambda: tmp_path)
    monkeypatch.setattr(youtube_compat, '_yt_dlp_ready', lambda: True)
    monkeypatch.setattr(youtube_compat.DownloadManager, 'inventory', lambda self, assets: [
        {'asset_id': asset.asset_id, 'installed': True, 'status': 'ready'} for asset in assets
    ])
    monkeypatch.setattr(youtube_compat, '_server_ready', lambda: True)
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, 'self_test', lambda self: {
        'plugin_discoverable': True, 'server_installed': True,
        'health': {'healthy': False, 'running': False}, 'loopback_only': True, 'ok': False,
    })
    result = youtube_compat.readiness()
    assert result['state'] == 'UNHEALTHY'
    assert result['ready'] is False
