import os
import subprocess
from pathlib import Path

import pytest

from clipgauge_pipeline import cli, setup_models
from clipgauge_pipeline.ingest import ytdlp, youtube_compat


def _row(asset_id, *, installed=False, status='not-installed'):
    return {
        'asset_id': asset_id,
        'display_name': 'Lightweight' if '1.7' in asset_id else 'Balanced',
        'installed': installed,
        'status': status,
        'size_bytes': 12,
        'installed_size_bytes': 12 if installed else 0,
    }


def test_cli_storage_predicate_excludes_optional_runtime_assets():
    assert cli._is_core_required_asset_id('model:asr:test', True)
    assert not cli._is_core_required_asset_id('runtime:node:win64', True)
    assert not cli._is_core_required_asset_id('runtime:yt-dlp:win64', True)
    assert not cli._is_core_required_asset_id('youtube:bgutil-provider', True)
    assert not cli._is_core_required_asset_id('runtime:llama-server:cpu', False)


def test_selection_prefers_persisted_valid_installed_model():
    rows = [_row('clipgauge-local/qwen3-1.7b-q8_0', installed=True), _row('clipgauge-local/qwen3-4b-q4_k_m', installed=False)]
    assert setup_models.select_model_id(rows, persisted_id='clipgauge-local/qwen3-1.7b-q8_0') == 'clipgauge-local/qwen3-1.7b-q8_0'


def test_selection_falls_back_to_valid_installed_then_recommended():
    rows = [_row('clipgauge-local/qwen3-1.7b-q8_0', installed=True), _row('clipgauge-local/qwen3-4b-q4_k_m', installed=False)]
    assert setup_models.select_model_id(rows, persisted_id='missing') == 'clipgauge-local/qwen3-1.7b-q8_0'


@pytest.mark.parametrize(
    ('module', 'pattern'),
    [(setup_models, '.local-ai-settings.json.*.part'), (youtube_compat, '.youtube-public-compatibility.json.*.part')],
)
def test_atomic_setup_writes_clean_failed_temporaries(monkeypatch, tmp_path, module, pattern):
    destination = tmp_path / 'state.json'
    destination.write_text('previous', encoding='utf-8')

    def fail_replace(*_args):
        raise OSError('replace failed')

    monkeypatch.setattr(module.os, 'replace', fail_replace)
    with pytest.raises(OSError, match='replace failed'):
        module._atomic_write_text(destination, 'new')

    assert destination.read_text(encoding='utf-8') == 'previous'
    assert list(tmp_path.glob(pattern)) == []
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


