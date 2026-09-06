use std::collections::HashMap;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::Command;

use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::sidecar::{self, RunPolicy};

#[derive(Clone)]
struct AssetSpec {
    asset_id: String,
    display_name: String,
    purpose: String,
    destination: String,
    installed_paths: Vec<String>,
    installed_hashes: Vec<(String, String)>,
    url: String,
    size_bytes: u64,
    sha256: String,
    required: bool,
    one_time: bool,
    license: String,
    source: String,
    consent_group: String,
    installed_size_bytes: Option<u64>,
}

fn text(value: Option<&Value>, fallback: &str) -> String {
    value
        .and_then(Value::as_str)
        .unwrap_or(fallback)
        .to_string()
}

fn number(value: Option<&Value>) -> u64 {
    value.and_then(Value::as_u64).unwrap_or_default()
}

fn manifest(resources: &Path) -> Result<Value, String> {
    let path = resources.join("runtime-manifest.json");
    let contents = fs::read_to_string(&path)
        .map_err(|error| format!("runtime manifest could not be read: {error}"))?;
    serde_json::from_str(&contents)
        .map_err(|error| format!("runtime manifest is invalid JSON: {error}"))
}

fn platform_key() -> &'static str {
    let architecture = std::env::consts::ARCH;
    if cfg!(target_os = "windows") {
        if architecture == "aarch64" {
            "windows-arm64"
        } else {
            "windows-x86_64"
        }
    } else if cfg!(target_os = "macos") {
        if architecture == "aarch64" {
            "macos-arm64"
        } else {
            "macos-x86_64"
        }
    } else if architecture == "aarch64" {
        "linux-arm64"
    } else {
        "linux-x86_64"
    }
}

fn yt_dlp_key() -> &'static str {
    if cfg!(target_os = "windows") {
        "yt-dlp.exe"
    } else if cfg!(target_os = "macos") {
        "yt-dlp_macos"
    } else if std::env::consts::ARCH == "aarch64" {
        "yt-dlp_linux_aarch64"
    } else {
        "yt-dlp_linux"
    }
}

fn manifest_asset<'a>(manifest: &'a Value, runtime: &str, key: &str) -> Option<&'a Value> {
    manifest
        .get("runtimes")?
        .get(runtime)?
        .get("assets")?
        .get(key)
}

fn manifest_model<'a>(manifest: &'a Value, key: &str) -> Option<&'a Value> {
    manifest.get("models")?.get(key)
}

fn model_spec(
    manifest: &Value,
    model_id: &str,
    manifest_key: &str,
    filename: &str,
) -> Option<AssetSpec> {
    let record = manifest_model(manifest, manifest_key)?;
    Some(AssetSpec {
        asset_id: model_id.to_string(),
        display_name: if model_id.contains("1.7b") {
            "Qwen3 1.7B · Lightweight".to_string()
        } else {
            "Qwen3 4B · Balanced".to_string()
        },
        purpose: "ClipGauge Local structured clip scoring".to_string(),
        destination: format!("models/clipgauge-local/{filename}"),
        installed_paths: vec![format!("models/clipgauge-local/{filename}")],
        installed_hashes: vec![(
            format!("models/clipgauge-local/{filename}"),
            text(record.get("sha256"), ""),
        )],
        url: text(record.get("url"), ""),
        size_bytes: number(record.get("size")),
        sha256: text(record.get("sha256"), ""),
        required: false,
        one_time: true,
        license: text(record.get("license"), "Apache-2.0"),
        source: text(record.get("provenance"), ""),
        consent_group: "core".to_string(),
        installed_size_bytes: None,
    })
}

#[allow(clippy::too_many_arguments)]
fn manifest_asset_spec(
    manifest: &Value,
    runtime: &str,
    key: &str,
    asset_id: &str,
    display_name: &str,
    purpose: &str,
    destination: &str,
    installed_path: &str,
    consent_group: &str,
    required: bool,
) -> Option<AssetSpec> {
    let record = manifest_asset(manifest, runtime, key)?;
    let runtime_record = manifest.get("runtimes")?.get(runtime)?;
    Some(AssetSpec {
        asset_id: asset_id.to_string(),
        display_name: display_name.to_string(),
        purpose: purpose.to_string(),
        destination: destination.to_string(),
        installed_paths: vec![installed_path.to_string()],
        installed_hashes: vec![(installed_path.to_string(), text(record.get("sha256"), ""))],
        url: text(record.get("url"), ""),
        size_bytes: number(record.get("size")),
        sha256: text(record.get("sha256"), ""),
        required,
        one_time: true,
        license: text(runtime_record.get("license"), "See upstream source"),
        source: text(runtime_record.get("provenance"), ""),
        consent_group: consent_group.to_string(),
        installed_size_bytes: None,
    })
}

#[allow(clippy::too_many_arguments)]
fn static_spec(
    asset_id: &str,
    display_name: &str,
    purpose: &str,
    destination: &str,
    installed_path: &str,
    url: &str,
    size_bytes: u64,
    sha256: &str,
    license: &str,
    source: &str,
    consent_group: &str,
    installed_size_bytes: Option<u64>,
) -> AssetSpec {
    AssetSpec {
        asset_id: asset_id.to_string(),
        display_name: display_name.to_string(),
        purpose: purpose.to_string(),
        destination: destination.to_string(),
        installed_paths: vec![installed_path.to_string()],
        installed_hashes: vec![(installed_path.to_string(), sha256.to_string())],
        url: url.to_string(),
        size_bytes,
        sha256: sha256.to_string(),
        required: true,
        one_time: true,
        license: license.to_string(),
        source: source.to_string(),
        consent_group: consent_group.to_string(),
        installed_size_bytes,
    }
}

#[allow(clippy::too_many_arguments)]
fn static_spec_with_paths(
    asset_id: &str,
    display_name: &str,
    purpose: &str,
    destination: &str,
    installed_paths: &[(&str, &str)],
    url: &str,
    size_bytes: u64,
    sha256: &str,
    license: &str,
    source: &str,
    consent_group: &str,
) -> AssetSpec {
    AssetSpec {
        asset_id: asset_id.to_string(),
        display_name: display_name.to_string(),
        purpose: purpose.to_string(),
        destination: destination.to_string(),
        installed_paths: installed_paths
            .iter()
            .map(|(path, _)| (*path).to_string())
            .collect(),
        installed_hashes: installed_paths
            .iter()
            .map(|(path, hash)| ((*path).to_string(), (*hash).to_string()))
            .collect(),
        url: url.to_string(),
        size_bytes,
        sha256: sha256.to_string(),
        required: true,
        one_time: true,
        license: license.to_string(),
        source: source.to_string(),
        consent_group: consent_group.to_string(),
        installed_size_bytes: None,
    }
}

