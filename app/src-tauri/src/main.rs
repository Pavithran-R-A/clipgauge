// ClipGauge desktop shell. The pipeline is a Python sidecar speaking JSONL
// on stdout (`clipgauge --jsonl ...`); this shell spawns it, forwards every
// event to the frontend, and exposes small filesystem/settings commands.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod artifact;
mod diagnostics;
mod edit_schema;
mod path_security;
mod process_manager;
mod secrets;

use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter, Manager, State};

#[derive(Clone)]
struct AppState {
    processes: Arc<Mutex<process_manager::ProcessManager>>,
}

impl AppState {
    fn new() -> Self {
        Self {
            processes: Arc::new(Mutex::new(process_manager::ProcessManager::new())),
        }
    }
}

fn home_dir() -> PathBuf {
    // The desktop owns one stable root. Direct Python CLI tests may still use
    // CLIPGAUGE_HOME, but packaged Rust commands never accept an arbitrary
    // user-provided root that could escape the asset scope.
    dirs_home().join(".clipgauge")
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
    // HOME on Unix; Windows services and some launch paths only set USERPROFILE.
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/"))
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
    cmd
}

/// Where the Python pipeline lives and how to invoke it.
/// Dev builds call `uv run` against the repo's pipeline/ directory. Packaged
/// builds invoke the bundled python env (M6); resolution stays in one place.
fn pipeline_invocation() -> (String, Vec<String>) {
    if cfg!(debug_assertions) {
        let pipeline_dir: PathBuf = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../pipeline")
            .canonicalize()
            .unwrap_or_else(|_| PathBuf::from("../pipeline"));
        (
            "uv".to_string(),
            vec![
                "--directory".to_string(),
                pipeline_dir.to_string_lossy().to_string(),
                "run".to_string(),
                "clipgauge".to_string(),
            ],
        )
    } else {
        // Packaged: bundled uv + pipeline source under the platform's
        // resource layout — macOS keeps them in the .app's Resources dir,
        // Windows (NSIS) lands them in resources\ next to the exe. The venv
        // bootstraps into CLIPGAUGE_HOME on first run (uv handles Python
        // 3.12 download + deps; the onboarding screen owns expectations).
        let exe_dir = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.to_path_buf()))
            .unwrap_or_else(|| PathBuf::from("."));
        let resources = if cfg!(target_os = "macos") {
            exe_dir.join("../Resources/resources")
        } else {
            exe_dir.join("resources")
        };
        let uv = if cfg!(target_os = "windows") {
            "bin/uv.exe"
        } else {
            "bin/uv"
        };
        (
            resources.join(uv).to_string_lossy().to_string(),
            vec![
                "--directory".to_string(),
                resources.join("pipeline").to_string_lossy().to_string(),
                "run".to_string(),
                "clipgauge".to_string(),
            ],
        )
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