def test_youtube_repair_reextracts_partial_managed_directories(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_compat, '_root', lambda: tmp_path / 'bgutil' / youtube_compat.PROVIDER_VERSION)
    root = youtube_compat._root()
    node_root = root / 'node' / youtube_compat.NODE_SPECS[youtube_compat.platform_key()].root_name
    source_root = root / 'source' / youtube_compat.PROVIDER_SOURCE_ROOT
    (node_root / 'partial').mkdir(parents=True)
    (source_root / 'server').mkdir(parents=True)
    (root / 'plugin' / 'yt_dlp_plugins').mkdir(parents=True)
    node_archive = root / 'node' / 'node.zip'
    provider_archive = root / 'provider.zip'
    node_archive.parent.mkdir(parents=True, exist_ok=True)
    node_archive.write_bytes(b'node archive')
    provider_archive.write_bytes(b'provider archive')
    extracted = []

    def extract(archive, destination, *, archive_type):
        extracted.append((archive, destination, archive_type))
        if archive == node_archive:
            spec = youtube_compat.NODE_SPECS[youtube_compat.platform_key()]
            installed = destination / spec.root_name
            installed.mkdir(parents=True)
            node = installed / spec.node_relative
            npm = installed / spec.npm_relative
            node.parent.mkdir(parents=True, exist_ok=True)
            npm.parent.mkdir(parents=True, exist_ok=True)
            node.write_bytes(b'node')
            npm.write_bytes(b'npm')
        else:
            installed = destination / youtube_compat.PROVIDER_SOURCE_ROOT
            (installed / 'server').mkdir(parents=True)
            (installed / 'server' / 'package.json').write_text('{"name":"bgutil-ytdlp-pot-provider","version":"2.0.0","dependencies":{},"scripts":{}}', encoding='utf-8')
            (installed / 'server' / 'package-lock.json').write_text('{"name":"bgutil-ytdlp-pot-provider","lockfileVersion":3,"packages":{}}', encoding='utf-8')
            (installed / 'server' / 'tsconfig.json').write_text('{"compilerOptions":{},"include":["./src/**/*"]}', encoding='utf-8')
            for name in ('main.ts', 'generate_once.ts', 'session_manager.ts', 'utils.ts'):
                source_file = installed / 'server' / 'src' / name
                source_file.parent.mkdir(parents=True, exist_ok=True)
                source_file.write_text('source', encoding='utf-8')
            type_file = installed / 'server' / 'types' / 'commander.d.ts'
            type_file.parent.mkdir(parents=True, exist_ok=True)
            type_file.write_text('type source = unknown', encoding='utf-8')
            plugin_dir = installed / 'plugin' / 'yt_dlp_plugins' / 'extractor'
            plugin_dir.mkdir(parents=True)
            for name in ('getpot_bgutil.py', 'getpot_bgutil_http.py', 'getpot_bgutil_script.py'):
                (plugin_dir / name).write_text('plugin', encoding='utf-8')

    monkeypatch.setattr(youtube_compat.runtime, 'extract_archive_verified', extract)

    youtube_compat._extract_assets(object(), [node_archive, provider_archive])

    assert [item[0] for item in extracted] == [node_archive, provider_archive]


def test_youtube_source_integrity_requires_pinned_build_inputs(monkeypatch, tmp_path):
    source = tmp_path / youtube_compat.PROVIDER_SOURCE_ROOT
    server = source / 'server'
    plugin = source / 'plugin' / 'yt_dlp_plugins' / 'extractor'
    server.mkdir(parents=True)
    plugin.mkdir(parents=True)
    (server / 'package.json').write_text('{}', encoding='utf-8')
    for name in ('getpot_bgutil.py', 'getpot_bgutil_http.py', 'getpot_bgutil_script.py'):
        (plugin / name).write_text('plugin', encoding='utf-8')
    monkeypatch.setattr(youtube_compat, 'source_home', lambda: source)

    assert youtube_compat._source_install_ready() is False

    (server / 'package.json').write_text('{"name":"bgutil-ytdlp-pot-provider","version":"2.0.0","dependencies":{},"scripts":{}}', encoding='utf-8')
    (server / 'package-lock.json').write_text('{"name":"bgutil-ytdlp-pot-provider","lockfileVersion":3,"packages":{}}', encoding='utf-8')
    (server / 'tsconfig.json').write_text('{"compilerOptions":{},"include":["./src/**/*"]}', encoding='utf-8')
    for name in ('main.ts', 'generate_once.ts', 'session_manager.ts', 'utils.ts'):
        source_file = server / 'src' / name
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text('source', encoding='utf-8')
    type_file = server / 'types' / 'commander.d.ts'
    type_file.parent.mkdir(parents=True, exist_ok=True)
    type_file.write_text('type source = unknown', encoding='utf-8')
    assert youtube_compat._source_install_ready() is True

    (server / 'src' / 'main.ts').unlink()
    assert youtube_compat._source_install_ready() is False