fn static_core_specs() -> Vec<AssetSpec> {
    let asr_source = "https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo";
    vec![
        static_spec("model:asr:faster-whisper-large-v3-turbo:model.bin", "Speech recognition weights", "Local speech transcription", "models/asr/faster-whisper-large-v3-turbo/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/model.bin", "models/asr/faster-whisper-large-v3-turbo/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/model.bin", "https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo/resolve/e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da/model.bin?download=true", 1_617_884_929, "e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da", "MIT model conversion; OpenAI Whisper notices apply", asr_source, "core:asr", None),
        static_spec("model:asr:faster-whisper-large-v3-turbo:config", "Speech recognition configuration", "CTranslate2 model configuration", "models/asr/faster-whisper-large-v3-turbo/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/config.json", "models/asr/faster-whisper-large-v3-turbo/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/config.json", "https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo/resolve/e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da/config.json?download=true", 2_263, "b0253ea6c0d3bea6b1e19e91a02acfd3b53f4467362efcb5a3e6b16c9b3a9b7e", "MIT model conversion; OpenAI Whisper notices apply", asr_source, "core:asr", None),
        static_spec("model:asr:faster-whisper-large-v3-turbo:preprocessor", "Speech preprocessing configuration", "CTranslate2 model preprocessing", "models/asr/faster-whisper-large-v3-turbo/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/preprocessor_config.json", "models/asr/faster-whisper-large-v3-turbo/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/preprocessor_config.json", "https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo/resolve/e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da/preprocessor_config.json?download=true", 340, "7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711", "MIT model conversion; OpenAI Whisper notices apply", asr_source, "core:asr", None),
        static_spec("model:asr:faster-whisper-large-v3-turbo:tokenizer", "Speech tokenizer", "CTranslate2 speech tokenizer", "models/asr/faster-whisper-large-v3-turbo/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/tokenizer.json", "models/asr/faster-whisper-large-v3-turbo/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/tokenizer.json", "https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo/resolve/e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da/tokenizer.json?download=true", 2_710_337, "297b13372ac43916285644fb9687add3cc62ee2a1adb60da3dc25cc94c1871fd", "MIT model conversion; OpenAI Whisper notices apply", asr_source, "core:asr", None),
        static_spec("model:asr:faster-whisper-large-v3-turbo:vocabulary", "Speech vocabulary", "CTranslate2 speech vocabulary", "models/asr/faster-whisper-large-v3-turbo/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/vocabulary.json", "models/asr/faster-whisper-large-v3-turbo/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/vocabulary.json", "https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo/resolve/e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da/vocabulary.json?download=true", 1_068_114, "c69260f2ab26d659b7c398f9a2b2b48ed0df16c3b47d7326782fd9cba71690c1", "MIT model conversion; OpenAI Whisper notices apply", asr_source, "core:asr", None),
        static_spec_with_paths(
            "model:vad:silero-vad",
            "Silero voice activity detector",
            "Offline speech activity detection for WhisperX",
            "models/torch/hub/silero-vad-806dcba3f0b5d95282d0889a074954a2f8c6397b.zip",
            &[
                (
                    "models/torch/hub/silero-vad-806dcba3f0b5d95282d0889a074954a2f8c6397b.zip",
                    "f5af06ac1db1e294364a6c0218b56e0d6b14958b380252fe64f0c0e9bbca7a30",
                ),
                (
                    "models/torch/hub/snakers4_silero-vad_master/hubconf.py",
                    "",
                ),
                (
                    "models/torch/hub/snakers4_silero-vad_master/src/silero_vad/utils_vad.py",
                    "",
                ),
                (
                    "models/torch/hub/snakers4_silero-vad_master/src/silero_vad/data/silero_vad.jit",
                    "",
                ),
            ],
            "https://github.com/snakers4/silero-vad/archive/806dcba3f0b5d95282d0889a074954a2f8c6397b.zip",
            28_235_828,
            "f5af06ac1db1e294364a6c0218b56e0d6b14958b380252fe64f0c0e9bbca7a30",
            "MIT",
            "https://github.com/snakers4/silero-vad/tree/806dcba3f0b5d95282d0889a074954a2f8c6397b",
            "core:asr",
        ),
        static_spec("model:alignment:en:wav2vec2-base-960h", "English word-alignment model", "Word timestamps for captions and candidate boundaries", "models/torch/checkpoints/wav2vec2_fairseq_base_ls960_asr_ls960.pth", "models/torch/checkpoints/wav2vec2_fairseq_base_ls960_asr_ls960.pth", "https://download.pytorch.org/torchaudio/models/wav2vec2_fairseq_base_ls960_asr_ls960.pth", 377_664_473, "488fd4f16de84438ffc945334278c1b9fb9b7159a806c1080b16111a958c945d", "MIT; LibriSpeech-trained torchaudio/fairseq checkpoint", "https://docs.pytorch.org/audio/main/generated/torchaudio.pipelines.WAV2VEC2_ASR_BASE_960H.html", "core:asr", None),
        static_spec("data:nltk:punkt-tab", "Sentence splitting data", "WhisperX alignment sentence segmentation", "data/nltk/punkt_tab.zip", "data/nltk/punkt_tab.zip", "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/tokenizers/punkt_tab.zip", 4_319_076, "e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106", "NLTK data license; see upstream nltk_data notices", "https://github.com/nltk/nltk_data/tree/gh-pages/packages/tokenizers", "core:asr", None),
        static_spec("model:laughter:jrgillick/best.pth.tar", "Laughter detector", "Adds laughter and energy signals to moment discovery", "models/laughter-jrgillick/best.pth.tar", "models/laughter-jrgillick/best.pth.tar", "https://raw.githubusercontent.com/jrgillick/laughter-detection/5d5e0327916959d832d95ffbef5f484efc93d799/checkpoints/in_use/resnet_with_augmentation/best.pth.tar", 9_805_316, "bfe450e41926a4e9de2abf007c9a13fa8420439eaa1383e986563c565f5ef206", "Upstream repository license; verify before redistribution", "https://github.com/jrgillick/laughter-detection/tree/5d5e0327916959d832d95ffbef5f484efc93d799", "core:analysis", None),
        static_spec("model:panns-cnn14-decisionlevelmax:Cnn14_DecisionLevelMax.pth", "PANNs audio event model", "Understands useful audio events beyond speech", "models/panns-cnn14-decisionlevelmax/Cnn14_DecisionLevelMax.pth", "models/panns-cnn14-decisionlevelmax/Cnn14_DecisionLevelMax.pth", "https://zenodo.org/records/3987831/files/Cnn14_DecisionLevelMax_mAP%3D0.385.pth?download=1", 327_428_481, "dd3b4043a87d4ec13df8082c0fcfee3fb5084151808e47e060987a95eabdd142", "Zenodo record license; verify before redistribution", "https://zenodo.org/records/3987831", "core:analysis", None),
        static_spec("model:campplus:campplus_cn_common.bin", "CampPlus speaker model", "Identifies who is speaking for safe reframing", "models/campplus/campplus_cn_common.bin", "models/campplus/campplus_cn_common.bin", "https://huggingface.co/funasr/campplus/resolve/e4b6ede7ce16997aff4ae69fbca1f0175e2afede/campplus_cn_common.bin", 28_036_335, "3388cf5fd3493c9ac9c69851d8e7a8badcfb4f3dc631020c4961371646d5ada8", "Hugging Face repository license; verify before redistribution", "https://huggingface.co/funasr/campplus/tree/e4b6ede7ce16997aff4ae69fbca1f0175e2afede", "core:analysis", None),
        static_spec("model:ultraface:ultraface-rfb-320.onnx", "UltraFace detector", "Finds faces for safe vertical reframing", "models/ultraface/ultraface-rfb-320.onnx", "models/ultraface/ultraface-rfb-320.onnx", "https://raw.githubusercontent.com/JeremySNR/clip-forge/7a935022a2396eb5b24f67b588945133dcb511fc/resources/models/ultraface-rfb-320.onnx", 1_270_727, "34cd7e60aeff28744c657de7a3dc64e872d506741de66987f3426f2b79f88017", "Upstream repository license; verify before redistribution", "https://github.com/JeremySNR/clip-forge/tree/7a935022a2396eb5b24f67b588945133dcb511fc", "core:analysis", None),
        static_spec("model:lr-asd:frontend.onnx", "LR-ASD frontend", "Estimates active-speaker motion for camera direction", "models/lr-asd/frontend.onnx", "models/lr-asd/frontend.onnx", "https://raw.githubusercontent.com/JeremySNR/clip-forge/7a935022a2396eb5b24f67b588945133dcb511fc/resources/models/lr-asd-frontend.onnx", 2_529_511, "f7c055612cd6f1f2da3ab8257567ab68a6b0d69b5e436699a5cf65334dd79461", "Upstream repository license; verify before redistribution", "https://github.com/JeremySNR/clip-forge/tree/7a935022a2396eb5b24f67b588945133dcb511fc", "core:analysis", None),
        static_spec("model:lr-asd:backend.onnx", "LR-ASD backend", "Estimates active-speaker motion for camera direction", "models/lr-asd/backend.onnx", "models/lr-asd/backend.onnx", "https://raw.githubusercontent.com/JeremySNR/clip-forge/7a935022a2396eb5b24f67b588945133dcb511fc/resources/models/lr-asd-backend.onnx", 834_401, "9453caa09998027995664fd5a3b1fab4ad0de30a92c6beba8c29c3619de510a9", "Upstream repository license; verify before redistribution", "https://github.com/JeremySNR/clip-forge/tree/7a935022a2396eb5b24f67b588945133dcb511fc", "core:analysis", None),
    ]
}

