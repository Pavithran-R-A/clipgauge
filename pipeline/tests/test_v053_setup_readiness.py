import json

import pytest

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

    assert result['state'] == 'DEPENDENCIES_READY'
    assert result['dependency_state'] == 'DEPENDENCIES_READY'
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


def test_youtube_readiness_distinguishes_dependencies_from_public_download(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_compat.config, 'home_dir', lambda: tmp_path)
    monkeypatch.setattr(youtube_compat, '_yt_dlp_ready', lambda: True)
    monkeypatch.setattr(youtube_compat.DownloadManager, 'inventory', lambda self, assets: [
        {'asset_id': asset.asset_id, 'installed': True, 'status': 'ready'} for asset in assets
    ])
    monkeypatch.setattr(youtube_compat, '_server_ready', lambda: True)
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, 'self_test', lambda self: {
        'plugin_discoverable': True, 'server_installed': True,
        'health': {'healthy': True, 'running': True, 'version': '1.3.2'}, 'loopback_only': True, 'ok': True,
    })
    result = youtube_compat.readiness()
    assert result['state'] == 'DEPENDENCIES_READY'
    assert result['ready'] is True
    assert result['public_download_verified'] is False
    assert result['dependency_state'] == 'DEPENDENCIES_READY'


def test_public_compatibility_success_is_metadata_only_and_secret_free(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_compat.config, 'home_dir', lambda: tmp_path)
    youtube_compat.record_public_compatibility_success(method='bgutil-http', ytdlp_version='2026.07.04')
    payload = (tmp_path / youtube_compat.PUBLIC_COMPATIBILITY_FILENAME).read_text(encoding='utf-8')
    assert 'token' not in payload.lower()
    assert 'cookie' not in payload.lower()
    status = youtube_compat.public_compatibility_status()
    assert status['verified'] is True
    assert status['method'] == 'bgutil-http'
    assert status['yt_dlp_version'] == '2026.07.04'
    assert 'verified_at' in status


def test_wpc_availability_does_not_launch_browser_and_requires_explicit_use(monkeypatch):
    launches = []
    monkeypatch.setattr(youtube_compat, '_find_browser', lambda: '/usr/bin/chromium')
    monkeypatch.setattr(youtube_compat, '_wpc_plugin_installed', lambda: True)
    monkeypatch.setattr(youtube_compat, '_launch_wpc_browser', lambda *args, **kwargs: launches.append(True))
    result = youtube_compat.wpc_availability()
    assert result['available'] is True
    assert result['browser_path'] == '/usr/bin/chromium'
    assert launches == []


def test_wpc_user_declines_without_browser_side_effect(monkeypatch):
    launches = []
    monkeypatch.setattr(youtube_compat, '_launch_wpc_browser', lambda *args, **kwargs: launches.append(True))
    result = youtube_compat.wpc_launch_decision(approved=False, browser_path='/usr/bin/chromium')
    assert result['state'] == 'USER_DECLINED'
    assert launches == []


def test_wpc_success_fixture_requires_explicit_approval_and_keeps_browser_path_only():
    result = youtube_compat.wpc_launch_decision(
        approved=True,
        browser_path='/usr/bin/chromium',
        launcher=lambda path: {'state': 'STARTED', 'provider': 'wpc', 'browser_path': path, 'public_session': True},
    )
    assert result == {'state': 'STARTED', 'provider': 'wpc', 'browser_path': '/usr/bin/chromium', 'public_session': True}
    assert 'cookie' not in str(result).lower()
    assert 'profile' not in str(result).lower()


def test_supported_mweb_fallback_is_explicit_and_not_missing_pot(monkeypatch):
    from clipgauge_pipeline.ingest import ytdlp
    class StubSupervisor:
        def start(self):
            return 'http://127.0.0.1:4416'
        def self_test(self):
            return {'ok': True}
    monkeypatch.setattr(ytdlp, '_provider_supervisor', StubSupervisor())
    args = ytdlp._youtube_provider_args('https://www.youtube.com/watch?v=aqz-KE-bpKQ', compatibility_method='mweb')
    assert '--extractor-args' in args
    joined = ' '.join(args)
    assert 'youtube:player_client=mweb' in joined
    assert 'missing_pot' not in joined