def test_youtube_source_readiness_ignores_stale_adjacent_provider_tree(monkeypatch, tmp_path):
    current = tmp_path / youtube_compat.PROVIDER_VERSION / youtube_compat.PROVIDER_SOURCE_ROOT
    server = current / 'server'
    plugin = current / 'plugin' / 'yt_dlp_plugins' / 'extractor'
    server.mkdir(parents=True)
    plugin.mkdir(parents=True)
    (server / 'package.json').write_text(
        '{"name":"bgutil-ytdlp-pot-provider","version":"2.0.0","dependencies":{},"scripts":{}}',
        encoding='utf-8',
    )
    (server / 'package-lock.json').write_text(
        '{"name":"bgutil-ytdlp-pot-provider","lockfileVersion":3,"packages":{}}',
        encoding='utf-8',
    )
    (server / 'tsconfig.json').write_text('{"compilerOptions":{},"include":["./src/**/*"]}', encoding='utf-8')
    for name in ('main.ts', 'generate_once.ts', 'session_manager.ts', 'utils.ts'):
        source_file = server / 'src' / name
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text('source', encoding='utf-8')
    type_file = server / 'types' / 'commander.d.ts'
    type_file.parent.mkdir(parents=True, exist_ok=True)
    type_file.write_text('type source = unknown', encoding='utf-8')
    for name in ('getpot_bgutil.py', 'getpot_bgutil_http.py', 'getpot_bgutil_script.py'):
        (plugin / name).write_text('plugin', encoding='utf-8')

    stale = tmp_path / '1.3.2' / youtube_compat.PROVIDER_SOURCE_ROOT
    (stale / 'server').mkdir(parents=True)
    (stale / 'server' / 'package.json').write_text('{"version":"1.3.2"}', encoding='utf-8')
    monkeypatch.setattr(youtube_compat, 'source_home', lambda: current)

    assert youtube_compat._source_install_ready() is True


def test_youtube_integrity_rejects_malformed_package_and_zero_byte_plugin(monkeypatch, tmp_path):
    source = tmp_path / youtube_compat.PROVIDER_SOURCE_ROOT
    server = source / 'server'
    source_plugin = source / 'plugin' / 'yt_dlp_plugins' / 'extractor'
    server.mkdir(parents=True)
    source_plugin.mkdir(parents=True)
    (server / 'package.json').write_text('not-json', encoding='utf-8')
    (source / youtube_compat.PROVIDER_PLUGIN_RELATIVE).write_text('', encoding='utf-8')
    monkeypatch.setattr(youtube_compat, 'source_home', lambda: source)
    monkeypatch.setattr(youtube_compat, 'plugin_dir', lambda: tmp_path / 'installed-plugin')

    assert youtube_compat._source_install_ready() is False
    assert youtube_compat._provider_plugin_ready() is False

def test_provider_build_readiness_rejects_empty_output(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_compat, "_root", lambda: tmp_path)
    monkeypatch.setattr(youtube_compat, "node_path", lambda: tmp_path / "node")
    monkeypatch.setattr(youtube_compat, "npm_path", lambda: tmp_path / "npm")
    monkeypatch.setattr(youtube_compat, "_source_install_ready", lambda: True)
    monkeypatch.setattr(youtube_compat, "_provider_plugin_ready", lambda: True)
    server = tmp_path / "source" / youtube_compat.PROVIDER_SOURCE_ROOT / "server"
    server.mkdir(parents=True)
    _write_provider_manifests(server)
    modules = server / "node_modules"
    (modules / "commander").mkdir(parents=True)
    (modules / "commander" / "package.json").write_text("{}", encoding="utf-8")
    (modules / "typescript").mkdir()
    (modules / "typescript" / "package.json").write_text("{}", encoding="utf-8")
    (modules / ".bin").mkdir()
    (modules / ".bin" / "tsc.cmd").write_text("tsc", encoding="utf-8")
    (modules / ".package-lock.json").write_text(
        '{"lockfileVersion":3,"packages":{"":{"dependencies":{"commander":"1.0.0"},"devDependencies":{"typescript":"1.0.0"}},"node_modules/commander":{"version":"1.0.0"},"node_modules/typescript":{"version":"1.0.0"}}}',
        encoding="utf-8",
    )
    (tmp_path / "node").write_bytes(b"node")
    (tmp_path / "npm").write_bytes(b"npm")
    (server / "build").mkdir()
    (server / "build" / "main.js").write_text("", encoding="utf-8")

    assert youtube_compat._server_ready() is False

    (server / "build" / "main.js").write_text("compiled provider", encoding="utf-8")
    assert youtube_compat._server_ready() is True