fn runtime_variant_keys(manifest: &Value) -> Vec<String> {
    let base = platform_key();
    let prefix = format!("{base}-");
    let Some(assets) = manifest
        .get("runtimes")
        .and_then(|runtimes| runtimes.get("llama-server"))
        .and_then(|runtime| runtime.get("assets"))
        .and_then(Value::as_object)
    else {
        return Vec::new();
    };
    let mut keys = assets
        .keys()
        .filter(|key| *key == base || key.starts_with(&prefix))
        .cloned()
        .collect::<Vec<_>>();
    keys.sort_by_key(|key| if key == base { 0 } else { 1 });
    keys
}

fn runtime_variant_spec(manifest: &Value, key: &str) -> Option<AssetSpec> {
    let record = manifest_asset(manifest, "llama-server", key)?;
    let runtime = manifest.get("runtimes")?.get("llama-server")?;
    let version = text(runtime.get("version"), "managed");
    let binary = text(record.get("binary"), "llama-server");
    let install_root = if key == platform_key() {
        format!("runtimes/llama-server/{version}")
    } else {
        format!("runtimes/llama-server/{version}/{key}")
    };
    let archive_type = text(record.get("archive_type"), "zip");
    let archive_path = format!(
        "downloads/llama-server-{version}-{key}.{}",
        archive_type.replace('.', "-")
    );
    let installed_path = format!("{install_root}/{binary}");
    Some(AssetSpec {
        asset_id: format!("runtime:llama-server:{key}"),
        display_name: format!("ClipGauge Local · llama.cpp {version} · {key}"),
        purpose: "Owned loopback local inference runtime".to_string(),
        destination: archive_path.clone(),
        installed_paths: vec![archive_path.clone(), installed_path],
        installed_hashes: vec![(archive_path, text(record.get("sha256"), ""))],
        url: text(record.get("url"), ""),
        size_bytes: number(record.get("size")),
        sha256: text(record.get("sha256"), ""),
        required: false,
        one_time: true,
        license: text(runtime.get("license"), "See upstream source"),
        source: text(runtime.get("provenance"), ""),
        consent_group: "core".to_string(),
        installed_size_bytes: None,
    })
}

fn load_download_state(home: &Path) -> HashMap<String, Value> {
    let path = home.join("downloads.json");
    let Ok(contents) = fs::read_to_string(path) else {
        return HashMap::new();
    };
    let Ok(value) = serde_json::from_str::<Value>(&contents) else {
        return HashMap::new();
    };
    value
        .as_object()
        .map(|object| {
            object
                .iter()
                .map(|(key, value)| (key.clone(), value.clone()))
                .collect()
        })
        .unwrap_or_default()
}

fn selected_model(home: &Path, requested: Option<&str>) -> String {
    if let Some(value) = requested.filter(|value| valid_model_id(value)) {
        return value.to_string();
    }
    let path = home.join("local-ai-settings.json");
    if let Ok(contents) = fs::read_to_string(path) {
        if let Ok(value) = serde_json::from_str::<Value>(&contents) {
            if let Some(model) = value.get("selected_model_id").and_then(Value::as_str) {
                if valid_model_id(model) {
                    return model.to_string();
                }
            }
        }
    }
    "clipgauge-local/qwen3-4b-q4_k_m".to_string()
}

pub fn valid_model_id(model_id: &str) -> bool {
    matches!(
        model_id,
        "clipgauge-local/qwen3-1.7b-q8_0" | "clipgauge-local/qwen3-4b-q4_k_m"
    )
}

pub fn save_selected_model(home: &Path, model_id: &str) -> Result<(), String> {
    if !valid_model_id(model_id) {
        return Err("unsupported local model".to_string());
    }
    fs::create_dir_all(home).map_err(|error| error.to_string())?;
    let path = home.join("local-ai-settings.json");
    let temporary = home.join(".local-ai-settings.json.part");
    let payload = serde_json::to_vec_pretty(&json!({"selected_model_id": model_id}))
        .map_err(|error| error.to_string())?;
    fs::write(&temporary, payload).map_err(|error| error.to_string())?;
    fs::rename(&temporary, &path).map_err(|error| error.to_string())
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let mut file = fs::File::open(path).map_err(|error| error.to_string())?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = file.read(&mut buffer).map_err(|error| error.to_string())?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    let digest = digest.finalize();
    Ok(format!("{digest:x}"))
}

