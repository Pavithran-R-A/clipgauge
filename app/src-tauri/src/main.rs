// ClipGauge desktop shell. The pipeline is a Python sidecar speaking JSONL
// on stdout (`clipgauge --jsonl ...`); this shell spawns it, forwards every
// event to the frontend, and exposes small filesystem/settings commands.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod artifact;
mod diagnostics;
mod edit_schema;
mod media_server;
mod path_security;
mod process_manager;
mod secrets;
mod setup_inventory;
mod sidecar;

use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{
    atomic::{AtomicU64, Ordering},
    Arc, Mutex,
};
use std::thread;
use std::time::{Duration, Instant};

use serde::Deserialize;
use serde_json::{json, Value};
use tauri::{AppHandle, Emitter, Manager, State};

#[derive(Clone)]
struct AppState {
    processes: Arc<Mutex<process_manager::ProcessManager>>,
    initialization: Arc<sidecar::InitializationCoordinator>,
    media: Arc<media_server::MediaServer>,
}

impl AppState {
    fn new(media: Arc<media_server::MediaServer>) -> Self {
        Self {
            processes: Arc::new(Mutex::new(process_manager::ProcessManager::new())),
            initialization: Arc::new(sidecar::InitializationCoordinator::new()),
            media,
        }
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RunJobRequest {
    source: String,
    #[serde(default)]
    llm: Option<String>,
    #[serde(default)]
    provider: Option<String>,
    #[serde(default)]
    model: Option<String>,
    #[serde(default)]
    endpoint: Option<String>,
    #[serde(default)]
    auth: Option<String>,
    #[serde(default)]
    secret_header: Option<String>,
    #[serde(default)]
    captions: Option<String>,
    #[serde(default)]
    quality_mode: Option<String>,
    #[serde(default)]
    output_preference: Option<String>,
    #[serde(default)]
    cookies_from_browser: Option<String>,
    #[serde(default)]
    allow_cpu_asr_fallback: bool,
}

fn validate_browser_session(value: Option<&str>) -> Result<Option<String>, String> {
    match value {
        None => Ok(None),
        Some(browser) if matches!(browser, "chrome" | "edge" | "chromium" | "firefox") => {
            Ok(Some(browser.to_string()))
        }
        Some(_) => Err(
            "Unsupported browser session. Choose Chrome, Edge, Chromium, or Firefox.".to_string(),
        ),
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ResumeJobRequest {
    job_id: String,
    #[serde(default)]
    llm: Option<String>,
    #[serde(default)]
    provider: Option<String>,
    #[serde(default)]
    model: Option<String>,
    #[serde(default)]
    endpoint: Option<String>,
    #[serde(default)]
    auth: Option<String>,
    #[serde(default)]
    secret_header: Option<String>,
    #[serde(default)]
    captions: Option<String>,
    #[serde(default)]
    camera: Option<String>,
    #[serde(default)]
    quality_mode: Option<String>,
    #[serde(default)]
    output_preference: Option<String>,
    #[serde(default)]
    allow_cpu_asr_fallback: bool,
}

fn application_home_from_env(
    qa_home: Option<std::ffi::OsString>,
    profile_home: PathBuf,
) -> PathBuf {
    #[cfg(feature = "qualification-vault")]
    if let Some(value) = qa_home {
        let candidate = PathBuf::from(value);
        if candidate.is_absolute() {
            return candidate;
        }
    }

    #[cfg(not(feature = "qualification-vault"))]
    let _ = qa_home;

    profile_home.join(".clipgauge")
}

fn home_dir() -> PathBuf {
    // Production always owns one stable profile root.
    // Qualification builds may use an isolated test root.
    application_home_from_env(std::env::var_os("CLIPGAUGE_QA_HOME"), dirs_home())
}

fn profile_home_from_env(
    home: Option<std::ffi::OsString>,
    userprofile: Option<std::ffi::OsString>,
) -> PathBuf {
    #[cfg(target_os = "windows")]
    let value = userprofile.or(home);
    #[cfg(not(target_os = "windows"))]
    let value = home.or(userprofile);

    value
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/"))
}

fn copy_legacy_tree(source: &Path, destination: &Path) -> Result<(), String> {
    let metadata = fs::symlink_metadata(source).map_err(|error| error.to_string())?;
    if metadata.file_type().is_symlink() {
        return Err(format!(
            "legacy migration refuses symlink: {}",
            source.display()
        ));
    }
    if metadata.is_dir() {
        fs::create_dir_all(destination).map_err(|error| error.to_string())?;
        for entry in fs::read_dir(source).map_err(|error| error.to_string())? {
            let entry = entry.map_err(|error| error.to_string())?;
            copy_legacy_tree(&entry.path(), &destination.join(entry.file_name()))?;
        }
        return Ok(());
    }
    if !metadata.is_file() {
        return Err(format!(
            "legacy migration refuses non-file: {}",
            source.display()
        ));
    }
    if destination.exists() {
        let existing = fs::read(destination).map_err(|error| error.to_string())?;
        let incoming = fs::read(source).map_err(|error| error.to_string())?;
        if existing != incoming {
            return Err(format!(
                "legacy migration collision at {}",
                destination.display()
            ));
        }
        return Ok(());
    }
    if let Some(parent) = destination.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::copy(source, destination).map_err(|error| error.to_string())?;
    Ok(())
}

fn migrate_legacy_data_from(legacy: &Path, destination: &Path) -> Result<(), String> {
    let marker = destination.join("migrations/legacy-publikclip-v1.done");
    if marker.exists() {
        return Ok(());
    }
    if legacy == destination || !legacy.exists() {
        fs::create_dir_all(marker.parent().unwrap()).map_err(|error| error.to_string())?;
        fs::write(marker, b"no legacy root found").map_err(|error| error.to_string())?;
        return Ok(());
    }
    copy_legacy_tree(legacy, destination)?;
    fs::create_dir_all(marker.parent().unwrap()).map_err(|error| error.to_string())?;
    fs::write(marker, b"legacy root copied; source preserved").map_err(|error| error.to_string())
}

fn migrate_legacy_data() -> Result<(), String> {
    let destination = home_dir();
    let legacy = std::env::var_os("PUBLIKCLIP_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| dirs_home().join(".publikclip"));
    migrate_legacy_data_from(&legacy, &destination)
}

fn dirs_home() -> PathBuf {
    // Windows profile identity must ignore shell-specific HOME overrides.
    profile_home_from_env(std::env::var_os("HOME"), std::env::var_os("USERPROFILE"))
}

fn onboarded_marker_exists(home: &Path) -> bool {
    home.join("onboarded").exists()
}

fn mark_onboarded_at(home: &Path) -> Result<(), String> {
    fs::create_dir_all(home).map_err(|e| e.to_string())?;
    fs::write(home.join("onboarded"), "1").map_err(|e| e.to_string())
}

fn validate_job_id(job_id: &str) -> Result<PathBuf, String> {
    path_security::resolve_job_dir(&home_dir(), job_id)
}

/// Command that never flashes a console window on Windows (CREATE_NO_WINDOW).
/// Every pipeline/tool spawn goes through this — a GUI app popping cmd.exe
/// windows for each sidecar call reads as malware to most people.
fn quiet_command(program: &str) -> Command {
    #[allow(unused_mut)]
    let mut cmd = Command::new(program);
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    if !cfg!(debug_assertions) {
        // Packaged resources are read-only. Keep uv's project environment in
        // the user-owned runtime area so edit, run, and setup commands work
        // after installation on every desktop platform.
        cmd.env(
            "UV_PROJECT_ENVIRONMENT",
            home_dir().join("runtimes").join("pipeline"),
        );
    }
    cmd
}

#[tauri::command]
fn vault_scope() -> &'static str {
    secrets::namespace_kind()
}

async fn spawn_blocking_result<T, F>(work: F) -> Result<T, String>
where
    T: Send + 'static,
    F: FnOnce() -> Result<T, String> + Send + 'static,
{
    tauri::async_runtime::spawn_blocking(work)
        .await
        .map_err(|error| diagnostics::redact(&format!("background task failed: {error}")))?
}

/// Where the Python pipeline lives and how to invoke it.
/// Dev builds call `uv run` against the repo's pipeline/ directory. Packaged
/// builds invoke the bundled python env (M6); resolution stays in one place.
fn packaged_resource_dir(exe_path: &std::path::Path, platform: &str, uv_name: &str) -> PathBuf {
    let exe_dir = exe_path
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from("."));
    let candidates = if platform == "macos" {
        vec![exe_dir.join("../Resources/resources")]
    } else if platform == "linux" {
        // AppImage and portable bundles keep resources beside the executable;
        // Debian installs the launcher in /usr/bin and resources in
        // /usr/lib/ClipGauge/resources.
        vec![
            exe_dir.join("resources"),
            exe_dir.join("../lib/ClipGauge/resources"),
        ]
    } else {
        vec![exe_dir.join("resources")]
    };
    candidates
        .into_iter()
        .find(|candidate| {
            candidate.join("pipeline").is_dir() && candidate.join("bin").join(uv_name).is_file()
        })
        .map(|candidate| candidate.canonicalize().unwrap_or(candidate))
        .unwrap_or_else(|| exe_dir.join("resources"))
}

fn pipeline_invocation() -> (String, Vec<String>) {
    pipeline_invocation_for(sidecar::PipelineMode::ManagedOperation)
}

fn pipeline_resources_dir() -> PathBuf {
    if cfg!(debug_assertions) {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../pipeline")
            .canonicalize()
            .unwrap_or_else(|_| PathBuf::from("../pipeline"))
    } else {
        let exe_path = std::env::current_exe().unwrap_or_else(|_| PathBuf::from("."));
        let uv_name = if cfg!(target_os = "windows") {
            "uv.exe"
        } else {
            "uv"
        };
        packaged_resource_dir(&exe_path, std::env::consts::OS, uv_name)
    }
}

fn pipeline_environment_dir() -> PathBuf {
    if cfg!(debug_assertions) {
        pipeline_resources_dir().join(".venv")
    } else {
        home_dir().join("runtimes").join("pipeline")
    }
}

fn pipeline_environment_ready() -> bool {
    let python = if cfg!(target_os = "windows") {
        pipeline_environment_dir()
            .join("Scripts")
            .join("python.exe")
    } else {
        pipeline_environment_dir().join("bin").join("python")
    };
    python.is_file() && home_dir().join("runtime-environment.json").is_file()
}

fn pipeline_invocation_for(mode: sidecar::PipelineMode) -> (String, Vec<String>) {
    if cfg!(debug_assertions) {
        let pipeline_dir = pipeline_resources_dir();
        (
            "uv".to_string(),
            sidecar::pipeline_args(&pipeline_dir, mode),
        )
    } else {
        // Packaged: bundled uv + pipeline source under the platform's
        // resource layout — macOS keeps them in the .app's Resources dir,
        // Windows (NSIS) lands them in resources\ next to the exe. The venv
        // bootstraps into CLIPGAUGE_HOME on first run (uv handles Python
        // 3.12 download + deps; the onboarding screen owns expectations).
        let resources = pipeline_resources_dir();
        let uv = if cfg!(target_os = "windows") {
            "bin/uv.exe"
        } else {
            "bin/uv"
        };
        (
            resources.join(uv).to_string_lossy().to_string(),
            sidecar::pipeline_args(&resources.join("pipeline"), mode),
        )
    }
}

fn initialize_pipeline() -> Result<(), String> {
    initialize_pipeline_with_registration(|_| {})
}

fn initialize_pipeline_with_registration<F>(on_spawn: F) -> Result<(), String>
where
    F: FnOnce(u32),
{
    let (program, args) = pipeline_invocation_for(sidecar::PipelineMode::Initialize);
    let mut command = quiet_command(&program);
    secrets::apply_operation_env(&mut command);
    command.env("CLIPGAUGE_HOME", home_dir()).args(args);
    let output =
        sidecar::run_bounded_with_callback(command, sidecar::RunPolicy::initialization(), on_spawn)
            .map_err(|error| format!("pipeline initialization failed: {error:?}"))?;
    if !output.status.success() {
        Err(format!(
            "pipeline initialization exited unsuccessfully: {}",
            diagnostics::redact(&output.stderr_tail)
        ))
    } else {
        let (program, mut args) = pipeline_invocation_for(sidecar::PipelineMode::ManagedOperation);
        args.push("environment-initialize".to_string());
        let mut identity_command = quiet_command(&program);
        secrets::apply_operation_env(&mut identity_command);
        identity_command
            .env("CLIPGAUGE_HOME", home_dir())
            .args(args);
        let identity = sidecar::run_bounded(identity_command, sidecar::RunPolicy::status())
            .map_err(|error| format!("pipeline identity recording failed: {error:?}"))?;
        if identity.status.success() {
            Ok(())
        } else {
            Err(format!(
                "pipeline identity recording failed: {}",
                diagnostics::redact(&identity.stderr_tail)
            ))
        }
    }
}

#[tauri::command]
fn privacy_summary(
    llm: Option<String>,
    provider: Option<String>,
    model: Option<String>,
    endpoint: Option<String>,
) -> Result<Value, String> {
    let selected = provider.or(llm).unwrap_or_else(|| "gemini".to_string());
    let llm_data = if selected == "ollama" {
        json!({
            "mode": selected.clone(),
            "device": ["transcript text", "local audio/video", "local score inputs"],
            "network": ["source URL download when a URL is provided", "pinned runtime/model downloads when absent", "optional Pexels visual queries"],
            "provider": "Ollama is contacted only on loopback; no transcript is sent to a cloud LLM by this mode"
        })
    } else if selected == "gemini" {
        json!({
            "mode": selected.clone(),
            "device": ["source media remains in the managed local job directory"],
            "network": ["source URL download when a URL is provided", "pinned runtime/model downloads when absent", "Gemini receives transcript slices, scoring context, and sampled finalist frames", "optional Pexels visual queries"],
            "provider": "Gemini is contacted with an operation-scoped vault credential; the API key is not included in requests as a query parameter"
        })
    } else if selected == "clipgauge-local" {
        json!({
            "mode": selected.clone(),
            "device": ["source media, transcript, sampled frames, and score inputs remain on this computer"],
            "network": ["source URL download when a URL is provided", "pinned runtime/model downloads when setup requires them", "optional Pexels visual queries"],
            "provider": "ClipGauge Local scores on this computer; no transcript or source-derived frames are sent to a cloud AI provider"
        })
    } else {
        json!({
            "mode": selected,
            "device": ["source media remains in the managed local job directory"],
            "network": ["source URL download when a URL is provided", "provider endpoint receives transcript slices and scoring context", "selected frames leave the device only when the selected model advertises vision"],
            "provider": "This selected provider is contacted outside ClipGauge; review its current privacy and retention terms before sending source-derived material",
            "model": model,
            "endpoint": endpoint.map(|value| value.split('/').take(3).collect::<Vec<_>>().join("/"))
        })
    };
    Ok(json!({
        "local_first": true,
        "telemetry": "disabled by default",
        "llm": llm_data,
        "instagram": "Meta requests occur only when the optional Instagram connection and sync features are used",
        "source": "ClipGauge runtime behavior"
    }))
}

fn sanitized_job_metadata(root: &Path) -> Value {
    let mut jobs = Vec::new();
    if let Ok(entries) = fs::read_dir(root.join("jobs")) {
        for entry in entries.flatten() {
            let id = entry.file_name().to_string_lossy().to_string();
            if !path_security::valid_job_id(&id) {
                continue;
            }
            let Ok(dir) = path_security::resolve_job_dir(root, &id) else {
                continue;
            };
            let mut stages = Vec::new();
            for stage in [
                "ingest",
                "asr",
                "diarize",
                "events",
                "candidates",
                "score",
                "camera",
                "render",
            ] {
                let path = dir.join(format!("{stage}.json"));
                if let Ok(metadata) = fs::metadata(path) {
                    stages.push(json!({"stage": stage, "bytes": metadata.len()}));
                }
            }
            jobs.push(json!({"id": id, "stages": stages}));
            if jobs.len() >= 50 {
                break;
            }
        }
    }
    json!({"jobs": jobs})
}

fn valid_diagnostic_id(id: &str) -> bool {
    let Some(suffix) = id.strip_prefix("diag-") else {
        return false;
    };
    matches!(suffix.len(), 16 | 32) && suffix.chars().all(|value| value.is_ascii_hexdigit())
}

fn diagnostic_tail(path: &Path) -> Result<String, String> {
    let text = fs::read_to_string(path).map_err(|error| error.to_string())?;
    let redacted = diagnostics::redact(&text);
    let safe_lines = redacted
        .lines()
        .filter(|line| {
            let lower = line.to_ascii_lowercase();
            !lower.contains("transcript") && !line.contains("S0:") && !line.contains("S1:")
        })
        .collect::<Vec<_>>()
        .join("\n");
    Ok(safe_lines
        .chars()
        .rev()
        .take(64 * 1024)
        .collect::<String>()
        .chars()
        .rev()
        .collect())
}

fn append_diagnostic_file(
    archive: &mut zip::ZipWriter<fs::File>,
    options: zip::write::SimpleFileOptions,
    path: &Path,
    archive_name: String,
    included: &mut Vec<String>,
) -> Result<bool, String> {
    if path.extension().and_then(|value| value.to_str()) != Some("log") {
        return Ok(false);
    }
    let Some(file_name) = path.file_name().and_then(|value| value.to_str()) else {
        return Ok(false);
    };
    let Some(diagnostic_id) = file_name.strip_suffix(".log") else {
        return Ok(false);
    };
    if !valid_diagnostic_id(diagnostic_id) {
        return Ok(false);
    }
    let tail = diagnostic_tail(path)?;
    archive
        .start_file(archive_name, options)
        .map_err(|error| error.to_string())?;
    archive
        .write_all(tail.as_bytes())
        .map_err(|error| error.to_string())?;
    included.push(diagnostic_id.to_string());
    Ok(true)
}

fn generate_support_bundle_at(
    root: &Path,
    job_id: Option<String>,
    diagnostic_id: Option<String>,
) -> Result<String, String> {
    if let Some(id) = &job_id {
        let _ = path_security::resolve_job_dir(root, id)?;
    }
    if let Some(id) = &diagnostic_id {
        if !valid_diagnostic_id(id) {
            return Err("invalid diagnostic identifier".into());
        }
    }
    let directory = root.join("support");
    fs::create_dir_all(&directory).map_err(|error| error.to_string())?;
    let bundle_id = diagnostics::diagnostic_id();
    let path = directory.join(format!("support-{bundle_id}.zip"));
    let temp = path.with_extension("zip.tmp");
    let file = fs::File::create(&temp).map_err(|error| error.to_string())?;
    let mut archive = zip::ZipWriter::new(file);
    let options = zip::write::SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);
    let mut included_diagnostics = Vec::new();
    let root_diagnostics = root.join("diagnostics");
    if let Ok(entries) = fs::read_dir(&root_diagnostics) {
        let entries = entries.flatten().filter(|entry| {
            let Some(requested) = &diagnostic_id else {
                return true;
            };
            entry.file_name().to_string_lossy() == format!("{requested}.log")
        });
        for entry in entries.take(8) {
            let path = entry.path();
            let Some(file_name) = path.file_name().and_then(|value| value.to_str()) else {
                continue;
            };
            let _ = append_diagnostic_file(
                &mut archive,
                options,
                &path,
                format!("diagnostics/{file_name}"),
                &mut included_diagnostics,
            )?;
        }
    }
    if let Some(id) = &job_id {
        let job_dir = path_security::resolve_job_dir(root, id)?;
        let job_diagnostics = job_dir.join("diagnostics");
        if let Ok(entries) = fs::read_dir(&job_diagnostics) {
            for entry in entries.flatten() {
                let path = entry.path();
                let Some(file_name) = path.file_name().and_then(|value| value.to_str()) else {
                    continue;
                };
                if let Some(requested) = &diagnostic_id {
                    if file_name != format!("{requested}.log") {
                        continue;
                    }
                }
                let _ = append_diagnostic_file(
                    &mut archive,
                    options,
                    &path,
                    format!("jobs/{id}/diagnostics/{file_name}"),
                    &mut included_diagnostics,
                )?;
            }
        }
    }
    let requested_missing = diagnostic_id.as_ref().filter(|requested| {
        !included_diagnostics
            .iter()
            .any(|included| included == *requested)
    });
    let report = json!({
        "app_version": env!("CARGO_PKG_VERSION"),
        "os": std::env::consts::OS,
        "architecture": std::env::consts::ARCH,
        "protocol_version": 2,
        "support_bundle_version": 2,
        "bundle_id": bundle_id,
        "job_id": job_id,
        "requested_diagnostic_id": diagnostic_id,
        "included_diagnostic_ids": included_diagnostics,
        "missing_diagnostic": requested_missing,
        "jobs": sanitized_job_metadata(root),
        "exclusions": ["API keys", "OAuth tokens", "browser cookies", "raw transcripts", "source media", "unrelated job diagnostics", "arbitrary filesystem contents"],
    });
    archive
        .start_file("report.json", options)
        .map_err(|error| error.to_string())?;
    archive
        .write_all(
            serde_json::to_string_pretty(&report)
                .map_err(|error| error.to_string())?
                .as_bytes(),
        )
        .map_err(|error| error.to_string())?;
    archive
        .start_file("README.txt", options)
        .map_err(|error| error.to_string())?;
    archive
        .write_all(b"ClipGauge support bundle. This archive contains sanitized metadata and redacted bounded diagnostic tails only. It excludes credentials, browser cookies, transcripts, media, and unrelated job diagnostics.\n")
        .map_err(|error| error.to_string())?;
    archive.finish().map_err(|error| error.to_string())?;
    fs::rename(&temp, &path).map_err(|error| error.to_string())?;
    Ok(path.to_string_lossy().to_string())
}

#[tauri::command]
async fn generate_support_bundle(
    job_id: Option<String>,
    diagnostic_id: Option<String>,
) -> Result<String, String> {
    spawn_blocking_result(move || generate_support_bundle_at(&home_dir(), job_id, diagnostic_id))
        .await
}

fn append_provider_args(
    args: &mut Vec<String>,
    llm: Option<String>,
    provider: Option<String>,
    model: Option<String>,
    endpoint: Option<String>,
    auth: Option<String>,
    secret_header: Option<String>,
) {
    let explicit_provider = provider.is_some();
    if let Some(kind) = provider.or(llm) {
        args.push(
            if explicit_provider {
                "--provider"
            } else {
                "--llm"
            }
            .to_string(),
        );
        args.push(kind);
    }
    if let Some(value) = model {
        args.push("--model".to_string());
        args.push(value);
    }
    if let Some(value) = endpoint {
        args.push("--endpoint".to_string());
        args.push(value);
    }
    if let Some(value) = auth {
        args.push("--auth".to_string());
        args.push(value);
    }
    if let Some(value) = secret_header {
        args.push("--secret-header".to_string());
        args.push(value);
    }
}

fn append_quality_mode_arg(args: &mut Vec<String>, quality_mode: Option<String>) {
    if let Some(mode) = quality_mode {
        args.push("--quality-mode".to_string());
        args.push(mode);
    }
}

fn append_output_preference_arg(args: &mut Vec<String>, output_preference: Option<String>) {
    if let Some(preference) = output_preference {
        args.push("--output-preference".to_string());
        args.push(preference);
    }
}

// Tauri exposes these named fields individually to the frontend.
#[allow(clippy::too_many_arguments)]
#[tauri::command]
async fn preflight(
    llm: Option<String>,
    provider: Option<String>,
    model: Option<String>,
    endpoint: Option<String>,
    auth: Option<String>,
    secret_header: Option<String>,
    source: Option<String>,
    quality_mode: Option<String>,
) -> Result<Value, String> {
    spawn_blocking_result(move || {
        let selected_provider = provider.clone();
        let (program, mut args) = pipeline_invocation();
        args.push("preflight".to_string());
        append_provider_args(
            &mut args,
            llm,
            provider,
            model,
            endpoint,
            auth,
            secret_header,
        );
        if let Some(value) = source {
            args.push("--source".to_string());
            args.push(value);
        }
        append_quality_mode_arg(&mut args, quality_mode);
        let mut command = quiet_command(&program);
        secrets::apply_operation_env(&mut command);
        if let Some((env_name, profile_id)) = selected_provider_env(selected_provider.as_deref()) {
            secrets::apply_provider_operation_env(&mut command, &profile_id, env_name);
        }
        command.env("CLIPGAUGE_HOME", home_dir()).args(&args);
        run_json_sidecar(command, "preflight")
    })
    .await
}

#[tauri::command]
async fn test_connection(
    llm: Option<String>,
    provider: Option<String>,
    model: Option<String>,
    endpoint: Option<String>,
    auth: Option<String>,
    secret_header: Option<String>,
) -> Result<Value, String> {
    spawn_blocking_result(move || {
        let selected_provider = provider.clone();
        let (program, mut args) = pipeline_invocation();
        args.push("provider-test".to_string());
        append_provider_args(
            &mut args,
            llm,
            provider,
            model,
            endpoint,
            auth,
            secret_header,
        );
        let mut command = quiet_command(&program);
        secrets::apply_operation_env(&mut command);
        if let Some((env_name, profile_id)) = selected_provider_env(selected_provider.as_deref()) {
            secrets::apply_provider_operation_env(&mut command, &profile_id, env_name);
        }
        command.env("CLIPGAUGE_HOME", home_dir()).args(&args);
        run_json_sidecar(command, "provider test")
    })
    .await
}

#[tauri::command]
async fn provider_models(
    llm: Option<String>,
    provider: Option<String>,
    model: Option<String>,
    endpoint: Option<String>,
    auth: Option<String>,
    secret_header: Option<String>,
) -> Result<Value, String> {
    spawn_blocking_result(move || {
        let selected_provider = provider.clone();
        let (program, mut args) = pipeline_invocation();
        args.push("provider-models".to_string());
        append_provider_args(
            &mut args,
            llm,
            provider,
            model,
            endpoint,
            auth,
            secret_header,
        );
        let mut command = quiet_command(&program);
        secrets::apply_operation_env(&mut command);
        if let Some((env_name, profile_id)) = selected_provider_env(selected_provider.as_deref()) {
            secrets::apply_provider_operation_env(&mut command, &profile_id, env_name);
        }
        command.env("CLIPGAUGE_HOME", home_dir()).args(&args);
        run_json_sidecar(command, "provider models")
    })
    .await
}

#[tauri::command]
fn run_job(
    app: AppHandle,
    state: State<'_, AppState>,
    request: RunJobRequest,
) -> Result<(), String> {
    let RunJobRequest {
        source,
        llm,
        provider,
        model,
        endpoint,
        auth,
        secret_header,
        captions,
        quality_mode,
        output_preference,
        cookies_from_browser,
        allow_cpu_asr_fallback,
    } = request;
    let cookies_from_browser = validate_browser_session(cookies_from_browser.as_deref())?;
    let (program, base_args) = pipeline_invocation();
    let processes = state.processes.clone();
    let initialization = state.initialization.clone();
    let key = format!("run:{}", diagnostics::diagnostic_id());
    reserve_process(&processes, key.clone())?;
    std::thread::spawn(move || {
        let init_processes = processes.clone();
        let init_key = key.clone();
        if let Err(error) = initialization.ensure_initialized(|| {
            initialize_pipeline_with_registration(|process_id| {
                if let Ok(mut lifecycle) = init_processes.lock() {
                    let _ = lifecycle.adopt_job_id(&init_key, init_key.clone());
                    let _ = lifecycle.register_process(&init_key, process_id);
                    if lifecycle.is_cancel_requested(&init_key) {
                        let _ = process_manager::terminate_owned(process_id);
                    }
                }
            })
        }) {
            if let Ok(mut lifecycle) = processes.lock() {
                let _ = lifecycle.finish(&key, false);
            }
            write_lifecycle_snapshot(&processes, &key);
            emit_terminal(
                &app,
                json!({
                    "event": "terminal",
                    "protocol_version": 2,
                    "ok": false,
                    "stage": "pipeline",
                    "code": "PIPELINE_INITIALIZATION_FAILED",
                    "message": diagnostics::redact(&error),
                    "retryable": true,
                    "diagnostic_id": diagnostics::diagnostic_id(),
                }),
            );
            return;
        }
        let mut args = base_args.clone();
        args.push("--jsonl".to_string());
        args.push("run".to_string());
        args.push(source);
        let selected_provider = provider.clone();
        append_provider_args(
            &mut args,
            llm,
            provider,
            model,
            endpoint,
            auth,
            secret_header,
        );
        if let Some(preset) = captions {
            args.push("--captions".to_string());
            args.push(preset);
        }
        append_quality_mode_arg(&mut args, quality_mode);
        append_output_preference_arg(&mut args, output_preference);
        if let Some(browser) = cookies_from_browser {
            args.push("--cookies-from-browser".to_string());
            args.push(browser);
        }
        if allow_cpu_asr_fallback {
            args.push("--allow-cpu-asr-fallback".to_string());
        }
        stream_pipeline(
            &app,
            &program,
            &args,
            processes,
            key,
            selected_provider.as_deref(),
        );
    });
    Ok(())
}

#[tauri::command]
fn resume_job(
    app: AppHandle,
    state: State<'_, AppState>,
    request: ResumeJobRequest,
) -> Result<(), String> {
    let ResumeJobRequest {
        job_id,
        llm,
        provider,
        model,
        endpoint,
        auth,
        secret_header,
        captions,
        camera,
        quality_mode,
        output_preference,
        allow_cpu_asr_fallback,
    } = request;
    validate_job_id(&job_id)?;
    let (program, base_args) = pipeline_invocation();
    let processes = state.processes.clone();
    let key = format!("job:{job_id}");
    reserve_process(&processes, key.clone())?;
    std::thread::spawn(move || {
        let mut args = base_args.clone();
        args.push("--jsonl".to_string());
        args.push("resume".to_string());
        args.push(job_id);
        let selected_provider = provider.clone();
        append_provider_args(
            &mut args,
            llm,
            provider,
            model,
            endpoint,
            auth,
            secret_header,
        );
        if let Some(preset) = captions {
            args.push("--captions".to_string());
            args.push(preset);
        }
        if let Some(cam) = camera {
            args.push("--camera".to_string());
            args.push(cam);
        }
        append_quality_mode_arg(&mut args, quality_mode);
        append_output_preference_arg(&mut args, output_preference);
        if allow_cpu_asr_fallback {
            args.push("--allow-cpu-asr-fallback".to_string());
        }
        stream_pipeline(
            &app,
            &program,
            &args,
            processes,
            key,
            selected_provider.as_deref(),
        );
    });
    Ok(())
}

fn reserve_process(
    processes: &Arc<Mutex<process_manager::ProcessManager>>,
    key: String,
) -> Result<(), String> {
    processes
        .lock()
        .map_err(|_| "job lifecycle state is unavailable".to_string())?
        .reserve(key)
        .map(|_| ())
        .map_err(|error| match error {
            process_manager::ReserveError::AlreadyActive => {
                "This job is already running in ClipGauge. Wait for it to finish or cancel it before retrying.".to_string()
            }
            process_manager::ReserveError::Busy => {
                "Another heavy ClipGauge job is running. Wait for it to finish or cancel it before starting another.".to_string()
            }
        })
}

fn lifecycle_path(job_id: &str) -> Result<PathBuf, String> {
    Ok(validate_job_id(job_id)?.join("runtime.json"))
}

fn write_lifecycle_snapshot(processes: &Arc<Mutex<process_manager::ProcessManager>>, key: &str) {
    let lease = processes
        .lock()
        .ok()
        .and_then(|state| state.lease(key, env!("CARGO_PKG_VERSION"), 1));
    let Some(lease) = lease else { return };
    let Ok(path) = lifecycle_path(&lease.job_id) else {
        return;
    };
    if let Ok(payload) = serde_json::to_vec_pretty(&lease) {
        let _ = setup_inventory::atomic_write(&path, &payload);
    }
}

fn reconcile_stale_leases(processes: &mut process_manager::ProcessManager) {
    let jobs = home_dir().join("jobs");
    let Ok(entries) = fs::read_dir(jobs) else {
        return;
    };
    for entry in entries.flatten() {
        let id = entry.file_name().to_string_lossy().to_string();
        if !path_security::valid_job_id(&id) {
            continue;
        }
        let Ok(path) = lifecycle_path(&id) else {
            continue;
        };
        let Ok(text) = fs::read_to_string(&path) else {
            continue;
        };
        let Ok(lease) = serde_json::from_str::<process_manager::LeaseRecord>(&text) else {
            continue;
        };
        if lease.session_id != processes.session_id() && !lease.state.terminal() {
            let stale = process_manager::ProcessManager::mark_interrupted(&lease);
            if let Ok(payload) = serde_json::to_vec_pretty(&stale) {
                let _ = setup_inventory::atomic_write(&path, &payload);
            }
        }
    }
}

fn emit_terminal(app: &AppHandle, payload: Value) {
    let _ = app.emit("pipeline-event", payload);
}

fn write_bridge_diagnostic(tail: &str) -> String {
    let directory = home_dir().join("diagnostics");
    for _ in 0..3 {
        let id = diagnostics::diagnostic_id();
        match diagnostics::write_log(&directory, &id, tail) {
            Ok(true) => return id,
            Ok(false) => continue,
            Err(_) => return id,
        }
    }
    diagnostics::diagnostic_id()
}

fn canonical_provider_id(value: &str) -> Result<String, String> {
    let kind = value.trim().to_ascii_lowercase();
    let kind = kind.strip_prefix("preset-").unwrap_or(&kind);
    if kind.is_empty()
        || !kind
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | ':' | '.'))
    {
        return Err("provider profile id is invalid".to_string());
    }
    Ok(format!("preset-{kind}"))
}