def test_provider_build_swaps_compiled_output_atomically(tmp_path, monkeypatch):
    server = tmp_path / "server"
    server.mkdir()
    old_build = server / "build"
    old_build.mkdir()
    (old_build / "main.js").write_text("old", encoding="utf-8")
    npm = tmp_path / "npm"
    npm.touch()

    def fake_command(args, *, cwd, failure_code, event):
        staged = tmp_path / args[args.index("--outDir") + 1]
        staged.mkdir(parents=True)
        (staged / "main.js").write_text("new", encoding="utf-8")

    monkeypatch.setattr(youtube_compat, "_run_provider_command", fake_command)
    youtube_compat._build_provider(npm, server, event=None)

    assert (server / "build" / "main.js").read_text(encoding="utf-8") == "new"
    assert not list(server.glob(".provider-build-*.backup"))


def _write_provider_manifests(server: Path) -> None:
    (server / "package.json").write_text(
        '{"name":"bgutil-ytdlp-pot-provider","version":"2.0.0","dependencies":{"commander":"1.0.0"},"devDependencies":{"typescript":"1.0.0"}}',
        encoding="utf-8",
    )
    (server / "package-lock.json").write_text(
        '{"name":"bgutil-ytdlp-pot-provider","version":"2.0.0","lockfileVersion":3,"packages":{"":{"dependencies":{"commander":"1.0.0"},"devDependencies":{"typescript":"1.0.0"}},"node_modules/commander":{"version":"1.0.0"},"node_modules/typescript":{"version":"1.0.0"}}}',
        encoding="utf-8",
    )


def test_youtube_node_modules_readiness_requires_locked_direct_dependencies_and_compiler(tmp_path, monkeypatch):
    server = tmp_path / "server"
    server.mkdir()
    monkeypatch.setattr(youtube_compat, "server_home", lambda: server)

    assert youtube_compat._node_modules_ready() is False
    (server / "node_modules").mkdir()
    assert youtube_compat._node_modules_ready() is False
    (server / "node_modules" / ".package-lock.json").write_text("{}", encoding="utf-8")
    assert youtube_compat._node_modules_ready() is False

    _write_provider_manifests(server)
    (server / "package-lock.json").write_text(
        '{"name":"bgutil-ytdlp-pot-provider","version":"2.0.0","lockfileVersion":3,"packages":{"":{"dependencies":{"commander":"1.0.0"},"devDependencies":{"typescript":"1.0.0"}},"node_modules/commander":{"version":"1.0.0"},"node_modules/typescript":{"version":"1.0.0"},"node_modules/commander/node_modules/transitive":{"version":"1.0.0"}}}',
        encoding="utf-8",
    )
    modules = server / "node_modules"
    (modules / "commander").mkdir()
    (modules / "commander" / "package.json").write_text("{}", encoding="utf-8")
    (modules / "typescript").mkdir()
    (modules / "typescript" / "package.json").write_text("{}", encoding="utf-8")
    (modules / ".bin").mkdir()
    (modules / ".bin" / "tsc.cmd").write_text("tsc", encoding="utf-8")
    (modules / ".package-lock.json").write_text(
        '{"lockfileVersion":3,"packages":{"":{"dependencies":{"commander":"1.0.0"},"devDependencies":{"typescript":"1.0.0"}},"node_modules/commander":{"version":"1.0.0"},"node_modules/typescript":{"version":"1.0.0"},"node_modules/commander/node_modules/transitive":{"version":"1.0.0"}}}',
        encoding="utf-8",
    )
    assert youtube_compat._node_modules_ready() is False
    transitive = modules / "commander" / "node_modules" / "transitive"
    transitive.mkdir(parents=True)
    (transitive / "package.json").write_text("{}", encoding="utf-8")
    assert youtube_compat._node_modules_ready() is True