fn installed_details(home: &Path, spec: &AssetSpec) -> (bool, Option<String>) {
    let mut first_digest = None;
    for path in &spec.installed_paths {
        let full_path = home.join(path);
        if !full_path.is_file() {
            return (false, first_digest);
        }
        let Ok(digest) = sha256_file(&full_path) else {
            return (false, first_digest);
        };
        if first_digest.is_none() {
            first_digest = Some(digest.clone());
        }
        let expected = spec
            .installed_hashes
            .iter()
            .find(|(expected_path, _)| expected_path == path)
            .map(|(_, expected)| expected.as_str())
            .unwrap_or_default();
        if !expected.is_empty() && !digest.eq_ignore_ascii_case(expected) {
            return (false, first_digest);
        }
    }
    if spec.installed_paths.len() == 1 {
        let Ok(metadata) = fs::metadata(home.join(&spec.installed_paths[0])) else {
            return (false, first_digest);
        };
        let size_ready = spec
            .installed_size_bytes
            .map(|size| metadata.len() == size)
            .unwrap_or_else(|| spec.size_bytes == 0 || metadata.len() == spec.size_bytes);
        if !size_ready {
            return (false, first_digest);
        }
    }
    (true, first_digest)
}

fn asset_row(
    home: &Path,
    states: &HashMap<String, Value>,
    spec: &AssetSpec,
    cache: &mut HashMap<String, (bool, Option<String>)>,
) -> Value {
    let (is_installed, installed_sha256) = cache
        .entry(spec.asset_id.clone())
        .or_insert_with(|| installed_details(home, spec))
        .clone();
    let persisted_status = states
        .get(&spec.asset_id)
        .and_then(|state| state.get("status"))
        .and_then(Value::as_str)
        .unwrap_or("not-installed");
    let status = if is_installed {
        "ready"
    } else if installed_sha256.is_some() {
        "needs-repair"
    } else {
        persisted_status
    };
    let installed_size = if is_installed {
        spec.installed_size_bytes.or(Some(spec.size_bytes))
    } else {
        Some(0)
    };
    json!({
        "asset_id": spec.asset_id,
        "display_name": spec.display_name,
        "purpose": spec.purpose,
        "destination": spec.destination,
        "url": spec.url,
        "size_bytes": spec.size_bytes,
        "installed_size_bytes": installed_size,
        "sha256": spec.sha256,
        "installed_sha256": installed_sha256,
        "required": spec.required,
        "one_time": spec.one_time,
        "license": spec.license,
        "source": spec.source,
        "consent_group": spec.consent_group,
        "installed": is_installed,
        "cached": is_installed || matches!(status, "ready" | "reused" | "installed"),
        "status": status,
        "state": status.to_ascii_uppercase().replace('-', "_"),
        "managed_path": home.join(&spec.destination),
        "consent_granted": false,
    })
}

fn row_installed(row: &Value) -> bool {
    row.get("installed")
        .and_then(Value::as_bool)
        .unwrap_or(false)
}

fn row_is_ready(spec: &AssetSpec, row: &Value, video_ready: bool) -> bool {
    if spec.asset_id.starts_with("runtime:ffmpeg:") {
        video_ready
    } else {
        row_installed(row)
    }
}

fn is_core_required(spec: &AssetSpec) -> bool {
    spec.required
        && !spec.asset_id.starts_with("runtime:node:")
        && !spec.asset_id.starts_with("youtube:")
        && !spec.asset_id.starts_with("runtime:yt-dlp:")
        && !spec.asset_id.starts_with("runtime:cuda:")
        && !spec.asset_id.starts_with("runtime:cudnn:")
}

fn path_executable(name: &str) -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    for directory in std::env::split_paths(&path) {
        let candidate = directory.join(name);
        if candidate.is_file() {
            return Some(candidate);
        }
        #[cfg(target_os = "windows")]
        if !name.ends_with(".exe") {
            let candidate = directory.join(format!("{name}.exe"));
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }
    None
}

fn probe_executable(name: &str, args: &[&str]) -> bool {
    let Some(path) = path_executable(name) else {
        return false;
    };
    let mut command = Command::new(path);
    command.args(args);
    sidecar::run_bounded(command, RunPolicy::status())
        .map(|output| output.status.success())
        .unwrap_or(false)
}

fn native_runtime_selection(
    _home: &Path,
    manifest: &Value,
    specs: &[AssetSpec],
) -> (String, String) {
    let base = platform_key().to_string();
    if !cfg!(target_os = "windows") {
        return (base, "Platform default selected.".to_string());
    }
    let available = specs
        .iter()
        .filter_map(|spec| spec.asset_id.strip_prefix("runtime:llama-server:"))
        .collect::<Vec<_>>();
    let nvidia_verified =
        probe_executable("nvidia-smi", &["--query-gpu=name", "--format=csv,noheader"]);
    let vulkan_verified = probe_executable("vulkaninfo", &["--summary"]);
    // CUDA selection remains owned by the Python hardware probe. Native
    // inventory cannot import CTranslate2 safely without reintroducing the
    // startup dependency that this path deliberately avoids.
    if available.contains(&"windows-x86_64-vulkan")
        && (nvidia_verified || vulkan_verified)
        && manifest_asset(manifest, "llama-server", "windows-x86_64-vulkan").is_some()
    {
        return (
            "windows-x86_64-vulkan".to_string(),
            "Verified NVIDIA or Vulkan capability found.".to_string(),
        );
    }
    (
        base,
        "CPU fallback selected until GPU runtime evidence is complete.".to_string(),
    )
}