fn selected_provider_env(provider: Option<&str>) -> Option<(&'static str, String)> {
    let kind = provider?.strip_prefix("preset-").unwrap_or(provider?);
    let env_name = match kind {
        "gemini" => "CLIPGAUGE_GEMINI_API_KEY",
        "openrouter" => "CLIPGAUGE_OPENROUTER_API_KEY",
        "groq" => "CLIPGAUGE_GROQ_API_KEY",
        "cloudflare" => "CLIPGAUGE_CLOUDFLARE_API_TOKEN",
        "huggingface" => "CLIPGAUGE_HF_TOKEN",
        "cerebras" => "CLIPGAUGE_CEREBRAS_API_KEY",
        _ => "CLIPGAUGE_PROVIDER_SECRET",
    };
    canonical_provider_id(kind).ok().map(|id| (env_name, id))
}

fn is_completion_payload(value: &Value) -> bool {
    matches!(
        value.get("event").and_then(Value::as_str),
        Some("terminal" | "result")
    )
}

fn read_bounded_line<R, F>(
    reader: &mut R,
    max_bytes: usize,
    line: &mut Vec<u8>,
    mut on_activity: F,
) -> std::io::Result<Option<bool>>
where
    R: BufRead,
    F: FnMut(),
{
    line.clear();
    let mut accepted = true;
    loop {
        let chunk = reader.fill_buf()?;
        if chunk.is_empty() {
            if line.is_empty() && accepted {
                return Ok(None);
            }
            return Ok(Some(accepted));
        }
        let newline = chunk.iter().position(|byte| *byte == b'\n');
        let consumed = newline.map_or(chunk.len(), |index| index + 1);
        if accepted {
            let content_len = newline.unwrap_or(chunk.len());
            let remaining = max_bytes.saturating_sub(line.len());
            if content_len <= remaining {
                line.extend_from_slice(&chunk[..content_len]);
            } else {
                line.clear();
                accepted = false;
            }
        }
        reader.consume(consumed);
        on_activity();
        if newline.is_some() {
            return Ok(Some(accepted));
        }
    }
}

