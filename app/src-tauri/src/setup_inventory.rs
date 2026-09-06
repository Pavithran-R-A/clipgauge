use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use serde_json::{json, Value};

use crate::sidecar::{self, RunPolicy};

#[derive(Clone)]
struct AssetSpec {
    asset_id: String,
    display_name: String,
    purpose: String,
    destination: String,
    installed_paths: Vec<String>,
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
    if cfg!(target_os = "windows") {
        "windows-x86_64"
    } else if cfg!(target_os = "macos") {
        "macos-arm64"
    } else {
        "linux-x86_64"
    }
}

fn yt_dlp_key() -> &'static str {
    if cfg!(target_os = "windows") {
        "yt-dlp.exe"
    } else if cfg!(target_os = "macos") {
        "yt-dlp_macos"
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
        destination: format!("downloads/{filename}"),
        installed_paths: vec![format!("models/clipgauge-local/{filename}")],
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
    installed_paths: &[&str],
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
            .map(|path| (*path).to_string())
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
        static_spec("model:vad:silero-vad", "Silero voice activity detector", "Offline speech activity detection for WhisperX", "models/torch/hub/silero-vad-806dcba3f0b5d95282d0889a074954a2f8c6397b.zip", "models/torch/hub/snakers4_silero-vad_master/src/silero_vad/data/silero_vad.jit", "https://github.com/snakers4/silero-vad/archive/806dcba3f0b5d95282d0889a074954a2f8c6397b.zip", 28_235_828, "f5af06ac1db1e294364a6c0218b56e0d6b14958b380252fe64f0c0e9bbca7a30", "MIT", "https://github.com/snakers4/silero-vad/tree/806dcba3f0b5d95282d0889a074954a2f8c6397b", "core:asr", Some(70_724_504)),
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

fn installed(home: &Path, spec: &AssetSpec) -> bool {
    if !spec
        .installed_paths
        .iter()
        .all(|path| home.join(path).is_file())
    {
        return false;
    }
    if spec.installed_paths.len() > 1 {
        return true;
    }
    let Ok(metadata) = fs::metadata(home.join(&spec.installed_paths[0])) else {
        return false;
    };
    if let Some(size) = spec.installed_size_bytes {
        return metadata.len() == size;
    }
    spec.size_bytes == 0 || metadata.len() == spec.size_bytes
}

fn asset_row(home: &Path, states: &HashMap<String, Value>, spec: &AssetSpec) -> Value {
    let is_installed = installed(home, spec);
    let persisted_status = states
        .get(&spec.asset_id)
        .and_then(|state| state.get("status"))
        .and_then(Value::as_str)
        .unwrap_or("not-installed");
    let status = if is_installed {
        "ready"
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
    let root = path
        .components()
        .next()
        .map(|component| PathBuf::from(component.as_os_str()))
        .unwrap_or_else(|| PathBuf::from("C:\\"));
    let mut wide: Vec<u16> = root.as_os_str().encode_wide().collect();
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
    let path = std::ffi::CString::new(path.to_string_lossy().as_bytes()).ok()?;
    let mut stats = std::mem::MaybeUninit::<libc::statvfs>::uninit();
    let result = unsafe { libc::statvfs(path.as_ptr(), stats.as_mut_ptr()) };
    if result == 0 {
        let stats = unsafe { stats.assume_init() };
        return Some(stats.f_bavail as u64 * stats.f_frsize as u64);
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
    if let Some(spec) = manifest_asset_spec(
        &manifest,
        "yt-dlp",
        yt_dlp_key(),
        "runtime:yt-dlp:yt-dlp.exe",
        "YouTube downloader",
        "Retrieves public video metadata and media",
        &format!("downloads/yt-dlp-{yt_version}.bin"),
        &format!("bin/{}", yt_dlp_key()),
        "core:youtube",
        true,
    ) {
        specs.push(spec);
    }
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
            installed_paths: vec![format!("runtimes/ffmpeg/{version}/{key}/ffmpeg.exe")],
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
    let runtime_manifest = manifest_asset(&manifest, "llama-server", platform_key())
        .ok_or_else(|| "ClipGauge Local is unavailable for this platform.".to_string())?;
    let runtime_version = text(
        manifest
            .get("runtimes")
            .and_then(|r| r.get("llama-server"))
            .and_then(|r| r.get("version")),
        "managed",
    );
    let runtime_key = platform_key();
    let runtime_binary = text(runtime_manifest.get("binary"), "llama-server");
    let runtime_base = format!("runtimes/llama-server/{runtime_version}");
    let runtime_install = if runtime_key == platform_key() {
        runtime_base.clone()
    } else {
        format!("{runtime_base}/{runtime_key}")
    };
    let runtime_spec = AssetSpec {
        asset_id: format!("runtime:llama-server:{runtime_key}"),
        display_name: format!("ClipGauge Local · llama.cpp {runtime_version}"),
        purpose: "Owned loopback local inference runtime".to_string(),
        destination: format!("downloads/llama-server-{runtime_version}-{runtime_key}.zip"),
        installed_paths: vec![format!("{runtime_install}/{runtime_binary}")],
        url: text(runtime_manifest.get("url"), ""),
        size_bytes: number(runtime_manifest.get("size")),
        sha256: text(runtime_manifest.get("sha256"), ""),
        required: false,
        one_time: true,
        license: text(
            manifest
                .get("runtimes")
                .and_then(|r| r.get("llama-server"))
                .and_then(|r| r.get("license")),
            "See upstream source",
        ),
        source: text(
            manifest
                .get("runtimes")
                .and_then(|r| r.get("llama-server"))
                .and_then(|r| r.get("provenance")),
            "",
        ),
        consent_group: "core".to_string(),
        installed_size_bytes: None,
    };
    specs.push(runtime_spec.clone());
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
                "downloads/cudart-llama-bin-win-cuda-12.4-x64.zip",
                "runtimes/cuda/12.4/cublas64_12.dll",
                "runtimes/cuda/12.4/cublasLt64_12.dll",
                "runtimes/cuda/12.4/cudart64_12.dll",
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
                "downloads/cudnn-windows-x86_64-9.11.0.98_cuda12-archive.zip",
                "runtimes/cuda/12.4/cudnn64_9.dll",
                "runtimes/cuda/12.4/cudnn_adv64_9.dll",
                "runtimes/cuda/12.4/cudnn_cnn64_9.dll",
                "runtimes/cuda/12.4/cudnn_engines_precompiled64_9.dll",
                "runtimes/cuda/12.4/cudnn_engines_runtime_compiled64_9.dll",
                "runtimes/cuda/12.4/cudnn_graph64_9.dll",
                "runtimes/cuda/12.4/cudnn_heuristic64_9.dll",
                "runtimes/cuda/12.4/cudnn_ops64_9.dll",
            ],
            "https://developer.download.nvidia.com/compute/cudnn/redist/cudnn/windows-x86_64/cudnn-windows-x86_64-9.11.0.98_cuda12-archive.zip",
            550_483_500,
            "947988b49209d0d22c81809f20f8e7a703e9347d519317e1468e11fd70bb195a",
            "NVIDIA cuDNN redistribution; see NVIDIA cuDNN license terms",
            "https://developer.download.nvidia.com/compute/cudnn/redist/redistrib_9.11.0.json",
            "core:asr",
        ));
    }
    specs.push(static_spec(
        "runtime:node:windows-x86_64",
        "YouTube support runtime",
        "Portable Node.js runtime for the managed PO-token provider",
        "runtimes/youtube/bgutil/1.3.2/node/node-v24.19.0-win-x64.zip",
        "runtimes/youtube/bgutil/1.3.2/node/node.exe",
        "https://nodejs.org/dist/v24.19.0/node-v24.19.0-win-x64.zip",
        0,
        "",
        "Node.js/OpenJS Foundation; see upstream notices",
        "https://nodejs.org/en/download/archive/v24.19.0",
        "core:youtube",
        None,
    ));
    specs.push(static_spec(
        "youtube:bgutil-provider:1.3.2",
        "YouTube PO-token provider",
        "yt-dlp plugin and loopback PO-token server source",
        "runtimes/youtube/bgutil/1.3.2/bgutil-ytdlp-pot-provider-1.3.2.zip",
        "runtimes/youtube/bgutil/1.3.2/plugin",
        "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/1.3.2.zip",
        125_366,
        "9055f9cbe9f47d242586a542c5b040a17d8e5ddbd1fbc72d3d80841b63dfed8b",
        "GPL-3.0-only",
        "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/tree/1.3.2",
        "core:youtube",
        None,
    ));

    let rows = specs
        .iter()
        .map(|spec| asset_row(home, &states, spec))
        .collect::<Vec<_>>();
    let selected_id = selected_model(home, requested_model);
    let selected = local_models
        .iter()
        .find(|model| model.asset_id == selected_id)
        .or_else(|| local_models.first());
    let selected_id = selected
        .map(|model| model.asset_id.clone())
        .unwrap_or(selected_id);
    let runtime_ready = installed(home, &runtime_spec);
    let model_ready = selected
        .map(|model| installed(home, model))
        .unwrap_or(false);
    let local_state = if runtime_ready && model_ready {
        "ready"
    } else if runtime_ready {
        "model-download-required"
    } else {
        "runtime-install-required"
    };
    let (video_ready, video_source, video_path, video_version, video_capabilities, video_reason) = configured_ffmpeg(home, &manifest)
        .map(|(source, path)| {
            let (ready, version, capabilities, reason) = probe_ffmpeg(&path);
            (ready, source, Some(path), version, capabilities, reason)
        })
        .unwrap_or_else(|| (false, "missing".to_string(), None, None, HashMap::new(), "No FFmpeg executable was found in the configured, managed, bundled, or system locations.".to_string()));
    let managed_ffmpeg_needed =
        !video_ready && manifest_asset(&manifest, "ffmpeg", "win64-gpl").is_some();
    let mut required_bytes = 0_u64;
    let mut optional_bytes = 0_u64;
    let mut installed_bytes = 0_u64;
    for spec in &specs {
        let ready =
            installed(home, spec) || (spec.asset_id.starts_with("runtime:ffmpeg:") && video_ready);
        if ready {
            installed_bytes += spec.installed_size_bytes.unwrap_or(spec.size_bytes);
        } else if spec.required && !(spec.asset_id.starts_with("runtime:ffmpeg:") && video_ready) {
            required_bytes += spec.size_bytes;
        } else {
            optional_bytes += spec.size_bytes;
        }
    }
    let required_ready = specs
        .iter()
        .filter(|spec| {
            spec.required
                && !spec.asset_id.starts_with("runtime:node:")
                && !spec.asset_id.starts_with("youtube:")
                && !spec.asset_id.starts_with("runtime:yt-dlp:")
                && !spec.asset_id.starts_with("runtime:cuda:")
                && !spec.asset_id.starts_with("runtime:cudnn:")
        })
        .all(|spec| {
            installed(home, spec) || (spec.asset_id.starts_with("runtime:ffmpeg:") && video_ready)
        });
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
    let model_rows = local_models
        .iter()
        .map(|model| asset_row(home, &states, model))
        .collect::<Vec<_>>();
    Ok(json!({
        "state": if required_ready { "ready" } else { "setup-required" },
        "runtime": asset_row(home, &states, &runtime_spec),
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
}
