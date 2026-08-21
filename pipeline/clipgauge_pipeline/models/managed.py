"""Managed speech, alignment, and sentence-data assets for v0.4."""

from __future__ import annotations

import os
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

from .. import config, downloads, runtime

ASR_REVISION = "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"
SILERO_REVISION = "806dcba3f0b5d95282d0889a074954a2f8c6397b"
ASR_ROOT = config.models_dir() / "asr" / "faster-whisper-large-v3-turbo" / ASR_REVISION
SILERO_ARCHIVE = config.models_dir() / "torch" / "hub" / f"silero-vad-{SILERO_REVISION}.zip"
SILERO_HUB_ROOT = config.models_dir() / "torch" / "hub" / "snakers4_silero-vad_master"
TORCH_CHECKPOINT = "wav2vec2_fairseq_base_ls960_asr_ls960.pth"
ASR_GROUP = "core:asr"


def _asset(
    asset_id: str,
    display_name: str,
    purpose: str,
    destination: Path,
    url: str,
    size: int,
    sha256: str,
    *,
    license: str,
    source: str,
    source_revision: str = ASR_REVISION,
    archive_type: str | None = None,
    expected_paths: tuple[str, ...] = (),
    installed_size_bytes: int | None = None,
) -> downloads.ManagedAsset:
    return downloads.ManagedAsset(
        asset_id=asset_id,
        display_name=display_name,
        purpose=purpose,
        destination=str(destination.relative_to(config.home_dir())),
        url=url,
        size_bytes=size,
        sha256=sha256,
        required=True,
        one_time=True,
        license=license,
        source=source,
        consent_group=ASR_GROUP,
        source_revision=source_revision,
        archive_type=archive_type,
        expected_paths=expected_paths,
        installed_size_bytes=installed_size_bytes,
    )


def asr_assets() -> list[downloads.ManagedAsset]:
    base = f"https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo/resolve/{ASR_REVISION}"
    source = f"https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo/tree/{ASR_REVISION}"
    return [
        _asset(
            "model:asr:faster-whisper-large-v3-turbo:model.bin",
            "Speech recognition weights",
            "Local speech transcription",
            ASR_ROOT / "model.bin",
            f"{base}/model.bin?download=true",
            1_617_884_929,
            "e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da",
            license="MIT model conversion; OpenAI Whisper notices apply",
            source=source,
        ),
        _asset(
            "model:asr:faster-whisper-large-v3-turbo:config",
            "Speech recognition configuration",
            "CTranslate2 model configuration",
            ASR_ROOT / "config.json",
            f"{base}/config.json?download=true",
            2_263,
            "b0253ea6c0d3bea6b1e19e91a02acfd3b53f4467362efcb5a3e6b16c9b3a9b7e",
            license="MIT model conversion; OpenAI Whisper notices apply",
            source=source,
        ),
        _asset(
            "model:asr:faster-whisper-large-v3-turbo:preprocessor",
            "Speech preprocessing configuration",
            "CTranslate2 model preprocessing",
            ASR_ROOT / "preprocessor_config.json",
            f"{base}/preprocessor_config.json?download=true",
            340,
            "7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711",
            license="MIT model conversion; OpenAI Whisper notices apply",
            source=source,
        ),
        _asset(
            "model:asr:faster-whisper-large-v3-turbo:tokenizer",
            "Speech tokenizer",
            "CTranslate2 tokenizer",
            ASR_ROOT / "tokenizer.json",
            f"{base}/tokenizer.json?download=true",
            2_710_337,
            "297b13372ac43916285644fb9687add3cc62ee2a1adb60da3dc25cc94c1871fd",
            license="MIT model conversion; OpenAI Whisper notices apply",
            source=source,
        ),
        _asset(
            "model:asr:faster-whisper-large-v3-turbo:vocabulary",
            "Speech vocabulary",
            "CTranslate2 vocabulary",
            ASR_ROOT / "vocabulary.json",
            f"{base}/vocabulary.json?download=true",
            1_068_114,
            "c69260f2ab26d659b7c398f9a2b2b48ed0df16c3b47d7326782fd9cba71690c1",
            license="MIT model conversion; OpenAI Whisper notices apply",
            source=source,
        ),
    ]