fn run_json_sidecar(command: Command, operation: &str) -> Result<Value, String> {
    let output =
        sidecar::run_bounded(command, sidecar::RunPolicy::initialization()).map_err(|error| {
            match error {
                sidecar::RunError::Spawn(message) | sidecar::RunError::Wait(message) => {
                    diagnostics::redact(&message)
                }
                sidecar::RunError::HardTimeout => {
                    format!(
                        "{operation} timed out; diagnostic {}",
                        diagnostics::diagnostic_id()
                    )
                }
                sidecar::RunError::IdleTimeout => format!(
                    "{operation} stopped producing output; diagnostic {}",
                    diagnostics::diagnostic_id()
                ),
            }
        })?;
    let stderr_tail = diagnostics::redact(&output.stderr_tail);
    let line = output
        .stdout
        .lines()
        .rev()
        .find(|line| line.trim_start().starts_with('{'));
    match line.and_then(|line| serde_json::from_str::<Value>(line).ok()) {
        Some(value) => Ok(value),
        None if !output.status.success() => Err(format!(
            "{operation} failed: {}",
            stderr_tail.chars().take(400).collect::<String>()
        )),
        None => Err(format!(
            "{operation} returned no JSON result: {}",
            stderr_tail.chars().take(400).collect::<String>()
        )),
    }
}

