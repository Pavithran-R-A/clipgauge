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


def test_youtube_test_refreshes_loopback_health_on_success(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_compat.config, 'home_dir', lambda: tmp_path)
    initial = {
        'state': 'UNHEALTHY',
        'ready': False,
        'checks': [
            {'name': 'yt-dlp', 'ready': True},
            {'name': 'loopback-health', 'ready': False, 'message': 'The local PO-token provider is not healthy.'},
        ],
    }
    monkeypatch.setattr(youtube_compat, 'readiness', lambda: initial)
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, 'start', lambda self: 'http://127.0.0.1:4416')
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, 'self_test', lambda self: {
        'plugin_discoverable': True,
        'server_installed': True,
        'health': {'healthy': True, 'running': True, 'version': '1.3.2'},
        'loopback_only': True,
        'ok': True,
    })
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, 'stop', lambda self: None)

    result = youtube_compat.test()

    assert result['state'] == 'READY'
    loopback = next(check for check in result['checks'] if check['name'] == 'loopback-health')
    assert loopback['ready'] is True
    assert loopback['message'] == 'The local PO-token provider is healthy.'


def test_youtube_ingest_starts_provider_before_live_health_check(monkeypatch):
    from clipgauge_pipeline.ingest import ytdlp

    events = []

    class StubSupervisor:
        def start(self):
            events.append('start')
            return 'http://127.0.0.1:4416'

        def self_test(self):
            events.append('self_test')
            return {'ok': True}

    monkeypatch.setattr(ytdlp, '_provider_supervisor', StubSupervisor())
    args = ytdlp._youtube_provider_args('https://www.youtube.com/watch?v=aqz-KE-bpKQ')

    assert events == ['start', 'self_test']
    assert '--plugin-dirs' in args
    assert 'youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416' in args