def test_youtube_provider_commands_prepend_managed_node_bin_to_path(tmp_path, monkeypatch):
    managed_node = tmp_path / "managed-node" / "node.exe"
    managed_node.parent.mkdir()
    managed_node.write_bytes(b"node")
    captured: dict[str, object] = {}

    def fake_run(args, *, cwd, env, **kwargs):
        captured.update({"args": args, "cwd": cwd, "env": env, "kwargs": kwargs})
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(youtube_compat, "node_path", lambda: managed_node)
    monkeypatch.setenv("PATH", "ambient-path")
    monkeypatch.setattr(youtube_compat.subprocess, "run", fake_run)

    youtube_compat._run_provider_command(["npm.cmd", "ci"], cwd=tmp_path, failure_code="TEST", event=None)

    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["PATH"] == f"{managed_node.parent}{os.pathsep}ambient-path"


def test_youtube_install_repairs_empty_node_modules(tmp_path, monkeypatch):
    server = tmp_path / "server"
    server.mkdir()
    (server / "package.json").write_text("{}", encoding="utf-8")
    modules = server / "node_modules"
    modules.mkdir()
    node = tmp_path / "node"
    npm = tmp_path / "npm"
    node.write_bytes(b"node")
    npm.write_bytes(b"npm")
    archives = [tmp_path / "node.zip", tmp_path / "provider.zip", tmp_path / "yt-dlp"]
    for archive in archives:
        archive.write_bytes(b"archive")
    commands = []

    monkeypatch.setattr(youtube_compat, "assets", lambda: [object(), object(), object()])
    monkeypatch.setattr(youtube_compat.DownloadManager, "download", lambda self, asset, cancel=None: archives.pop(0))
    monkeypatch.setattr(youtube_compat, "_extract_assets", lambda manager, paths: None)
    monkeypatch.setattr(youtube_compat, "node_path", lambda: node)
    monkeypatch.setattr(youtube_compat, "npm_path", lambda: npm)
    monkeypatch.setattr(youtube_compat, "server_home", lambda: server)
    monkeypatch.setattr(youtube_compat, "_source_install_ready", lambda: True)
    monkeypatch.setattr(youtube_compat, "_provider_plugin_ready", lambda: True)
    monkeypatch.setattr(youtube_compat, "_build_ready", lambda _build: True)
    monkeypatch.setattr(youtube_compat, "_server_ready", lambda: True)

    def fake_command(args, **kwargs):
        commands.append(args)
        modules.mkdir(parents=True, exist_ok=True)
        (modules / ".package-lock.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(youtube_compat, "_run_provider_command", fake_command)
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, "start", lambda self: "http://127.0.0.1:4416")
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, "self_test", lambda self: {"plugin_discoverable": True, "server_installed": True, "health": {"healthy": True}})
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, "stop", lambda self: None)

    youtube_compat.install(require_consent=False)

    assert commands and commands[0][1:3] == ["ci", "--no-audit"]


def test_provider_build_cleans_interrupted_staging_before_rebuild(tmp_path, monkeypatch):
    server = tmp_path / "server"
    server.mkdir()
    (server / ".provider-build-interrupted").mkdir()
    npm = tmp_path / "npm"
    npm.touch()

    def fake_command(args, *, cwd, failure_code, event):
        staged = Path(args[args.index("--outDir") + 1])
        staged.mkdir(parents=True)
        (staged / "main.js").write_text("new", encoding="utf-8")

    monkeypatch.setattr(youtube_compat, "_run_provider_command", fake_command)
    youtube_compat._build_provider(npm, server, event=None)

    assert not (server / ".provider-build-interrupted").exists()


def test_youtube_setup_group_includes_pinned_ytdlp_asset():
    asset_ids = {asset.asset_id for asset in youtube_compat.assets()}
    assert any(asset_id.startswith('runtime:yt-dlp:') for asset_id in asset_ids)