fn stream_pipeline(
    app: &AppHandle,
    program: &str,
    args: &[String],
    processes: Arc<Mutex<process_manager::ProcessManager>>,
    key: String,
    provider: Option<&str>,
) {
    let mut command = quiet_command(program);
    secrets::apply_operation_env(&mut command);
    if let Some((env_name, profile_id)) = selected_provider_env(provider) {
        secrets::apply_provider_operation_env(&mut command, &profile_id, env_name);
    }
    process_manager::configure_process_group(&mut command);
    let child = command
        .env("CLIPGAUGE_HOME", home_dir())
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn();
    let mut child = match child {
        Ok(c) => {
            let _ = processes
                .lock()
                .map_err(|_| ())
                .and_then(|mut state| state.register_process(&key, c.id()).map_err(|_| ()));
            c
        }
        Err(err) => {
            if let Ok(mut state) = processes.lock() {
                let _ = state.finish(&key, false);
            }
            write_lifecycle_snapshot(&processes, &key);
            emit_terminal(
                app,
                json!({
                    "event": "terminal",
                    "protocol_version": 2,
                    "ok": false,
                    "stage": "pipeline",
                    "code": "PIPELINE_START_FAILED",
                    "message": "Could not start the local pipeline. Check the installation and try again.",
                    "retryable": true,
                    "diagnostic_id": write_bridge_diagnostic(&err.to_string()),
                }),
            );
            return;
        }
    };
    let stderr_thread = child.stderr.take().map(|stderr| {
        std::thread::spawn(move || {
            let mut tail = diagnostics::BoundedTail::default();
            let mut reader = BufReader::new(stderr);
            let mut buffer = [0u8; 4096];
            loop {
                match reader.read(&mut buffer) {
                    Ok(0) | Err(_) => break,
                    Ok(count) => tail.push(&buffer[..count]),
                }
            }
            tail
        })
    });
    let mut completion_payload: Option<Value> = None;
    if let Some(stdout) = child.stdout.take() {
        let mut reader = BufReader::new(stdout);
        let mut line = Vec::with_capacity(8192);
        loop {
            let result =
                read_bounded_line(&mut reader, sidecar::MAX_DIAGNOSTIC_BYTES, &mut line, || {});
            let Ok(Some(accepted)) = result else { break };
            if !accepted {
                continue;
            }
            if let Ok(value) = serde_json::from_slice::<Value>(&line) {
                if is_completion_payload(&value) {
                    completion_payload = Some(value);
                    continue;
                }
                if let Some(job_id) = value.get("job_id").and_then(Value::as_str) {
                    if let Ok(mut state) = processes.lock() {
                        let _ = state.adopt_job_id(&key, job_id.to_string());
                        state.update_stage(
                            &key,
                            value
                                .get("stage")
                                .and_then(Value::as_str)
                                .map(str::to_string),
                        );
                    }
                    write_lifecycle_snapshot(&processes, &key);
                }
                let _ = app.emit("pipeline-event", value);
            }
        }
    }
    let status = child.wait();
    let stderr_tail = stderr_thread
        .and_then(|thread| thread.join().ok())
        .unwrap_or_default();
    let cancelled = processes
        .lock()
        .map(|state| state.is_cancel_requested(&key))
        .unwrap_or(false);
    if cancelled {
        if let Ok(mut state) = processes.lock() {
            let _ = state.finish(&key, false);
        }
        write_lifecycle_snapshot(&processes, &key);
        emit_terminal(
            app,
            json!({
                "event": "terminal",
                "protocol_version": 2,
                "ok": false,
                "stage": "pipeline",
                "code": "CANCELLED",
                "message": "The job was cancelled. Completed checkpoints remain available for resume.",
                "retryable": true,
            }),
        );
    } else if let Some(payload) = completion_payload {
        let success = payload.get("ok").and_then(Value::as_bool).unwrap_or(false);
        if let Ok(mut state) = processes.lock() {
            let _ = state.finish(&key, success);
        }
        write_lifecycle_snapshot(&processes, &key);
        let _ = app.emit("pipeline-event", payload);
    } else {
        if let Ok(mut state) = processes.lock() {
            let _ = state.finish(&key, false);
        }
        write_lifecycle_snapshot(&processes, &key);
        let exit_code = status.as_ref().ok().and_then(|s| s.code());
        let diagnostic_id = write_bridge_diagnostic(&stderr_tail.text());
        emit_terminal(
            app,
            json!({
                "event": "terminal",
                "protocol_version": 2,
                "ok": false,
                "stage": "pipeline",
                "code": "PIPELINE_EXIT_WITHOUT_TERMINAL",
                "message": "The local pipeline stopped before reporting a complete result. Retry the job or use the diagnostic ID for support.",
                "retryable": true,
                "diagnostic_id": diagnostic_id,
                "exit_code": exit_code,
            }),
        );
    }
}

/// Everything the review UI needs for one job, read straight off the job
/// dir's checkpoint files (artifacts are the truth).
#[tauri::command]
fn cancel_job(state: State<'_, AppState>, job_id: String) -> Result<(), String> {
    validate_job_id(&job_id)?;
    let process_id = state
        .processes
        .lock()
        .map_err(|_| "job lifecycle state is unavailable".to_string())?
        .request_cancel(&job_id)?;
    process_manager::terminate_owned(process_id)
}

#[tauri::command]
async fn job_results(job_id: String) -> Result<Value, String> {
    spawn_blocking_result(move || artifact::job_results(&home_dir(), &job_id)).await
}

#[tauri::command]
async fn list_job_dirs() -> Result<Vec<Value>, String> {
    spawn_blocking_result(list_job_dirs_blocking).await
}

fn list_job_dirs_blocking() -> Result<Vec<Value>, String> {
    let jobs_dir = home_dir().join("jobs");
    let mut out = vec![];
    if let Ok(entries) = fs::read_dir(&jobs_dir) {
        for entry in entries.flatten() {
            let id = entry.file_name().to_string_lossy().to_string();
            if !path_security::valid_job_id(&id)
                || path_security::resolve_job_dir(&home_dir(), &id).is_err()
            {
                continue;
            }
            let dir = entry.path();
            let has_render = dir.join("render.json").exists();
            let has_ingest = dir.join("ingest.json").exists();
            let outcome = fs::read_to_string(dir.join("score.json"))
                .ok()
                .and_then(|text| serde_json::from_str::<Value>(&text).ok())
                .and_then(|value| value["data"]["outcome"].as_str().map(String::from));
            let lifecycle = fs::read_to_string(dir.join("lifecycle.json"))
                .ok()
                .and_then(|text| serde_json::from_str::<Value>(&text).ok());
            let lifecycle_state = lifecycle
                .as_ref()
                .and_then(|value| value["state"].as_str())
                .unwrap_or(
                    if outcome.as_deref() == Some("SUCCESS_NO_RECOMMENDATIONS") {
                        "COMPLETED_NO_RECOMMENDATIONS"
                    } else if has_render {
                        "COMPLETED"
                    } else {
                        "RESUMABLE"
                    },
                );
            let last_stage = lifecycle.as_ref().and_then(|value| value["stage"].as_str());
            let resume_safe = !has_render
                && matches!(
                    lifecycle_state,
                    "RESUMABLE" | "INTERRUPTED" | "CANCELLED" | "FAILED"
                );
            let title = fs::read_to_string(dir.join("ingest.json"))
                .ok()
                .and_then(|s| serde_json::from_str::<Value>(&s).ok())
                .and_then(|v| v["data"]["title"].as_str().map(String::from));
            out.push(json!({
                "id": id, "title": title,
                "ingested": has_ingest, "rendered": has_render,
                "outcome": outcome,
                "lifecycle_state": lifecycle_state,
                "last_stage": last_stage,
                "resume_safe": resume_safe,
            }));
        }
    }
    out.sort_by(|a, b| b["id"].as_str().cmp(&a["id"].as_str()));
    Ok(out)
}

#[tauri::command]
async fn save_gemini_key(key: String) -> Result<bool, String> {
    spawn_blocking_result(move || {
        secrets::set(secrets::SecretName::GeminiApiKey, key.trim())?;
        Ok(true)
    })
    .await
}

#[tauri::command]
async fn save_provider_key(profile_id: String, key: String) -> Result<bool, String> {
    spawn_blocking_result(move || {
        let canonical = canonical_provider_id(&profile_id)?;
        secrets::set_provider_auth(&canonical, key.trim())?;
        Ok(true)
    })
    .await
}

#[tauri::command]
async fn remove_provider_key(profile_id: String) -> Result<bool, String> {
    spawn_blocking_result(move || {
        let canonical = canonical_provider_id(&profile_id)?;
        secrets::delete_provider_auth(&canonical)?;
        Ok(true)
    })
    .await
}

#[tauri::command]
async fn remove_gemini_key() -> Result<bool, String> {
    spawn_blocking_result(|| {
        secrets::delete(secrets::SecretName::GeminiApiKey)?;
        Ok(true)
    })
    .await
}

#[tauri::command]
async fn get_setup_state() -> Result<Value, String> {
    spawn_blocking_result(get_setup_state_blocking).await
}

fn get_setup_state_blocking() -> Result<Value, String> {
    let has_key = secrets::get(secrets::SecretName::GeminiApiKey)?.is_some();
    let mut provider_keys = serde_json::Map::new();
    for kind in [
        "openrouter",
        "groq",
        "cloudflare",
        "huggingface",
        "cerebras",
        "custom",
    ] {
        let id = canonical_provider_id(kind)?;
        let has = secrets::get_provider_auth(&id)?.is_some();
        provider_keys.insert(kind.to_string(), Value::Bool(has));
    }
    let onboarded = onboarded_marker_exists(&home_dir());
    Ok(json!({"has_gemini_key": has_key, "onboarded": onboarded, "provider_keys": provider_keys}))
}

#[tauri::command]
async fn mark_onboarded() -> Result<(), String> {
    spawn_blocking_result(|| mark_onboarded_at(&home_dir())).await
}

#[tauri::command]
async fn save_local_model(model_id: String) -> Result<(), String> {
    spawn_blocking_result(move || setup_inventory::save_selected_model(&home_dir(), &model_id))
        .await
}

fn loopback_json(path: &str) -> Result<Value, String> {
    use std::net::{TcpStream, ToSocketAddrs};
    use std::time::Duration;

    let address = ("127.0.0.1", 11434)
        .to_socket_addrs()
        .map_err(|_| "Ollama address could not be resolved".to_string())?
        .next()
        .ok_or_else(|| "Ollama loopback address is unavailable".to_string())?;
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_secs(3))
        .map_err(|_| "Ollama is stopped or absent".to_string())?;
    stream
        .set_read_timeout(Some(Duration::from_secs(3)))
        .map_err(|error| error.to_string())?;
    stream
        .set_write_timeout(Some(Duration::from_secs(3)))
        .map_err(|error| error.to_string())?;
    let request =
        format!("GET {path} HTTP/1.1\r\nHost: 127.0.0.1:11434\r\nConnection: close\r\n\r\n");
    stream
        .write_all(request.as_bytes())
        .map_err(|_| "Ollama health request could not be sent".to_string())?;
    let mut response = Vec::new();
    let mut buffer = [0_u8; 8192];
    loop {
        let count = stream
            .read(&mut buffer)
            .map_err(|_| "Ollama health response timed out".to_string())?;
        if count == 0 {
            break;
        }
        if response.len() + count > 1024 * 1024 {
            return Err("Ollama health response exceeded the 1 MiB safety limit".to_string());
        }
        response.extend_from_slice(&buffer[..count]);
    }
    let marker = b"\r\n\r\n";
    let body_start = response
        .windows(marker.len())
        .position(|window| window == marker)
        .map(|index| index + marker.len())
        .ok_or_else(|| "Ollama returned an invalid HTTP response".to_string())?;
    let headers = String::from_utf8_lossy(&response[..body_start]);
    if !headers.starts_with("HTTP/1.1 200") && !headers.starts_with("HTTP/1.0 200") {
        return Err("Ollama health endpoint returned a non-success status".to_string());
    }
    serde_json::from_slice(&response[body_start..])
        .map_err(|_| "Ollama returned malformed health JSON".to_string())
}