fn youtube_node_spec() -> Option<AssetSpec> {
    let (platform, archive, _archive_type, root, node, npm, url, size, sha256) =
        match platform_key() {
            "windows-x86_64" => (
                "windows-x86_64",
                "node-v24.19.0-win-x64.zip",
                "zip",
                "node-v24.19.0-win-x64",
                "node.exe",
                "npm.cmd",
                "https://nodejs.org/dist/v24.19.0/node-v24.19.0-win-x64.zip",
                37_304_352,
                "57f71ab3652e797d84acddc79c81cc9ff1c6ddb2a1974cdb83f00fee9bff4c73",
            ),
            "macos-x86_64" => (
                "macos-x86_64",
                "node-v24.19.0-darwin-x64.tar.gz",
                "tar.gz",
                "node-v24.19.0-darwin-x64",
                "bin/node",
                "bin/npm",
                "https://nodejs.org/dist/v24.19.0/node-v24.19.0-darwin-x64.tar.gz",
                53_439_583,
                "d1b5e999db158c62fe8f7267a4476b035d8bd93b1a605bac24a3f0dd166e3316",
            ),
            "macos-arm64" => (
                "macos-arm64",
                "node-v24.19.0-darwin-arm64.tar.gz",
                "tar.gz",
                "node-v24.19.0-darwin-arm64",
                "bin/node",
                "bin/npm",
                "https://nodejs.org/dist/v24.19.0/node-v24.19.0-darwin-arm64.tar.gz",
                52_234_372,
                "8294b7aa9b03997481c06babf1e8b270c859358f27da57a11509afe537ac381d",
            ),
            "linux-x86_64" => (
                "linux-x86_64",
                "node-v24.19.0-linux-x64.tar.xz",
                "tar.xz",
                "node-v24.19.0-linux-x64",
                "bin/node",
                "bin/npm",
                "https://nodejs.org/dist/v24.19.0/node-v24.19.0-linux-x64.tar.xz",
                31_633_904,
                "14b342e71204f811bde6153be8e04b62aef63c236fef92b55f9c83154b409647",
            ),
            "linux-arm64" => (
                "linux-arm64",
                "node-v24.19.0-linux-arm64.tar.xz",
                "tar.xz",
                "node-v24.19.0-linux-arm64",
                "bin/node",
                "bin/npm",
                "https://nodejs.org/dist/v24.19.0/node-v24.19.0-linux-arm64.tar.xz",
                30_553_480,
                "01443c1e1a29e531ccad5a46fefa6df490d2189c49f7955904aecdbb0fe86fdc",
            ),
            _ => return None,
        };
    let root_path = format!("runtimes/youtube/bgutil/1.3.2/node/{root}");
    Some(static_spec_with_paths(
        &format!("runtime:node:{platform}"),
        "YouTube support runtime",
        "Portable Node.js runtime for the managed PO-token provider",
        &format!("runtimes/youtube/bgutil/1.3.2/node/{archive}"),
        &[
            (
                &format!("runtimes/youtube/bgutil/1.3.2/node/{archive}"),
                sha256,
            ),
            (&format!("{root_path}/{node}"), ""),
            (&format!("{root_path}/{npm}"), ""),
        ],
        url,
        size,
        sha256,
        "Node.js/OpenJS Foundation; see upstream notices",
        "https://nodejs.org/en/download/archive/v24.19.0",
        "core:youtube",
    ))
}

fn youtube_provider_spec() -> AssetSpec {
    static_spec_with_paths(
        "youtube:bgutil-provider:1.3.2",
        "YouTube PO-token provider",
        "yt-dlp plugin and loopback PO-token server source",
        "runtimes/youtube/bgutil/1.3.2/bgutil-ytdlp-pot-provider-1.3.2.zip",
        &[
            (
                "runtimes/youtube/bgutil/1.3.2/bgutil-ytdlp-pot-provider-1.3.2.zip",
                "9055f9cbe9f47d242586a542c5b040a17d8e5ddbd1fbc72d3d80841b63dfed8b",
            ),
            (
                "runtimes/youtube/bgutil/1.3.2/plugin/yt_dlp_plugins/extractor/getpot_bgutil_http.py",
                "",
            ),
            (
                "runtimes/youtube/bgutil/1.3.2/source/bgutil-ytdlp-pot-provider-1.3.2/server/build/main.js",
                "",
            ),
        ],
        "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/1.3.2.zip",
        125_366,
        "9055f9cbe9f47d242586a542c5b040a17d8e5ddbd1fbc72d3d80841b63dfed8b",
        "GPL-3.0-only",
        "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/tree/1.3.2",
        "core:youtube",
    )
}

fn configured_ffmpeg(home: &Path, manifest: &Value) -> Option<(String, PathBuf)> {
    if let Some(path) = std::env::var_os("CLIPGAUGE_FFMPEG") {
        return Some(("configured".to_string(), PathBuf::from(path)));
    }
    if let Some(record) = manifest_asset(manifest, "ffmpeg", "win64-gpl") {
        let version = text(
            manifest.get("runtimes")?.get("ffmpeg")?.get("version"),
            "managed",
        );
        let path = home
            .join("runtimes")
            .join("ffmpeg")
            .join(version)
            .join("win64-gpl")
            .join("ffmpeg.exe");
        if path.is_file() {
            return Some(("managed".to_string(), path));
        }
        let _ = record;
    }
    std::env::var_os("CLIPGAUGE_BUNDLED_FFMPEG")
        .map(|path| ("bundled".to_string(), PathBuf::from(path)))
        .or_else(|| {
            path_executable(if cfg!(target_os = "windows") {
                "ffmpeg.exe"
            } else {
                "ffmpeg"
            })
            .map(|path| ("system".to_string(), path))
        })
}

fn probe_ffmpeg(path: &Path) -> (bool, Option<String>, HashMap<String, bool>, String) {
    let mut version_command = Command::new(path);
    version_command.args(["-hide_banner", "-version"]);
    let version_output = sidecar::run_bounded(version_command, RunPolicy::status());
    let (starts, version) = match version_output {
        Ok(output) => {
            let combined = format!("{}\n{}", output.stdout, output.stderr_tail);
            let first = combined
                .lines()
                .find(|line| !line.trim().is_empty())
                .map(str::to_string);
            (output.status.success(), first)
        }
        Err(_) => (false, None),
    };
    let mut filters_command = Command::new(path);
    filters_command.args(["-hide_banner", "-filters"]);
    let filters = sidecar::run_bounded(filters_command, RunPolicy::status())
        .map(|output| format!("{}\n{}", output.stdout, output.stderr_tail))
        .unwrap_or_default();
    let subtitles = filters
        .lines()
        .any(|line| line.split_whitespace().any(|token| token == "subtitles"));
    let mut capabilities = HashMap::new();
    capabilities.insert("starts".to_string(), starts);
    capabilities.insert("subtitles".to_string(), subtitles);
    let reason = if starts && subtitles {
        "Compatible caption-capable FFmpeg."
    } else if !starts {
        "FFmpeg did not start successfully."
    } else {
        "FFmpeg is missing the subtitles filter required for caption rendering."
    };
    (
        starts && subtitles,
        version,
        capabilities,
        reason.to_string(),
    )
}

#[cfg(target_os = "windows")]
fn available_bytes(path: &Path) -> Option<u64> {
    use std::os::windows::ffi::OsStrExt;
    let query = path
        .ancestors()
        .find(|candidate| candidate.is_dir())
        .unwrap_or_else(|| Path::new("C:\\"));
    let mut wide: Vec<u16> = query.as_os_str().encode_wide().collect();
    wide.push(0);
    let mut free = 0_u64;
    let result = unsafe {
        GetDiskFreeSpaceExW(
            wide.as_ptr(),
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            &mut free,
        )
    };
    (result != 0).then_some(free)
}

#[cfg(unix)]
fn available_bytes(path: &Path) -> Option<u64> {
    let query = path
        .ancestors()
        .find(|candidate| candidate.is_dir())
        .unwrap_or(path);
    let path = std::ffi::CString::new(query.to_string_lossy().as_bytes()).ok()?;
    let mut stats = std::mem::MaybeUninit::<libc::statvfs>::uninit();
    let result = unsafe { libc::statvfs(path.as_ptr(), stats.as_mut_ptr()) };
    if result == 0 {
        let stats = unsafe { stats.assume_init() };
        let bytes = u128::from(stats.f_bavail) * u128::from(stats.f_frsize);
        return u64::try_from(bytes).ok();
    }
    None
}