def test_youtube_readiness_does_not_block_on_dormant_provider(monkeypatch, tmp_path):
    self_tests = []
    monkeypatch.setattr(youtube_compat.config, 'home_dir', lambda: tmp_path)
    monkeypatch.setattr(youtube_compat, '_yt_dlp_ready', lambda: True)
    monkeypatch.setattr(youtube_compat.DownloadManager, 'inventory', lambda self, assets: [
        {'asset_id': asset.asset_id, 'installed': True, 'status': 'ready'} for asset in assets
    ])
    monkeypatch.setattr(youtube_compat, '_server_ready', lambda: True)
    monkeypatch.setattr(youtube_compat, '_provider_plugin_ready', lambda: True)
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, 'self_test', lambda self: (self_tests.append(True) or {
        'plugin_discoverable': True, 'server_installed': True,
        'health': {'healthy': False, 'running': False}, 'loopback_only': True, 'ok': False,
    }))
    result = youtube_compat.readiness()
    assert result['state'] == 'DEPENDENCIES_READY'
    assert result['dependency_state'] == 'DEPENDENCIES_READY'
    assert result['ready'] is True
    assert result['provider_state'] == 'DORMANT'
    assert result['public_download_verified'] is False
    assert self_tests == []


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
        'health': {'healthy': True, 'running': True, 'version': '2.0.0'},
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


def test_youtube_attestation_recovery_restarts_once_without_cookies(monkeypatch):
    events = []
    monkeypatch.setattr(ytdlp.youtube_compat, "invalidate_public_compatibility", lambda: events.append("invalidate"))
    monkeypatch.setattr(ytdlp, "_stop_operation_provider", lambda: events.append("stop"))
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ytdlp.YtDlpError(
                "HTTP Error 403: Forbidden",
                code="YTDLP_ATTESTATION_REQUIRED",
                details={
                    "failure_phase": "GVS_TRANSFER",
                    "http_status": 403,
                },
            )
        raise ytdlp.YtDlpError(
            "HTTP Error 403: Forbidden",
            code="YTDLP_ATTESTATION_REQUIRED",
            details={
                "failure_phase": "GVS_TRANSFER",
                "http_status": 403,
            },
        )

    with pytest.raises(ytdlp.YtDlpError) as exc_info:
        ytdlp._run_youtube_recovery(
            operation,
            source_url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
            cookies_from_browser=None,
        )

    assert attempts == 2
    assert events == ["invalidate", "stop"]
    assert exc_info.value.details["cache_invalidated"] is True
    assert exc_info.value.details["retry_count"] == 1


def test_youtube_attestation_recovery_never_uses_cookies_implicitly(monkeypatch):
    called = []
    monkeypatch.setattr(ytdlp.youtube_compat, "invalidate_public_compatibility", lambda: called.append(True))

    def operation():
        raise ytdlp.YtDlpError(
            "HTTP Error 403: Forbidden",
            code="YTDLP_ATTESTATION_REQUIRED",
            details={"failure_phase": "GVS_TRANSFER", "http_status": 403},
        )

    with pytest.raises(ytdlp.YtDlpError):
        ytdlp._run_youtube_recovery(
            operation,
            source_url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
            cookies_from_browser="chrome",
        )
    assert called == []


def test_youtube_readiness_distinguishes_dependencies_from_public_download(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_compat.config, 'home_dir', lambda: tmp_path)
    monkeypatch.setattr(youtube_compat, '_yt_dlp_ready', lambda: True)
    monkeypatch.setattr(youtube_compat.DownloadManager, 'inventory', lambda self, assets: [
        {'asset_id': asset.asset_id, 'installed': True, 'status': 'ready'} for asset in assets
    ])
    monkeypatch.setattr(youtube_compat, '_server_ready', lambda: True)
    monkeypatch.setattr(youtube_compat, '_provider_plugin_ready', lambda: True)
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, 'self_test', lambda self: {
        'plugin_discoverable': True, 'server_installed': True,
        'health': {'healthy': True, 'running': True, 'version': '2.0.0'}, 'loopback_only': True, 'ok': True,
    })
    result = youtube_compat.readiness()
    assert result['state'] == 'DEPENDENCIES_READY'
    assert result['ready'] is True
    assert result['public_download_verified'] is False
    assert result['dependency_state'] == 'DEPENDENCIES_READY'