#[tauri::command]
async fn check_ollama() -> Result<Value, String> {
    spawn_blocking_result(|| {
        let parsed = match loopback_json("/api/tags") {
            Ok(value) => value,
            Err(message) => {
                return Ok(
                    json!({"state": "service-stopped", "running": false, "models": [], "message": message}),
                )
            }
        };
        let models: Vec<String> = parsed["models"]
            .as_array()
            .map(|arr| {
                arr.iter()
                    .filter_map(|m| m["name"].as_str().map(String::from))
                    .collect()
            })
            .unwrap_or_default();
        let state = if models.is_empty() {
            "model-missing"
        } else {
            "service-healthy"
        };
        Ok(json!({"state": state, "running": true, "models": models}))
    })
    .await
}

fn stream_setup(
    app: &AppHandle,
    program: &str,
    args: &[String],
    processes: Arc<Mutex<process_manager::ProcessManager>>,
    key: String,
) {
    let mut command = quiet_command(program);
    secrets::apply_operation_env(&mut command);
    process_manager::configure_process_group(&mut command);
    let child = command
        .env("CLIPGAUGE_HOME", home_dir())
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn();
    let mut child = match child {
        Ok(child) => child,
        Err(_error) => {
            if let Ok(mut state) = processes.lock() {
                let _ = state.finish(&key, false);
            }
            write_lifecycle_snapshot(&processes, &key);
            let _ = app.emit(
                "setup-event",
                json!({
                    "event": "terminal",
                    "ok": false,
                    "code": "SETUP_START_FAILED",
                    "message": setup_start_failure_message(),
                    "retryable": true,
                    "diagnostic_id": diagnostics::diagnostic_id(),
                }),
            );
            return;
        }
    };
    let cancelled_during_registration = match processes.lock() {
        Ok(mut state) => {
            let _ = state.adopt_job_id(&key, key.clone());
            let _ = state.register_process(&key, child.id());
            state.is_cancel_requested(&key)
        }
        Err(_) => true,
    };
    if cancelled_during_registration {
        let _ = process_manager::terminate_owned(child.id());
    }
    let started = Instant::now();
    let last_output = Arc::new(AtomicU64::new(0));
    let stdout_reader = if let Some(stdout) = child.stdout.take() {
        let app_clone = app.clone();
        let activity = Arc::clone(&last_output);
        Some(thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            let mut line = Vec::with_capacity(8192);
            loop {
                line.clear();
                let result = read_bounded_line(
                    &mut reader,
                    sidecar::MAX_DIAGNOSTIC_BYTES,
                    &mut line,
                    || activity.store(started.elapsed().as_millis() as u64, Ordering::Relaxed),
                );
                let Ok(Some(accepted)) = result else { break };
                if accepted {
                    if let Ok(value) = serde_json::from_slice::<Value>(&line) {
                        let _ = app_clone.emit("setup-event", value);
                    }
                }
            }
        }))
    } else {
        None
    };
    let stderr_reader = child.stderr.take().map(|mut stderr| {
        let activity = Arc::clone(&last_output);
        thread::spawn(move || {
            let mut tail = diagnostics::BoundedTail::new(sidecar::MAX_DIAGNOSTIC_BYTES);
            let mut buffer = [0_u8; 8192];
            loop {
                match stderr.read(&mut buffer) {
                    Ok(0) | Err(_) => break,
                    Ok(count) => {
                        activity.store(started.elapsed().as_millis() as u64, Ordering::Relaxed);
                        tail.push(&buffer[..count]);
                    }
                }
            }
            tail.text()
        })
    });
    let policy = sidecar::RunPolicy::initialization();
    let mut timed_out = None;
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) => {}
            Err(error) => {
                let _ = process_manager::terminate_owned(child.id());
                let _ = child.wait();
                timed_out = Some(format!("Setup process could not be monitored: {error}"));
                break None;
            }
        }
        if started.elapsed() >= policy.hard_timeout {
            timed_out = Some("Setup exceeded its two-hour safety limit.".to_string());
            let _ = process_manager::terminate_owned(child.id());
            let _ = child.wait();
            break None;
        }
        let last_activity = Duration::from_millis(last_output.load(Ordering::Relaxed));
        if started.elapsed().saturating_sub(last_activity) >= policy.idle_timeout {
            timed_out = Some("Setup stopped producing progress for five minutes.".to_string());
            let _ = process_manager::terminate_owned(child.id());
            let _ = child.wait();
            break None;
        }
        thread::sleep(policy.poll_interval);
    };
    let _ = stdout_reader.and_then(|reader| reader.join().ok());
    let stderr_tail = stderr_reader
        .and_then(|reader| reader.join().ok())
        .unwrap_or_default();
    let success = status.map(|value| value.success()).unwrap_or(false);
    if let Ok(mut state) = processes.lock() {
        let cancelled = state.is_cancel_requested(&key);
        let _ = state.finish(&key, success && !cancelled);
        let event = if cancelled {
            json!({"event": "terminal", "ok": false, "code": "CANCELLED", "message": "Setup was cancelled. Verified assets remain reusable."})
        } else if let Some(message) = timed_out {
            json!({"event": "terminal", "ok": false, "code": "SETUP_TIMED_OUT", "message": message, "retryable": true, "diagnostic_id": diagnostics::diagnostic_id(), "stderr_tail": diagnostics::redact(&stderr_tail)})
        } else if success {
            json!({"event": "terminal", "ok": true, "code": "OK", "message": "Setup completed."})
        } else {
            json!({"event": "terminal", "ok": false, "code": "SETUP_FAILED", "message": "Setup failed; retry or repair the selected asset.", "retryable": true, "diagnostic_id": diagnostics::diagnostic_id(), "stderr_tail": diagnostics::redact(&stderr_tail)})
        };
        drop(state);
        let _ = app.emit("setup-event", event);
        write_lifecycle_snapshot(&processes, &key);
    }
}

fn setup_start_failure_message() -> &'static str {
    "Setup could not start. Check the installation and retry. Use the diagnostic ID for support."
}

fn valid_start_setup_args(args: &[String]) -> bool {
    matches!(args, [command] if command == "install-runtime" || command == "install-ffmpeg")
        || matches!(args, [command, group, value] if command == "install-group" && group == "--group" && matches!(value.as_str(), "core:asr" | "core:analysis" | "core:youtube"))
        || matches!(args, [command, asset] if command == "install-asset" && asset.len() <= 180 && asset.chars().all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, ':' | '-' | '_' | '/' | '.')))
        || matches!(args, [command, model] if command == "download-model" && model.starts_with("clipgauge-local/") && model.len() <= 120 && model.chars().all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '/' | '.')))
}

fn valid_setup_tool_args(args: &[String]) -> bool {
    let storage_target = |value: &str| {
        matches!(
            value,
            "session" | "failed-session" | "safe-cache" | "obsolete-runtime-archives"
        )
    };
    let valid_storage_preview = matches!(args, [command, target] if command == "storage-preview" && storage_target(target))
        || matches!(args, [command, target, job_id] if command == "storage-preview" && storage_target(target) && path_security::valid_job_id(job_id));
    let valid_storage_cleanup = matches!(args, [command, target, confirm] if command == "storage-cleanup" && storage_target(target) && confirm == "--confirm")
        || matches!(args, [command, target, job_id, confirm] if command == "storage-cleanup" && storage_target(target) && path_security::valid_job_id(job_id) && confirm == "--confirm");
    valid_storage_preview
        || valid_storage_cleanup
        || matches!(args, [command] if command == "inventory" || command == "gpu-status" || command == "gpu-repair" || command == "youtube-status" || command == "youtube-test" || command == "install-runtime" || command == "install-ffmpeg")
        || matches!(args, [command, flag, model] if command == "inventory" && flag == "--model" && model.starts_with("clipgauge-local/") && model.len() <= 120 && model.chars().all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '/' | '.')))
        || matches!(args, [command, group, value] if command == "install-group" && group == "--group" && matches!(value.as_str(), "core:asr" | "core:analysis" | "core:youtube"))
        || matches!(args, [command, asset] if command == "install-asset" && asset.len() <= 180 && asset.chars().all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, ':' | '-' | '_' | '/' | '.')))
        || matches!(args, [command, model] if command == "download-model" && model.starts_with("clipgauge-local/") && model.len() <= 120 && model.chars().all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '/' | '.')))
}

#[tauri::command]
fn start_setup(
    app: AppHandle,
    state: State<'_, AppState>,
    args: Vec<String>,
) -> Result<String, String> {
    if !valid_start_setup_args(&args) {
        return Err("unsupported setup operation".to_string());
    }
    let (program, base_args) = pipeline_invocation();
    let key = format!("setup:{}", diagnostics::diagnostic_id());
    reserve_process(&state.processes, key.clone())?;
    state
        .processes
        .lock()
        .map_err(|_| "setup lifecycle state is unavailable".to_string())?
        .adopt_job_id(&key, key.clone())?;
    let processes = state.processes.clone();
    let initialization = state.initialization.clone();
    let worker_key = key.clone();
    std::thread::spawn(move || {
        let init_processes = processes.clone();
        let init_key = worker_key.clone();
        if let Err(_error) = initialization.ensure_initialized(|| {
            initialize_pipeline_with_registration(|process_id| {
                if let Ok(mut lifecycle) = init_processes.lock() {
                    let _ = lifecycle.adopt_job_id(&init_key, init_key.clone());
                    let _ = lifecycle.register_process(&init_key, process_id);
                    if lifecycle.is_cancel_requested(&init_key) {
                        let _ = process_manager::terminate_owned(process_id);
                    }
                }
            })
        }) {
            let cancelled = processes
                .lock()
                .map(|state| state.is_cancel_requested(&worker_key))
                .unwrap_or(false);
            let message = if cancelled {
                "Setup was cancelled. Verified assets remain reusable.".to_string()
            } else {
                setup_start_failure_message().to_string()
            };
            if let Ok(mut state) = processes.lock() {
                let _ = state.finish(&worker_key, false);
            }
            write_lifecycle_snapshot(&processes, &worker_key);
            let _ = app.emit(
                "setup-event",
                json!({
                    "event": "terminal",
                    "ok": false,
                    "code": if cancelled { "CANCELLED" } else { "SETUP_INITIALIZATION_FAILED" },
                    "message": message,
                    "retryable": true,
                    "diagnostic_id": diagnostics::diagnostic_id(),
                }),
            );
            return;
        }
        let cancelled_during_initialization = processes
            .lock()
            .map(|state| state.is_cancel_requested(&worker_key))
            .unwrap_or(true);
        if cancelled_during_initialization {
            if let Ok(mut state) = processes.lock() {
                let _ = state.finish(&worker_key, false);
            }
            write_lifecycle_snapshot(&processes, &worker_key);
            let _ = app.emit(
                "setup-event",
                json!({
                    "event": "terminal",
                    "ok": false,
                    "code": "CANCELLED",
                    "message": "Setup was cancelled. Verified assets remain reusable.",
                }),
            );
            return;
        }
        let mut full = base_args;
        full.push("--jsonl".to_string());
        full.push("setup".to_string());
        full.extend(args);
        stream_setup(&app, &program, &full, processes, worker_key);
    });
    Ok(key)
}

#[tauri::command]
fn cancel_setup(state: State<'_, AppState>, operation_id: String) -> Result<(), String> {
    if !operation_id.starts_with("setup:") || operation_id.len() > 120 {
        return Err("invalid setup operation id".to_string());
    }
    let mut lifecycle = state
        .processes
        .lock()
        .map_err(|_| "setup lifecycle state is unavailable".to_string())?;
    match lifecycle.request_cancel(&operation_id) {
        Ok(process_id) => process_manager::terminate_owned(process_id),
        Err(_error) if lifecycle.is_cancel_requested_for_job_id(&operation_id) => Ok(()),
        Err(error) => Err(error),
    }
}

#[tauri::command]
async fn setup_tool(state: State<'_, AppState>, args: Vec<String>) -> Result<Value, String> {
    let initialization = state.initialization.clone();
    spawn_blocking_result(move || setup_tool_blocking(args, initialization)).await
}