def silero_asset() -> downloads.ManagedAsset:
    return _asset(
        "model:vad:silero-vad",
        "Silero voice activity detector",
        "Offline speech activity detection for WhisperX",
        SILERO_ARCHIVE,
        f"https://github.com/snakers4/silero-vad/archive/{SILERO_REVISION}.zip",
        28_235_828,
        "f5af06ac1db1e294364a6c0218b56e0d6b14958b380252fe64f0c0e9bbca7a30",
        license="MIT",
        source=f"https://github.com/snakers4/silero-vad/tree/{SILERO_REVISION}",
        source_revision=SILERO_REVISION,
        archive_type="zip",
        expected_paths=("hubconf.py", "src/silero_vad/utils_vad.py", "src/silero_vad/data/silero_vad.jit"),
        installed_size_bytes=70_724_504,
    )


def alignment_asset() -> downloads.ManagedAsset:
    return _asset(
        "model:alignment:en:wav2vec2-base-960h",
        "English word-alignment model",
        "Word timestamps for captions and candidate boundaries",
        config.models_dir() / "torch" / "checkpoints" / TORCH_CHECKPOINT,
        f"https://download.pytorch.org/torchaudio/models/{TORCH_CHECKPOINT}",
        377_664_473,
        "488fd4f16de84438ffc945334278c1b9fb9b7159a806c1080b16111a958c945d",
        license="MIT; LibriSpeech-trained torchaudio/fairseq checkpoint",
        source="https://docs.pytorch.org/audio/main/generated/torchaudio.pipelines.WAV2VEC2_ASR_BASE_960H.html",
    )


def punkt_asset() -> downloads.ManagedAsset:
    return _asset(
        "data:nltk:punkt-tab",
        "Sentence splitting data",
        "WhisperX alignment sentence segmentation",
        config.data_dir() / "nltk" / "punkt_tab.zip",
        "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/tokenizers/punkt_tab.zip",
        4_319_076,
        "e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106",
        license="NLTK data license; see upstream nltk_data notices",
        source="https://github.com/nltk/nltk_data/tree/gh-pages/packages/tokenizers",
    )


def all_assets() -> list[downloads.ManagedAsset]:
    return [*asr_assets(), silero_asset(), alignment_asset(), punkt_asset()]


def migrate_existing_caches(manager: downloads.DownloadManager) -> dict[str, str]:
    """Reuse verified v0.3/library caches without deleting legacy data."""
    source_candidates = [
        config.models_dir() / "hf" / "hub" / "models--dropbox-dash--faster-whisper-large-v3-turbo" / "snapshots" / ASR_REVISION,
        Path.home() / ".cache" / "huggingface" / "hub" / "models--dropbox-dash--faster-whisper-large-v3-turbo" / "snapshots" / ASR_REVISION,
    ]
    outcomes: dict[str, str] = {}
    for asset in asr_assets():
        relative = Path(asset.destination).relative_to(Path("models"))
        copied = False
        for source_root in source_candidates:
            candidate = source_root / relative.name
            if candidate.is_file():
                outcomes[asset.asset_id] = manager.migrate_legacy_asset(asset, [candidate])
                copied = True
                break
        if not copied:
            outcomes[asset.asset_id] = "not-found"
    return outcomes


def local_env() -> dict[str, str]:
    hf_home = config.models_dir() / "hf"
    torch_home = config.models_dir() / "torch"
    nltk_home = config.nltk_data_dir()
    for directory in (hf_home, torch_home, torch_home / "checkpoints", nltk_home):
        directory.mkdir(parents=True, exist_ok=True)
    return {
        "HF_HOME": str(hf_home),
        "TORCH_HOME": str(torch_home),
        "NLTK_DATA": str(nltk_home),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }


def apply_local_env() -> None:
    for key, value in local_env().items():
        os.environ[key] = value


def asr_model_path() -> Path:
    return ASR_ROOT