def test_youtube_readiness_keeps_dependency_and_public_transfer_times_distinct(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_compat.config, 'home_dir', lambda: tmp_path)
    monkeypatch.setattr(youtube_compat, '_yt_dlp_ready', lambda: True)
    monkeypatch.setattr(youtube_compat.DownloadManager, 'inventory', lambda self, assets: [
        {'asset_id': asset.asset_id, 'installed': True, 'status': 'ready'} for asset in assets
    ])
    monkeypatch.setattr(youtube_compat, '_server_ready', lambda: True)
    monkeypatch.setattr(youtube_compat, '_provider_plugin_ready', lambda: True)
    youtube_compat.record_public_compatibility_success(method='bgutil-http', ytdlp_version='2026.08.19')

    result = youtube_compat.readiness()

    assert isinstance(result['dependency_checked_at'], str)
    assert result.get('provider_self_tested_at') is None
    assert result['public_transfer_verified_at'] == result['public_compatibility']['verified_at']
    assert result['public_download_verified'] is True


def test_youtube_self_test_records_only_provider_self_test_time(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_compat.config, 'home_dir', lambda: tmp_path)
    initial = {
        'state': 'DEPENDENCIES_READY',
        'ready': True,
        'public_download_verified': False,
        'public_transfer_verified_at': '2026-09-01T00:00:00+00:00',
        'checks': [],
    }
    monkeypatch.setattr(youtube_compat, 'readiness', lambda: initial)
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, 'start', lambda self: 'http://127.0.0.1:4416')
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, 'self_test', lambda self: {
        'plugin_discoverable': True,
        'server_installed': True,
        'health': {'healthy': True, 'running': True, 'version': '2.0.0'},
        'loopback_only': True,
        'ok': True,
    })
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, 'stop', lambda self: None)

    result = youtube_compat.test()

    assert isinstance(result['provider_self_tested_at'], str)
    assert result['public_transfer_verified_at'] == initial['public_transfer_verified_at']


def test_public_download_records_transfer_verification_after_output_exists(monkeypatch, tmp_path):
    from clipgauge_pipeline.ingest import ytdlp

    monkeypatch.setattr(youtube_compat.config, 'home_dir', lambda: tmp_path)
    binary = tmp_path / 'yt-dlp.exe'
    output = tmp_path / 'video.mp4'
    monkeypatch.setattr(ytdlp, 'ensure_ytdlp', lambda progress: binary)
    monkeypatch.setattr(ytdlp, '_youtube_provider_args', lambda *args, **kwargs: [])
    monkeypatch.setattr(ytdlp, '_stop_operation_provider', lambda: None)
    monkeypatch.setattr(ytdlp, '_run_youtube_recovery', lambda fn, **kwargs: fn())
    monkeypatch.setattr(ytdlp, '_run', lambda binary_path, args, on_line=None: output.write_bytes(b'video') or '')
    monkeypatch.setattr(ytdlp.ffmpeg_bin, 'readiness', lambda: type('Decision', (), {'ready': False})())

    ytdlp.download('https://www.youtube.com/watch?v=aqz-KE-bpKQ', output, lambda *_args: None)

    status = youtube_compat.public_compatibility_status()
    assert status['verified'] is True
    assert status['provider_version'] == youtube_compat.PROVIDER_VERSION


def test_youtube_readiness_rejects_public_verification_from_old_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_compat.config, 'home_dir', lambda: tmp_path)
    monkeypatch.setattr(youtube_compat, '_yt_dlp_ready', lambda: True)
    monkeypatch.setattr(youtube_compat.DownloadManager, 'inventory', lambda self, assets: [
        {'asset_id': asset.asset_id, 'installed': True, 'status': 'ready'} for asset in assets
    ])
    monkeypatch.setattr(youtube_compat, '_server_ready', lambda: True)
    monkeypatch.setattr(youtube_compat, '_provider_plugin_ready', lambda: True)
    (tmp_path / youtube_compat.PUBLIC_COMPATIBILITY_FILENAME).write_text(
        '{"verified": true, "provider_version": "1.3.2", "yt_dlp_version": "2026.08.19", "method": "mweb"}',
        encoding='utf-8',
    )

    result = youtube_compat.readiness()

    assert result['state'] == 'DEPENDENCIES_READY'
    assert result['public_download_verified'] is False


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