fn setup_tool_blocking(
    args: Vec<String>,
    initialization: Arc<sidecar::InitializationCoordinator>,
) -> Result<Value, String> {
    if !valid_setup_tool_args(&args) {
        return Err("unsupported setup operation".to_string());
    }
    if args.first().map(String::as_str) == Some("storage-preview")
        || args.first().map(String::as_str) == Some("storage-cleanup")
    {
        let mode = if args[0] == "storage-preview" {
            sidecar::PipelineMode::ReadOnly
        } else {
            sidecar::PipelineMode::ManagedOperation
        };
        if mode == sidecar::PipelineMode::ManagedOperation {
            initialization.ensure_initialized(initialize_pipeline)?;
        }
        let (program, base_args) = pipeline_invocation_for(mode);
        let mut full = base_args;
        full.push("--jsonl".to_string());
        full.push("setup".to_string());
        full.extend(args);
        let mut command = quiet_command(&program);
        secrets::apply_operation_env(&mut command);
        command.env("CLIPGAUGE_HOME", home_dir()).args(&full);
        let out = sidecar::run_bounded(command, sidecar::RunPolicy::status())
            .map_err(|error| format!("storage operation failed: {error:?}"))?;
        return serde_json::from_str(&out.stdout)
            .map_err(|error| format!("storage operation returned invalid JSON: {error}"));
    }
    if args.first().map(String::as_str) == Some("inventory") {
        let requested_model = args.get(2).map(String::as_str);
        return setup_inventory::native_inventory(
            &pipeline_resources_dir(),
            &home_dir(),
            requested_model,
        )
        .map_err(|error| diagnostics::redact(&error));
    }
    let mode = match args.first().map(String::as_str) {
        Some("inventory" | "gpu-status" | "youtube-status" | "youtube-test") => {
            sidecar::PipelineMode::ReadOnly
        }
        _ => sidecar::PipelineMode::ManagedOperation,
    };
    if mode == sidecar::PipelineMode::ReadOnly && !pipeline_environment_ready() {
        return Err("PIPELINE_NOT_INITIALIZED".to_string());
    }
    if mode == sidecar::PipelineMode::ManagedOperation {
        initialization.ensure_initialized(initialize_pipeline)?;
    }
    let (program, base_args) = pipeline_invocation_for(mode);
    let mut full = base_args;
    full.push("--jsonl".to_string());
    full.push("setup".to_string());
    full.extend(args);
    let mut command = quiet_command(&program);
    secrets::apply_operation_env(&mut command);
    // Forward an explicitly configured system tool across the packaged
    // native-to-sidecar boundary so Setup reflects the actual GUI runtime.
    if let Some(ffmpeg) = std::env::var_os("CLIPGAUGE_FFMPEG") {
        command.env("CLIPGAUGE_FFMPEG", ffmpeg);
    }
    if let Some(path) = std::env::var_os("PATH") {
        command.env("PATH", path);
    }
    #[cfg(target_os = "windows")]
    apply_qa_ffmpeg_env(&mut command);
    command.env("CLIPGAUGE_HOME", home_dir()).args(&full);
    let policy = if mode == sidecar::PipelineMode::ReadOnly {
        sidecar::RunPolicy::status()
    } else {
        sidecar::RunPolicy::initialization()
    };
    let out = sidecar::run_bounded(command, policy).map_err(|error| match error {
        sidecar::RunError::Spawn(message) | sidecar::RunError::Wait(message) => {
            diagnostics::redact(&message)
        }
        sidecar::RunError::HardTimeout => format!(
            "setup command timed out; diagnostic {}",
            diagnostics::diagnostic_id()
        ),
        sidecar::RunError::IdleTimeout => format!(
            "setup command stopped producing output; diagnostic {}",
            diagnostics::diagnostic_id()
        ),
    })?;
    if !out.status.success() {
        return Err(format!(
            "setup command failed: {}",
            diagnostics::redact(&out.stderr_tail)
        ));
    }
    let stdout = out.stdout;
    let line = stdout
        .lines()
        .rev()
        .find(|line| line.trim_start().starts_with('{'));
    match line.and_then(|line| serde_json::from_str::<Value>(line).ok()) {
        Some(value) => Ok(value),
        None => Err(format!(
            "setup command produced no JSON: {}",
            diagnostics::redact(&out.stderr_tail)
                .chars()
                .take(400)
                .collect::<String>()
        )),
    }
}

/// Sync pipeline call that returns one JSON blob (edit context, visual
/// suggestions). Long-running render-clip goes through run_edit_render
/// instead so progress streams.
#[tauri::command]
async fn edit_tool(args: Vec<String>) -> Result<Value, String> {
    spawn_blocking_result(move || edit_tool_blocking(args)).await
}

fn edit_tool_blocking(args: Vec<String>) -> Result<Value, String> {
    let (program, base_args) = pipeline_invocation();
    let mut full = base_args;
    full.push("edit".to_string());
    full.extend(args);
    let mut command = quiet_command(&program);
    secrets::apply_operation_env(&mut command);
    command.env("CLIPGAUGE_HOME", home_dir()).args(&full);
    run_json_sidecar(command, "edit tool")
}

#[tauri::command]
fn run_edit_render(
    app: AppHandle,
    state: State<'_, AppState>,
    job_id: String,
    clip: u32,
) -> Result<(), String> {
    validate_job_id(&job_id)?;
    let (program, base_args) = pipeline_invocation();
    let processes = state.processes.clone();
    let key = format!("edit:{job_id}:{clip}");
    reserve_process(&processes, key.clone())?;
    std::thread::spawn(move || {
        let mut args = base_args.clone();
        args.push("--jsonl".to_string());
        args.push("edit".to_string());
        args.push("render-clip".to_string());
        args.push(job_id);
        args.push(clip.to_string());
        stream_pipeline(&app, &program, &args, processes, key, None);
    });
    Ok(())
}

#[tauri::command]
async fn save_clip_edits(
    job_id: String,
    input: edit_schema::SaveClipEditsInput,
) -> Result<(), String> {
    spawn_blocking_result(move || save_clip_edits_blocking(job_id, input)).await
}

fn save_clip_edits_blocking(
    job_id: String,
    input: edit_schema::SaveClipEditsInput,
) -> Result<(), String> {
    let dir = validate_job_id(&job_id)?;
    let score_path = dir.join("score.json");
    let score: Value = serde_json::from_str(
        &fs::read_to_string(&score_path)
            .map_err(|_| "score checkpoint is unavailable".to_string())?,
    )
    .map_err(|_| "score checkpoint is malformed".to_string())?;
    let incoming = edit_schema::validate(&dir, &input, &score)?;
    let path = dir.join("clip_edits.json");
    let mut current: Value = fs::read_to_string(&path)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_else(|| json!({}));
    let current_obj = current
        .as_object_mut()
        .ok_or_else(|| "existing clip edits are malformed".to_string())?;
    let incoming_obj = incoming
        .as_object()
        .ok_or_else(|| "validated clip edits are malformed".to_string())?;
    for (key, value) in incoming_obj {
        current_obj.insert(key.clone(), value.clone());
    }
    let payload = serde_json::to_vec_pretty(&current).map_err(|e| e.to_string())?;
    setup_inventory::atomic_write(&path, &payload)
}

#[tauri::command]
async fn save_pexels_key(key: String) -> Result<bool, String> {
    spawn_blocking_result(move || {
        secrets::set(secrets::SecretName::PexelsApiKey, key.trim())?;
        Ok(true)
    })
    .await
}

#[tauri::command]
async fn ig_status() -> Result<Value, String> {
    spawn_blocking_result(ig_status_blocking).await
}

fn ig_status_blocking() -> Result<Value, String> {
    let connected = secrets::get(secrets::SecretName::InstagramConnection)?
        .and_then(|raw| serde_json::from_str::<Value>(&raw).ok());
    match connected.filter(instagram_connection_is_valid) {
        Some(v) => Ok(json!({
            "connected": true,
            "username": v["username"],
            "obtained_at": v["token_obtained_at"],
        })),
        None => Ok(json!({"connected": false})),
    }
}

fn instagram_connection_from_json(raw: &str) -> Result<Value, String> {
    let value = serde_json::from_str::<Value>(raw)
        .map_err(|_| "Instagram connection is malformed.".to_string())?;
    if !instagram_connection_is_valid(&value) {
        return Err("Instagram connection is incomplete.".to_string());
    }
    Ok(value)
}

fn instagram_connection_is_valid(value: &Value) -> bool {
    let Some(object) = value.as_object() else {
        return false;
    };
    ["user_id", "access_token"].iter().all(|field| {
        object
            .get(*field)
            .and_then(Value::as_str)
            .is_some_and(|value| !value.trim().is_empty())
    })
}

fn ig_connect_args(mut base_args: Vec<String>, app_id: String) -> Vec<String> {
    base_args.extend([
        "ig".into(),
        "connect".into(),
        "--app-id".into(),
        app_id,
        "--app-secret-stdin".into(),
    ]);
    base_args
}

fn ig_failure_message(stderr: &str, stdout: &str, exit_code: Option<i32>) -> String {
    let context = if stderr.trim().is_empty() {
        stdout
    } else {
        stderr
    };
    let safe = diagnostics::redact(context.trim());
    match exit_code {
        Some(code) if safe.is_empty() => format!("Instagram connection failed (exit code {code})."),
        Some(code) => format!("Instagram connection failed (exit code {code}): {safe}"),
        None if safe.is_empty() => {
            "Instagram connection failed before it returned a result.".to_string()
        }
        None => format!("Instagram connection failed: {safe}"),
    }
}

/// Runs the CLI's OAuth dance (it opens the browser + catches the localhost
/// callback). Blocking by design — the frontend shows a "finish in your
/// browser" state until this returns.
#[tauri::command]
async fn ig_connect(app_id: String, app_secret: String) -> Result<String, String> {
    spawn_blocking_result(move || ig_connect_blocking(app_id, app_secret)).await
}

fn ig_connect_blocking(app_id: String, app_secret: String) -> Result<String, String> {
    let (program, base_args) = pipeline_invocation();
    let args = ig_connect_args(base_args, app_id);
    let connection_output = home_dir().join(format!(
        ".instagram-connection-{}.json",
        uuid::Uuid::new_v4()
    ));

    let mut command = quiet_command(&program);
    secrets::apply_operation_env(&mut command);
    command
        .env("CLIPGAUGE_HOME", home_dir())
        .env("CLIPGAUGE_CONNECTION_OUTPUT", &connection_output)
        .args(&args);
    let out = sidecar::run_bounded_with_stdin(
        command,
        app_secret.as_bytes(),
        sidecar::RunPolicy::interactive(),
    )
    .map_err(|error| match error {
        sidecar::RunError::Spawn(message) | sidecar::RunError::Wait(message) => {
            diagnostics::redact(&message)
        }
        sidecar::RunError::HardTimeout => {
            format!(
                "Instagram connection timed out; diagnostic {}",
                diagnostics::diagnostic_id()
            )
        }
        sidecar::RunError::IdleTimeout => format!(
            "Instagram connection stopped producing output; diagnostic {}",
            diagnostics::diagnostic_id()
        ),
    })?;
    let stdout = out.stdout.trim().to_string();
    let stderr = out.stderr_tail.trim().to_string();
    if out.status.success() {
        let persisted = fs::read_to_string(&connection_output)
            .map_err(|error| diagnostics::redact(&error.to_string()))?;
        let parsed = instagram_connection_from_json(&persisted)?;
        let compact = serde_json::to_string(&parsed).map_err(|error| error.to_string())?;
        secrets::set(secrets::SecretName::InstagramConnection, &compact)?;
        let _ = fs::remove_file(&connection_output);
        Ok(stdout)
    } else {
        let _ = fs::remove_file(&connection_output);
        Err(ig_failure_message(&stderr, &stdout, out.status.code()))
    }
}

/// One-shot `clipgauge ig <args...>` call returning the CLI's JSON line
/// (sync / overview / link / unlink / reject — same contract as edit_tool).
#[tauri::command]
async fn ig_tool(args: Vec<String>) -> Result<Value, String> {
    spawn_blocking_result(move || ig_tool_blocking(args)).await
}

fn ig_tool_blocking(args: Vec<String>) -> Result<Value, String> {
    let (program, base_args) = pipeline_invocation();
    let mut full = base_args;
    full.push("ig".to_string());
    full.extend(args);
    let mut command = quiet_command(&program);
    secrets::apply_operation_env(&mut command);
    command.env("CLIPGAUGE_HOME", home_dir()).args(&full);
    run_json_sidecar(command, "ig tool")
}