#[cfg(not(any(target_os = "windows", unix)))]
fn available_bytes(_path: &Path) -> Option<u64> {
    None
}

#[cfg(target_os = "windows")]
#[link(name = "kernel32")]
extern "system" {
    fn GetDiskFreeSpaceExW(
        directory_name: *const u16,
        free_bytes_available: *mut u64,
        total_bytes: *mut u64,
        total_free_bytes: *mut u64,
    ) -> i32;
}

pub fn native_inventory(
    resources: &Path,
    home: &Path,
    requested_model: Option<&str>,
) -> Result<Value, String> {
    let manifest = manifest(resources)?;
    let states = load_download_state(home);
    let mut specs = static_core_specs();
    let yt_version = text(
        manifest
            .get("runtimes")
            .and_then(|runtimes| runtimes.get("yt-dlp"))
            .and_then(|runtime| runtime.get("version")),
        "managed",
    );
    let yt_dlp_path = format!("runtimes/yt-dlp/{yt_version}/{}", yt_dlp_key());
    if let Some(spec) = manifest_asset_spec(
        &manifest,
        "yt-dlp",
        yt_dlp_key(),
        &format!("runtime:yt-dlp:{}", yt_dlp_key()),
        "YouTube downloader",
        "Retrieves public video metadata and media",
        &yt_dlp_path,
        &yt_dlp_path,
        "core:youtube",
        true,
    ) {
        specs.push(spec);
    }
    if cfg!(target_os = "windows") {
        if let Some(record) = manifest_asset(&manifest, "ffmpeg", "win64-gpl") {
            let version = text(
                manifest
                    .get("runtimes")
                    .and_then(|r| r.get("ffmpeg"))
                    .and_then(|r| r.get("version")),
                "managed",
            );
            let key = "win64-gpl";
            specs.push(AssetSpec {
                asset_id: "runtime:ffmpeg:win64-gpl".to_string(),
                display_name: "FFmpeg · Video engine".to_string(),
                purpose: "Decode, probe, caption, and render video clips".to_string(),
                destination: format!("runtimes/ffmpeg/{version}/{key}/ffmpeg.zip"),
                installed_paths: vec![
                    format!("runtimes/ffmpeg/{version}/{key}/ffmpeg.zip"),
                    format!("runtimes/ffmpeg/{version}/{key}/ffmpeg.exe"),
                ],
                installed_hashes: vec![
                    (
                        format!("runtimes/ffmpeg/{version}/{key}/ffmpeg.zip"),
                        text(record.get("sha256"), ""),
                    ),
                    (
                        format!("runtimes/ffmpeg/{version}/{key}/ffmpeg.exe"),
                        String::new(),
                    ),
                ],
                url: text(record.get("url"), ""),
                size_bytes: number(record.get("size")),
                sha256: text(record.get("sha256"), ""),
                required: true,
                one_time: true,
                license: text(
                    manifest
                        .get("runtimes")
                        .and_then(|r| r.get("ffmpeg"))
                        .and_then(|r| r.get("license")),
                    "See upstream source",
                ),
                source: text(
                    manifest
                        .get("runtimes")
                        .and_then(|r| r.get("ffmpeg"))
                        .and_then(|r| r.get("provenance")),
                    "",
                ),
                consent_group: "core".to_string(),
                installed_size_bytes: None,
            });
        }
    }
    let runtime_specs = runtime_variant_keys(&manifest)
        .iter()
        .filter_map(|key| runtime_variant_spec(&manifest, key))
        .collect::<Vec<_>>();
    let base_runtime_spec = runtime_specs
        .iter()
        .find(|spec| spec.asset_id == format!("runtime:llama-server:{}", platform_key()))
        .cloned()
        .ok_or_else(|| "ClipGauge Local is unavailable for this platform.".to_string())?;
    specs.extend(runtime_specs.iter().cloned());
    let local_models = [
        model_spec(
            &manifest,
            "clipgauge-local/qwen3-1.7b-q8_0",
            "clipgauge-local/qwen3-1.7b-q8_0.gguf",
            "Qwen3-1.7B-Q8_0.gguf",
        ),
        model_spec(
            &manifest,
            "clipgauge-local/qwen3-4b-q4_k_m",
            "clipgauge-local/qwen3-4b-q4_k_m.gguf",
            "Qwen3-4B-Q4_K_M.gguf",
        ),
    ]
    .into_iter()
    .flatten()
    .collect::<Vec<_>>();
    specs.extend(local_models.iter().cloned());
    if cfg!(target_os = "windows") {
        specs.push(static_spec_with_paths(
            "runtime:cuda:windows-x86_64:12.4",
            "CUDA 12.4 speech runtime",
            "CTranslate2 CUDA speech execution",
            "downloads/cudart-llama-bin-win-cuda-12.4-x64.zip",
            &[
                (
                    "downloads/cudart-llama-bin-win-cuda-12.4-x64.zip",
                    "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6",
                ),
                (
                    "runtimes/cuda/12.4/cublas64_12.dll",
                    "e40202fe4223c1cd2d2dce7beec59e1ed61c7801bd827309183be9b50e358f4c",
                ),
                (
                    "runtimes/cuda/12.4/cublasLt64_12.dll",
                    "2a896460bef60ed57ef32b0875812f355a6984e671d638bb632f5e8c1d7a831f",
                ),
                (
                    "runtimes/cuda/12.4/cudart64_12.dll",
                    "d28e42265da7462162a54da6b7a99ea4fa2caf8139d862bb500db875d0b32dfc",
                ),
            ],
            "https://github.com/ggml-org/llama.cpp/releases/download/b10545/cudart-llama-bin-win-cuda-12.4-x64.zip",
            391_443_627,
            "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6",
            "CUDA runtime redistribution; see NVIDIA and llama.cpp notices",
            "https://github.com/ggml-org/llama.cpp/releases/tag/b10545",
            "core:asr",
        ));
        specs.push(static_spec_with_paths(
            "runtime:cudnn:windows-x86_64:9.11.0.98-cuda12",
            "NVIDIA cuDNN 9 speech runtime",
            "CTranslate2 CUDA speech execution",
            "downloads/cudnn-windows-x86_64-9.11.0.98_cuda12-archive.zip",
            &[
                (
                    "downloads/cudnn-windows-x86_64-9.11.0.98_cuda12-archive.zip",
                    "947988b49209d0d22c81809f20f8e7a703e9347d519317e1468e11fd70bb195a",
                ),
                (
                    "runtimes/cuda/12.4/cudnn64_9.dll",
                    "98461c2e24270b75c6d4767ff469c244d7f7c91cb3d9c9ac76d497510d7d9c5f",
                ),
                (
                    "runtimes/cuda/12.4/cudnn_adv64_9.dll",
                    "950b04f148fbcfacaf2fb98eee36a422e2a8faf94aedfcbcbac15d7ece938a84",
                ),
                (
                    "runtimes/cuda/12.4/cudnn_cnn64_9.dll",
                    "da0a92803013d96bf71f872e914e2dbba543e54537d97de555aa53376d07b580",
                ),
                (
                    "runtimes/cuda/12.4/cudnn_engines_precompiled64_9.dll",
                    "f1b2e8aa17931391ae9c7d7cc974c419b85440229b3145c8cc6662b4e5af29be",
                ),
                (
                    "runtimes/cuda/12.4/cudnn_engines_runtime_compiled64_9.dll",
                    "f826723e3ebaa2487389636f30a8d374b81357ead8c76b220b4121f107d4e332",
                ),
                (
                    "runtimes/cuda/12.4/cudnn_graph64_9.dll",
                    "41f57d2b475bbe5bd10095c9529bbd58711c71cca984bf13bfe813ee89d9b949",
                ),
                (
                    "runtimes/cuda/12.4/cudnn_heuristic64_9.dll",
                    "7b9d9ceaa915093128b2d4d021c5dffac3fbc52539262c44dc2953d028bf2419",
                ),
                (
                    "runtimes/cuda/12.4/cudnn_ops64_9.dll",
                    "f6b491ab3bc30406326423041f19f69b2c5e6de21f6afb9f1350d3d9c3d7af99",
                ),
            ],
            "https://developer.download.nvidia.com/compute/cudnn/redist/cudnn/windows-x86_64/cudnn-windows-x86_64-9.11.0.98_cuda12-archive.zip",
            550_483_500,
            "947988b49209d0d22c81809f20f8e7a703e9347d519317e1468e11fd70bb195a",
            "NVIDIA cuDNN redistribution; see NVIDIA cuDNN license terms",
            "https://developer.download.nvidia.com/compute/cudnn/redist/redistrib_9.11.0.json",
            "core:asr",
        ));
    }
    if let Some(spec) = youtube_node_spec() {
        specs.push(spec);
    }
    specs.push(youtube_provider_spec());

    let (video_ready, video_source, video_path, video_version, video_capabilities, video_reason) = configured_ffmpeg(home, &manifest)
        .map(|(source, path)| {
            let (ready, version, capabilities, reason) = probe_ffmpeg(&path);
            (ready, source, Some(path), version, capabilities, reason)
        })
        .unwrap_or_else(|| (false, "missing".to_string(), None, None, HashMap::new(), "No FFmpeg executable was found in the configured, managed, bundled, or system locations.".to_string()));
    let mut installed_cache = HashMap::new();
    let mut rows = specs
        .iter()
        .map(|spec| asset_row(home, &states, spec, &mut installed_cache))
        .collect::<Vec<_>>();
    if !video_ready {
        for row in &mut rows {
            if row
                .get("asset_id")
                .and_then(Value::as_str)
                .map(|id| id.starts_with("runtime:ffmpeg:"))
                .unwrap_or(false)
                && row_installed(row)
            {
                row["installed"] = Value::Bool(false);
                row["cached"] = Value::Bool(false);
                row["status"] = Value::String("needs-repair".to_string());
                row["state"] = Value::String("NEEDS_REPAIR".to_string());
                row["reason"] = Value::String(video_reason.clone());
            }
        }
    }
    let (selected_runtime_key, runtime_selection_reason) =
        native_runtime_selection(home, &manifest, &runtime_specs);
    let runtime_spec = runtime_specs
        .iter()
        .find(|spec| spec.asset_id == format!("runtime:llama-server:{selected_runtime_key}"))
        .unwrap_or(&base_runtime_spec);
    let runtime_rows = rows
        .iter()
        .filter(|row| {
            row.get("asset_id")
                .and_then(Value::as_str)
                .map(|id| id.starts_with("runtime:llama-server:"))
                .unwrap_or(false)
        })
        .cloned()
        .collect::<Vec<_>>();
    let selected_id = selected_model(home, requested_model);
    let selected = local_models
        .iter()
        .find(|model| model.asset_id == selected_id)
        .or_else(|| local_models.first());
    let selected_id = selected
        .map(|model| model.asset_id.clone())
        .unwrap_or(selected_id);
    let runtime_ready = installed_cache
        .get(&runtime_spec.asset_id)
        .map(|(ready, _)| *ready)
        .unwrap_or(false);
    let model_ready = selected
        .map(|model| {
            installed_cache
                .get(&model.asset_id)
                .map(|(ready, _)| *ready)
                .unwrap_or(false)
        })
        .unwrap_or(false);
    let local_state = if runtime_ready && model_ready {
        "ready"
    } else if runtime_ready {
        "model-download-required"
    } else {
        "runtime-install-required"
    };
    let managed_ffmpeg_needed =
        !video_ready && manifest_asset(&manifest, "ffmpeg", "win64-gpl").is_some();
    let mut required_bytes = 0_u64;
    let mut optional_bytes = 0_u64;
    let mut installed_bytes = 0_u64;
    for (spec, row) in specs.iter().zip(rows.iter()) {
        let ready = row_is_ready(spec, row, video_ready);
        if ready {
            installed_bytes += spec.installed_size_bytes.unwrap_or(spec.size_bytes);
        } else if is_core_required(spec) {
            required_bytes += spec.size_bytes;
        } else {
            optional_bytes += spec.size_bytes;
        }
    }
    let required_ready = specs
        .iter()
        .zip(rows.iter())
        .filter(|(spec, _)| is_core_required(spec))
        .all(|(spec, row)| row_is_ready(spec, row, video_ready));
    let core_assets = rows
        .iter()
        .filter(|row| {
            row.get("asset_id")
                .and_then(Value::as_str)
                .map(|id| {
                    id == "runtime:ffmpeg:win64-gpl"
                        || id.starts_with("runtime:yt-dlp:")
                        || id.starts_with("model:")
                })
                .unwrap_or(false)
        })
        .cloned()
        .collect::<Vec<_>>();
    let model_ids = local_models
        .iter()
        .map(|model| model.asset_id.as_str())
        .collect::<Vec<_>>();
    let model_rows = rows
        .iter()
        .filter(|row| {
            row.get("asset_id")
                .and_then(Value::as_str)
                .map(|id| model_ids.contains(&id))
                .unwrap_or(false)
        })
        .collect::<Vec<_>>();
    let runtime_row = rows
        .iter()
        .find(|row| row.get("asset_id") == Some(&json!(runtime_spec.asset_id)))
        .cloned()
        .unwrap_or_else(|| json!({}));
    Ok(json!({
        "state": if required_ready { "ready" } else { "setup-required" },
        "runtime": runtime_row,
        "runtime_variants": runtime_rows,
        "runtime_selection": {
            "key": selected_runtime_key,
            "backend": manifest_asset(&manifest, "llama-server", &selected_runtime_key)
                .map(|record| text(record.get("backend"), "cpu"))
                .unwrap_or_else(|| "cpu".to_string()),
            "reason": runtime_selection_reason,
        },
        "models": model_rows,
        "core_assets": core_assets,
        "video_tools": {
            "ready": video_ready,
            "source": video_source,
            "executable": video_path,
            "version": video_version,
            "capabilities": video_capabilities,
            "managed_download_needed": managed_ffmpeg_needed,
            "reason": video_reason,
        },
        "local_ai": {
            "state": local_state,
            "runtime_ready": runtime_ready,
            "model_ready": model_ready,
            "selected_model_id": selected_id,
            "required_bytes": (if runtime_ready { 0 } else { runtime_spec.size_bytes }) + (if model_ready { 0 } else { selected.map(|model| model.size_bytes).unwrap_or_default() }),
            "action": if runtime_ready && model_ready { "Ready" } else if runtime_ready { "Download selected model" } else { "Install ClipGauge Local" },
        },
        "managed_assets": rows,
        "storage": {
            "required_bytes": required_bytes,
            "optional_bytes": optional_bytes,
            "download_bytes": required_bytes + optional_bytes,
            "installed_bytes": installed_bytes,
            "available_bytes": available_bytes(home),
            "assets": [],
            "consent_required": required_bytes > 0,
            "location": home,
        },
        "catalog": local_models.iter().map(|model| json!({
            "model_id": model.asset_id,
            "display_name": model.display_name,
            "license": model.license,
            "context_window": if model.asset_id.contains("1.7b") { 32_768 } else { 131_072 },
            "capabilities": ["text", "structured_json"],
            "provenance": model.source,
        })).collect::<Vec<_>>(),
    }))
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::fs;
    use std::path::PathBuf;
    use std::time::{SystemTime, UNIX_EPOCH};

    use super::native_inventory;
    use super::save_selected_model;

    fn temporary_home() -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock must be available")
            .as_nanos();
        let path = std::env::temp_dir().join(format!("clipgauge-inventory-{suffix}"));
        fs::create_dir_all(&path).expect("temporary inventory home must be creatable");
        path
    }

    #[test]
    fn fresh_inventory_is_manifest_backed_and_download_free() {
        let home = temporary_home();
        let resources = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../pipeline");
        let inventory = native_inventory(&resources, &home, None).expect("inventory must load");

        assert_eq!(inventory["state"], "setup-required");
        assert!(inventory["storage"]["required_bytes"].as_u64().unwrap() > 0);
        assert!(inventory["managed_assets"].as_array().unwrap().len() >= 10);
        assert!(!home.join("downloads.json").exists());
        assert!(!home.join("local-ai-settings.json").exists());

        fs::remove_dir_all(home).expect("temporary inventory home must be removable");
    }

    #[test]
    fn available_storage_uses_an_existing_parent_for_new_homes() {
        let home = std::env::temp_dir().join("clipgauge-inventory-home-not-created");
        assert!(super::available_bytes(&home).is_some());
    }

    #[test]
    fn selected_model_is_explicitly_preserved() {
        let home = temporary_home();
        let resources = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../pipeline");
        let inventory =
            native_inventory(&resources, &home, Some("clipgauge-local/qwen3-1.7b-q8_0"))
                .expect("inventory must load");

        assert_eq!(
            inventory["local_ai"]["selected_model_id"],
            "clipgauge-local/qwen3-1.7b-q8_0"
        );
        assert_eq!(inventory["models"].as_array().unwrap().len(), 2);

        fs::remove_dir_all(home).expect("temporary inventory home must be removable");
    }

    #[test]
    fn selected_model_persistence_is_allowlisted_and_atomic() {
        let home = temporary_home();
        save_selected_model(&home, "clipgauge-local/qwen3-1.7b-q8_0")
            .expect("supported model selection must save");
        let contents = fs::read_to_string(home.join("local-ai-settings.json"))
            .expect("saved model selection must be readable");
        assert!(contents.contains("clipgauge-local/qwen3-1.7b-q8_0"));
        assert!(save_selected_model(&home, "clipgauge-local/unknown").is_err());
        assert!(!home.join(".local-ai-settings.json.part").exists());
        fs::remove_dir_all(home).expect("temporary inventory home must be removable");
    }

    #[test]
    fn same_size_tampering_requires_repair() {
        let home = temporary_home();
        let path = home.join("asset.bin");
        fs::write(&path, b"tampered").expect("test asset must be writable");
        let spec = super::static_spec(
            "test:asset",
            "Test asset",
            "Integrity test",
            "downloads/asset.bin",
            "asset.bin",
            "https://example.com/asset.bin",
            8,
            "0000000000000000000000000000000000000000000000000000000000000000",
            "Test",
            "https://example.com",
            "test",
            None,
        );
        let mut cache = HashMap::new();
        let row = super::asset_row(&home, &HashMap::new(), &spec, &mut cache);

        assert_eq!(row["status"], "needs-repair");
        assert_eq!(row["installed"], false);
        assert!(row["installed_sha256"].as_str().is_some());
        fs::remove_dir_all(home).expect("temporary inventory home must be removable");
    }

    #[test]
    fn ffmpeg_asset_requires_a_successful_capability_probe() {
        let spec = super::static_spec(
            "runtime:ffmpeg:test",
            "Test FFmpeg",
            "Capability test",
            "downloads/ffmpeg.zip",
            "ffmpeg.exe",
            "https://example.com/ffmpeg.zip",
            1,
            "",
            "Test",
            "https://example.com",
            "core",
            None,
        );
        let row = serde_json::json!({"installed": true});
        assert!(!super::row_is_ready(&spec, &row, false));
        assert!(super::row_is_ready(&spec, &row, true));
    }

    #[test]
    fn optional_setup_assets_do_not_inflate_core_storage() {
        let spec = super::static_spec(
            "runtime:node:test",
            "Test Node",
            "Optional test runtime",
            "downloads/node.zip",
            "node.exe",
            "https://example.com/node.zip",
            1,
            "",
            "Test",
            "https://example.com",
            "core:youtube",
            None,
        );
        assert!(!super::is_core_required(&spec));
    }

    #[test]
    fn native_inventory_exposes_runtime_variants() {
        let home = temporary_home();
        let resources = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../pipeline");
        let inventory = native_inventory(&resources, &home, None).expect("inventory must load");
        let ids = inventory["runtime_variants"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|row| row["asset_id"].as_str())
            .collect::<Vec<_>>();

        assert!(ids.iter().any(|id| id.ends_with("windows-x86_64")
            || id.ends_with("macos-arm64")
            || id.ends_with("linux-x86_64")));
        #[cfg(target_os = "windows")]
        {
            assert!(ids.iter().any(|id| id.ends_with("windows-x86_64-vulkan")));
            assert!(ids.iter().any(|id| id.ends_with("windows-x86_64-cuda")));
            let node = super::youtube_node_spec().expect("Windows Node spec must exist");
            assert!(node
                .installed_paths
                .iter()
                .any(|path| path.ends_with("node-v24.19.0-win-x64/node.exe")));
            assert!(node
                .installed_paths
                .iter()
                .any(|path| path.ends_with("node-v24.19.0-win-x64/npm.cmd")));
        }
        fs::remove_dir_all(home).expect("temporary inventory home must be removable");
    }
}