def test_youtube_failure_diagnostic_is_sanitized_and_classifies_gvs():
    from clipgauge_pipeline.ingest import ytdlp
    diagnostic = ytdlp.compatibility_diagnostic(
        phase='GVS_TRANSFER',
        method='bgutil-http',
        stderr='[debug] [youtube] [pot] PO Token Providers: bgutil:http-1.3.2 (external)\nERROR: HTTP Error 403: Forbidden',
        http_status=403,
    )
    assert diagnostic['failure_phase'] == 'GVS_TRANSFER'
    assert diagnostic['provider'] == 'bgutil:http-1.3.2'
    assert diagnostic['http_status'] == 403
    assert diagnostic['token_contexts_requested'] == ['GVS']
    assert diagnostic['cache_invalidated'] is False
    assert '403' in diagnostic['error_summary']
    assert 'token contents' not in str(diagnostic).lower()


def test_attestation_failure_invalidates_public_verification_without_deleting_dependencies(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_compat.config, 'home_dir', lambda: tmp_path)
    youtube_compat.record_public_compatibility_success(method='bgutil-http', ytdlp_version='2026.07.04')
    youtube_compat.invalidate_public_compatibility()
    assert youtube_compat.public_compatibility_status()['verified'] is False
    assert (tmp_path / youtube_compat.PUBLIC_COMPATIBILITY_FILENAME).exists()


def test_readiness_exposes_wpc_as_optional_metadata_only(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_compat.config, 'home_dir', lambda: tmp_path)
    monkeypatch.setattr(youtube_compat, '_yt_dlp_ready', lambda: True)
    monkeypatch.setattr(youtube_compat.DownloadManager, 'inventory', lambda self, assets: [
        {'asset_id': asset.asset_id, 'installed': True, 'status': 'ready'} for asset in assets
    ])
    monkeypatch.setattr(youtube_compat, '_server_ready', lambda: True)
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, 'self_test', lambda self: {
        'plugin_discoverable': True, 'server_installed': True,
        'health': {'healthy': True, 'running': True, 'version': '1.3.2'}, 'loopback_only': True, 'ok': True,
    })
    monkeypatch.setattr(youtube_compat, '_find_browser', lambda: None)
    result = youtube_compat.readiness()
    assert result['wpc']['available'] is False
    assert result['wpc']['plugin_installed'] is False
    assert 'install Chrome' in result['wpc']['reason'] or 'Chrome' in result['wpc']['reason']


def test_mweb_fallback_uses_supported_automatic_format_selection():
    from clipgauge_pipeline.ingest import ytdlp
    selected = ytdlp.download_format_for('mweb')
    assert 'missing_pot' not in selected
    assert '[ext=mp4]' not in selected
    assert 'height<=' in selected


def test_local_file_fallback_bypasses_all_youtube_providers():
    from clipgauge_pipeline.ingest import ytdlp
    assert ytdlp._youtube_provider_args('/managed/jobs/example/media.mp4') == []
    assert ytdlp._needs_youtube_provider('/managed/jobs/example/media.mp4') is False


def test_ytdlp_classifies_provider_startup_failure(monkeypatch):
    from clipgauge_pipeline import runtime
    from clipgauge_pipeline.ingest import ytdlp

    class StubSupervisor:
        def start(self):
            raise runtime.RuntimeIntegrityError("HEALTH_TIMEOUT: provider did not become healthy")

    monkeypatch.setattr(ytdlp, '_provider_supervisor', StubSupervisor())
    with pytest.raises(ytdlp.YtDlpError) as caught:
        ytdlp._youtube_provider_args('https://www.youtube.com/watch?v=aqz-KE-bpKQ')
    assert caught.value.code == 'YTDLP_PROVIDER_HEALTH_TIMEOUT'
    assert caught.value.details == {
        'startup_error_code': 'HEALTH_TIMEOUT',
        'error_summary': 'YouTube compatibility service did not become healthy before the startup timeout.',
    }