#[tauri::command]
fn record_media_event(input: Value) -> Result<(), String> {
    if std::env::var("CLIPGAUGE_QA_MEDIA_TRACE").ok().as_deref() != Some("1") {
        return Ok(());
    }
    let object = input
        .as_object()
        .ok_or_else(|| "media trace payload is malformed".to_string())?;
    let allowed = [
        "label",
        "event",
        "error_code",
        "error_message",
        "network_state",
        "ready_state",
        "duration",
        "video_width",
        "video_height",
        "current_src",
    ];
    let safe = object
        .iter()
        .filter(|(key, _)| allowed.contains(&key.as_str()))
        .map(|(key, value)| (key.clone(), value.clone()))
        .collect::<serde_json::Map<_, _>>();
    let mut line = serde_json::to_string(&safe).map_err(|error| error.to_string())?;
    line.push('\n');
    let path = home_dir().join("qa-media-events.jsonl");
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    if fs::metadata(&path)
        .map(|metadata| metadata.len())
        .unwrap_or(0)
        >= 64 * 1024
    {
        return Ok(());
    }
    let mut file = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| error.to_string())?;
    file.write_all(line.as_bytes())
        .map_err(|error| error.to_string())
}

#[tauri::command]
async fn request_playback_url(
    state: State<'_, AppState>,
    job_id: String,
    artifact_type: String,
    clip: Option<u32>,
) -> Result<String, String> {
    let media = state.media.clone();
    spawn_blocking_result(move || {
        let path = match artifact_type.as_str() {
            "render" => artifact::render_artifact(&home_dir(), &job_id, clip.unwrap_or(0))?,
            "source" => artifact::source_media_artifact(&home_dir(), &job_id)?,
            _ => return Err("unsupported playback artifact".into()),
        };
        media.authorize(path)
    })
    .await
}

#[tauri::command]
async fn export_clip(
    job_id: String,
    clip: u32,
    title: Option<String>,
    destination: Option<String>,
) -> Result<String, String> {
    spawn_blocking_result(move || {
        let home = home_dir();
        match destination {
            Some(path) => artifact::export_clip_to(&home, &job_id, clip, Path::new(&path)),
            None => {
                artifact::export_clip(&home, &dirs_home().join("Downloads"), &job_id, clip, title)
            }
        }
    })
    .await
}

#[cfg(target_os = "windows")]
fn apply_qa_ffmpeg_env(command: &mut Command) {
    if std::env::var_os("CLIPGAUGE_QA_WEBVIEW2_CDP").is_some() {
        command.env_remove("CLIPGAUGE_FFMPEG");
    }
}