fn generate_support_bundle_at(root: &Path, job_id: Option<String>) -> Result<String, String> {
    if let Some(id) = &job_id {
        let _ = path_security::resolve_job_dir(root, id)?;
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
    let report = json!({
        "app_version": env!("CARGO_PKG_VERSION"),
        "os": std::env::consts::OS,
        "architecture": std::env::consts::ARCH,
        "protocol_version": 1,
        "bundle_id": bundle_id,
        "job_id": job_id,
        "jobs": sanitized_job_metadata(root),
        "exclusions": ["API keys", "OAuth tokens", "raw transcripts", "source media", "arbitrary filesystem contents"],
    });
    archive
        .start_file("report.json", options)
        .map_err(|error| error.to_string())?;
    archive
        .write_all(serde_json::to_string_pretty(&report).unwrap().as_bytes())
        .map_err(|error| error.to_string())?;
    archive
        .start_file("README.txt", options)
        .map_err(|error| error.to_string())?;
    archive.write_all(b"ClipGauge support bundle. This archive contains sanitized metadata and redacted diagnostic tails only.\n").map_err(|error| error.to_string())?;
    if let Ok(entries) = fs::read_dir(root.join("diagnostics")) {
        for entry in entries.flatten().take(8) {
            let path = entry.path();
            if path.extension().and_then(|value| value.to_str()) != Some("log") {
                continue;
            }
            let Ok(text) = fs::read_to_string(&path) else {
                continue;
            };
            let redacted = diagnostics::redact(&text);
            let safe_lines = redacted
                .lines()
                .filter(|line| {
                    let lower = line.to_ascii_lowercase();
                    !lower.contains("transcript") && !line.contains("S0:") && !line.contains("S1:")
                })
                .collect::<Vec<_>>()
                .join("\n");
            let tail: String = safe_lines
                .chars()
                .rev()
                .take(64 * 1024)
                .collect::<String>()
                .chars()
                .rev()
                .collect();
            let name = format!("diagnostics/{}", entry.file_name().to_string_lossy());
            archive
                .start_file(name, options)
                .map_err(|error| error.to_string())?;
            archive
                .write_all(tail.as_bytes())
                .map_err(|error| error.to_string())?;
        }
    }
    archive.finish().map_err(|error| error.to_string())?;
    fs::rename(&temp, &path).map_err(|error| error.to_string())?;
    Ok(path.to_string_lossy().to_string())
}

#[tauri::command]
fn generate_support_bundle(job_id: Option<String>) -> Result<String, String> {
    generate_support_bundle_at(&home_dir(), job_id)
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

#[tauri::command]
fn preflight(
    llm: Option<String>,
    provider: Option<String>,
    model: Option<String>,
    endpoint: Option<String>,
    auth: Option<String>,
    secret_header: Option<String>,
) -> Result<Value, String> {
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
    let mut command = quiet_command(&program);
    secrets::apply_operation_env(&mut command);
    let output = command
        .env("CLIPGAUGE_HOME", home_dir())
        .args(&args)
        .output()
        .map_err(|error| diagnostics::redact(&error.to_string()))?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let line = stdout
        .lines()
        .rev()
        .find(|line| line.trim_start().starts_with('{'))
        .ok_or_else(|| "preflight returned no JSON result".to_string())?;
    serde_json::from_str(line).map_err(|error| diagnostics::redact(&error.to_string()))
}

#[tauri::command]
fn test_connection(
    llm: Option<String>,
    provider: Option<String>,
    model: Option<String>,
    endpoint: Option<String>,
    auth: Option<String>,
    secret_header: Option<String>,
) -> Result<Value, String> {
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
    let output = command
        .env("CLIPGAUGE_HOME", home_dir())
        .args(&args)
        .output()
        .map_err(|error| diagnostics::redact(&error.to_string()))?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let line = stdout
        .lines()
        .rev()
        .find(|line| line.trim_start().starts_with('{'))
        .ok_or_else(|| "provider test returned no JSON result".to_string())?;
    serde_json::from_str(line).map_err(|error| diagnostics::redact(&error.to_string()))
}

#[tauri::command]
fn run_job(
    app: AppHandle,
    state: State<'_, AppState>,
    source: String,
    llm: Option<String>,
    provider: Option<String>,
    model: Option<String>,
    endpoint: Option<String>,
    auth: Option<String>,
    secret_header: Option<String>,
    captions: Option<String>,
) -> Result<(), String> {
    let (program, base_args) = pipeline_invocation();
    let processes = state.processes.clone();
    let key = format!("run:{}", diagnostics::diagnostic_id());
    reserve_process(&processes, key.clone())?;
    std::thread::spawn(move || {
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
    job_id: String,
    llm: Option<String>,
    provider: Option<String>,
    model: Option<String>,
    endpoint: Option<String>,
    auth: Option<String>,
    secret_header: Option<String>,
    captions: Option<String>,
    camera: Option<String>,
) -> Result<(), String> {
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
    let temp = path.with_extension("json.tmp");
    if let Ok(payload) = serde_json::to_vec_pretty(&lease) {
        if fs::write(&temp, payload).is_ok() {
            let _ = fs::rename(&temp, &path);
        }
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
            let temp = path.with_extension("json.tmp");
            if let Ok(payload) = serde_json::to_vec_pretty(&stale) {
                if fs::write(&temp, payload).is_ok() {
                    let _ = fs::rename(temp, path);
                }
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

fn selected_provider_env(provider: Option<&str>) -> Option<(&'static str, String)> {
    let kind = provider?;
    let env_name = match kind {
        "gemini" => "CLIPGAUGE_GEMINI_API_KEY",
        "openrouter" => "CLIPGAUGE_OPENROUTER_API_KEY",
        "groq" => "CLIPGAUGE_GROQ_API_KEY",
        "cloudflare" => "CLIPGAUGE_CLOUDFLARE_API_TOKEN",
        "huggingface" => "CLIPGAUGE_HF_TOKEN",
        "cerebras" => "CLIPGAUGE_CEREBRAS_API_KEY",
        _ => "CLIPGAUGE_PROVIDER_SECRET",
    };
    Some((env_name, format!("preset-{kind}")))
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
                    "protocol_version": 1,
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
    let mut terminal_payload: Option<Value> = None;
    if let Some(stdout) = child.stdout.take() {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            if let Ok(value) = serde_json::from_str::<Value>(&line) {
                if value.get("event").and_then(Value::as_str) == Some("terminal") {
                    terminal_payload = Some(value);
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
                "protocol_version": 1,
                "ok": false,
                "stage": "pipeline",
                "code": "CANCELLED",
                "message": "The job was cancelled. Completed checkpoints remain available for resume.",
                "retryable": true,
            }),
        );
    } else if let Some(payload) = terminal_payload {
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
                "protocol_version": 1,
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
fn job_results(job_id: String) -> Result<Value, String> {
    artifact::job_results(&home_dir(), &job_id)
}

#[tauri::command]
fn list_job_dirs() -> Result<Vec<Value>, String> {
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
            let lifecycle = fs::read_to_string(dir.join("lifecycle.json"))
                .ok()
                .and_then(|text| serde_json::from_str::<Value>(&text).ok());
            let lifecycle_state = lifecycle
                .as_ref()
                .and_then(|value| value["state"].as_str())
                .unwrap_or(if has_render { "COMPLETED" } else { "RESUMABLE" });
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
fn save_gemini_key(key: String) -> Result<bool, String> {
    secrets::set(secrets::SecretName::GeminiApiKey, key.trim())?;
    Ok(true)
}

#[tauri::command]
fn save_provider_key(profile_id: String, key: String) -> Result<bool, String> {
    if profile_id.is_empty()
        || profile_id.len() > 120
        || !profile_id
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | ':' | '.'))
    {
        return Err("provider profile id is invalid".to_string());
    }
    secrets::set_provider_auth(&profile_id, key.trim())?;
    Ok(true)
}

#[tauri::command]
fn get_setup_state() -> Result<Value, String> {
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
        let id = format!("preset-{kind}");
        let has = secrets::get_provider_auth(&id)?.is_some();
        provider_keys.insert(kind.to_string(), Value::Bool(has));
    }
    let onboarded = home_dir().join("onboarded").exists();
    Ok(json!({"has_gemini_key": has_key, "onboarded": onboarded, "provider_keys": provider_keys}))
}

#[tauri::command]
fn mark_onboarded() -> Result<(), String> {
    let home = home_dir();
    fs::create_dir_all(&home).map_err(|e| e.to_string())?;
    fs::write(home.join("onboarded"), "1").map_err(|e| e.to_string())
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
}

/// Sync pipeline call that returns one JSON blob (edit context, visual
/// suggestions). Long-running render-clip goes through run_edit_render
/// instead so progress streams.
#[tauri::command]
async fn edit_tool(args: Vec<String>) -> Result<Value, String> {
    let (program, base_args) = pipeline_invocation();
    let mut full = base_args;
    full.push("edit".to_string());
    full.extend(args);
    let mut command = quiet_command(&program);
    secrets::apply_operation_env(&mut command);
    let out = command
        .env("CLIPGAUGE_HOME", home_dir())
        .args(&full)
        .output()
        .map_err(|e| e.to_string())?;
    let stdout = String::from_utf8_lossy(&out.stdout);
    // last JSON line is the payload (progress lines may precede it)
    let line = stdout
        .lines()
        .rev()
        .find(|l| l.trim_start().starts_with('{'));
    match line.and_then(|l| serde_json::from_str::<Value>(l).ok()) {
        Some(v) => Ok(v),
        None => Err(format!(
            "edit tool produced no JSON: {}",
            String::from_utf8_lossy(&out.stderr)
                .chars()
                .take(400)
                .collect::<String>()
        )),
    }
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
fn save_clip_edits(job_id: String, input: edit_schema::SaveClipEditsInput) -> Result<(), String> {
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
    let temp = path.with_extension("json.tmp");
    fs::write(
        &temp,
        serde_json::to_vec_pretty(&current).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    fs::rename(&temp, &path).map_err(|e| e.to_string())
}

#[tauri::command]
fn save_pexels_key(key: String) -> Result<bool, String> {
    secrets::set(secrets::SecretName::PexelsApiKey, key.trim())?;
    Ok(true)
}

#[tauri::command]
fn ig_status() -> Result<Value, String> {
    let connected = secrets::get(secrets::SecretName::InstagramConnection)?
        .and_then(|raw| serde_json::from_str::<Value>(&raw).ok());
    match connected {
        Some(v) => Ok(json!({
            "connected": true,
            "username": v["username"],
            "obtained_at": v["token_obtained_at"],
        })),
        None => Ok(json!({"connected": false})),
    }
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
    let (program, base_args) = pipeline_invocation();
    let args = ig_connect_args(base_args, app_id);
    let connection_output = home_dir().join(format!(
        ".instagram-connection-{}.json",
        uuid::Uuid::new_v4()
    ));

    let mut command = quiet_command(&program);
    secrets::apply_operation_env(&mut command);
    let mut child = command
        .env("CLIPGAUGE_HOME", home_dir())
        .env("CLIPGAUGE_CONNECTION_OUTPUT", &connection_output)
        .args(&args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| diagnostics::redact(&e.to_string()))?;
    if let Some(mut stdin) = child.stdin.take() {
        stdin
            .write_all(app_secret.as_bytes())
            .map_err(|e| diagnostics::redact(&e.to_string()))?;
    }
    let out = child
        .wait_with_output()
        .map_err(|e| diagnostics::redact(&e.to_string()))?;
    let stdout = String::from_utf8_lossy(&out.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&out.stderr).trim().to_string();
    if out.status.success() {
        let persisted = fs::read_to_string(&connection_output)
            .map_err(|error| diagnostics::redact(&error.to_string()))?;
        secrets::set(secrets::SecretName::InstagramConnection, &persisted)?;
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
    let (program, base_args) = pipeline_invocation();
    let mut full = base_args;
    full.push("ig".to_string());
    full.extend(args);
    let mut command = quiet_command(&program);
    secrets::apply_operation_env(&mut command);
    let out = command
        .env("CLIPGAUGE_HOME", home_dir())
        .args(&full)
        .output()
        .map_err(|e| e.to_string())?;
    let stdout = String::from_utf8_lossy(&out.stdout);
    let line = stdout
        .lines()
        .rev()
        .find(|l| l.trim_start().starts_with('{'));
    match line.and_then(|l| serde_json::from_str::<Value>(l).ok()) {
        Some(v) => Ok(v),
        None => Err(format!(
            "ig tool produced no JSON: {}",
            String::from_utf8_lossy(&out.stderr)
                .chars()
                .take(400)
                .collect::<String>()
        )),
    }
}

#[tauri::command]
fn export_clip(job_id: String, clip: u32, title: Option<String>) -> Result<String, String> {
    artifact::export_clip(
        &home_dir(),
        &dirs_home().join("Downloads"),
        &job_id,
        clip,
        title,
    )
}

fn main() {
    tauri::Builder::default()
        .manage(AppState::new())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            preflight,
            privacy_summary,
            test_connection,
            generate_support_bundle,
            run_job,
            resume_job,
            cancel_job,
            job_results,
            list_job_dirs,
            save_gemini_key,
            save_provider_key,
            get_setup_state,
            mark_onboarded,
            check_ollama,
            ig_status,
            ig_connect,
            ig_tool,
            edit_tool,
            run_edit_render,
            save_clip_edits,
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
        .run(tauri::generate_context!())
        .expect("error while running ClipGauge");
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::io::Read;

    use super::{
        generate_support_bundle_at, ig_connect_args, ig_failure_message, migrate_legacy_data_from,
    };

    #[test]
    fn meta_secret_is_not_part_of_child_arguments() {
        let args = ig_connect_args(vec!["uv".into()], "app-id".into());
        assert!(args.iter().any(|arg| arg == "--app-secret-stdin"));
        assert!(!args.iter().any(|arg| arg == "super-secret"));
        assert!(!args.iter().any(|arg| arg == "--app-secret"));
    }

    #[test]
    fn support_bundle_excludes_known_secrets() {
        let root = std::env::temp_dir().join(format!(
            "clipgauge-support-{}",
            super::diagnostics::diagnostic_id()
        ));
        fs::create_dir_all(root.join("diagnostics")).unwrap();
        fs::write(
            root.join("diagnostics/sample.log"),
            "key=AIzaKnownSecret Authorization: Bearer oauth-known transcript=private words",
        )
        .unwrap();
        let bundle = generate_support_bundle_at(&root, None).unwrap();
        let file = fs::File::open(bundle).unwrap();
        let mut archive = zip::ZipArchive::new(file).unwrap();
        let mut report = String::new();
        archive
            .by_name("report.json")
            .unwrap()
            .read_to_string(&mut report)
            .unwrap();
        let mut diagnostic = String::new();
        archive
            .by_name("diagnostics/sample.log")
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
}
