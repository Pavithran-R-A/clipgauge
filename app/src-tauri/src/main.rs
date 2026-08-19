// publikclip desktop shell. The pipeline is a Python sidecar speaking JSONL
// on stdout (`publikclip --jsonl ...`); this shell spawns it, forwards every
// event to the frontend, and exposes small filesystem/settings commands.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod artifact;
mod diagnostics;
mod path_security;
mod process_manager;
mod secrets;

use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::PathBuf;
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
    // PUBLIKCLIP_HOME, but packaged Rust commands never accept an arbitrary
    // user-provided root that could escape the asset scope.
    dirs_home().join(".publikclip")
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
                "publikclip".to_string(),
            ],
        )
    } else {
        // Packaged: bundled uv + pipeline source under the platform's
        // resource layout — macOS keeps them in the .app's Resources dir,
        // Windows (NSIS) lands them in resources\ next to the exe. The venv
        // bootstraps into PUBLIKCLIP_HOME on first run (uv handles Python
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
                "publikclip".to_string(),
            ],
        )
    }
}

#[tauri::command]
fn run_job(
    app: AppHandle,
    state: State<'_, AppState>,
    source: String,
    llm: Option<String>,
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
        if let Some(mode) = llm {
            args.push("--llm".to_string());
            args.push(mode);
        }
        if let Some(preset) = captions {
            args.push("--captions".to_string());
            args.push(preset);
        }
        stream_pipeline(&app, &program, &args, processes, key);
    });
    Ok(())
}

#[tauri::command]
fn resume_job(
    app: AppHandle,
    state: State<'_, AppState>,
    job_id: String,
    llm: Option<String>,
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
        if let Some(mode) = llm {
            args.push("--llm".to_string());
            args.push(mode);
        }
        if let Some(preset) = captions {
            args.push("--captions".to_string());
            args.push(preset);
        }
        if let Some(cam) = camera {
            args.push("--camera".to_string());
            args.push(cam);
        }
        stream_pipeline(&app, &program, &args, processes, key);
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

fn stream_pipeline(
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
        .env("PUBLIKCLIP_HOME", home_dir())
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
            let title = fs::read_to_string(dir.join("ingest.json"))
                .ok()
                .and_then(|s| serde_json::from_str::<Value>(&s).ok())
                .and_then(|v| v["data"]["title"].as_str().map(String::from));
            out.push(json!({
                "id": id, "title": title,
                "ingested": has_ingest, "rendered": has_render,
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
fn get_setup_state() -> Result<Value, String> {
    let has_key = secrets::get(secrets::SecretName::GeminiApiKey)?.is_some();
    let onboarded = home_dir().join("onboarded").exists();
    Ok(json!({"has_gemini_key": has_key, "onboarded": onboarded}))
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
        .env("PUBLIKCLIP_HOME", home_dir())
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
        stream_pipeline(&app, &program, &args, processes, key);
    });
    Ok(())
}

#[tauri::command]
fn save_clip_edits(job_id: String, edits: Value) -> Result<(), String> {
    let dir = validate_job_id(&job_id)?;
    let path = dir.join("clip_edits.json");
    // Merge: the app sends one clip's state at a time; other clips' edits
    // must survive.
    let mut current: Value = fs::read_to_string(&path)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_else(|| json!({}));
    if let (Some(obj), Some(new)) = (current.as_object_mut(), edits.as_object()) {
        for (k, v) in new {
            obj.insert(k.clone(), v.clone());
        }
    }
    fs::write(&path, serde_json::to_string_pretty(&current).unwrap()).map_err(|e| e.to_string())
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
        .env("PUBLIKCLIP_HOME", home_dir())
        .env("PUBLIKCLIP_CONNECTION_OUTPUT", &connection_output)
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

/// One-shot `publikclip ig <args...>` call returning the CLI's JSON line
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
        .env("PUBLIKCLIP_HOME", home_dir())
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
            run_job,
            resume_job,
            cancel_job,
            job_results,
            list_job_dirs,
            save_gemini_key,
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
            secrets::migrate_legacy(&home_dir()).map_err(std::io::Error::other)?;
            secrets::migrate_instagram_file(&home_dir()).map_err(std::io::Error::other)?;
            if let Ok(mut processes) = app.state::<AppState>().processes.lock() {
                reconcile_stale_leases(&mut processes);
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running publikclip");
}

#[cfg(test)]
mod tests {
    use super::{ig_connect_args, ig_failure_message};

    #[test]
    fn meta_secret_is_not_part_of_child_arguments() {
        let args = ig_connect_args(vec!["uv".into()], "app-id".into());
        assert!(args.iter().any(|arg| arg == "--app-secret-stdin"));
        assert!(!args.iter().any(|arg| arg == "super-secret"));
        assert!(!args.iter().any(|arg| arg == "--app-secret"));
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