fn main() {
    let context = tauri::generate_context!();
    #[cfg(target_os = "windows")]
    let context = {
        if std::env::var_os("CLIPGAUGE_QA_WEBVIEW2_CDP").is_some() {
            let mut context = context;
            if let Some(window) = context.config_mut().app.windows.first_mut() {
                let port = std::env::var("CLIPGAUGE_QA_WEBVIEW2_PORT")
                    .unwrap_or_else(|_| "9222".to_string());
                window.additional_browser_args = Some(format!("--remote-debugging-port={port}"));
            }
            context
        } else {
            context
        }
    };

    let media =
        Arc::new(media_server::MediaServer::start().expect("failed to start local media server"));
    tauri::Builder::default()
        .manage(AppState::new(media))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            preflight,
            privacy_summary,
            test_connection,
            provider_models,
            generate_support_bundle,
            run_job,
            resume_job,
            cancel_job,
            job_results,
            list_job_dirs,
            save_gemini_key,
            save_provider_key,
            remove_provider_key,
            remove_gemini_key,
            vault_scope,
            get_setup_state,
            mark_onboarded,
            save_local_model,
            check_ollama,
            setup_tool,
            start_setup,
            cancel_setup,
            ig_status,
            ig_connect,
            ig_tool,
            edit_tool,
            run_edit_render,
            save_clip_edits,
            record_media_event,
            request_playback_url,
            save_pexels_key,
            export_clip
        ])
        .setup(|app| {
            let _ = app.get_webview_window("main");
            migrate_legacy_data().map_err(std::io::Error::other)?;
            secrets::migrate_legacy(&home_dir()).map_err(std::io::Error::other)?;
            secrets::migrate_instagram_file(&home_dir()).map_err(std::io::Error::other)?;
            if let Ok(mut processes) = app.state::<AppState>().processes.lock() {
                reconcile_stale_leases(&mut processes);
            }
            Ok(())
        })
        .run(context)
        .expect("error while running ClipGauge");
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::io::{Cursor, Read};
    use std::thread;

    #[cfg(target_os = "linux")]
    use super::packaged_resource_dir;
    use super::{
        append_output_preference_arg, canonical_provider_id, generate_support_bundle_at,
        ig_connect_args, ig_failure_message, instagram_connection_from_json,
        instagram_connection_is_valid, is_completion_payload, migrate_legacy_data_from,
        privacy_summary, read_bounded_line, selected_provider_env, setup_start_failure_message,
        spawn_blocking_result, valid_setup_tool_args, valid_start_setup_args,
        validate_browser_session, ResumeJobRequest, RunJobRequest,
    };
    use serde_json::json;

    #[test]
    fn sidecar_json_lines_are_bounded_and_recover_after_oversize_input() {
        let input = format!(
            "{}\n{{\"event\":\"terminal\"}}\n",
            "x".repeat(super::sidecar::MAX_DIAGNOSTIC_BYTES + 1)
        );
        let mut reader = std::io::BufReader::new(Cursor::new(input));
        let mut line = Vec::new();

        assert_eq!(
            read_bounded_line(
                &mut reader,
                super::sidecar::MAX_DIAGNOSTIC_BYTES,
                &mut line,
                || {},
            )
            .unwrap(),
            Some(false)
        );
        assert_eq!(
            read_bounded_line(
                &mut reader,
                super::sidecar::MAX_DIAGNOSTIC_BYTES,
                &mut line,
                || {},
            )
            .unwrap(),
            Some(true)
        );
        assert_eq!(line, br#"{"event":"terminal"}"#);
    }

    #[cfg(target_os = "windows")]
    #[test]
    fn windows_profile_resolution_ignores_shell_home() {
        let resolved = super::profile_home_from_env(
            Some(std::ffi::OsString::from(r"C:\\fake-terminal-home")),
            Some(std::ffi::OsString::from(r"C:\\fake-windows-profile")),
        );
        assert_eq!(
            resolved,
            std::path::PathBuf::from(r"C:\\fake-windows-profile")
        );
    }

    #[cfg(not(feature = "qualification-vault"))]
    #[test]
    fn application_home_uses_profile_root_by_default() {
        let profile = std::path::PathBuf::from(r"C:\\fake-windows-profile");
        assert_eq!(
            super::application_home_from_env(
                Some(std::ffi::OsString::from(r"C:\\fake-qa-home")),
                profile.clone(),
            ),
            profile.join(".clipgauge")
        );
    }

    #[cfg(feature = "qualification-vault")]
    #[test]
    fn qualification_home_accepts_absolute_isolated_root() {
        let profile = std::path::PathBuf::from(r"C:\\fake-windows-profile");
        let isolated = std::path::PathBuf::from(r"C:\\qa-output\\clipgauge-home");
        assert_eq!(
            super::application_home_from_env(Some(isolated.as_os_str().to_os_string()), profile,),
            isolated
        );
    }

    #[cfg(target_os = "windows")]
    #[test]
    fn windows_onboarding_marker_survives_cross_launch_home_change() {
        let root = std::env::temp_dir().join(format!(
            "clipgauge-profile-resolution-{}",
            super::diagnostics::diagnostic_id()
        ));
        let profile = root.join("windows-profile");
        let first_profile = super::profile_home_from_env(
            Some(std::ffi::OsString::from(r"C:\\fake-terminal-home")),
            Some(profile.as_os_str().to_os_string()),
        );
        let first_data_root = first_profile.join(".clipgauge");
        super::mark_onboarded_at(&first_data_root).unwrap();

        let second_profile = super::profile_home_from_env(
            Some(std::ffi::OsString::from(r"C:\\different-terminal-home")),
            Some(profile.as_os_str().to_os_string()),
        );
        let second_data_root = second_profile.join(".clipgauge");

        assert_eq!(first_data_root, second_data_root);
        assert!(super::onboarded_marker_exists(&second_data_root));
        let _ = fs::remove_dir_all(root);
    }

    #[cfg(target_os = "windows")]
    #[test]
    fn windows_onboarding_commands_share_profile_root_across_launches() {
        let root = std::env::temp_dir().join(format!(
            "clipgauge-onboarding-resolution-{}",
            super::diagnostics::diagnostic_id()
        ));
        let profile = root.join("windows-profile");
        let previous_home = std::env::var_os("HOME");
        let previous_userprofile = std::env::var_os("USERPROFILE");

        std::env::set_var("HOME", r"C:\\fake-terminal-home");
        std::env::set_var("USERPROFILE", profile.as_os_str());
        let mark_result = tauri::async_runtime::block_on(super::mark_onboarded());

        std::env::set_var("HOME", r"C:\\different-terminal-home");
        let state_result = super::get_setup_state_blocking();

        match previous_home {
            Some(value) => std::env::set_var("HOME", value),
            None => std::env::remove_var("HOME"),
        }
        match previous_userprofile {
            Some(value) => std::env::set_var("USERPROFILE", value),
            None => std::env::remove_var("USERPROFILE"),
        }

        mark_result.unwrap();
        let state = state_result.unwrap();
        assert_eq!(state["onboarded"], true);
        assert!(profile.join(".clipgauge/onboarded").exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn blocking_bridge_helper_runs_work_on_a_worker_thread() {
        let caller = thread::current().id();
        let worker = tauri::async_runtime::block_on(spawn_blocking_result(|| {
            Ok::<_, String>(thread::current().id())
        }))
        .unwrap();

        assert_ne!(worker, caller);
    }

    #[test]
    fn blocking_bridge_helper_preserves_worker_errors() {
        let result = tauri::async_runtime::block_on(spawn_blocking_result(|| {
            Err::<(), _>("worker failed".to_string())
        }));

        assert_eq!(result, Err("worker failed".to_string()));
    }

    #[test]
    fn start_setup_rejects_read_only_commands() {
        assert!(!valid_start_setup_args(&["inventory".to_string()]));
        assert!(!valid_start_setup_args(&["youtube-status".to_string()]));
        assert!(!valid_start_setup_args(&["youtube-test".to_string()]));
        assert!(valid_start_setup_args(&["install-runtime".to_string()]));
    }

    #[test]
    fn setup_start_failure_uses_safe_user_copy() {
        let message = setup_start_failure_message();
        assert!(!message.contains("C:\\Users"));
        assert!(!message.contains("token="));
        assert!(message.contains("diagnostic ID"));
    }

    #[test]
    fn local_privacy_summary_does_not_claim_cloud_transfer() {
        let summary =
            privacy_summary(Some("clipgauge-local".to_string()), None, None, None).unwrap();
        let text = summary.to_string();

        assert!(text.contains("scores on this computer"));
        assert!(!text.contains("provider endpoint receives transcript slices"));
        assert!(!text.contains("selected frames leave the device"));
    }

    #[test]
    fn setup_tool_accepts_gpu_diagnostics_and_repair() {
        assert!(valid_setup_tool_args(&["gpu-status".to_string()]));
        assert!(valid_setup_tool_args(&["gpu-repair".to_string()]));
        assert!(!valid_setup_tool_args(&[
            "gpu-repair".to_string(),
            "unexpected".to_string()
        ]));
    }

    #[test]
    fn canonical_provider_ids_are_stable_for_bare_and_preset_forms() {
        assert_eq!(
            canonical_provider_id("openrouter").unwrap(),
            "preset-openrouter"
        );
        assert_eq!(
            canonical_provider_id("preset-openrouter").unwrap(),
            "preset-openrouter"
        );
        assert!(canonical_provider_id("../openrouter").is_err());
    }

    #[test]
    fn browser_session_validation_is_explicit_and_allowlisted() {
        assert_eq!(validate_browser_session(None).unwrap(), None);
        assert_eq!(
            validate_browser_session(Some("firefox"))
                .unwrap()
                .as_deref(),
            Some("firefox")
        );
        assert!(validate_browser_session(Some("safari")).is_err());
    }

    #[test]
    fn selected_provider_env_uses_canonical_profile_id() {
        assert_eq!(
            selected_provider_env(Some("openrouter")),
            Some((
                "CLIPGAUGE_OPENROUTER_API_KEY",
                "preset-openrouter".to_string()
            ))
        );
        assert_eq!(
            selected_provider_env(Some("preset-groq")),
            Some(("CLIPGAUGE_GROQ_API_KEY", "preset-groq".to_string()))
        );
    }

    #[test]
    fn edit_result_payload_is_a_valid_stream_completion() {
        assert!(is_completion_payload(
            &json!({"event": "terminal", "ok": true})
        ));
        assert!(is_completion_payload(
            &json!({"event": "result", "ok": true})
        ));
        assert!(!is_completion_payload(
            &json!({"event": "progress", "ok": true})
        ));
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn debian_resource_layout_is_discovered_from_usr_bin_launcher() {
        let root = std::env::temp_dir().join(format!(
            "clipgauge-resource-{}",
            super::diagnostics::diagnostic_id()
        ));
        let exe = root.join("usr/bin/clipgauge-app");
        let resources = root.join("usr/lib/ClipGauge/resources");
        fs::create_dir_all(exe.parent().unwrap()).unwrap();
        fs::create_dir_all(resources.join("pipeline")).unwrap();
        fs::create_dir_all(resources.join("bin")).unwrap();
        fs::write(resources.join("bin/uv"), b"uv").unwrap();
        assert_eq!(packaged_resource_dir(&exe, "linux", "uv"), resources);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn meta_secret_is_not_part_of_child_arguments() {
        let args = ig_connect_args(vec!["uv".into()], "app-id".into());
        assert!(args.iter().any(|arg| arg == "--app-secret-stdin"));
        assert!(!args.iter().any(|arg| arg == "super-secret"));
        assert!(!args.iter().any(|arg| arg == "--app-secret"));
    }

    #[test]
    fn instagram_status_requires_nonempty_identity_and_token() {
        assert!(!instagram_connection_is_valid(&json!({})));
        assert!(!instagram_connection_is_valid(&json!({"user_id": "42"})));
        assert!(!instagram_connection_is_valid(
            &json!({"access_token": "token"})
        ));
        assert!(!instagram_connection_is_valid(
            &json!({"user_id": "", "access_token": "token"})
        ));
        assert!(instagram_connection_is_valid(
            &json!({"user_id": "42", "access_token": "token"})
        ));
    }

    #[test]
    fn instagram_connection_parser_rejects_malformed_oauth_output() {
        assert!(instagram_connection_from_json("not-json").is_err());
        assert!(instagram_connection_from_json(r#"{"user_id":"42"}"#).is_err());
        assert!(
            instagram_connection_from_json(r#"{"user_id":"42","access_token":"token"}"#).is_ok()
        );
    }

    #[test]
    fn support_bundle_excludes_known_secrets() {
        let root = std::env::temp_dir().join(format!(
            "clipgauge-support-{}",
            super::diagnostics::diagnostic_id()
        ));
        let diagnostic_id = super::diagnostics::diagnostic_id();
        fs::create_dir_all(root.join("diagnostics")).unwrap();
        fs::write(
            root.join("diagnostics")
                .join(format!("{diagnostic_id}.log")),
            "key=AIzaKnownSecret Authorization: Bearer oauth-known transcript=private words",
        )
        .unwrap();
        let bundle = generate_support_bundle_at(&root, None, None).unwrap();
        let file = fs::File::open(bundle).unwrap();
        let mut archive = zip::ZipArchive::new(file).unwrap();
        let mut report = String::new();
        archive
            .by_name("report.json")
            .unwrap()
            .read_to_string(&mut report)
            .unwrap();
        let mut diagnostic = String::new();
        let diagnostic_name = format!("diagnostics/{diagnostic_id}.log");
        archive
            .by_name(&diagnostic_name)
            .unwrap()
            .read_to_string(&mut diagnostic)
            .unwrap();
        let contents = format!("{report}{diagnostic}");
        assert!(!contents.contains("AIzaKnownSecret"));
        assert!(!contents.contains("oauth-known"));
        assert!(!contents.contains("private words"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn support_bundle_includes_requested_job_diagnostic() {
        let root = std::env::temp_dir().join(format!(
            "clipgauge-support-job-{}",
            super::diagnostics::diagnostic_id()
        ));
        let job_id = "20260818-155237-c6b118";
        let diagnostic_id = super::diagnostics::diagnostic_id();
        let diagnostic_dir = root.join("jobs").join(job_id).join("diagnostics");
        fs::create_dir_all(&diagnostic_dir).unwrap();
        fs::write(
            diagnostic_dir.join(format!("{diagnostic_id}.log")),
            "stage=speakers code=SPEAKER_MODEL_LOAD_FAILED",
        )
        .unwrap();
        let bundle = generate_support_bundle_at(
            &root,
            Some(job_id.to_string()),
            Some(diagnostic_id.clone()),
        )
        .unwrap();
        let file = fs::File::open(bundle).unwrap();
        let mut archive = zip::ZipArchive::new(file).unwrap();
        let name = format!("jobs/{job_id}/diagnostics/{diagnostic_id}.log");
        assert!(archive.by_name(&name).is_ok());
        let mut report = String::new();
        archive
            .by_name("report.json")
            .unwrap()
            .read_to_string(&mut report)
            .unwrap();
        assert!(report.contains(&diagnostic_id));
        assert!(report.contains("\"missing_diagnostic\": null"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn support_bundle_finds_requested_root_diagnostic_beyond_sample_limit() {
        let root = std::env::temp_dir().join(format!(
            "clipgauge-support-root-limit-{}",
            super::diagnostics::diagnostic_id()
        ));
        let requested_id = "diag-ffffffffffffffff".to_string();
        let diagnostics_dir = root.join("diagnostics");
        fs::create_dir_all(&diagnostics_dir).unwrap();
        for index in 1..=8 {
            let filler_id = format!("diag-000000000000000{index}");
            fs::write(
                diagnostics_dir.join(format!("{filler_id}.log")),
                "stage=filler",
            )
            .unwrap();
        }
        fs::write(
            diagnostics_dir.join(format!("{requested_id}.log")),
            "stage=requested",
        )
        .unwrap();

        let bundle = generate_support_bundle_at(&root, None, Some(requested_id.clone())).unwrap();
        let file = fs::File::open(bundle).unwrap();
        let mut archive = zip::ZipArchive::new(file).unwrap();
        let name = format!("diagnostics/{requested_id}.log");
        assert!(archive.by_name(&name).is_ok());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn support_bundle_excludes_unrelated_job_diagnostics() {
        let root = std::env::temp_dir().join(format!(
            "clipgauge-support-jobs-{}",
            super::diagnostics::diagnostic_id()
        ));
        let requested_job = "20260818-155237-c6b118";
        let unrelated_job = "20260818-155238-d7c229";
        let requested_id = super::diagnostics::diagnostic_id();
        let unrelated_id = super::diagnostics::diagnostic_id();
        for (job_id, diagnostic_id) in [
            (requested_job, &requested_id),
            (unrelated_job, &unrelated_id),
        ] {
            let directory = root.join("jobs").join(job_id).join("diagnostics");
            fs::create_dir_all(&directory).unwrap();
            fs::write(directory.join(format!("{diagnostic_id}.log")), "stage=test").unwrap();
        }
        let bundle = generate_support_bundle_at(
            &root,
            Some(requested_job.to_string()),
            Some(requested_id.clone()),
        )
        .unwrap();
        let file = fs::File::open(bundle).unwrap();
        let mut archive = zip::ZipArchive::new(file).unwrap();
        let requested_name = format!("jobs/{requested_job}/diagnostics/{requested_id}.log");
        let unrelated_name = format!("jobs/{unrelated_job}/diagnostics/{unrelated_id}.log");
        assert!(archive.by_name(&requested_name).is_ok());
        assert!(archive.by_name(&unrelated_name).is_err());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn support_bundle_reports_missing_requested_diagnostic() {
        let root = std::env::temp_dir().join(format!(
            "clipgauge-support-missing-{}",
            super::diagnostics::diagnostic_id()
        ));
        let job_id = "20260818-155237-c6b118";
        let requested_id = super::diagnostics::diagnostic_id();
        fs::create_dir_all(root.join("jobs").join(job_id).join("diagnostics")).unwrap();
        let bundle =
            generate_support_bundle_at(&root, Some(job_id.to_string()), Some(requested_id.clone()))
                .unwrap();
        let file = fs::File::open(bundle).unwrap();
        let mut archive = zip::ZipArchive::new(file).unwrap();
        let mut report = String::new();
        archive
            .by_name("report.json")
            .unwrap()
            .read_to_string(&mut report)
            .unwrap();
        assert!(report.contains(&format!("\"missing_diagnostic\": \"{requested_id}\"")));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn legacy_migration_is_retryable_and_preserves_source_on_collision() {
        let root = std::env::temp_dir().join(format!(
            "clipgauge-migration-{}",
            super::diagnostics::diagnostic_id()
        ));
        let legacy = root.join("legacy");
        let destination = root.join("new");
        fs::create_dir_all(legacy.join("jobs/job-1")).unwrap();
        fs::write(legacy.join("jobs/job-1/checkpoint.json"), b"old-data").unwrap();
        migrate_legacy_data_from(&legacy, &destination).unwrap();
        assert_eq!(
            fs::read(destination.join("jobs/job-1/checkpoint.json")).unwrap(),
            b"old-data"
        );
        assert!(legacy.join("jobs/job-1/checkpoint.json").exists());
        assert!(destination
            .join("migrations/legacy-publikclip-v1.done")
            .exists());

        let collision_root = root.join("collision");
        let collision_legacy = collision_root.join("legacy");
        let collision_destination = collision_root.join("new");
        fs::create_dir_all(&collision_legacy).unwrap();
        fs::create_dir_all(&collision_destination).unwrap();
        fs::write(collision_legacy.join("settings.json"), b"source").unwrap();
        fs::write(collision_destination.join("settings.json"), b"different").unwrap();
        assert!(migrate_legacy_data_from(&collision_legacy, &collision_destination).is_err());
        assert!(!collision_destination
            .join("migrations/legacy-publikclip-v1.done")
            .exists());
        assert_eq!(
            fs::read(collision_legacy.join("settings.json")).unwrap(),
            b"source"
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn ig_failure_message_redacts_the_exact_stdin_secret() {
        let secret = "meta-secret-exact-value";
        let stderr =
            format!("provider=Meta status=401 Authorization: Bearer {secret} app_secret={secret}");
        let public = ig_failure_message(&stderr, "", Some(1));
        assert!(!public.contains(secret));
        assert!(public.contains("Instagram connection failed"));
        assert!(public.contains("401"));
        assert!(public.contains("provider=Meta"));
    }

    #[test]
    fn typed_job_requests_reject_unknown_fields() {
        let run = json!({"source": "clip.mp4", "provider": "ollama", "unexpected": true});
        let resume = json!({"job_id": "20260819-120000-abcdef", "unexpected": true});
        assert!(serde_json::from_value::<RunJobRequest>(run).is_err());
        assert!(serde_json::from_value::<ResumeJobRequest>(resume).is_err());
    }

    #[test]
    fn typed_job_requests_accept_provider_fields() {
        let run = json!({
            "source": "clip.mp4",
            "llm": "ollama",
            "provider": "ollama",
            "model": "llama3.2",
            "endpoint": "http://127.0.0.1:11434",
            "auth": "none",
            "secret_header": null,
            "captions": "classic",
            "output_preference": "more"
        });
        let parsed = serde_json::from_value::<RunJobRequest>(run).unwrap();
        assert_eq!(parsed.source, "clip.mp4");
        assert_eq!(parsed.provider.as_deref(), Some("ollama"));
        assert_eq!(parsed.model.as_deref(), Some("llama3.2"));
        assert_eq!(parsed.output_preference.as_deref(), Some("more"));

        let resume = json!({
            "job_id": "20260819-120000-abcdef",
            "provider": "custom",
            "model": "manual",
            "camera": "locked",
            "output_preference": "best"
        });
        let parsed = serde_json::from_value::<ResumeJobRequest>(resume).unwrap();
        assert_eq!(parsed.job_id, "20260819-120000-abcdef");
        assert_eq!(parsed.camera.as_deref(), Some("locked"));
        assert_eq!(parsed.output_preference.as_deref(), Some("best"));
    }

    #[test]
    fn output_preference_is_forwarded_as_a_cli_argument() {
        let mut args = Vec::new();
        append_output_preference_arg(&mut args, Some("more".to_string()));
        assert_eq!(args, vec!["--output-preference", "more"]);
    }
}