def alignment_model_dir() -> Path:
    path = config.models_dir() / "torch" / "checkpoints"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_extract_punkt(archive: Path) -> None:
    target_root = config.nltk_data_dir()
    staging = target_root / f".punkt_tab.{time.time_ns()}.staging"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(archive) as handle:
            for info in handle.infolist():
                name = info.filename.replace("\\", "/")
                path = Path(name)
                if not name or path.is_absolute() or ".." in path.parts:
                    raise runtime.RuntimeIntegrityError("punkt archive contains an unsafe path")
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise runtime.RuntimeIntegrityError("punkt archive contains a symlink")
                output = staging / path
                if info.is_dir():
                    output.mkdir(parents=True, exist_ok=True)
                    continue
                output.parent.mkdir(parents=True, exist_ok=True)
                with handle.open(info) as source, output.open("wb") as target:
                    shutil.copyfileobj(source, target)
        extracted = staging / "punkt_tab"
        if not extracted.is_dir():
            raise runtime.RuntimeIntegrityError("punkt archive did not contain punkt_tab data")
        destination = target_root / "tokenizers" / "punkt_tab"
        backup = target_root / f".punkt_tab.{time.time_ns()}.previous"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            os.replace(destination, backup)
        os.replace(extracted, destination)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _safe_extract_silero(archive: Path) -> None:
    """Install the pinned repo under the directory torch.hub expects."""
    target_root = SILERO_HUB_ROOT
    staging = target_root.parent / f".{target_root.name}.{time.time_ns()}.staging"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        root_name: str | None = None
        with zipfile.ZipFile(archive) as handle:
            for info in handle.infolist():
                name = info.filename.replace("\\", "/")
                path = Path(name)
                if not name or path.is_absolute() or ".." in path.parts:
                    raise runtime.RuntimeIntegrityError("Silero archive contains an unsafe path")
                if root_name is None:
                    root_name = path.parts[0]
                if not path.parts or path.parts[0] != root_name:
                    raise runtime.RuntimeIntegrityError("Silero archive has multiple roots")
                relative = Path(*path.parts[1:])
                if not relative:
                    continue
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise runtime.RuntimeIntegrityError("Silero archive contains a symlink")
                output = staging / relative
                if info.is_dir():
                    output.mkdir(parents=True, exist_ok=True)
                    continue
                output.parent.mkdir(parents=True, exist_ok=True)
                with handle.open(info) as source, output.open("wb") as target:
                    shutil.copyfileobj(source, target)
        required = [staging / item for item in silero_asset().expected_paths]
        if not all(path.is_file() for path in required):
            raise runtime.RuntimeIntegrityError("Silero archive is missing the torch.hub entrypoint or model")
        backup = target_root.parent / f".{target_root.name}.{time.time_ns()}.previous"
        if target_root.exists():
            os.replace(target_root, backup)
        os.replace(staging, target_root)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _ensure_silero_hub_cache() -> None:
    required = [SILERO_HUB_ROOT / item for item in silero_asset().expected_paths]
    if all(path.is_file() for path in required):
        return
    if not SILERO_ARCHIVE.is_file():
        raise runtime.RuntimeIntegrityError("Silero VAD archive is not installed")
    _safe_extract_silero(SILERO_ARCHIVE)


def prepare_assets(manager: downloads.DownloadManager, *, require_consent: bool, cancel: Callable[[], bool] | None = None) -> list[Path]:
    apply_local_env()
    migrate_existing_caches(manager)
    assets = all_assets()
    paths = manager.download_group(assets, group_id=ASR_GROUP, cancel=cancel) if require_consent else [manager.download(asset, cancel=cancel) for asset in assets]
    punkt_archive = config.data_dir() / "nltk" / "punkt_tab.zip"
    _safe_extract_punkt(punkt_archive)
    _ensure_silero_hub_cache()
    return paths


def ready(manager: downloads.DownloadManager) -> bool:
    apply_local_env()
    migrate_existing_caches(manager)
    assets = all_assets()
    rows = manager.inventory(assets)
    archive_installed = next((bool(row.get("installed")) for row in rows if row.get("asset_id") == silero_asset().asset_id), False)
    if archive_installed:
        _ensure_silero_hub_cache()
    punkt_ready = (config.nltk_data_dir() / "tokenizers" / "punkt_tab" / "english").is_dir()
    silero_ready = all(
        (SILERO_HUB_ROOT / item).is_file()
        for item in silero_asset().expected_paths
    )
    return all(bool(row.get("installed")) for row in rows) and archive_installed and punkt_ready and silero_ready