def test_windows_browser_discovery_checks_installed_paths_without_profiles(monkeypatch, tmp_path):
    from clipgauge_pipeline.ingest import youtube_compat

    chrome = tmp_path / "Google" / "Chrome" / "Application" / "chrome.exe"
    chrome.parent.mkdir(parents=True)
    chrome.write_bytes(b"browser")
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "missing-x86"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "missing-local"))
    monkeypatch.setattr(youtube_compat.shutil, "which", lambda _name: None)

    assert youtube_compat._find_browser() == str(chrome.resolve())


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
        stderr='[debug] [youtube] [pot] PO Token Providers: bgutil:http-2.0.0 (external)\nERROR: HTTP Error 403: Forbidden',
        http_status=403,
    )
    assert diagnostic['failure_phase'] == 'GVS_TRANSFER'
    assert diagnostic['provider'] == 'bgutil:http-2.0.0'
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
    monkeypatch.setattr(youtube_compat, '_provider_plugin_ready', lambda: True)
    monkeypatch.setattr(youtube_compat.ProviderSupervisor, 'self_test', lambda self: {
        'plugin_discoverable': True, 'server_installed': True,
        'health': {'healthy': True, 'running': True, 'version': '2.0.0'}, 'loopback_only': True, 'ok': True,
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


def test_youtube_guest_defaults_to_mweb_client():
    from clipgauge_pipeline.ingest import ytdlp

    class StubSupervisor:
        def start(self):
            return 'http://127.0.0.1:4416'

        def self_test(self):
            return {'ok': True}

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(ytdlp, '_provider_supervisor', StubSupervisor())
        args = ytdlp._youtube_provider_args('https://www.youtube.com/watch?v=aqz-KE-bpKQ')
    finally:
        monkeypatch.undo()

    assert 'youtube:player_client=mweb' in ' '.join(args)


def test_youtube_metadata_failure_stops_operation_scoped_provider(monkeypatch, tmp_path):
    from clipgauge_pipeline.ingest import ytdlp

    class StubSupervisor:
        def __init__(self):
            self.stopped = False

        def start(self):
            return 'http://127.0.0.1:4416'

        def self_test(self):
            return {'ok': True}

        def stop(self):
            self.stopped = True

    supervisor = StubSupervisor()
    monkeypatch.setattr(ytdlp, '_provider_supervisor', supervisor)
    monkeypatch.setattr(ytdlp, 'ensure_ytdlp', lambda progress: tmp_path / 'yt-dlp.exe')
    monkeypatch.setattr(ytdlp, '_run', lambda *args, **kwargs: (_ for _ in ()).throw(ytdlp.YtDlpError('blocked', code='YTDLP_ATTESTATION_REQUIRED')))

    with pytest.raises(ytdlp.YtDlpError):
        ytdlp.fetch_meta('https://www.youtube.com/watch?v=aqz-KE-bpKQ', lambda *_: None)

    assert supervisor.stopped is True


def test_local_file_fallback_bypasses_all_youtube_providers():
    from clipgauge_pipeline.ingest import ytdlp
    assert ytdlp._youtube_provider_args('/managed/jobs/example/media.mp4') == []
    assert ytdlp._needs_youtube_provider('/managed/jobs/example/media.mp4') is False


def test_youtube_share_urls_normalize_without_timestamp_parameter():
    from clipgauge_pipeline.ingest import ytdlp

    canonical = 'https://www.youtube.com/watch?v=_AbFXuGDRTs'

    assert ytdlp.normalize_youtube_url('https://www.youtube.com/watch?v=_AbFXuGDRTs&t=41s') == canonical
    assert ytdlp.normalize_youtube_url('https://youtu.be/_AbFXuGDRTs?t=41') == canonical
    assert ytdlp.normalize_youtube_url('https://www.youtube-nocookie.com/watch?v=_AbFXuGDRTs&feature=share') == canonical


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
